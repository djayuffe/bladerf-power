# Changelog

## 0.4.0 — 2026-09-30

- Added `--average-frames` for linear-power averaging across accepted frames.
- Kept callback capture real-time by batching immutable frame copies in the
  main loop and preserving ordered worker output.
- Added CLI validation and regression coverage for averaging and clipping.

## 0.3.1 — 2026-09-30

- Corrected synthetic DSP test binding so the NumPy-backed CI suite executes
  the intended functions rather than passing the test instance implicitly.

## 0.3.0 — 2026-09-30

- Added reusable DSP math for amplitude dBFS, power dBFS, and PSD dBFS/Hz.
- Added DC-notch, IQ gain/phase, calibration-offset, and clipping controls.
- Added synthetic math tests for SC16 conversion, tone normalization, and ENBW.

## 0.2.7 — 2026-09-30

- Hardened heatmap CSV parsing and fractional timestamp support.
- Fixed final compressed-bucket rendering and timestamp lookup performance.
- Made installed font resolution deterministic and removed dead network code.
- Added heatmap parser, palette, and slice regression coverage.

## 0.2.6 — 2026-09-30

- Added configurable `--settle-frames` for post-retune transient rejection.
- Added clearer heatmap failures for malformed or empty captures.

## 0.2.5 — 2026-09-30

- Preserved CSV chronology by collecting asynchronous FFT results in order.
- Added `next_fast_len` FFT sizing for better throughput at requested
  resolution.
- Added device-frequency readback checks and callback-side settle-frame
  rejection.
- Tightened worker, buffer, parameter, and heatmap edge-case handling.

## 0.2.4 — 2026-09-30

- Added SC16_Q11 full-scale normalization and window coherent-gain correction.
- Added per-retune epochs to discard frames captured during LO settling.
- Added frequency-plan and FFT-normalization regression tests.
- Documented measurement math, calibration limits, and lock methodology.

## 0.2.3 — 2026-09-30

- Expanded README with tuning, output-format, and operating guidance.
- Added `ARCHITECTURE.md` documenting planner, lock settling, FFT workers,
  ordered CSV output, and the two-pass heatmap renderer.

## 0.2.2 — 2026-09-30

- Added safer retune settling and configurable ADC sample rate.
- Eliminated asynchronous FFT buffer races.
- Improved worker shutdown, FFT window validation, and heatmap edge handling.
- Added parser and tuning regression tests.

## 0.2.1 — 2026-09-30

- Added hardware-free CLI regression tests and GitHub Actions CI.
- Added a safe local install/clean helper.
- Fixed the CLI exit status for invalid sweep ranges.
- Added explicit public release metadata and package entry points.

## 0.2.0

- Python 3 and argparse port.
- Safer gzip output and heatmap/Pillow compatibility fixes.
