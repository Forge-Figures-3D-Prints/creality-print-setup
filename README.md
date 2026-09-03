# creality-print-setup

Version-controlled backup of my custom [Creality Print](https://www.crealitycloud.com/software-firmware/creality-print) profiles — printer, filament, and process presets calibrated on my own machines.

Creality Print keeps user presets in an application-support folder that gets wiped or migrated on upgrade, so they live here instead.

## Layout

```
<Printer>/
  Printer Profiles/    machine presets  (bed size, Z offset, kinematics, start/end G-code)
  Filament Profiles/   filament presets (temps, cooling, flow)
  Process Profiles/    print presets    (layer height, walls, infill, supports)
```

| Printer | Printer | Filament | Process |
| --- | --- | --- | --- |
| Creality Hi | — | PETG | PLA · PETG · ASA |
| Creality K1 Max | PLA · PETG · ASA | — | PLA · PETG · ASA |
| Creality K2 Plus | — | — | PLA · ASA |

A folder only appears where a preset was actually saved and calibrated; a dash means there's nothing worth keeping, not that it's missing. The Hi runs fine on the stock machine preset, so it doesn't have one here.

Every preset is JSON exported from Creality Print 7.x. They're diffs, not full configs: each carries an `inherits` field naming the stock Creality preset it's based on and stores only the keys that were changed. That keeps them small and readable, but it also means **the matching stock preset must exist in your Creality Print install** for these to load.

## What's calibrated

Common ground across all three printers: gyroid sparse infill, tree (auto) supports at a 45° threshold, and small overhangs kept rather than pruned.

### Creality Hi

Process presets inherit `0.20mm Standard @Creality Hi 0.4 nozzle`. All three use a 0.38 mm top surface line width, outer-only brim, and a 100 % raft first layer.

- **PLA** — 3 walls, hybrid tree supports
- **PETG** — 3 walls, hybrid tree supports, back seam, and loosened support gaps (0.23 mm Z, 0.5 mm XY, 0.7 mm interface spacing) so supports release cleanly
- **ASA** — 6 walls and 40 % infill for strength, organic supports, build-plate-only

The filament preset `Generic PETG @Creality Hi 0.4 nozzle - Calibrated` turns cooling right down: 20–30 % fan, off entirely for the first 5 layers, no fan stop/start smoothing. That's what keeps layer adhesion and stops warping on PETG.

### Creality K1 Max

The printer presets exist **only to carry a per-material Z offset** — everything else is identical to the stock `Creality K1 Max 0.4 nozzle`:

| Preset | Z offset | Note |
| --- | --- | --- |
| `- PLA` | 0.05 mm | 300 × 300 bed |
| `- PETG` | 0.175 mm | bed Y trimmed to 295 mm |
| `- ASA` | 0.7 mm | 300 × 300 bed |

Pick the printer preset matching your filament, or first layers will be squashed or lifted.

Process presets inherit `0.20mm Standard @Creality K1 Max 0.4 nozzle`, all at 3 walls with a 0.5 mm support XY distance and Z-overrides-XY spacing — except ASA:

- **PLA** — organic supports, build-plate-only, 5 bottom shell layers
- **PETG** — hybrid tree supports, 10 mm outer brim, 0.23 mm support Z gap
- **ASA** — the heavily tuned one. 4 walls with Arachne, precise outer wall, 25 % infill, monotonic top surface, full speed and acceleration ladder (120 mm/s outer wall, 400 mm/s travel), staged overhang slowdowns (40 / 25 / 20 mm/s), organic supports at a 0.21 mm Z gap, elephant foot and XY hole compensation

### Creality K2 Plus

Process presets inherit `0.20mm Standard @Creality K2 Plus 0.4 nozzle`, both at 3 walls.

- **PLA** — hybrid tree supports. Note this one also carries `mixed_filament_definitions` (CFS multi-material config), so it doubles as the general default
- **ASA** — organic supports, build-plate-only, 5 interface top layers, 0.25 mm support Z gap

## Keeping in sync with Creality Print

The repo is the source of truth. `tools/sync.py` moves presets between here and
the installed app, finding the app folder itself so it works on any machine.

```bash
tools/sync.py status     # compare, change nothing
tools/sync.py export     # Creality Print -> repo, after calibrating
tools/sync.py import     # repo -> Creality Print, on a new machine
```

Add `-n` to any of them to see what would happen without writing. Restart
Creality Print after an `import`. If you have several accounts or app versions,
pass `--account <id>` or `--app <path>`.

After an `export`, review with `git diff` and commit. After an `import`, the
restored presets have no `.info` sidecar, so Creality Print treats them as
local-only until you next edit and save each one.

### Testing the sync

```bash
python3 tools/test_sync.py
```

11 tests covering both directions, run against a synthetic Creality Print
install in a temp directory. Nothing reads or writes your real preset folder,
so it is safe to run any time. They cover the things that would quietly lose a
profile: filename-vs-internal-name identity, round-trip fidelity, export not
duplicating a renamed file, machine-bound keys never reaching the repo, `.bak`
backups before an overwrite, `--dry-run` writing nothing, `.syncignore`
behaviour, printer routing, and full-vs-minimal shapes comparing equal.

**What this cannot prove** is that Creality Print itself accepts a restored
preset — the tests exercise the script, not the slicer. Restored presets have no
`.info` sidecar, and only the real app can confirm it takes them anyway. To
check that end to end, with a preset already committed here so nothing is at
risk:

1. Quit Creality Print.
2. Move one preset's `.json` and `.info` out of the app's `process/` folder.
3. Run `tools/sync.py import`.
4. Start Creality Print and confirm the preset appears in the process dropdown
   with its settings intact.

If it does, a restore onto a new machine works. Do this once after a Creality
Print major upgrade, since the preset format is versioned.

### Choosing what gets backed up

This repo curates the 0.20mm calibrated profiles. Other layer heights and
one-off experiments stay in Creality Print on purpose. `.syncignore` lists them
as globs matched against a preset's internal name:

```
0.24mm *        # every 0.24mm profile, including ones not made yet
PLA+            # filament preset for an Ender-3 V3, a printer not covered here
```

`export` skips anything matching, and `status` lists them under "ignored" so you
can still see what exists in the app but isn't backed up. A preset already
committed here keeps being synced even if a pattern would match it — the ignore
list decides what to *start* tracking, and never drops what you already keep.

### Doing it by hand

Without the script: import a `.json` through the config import option in
Creality Print's File menu, or copy files straight into the preset folder and
restart. Where a printer preset exists (K1 Max), import it first — the process
presets bind to it and won't appear otherwise.

```
macOS    ~/Library/Application Support/Creality/Creality Print/<version>/user/<account-id>/
Windows  %APPDATA%\Creality\Creality Print\<version>\user\<account-id>\

    machine/  <- Printer Profiles      filament/ <- Filament Profiles
    process/  <- Process Profiles
```

Presets saved while signed out land under `user/default/` instead of an account id.

### What the script has to reconcile

A preset's identity is its internal `name` field, never its filename. That lets
this repo keep readable filenames — the `(PLA)` suffix below — while still
restoring to exactly the name Creality Print expects.

Presets exist in two shapes, and the repo contains both:

- **minimal** — what Creality Print writes to disk: only the keys you changed,
  on top of an `inherits` reference to a stock preset
- **full** — what the app's own Export function writes: the entire resolved
  configuration, roughly 140 keys

A full export cannot be reconstructed offline. It contains defaults compiled
into the application binary (`curr_bed_type`, `nozzle_height` and about 26
others) that appear in no file on disk. So the script never converts between
the shapes: it keeps whichever one a preset already uses, and compares presets
by the settings they actually override rather than key by key. `status` reports
"same settings, stored differently" when the two sides hold different shapes of
an identical preset.

Machine-bound keys are stripped on the way in — `printer_select_mac` is a
specific printer's MAC address, and the `.info` sidecars hold account ids and
sync state. None of that belongs in a portable repo.

### Filename convention

The default preset gets a `(PLA)` suffix here. Creality Print names the un-suffixed base preset just `- Calibrated`; it's filed here as `- Calibrated (PLA).json` so it sorts alongside its siblings. The internal `name` field is left untouched, so the app still sees the original name, and `import` restores it under that name.
