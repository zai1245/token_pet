"""Create a reproducible full TokenPet Unity + Python development package."""

from __future__ import annotations

import re
import shutil
import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "unity_poc" / "Build"
DIST = ROOT / "dist"

SOURCE_FILES = (
    "DEVELOPMENT.md",
    "GITHUB_RELEASES.md",
    "README.md",
    "requirements.txt",
    "collect_debug_logs.cmd",
    "run_unity_preview.cmd",
    "UNITY_POC.md",
    "emojinoko_game.py",
    "emojinoko_monitor.py",
    "unity_renderer_bridge.py",
    "usage_widget.py",
)

RUNTIME_ENTRIES = (
    "TokenPetUnity.exe",
    "TokenPetUnity_Data",
    "UnityPlayer.dll",
    "UnityCrashHandler64.exe",
    "MonoBleedingEdge",
    "D3D12",
)


def renderer_version() -> str:
    bootstrap = ROOT / "unity_poc" / "Assets" / "TokenPet" / "Scripts" / "TokenPetPocBootstrap.cs"
    match = re.search(r'RendererVersion\s*=\s*"([^"]+)"', bootstrap.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("Unable to read RendererVersion from TokenPetPocBootstrap.cs")
    return match.group(1)


def copy_entry(source: Path, destination: Path) -> None:
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the package for the current RendererVersion.",
    )
    args = parser.parse_args()
    version = renderer_version()
    package_name = f"TokenPetIntegrated-v{version}-dev-win-x64"
    package_dir = DIST / package_name
    archive_path = DIST / f"{package_name}.zip"

    if (package_dir.exists() or archive_path.exists()) and not args.replace:
        raise RuntimeError(
            f"Package target already exists: {package_name}. "
            "Bump RendererVersion before packaging another approved build."
        )
    if args.replace:
        if package_dir.exists():
            shutil.rmtree(package_dir)
        if archive_path.exists():
            archive_path.unlink()

    required = [ROOT / name for name in SOURCE_FILES]
    required.extend(BUILD / name for name in RUNTIME_ENTRIES)
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing package inputs:\n" + "\n".join(missing))

    package_dir.mkdir(parents=True)
    for name in SOURCE_FILES:
        copy_entry(ROOT / name, package_dir / name)
    runtime_dir = package_dir / "unity_poc" / "Build"
    runtime_dir.mkdir(parents=True)
    for name in RUNTIME_ENTRIES:
        copy_entry(BUILD / name, runtime_dir / name)

    manifest = (
        f"TokenPet integrated developer preview\n"
        f"Renderer version: {version}\n\n"
        "Start: double-click run_unity_preview.cmd\n"
        "Do not start unity_poc\\Build\\TokenPetUnity.exe by itself; "
        "the Python bridge owns menus and game systems.\n"
        "Environment and rebuild instructions: DEVELOPMENT.md and UNITY_POC.md\n"
    )
    (package_dir / "PACKAGE_INFO.txt").write_text(manifest, encoding="utf-8")

    with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
        for path in sorted(package_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(DIST).as_posix())

    with ZipFile(archive_path) as archive:
        bad_file = archive.testzip()
        if bad_file:
            raise RuntimeError(f"ZIP integrity check failed at {bad_file}")
        file_count = len(archive.infolist())

    print(f"package={archive_path}")
    print(f"size={archive_path.stat().st_size}")
    print(f"files={file_count}")


if __name__ == "__main__":
    main()
