# creality-print-setup

Version-controlled backup of my custom [Creality Print](https://www.crealitycloud.com/software-firmware/creality-print) profiles — printer, filament, and process presets that have been calibrated on my own machines.

Creality Print keeps user presets in an application-support folder that gets wiped or migrated on upgrade, so they live here instead.

## Layout

```
<Printer>/
  Printer Profiles/    machine presets  (bed size, kinematics, start/end G-code)
  Filament Profiles/   filament presets (temps, cooling, flow)
  Process Profiles/    print presets    (layer height, walls, infill, supports)
```

| Printer | Status |
| --- | --- |
| Creality Hi | Calibrated — printer, filament (PETG), process (PLA / PETG / ASA) |
| Creality K1 Max | Placeholder — not yet exported |
| Creality K2 Plus | Placeholder — not yet exported |

Every preset is exported from Creality Print 7.x as JSON. The user presets are diffs: each carries an `inherits` field naming the stock Creality preset it is based on, and only stores the keys that were changed. That keeps the files small and readable, but it also means **the matching stock preset must exist in your Creality Print install** for these to load.

## Creality Hi — what's calibrated

**Printer** — `Creality Hi 0.4 nozzle`
- 260 × 260 × 300 mm build volume, 0.4 mm hardened steel nozzle, Klipper flavour
- Retraction 0.8 mm @ 40 mm/s, wipe on, 0.4 mm auto-lift Z hop
- Custom start G-code with a two-line front purge, plus timelapse and layer-change hooks

**Process** — all three inherit `0.20mm Standard @Creality Hi 0.4 nozzle`
- Shared: gyroid sparse infill, tree (auto) supports at a 45° threshold, small overhangs kept, 0.38 mm top surface line width, outer-only brim, 100 % raft first layer
- PLA — 3 walls, hybrid tree supports
- PETG — 3 walls, hybrid tree supports, wider support gaps (0.23 mm Z, 0.5 mm XY, 0.7 mm interface spacing) so supports release cleanly
- ASA — 6 walls and 40 % infill for strength, organic supports, build-plate-only

**Filament** — `Generic PETG @Creality Hi 0.4 nozzle - Calibrated`
- Cooling turned right down: 20–30 % fan, fully off for the first 5 layers, no fan stop/start smoothing — reduces layer-adhesion loss and warping on PETG

## Importing a profile

In Creality Print, use the config import option in the File menu and pick the `.json` file. Import the **printer** profile first — the filament and process profiles are bound to it and won't show up otherwise.

Alternatively, copy the files straight into the user preset folder and restart Creality Print:

```
~/Library/Application Support/Creality/Creality Print/<version>/user/<account-id>/
    machine/    <- Printer Profiles
    filament/   <- Filament Profiles
    process/    <- Process Profiles
```

On Windows that folder is `%APPDATA%\Creality\Creality Print\<version>\user\<account-id>\`. Presets saved while signed out land under `user/default/` instead of an account id.

Note that a hand-copied preset has no accompanying `.info` sidecar, so Creality Print treats it as unsynced local-only until you next edit and save it. Importing through the app avoids this.

## Exporting after a change

Recalibrated something? Export the preset from Creality Print, drop the `.json` into the matching folder here, and commit. Don't commit the `.info` sidecars — they hold sync state and account ids, not settings.
