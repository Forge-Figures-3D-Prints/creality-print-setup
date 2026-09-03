#!/usr/bin/env python3
"""Sync Creality Print user presets between this repo and the installed app.

The repo is the source of truth. Presets are stored here grouped by printer
with human-readable folder names; Creality Print stores them flat, grouped by
preset type, under a per-account folder. This script translates between the two.

A preset's identity is its internal "name" field, never its filename. That lets
the repo use friendlier filenames (e.g. a "(PLA)" suffix on the default preset)
while still restoring to exactly the name Creality Print expects.

Usage:
    tools/sync.py status            compare repo against the app, change nothing
    tools/sync.py export            app  -> repo   (capture calibration work)
    tools/sync.py import            repo -> app    (restore onto a new machine)

    -n/--dry-run    print what would happen, write nothing
    --app PATH      use a specific user/<account-id> folder
    --account ID    pick an account when several exist
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import json
import os
import platform
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# app preset folder -> repo folder
KINDS = {
    "machine": "Printer Profiles",
    "filament": "Filament Profiles",
    "process": "Process Profiles",
}
UNSORTED = "_Unsorted"
IGNORE_FILE = ".syncignore"

# Bound to one physical machine or one login - never commit these.
VOLATILE = {"printer_select_mac", "setting_id", "user_id", "sync_info"}

# Bookkeeping that changes on its own and says nothing about the calibration.
META = {"version", "base_id", "from", "is_custom_defined",
        "print_settings_id", "printer_settings_id", "filament_settings_id"}

# "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated" -> "Creality Hi"
# "Creality K1 Max 0.4 nozzle - PLA"                     -> "Creality K1 Max"
# The printer follows "@" when there is one; only then does the name itself
# start with the printer, so "@" must be tried first or the leading
# "0.20mm Standard ..." gets swallowed into the printer name.
AFTER_AT_RE = re.compile(r"@\s*(.+?)\s+\d+(?:\.\d+)?\s*nozzle")
AT_START_RE = re.compile(r"^\s*(.+?)\s+\d+(?:\.\d+)?\s*nozzle")


def ignore_patterns() -> list[str]:
    """Globs from .syncignore, matched against preset names."""
    path = os.path.join(REPO, IGNORE_FILE)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [ln.strip() for ln in fh if ln.strip() and not ln.startswith("#")]


def ignored(name: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


# ---------------------------------------------------------------- discovery

def app_roots() -> list[str]:
    """Every user/<account-id> preset folder of every installed version."""
    home = os.path.expanduser("~")
    if platform.system() == "Darwin":
        base = f"{home}/Library/Application Support/Creality/Creality Print"
    elif platform.system() == "Windows":
        base = os.path.join(os.environ.get("APPDATA", ""), "Creality", "Creality Print")
    else:
        base = f"{home}/.config/Creality/Creality Print"
    roots = [p for p in glob.glob(f"{base}/*/user/*") if os.path.isdir(p)]
    # newest app version first, real accounts before the signed-out "default"
    return sorted(roots, key=lambda p: (os.path.basename(p) == "default", p), reverse=False)


def has_presets(root: str) -> bool:
    return any(glob.glob(os.path.join(root, kind, "*.json")) for kind in KINDS)


def pick_root(args) -> str:
    if args.app:
        return os.path.abspath(os.path.expanduser(args.app))
    roots = app_roots()
    if not roots:
        sys.exit("No Creality Print install found. Pass --app <path to user/<account-id>>.")
    if args.account:
        for r in roots:
            if os.path.basename(r) == args.account:
                return r
        sys.exit(f"No account {args.account!r}. Found: {', '.join(os.path.basename(r) for r in roots)}")
    real = [r for r in roots if os.path.basename(r) != "default"]
    # Creality Print leaves behind account folders holding only sync bookkeeping.
    # They are not a real choice, so don't make the user disambiguate against them.
    populated = [r for r in real if has_presets(r)]
    candidates = populated or real
    if len(candidates) > 1:
        sys.exit(
            "Several accounts found; pick one with --account:\n  "
            + "\n  ".join(os.path.basename(r) for r in candidates)
        )
    return candidates[0] if candidates else roots[0]


# ---------------------------------------------------------------- resolving

def system_roots(app_root: str) -> list[str]:
    """The stock preset folders that ship with Creality Print."""
    version_dir = os.path.dirname(os.path.dirname(app_root))  # .../<version>
    return [p for p in glob.glob(os.path.join(version_dir, "system", "*")) if os.path.isdir(p)]


def build_index(app_root: str) -> dict:
    """{(kind, name): data} for every stock and user preset the app can see."""
    index = {}
    for root in system_roots(app_root) + [app_root]:
        for kind in KINDS:
            for path in glob.glob(os.path.join(root, kind, "*.json")):
                data = load(path)
                if data:
                    index.setdefault((kind, data["name"]), data)
    return index


def resolve(data: dict, kind: str, index: dict) -> dict:
    """Flatten a preset's `inherits` chain into a complete, self-contained preset."""
    chain, seen = [], set()
    node = data
    while node:
        chain.append(node)
        parent = node.get("inherits")
        if not parent or parent in seen:
            break
        seen.add(parent)
        node = index.get((kind, parent))

    merged = {}
    for node in reversed(chain):          # base first, own settings last
        merged.update(node)
    merged["inherits"] = data.get("inherits", "")
    merged["name"] = data["name"]
    return strip(merged)


def strip(data: dict) -> dict:
    return {k: v for k, v in data.items() if k not in VOLATILE}


def norm(value, key: str = "") -> str:
    """Creality writes the same value as a scalar, a 1-list, or a comma string."""
    if isinstance(value, list):
        value = [str(v) for v in value]
        value = value[0] if len(value) == 1 else ",".join(value)
    value = str(value)
    if key == "thumbnails":
        # the exporter rewrites "96x96,300x300" as "96x96/PNG, 300x300/PNG"
        value = re.sub(r"/[A-Z]+", "", value).replace(" ", "")
    return value


def overrides(data: dict, kind: str, index: dict) -> dict:
    """Only the settings this preset actually changes from the stock preset.

    This is the meaningful content of a preset, and the only representation
    that is identical whether the preset came from the app's Export function
    or straight off disk - a full export additionally carries defaults that
    live inside the application binary and exist in no file.
    """
    parent = index.get((kind, data.get("inherits", "")))
    base = resolve(parent, kind, index) if parent else {}
    return {
        k: norm(v, k) for k, v in data.items()
        if k not in META and k != "inherits" and k != "name"
        and norm(v, k) != norm(base.get(k, object()), k)
    }


def differences(a: dict, b: dict, kind: str, index: dict) -> dict:
    """Meaningful setting differences between two copies of the same preset.

    Ignores keys that exist nowhere on disk and are stated by only one side:
    the app's Export function bakes in defaults compiled into the binary, so a
    full export always carries ~28 keys a minimal on-disk preset cannot. Those
    are application defaults, not calibration, and comparing them is noise.
    """
    ao, bo = overrides(a, kind, index), overrides(b, kind, index)
    parent = index.get((kind, a.get("inherits", "")))
    base = resolve(parent, kind, index) if parent else {}
    domain = {k for k in set(ao) | set(bo) if k in base or (k in ao and k in bo)}
    return {k: (ao.get(k), bo.get(k)) for k in domain if ao.get(k) != bo.get(k)}


def is_full(data: dict) -> bool:
    """A resolved export carries the whole config; an on-disk preset is a stub."""
    return len(data) > 30


# ---------------------------------------------------------------- routing

def printer_of(preset: dict) -> str | None:
    """Which printer a preset belongs to, from its name or what it inherits."""
    for field in ("name", "inherits"):
        value = preset.get(field) or ""
        m = AFTER_AT_RE.search(value) or AT_START_RE.match(value)
        if m:
            return m.group(1).strip()
    return None


def load(path: str) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return strip(data) if isinstance(data, dict) and data.get("name") else None
    except (json.JSONDecodeError, OSError):
        return None


def scan_app(root: str) -> dict:
    """{(kind, name): {path, data}} for every user preset in the app."""
    found = {}
    for kind in KINDS:
        for path in sorted(glob.glob(os.path.join(root, kind, "*.json"))):
            data = load(path)
            if data:
                found[(kind, data["name"])] = {"path": path, "data": data}
    return found


def scan_repo() -> dict:
    """{(kind, name): {path, data}} for every preset committed here."""
    found = {}
    for kind, folder in KINDS.items():
        for path in sorted(glob.glob(os.path.join(REPO, "*", folder, "*.json"))):
            data = load(path)
            if data:
                key = (kind, data["name"])
                if key in found:
                    print(f"  ! duplicate {data['name']!r} in repo:\n      {found[key]['path']}\n      {path}")
                found[key] = {"path": path, "data": data}
    return found


def repo_path_for(kind: str, data: dict, existing: dict) -> str:
    """Where a preset belongs in the repo, preserving any filename already used."""
    prior = existing.get((kind, data["name"]))
    if prior:
        return prior["path"]  # keep the cosmetic filename already committed
    printer = printer_of(data) or UNSORTED
    return os.path.join(REPO, printer, KINDS[kind], data["name"] + ".json")


def app_path_for(root: str, kind: str, data: dict) -> str:
    """Where a preset belongs in the app: always named by its internal name."""
    return os.path.join(root, kind, data["name"] + ".json")


# ---------------------------------------------------------------- commands

def write(path: str, data: dict, dry: bool) -> None:
    if dry:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=4, ensure_ascii=False, sort_keys=True)
        fh.write("\n")


def rel(path: str) -> str:
    return os.path.relpath(path, REPO) if path.startswith(REPO) else path


def cmd_status(root: str, _args) -> int:
    app, repo = scan_app(root), scan_repo()
    index = build_index(root)
    patterns = ignore_patterns()
    skipped = sorted(k for k in set(app) - set(repo) if ignored(k[1], patterns))
    only_app = sorted(k for k in set(app) - set(repo) if not ignored(k[1], patterns))
    only_repo = sorted(set(repo) - set(app))

    differing, reformat = [], []
    for key in sorted(set(app) & set(repo)):
        kind, _ = key
        if differences(app[key]["data"], repo[key]["data"], kind, index):
            differing.append(key)
        elif is_full(repo[key]["data"]) != is_full(app[key]["data"]):
            reformat.append(key)

    print(f"app:  {root}")
    print(f"repo: {REPO}\n")
    if only_app:
        print(f"In Creality Print but not in the repo ({len(only_app)}) - `export` to capture:")
        for kind, name in only_app:
            print(f"  + [{kind}] {name}")
    if differing:
        print(f"\nDiffer ({len(differing)}) - app value vs repo value:")
        for kind, name in differing:
            print(f"  ~ [{kind}] {name}")
            for k, (av, rv) in differences(app[(kind, name)]["data"],
                                           repo[(kind, name)]["data"], kind, index).items():
                print(f"        {k}: app={av!r} repo={rv!r}")
    if reformat:
        print(f"\nSame settings, stored differently ({len(reformat)}) - no action needed:")
        for kind, name in reformat:
            shape = "full export" if is_full(repo[(kind, name)]["data"]) else "minimal diff"
            print(f"  = [{kind}] {name}  (repo holds the {shape})")
    if only_repo:
        print(f"\nIn the repo but not in Creality Print ({len(only_repo)}) - `import` to restore:")
        for kind, name in only_repo:
            print(f"  - [{kind}] {name}")
    if not (only_app or only_repo or differing or reformat):
        print(f"In sync - {len(repo)} presets match.")
    if skipped:
        print(f"\nIgnored via {IGNORE_FILE} ({len(skipped)}) - present in Creality Print, not backed up:")
        for kind, name in skipped:
            print(f"  . [{kind}] {name}")
    return 0


def cmd_export(root: str, args) -> int:
    app, repo = scan_app(root), scan_repo()
    index = build_index(root)
    patterns = ignore_patterns()
    added = updated = skipped = 0
    for key in sorted(app):
        kind, name = key
        if key not in repo and ignored(name, patterns):
            skipped += 1
            continue
        data = app[key]["data"]
        # keep whatever shape the repo already uses for this preset
        dest = repo_path_for(kind, data, repo)
        if key not in repo:
            print(f"  + {rel(dest)}")
            added += 1
        elif differences(repo[key]["data"], data, kind, index):
            print(f"  ~ {rel(dest)}")
            updated += 1
        else:
            continue
        write(dest, data, args.dry_run)

    stale = sorted(set(repo) - set(app))
    if stale:
        print(f"\n  Note: {len(stale)} preset(s) are in the repo but not in the app.")
        print("  Left alone - the repo is the source of truth. Delete by hand if retired:")
        for key in stale:
            print(f"      {rel(repo[key]['path'])}")

    print(f"\n{'Would add' if args.dry_run else 'Added'} {added}, "
          f"{'update' if args.dry_run else 'updated'} {updated}"
          f"{f', skipped {skipped} via {IGNORE_FILE}' if skipped else ''}.")
    if not args.dry_run and (added or updated):
        print("Review with `git diff`, then commit.")
    return 0


def cmd_import(root: str, args) -> int:
    app, repo = scan_app(root), scan_repo()
    index = build_index(root)
    added = updated = 0
    for key in sorted(repo):
        kind, _ = key
        data = repo[key]["data"]
        dest = app_path_for(root, kind, data)
        if key not in app:
            print(f"  + {kind}/{os.path.basename(dest)}")
            added += 1
        elif differences(app[key]["data"], data, kind, index):
            print(f"  ~ {kind}/{os.path.basename(dest)}")
            # keep a copy of whatever the app had, in case it was newer
            if not args.dry_run:
                shutil.copy2(app[key]["path"], app[key]["path"] + ".bak")
            updated += 1
        else:
            continue
        write(dest, data, args.dry_run)

    print(f"\n{'Would restore' if args.dry_run else 'Restored'} {added} new, "
          f"{'overwrite' if args.dry_run else 'overwrote'} {updated} "
          f"(previous versions kept as .bak).")
    if not args.dry_run and (added or updated):
        print("Restart Creality Print to pick them up.")
        print("Restored presets have no .info sidecar, so the app treats them as")
        print("local-only until you next edit and save each one.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["status", "export", "import"])
    ap.add_argument("-n", "--dry-run", action="store_true", help="print changes, write nothing")
    ap.add_argument("--app", help="path to a user/<account-id> folder")
    ap.add_argument("--account", help="account id, when several are present")
    ap.add_argument("--format", choices=["full", "minimal"], default="full",
                    help="shape for presets new to the repo (default: full, self-contained)")
    args = ap.parse_args()

    root = pick_root(args)
    return {"status": cmd_status, "export": cmd_export, "import": cmd_import}[args.command](root, args)


if __name__ == "__main__":
    sys.exit(main())
