import unittest

from bladerf_diagnostics import (clipping_sweep, recommend, run_self_test,
                                 usb_throughput_matrix, usb_throughput_test)


class DiagnosticsTests(unittest.TestCase):
    def test_self_test_and_clipping_boundaries(self):
        report = run_self_test()
        self.assertTrue(report["checks"]["all_checks_pass"])
        levels = {row["level"]: row["clipped_samples"]
                  for row in clipping_sweep()["levels"]}
        self.assertEqual(levels[0.99], 0)
        self.assertGreater(levels[1.01], 0)

    def test_recommendation_requires_safe_rows(self):
        rows = []
        self.assertEqual(recommend(rows)["status"], "no-safe-configuration")

    def test_usb_test_validates_without_hardware(self):
        result = usb_throughput_test(duration=0)
        self.assertEqual(result["status"], "invalid")

    def test_usb_test_rejects_legacy_module(self):
        result = usb_throughput_test(duration=0.1, module=object())
        self.assertEqual(result["status"], "unsupported")

    def test_usb_matrix_is_empty_safe_without_hardware(self):
        results = usb_throughput_matrix('', 0, (1,), (1,))
        self.assertEqual(results[0]["status"], "invalid")
        self.assertEqual(results[0]["requested_buffer_size"], 1)


if __name__ == "__main__":
    unittest.main()
