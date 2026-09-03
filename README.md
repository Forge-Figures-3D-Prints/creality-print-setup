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

## Importing a profile

In Creality Print, use the config import option in the File menu and pick the `.json` file. Where a printer preset exists (K1 Max), import it first — the process presets bind to it and won't show up otherwise.

Alternatively, copy the files straight into the user preset folder and restart Creality Print:

```
~/Library/Application Support/Creality/Creality Print/<version>/user/<account-id>/
    machine/    <- Printer Profiles
    filament/   <- Filament Profiles
    process/    <- Process Profiles
```

On Windows that folder is `%APPDATA%\Creality\Creality Print\<version>\user\<account-id>\`. Presets saved while signed out land under `user/default/` instead of an account id.

A hand-copied preset has no accompanying `.info` sidecar, so Creality Print treats it as unsynced local-only until you next edit and save it. Importing through the app avoids this.

## Exporting after a change

Recalibrated something? Export the preset from Creality Print — or copy it out of the folder above — drop the `.json` into the matching folder here, and commit.

Two conventions worth keeping:

- **Don't commit the `.info` sidecars.** They hold sync state and account ids, not settings.
- **The default preset gets a `(PLA)` suffix on the filename.** Creality Print names the un-suffixed base preset just `- Calibrated`; it's filed here as `- Calibrated (PLA).json` so it sorts alongside its siblings. The internal `name` field is left untouched, so the app still sees the original name.
