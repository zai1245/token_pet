import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

from unity_renderer_bridge import UnityRendererBridge, unity_renderer_requested


class _RecordingSocket:
    def __init__(self):
        self.messages = []

    def sendall(self, data):
        self.messages.append(data)


class UnityRendererBridgeTests(unittest.TestCase):
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
        }
        self.assertTrue(bridge.send_snapshot(**kwargs))
        self.assertTrue(bridge.send_snapshot(**kwargs))
        self.assertEqual(len(recording_socket.messages), 1)
        self.assertTrue(recording_socket.messages[0].endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
