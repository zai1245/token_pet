"""Compile a test-only probe into an isolated copy of the real Unity player."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

from unity_renderer_bridge import UnityRendererBridge


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "unity_poc/Build"


def find_compiler():
    if not shutil.which("dotnet"):
        return None
    try:
        sdks = subprocess.check_output(["dotnet", "--list-sdks"], text=True, timeout=10).splitlines()
        for entry in reversed(sdks):
            version, location = entry.split(" [", 1)
            compiler = Path(location.rstrip("]")) / version / "Roslyn/bincore/csc.dll"
            if compiler.is_file():
                return compiler
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


COMPILER = find_compiler() if os.name == "nt" else None


@unittest.skipUnless(COMPILER and (BUILD / "TokenPetUnity.exe").is_file(),
                     "Built Windows Mono player and .NET SDK required")
class UnityThrowRuntimeTests(unittest.TestCase):
    def test_native_sampling_handoff_and_canvas_rotation(self):
        with tempfile.TemporaryDirectory(prefix="tokenpet-throw-test-") as directory:
            work = Path(directory)
            runtime = work / "runtime"
            # A crash reporter may intentionally outlive the player and keep a
            # temporary executable locked. It is not part of these assertions.
            shutil.copytree(BUILD, runtime, ignore=shutil.ignore_patterns("UnityCrashHandler64.exe"))
            scripts = ROOT / "unity_poc/Assets/TokenPet/Scripts"
            bootstrap = work / "TokenPetPocBootstrap.cs"
            source = (scripts / bootstrap.name).read_text(encoding="utf-8")
            marker = "StartCoroutine(AnnounceReady());"
            self.assertEqual(1, source.count(marker))
            bootstrap.write_text(source.replace(marker, marker +
                '\n            new GameObject("Throw physics probe").AddComponent<TokenPet.ThrowPhysicsProbe>();'),
                encoding="utf-8")
            managed = runtime / "TokenPetUnity_Data/Managed"
            arguments = ["/nologo", "/target:library", "/langversion:9.0", "/nostdlib+", "/optimize+",
                         "/define:UNITY_STANDALONE_WIN,UNITY_STANDALONE,UNITY_64,UNITY_6000_0,ENABLE_LEGACY_INPUT_MANAGER",
                         f'/out:"{managed / "Assembly-CSharp.dll"}"']
            arguments += [f'/reference:"{path}"' for path in sorted(managed.glob("*.dll"))
                          if path.name != "Assembly-CSharp.dll"]
            arguments += [f'"{path}"' for path in sorted(scripts.glob("*.cs")) if path.name != bootstrap.name]
            arguments += [f'"{bootstrap}"', f'"{ROOT / "tests/unity/ThrowPhysicsProbe.cs"}"']
            response_file = work / "probe.rsp"
            response_file.write_text("\n".join(arguments), encoding="utf-8")
            result = subprocess.run(["dotnet", str(COMPILER), "@" + str(response_file)],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            output, log = work / "result.txt", work / "player.log"
            bridge = UnityRendererBridge(runtime / "TokenPetUnity.exe")
            popen = subprocess.Popen

            def launch(command, **kwargs):
                return popen([*command, "-logFile", str(log)], **kwargs)

            try:
                with mock.patch.dict(os.environ, TOKENPET_THROW_PROBE_OUTPUT=str(output)), \
                        mock.patch("unity_renderer_bridge.subprocess.Popen", side_effect=launch):
                    self.assertTrue(bridge.start())
                exit_code = bridge.process.wait(timeout=25)
                details = output.read_text() if output.exists() else log.read_text(errors="replace")[-4000:]
                self.assertEqual(0, exit_code, details)
                self.assertTrue(details.startswith("PASS:"), details)
                print(details)
            finally:
                bridge.stop()


if __name__ == "__main__":
    unittest.main()
