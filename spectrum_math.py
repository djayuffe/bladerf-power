"""Hardware-independent DSP primitives used by the bladeRF survey pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np


@dataclass(frozen=True)
class SpectrumResult:
    values_db: np.ndarray
    frequencies_hz: np.ndarray
    clipped_samples: int
    dc_offset: complex
    noise_floor_db: float
    peak_frequency_hz: float | None
    peak_db: float | None


def sc16_to_complex(raw: np.ndarray, full_scale: float = 2048.0) -> tuple[np.ndarray, int]:
    """Convert interleaved SC16_Q11 I/Q samples and count clipping."""
    values = np.asarray(raw)
    if values.ndim != 1 or values.size % 2:
        raise ValueError("SC16 input must be a one-dimensional even-length array")
    if full_scale <= 0 or not math.isfinite(full_scale):
        raise ValueError("full_scale must be positive and finite")
    # SC16_Q11 uses the low 12 bits for signed samples; values beyond the
    # nominal +/-2048 range indicate an overloaded or mis-scaled stream.
    clipped = int(np.count_nonzero(np.abs(values) > full_scale))
    complex_samples = values[::2].astype(np.float64) + 1j * values[1::2].astype(np.float64)
    return complex_samples / full_scale, clipped


def correct_iq(samples: np.ndarray, dc_notch: bool = True, iq_gain: float = 1.0,
               iq_phase_deg: float = 0.0) -> tuple[np.ndarray, complex]:
    """Apply optional DC removal and a simple gain/phase IQ correction."""
    values = np.asarray(samples, dtype=np.complex128)
    if values.ndim != 1 or not values.size:
        raise ValueError("samples must be a non-empty one-dimensional array")
    offset = complex(values.mean())
    if dc_notch:
        values = values - offset
    if iq_gain <= 0 or not math.isfinite(iq_gain):
        raise ValueError("iq_gain must be positive and finite")
    values = values * iq_gain * np.exp(1j * math.radians(iq_phase_deg))
    return values, offset


def window_metrics(window: np.ndarray) -> tuple[float, float]:
    """Return coherent gain and equivalent noise bandwidth in bins."""
    values = np.asarray(window, dtype=np.float64)
    if values.ndim != 1 or not values.size:
        raise ValueError("window must be a non-empty one-dimensional array")
    coherent_gain = float(values.sum())
    if coherent_gain <= 0:
        raise ValueError("window has no coherent gain")
    enbw = float(values.size * np.sum(values * values) / (coherent_gain * coherent_gain))
    return coherent_gain, enbw


def analyze_sc16(raw: np.ndarray, sample_rate: float, center_frequency: float,
                 window: np.ndarray, metric: str = "amplitude",
                 full_scale: float = 2048.0, dc_notch: bool = True,
                 iq_gain: float = 1.0, iq_phase_deg: float = 0.0,
                 calibration_db: float = 0.0) -> SpectrumResult:
    """Analyze one SC16 frame with calibrated amplitude or PSD output."""
    if sample_rate <= 0 or not math.isfinite(sample_rate):
        raise ValueError("sample_rate must be positive and finite")
    samples, clipped = sc16_to_complex(raw, full_scale)
    samples, dc_offset = correct_iq(samples, dc_notch, iq_gain, iq_phase_deg)
    values = np.asarray(window, dtype=np.float64)
    if values.size != samples.size:
        raise ValueError("window length must match the sample frame")
    coherent_gain, enbw = window_metrics(values)
    spectrum = np.fft.fft(samples * values) / coherent_gain
    magnitude = np.maximum(np.abs(spectrum), 1e-15)
    if metric == "amplitude":
        db = 20.0 * np.log10(magnitude)
    elif metric == "power":
        db = 10.0 * np.log10(np.maximum(magnitude * magnitude, 1e-30))
    elif metric == "psd":
        db = 10.0 * np.log10(np.maximum(magnitude * magnitude / (sample_rate * enbw), 1e-30))
    else:
        raise ValueError("metric must be amplitude, power, or psd")
    db = db + float(calibration_db)
    frequencies = center_frequency + np.fft.fftfreq(samples.size, 1.0 / sample_rate)
    positive = np.argsort(frequencies)
    sorted_db = db[positive]
    sorted_freq = frequencies[positive]
    peak_index = int(np.argmax(sorted_db)) if sorted_db.size else None
    peak_frequency = float(sorted_freq[peak_index]) if peak_index is not None else None
    peak_db = float(sorted_db[peak_index]) if peak_index is not None else None
    noise_floor = float(np.median(sorted_db)) if sorted_db.size else float("nan")
    return SpectrumResult(sorted_db, sorted_freq, clipped, dc_offset, noise_floor,
                          peak_frequency, peak_db)


def analyze_sc16_frames(frames: np.ndarray, sample_rate: float, center_frequency: float,
                        window: np.ndarray, metric: str = "power",
                        full_scale: float = 2048.0, dc_notch: bool = True,
                        iq_gain: float = 1.0, iq_phase_deg: float = 0.0,
                        calibration_db: float = 0.0) -> SpectrumResult:
    """Average multiple frames in linear power before converting to dB.

    Linear-power averaging reduces uncorrelated noise approximately with the
    number of frames while preserving narrowband signals. A single frame is
    delegated to :func:`analyze_sc16` so the fast path has no extra overhead.
    """
    values = np.asarray(frames)
    if values.ndim == 1:
        return analyze_sc16(values, sample_rate, center_frequency, window, metric,
                            full_scale, dc_notch, iq_gain, iq_phase_deg,
                            calibration_db)
    if values.ndim != 2 or values.shape[0] < 1:
        raise ValueError("frames must be a non-empty two-dimensional array")
    results = [analyze_sc16(frame, sample_rate, center_frequency, window,
                            "amplitude", full_scale, dc_notch, iq_gain,
                            iq_phase_deg, 0.0) for frame in values]
    # The per-frame amplitude spectrum is converted back to linear power
    # before averaging.  This avoids the bias and information loss caused by
    # averaging logarithmic values, while retaining the single-frame fast path.
    power = np.mean([np.square(10.0 ** (result.values_db / 20.0))
                     for result in results], axis=0)
    if metric == "amplitude":
        db = 10.0 * np.log10(np.maximum(power, 1e-30))
    elif metric in ("power", "psd"):
        if metric == "psd":
            _, enbw = window_metrics(np.asarray(window))
            power = power / (sample_rate * enbw)
        db = 10.0 * np.log10(np.maximum(power, 1e-30))
    else:
        raise ValueError("metric must be amplitude, power, or psd")
    db += float(calibration_db)
    peak_index = int(np.argmax(db))
    return SpectrumResult(db, results[0].frequencies_hz, sum(r.clipped_samples for r in results),
                          sum(r.dc_offset for r in results) / len(results),
                          float(np.median(db)), float(results[0].frequencies_hz[peak_index]),
                          float(db[peak_index]))
