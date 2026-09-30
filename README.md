# bladeRF Power Survey

Receive-only spectrum surveying for Nuand bladeRF hardware, with an offline
heatmap renderer. This is an audited Python 3 port of the original project.

The project is intentionally split into two stages: a hardware-facing survey
writer and a deterministic offline renderer. That separation makes long RF
captures restartable, compressible, and safe to analyze on another machine.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the complete data path and
extension points.

## Quick start

Create a Python 3.10+ environment and install the analysis dependencies:

```sh
python3 -m pip install -e .
python3 bladerf_power.py 300M:3.7G:10k --exit-timer 4h --file output.csv.gz --compress
python3 heatmap.py output.csv.gz output.png
```

Useful capture controls:

```sh
# Faster retuning on a stable device
python3 bladerf_power.py 430M:440M:2k --bandwidth 2M --sample-rate 2.4M \
  --settle-time 0.005 --num-workers 4 --file uhf.csv.gz --compress

# Reject two complete frames after each retune when lock transients are severe
python3 bladerf_power.py 430M:440M:2k --settle-time 0.02 --settle-frames 2 \
  --file conservative.csv.gz --compress

# Average four accepted frames in linear power for a lower-noise survey
python3 bladerf_power.py 430M:440M:2k --average-frames 4 \
  --metric power --file averaged.csv.gz --compress

# Export calibrated PSD instead of amplitude dBFS
python3 bladerf_power.py 100M:110M:5k --metric psd --calibration-db 2.3 \
  --iq-gain 0.998 --iq-phase -0.4 --file calibrated.csv

# Crop and annotate a large capture during rendering
python3 heatmap.py uhf.csv.gz uhf.png --low 433M --high 435M \
  --db -120 -20 --ytick 1m --palette extended
```

The requested bin width is quantized to the actual FFT bin width. The program
reads back the hardware-selected bandwidth and ADC sample rate after setting
them; libbladeRF may quantize requests to supported discrete values. FFT
spacing follows the ADC sample rate, while each tuning view is limited by the
narrower of the analog bandwidth and sample rate. Smaller bins increase
resolution and CPU/disk cost; a larger `--settle-time` improves lock
confidence on devices that need longer retunes. `--num-workers` controls FFT
parallelism, while CSV writing remains ordered through a single writer.

Validate a sweep without a bladeRF, driver, NumPy, or SciPy:

```sh
python3 bladerf_power.py 100M:110M:1M --dry-run
```

Hardware capture requires a Nuand Python binding and `libbladeRF` installation.
Both the historical `bladeRF.Device` callback API and the current
`bladerf.BladeRF` synchronous API are supported. The old vendored `pybladeRF`
tree was intentionally removed because it is Python 2-era generated code; use
a binding supported by your libbladeRF release.

## Changes in the audited port

- Python 3 CLI using `argparse`; `--help`, `--version`, and `--dry-run` work
  without SDR/DSP dependencies.
- Removed shell interpolation from gzip output and added UTF-8 handling.
- Added validation for sweep direction and bin width.
- Added amplitude dBFS, power dBFS, and PSD dBFS/Hz metrics.
- Added SC16 clipping counts, DC removal, IQ gain/phase correction, and
  calibration offsets.
- Uses the bladeRF SC16_Q11 signed range correctly (`-2048..2047`) and reports
  overloaded samples instead of silently treating them as valid ADC data.
- Added configurable ADC sample rate, post-retune settling, and validated FFT
  window selection for more reliable tuning/lock behavior.
- Added configurable linear-power frame averaging (`--average-frames`) to
  reduce uncorrelated noise without averaging inside the hardware callback.
- Asynchronous FFT workers now receive immutable per-frame copies, preventing
  capture/analysis races during fast sweeps.
- Fixed heatmap frequency slicing, equal-range color scaling, Pillow resampling,
  mutable defaults, and the missing-font/network side effect.
- Excluded generated CSV/PNG captures and build products from version control.

## Output format

Each CSV row contains timestamp, lower frequency, upper frequency, bin width,
sample count, and dB values. Files may be plain UTF-8 CSV or gzip-compressed
CSV. The heatmap reader accepts both forms, supports frequency/time cropping,
DB range control, palettes, time compression, fractional timestamps, and
timestamp tick marks. It performs two passes, so automatic DB limits reflect
the selected crop rather than the entire capture.

Malformed rows, empty crops, invalid suffixes, and non-positive frequency steps
fail with actionable errors. The bundled font is resolved relative to the
installed module, so `bladerf-heatmap` works outside the source directory and
never downloads assets.

## Project layout

- `bladerf_power.py` — capture planner, retune loop, SC16 FFT analysis, and
  streaming CSV writer.
- `heatmap.py` — two-pass CSV reader and PIL renderer.
- `tests/` — hardware-free parser and CLI regression tests.
- `Vera.ttf` — bundled renderer font; no network access is needed at runtime.
- `ARCHITECTURE.md` — design, tuning, concurrency, and extension notes.

## Safety

This project is receive-only. Do not transmit, monitor restricted services, or
collect data without authorization. Follow local spectrum rules and calibrate
the bladeRF before interpreting results.

## Hardware and ADC references

The capture path uses libbladeRF's interleaved little-endian SC16_Q11 stream.
Nuand documents the format as sign-extended 16-bit I/Q values with a nominal
12-bit range of `-2048..2047`; the implementation normalizes by 2048 and
counts values outside that interval as clipping. Hardware-specific frequency,
bandwidth, gain, and sample-rate ranges are selected by libbladeRF and may be
quantized per device, so readback values—not legacy compile-time constants—are
used for measurement math.

See the [SC16_Q11 reference implementation](https://github.com/Nuand/bladeRF/blob/master/host/misc/matlab/load_sc16q11.m),
[current Python binding](https://github.com/Nuand/bladeRF/tree/master/host/libraries/libbladeRF_bindings/python),
and [Nuand's device-operation guide](https://github.com/Nuand/bladeRF/wiki/Getting-Started%3A-Verifying-Basic-Device-Operation).

## License

The original project is GPLv2; see [`LICENSE.txt`](LICENSE.txt).
