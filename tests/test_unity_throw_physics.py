import math
from types import SimpleNamespace
import unittest
from unittest import mock

import emojinoko_monitor as app
from emojinoko_monitor import canvas_drag_velocity, map_unity_throw_velocity
from unity_renderer_bridge import UnityRendererBridge


class UnityThrowPhysicsTests(unittest.TestCase):
    def monitor(self, y=300):
        pet = app.EmojinokoMonitor.__new__(app.EmojinokoMonitor)
        pet.root = mock.Mock()
        pet.root.winfo_x.return_value = 400
        pet.root.winfo_y.return_value = y
        pet._physics_win_x, pet._physics_win_y = 400, y
        pet.pet = SimpleNamespace(state="idle", roll_angle=0.0, roll_speed=0.0,
                                  eye_state="normal", mouth_state="normal")
        pet.get_current_monitor_info = mock.Mock(return_value={"work_y": 0, "work_h": 1080})
        pet.create_text_popup = mock.Mock()
        pet.update_geometry = mock.Mock()
        pet.check_furniture_overlap = mock.Mock()
        return pet

    def test_velocity_uses_canvas_impulse_including_gentle_and_fast_motion(self):
        for vx, vy in ((0, 0), (40, -30), (500, -1200), (-2000, 1800), (4000, -3000)):
            with self.subTest(velocity=(vx, vy)):
                result = map_unity_throw_velocity(vx, vy)
                self.assertEqual((vx * 0.016, vy * 0.016, math.hypot(vx, vy)), result)

    def test_invalid_velocity_cannot_poison_position(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            self.assertEqual((0, 0, 0), map_unity_throw_velocity(value, 1))

    def test_velocity_averages_last_120ms_of_motion(self):
        history = [(0.7, -500, 50), (1.0, 0, 0), (1.04, 20, -20), (1.10, 100, -60)]
        vx, vy = canvas_drag_velocity(history, 1.12)
        self.assertAlmostEqual(1000, vx)
        self.assertAlmostEqual(-600, vy)

    def test_pause_before_release_cancels_old_flick(self):
        history = [(1.0, 0, 0), (1.1, 100, -100)]
        self.assertEqual((0, 0), canvas_drag_velocity(history, 1.3))
        self.assertNotEqual((0, 0), canvas_drag_velocity(history, 1.25))

    def test_single_sample_and_tiny_sample_interval_are_safe(self):
        self.assertEqual((0, 0), canvas_drag_velocity([(1, 10, 20)], 1))
        self.assertEqual((1000, -1000), canvas_drag_velocity([(1, 0, 0), (1.001, 10, -10)], 1.002))

    def test_canvas_and_unity_release_have_identical_initial_conditions(self):
        for vx, vy, y in ((0, 0, 300), (300, -200, 300), (800, -1200, 300),
                          (-1000, 200, 300), (40, -30, 780)):
            canvas, unity = self.monitor(y), self.monitor(y)
            canvas._has_dragged = True
            canvas._drag_history = [(1.0, 0, 0), (1.1, vx * 0.1, vy * 0.1)]
            with self.subTest(velocity=(vx, vy), y=y), mock.patch.object(app, "save_config"), \
                    mock.patch.object(app.time, "time", return_value=1.12):
                canvas._on_drag_end(SimpleNamespace())
                unity._begin_unity_release_fall({"velocity_x": vx, "velocity_y": -vy, "y": y})
            self.assertEqual(vars(canvas.pet), vars(unity.pet))
            for field in ("_fall_vx", "_fall_vy", "_fall_gravity", "_fall_air_drag", "_fall_peak_y"):
                self.assertAlmostEqual(getattr(canvas, field, 0), getattr(unity, field, 0))
            self.assertEqual(canvas.create_text_popup.call_args_list, unity.create_text_popup.call_args_list)

    def test_grabbing_airborne_pet_stops_old_physics_until_release(self):
        pet = self.monitor()
        pet._unity_renderer_active = True
        pet.pet.state, pet._fall_vx, pet._fall_vy = "backflip", 10, -20
        pet._detach_unity_drag()
        pet.tick_physics()
        self.assertEqual("idle", pet.pet.state)
        self.assertEqual((0, 0), (pet._fall_vx, pet._fall_vy))
        pet.update_geometry.assert_not_called()
        pet.root.after.assert_called_once_with(16, pet.tick_physics)

    def test_release_acknowledges_before_any_desktop_move(self):
        pet = self.monitor()
        trace = mock.Mock()
        pet.unity_renderer = trace.bridge
        pet.update_geometry = trace.move
        with mock.patch.object(app, "save_config"):
            pet._begin_unity_release_fall({"drag_id": 7, "x": 500, "y": 250})
        self.assertEqual(mock.call.bridge.send({"command": "drag_release_ack", "drag_id": 7}), trace.mock_calls[0])
        self.assertEqual(mock.call.move(500, 250), trace.mock_calls[1])
        self.assertFalse(pet._unity_dragging)

    def test_stationary_drop_has_no_artificial_launch(self):
        pet = self.monitor()
        pet._release_desktop_drag(0, 0, 300)
        self.assertEqual((0, 0), (pet._fall_vx, pet._fall_vy))
        self.assertEqual(0, pet.pet.roll_speed)
        self.assertEqual("fall", pet.pet.state)

    def test_late_render_landing_event_cannot_stop_a_new_throw(self):
        pet = self.monitor()
        pet._unity_renderer_active = True
        pet.pet.state = "backflip"
        pet.unity_renderer = mock.Mock()
        pet.unity_renderer.poll_events.return_value = [{"event_name": "action_finished", "action": "land"}]
        pet._poll_unity_renderer()
        self.assertEqual("backflip", pet.pet.state)

    def test_click_release_returns_position_ownership_without_throwing(self):
        pet = self.monitor()
        pet._unity_dragging = True
        pet._release_desktop_drag = mock.Mock()
        with mock.patch.object(app, "save_config"):
            pet._begin_unity_release_fall({"action": "click", "drag_id": 3})
        self.assertFalse(pet._unity_dragging)
        pet._release_desktop_drag.assert_not_called()

    def test_ground_release_does_not_start_a_fall(self):
        pet = self.monitor(780)
        pet._release_desktop_drag(40, -30, 780)
        self.assertEqual("idle", pet.pet.state)
        self.assertFalse(hasattr(pet, "_fall_vy"))

    def test_physical_rotation_and_squash_are_in_the_snapshot(self):
        bridge = UnityRendererBridge("unused.exe")
        with mock.patch.object(bridge, "send", return_value=True) as send:
            kwargs = dict(state="fall", emotion="normal", accessory=None, look_x=0, look_y=0,
                          roll_angle=1.25, scale_x=0.9, scale_y=1.1)
            bridge.send_snapshot(**kwargs)
            kwargs["roll_angle"] = 1.5
            bridge.send_snapshot(**kwargs)
        self.assertEqual(2, send.call_count)
        self.assertEqual(1.5, send.call_args.args[0]["roll_angle"])
        self.assertEqual(0.9, send.call_args.args[0]["scale_x"])
        self.assertEqual(1.1, send.call_args.args[0]["scale_y"])


if __name__ == "__main__":
    unittest.main()
