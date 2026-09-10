import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from unity_renderer_bridge import (
    UNITY_WINDOW_HEIGHT,
    UNITY_WINDOW_WIDTH,
    UnityRendererBridge,
    unity_renderer_requested,
)

MONITOR_SOURCE = Path(__file__).resolve().parents[1] / "emojinoko_monitor.py"


class _RecordingSocket:
    def __init__(self):
        self.messages = []

    def sendall(self, data):
        self.messages.append(data)


class UnityRendererBridgeTests(unittest.TestCase):
    def test_unity_window_matches_legacy_canvas_dimensions(self):
        self.assertEqual((UNITY_WINDOW_WIDTH, UNITY_WINDOW_HEIGHT), (340, 300))

    def test_renderer_is_opt_in(self):
        with mock.patch.object(sys, "argv", ["TokenPet"]):
            self.assertFalse(unity_renderer_requested({}))
            self.assertTrue(unity_renderer_requested({"renderer_backend": "unity"}))

        with mock.patch.object(sys, "argv", ["TokenPet", "--unity-poc"]):
            self.assertTrue(unity_renderer_requested({}))

    def test_missing_player_fails_without_starting_process(self):
        missing = Path(tempfile.gettempdir()) / "tokenpet-no-such-renderer.exe"
        bridge = UnityRendererBridge(missing)
        self.assertFalse(bridge.start())
        self.assertIsNone(bridge.process)
        events = bridge.poll_events()
        self.assertEqual(events[0]["event_name"], "start_failed")

    def test_identical_snapshots_are_throttled(self):
        bridge = UnityRendererBridge("unused.exe")
        recording_socket = _RecordingSocket()
        bridge._connection = recording_socket
        bridge._connected_event.set()

        kwargs = {
            "state": "idle",
            "emotion": "normal",
            "accessory": None,
            "look_x": 0.0,
            "look_y": 0.0,
            "mouth": "open",
            "level": 3,
            "xp": 25.0,
            "xp_max": 200.0,
            "satiety": 72.5,
            "coins": 44,
        }
        self.assertTrue(bridge.send_snapshot(**kwargs))
        self.assertTrue(bridge.send_snapshot(**kwargs))
        self.assertEqual(len(recording_socket.messages), 1)
        self.assertTrue(recording_socket.messages[0].endswith(b"\n"))
        self.assertIn(b'"level":3', recording_socket.messages[0])
        self.assertIn(b'"mouth":"open"', recording_socket.messages[0])
        self.assertIn(b'"satiety":72.5', recording_socket.messages[0])
        self.assertIn(b'"coins":44', recording_socket.messages[0])

    def test_desktop_motion_and_popups_are_forwarded_to_unity(self):
        bridge = UnityRendererBridge("unused.exe")
        recording_socket = _RecordingSocket()
        bridge._connection = recording_socket

        self.assertTrue(bridge.move_window(12.4, 98.7))
        self.assertTrue(bridge.show_popup("+5 XP", 170, 120, "#f9e2af"))

        move = recording_socket.messages[0].decode("utf-8")
        popup = recording_socket.messages[1].decode("utf-8")
        self.assertIn('"command":"move_window"', move)
        self.assertIn('"x":12', move)
        self.assertIn('"y":99', move)
        self.assertIn('"command":"popup"', popup)
        self.assertIn('"text":"+5 XP"', popup)

    def test_unity_release_reuses_original_desktop_fall_engine(self):
        source = MONITOR_SOURCE.read_text(encoding="utf-8")
        self.assertIn("def _begin_unity_release_fall", source)
        self.assertIn("bridge.move_window(x, y)", source)
        self.assertIn('self.pet.state = "backflip"', source)
        self.assertIn('self.pet.state = "fall"', source)
        self.assertIn("max(-9.0, min(10.0, vy * 0.016))", source)
        self.assertIn("self._unity_floor_bounced = False", source)
        self.assertIn("def _apply_unity_desktop_metrics", source)
        self.assertIn('event_name == "desktop_metrics"', source)

    def test_furniture_state_is_forwarded_to_unity(self):
        bridge = UnityRendererBridge("unused.exe")
        recording_socket = _RecordingSocket()
        bridge._connection = recording_socket

        self.assertTrue(bridge.sync_furniture([
            {"id": "futon", "x": 40, "y": 80, "width": 180, "height": 100}
        ]))
        message = recording_socket.messages[0].decode("utf-8")
        self.assertIn('"command":"sync_furniture"', message)
        self.assertIn('\\"id\\":\\"futon\\"', message)

    def test_unity_popup_uses_global_outside_click_detection_without_grab(self):
        source = MONITOR_SOURCE.read_text(encoding="utf-8")
        menu_source = source.split("class TokenPetActionMenu", 1)[1].split(
            "class HudWindow", 1
        )[0]
        self.assertIn("GetAsyncKeyState(0x01)", menu_source)
        self.assertIn("_poll_global_dismiss", menu_source)
        self.assertIn('("✕  退出寵物", self.root.destroy)', source)
        self.assertIn('is_exit = "退出寵物" in label', menu_source)
        self.assertNotIn("grab_set()", menu_source)


if __name__ == "__main__":
    unittest.main()
