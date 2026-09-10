# TokenPet Unity Renderer PoC

This project is an **opt-in renderer experiment**. It does not replace or
delete the original Tkinter/Canvas pet. The Python application remains the
source of truth for account data, economy, save data, furniture, and AI.

Renderer **v0.7.0-preview** consumes the legacy visual snapshot: expressions,
consumables, buffs, accessories, furniture reactions, board text, and overtime
state. These are separate modular Unity layers; the original Canvas remains the
automatic fallback.

Drag release is now connected to the original Python desktop-physics loop.
Python owns gravity, screen-edge and floor collisions, trampoline/basketball
interactions, and landing rewards; Unity animates the airborne and landing
poses while its native window follows the resulting desktop coordinates.
Canvas floating feedback is mirrored into Unity, and click streaks, drag start,
release velocity, and shake gestures are sent back to Python.

The item and furniture shop is rendered inside the same Unity surface with
category tabs, scrolling rows, coin balance, and contextual action buttons.
Purchases, ownership, equipment, consumables, furniture spawning, and save data
remain authoritative in the existing Python game layer. Escape or the close
button returns to the pet surface.

The native Player now spans the Windows virtual desktop as a chroma-key stage.
Transparent regions are click-through; pet, furniture, and panel hit regions
become interactive on hover. The apparent 104 px character size is unchanged,
but motion and equipment are no longer clipped by a 340x300 native window.
All eight legacy furniture types are Unity-rendered entities with desktop drag
and recycle interactions. Python remains authoritative for their positions,
collisions, timed reactions, rewards, and persistence.

## What the PoC proves

- an original, minimal kawaii transparent character sprite
- Windows borderless, topmost chroma-key overlay
- virtual-desktop transparent stage with selective click-through hit testing
- idle, walk, poke, drag, desktop fall, bounce, and land reactions
- data-driven motion profiles with anticipation, velocity stretch, gaze lean,
  idle micro-gestures, and damped landing rebounds
- a layered character rig: the accepted painted body is preserved as art while
  four Unity-driven noodle limbs change pose for idle, walk, poke, drag,
  airborne, and landing states
- a procedural face rig with cursor gaze, randomized blinks, animated brows,
  and state-specific eye/mouth poses instead of a baked static expression
- a compact warm status tag for level, XP, satiety, and coins rendered inside
  the pet's original 340x300 logical area instead of a detached Tk window
- Unity-rendered futon, laptop, trampoline, lamp, plant, sofa, TV and kotatsu;
  Python-compatible proxies preserve the original interaction physics
- a data-driven equipment controller with head/face/neck/body sockets and all
  legacy accessories
- newline-delimited JSON communication over localhost TCP
- Python-side startup failure and crash fallback to the legacy renderer

The current Windows overlay uses a reserved magenta color key as the
compatibility-first PoC path. Before shipping, validate a native
per-pixel-alpha swapchain path to eliminate possible chroma fringes on
semi-transparent sprite edges.

Global desktop movement belongs to `TokenPetWindowsOverlay`. The Player surface
spans the virtual desktop while the pet keeps the same 340x300 logical area and
approximately 104 px body diameter as the legacy Canvas. Python sends logical
desktop positions; Unity maps the pet and furniture into the larger stage.

## Open and run

1. Install Unity 6.0 LTS with Windows Build Support.
2. Open this `unity_poc` directory in Unity Hub.
3. Unity creates `Assets/TokenPet/Scenes/TokenPetPoc.unity` automatically.
4. Press Play to test the renderer by itself.
5. Use **TokenPet > Build Windows PoC** to create:
   `unity_poc/Build/TokenPetUnity.exe`.

A normal build only creates a preview executable. After the preview is
approved, use **TokenPet > Package Approved Windows Build** (or execute
`TokenPet.Editor.TokenPetPocBuilder.PackageApprovedWindowsBuild` in batch mode)
to create `dist/TokenPetUnity-v<version>-win-x64.zip`. The package contains
the complete Player runtime and excludes Unity's
`BurstDebugInformation_DoNotShip` folder.

Or build from a command prompt:

```powershell
Unity.exe -batchmode -quit -projectPath .\unity_poc `
  -executeMethod TokenPet.Editor.TokenPetPocBuilder.BuildWindows
```

## Run with Python

After building the Unity player:

```powershell
python emojinoko_monitor.py --standalone --unity-poc
```

On Windows, `../run_unity_preview.cmd` is the double-click development launcher
for this integrated mode. Do not use the renderer executable by itself to test
Python-owned menus or game systems.

Use this integrated launch for the real application. The Unity executable is a
renderer-only process; the warm right-click action panel and shop are rendered
by Unity while their actions, memos, save data, and other game systems remain
in Python and are reached through IPC. A directly launched renderer can be
closed with `Esc`; in integrated mode, the original **Close TokenPet** action
shuts down both processes.

You can override the player path with `TOKENPET_UNITY_RENDERER`. Without the
flag/config setting, or when the Unity player cannot start, the original pet is
used unchanged.

For a clean-machine setup, pinned versions, ignored Unity directories, and the
verification checklist, see `../DEVELOPMENT.md`.

## IPC contract

Python launches the player with `--tokenpet-port=<port>`. The Unity renderer
connects to `127.0.0.1`, sends `hello`, receives `snapshot`, `trigger`, `equip`,
`move_window`, `popup`, `show_shop`, `hide_shop`, `set_visible`,
`set_status_visible`, `sync_furniture`, `trigger_furniture`, and `shutdown`
commands, and sends interaction/lifecycle events (including `shop_action`,
`shop_closed`, `furniture_moved`, and `furniture_despawn`) back to Python. Status values
plus food, furniture, active effects, board and overtime state are carried by
the snapshot; Python remains authoritative for all economy and save data.

## Adding equipment

Add an entry to `Assets/TokenPet/Resources/accessory_catalog.json` and point
its `resource` field at a prefab under `Resources`. The equipment controller
parents it to the requested socket, applies its offset/scale/sorting order, and
keeps this logic out of the character animation code. The procedural crown is
only a zero-dependency PoC item.

## Tuning motion

Edit `Assets/TokenPet/Resources/motion_profiles.json` for timing, bob, sway,
tilt, squash/stretch, and smoothing. `MotionRoot` applies one coherent pose to
the body and every equipment socket. The C# profile library contains matching
fallback values so a malformed or missing optional entry does not crash the
renderer.

`TokenPetLimbRig` owns the procedural arm/leg poses. The rig loads
`tokenpet_body.png` first and automatically falls back to the untouched
`tokenpet_stylized.png` full-body sprite if the layered art is unavailable.
`TokenPetExpressionRig` is enabled when `tokenpet_body_faceless.png` is
available; otherwise the painted-face body remains the visual fallback.
