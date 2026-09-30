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

## Capture stage

`bladerf_power.py` parses human-readable frequency/time suffixes, validates the
range, and computes an FFT length from the requested bandwidth and bin width.
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
bandwidth, while `--bandwidth` remains the filter/FFT planning bandwidth.

## FFT and writer stage

FFT work runs in a bounded process pool. A validated SciPy window is generated
per frame, the requested sideband is sliced, and magnitudes are converted to
dB. Workers enqueue complete CSV rows to one writer process. Keeping file I/O
single-owner prevents interleaved rows and makes gzip output safe without shell
redirection. Worker and manager shutdown is explicit so normal termination
does not leak child processes.

## Heatmap stage

`heatmap.py` scans the input once to determine the time/frequency grid and DB
range, then scans again to populate pixels. This avoids retaining a multi-GB
capture in memory. Frequency and time selectors are applied during both passes
so large captures can be cropped without creating an intermediate file.

The renderer clamps palette indices, handles constant-value captures, supports
plain or gzip CSV, and uses the bundled Vera font. It never downloads assets.

## Extension points

- Add a device backend by adapting the RX setup and callback contract; keep
  `analyze_view()` hardware-independent.
- Add averaging by accumulating copied FFT frames before worker dispatch; do
  not average inside the hardware callback.
- Add a binary/SigMF writer beside the CSV writer without changing the planner.
- Add a renderer palette by returning a list of RGB tuples and registering it
  in `palette_parse()`.

## Operational limits

The hardware path depends on a compatible bladeRF Python binding and
`libbladeRF`. No hardware is required for tests or `--dry-run`. This project
does not transmit and does not implement device calibration, clock discipline,
or regulatory band-plan enforcement; those remain deployment responsibilities.
