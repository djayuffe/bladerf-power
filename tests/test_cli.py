import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]


class CliTests(unittest.TestCase):
    def test_dry_run_does_not_require_hardware(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bladerf_power.py"), "100M:110M:1M", "--dry-run"],
            check=True, capture_output=True, text=True,
        )
        self.assertIn("validated sweep", result.stdout)

    def test_rejects_reversed_range(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bladerf_power.py"), "110M:100M:1M", "--dry-run"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2)

    def test_settle_frames_is_exposed(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "bladerf_power.py"), "100M:110M:1M",
             "--dry-run", "--settle-frames", "2"],
            check=True, capture_output=True, text=True,
        )
        self.assertIn("validated sweep", result.stdout)
