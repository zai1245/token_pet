import json
from pathlib import Path
import unittest


PROFILE_PATH = (
    Path(__file__).resolve().parents[1]
    / "unity_poc"
    / "Assets"
    / "TokenPet"
    / "Resources"
    / "motion_profiles.json"
)
LIMB_RIG_PATH = PROFILE_PATH.parents[1] / "Scripts" / "TokenPetLimbRig.cs"


class UnityMotionProfileTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        self.profiles = self.catalog["profiles"]

    def test_required_motion_profiles_are_present_once(self):
        ids = [profile["id"] for profile in self.profiles]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            {"idle", "walk", "poke", "drag", "airborne", "land"},
            set(ids),
        )

    def test_motion_values_stay_inside_safe_ranges(self):
        for profile in self.profiles:
            with self.subTest(profile=profile["id"]):
                self.assertGreater(profile["duration"], 0)
                self.assertGreater(profile["frequency"], 0)
                self.assertGreater(profile["smoothing"], 0)
                self.assertLessEqual(abs(profile["bob"]), 0.8)
                self.assertLess(abs(profile["squash"]), 0.5)
                self.assertLess(abs(profile["stretch"]), 0.5)

    def test_leg_roots_are_embedded_inside_body(self):
        source = LIMB_RIG_PATH.read_text(encoding="utf-8")
        self.assertIn("LegRootY = -0.73f", source)
        self.assertIn("new Vector2(-0.36f, LegRootY)", source)
        self.assertIn("new Vector2(0.36f, LegRootY)", source)


if __name__ == "__main__":
    unittest.main()
