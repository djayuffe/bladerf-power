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

## Remaining hardware boundary

The original bladeRF callback API is tied to an old third-party Python binding.
The hardware path is retained but requires a current compatible binding and
libbladeRF installation. No hardware is accessed by CI or `--dry-run`.

The historical `pybladeRF` vendored package, generated eggs, CSV captures, PNG
outputs, and build directories were excluded because they are stale/generated
artifacts rather than maintainable source.
