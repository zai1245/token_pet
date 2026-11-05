import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import test_unity_throw_runtime as native


@unittest.skipUnless(os.name == "nt" and native.COMPILER and (native.BUILD / "TokenPetUnity.exe").is_file(),
                     "Built Windows Mono player and .NET SDK required")
class UnityArtRuntimeTests(unittest.TestCase):
    def test_real_desktop_alpha_edges_shadows_and_ui(self):
        with tempfile.TemporaryDirectory(prefix="tokenpet-art-backdrop-") as directory:
            fixture = Path(directory) / "fixture.py"
            ready, stop = Path(directory) / "ready", Path(directory) / "stop"
            fixture.write_text('''import ctypes, pathlib, sys, tkinter as tk
try: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except (AttributeError, OSError): pass
api = ctypes.windll.user32
x, y, w, h = [api.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
left, top = x + min(360, max(0, w - 850)), y + min(260, max(0, h - 430))
root = tk.Tk()
root.overrideredirect(True)
root.geometry(f"850x430+{left}+{top}")
root.configure(bg="white")
root.attributes("-topmost", True)
root.update()
pathlib.Path(sys.argv[1]).touch()
def poll():
    if pathlib.Path(sys.argv[2]).exists(): root.destroy()
    else: root.after(50, poll)
root.after(50, poll)
root.after(45000, root.destroy)
root.mainloop()
''', encoding="utf-8")
            process = subprocess.Popen([sys.executable, str(fixture), str(ready), str(stop)],
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                deadline = time.monotonic() + 5
                while not ready.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(ready.exists(), "foreign backdrop did not start")
                with mock.patch.dict(os.environ, TOKENPET_ART_FOREIGN_PID=str(process.pid)):
                    native.UnityThrowRuntimeTests.run_native_probe(self, "ArtQualityProbe", "TOKENPET_ART_PROBE_RESULT",
                                                                 native.ROOT / "scratch/art-review")
            finally:
                stop.touch()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
