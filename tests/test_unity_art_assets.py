import struct
from pathlib import Path
import unittest


RESOURCE_DIR = (
    Path(__file__).resolve().parents[1]
    / "unity_poc"
    / "Assets"
    / "TokenPet"
    / "Resources"
)


def read_png_ihdr(path: Path):
    header = path.read_bytes()[:29]
    if len(header) < 29 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"Not a valid PNG: {path}")
    if header[12:16] != b"IHDR":
        raise AssertionError(f"PNG has no leading IHDR chunk: {path}")
    return struct.unpack(">IIBBBBB", header[16:29])


class UnityArtAssetTests(unittest.TestCase):
    def test_rig_bodies_have_real_transparency_and_working_resolution(self):
        for filename in ("tokenpet_body.png", "tokenpet_body_faceless.png"):
            with self.subTest(filename=filename):
                width, height, bit_depth, color_type, _, _, _ = read_png_ihdr(
                    RESOURCE_DIR / filename
                )
                self.assertGreaterEqual(width, 1024)
                self.assertGreaterEqual(height, 1024)
                self.assertEqual(8, bit_depth)
                self.assertIn(
                    color_type,
                    {4, 6},
                    "body PNG must contain an alpha channel",
                )

    def test_original_sprite_remains_available_as_fallback(self):
        self.assertTrue((RESOURCE_DIR / "tokenpet_stylized.png").is_file())


if __name__ == "__main__":
    unittest.main()
