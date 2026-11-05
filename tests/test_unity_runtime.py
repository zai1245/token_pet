"""Optional real Windows Mono-player regression, using the local built runtime."""
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tempfile
import time
import unittest
from unittest import mock

from emojinoko_game import ShopWindow
from tokenpet_version import VERSION
from unity_renderer_bridge import UnityRendererBridge


ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "unity_poc/Build/TokenPetUnity.exe"


@unittest.skipUnless(os.name == "nt" and PLAYER.is_file(), "Built Windows Unity runtime required")
class UnityRuntimeTests(unittest.TestCase):
    def test_full_snapshot_catalog_malformed_message_and_parent_disconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "player.log"
            bridge = UnityRendererBridge(PLAYER)
            popen = subprocess.Popen

            def launch(command, **kwargs):
                return popen([*command, "-logFile", str(log)], **kwargs)

            try:
                with mock.patch("unity_renderer_bridge.subprocess.Popen", side_effect=launch):
                    self.assertTrue(bridge.start())
                events = []
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    events.extend(bridge.poll_events())
                    if any(event.get("event_name") == "ready" for event in events):
                        break
                    time.sleep(0.05)
                self.assertTrue(any(event.get("event_name") == "ready" for event in events), events)
                self.assertTrue(any(event.get("version") == f"unity-poc-{VERSION}" for event in events), events)
                bridge._connection.sendall(b'{malformed}\n')
                bridge.sync_furniture([None])  # tolerate a removed/null entry
                catalog = ShopWindow(None, None, build_ui=False).items
                furniture = [item for item in catalog if item.get("type") == "furniture"]
                bridge.sync_furniture([dict(id=item["id"], x=100 + i * 95, y=600, width=140, height=100)
                                       for i, item in enumerate(furniture)])
                profiles = json.loads((ROOT / "unity_poc/Assets/TokenPet/Resources/motion_profiles.json").read_text())
                states = [profile["id"] for profile in profiles["profiles"]]
                states += ["sleep_futon", "work_laptop", "relax_sofa", "warm_kotatsu", "watch_tv", "meditate_lamp", "water_plant", "memo_eat"]
                variants = [{"state": state} for state in states]
                variants += [{"accessory": item["id"]} for item in catalog if item.get("type") != "furniture" and item.get("type") != "food"]
                variants += [{"state": "eat", "eat_type": item["id"]} for item in catalog if item.get("type") == "food"]
                for variant in variants:
                    snapshot = dict(state="idle", emotion="happy", accessory=None, look_x=0, look_y=0,
                                    cost_usd=12.34, prompt_tokens=3_000_000_000,
                                    show_board=True, board_text=["result", "second line"])
                    snapshot.update(variant)
                    self.assertTrue(bridge.send_snapshot(**snapshot))
                    time.sleep(0.035)
                bridge.sync_furniture([])
                bridge.show_basketball(1200, 250)
                bridge.basketball_goal()
                bridge.hide_basketball()
                bridge.show_popup("review complete", 170, 100)
                time.sleep(0.3)
                self.assertTrue(bridge.running)
                # Simulate Python crashing, without sending a shutdown command.
                bridge._connection.shutdown(socket.SHUT_RDWR)
                bridge._connection.close()
                self.assertEqual(0, bridge.process.wait(timeout=10))
            finally:
                bridge.stop()
            output = log.read_text(encoding="utf-8", errors="replace")
            self.assertIn("ignored a malformed IPC command", output)
            self.assertIsNone(re.search(r"(?:\w+Exception:|NullReferenceException|MissingMethodException|Unknown accessory|Missing painted accessory)", output), output[-5000:])


if __name__ == "__main__":
    unittest.main()
