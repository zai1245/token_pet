"""GitHub Release client and external whole-package updater for TokenPet."""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile


API_ROOT = "https://api.github.com"
ASSET_PREFIX = "TokenPetIntegrated-"
REQUIRED_PACKAGE_FILES = (
    "PACKAGE_INFO.txt",
    "run_unity_preview.cmd",
    "emojinoko_monitor.py",
    "tokenpet_github_updater.py",
    "unity_poc/Build/TokenPetUnity.exe",
)


def parse_version(value: str) -> tuple[int, int, int]:
    import re

    parts = [int(part) for part in re.findall(r"\d+", str(value))[:3]]
    return tuple((parts + [0, 0, 0])[:3])


def find_newer_release(
    repository: str,
    current_version: str,
    *,
    include_prerelease: bool,
    timeout: int = 10,
) -> dict | None:
    request = urllib.request.Request(
        f"{API_ROOT}/repos/{repository}/releases?per_page=30",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "TokenPet-Updater",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        releases = json.loads(response.read().decode("utf-8"))

    candidates = []
    for release in releases:
        if release.get("draft") or (release.get("prerelease") and not include_prerelease):
            continue
        version = str(release.get("tag_name", "")).lstrip("vV")
        if parse_version(version) <= parse_version(current_version):
            continue
        asset = next(
            (
                item
                for item in release.get("assets", [])
                if str(item.get("name", "")).startswith(ASSET_PREFIX)
                and str(item.get("name", "")).lower().endswith(".zip")
            ),
            None,
        )
        if asset is None:
            continue
        candidates.append((parse_version(version), release, asset, version))

    if not candidates:
        return None
    _, release, asset, version = max(candidates, key=lambda entry: entry[0])
    return {
        "version": version,
        "name": release.get("name") or release.get("tag_name") or version,
        "notes": release.get("body") or "",
        "html_url": release.get("html_url") or "",
        "asset_name": asset["name"],
        "download_url": asset["browser_download_url"],
        "size": int(asset.get("size") or 0),
        "digest": str(asset.get("digest") or ""),
    }


def download_and_verify(release: dict, destination: Path, progress=None) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    expected_digest = release.get("digest", "")
    if not expected_digest.startswith("sha256:"):
        raise RuntimeError("GitHub Release asset does not provide a SHA-256 digest")

    request = urllib.request.Request(
        release["download_url"],
        headers={"User-Agent": "TokenPet-Updater"},
    )
    digest = hashlib.sha256()
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, open(temporary, "wb") as output:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if progress:
                    progress(received, int(release.get("size") or 0))

        expected_size = int(release.get("size") or 0)
        if expected_size and received != expected_size:
            raise RuntimeError(f"download size mismatch: expected {expected_size}, got {received}")
        actual = digest.hexdigest().lower()
        expected = expected_digest.split(":", 1)[1].lower()
        if actual != expected:
            raise RuntimeError(f"SHA-256 mismatch: expected {expected}, got {actual}")
        os.replace(temporary, destination)
        return actual
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def launch_external_installer(archive: Path, install_dir: Path, parent_pid: int) -> None:
    updater = Path(__file__).resolve()
    command = [
        sys.executable,
        os.fspath(updater),
        "--apply",
        "--archive",
        os.fspath(archive),
        "--install-dir",
        os.fspath(install_dir),
        "--parent-pid",
        str(parent_pid),
    ]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        command,
        cwd=os.fspath(install_dir),
        close_fds=True,
        creationflags=creationflags,
    )


def _log_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
    path = base / "TokenPet" / "logs" / "TokenPet-updater.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _write_log(message: str) -> None:
    with open(_log_path(), "a", encoding="utf-8") as output:
        output.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def _wait_for_process(pid: int, timeout_seconds: int = 45) -> None:
    if os.name != "nt" or pid <= 0:
        return
    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
    if not handle:
        return
    try:
        ctypes.windll.kernel32.WaitForSingleObject(handle, timeout_seconds * 1000)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _safe_extract(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as package:
        bad_file = package.testzip()
        if bad_file:
            raise RuntimeError(f"ZIP integrity failure at {bad_file}")
        for member in package.infolist():
            target = (destination / member.filename).resolve()
            if target != root and root not in target.parents:
                raise RuntimeError(f"unsafe ZIP member: {member.filename}")
        package.extractall(destination)

    top_level = [entry for entry in destination.iterdir() if entry.is_dir()]
    package_root = top_level[0] if len(top_level) == 1 else destination
    missing = [name for name in REQUIRED_PACKAGE_FILES if not (package_root / name).exists()]
    if missing:
        raise RuntimeError("update package is missing: " + ", ".join(missing))
    return package_root


def _replace_tree(package_root: Path, install_dir: Path, backup_dir: Path) -> None:
    files = [path for path in package_root.rglob("*") if path.is_file()]
    created = []
    backed_up = []
    try:
        for source in files:
            relative = source.relative_to(package_root)
            target = install_dir / relative
            if target.exists():
                backup = backup_dir / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, backup)
                backed_up.append((backup, target))
            else:
                created.append(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            incoming = target.with_name(target.name + ".update-new")
            shutil.copy2(source, incoming)
            last_error = None
            for _ in range(40):
                try:
                    os.replace(incoming, target)
                    last_error = None
                    break
                except OSError as exc:
                    last_error = exc
                    time.sleep(0.25)
            if last_error:
                raise last_error
    except Exception:
        _write_log("copy failed; restoring previous package")
        for target in reversed(created):
            target.unlink(missing_ok=True)
        for backup, target in reversed(backed_up):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        raise


def _start_tokenpet(install_dir: Path) -> None:
    launcher = install_dir / "run_unity_preview.cmd"
    if not launcher.exists():
        _write_log(f"launcher missing after update attempt: {launcher}")
        return
    subprocess.Popen(
        ["cmd.exe", "/c", os.fspath(launcher)],
        cwd=os.fspath(install_dir),
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def apply_update(archive: Path, install_dir: Path, parent_pid: int) -> None:
    local_base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "TokenPet" / "updates"
    local_base.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    stage = Path(tempfile.mkdtemp(prefix="stage-", dir=local_base))
    backup = local_base / f"backup-{stamp}"
    try:
        _write_log(f"preparing archive={archive} install_dir={install_dir}")
        package_root = _safe_extract(archive, stage)
        _wait_for_process(parent_pid)
        time.sleep(1.0)
        _replace_tree(package_root, install_dir, backup)
        _write_log(f"update installed; backup={backup}")
        _start_tokenpet(install_dir)
    except Exception as exc:
        _write_log(f"update failed: {exc!r}")
        _start_tokenpet(install_dir)
        raise
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        archive.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--install-dir", type=Path)
    parser.add_argument("--parent-pid", type=int, default=0)
    args = parser.parse_args()
    if not args.apply or args.archive is None or args.install_dir is None:
        parser.error("--apply, --archive and --install-dir are required")
    apply_update(args.archive.resolve(), args.install_dir.resolve(), args.parent_pid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
