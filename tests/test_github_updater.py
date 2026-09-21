import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

import tokenpet_github_updater as updater
from tokenpet_version import VERSION


ROOT = Path(__file__).resolve().parents[1]


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


class GitHubUpdaterTests(unittest.TestCase):
    def test_python_and_unity_release_versions_match(self):
        bootstrap = (
            ROOT
            / "unity_poc"
            / "Assets"
            / "TokenPet"
            / "Scripts"
            / "TokenPetPocBootstrap.cs"
        ).read_text(encoding="utf-8")
        self.assertIn(f'RendererVersion = "{VERSION}"', bootstrap)

    def test_release_lookup_selects_new_integrated_preview(self):
        releases = [
            {
                "tag_name": "v0.8.5-preview",
                "name": "TokenPet v0.8.5-preview",
                "draft": False,
                "prerelease": True,
                "html_url": "https://example.test/release",
                "body": "changes",
                "assets": [
                    {
                        "name": "TokenPetIntegrated-v0.8.5-preview-dev-win-x64.zip",
                        "browser_download_url": "https://example.test/package.zip",
                        "size": 123,
                        "digest": "sha256:" + "a" * 64,
                    }
                ],
            },
            {
                "tag_name": "v0.8.6-preview",
                "draft": True,
                "prerelease": True,
                "assets": [],
            },
        ]
        response = _Response(json.dumps(releases).encode("utf-8"))
        with mock.patch("urllib.request.urlopen", return_value=response):
            release = updater.find_newer_release(
                "zai1245/token_pet",
                "0.8.4-preview",
                include_prerelease=True,
            )
        self.assertEqual("0.8.5-preview", release["version"])
        self.assertTrue(release["asset_name"].startswith("TokenPetIntegrated-"))

    def test_download_requires_and_verifies_github_sha256(self):
        payload = b"tokenpet-package"
        digest = hashlib.sha256(payload).hexdigest()
        release = {
            "download_url": "https://example.test/package.zip",
            "size": len(payload),
            "digest": f"sha256:{digest}",
        }
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "package.zip"
            with mock.patch(
                "urllib.request.urlopen", return_value=_Response(payload)
            ):
                actual = updater.download_and_verify(release, destination)
            self.assertEqual(digest, actual)
            self.assertEqual(payload, destination.read_bytes())

    def test_zip_slip_is_rejected_before_install(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            archive = directory / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("../escaped.txt", "bad")
            with self.assertRaisesRegex(RuntimeError, "unsafe ZIP member"):
                updater._safe_extract(archive, directory / "stage")

    def test_whole_package_replace_preserves_local_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            package = directory / "package"
            install = directory / "install"
            backup = directory / "backup"
            package.mkdir()
            install.mkdir()
            (package / "emojinoko_monitor.py").write_text("new", encoding="utf-8")
            (package / "new_runtime.dll").write_bytes(b"runtime")
            (install / "emojinoko_monitor.py").write_text("old", encoding="utf-8")
            (install / ".credentials").write_text("private", encoding="utf-8")

            updater._replace_tree(package, install, backup)

            self.assertEqual("new", (install / "emojinoko_monitor.py").read_text())
            self.assertEqual(b"runtime", (install / "new_runtime.dll").read_bytes())
            self.assertEqual("private", (install / ".credentials").read_text())
            self.assertEqual("old", (backup / "emojinoko_monitor.py").read_text())

    def test_package_builder_includes_updater_and_manifest(self):
        source = (ROOT / "tools" / "package_integrated.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"tokenpet_github_updater.py"', source)
        self.assertIn('"tokenpet_version.py"', source)
        self.assertIn('"PACKAGE_MANIFEST.json"', source)

    def test_standalone_context_menu_uses_github_updater(self):
        monitor = (ROOT / "emojinoko_monitor.py").read_text(encoding="utf-8")
        definitions = [
            index
            for index in range(len(monitor))
            if monitor.startswith("    def check_auto_update", index)
        ]
        self.assertEqual(1, len(definitions))
        active_block = monitor[definitions[0] : monitor.index(
            "\n\n# ──────────────────────────────────────────────────", definitions[0]
        )]
        self.assertIn("find_newer_release", active_block)
        self.assertIn("download_and_verify", active_block)
        self.assertNotIn("if getattr(self, \"STANDALONE\"", active_block)


if __name__ == "__main__":
    unittest.main()
