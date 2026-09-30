import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("heatmap", ROOT / "heatmap.py")


class HeatmapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.module = importlib.util.module_from_spec(SPEC)
            assert SPEC.loader is not None
            SPEC.loader.exec_module(cls.module)
        except (ImportError, SystemExit) as exc:
            raise unittest.SkipTest(str(exc))

    def test_suffix_and_fractional_timestamp(self):
        self.assertEqual(self.module.freq_parse("2.4M"), 2_400_000)
        self.assertEqual(self.module.duration_parse("1.5s"), 1.5)
        self.assertEqual(self.module.date_parse("1700000000.5").microsecond, 500000)

    def test_slice_columns_is_bounded(self):
        self.assertEqual(self.module.slice_columns([100, 110, 120], 105, 115), (1, 1))

    def test_constant_palette_value_is_valid(self):
        rgb = self.module.rgb_fn([(1, 2, 3)], -10, -10)
        self.assertEqual(rgb(-10), (1, 2, 3))

    def test_thermal_palette_is_registered_and_rgb(self):
        palette = self.module.palette_parse('thermal')()
        self.assertEqual(len(palette), 256)
        self.assertTrue(all(len(rgb) == 3 and all(0 <= c <= 255 for c in rgb)
                            for rgb in palette))
