# TokenPet Unity Renderer PoC

This project is an **opt-in renderer experiment**. It does not replace or
delete the original Tkinter/Canvas pet. The Python application remains the
source of truth for account data, economy, save data, furniture, and AI.

## What the PoC proves

- an original, minimal kawaii transparent character sprite
- Windows borderless, topmost chroma-key overlay
- idle, walk, poke, drag, fall, and land reactions
- a data-driven equipment controller and `head` socket with a crown test item
- newline-delimited JSON communication over localhost TCP
- Python-side startup failure and crash fallback to the legacy renderer

The current Windows overlay uses a reserved magenta color key as the
compatibility-first PoC path. Before shipping, validate a native
per-pixel-alpha swapchain path to eliminate possible chroma fringes on
semi-transparent sprite edges.

Global desktop movement belongs to the native window. Character animation is
clamped to a viewport-safe inset, so drag-release spins, walk cycles, and
equipment cannot move the rig beyond the 512x512 player surface.

## Open and run

1. Install Unity 6.0 LTS with Windows Build Support.
2. Open this `unity_poc` directory in Unity Hub.
3. Unity creates `Assets/TokenPet/Scenes/TokenPetPoc.unity` automatically.
4. Press Play to test the renderer by itself.
5. Use **TokenPet > Build Windows PoC** to create:
   `unity_poc/Build/TokenPetUnity.exe`.

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

You can override the player path with `TOKENPET_UNITY_RENDERER`. Without the
flag/config setting, or when the Unity player cannot start, the original pet is
used unchanged.

For a clean-machine setup, pinned versions, ignored Unity directories, and the
verification checklist, see `../DEVELOPMENT.md`.

## IPC contract

Python launches the player with `--tokenpet-port=<port>`. The Unity renderer
connects to `127.0.0.1`, sends `hello`, receives `snapshot`, `trigger`, `equip`,
`set_visible`, and `shutdown` commands, and sends interaction/lifecycle events
back to Python.

## Adding equipment

Add an entry to `Assets/TokenPet/Resources/accessory_catalog.json` and point
its `resource` field at a prefab under `Resources`. The equipment controller
parents it to the requested socket, applies its offset/scale/sorting order, and
keeps this logic out of the character animation code. The procedural crown is
only a zero-dependency PoC item.
