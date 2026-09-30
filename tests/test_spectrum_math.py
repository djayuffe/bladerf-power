import unittest


class SpectrumMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import numpy as np
            from spectrum_math import analyze_sc16, sc16_to_complex, window_metrics
        except ImportError as exc:
            raise unittest.SkipTest(str(exc))
        cls.np = np
        cls.analyze_sc16 = staticmethod(analyze_sc16)
        cls.sc16_to_complex = staticmethod(sc16_to_complex)
        cls.window_metrics = staticmethod(window_metrics)

    def test_q11_conversion_and_clipping(self):
        raw = self.np.array([2047, -2048, 32767, 0], dtype=self.np.int16)
        samples, clipped = self.sc16_to_complex(raw)
        self.assertEqual(clipped, 1)
        self.assertEqual(samples[0], 2047 / 2048 - 1j)

    def test_full_scale_tone_is_zero_dbfs(self):
        n = 256
        raw = self.np.zeros(n * 2, dtype=self.np.int16)
        raw[::2] = 2048
        result = self.analyze_sc16(raw, n, 100.0, self.np.ones(n), dc_notch=False)
        self.assertAlmostEqual(float(result.peak_db), 0.0, places=5)

    def test_psd_metric_and_window_enbw(self):
        n = 128
        window = self.np.hanning(n)
        coherent, enbw = self.window_metrics(window)
        self.assertGreater(coherent, 0)
        self.assertGreater(enbw, 1)
        raw = self.np.zeros(n * 2, dtype=self.np.int16)
        result = self.analyze_sc16(raw, n, 0, window, metric='psd', dc_notch=False)
        self.assertTrue(self.np.all(self.np.isfinite(result.values_db)))
