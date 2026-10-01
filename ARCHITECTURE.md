# Architecture

## Overview

`bladerf-power` is a receive-only spectrum-survey pipeline:

```text
CLI/config
   │
   ▼
frequency planner ──► bladeRF RX retune ──► SC16 callback buffer
                                               │
                                               ▼
                                      copied FFT work item
                                               │
                                               ▼
                                      worker-pool FFT/DB
                                               │
                                               ▼
                                   one ordered CSV writer
                                               │
                                               ▼
                                      CSV or gzip CSV
                                               │
                                               ▼
                              heatmap two-pass renderer ──► PNG
```

The capture and render stages are deliberately independent. Capturing touches
hardware and can run for hours; rendering is offline, repeatable, and can be
re-run with different crops, palettes, DB limits, and time compression.

`bladerf_diagnostics.py` is the validation boundary around both stages. Its
self-test uses deterministic synthetic SC16_Q11 frames; its benchmark sweeps
FFT sizes, windows, metrics, averaging counts, latency, throughput, noise
floor, and clipping; its auto-configuration mode combines that result with a
non-destructive hardware readback. No diagnostic mode transmits or writes
device firmware.

Its optional USB test uses the synchronous RX API directly, repeatedly submits
SC16_Q11 buffers for a bounded interval, and reports delivered samples,
four-byte complex-sample payload rate, effective readback rate, and utilization.
It measures transport capacity only; it does not claim RF sensitivity or prove
that a particular antenna/gain configuration is unclipped.

## Calibration-table integration

`calibration.py` validates Nuand binary table magic, filename/serial naming,
size, direction, and SHA-256 provenance, then can install the file into the
documented per-user libbladeRF search directory. Capture opens the device only
after validation/installation, allowing libbladeRF to apply its own nearest
frequency correction entry during each retune. The application does not parse
or reinterpret the opaque DC/IQ coefficients as power calibration.

## Backend compatibility

The planner and DSP code do not depend on one particular Python binding. The
legacy `bladeRF.Device` backend receives callback buffers; the current Nuand
`bladerf.BladeRF` backend is adapted by `bladerf_backend.py` and receives
synchronous buffers from `sync_rx`. Both expose the same internal contract:
interleaved SC16_Q11 bytes become complete epoch-tagged frames, are copied
before worker dispatch, and are closed through the same shutdown path. This
keeps API compatibility code out of frequency planning and measurement math.

## Capture stage

`bladerf_power.py` parses human-readable frequency/time suffixes, validates the
range, configures RX, reads back the effective bandwidth/sample rate, and
computes an FFT length from the effective ADC rate and requested bin width.
The frequency planner creates adjacent tuning views with a filter-margin
overlap so edge bins are discarded where anti-aliasing leakage is strongest.

For each view, the bladeRF RX stream supplies interleaved SC16 samples. The
callback only fills a fixed-size frame and signals the main loop; it does not
perform FFT work. Before dispatch, the main loop copies the frame. This copy is
important: the callback reuses its buffer immediately after signaling, so
passing the original array would create a data race and corrupt spectra.

After every retune, `--settle-time` gives the tuner/LO time to lock before the
next frame is accepted. The default is conservative; lower it only after
checking repeated captures on the specific device and firmware. A separate
`--sample-rate` allows the ADC rate to differ from the analog capture
bandwidth, while `--bandwidth` remains the analog filter setting. The planner
quantizes useful view width to whole FFT bins and uses the narrower of the
analog filter bandwidth and ADC sample rate. This prevents a requested 28 MHz
filter from being mistaken for 28 MHz of usable complex sample span when the
ADC is configured below that rate.

## FFT and writer stage

FFT work runs in a bounded process pool. The requested FFT length is rounded up
with SciPy's `next_fast_len`, so the actual bin width is never worse than the
request while favoring efficient composite FFT sizes. A validated window is
generated per frame, the requested sideband is sliced, and magnitudes are
converted to dBFS. Workers return complete rows; the main loop collects those
results in submission order before sending them to one writer process. This
preserves chronological CSV order without interleaved file I/O. Worker and
manager shutdown is explicit so normal termination does not leak child
processes.

## Measurement math

SC16 samples are interpreted as complex signed 16-bit I/Q pairs and normalized
by the SC16_Q11 full-scale value (2048). The valid signed ADC interval is
`[-2048, 2047]`; out-of-range values are counted as clipping. Each frame is
windowed and its FFT is divided by the window coherent gain, `sum(window)`,
before conversion to amplitude dBFS:

```text
samples = (I + jQ) / 2048
A[k] = abs(FFT(samples * window)[k]) / sum(window)
dBFS[k] = 20 * log10(max(A[k], 1e-15))
```

This makes a bin-centred full-scale complex tone approximately 0 dBFS and
prevents FFT length/window choice from changing its nominal level. It is not
calibrated dBm; antenna gain, front-end loss, device calibration, and window
noise bandwidth still require an external reference.

FFT spacing uses the device's read-back ADC sample rate. The analog filter
bandwidth only limits the useful view, so the planner uses
`min(sample_rate, bandwidth)` and never assumes a requested rate was accepted
unchanged by libbladeRF.

The DSP layer also supports power dBFS and PSD dBFS/Hz. PSD divides by sample
rate and window equivalent noise bandwidth, which makes noise measurements
comparable across FFT sizes and windows. Optional DC removal, IQ gain/phase
correction, and a user-supplied calibration offset are applied before the FFT.
Frames that contain signed-16-bit clipping are counted so a survey can flag
overload rather than treating it as a real signal. For SC16_Q11 the nominal
sample range is approximately +/-2048, not the full int16 range.

## Retune and lock methodology

Every view has an epoch. The callback tags completed frames with that epoch;
the main loop increments it before changing frequency, resets the partial
frame, applies the retune, and waits `--settle-time`. Frames captured during
the transition are discarded by epoch rather than analyzed as the new
frequency. The callback also clears partial frames until the settle deadline,
covering samples that arrive after the frequency write but before the device
has stabilized. This is safer than sleeping alone because the callback
continues while the LO settles.

After the timer expires, `--settle-frames` discards a configurable number of
complete frames as an additional guard against PLL/AGC transients. Use zero
only after validating the device with repeated narrow-band captures; one or two
discarded frames usually gives better data quality than trying to reduce every
millisecond of dwell time.

For a new device, capture the same narrow band repeatedly at several settle
times, compare the first accepted frame with later frames, and choose the
shortest time that removes frequency splatter or amplitude transients. The
software does not claim a hardware PLL lock bit; the epoch/settle method is a
data-quality barrier.

For noisy signals, `--average-frames N` collects N accepted frames after the
settle barrier and averages their linear power spectra in the worker. This
reduces uncorrelated noise while preserving tones, at the cost of N frame
times per view. Averaging stays outside the callback so the SDR stream remains
real-time and only complete, epoch-tagged copies enter the worker queue.
The estimator is selectable: arithmetic mean, median, 20% trimmed mean, or
20% winsorized mean. Robust estimators reject impulsive interference without
changing capture timing or callback behavior.

## Raw and SigMF output

The optional `--raw-file` writer stores interleaved little-endian SC16_Q11
samples beside the analyzed CSV. `--sigmf-prefix PREFIX` writes
`PREFIX.sigmf-data` plus `PREFIX.sigmf-meta` with `ci16_le` datatype, sample
rate, and frequency-segment records. The writer consumes the same immutable
frame copies as the DSP worker, so frequency planning and retune epochs remain
unchanged.

## Heatmap stage

`heatmap.py` scans the input once to determine the time/frequency grid and DB
range, then scans again to populate pixels. This avoids retaining a multi-GB
capture in memory. Frequency and time selectors are applied during both passes
so large captures can be cropped without creating an intermediate file.

The renderer clamps palette indices, handles constant-value captures, supports
plain or gzip CSV, and uses the bundled Vera font. It never downloads assets.
CSV parsing uses Python's CSV reader rather than string splitting, accepts
fractional Unix timestamps and fractional ISO seconds, rejects malformed rows,
and maps rendered timestamps through an index table instead of repeated linear
searches. The final compressed pixel bucket is explicitly flushed so the last
time interval is never lost.

## Extension points

- Add a device backend by adapting the RX setup and callback contract; keep
  `analyze_view()` hardware-independent.
- Add alternative robust estimators beside the existing linear-power frame
  average; do not average inside the hardware callback.
- Add a binary/SigMF writer beside the CSV writer without changing the planner.
- Add a renderer palette by returning a list of RGB tuples and registering it
  in `palette_parse()`; `thermal` is the reference gradient implementation.

## Operational limits

The hardware path depends on a compatible bladeRF Python binding and
`libbladeRF`. No hardware is required for tests or `--dry-run`. This project
does not transmit and does not implement device calibration, clock discipline,
or regulatory band-plan enforcement; those remain deployment responsibilities.

The software cannot infer antenna response, absolute RF power, external clock
quality, USB signal integrity, or a hardware PLL lock bit. Those are measured
or verified at deployment. Read-back settings, clipping counts, settle
barriers, and stream-error diagnostics make those limits visible in the data
instead of silently hiding them.
