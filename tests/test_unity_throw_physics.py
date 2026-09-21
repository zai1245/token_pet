import unittest

from emojinoko_monitor import map_unity_throw_velocity


class UnityThrowPhysicsTests(unittest.TestCase):
    def test_gentle_release_drops_instead_of_self_launching(self):
        vx, vy, speed = map_unity_throw_velocity(40.0, -30.0)
        self.assertLess(speed, 110.0)
        self.assertEqual(0.0, vx)
        self.assertGreater(vy, 0.0)

    def test_upward_flick_can_reach_basketball_hoop(self):
        vx, vy, _ = map_unity_throw_velocity(500.0, -1200.0)
        self.assertGreater(vx, 0.0)
        self.assertLess(vy, 0.0)
        ballistic_height = (vy * vy) / (2.0 * 0.85)
        self.assertGreater(ballistic_height, 300.0)

    def test_extreme_pointer_spikes_are_capped(self):
        vx, vy, _ = map_unity_throw_velocity(100000.0, -100000.0)
        self.assertEqual(24.0, vx)
        self.assertEqual(-32.0, vy)


if __name__ == "__main__":
    unittest.main()
