import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("bladerf_power", ROOT / "bladerf_power.py")
module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(module)


class ParserTests(unittest.TestCase):
    def test_frequency_suffixes(self):
        self.assertEqual(module.floatish("2.4M"), 2_400_000)
        self.assertEqual(module.intish("10k"), 10_000)

    def test_duration_composition(self):
        self.assertEqual(module.timeish("1h30m5s"), 5_405)

    def test_zero_formatting(self):
        self.assertEqual(module.suffixed(0), "0")

    def test_frequency_plan_is_contiguous(self):
        plan = module.freq_planning(100, 1_000, 10, 200)
        self.assertGreaterEqual(len(plan), 1)
        self.assertEqual(plan[0][0], 90)

    def test_fft_normalization(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy is not installed")
        n = 128
        raw = np.zeros(n * 2, dtype=np.int16)
        raw[::2] = 2048
        values = module.fft_dbfs(raw, lambda size: np.ones(size))
        self.assertAlmostEqual(float(values[0]), 0.0, places=5)


if __name__ == "__main__":
    unittest.main()
