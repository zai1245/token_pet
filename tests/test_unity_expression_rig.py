from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RIG_SOURCE = (
    ROOT
    / "unity_poc"
    / "Assets"
    / "TokenPet"
    / "Scripts"
    / "TokenPetExpressionRig.cs"
)
BOOTSTRAP_SOURCE = RIG_SOURCE.with_name("TokenPetPocBootstrap.cs")


class UnityExpressionRigTests(unittest.TestCase):
    def test_interactive_states_have_expression_poses(self):
        source = RIG_SOURCE.read_text(encoding="utf-8")
        for state in ("walk", "poke", "drag", "airborne", "land"):
            with self.subTest(state=state):
                self.assertIn(f'case "{state}"', source)

    def test_face_uses_overlay_compatible_line_renderers(self):
        source = RIG_SOURCE.read_text(encoding="utf-8")
        self.assertIn("LineRenderer leftEye", source)
        self.assertIn("LineRenderer mouthFill", source)
        self.assertIn("LineRenderer philtrum", source)
        self.assertIn("SetDorkyCatMouth", source)
        self.assertNotIn("SpriteRenderer", source)

    def test_faceless_body_is_loaded_before_visual_fallbacks(self):
        source = BOOTSTRAP_SOURCE.read_text(encoding="utf-8")
        faceless = source.index('Resources.Load<Texture2D>("tokenpet_body_faceless")')
        layered = source.index('Resources.Load<Texture2D>("tokenpet_body")')
        original = source.index('Resources.Load<Texture2D>("tokenpet_stylized")')
        self.assertLess(faceless, layered)
        self.assertLess(layered, original)


if __name__ == "__main__":
    unittest.main()
