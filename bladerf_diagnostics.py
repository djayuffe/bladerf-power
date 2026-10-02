"""Hardware-independent validation, benchmark, and configuration advisor.

The diagnostic command deliberately separates safe synthetic tests from
hardware probing. Synthetic tests can be run in CI and cover SC16_Q11 scaling,
clipping, DC/IQ correction, metrics, windows, FFT sizes, and frame averaging.
Hardware probing only reads/configures a temporary receiver object and reports
what libbladeRF actually accepts; it never transmits or permanently changes a
device profile.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from dataclasses import asdict, dataclass

import numpy as np

from spectrum_math import analyze_sc16, analyze_sc16_frames


def _binding_attr(module, name):
    """Return a binding enum namespace from either public or native module API."""
    value = getattr(module, name, None)
    if value is not None:
        return value
    native = getattr(module, "_bladerf", None)
    value = getattr(native, name, None) if native is not None else None
    if value is None:
        raise AttributeError("bladeRF binding does not expose %s" % name)
    return value


def _device_identifier(module, identifier):
    """Map a serial string to a devstr when the modern binding exposes devices."""
    if not identifier or not hasattr(module, "get_device_list"):
        return identifier
    for device in module.get_device_list():
        if getattr(device, "serial_str", "") == identifier:
            return getattr(device, "devstr", identifier)
    return identifier


@dataclass
class BenchmarkRow:
    fft_size: int
    window: str
    metric: str
    average_frames: int
    milliseconds: float
    frames_per_second: float
    peak_db: float
    noise_floor_db: float
    clipped_samples: int


def window_values(name: str, size: int) -> np.ndarray:
    """Return a deterministic analysis window without requiring SciPy."""
    if name == "rectangular":
        return np.ones(size)
    if name == "hann":
        return np.hanning(size)
    if name == "hamming":
        return np.hamming(size)
    if name == "blackman":
        return np.blackman(size)
    try:
        from scipy.signal import get_window
        return np.asarray(get_window(name, size, fftbins=True), dtype=float)
    except (ImportError, ValueError):
        raise ValueError("unknown diagnostic window: %s" % name)


def synthetic_frames(size: int, count: int, level: float = 0.5,
                     noise: float = 0.002, tone_bin: int = 7,
                     seed: int = 1234) -> np.ndarray:
    """Create deterministic SC16_Q11 frames with a bin-centred complex tone."""
    rng = np.random.default_rng(seed)
    n = np.arange(size)
    tone = level * np.exp(2j * np.pi * tone_bin * n / size)
    frames = tone + noise * (rng.standard_normal((count, size)) +
                             1j * rng.standard_normal((count, size)))
    raw = np.empty((count, size * 2), dtype=np.int16)
    raw[:, 0::2] = np.clip(np.rint(frames.real * 2048), -32768, 32767)
    raw[:, 1::2] = np.clip(np.rint(frames.imag * 2048), -32768, 32767)
    return raw


def clipping_sweep(size: int = 256) -> dict:
    """Validate valid endpoints and quantify overload at multiple headrooms."""
    levels = (0.25, 0.50, 0.75, 0.90, 0.99, 1.00, 1.01, 1.25, 2.0)
    rows = []
    for level in levels:
        raw = synthetic_frames(size, 1, level=level, noise=0.0)[0]
        # Force exact representable endpoints into the first I/Q pair.
        raw[0] = int(round(level * 2048))
        raw[1] = int(round(-level * 2048))
        from spectrum_math import sc16_to_complex
        _, clipped = sc16_to_complex(raw)
        rows.append({"level": level, "clipped_samples": clipped,
                     "clipping_fraction": clipped / float(raw.size)})
    return {"levels": rows, "valid_range": [-2048, 2047],
            "rule": "values >= +2048 or < -2048 are overload"}


def run_self_test() -> dict:
    """Run deterministic correctness checks and return a JSON-safe report."""
    size = 256
    window = window_values("rectangular", size)
    # +1.0 would quantize to the invalid SC16_Q11 code +2048. Use the largest
    # representable positive full-scale tone instead.
    raw = synthetic_frames(size, 1, level=2047.0 / 2048.0, noise=0.0)[0]
    result = analyze_sc16(raw, size, 0.0, window, metric="amplitude",
                          dc_notch=False)
    checks = {
        "full_scale_tone_near_0_dbfs": abs(float(result.peak_db)) < 0.1,
        "finite_spectrum": bool(np.isfinite(result.values_db).all()),
        "no_unexpected_clipping": result.clipped_samples == 0,
    }
    averaged = analyze_sc16_frames(synthetic_frames(size, 4, level=0.2),
                                   size, 0.0, window, metric="power",
                                   dc_notch=False)
    checks["averaged_spectrum_finite"] = bool(np.isfinite(averaged.values_db).all())
    checks["all_checks_pass"] = all(checks.values())
    return {"checks": checks, "clipping": clipping_sweep(size),
            "full_scale_peak_db": float(result.peak_db),
            "averaged_peak_db": float(averaged.peak_db)}


def benchmark_matrix(fft_sizes=(256, 1024, 4096), windows=("hann", "blackman"),
                      metrics=("amplitude", "power", "psd"), averages=(1, 4),
                      repeats=3) -> list[BenchmarkRow]:
    """Benchmark every requested DSP dimension using deterministic frames."""
    rows = []
    for size in fft_sizes:
        for window_name in windows:
            window = window_values(window_name, size)
            for metric in metrics:
                for average in averages:
                    frames = synthetic_frames(size, average)
                    # Warm up imports/allocation paths before timing.
                    analyze_sc16_frames(frames, size, 0.0, window, metric,
                                        dc_notch=False)
                    samples = []
                    result = None
                    for _ in range(max(1, repeats)):
                        started = time.perf_counter()
                        result = analyze_sc16_frames(frames, size, 0.0, window,
                                                     metric, dc_notch=False)
                        samples.append((time.perf_counter() - started) * 1000.0)
                    elapsed = statistics.median(samples)
                    rows.append(BenchmarkRow(
                        size, window_name, metric, average, elapsed,
                        1000.0 / elapsed if elapsed > 0 else math.inf,
                        float(result.peak_db), float(result.noise_floor_db),
                        int(result.clipped_samples)))
    return rows


def recommend(rows: list[BenchmarkRow], target_headroom_db: float = 1.0) -> dict:
    """Rank safe configurations, preferring throughput after quality guards."""
    safe = [row for row in rows if row.clipped_samples == 0 and
            row.peak_db <= -target_headroom_db]
    if not safe:
        safe = [row for row in rows if row.clipped_samples == 0]
    if not safe:
        return {"status": "no-safe-configuration", "recommendation": None}
    # PSD/power are stable for surveys; prefer the fastest safe row, then
    # prefer averaging for noise robustness, then a Hann window.
    ranked = sorted(safe, key=lambda row: (
        row.frames_per_second,
        row.average_frames > 1,
        row.window == "hann",
        row.metric in ("power", "psd")), reverse=True)
    best = ranked[0]
    return {"status": "ok", "recommendation": asdict(best),
            "tested_safe_configurations": len(safe),
            "selection": "highest measured DSP throughput with no clipping"}


def probe_hardware(identifier: str = "") -> dict:
    """Read hardware identity/current ranges without starting RX or TX."""
    try:
        try:
            import bladeRF as module
        except ImportError:
            import bladerf as module
        if hasattr(module, "Device"):
            device = module.Device(identifier)
            rx = device.rx
            backend = "legacy"
        else:
            from bladerf_backend import ModernDeviceAdapter
            device = ModernDeviceAdapter(module, identifier)
            rx = device.rx
            backend = "modern"
        report = {"status": "ok", "backend": backend,
                  "frequency_hz": int(rx.frequency),
                  "bandwidth_hz": int(rx.bandwidth),
                  "sample_rate_hz": int(rx.sample_rate)}
        if hasattr(device, "close"):
            device.close()
        return report
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}


def usb_throughput_test(identifier: str = "", duration: float = 2.0,
                        sample_rate: int = 2_400_000, buffer_size: int = 8192,
                        module=None) -> dict:
    """Measure receive delivery over USB using the current sync API.

    This is intentionally a transport test, not an RF sensitivity test. It
    counts successful SC16_Q11 buffers and reports payload throughput. The
    test stops and closes the device in all cases and never enables TX.
    """
    if duration <= 0 or sample_rate <= 0 or buffer_size <= 0:
        return {"status": "invalid", "error": "duration, rate, and buffer size must be positive"}
    try:
        if module is None:
            try:
                import bladerf as module
            except ImportError:
                return {"status": "unavailable",
                        "error": "USB benchmark requires the current bladerf Python binding"}
        if not hasattr(module, "BladeRF"):
            return {"status": "unsupported",
                    "error": "USB benchmark requires the synchronous bladerf.BladeRF API"}
        try:
            device = module.BladeRF(_device_identifier(module, identifier)) if identifier else module.BladeRF()
        except TypeError:
            device = module.BladeRF()
        channel = device.Channel(module.CHANNEL_RX(0))
        channel.frequency = int(getattr(channel, "frequency", 100_000_000))
        channel.sample_rate = int(sample_rate)
        channel.bandwidth = int(min(sample_rate, 2_000_000))
        if hasattr(channel, "gain_mode") and hasattr(module, "GainMode"):
            channel.gain_mode = module.GainMode.Manual
        if hasattr(channel, "gain"):
            channel.gain = 0
        device.sync_config(layout=_binding_attr(module, 'ChannelLayout').RX_X1,
                           fmt=_binding_attr(module, 'Format').SC16_Q11,
                           num_buffers=16, buffer_size=int(buffer_size),
                           num_transfers=8, stream_timeout=3500)
        channel.enable = True
        raw = bytearray(int(buffer_size) * 4)
        started = time.perf_counter()
        calls = 0
        samples = 0
        while time.perf_counter() - started < duration:
            device.sync_rx(raw, int(buffer_size))
            calls += 1
            samples += int(buffer_size)
        elapsed = time.perf_counter() - started
        return {"status": "ok", "backend": "modern-sync",
                "requested_sample_rate": int(sample_rate),
                "readback_sample_rate": int(getattr(channel, "sample_rate", sample_rate)),
                "readback_bandwidth": int(getattr(channel, "bandwidth", min(sample_rate, 2_000_000))),
                "buffer_samples": int(buffer_size), "buffers": calls,
                "samples": samples, "elapsed_seconds": elapsed,
                "samples_per_second": samples / elapsed,
                "payload_bytes_per_second": samples * 4 / elapsed,
                "rate_utilization": samples / elapsed / float(sample_rate)}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
    finally:
        try:
            channel.enable = False
        except (NameError, AttributeError, RuntimeError):
            pass
        try:
            if 'device' in locals() and hasattr(device, "close"):
                device.close()
        except Exception:
            pass


def usb_throughput_matrix(identifier: str, duration: float,
                          sample_rates: tuple[int, ...],
                          buffer_sizes: tuple[int, ...]) -> list[dict]:
    """Run isolated USB probes across rate/buffer combinations."""
    results = []
    for sample_rate in sample_rates:
        for buffer_size in buffer_sizes:
            result = usb_throughput_test(identifier, duration, sample_rate,
                                         buffer_size)
            result["requested_buffer_size"] = buffer_size
            results.append(result)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description="bladerf-power validation and benchmark advisor")
    parser.add_argument("--self-test", action="store_true",
                        help="run deterministic DSP/clipping checks")
    parser.add_argument("--benchmark", action="store_true",
                        help="benchmark FFT/window/metric/averaging combinations")
    parser.add_argument("--auto-configure", action="store_true",
                        help="rank a safe configuration and probe current hardware")
    parser.add_argument("--usb-test", action="store_true",
                        help="run a receive-only low-level USB throughput test")
    parser.add_argument("--usb-seconds", type=float, default=2.0)
    parser.add_argument("--usb-rate", type=int, default=2_400_000)
    parser.add_argument("--usb-buffer-size", type=int, default=8192)
    parser.add_argument("--usb-rates", default=None,
                        help="comma-separated USB test rates (overrides --usb-rate)")
    parser.add_argument("--usb-buffer-sizes", default=None,
                        help="comma-separated USB test buffer sizes")
    parser.add_argument("--device", default="", help="optional bladeRF identifier for readback")
    parser.add_argument("--calibration-file", default=None,
                        help="inspect a Nuand <serial>_dc_rx.tbl calibration table")
    parser.add_argument("--install-calibration", action="store_true",
                        help="install --calibration-file in libbladeRF's search directory")
    parser.add_argument("--fft-sizes", default="256,1024,4096",
                        help="comma-separated benchmark FFT sizes")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args(argv)
    if not (args.self_test or args.benchmark or args.auto_configure or args.usb_test or args.calibration_file):
        parser.error("select --self-test, --benchmark, --auto-configure, or --usb-test")
    report = {}
    if args.install_calibration and not args.calibration_file:
        parser.error("--install-calibration requires --calibration-file")
    if args.calibration_file:
        from calibration import inspect_calibration, install_calibration
        try:
            report["calibration"] = (install_calibration(args.calibration_file)
                                      if args.install_calibration
                                      else inspect_calibration(args.calibration_file))
        except (FileNotFoundError, ValueError, OSError) as exc:
            report["calibration"] = {"status": "invalid", "error": str(exc)}
            if not (args.self_test or args.benchmark or args.auto_configure or args.usb_test):
                print(json.dumps(report, indent=2, sort_keys=True))
                return 2
    if args.self_test or args.auto_configure:
        report["self_test"] = run_self_test()
    if args.benchmark or args.auto_configure:
        sizes = tuple(int(item) for item in args.fft_sizes.split(","))
        if any(size < 32 or size & (size - 1) for size in sizes):
            parser.error("FFT sizes must be powers of two >= 32")
        rows = benchmark_matrix(fft_sizes=sizes, repeats=max(1, args.repeats))
        report["benchmark"] = [asdict(row) for row in rows]
        report["recommendation"] = recommend(rows)
    if args.auto_configure:
        report["hardware"] = probe_hardware(args.device)
    if args.usb_test:
        rates = tuple(int(item) for item in args.usb_rates.split(',')) if args.usb_rates else (args.usb_rate,)
        buffers = tuple(int(item) for item in args.usb_buffer_sizes.split(',')) if args.usb_buffer_sizes else (args.usb_buffer_size,)
        if any(value <= 0 for value in rates + buffers):
            parser.error("USB rates and buffer sizes must be positive")
        if len(rates) == 1 and len(buffers) == 1:
            report["usb"] = usb_throughput_test(args.device, args.usb_seconds,
                                                  rates[0], buffers[0])
        else:
            report["usb"] = usb_throughput_matrix(args.device, args.usb_seconds,
                                                   rates, buffers)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    calibration_ok = report.get("calibration", {}).get("status", "ok") != "invalid"
    return 0 if calibration_ok and report.get("self_test", {}).get("checks", {}).get("all_checks_pass", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
