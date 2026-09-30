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


if __name__ == "__main__":
    unittest.main()
