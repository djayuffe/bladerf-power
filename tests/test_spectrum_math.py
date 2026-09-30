import unittest


class SpectrumMathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import numpy as np
            from spectrum_math import analyze_sc16, analyze_sc16_frames, sc16_to_complex, window_metrics
        except ImportError as exc:
            raise unittest.SkipTest(str(exc))
        cls.np = np
        cls.analyze_sc16 = staticmethod(analyze_sc16)
        cls.analyze_sc16_frames = staticmethod(analyze_sc16_frames)
        cls.sc16_to_complex = staticmethod(sc16_to_complex)
        cls.window_metrics = staticmethod(window_metrics)

    def test_q11_conversion_and_clipping(self):
        raw = self.np.array([2047, -2048, 2048, 0], dtype=self.np.int16)
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

    def test_frame_average_preserves_tone_and_reports_all_clips(self):
        n = 128
        window = self.np.ones(n)
        frames = self.np.zeros((3, n * 2), dtype=self.np.int16)
        frames[:, ::2] = 1024
        clean = self.analyze_sc16_frames(frames, n, 0, window, dc_notch=False)
        frames[1, 3] = 32767
        result = self.analyze_sc16_frames(frames, n, 0, window, dc_notch=False)
        self.assertEqual(result.clipped_samples, 1)
        self.assertAlmostEqual(float(clean.peak_db), -6.0206, places=3)

    def test_robust_estimators_reject_impulsive_frame(self):
        n = 128
        window = self.np.ones(n)
        frames = self.np.zeros((5, n * 2), dtype=self.np.int16)
        frames[:, ::2] = 256
        frames[2, ::2] = 1800
        median = self.analyze_sc16_frames(frames, n, 0, window,
                                          estimator='median', dc_notch=False)
        mean = self.analyze_sc16_frames(frames, n, 0, window,
                                        estimator='mean', dc_notch=False)
        self.assertLess(float(median.peak_db), float(mean.peak_db))
