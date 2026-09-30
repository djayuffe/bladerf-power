# Changelog

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
