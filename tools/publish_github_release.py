"""Build, package, and publish the current TokenPet preview to GitHub Releases."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "unity_poc" / "Assets" / "TokenPet" / "Scripts" / "TokenPetPocBootstrap.cs"


def run(*command: str) -> None:
    print("+", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def capture(*command: str) -> str:
    return subprocess.check_output(command, cwd=ROOT, text=True).strip()


def git_capture(*arguments: str) -> str:
    return capture("git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments)


def version() -> str:
    match = re.search(r'RendererVersion\s*=\s*"([^"]+)"', BOOTSTRAP.read_text(encoding="utf-8"))
    if not match:
        raise RuntimeError("RendererVersion was not found")
    return match.group(1)


def repository() -> str:
    remote = git_capture("remote", "get-url", "origin")
    match = re.search(r"github\.com[/:]([^/]+/[^/.]+)(?:\.git)?$", remote)
    if not match:
        raise RuntimeError(f"Unsupported GitHub origin URL: {remote}")
    return match.group(1)


def find_unity() -> Path:
    configured = os.environ.get("UNITY_EDITOR")
    candidates = [Path(configured)] if configured else []
    candidates.extend(
        [
            Path(r"D:\Unity\Hub\Editor\6000.0.65f1\Editor\Unity.exe"),
            Path(r"C:\Program Files\Unity\Hub\Editor\6000.0.65f1\Editor\Unity.exe"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Unity 6000.0.65f1 was not found. Set UNITY_EDITOR to Unity.exe."
    )


def ensure_publishable_git_state() -> str:
    if git_capture("status", "--porcelain"):
        raise RuntimeError("Commit all source changes before publishing a release.")
    head = git_capture("rev-parse", "HEAD")
    branch = git_capture("branch", "--show-current")
    remote_head = git_capture("rev-parse", f"origin/{branch}")
    if head != remote_head:
        raise RuntimeError(f"Push {branch} before publishing a release.")
    return head


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--publish-existing",
        action="store_true",
        help="Upload the already verified ZIP instead of rebuilding it.",
    )
    args = parser.parse_args()

    release_version = version()
    tag = f"v{release_version}"
    repo = repository()
    head = ensure_publishable_git_state()
    run("gh", "auth", "status")

    archive = ROOT / "dist" / f"TokenPetIntegrated-v{release_version}-dev-win-x64.zip"
    if not args.publish_existing:
        run(os.fspath(Path(os.sys.executable)), "-m", "pytest", "-q")
        unity = find_unity()
        run(
            os.fspath(unity),
            "-batchmode",
            "-nographics",
            "-quit",
            "-projectPath",
            os.fspath(ROOT / "unity_poc"),
            "-executeMethod",
            "TokenPet.Editor.TokenPetPocBuilder.BuildWindows",
            "-logFile",
            os.fspath(ROOT / "unity_poc" / "publish-build.log"),
        )
        run(os.sys.executable, os.fspath(ROOT / "tools" / "package_integrated.py"), "--replace")
    if not archive.is_file():
        raise FileNotFoundError(f"Release archive does not exist: {archive}")

    existing = subprocess.run(
        ["gh", "release", "view", tag, "--repo", repo],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
    if existing:
        run("gh", "release", "upload", tag, os.fspath(archive), "--clobber", "--repo", repo)
    else:
        command = [
            "gh", "release", "create", tag, os.fspath(archive),
            "--repo", repo,
            "--target", head,
            "--title", f"TokenPet {tag}",
            "--generate-notes",
        ]
        if "preview" in release_version or "dev" in release_version:
            command.append("--prerelease")
        run(*command)

    url = capture("gh", "release", "view", tag, "--repo", repo, "--json", "url", "--jq", ".url")
    print(f"release={url}")
    print(f"asset={archive.name}")


if __name__ == "__main__":
    main()
