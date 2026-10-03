# Audit and port notes

## Fixed

- Ported the command-line parser and runtime prints to Python 3.
- Removed the deprecated `docopt` dependency from the main CLI.
- Added dependency-light `--dry-run` validation.
- Replaced gzip shell commands with Python's `gzip` module, eliminating output
  path shell injection.
- Added UTF-8 output handling and safer numeric range validation.
- Fixed heatmap slicing that referenced undefined `low`/`high` names.
- Fixed Pillow's removed `Image.ANTIALIAS` and `FreeTypeFont.getsize` APIs.
- Removed the automatic network download of `Vera.ttf`.
- Fixed equal min/max color scaling and mutable default sets.
- Copied capture buffers before asynchronous FFT work to prevent data races.
- Added configurable ADC sample rate and post-retune settle delay.
- Replaced fragile SciPy window attribute lookup with validated `get_window`.
- Kept worker manager lifetime explicit and shut down workers cleanly.
- Added empty-range and floating-point heatmap guards.
- Added SC16_Q11 normalization and FFT coherent-gain correction for stable
  amplitude dBFS math.
- Added per-retune epochs so frames captured during LO settling are discarded.
- Preserved CSV chronology by collecting asynchronous FFT results in submission
  order before writing.
- Rounded FFT sizes with `scipy.fft.next_fast_len` for better throughput while
  maintaining requested-or-better bin resolution.
- Added callback-side settle deadlines so post-retune partial frames cannot
  slip through as valid measurements.
- Added configurable complete-frame discard after each retune for PLL/AGC
  transient rejection.
- Added user-facing heatmap errors for malformed or empty input.
- Switched heatmap parsing to the CSV module and fixed fractional Unix/ISO
  timestamps, final compressed-bucket flushing, and O(1) timestamp lookup.
- Removed obsolete network-download code and made bundled-font lookup robust
  when installed as a package.
- Added a reusable `spectrum_math.py` DSP layer with amplitude/power/PSD
  metrics, ENBW correction, DC/IQ correction, calibration offsets, and clipping
  diagnostics.
- Added Ruff lint coverage and corrected remaining parser, exception-boundary,
  import-hygiene, and renderer dead-code findings.
- Corrected SC16_Q11 overload detection to include the invalid positive endpoint
  (`+2048`) while retaining the valid negative endpoint (`-2048`).
- Made FFT spacing follow the device read-back ADC sample rate and limited
  tuning views by the narrower of ADC rate and analog filter bandwidth.
- Added validation before `--dry-run`, strict numeric suffix handling, short
  callback rejection, guaranteed gzip trailer flushing, and RX disable/close
  cleanup.
- Added current Nuand `bladerf.BladeRF` compatibility through a synchronous RX
  adapter, including serial-to-`devstr` resolution, public/private enum lookup,
  and `current_as_buffer()` conversion to SC16_Q11 `int16` samples.
- Eliminated the historical half-spectrum waste: each LO now contributes the
  complete trusted interval around the center frequency instead of retaining
  only one sideband. The exact LO/DC coordinate is retained so CSV rows remain
  geometrically contiguous; DC suppression changes values, not bin positions.
- Added bounded retune retry with readback validation and exponential backoff,
  so transient USB/NIOS control failures do not automatically destroy long
  surveys.
- Corrected PSD math to use equivalent noise bandwidth in Hz:
  `ENBW_bins * sample_rate / FFT_N`. The previous `sample_rate * ENBW_bins`
  denominator understated PSD by roughly `10*log10(FFT_N)`.
- Added `heatmap_fast.py` support for frequency-wrap sweep reconstruction,
  minimum coverage checks, explicit peak/mean/median/percentile reducer modes,
  optional no-interpolation output for quantitative plots, overlap averaging in
  linear power, and ruler/metadata overlays.

## Remaining hardware boundary

The hardware path supports both the historical callback-oriented `bladeRF`
Python binding (`bladeRF.Device`/`device.rx`) and the current Nuand
`bladerf.BladeRF`/`Channel` synchronous API through `bladerf_backend.py`. The
adapter preserves the same epoch, settle, copy, DSP, and ordered-writer
contract. No hardware is accessed by CI or `--dry-run`; validate the installed
firmware/FPGA and USB throughput on the target device before long captures.

The historical `pybladeRF` vendored package, generated eggs, CSV captures, PNG
outputs, and build directories were excluded because they are stale/generated
artifacts rather than maintainable source.
