# bladeRF Power Survey

Receive-only spectrum surveying for Nuand bladeRF hardware, with an offline
heatmap renderer. This is an audited Python 3 port of the original project.

## Quick start

Create a Python 3.10+ environment and install the analysis dependencies:

```sh
python3 -m pip install -e .
python3 bladerf_power.py 300M:3.7G:10k --exit-timer 4h --file output.csv.gz --compress
python3 heatmap.py output.csv.gz output.png
```

Validate a sweep without a bladeRF, driver, NumPy, or SciPy:

```sh
python3 bladerf_power.py 100M:110M:1M --dry-run
```

Hardware capture requires a compatible `bladeRF` Python binding and
`libbladeRF` installation. The old vendored `pybladeRF` tree was intentionally
removed from this repository because it is Python 2-era generated code; use a
current binding supported by your libbladeRF release.

## Changes in the audited port

- Python 3 CLI using `argparse`; `--help`, `--version`, and `--dry-run` work
  without SDR/DSP dependencies.
- Removed shell interpolation from gzip output and added UTF-8 handling.
- Added validation for sweep direction and bin width.
- Fixed heatmap frequency slicing, equal-range color scaling, Pillow resampling,
  mutable defaults, and the missing-font/network side effect.
- Excluded generated CSV/PNG captures and build products from version control.

## Safety

This project is receive-only. Do not transmit, monitor restricted services, or
collect data without authorization. Follow local spectrum rules and calibrate
the bladeRF before interpreting results.

## License

The original project is GPLv2; see [`LICENSE.txt`](LICENSE.txt).
