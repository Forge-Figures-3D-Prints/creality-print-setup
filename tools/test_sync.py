#!/usr/bin/env python3
"""Tests for sync.py, run against a synthetic Creality Print install.

    python3 tools/test_sync.py

Everything happens in a temp directory: no real preset folder is read or
written, so this is safe to run at any time. What it cannot prove is that
Creality Print itself accepts a restored preset - see "Testing a real
restore" in the README for that half.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sync", os.path.join(HERE, "sync.py"))
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def read_text(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write_json(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=4)


class SyncTest(unittest.TestCase):
    """Each test gets a fresh fake repo and a fresh fake app install."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sync-test-")
        self.repo = os.path.join(self.tmp, "repo")
        self.app = os.path.join(self.tmp, "app", "7.0", "user", "acct")
        for kind in sync.KINDS:
            os.makedirs(os.path.join(self.app, kind), exist_ok=True)
        os.makedirs(self.repo, exist_ok=True)
        # a stock preset for user presets to inherit from
        write_json(
            os.path.join(self.tmp, "app", "7.0", "system", "Creality", "process",
                         "0.20mm Standard @Creality Hi 0.4 nozzle.json"),
            {"name": "0.20mm Standard @Creality Hi 0.4 nozzle",
             "layer_height": "0.2", "wall_loops": "2", "sparse_infill_density": "15%",
             "thumbnails": "96x96,300x300"},
        )
        self._real_repo = sync.REPO
        sync.REPO = self.repo

    def tearDown(self):
        sync.REPO = self._real_repo
        shutil.rmtree(self.tmp, ignore_errors=True)

    def args(self, **kw):
        base = {"dry_run": False, "app": self.app, "account": None, "format": "full"}
        base.update(kw)
        return argparse.Namespace(**base)

    def app_preset(self, kind, name, **settings):
        data = {"name": name, "inherits": "0.20mm Standard @Creality Hi 0.4 nozzle",
                "from": "User", **settings}
        write_json(os.path.join(self.app, kind, name + ".json"), data)
        return data

    def repo_preset(self, printer, kind, filename, name, **settings):
        data = {"name": name, "inherits": "0.20mm Standard @Creality Hi 0.4 nozzle",
                "from": "User", **settings}
        write_json(os.path.join(self.repo, printer, sync.KINDS[kind], filename + ".json"), data)
        return data

    def silent(self, fn, *a):
        """Run a command with its printing suppressed."""
        out = sys.stdout
        with open(os.devnull, "w") as devnull:
            sys.stdout = devnull
            try:
                return fn(*a)
            finally:
                sys.stdout = out

    # ------------------------------------------------------------------ tests

    def test_import_restores_preset_to_app(self):
        self.repo_preset("Creality Hi", "process",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                         wall_loops="4")
        self.silent(sync.cmd_import, self.app, self.args())
        dest = os.path.join(self.app, "process",
                            "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated.json")
        self.assertTrue(os.path.exists(dest), "import did not write the preset")
        self.assertEqual(read_json((dest))["wall_loops"], "4")

    def test_import_uses_internal_name_not_filename(self):
        """A repo file named "... (PLA).json" must restore under its real name."""
        self.repo_preset("Creality Hi", "process",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated (PLA)",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                         wall_loops="3")
        self.silent(sync.cmd_import, self.app, self.args())
        listed = os.listdir(os.path.join(self.app, "process"))
        self.assertEqual(listed,
                         ["0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated.json"],
                         "cosmetic (PLA) suffix leaked into the app folder")

    def test_round_trip_preserves_settings(self):
        original = self.repo_preset(
            "Creality Hi", "process", "p (PLA)",
            "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
            wall_loops="5", sparse_infill_density="40%", support_style="organic")
        self.silent(sync.cmd_import, self.app, self.args())
        self.silent(sync.cmd_export, self.app, self.args())
        back = read_json((os.path.join(
            self.repo, "Creality Hi", sync.KINDS["process"], "p (PLA).json")))
        for key in ("wall_loops", "sparse_infill_density", "support_style"):
            self.assertEqual(back[key], original[key], f"{key} changed in the round trip")

    def test_export_keeps_existing_repo_filename(self):
        """Re-exporting must not create a duplicate under the app's filename."""
        self.repo_preset("Creality Hi", "process", "p (PLA)",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                         wall_loops="3")
        self.app_preset("process", "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                        wall_loops="9")
        self.silent(sync.cmd_export, self.app, self.args())
        listed = sorted(os.listdir(os.path.join(self.repo, "Creality Hi", sync.KINDS["process"])))
        self.assertEqual(listed, ["p (PLA).json"], "export created a duplicate file")
        self.assertEqual(read_json((os.path.join(
            self.repo, "Creality Hi", sync.KINDS["process"], "p (PLA).json")))["wall_loops"], "9")

    def test_volatile_keys_never_reach_the_repo(self):
        self.app_preset("machine", "Creality Hi 0.4 nozzle - PLA",
                        z_offset="0.05", printer_select_mac="FCEE28055CF9")
        self.silent(sync.cmd_export, self.app, self.args())
        blob = read_text(os.path.join(self.repo, "Creality Hi", sync.KINDS["machine"],
                                      "Creality Hi 0.4 nozzle - PLA.json"))
        self.assertNotIn("printer_select_mac", blob)
        self.assertIn("z_offset", blob)

    def test_import_backs_up_before_overwriting(self):
        self.app_preset("process", "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                        wall_loops="2")
        self.repo_preset("Creality Hi", "process", "p",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                         wall_loops="7")
        self.silent(sync.cmd_import, self.app, self.args())
        base = os.path.join(self.app, "process",
                            "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated.json")
        self.assertEqual(read_json((base))["wall_loops"], "7")
        self.assertEqual(read_json((base + ".bak"))["wall_loops"], "2",
                         "the app's previous version was not preserved")

    def test_dry_run_writes_nothing(self):
        self.repo_preset("Creality Hi", "process", "p",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated")
        self.silent(sync.cmd_import, self.app, self.args(dry_run=True))
        self.assertEqual(os.listdir(os.path.join(self.app, "process")), [])

    def test_syncignore_blocks_new_presets_but_not_tracked_ones(self):
        with open(os.path.join(self.repo, sync.IGNORE_FILE), "w") as fh:
            fh.write("0.24mm *\n")
        self.app_preset("process", "0.24mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                        wall_loops="3")
        self.app_preset("process", "0.24mm Standard @Creality Hi 0.4 nozzle - Tracked",
                        wall_loops="8")
        self.repo_preset("Creality Hi", "process", "tracked",
                         "0.24mm Standard @Creality Hi 0.4 nozzle - Tracked", wall_loops="1")
        self.silent(sync.cmd_export, self.app, self.args())
        files = sorted(os.listdir(os.path.join(self.repo, "Creality Hi", sync.KINDS["process"])))
        self.assertEqual(files, ["tracked.json"], "an ignored preset was exported")
        self.assertEqual(read_json((os.path.join(
            self.repo, "Creality Hi", sync.KINDS["process"], "tracked.json")))["wall_loops"], "8",
            "an already-tracked preset stopped syncing because a pattern matched it")

    def test_printer_routing(self):
        cases = [
            ({"name": "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated"}, "Creality Hi"),
            ({"name": "Creality K1 Max 0.4 nozzle - PLA"}, "Creality K1 Max"),
            ({"name": "0.5mm PETG Functional - Min Time @Creality K1 Max 0.8 nozzle"},
             "Creality K1 Max"),
            ({"name": "PLA+", "inherits": "Ender-PLA @Creality Ender-3 V3 0.4 nozzle"},
             "Creality Ender-3 V3"),
            ({"name": "something unparseable"}, None),
        ]
        for preset, expected in cases:
            self.assertEqual(sync.printer_of(preset), expected, f"routing {preset['name']!r}")

    def test_full_and_minimal_shapes_compare_equal(self):
        """The same preset in both shapes must not look like a difference."""
        self.app_preset("process", "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                        wall_loops="4")
        # the full-export shape: same override, plus inherited and binary defaults
        self.repo_preset("Creality Hi", "process", "p",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                         wall_loops="4", layer_height="0.2", sparse_infill_density="15%",
                         thumbnails="96x96/PNG, 300x300/PNG", curr_bed_type="Cool Plate")
        index = sync.build_index(self.app)
        app, repo = sync.scan_app(self.app), sync.scan_repo()
        key = ("process", "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated")
        self.assertEqual(
            sync.differences(app[key]["data"], repo[key]["data"], "process", index), {},
            "identical settings in different shapes reported as differing")

    def test_real_difference_is_detected(self):
        self.app_preset("process", "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                        wall_loops="4")
        self.repo_preset("Creality Hi", "process", "p",
                         "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated",
                         wall_loops="6")
        index = sync.build_index(self.app)
        app, repo = sync.scan_app(self.app), sync.scan_repo()
        key = ("process", "0.20mm Standard @Creality Hi 0.4 nozzle - Calibrated")
        diff = sync.differences(app[key]["data"], repo[key]["data"], "process", index)
        self.assertIn("wall_loops", diff, "a genuine setting change was missed")


if __name__ == "__main__":
    unittest.main(verbosity=2)
