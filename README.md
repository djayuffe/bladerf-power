# bladeRF Power Survey

Receive-only spectrum surveying for Nuand bladeRF hardware, with an offline
heatmap renderer. This is an audited Python 3 port of the original project.

The project is intentionally split into two stages: a hardware-facing survey
writer and a deterministic offline renderer. That separation makes long RF
captures restartable, compressible, and safe to analyze on another machine.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the complete data path and
extension points.

## What this project does

`bladerf-power` turns a bladeRF receiver into a repeatable, receive-only
spectrum survey instrument. It plans overlapping tuning views, waits for the
LO/AGC path to settle, captures SC16_Q11 I/Q frames, computes calibrated FFT
metrics, and writes an ordered CSV stream. `heatmap.py` then renders that
stream as a time/frequency PNG without loading the entire capture into RAM.

The project is designed for unattended surveys and post-processing:

- hardware capture and offline rendering are separate commands;
- compressed CSV is streamable and restart-friendly;
- amplitude, power, and PSD outputs share one tested DSP implementation;
- current and legacy Nuand Python bindings use the same capture contract;
- every result retains the effective bin width and device-selected ADC rate;
- clipping, DC offset, IQ correction, calibration, and retune diagnostics are
  explicit rather than hidden in a “magic” normalization constant.

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

# Reject impulsive interference while averaging five frames
python3 bladerf_power.py 430M:440M:2k --average-frames 5 \
  --estimator median --file robust.csv.gz --compress

# Keep the raw SC16_Q11 stream and a standards-oriented SigMF sidecar
python3 bladerf_power.py 433M:435M:2k --sigmf-prefix captures/433mhz

# Export calibrated PSD instead of amplitude dBFS
python3 bladerf_power.py 100M:110M:5k --metric psd --calibration-db 2.3 \
  --iq-gain 0.998 --iq-phase -0.4 --file calibrated.csv

# Crop and annotate a large capture during rendering
python3 heatmap.py uhf.csv.gz uhf.png --low 433M --high 435M \
  --db -120 -20 --ytick 1m --palette thermal
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

For a source checkout, the analysis-only install is sufficient for `--dry-run`
and heatmap rendering. Install the binding supplied by your platform’s
libbladeRF package for hardware capture; keep the binding and firmware/FPGA
versions matched. Verify the device first with `bladeRF-cli -p` or the Nuand
device-operation checks before starting a long survey.

## Capture workflow

1. Start with `--dry-run` to validate the range, units, filter margin, rate,
   settling, and averaging settings.
2. Run a short narrow-band capture with a conservative settle time and one or
   two settle frames. Inspect clipping and the first few rows before widening
   the sweep.
3. Increase `--num-workers` only when CPU is the bottleneck; USB/host transfer
   loss is never fixed by adding FFT workers.
4. Use `--average-frames` to trade sweep speed for lower uncorrelated noise.
   It averages linear power after the retune barrier, not logarithmic dB rows.
5. Render the capture offline with `heatmap.py`, then crop and adjust the dB
   range without touching the original data.

Example end-to-end run:

```sh
python3 bladerf_power.py 433M:435M:2k \
  --bandwidth 2M --sample-rate 2.4M \
  --settle-time 0.02 --settle-frames 2 --average-frames 2 \
  --metric psd --file 433mhz.csv.gz --compress
python3 heatmap.py 433mhz.csv.gz 433mhz.png \
  --low 433M --high 435M --db -130 -20 --palette extended
```

## Validation, benchmark, and auto-configuration advisor

Run the diagnostic tool before a deployment or after changing firmware,
drivers, host USB topology, or analysis parameters:

```sh
# Deterministic DSP, SC16_Q11 endpoint, and clipping checks
bladerf-diagnostics --self-test --json

# Benchmark FFT sizes, windows, metrics, and frame averaging
bladerf-diagnostics --benchmark --fft-sizes 256,1024,4096 --repeats 5 --json

# Run both suites and include a non-destructive device readback probe
bladerf-diagnostics --auto-configure --device YOUR_SERIAL --json

# Measure receive-only USB delivery at a controlled ADC rate
bladerf-diagnostics --usb-test --usb-seconds 5 \
  --usb-rate 2400000 --usb-buffer-size 8192 --device YOUR_SERIAL --json
```

The benchmark reports median latency, frames/second, peak level, noise floor,
and clipped-sample counts for every tested combination. The recommendation is
chosen only from configurations with no synthetic clipping and is a measured
throughput/quality suggestion—not a claim that one setting is safe for every
antenna or RF environment. `--auto-configure` does not transmit, flash
firmware, or persist gain/rate changes; it combines the synthetic recommendation
with the device’s current read-back values so an operator can review the
profile before starting a survey.

The USB test measures successful SC16_Q11 payload delivery, not RF sensitivity:
`payload_bytes_per_second` is four bytes per complex sample and
`rate_utilization` compares delivered samples with the requested ADC rate.
Run it at several buffer sizes/rates when diagnosing host USB limits, dropped
buffers, or a capture that cannot sustain its configured rate.

## CLI reference

The positional range is `LOWER:UPPER:BIN_WIDTH`; suffixes `k`, `M`, `G`, `T`,
`P`, and `E` are accepted. Important controls are:

| Option | Purpose |
| --- | --- |
| `--bandwidth` | Requested analog RX filter bandwidth. The device may quantize it. |
| `--sample-rate` | Requested ADC rate. FFT spacing uses the read-back value. |
| `--filter-margin` | Fraction of the usable half-band retained per tuning view. |
| `--settle-time` / `--settle-frames` | Retune lock barrier and transient rejection. |
| `--average-frames` | Number of accepted frames averaged in linear power. |
| `--estimator` | `mean`, `median`, `trimmed`, or `winsorized` robust power estimator. |
| `--metric amplitude\|power\|psd` | Output dBFS amplitude, dBFS power, or dBFS/Hz PSD. |
| `--window-type` | Any window accepted by `scipy.signal.get_window`. |
| `--iq-gain` / `--iq-phase` | Optional complex IQ correction before the FFT. |
| `--calibration-db` | External absolute calibration offset. |
| `--num-workers` | Parallel FFT workers; CSV writing remains ordered. |
| `--raw-file` / `--sigmf-prefix` | Optional raw `ci16_le` or SigMF capture beside CSV. |

Run `python3 bladerf_power.py --help` for the complete option list.

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

The CSV values are dBFS-derived measurements, not absolute dBm. Convert to
dBm only after applying a traceable external calibration for the antenna,
cable/filter losses, front-end gain, and device frequency response. A row’s
`sample count` is the number of complex ADC samples represented by each FFT;
the effective bin width is the fourth field and is based on the actual device
sample rate.

## Project layout

- `bladerf_power.py` — capture planner, retune loop, SC16 FFT analysis, and
  streaming CSV writer.
- `capture_io.py` — optional raw SC16_Q11 and SigMF sidecar writer.
- `bladerf_diagnostics.py` — self-test, clipping sweep, benchmark matrix, and
  configuration advisor.
- `heatmap.py` — two-pass CSV reader and PIL renderer.
- `tests/` — hardware-free parser and CLI regression tests.
- `Vera.ttf` — bundled renderer font; no network access is needed at runtime.
- `ARCHITECTURE.md` — design, tuning, concurrency, and extension notes.
- `AUDIT.md` — audit history, compatibility boundary, and deliberate limits.
- `CHANGELOG.md` — release history and user-visible changes.
- `bladerf_diagnostics.py` — self-test, exhaustive DSP benchmark, clipping
  sweep, and safe configuration advisor.

## Safety

This project is receive-only. Do not transmit, monitor restricted services, or
collect data without authorization. Follow local spectrum rules and calibrate
the bladeRF before interpreting results.

## Troubleshooting

- **No device / binding import error:** install matching libbladeRF runtime,
  firmware, FPGA image, and Nuand Python bindings; then verify with
  `bladeRF-cli -p`.
- **Requested rate differs from the log:** this is expected when libbladeRF
  selects the nearest supported hardware value. The log and CSV use the
  read-back rate for FFT math.
- **Many clipped samples:** reduce manual gain, use a front-end attenuator,
  or narrow the measurement path. Clipping is overload, not a stronger useful
  signal.
- **Splatter after every retune:** increase `--settle-time` and
  `--settle-frames`; compare repeated captures before optimizing dwell time.
- **Dropped/short stream callbacks:** reduce sample rate or buffer pressure,
  increase USB/transfer buffers, and check host USB bandwidth before increasing
  FFT workers.
- **Noisy but stable trace:** use `--average-frames`, a suitable window, and
  PSD mode for comparisons across FFT sizes.

Robust estimators need at least three averaged frames. `median` is the most
impulse-resistant; `trimmed` removes the outer 20 percent; `winsorized` clamps
the same tails before averaging. These operate on linear power and never run
inside the hardware callback. The `thermal` palette is a dark-blue/cyan/
yellow/white RGB gradient intended to make weak-to-strong signal structure
easy to inspect.

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
