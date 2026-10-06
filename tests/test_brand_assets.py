import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web" / "frontend"


def png_size(path):
    data = path.read_bytes()[:24]
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"{path} is not a PNG")
    return struct.unpack(">II", data[16:24])


class BrandAssetTests(unittest.TestCase):
    def test_official_logo_and_web_banner_are_published_at_native_size(self):
        self.assertEqual((500, 500), png_size(FRONTEND / "img" / "logo.png"))
        self.assertEqual(
            (1920, 1080),
            png_size(FRONTEND / "img" / "flowmate-workspace-hero.png"),
        )

    def test_web_icons_match_manifest_dimensions(self):
        expected = {
            "favicon-16x16.png": (16, 16),
            "favicon-32x32.png": (32, 32),
            "apple-touch-icon.png": (180, 180),
            "android-chrome-192x192.png": (192, 192),
            "android-chrome-512x512.png": (512, 512),
        }
        for name, size in expected.items():
            with self.subTest(name=name):
                self.assertEqual(size, png_size(FRONTEND / "img" / name))

    def test_primary_surfaces_use_the_official_brand_assets(self):
        landing = (FRONTEND / "landing.html").read_text(encoding="utf-8")
        app = (FRONTEND / "index.html").read_text(encoding="utf-8")

        self.assertIn("/img/flowmate-workspace-hero.png?v=20261006-brand", landing)
        self.assertIn("/img/logo.png?v=20261006-brand", landing)
        self.assertIn("/img/logo.png?v=20261006-brand", app)
        self.assertNotIn('id="bmLine"', app)

    def test_official_palette_is_exposed_in_web_and_mobile_themes(self):
        landing = (FRONTEND / "landing.html").read_text(encoding="utf-8").upper()
        react_native = (
            ROOT / "mobile" / "src" / "theme" / "ThemeContext.js"
        ).read_text(encoding="utf-8").upper()
        flutter = (
            ROOT / "mobile_flutter" / "lib" / "theme" / "app_theme.dart"
        ).read_text(encoding="utf-8").upper()

        for color in ("0058DE", "87DEF1", "8BC24B", "F4C364"):
            self.assertIn(color, landing)
            self.assertIn(color, react_native)
            self.assertIn(color, flutter)


if __name__ == "__main__":
    unittest.main()
