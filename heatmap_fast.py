#!/usr/bin/env python3

import argparse
import csv
import gzip
import math
from datetime import datetime

import numpy as np
from PIL import Image


def parse_freq(s):
    s = str(s).strip()
    if not s:
        raise ValueError("empty frequency")
    suffix = s[-1].lower()
    scales = {"g": 1e9, "m": 1e6, "k": 1e3}
    if suffix in scales:
        return float(s[:-1]) * scales[suffix]
    return float(s)


def open_csv(path):
    if str(path).lower().endswith(".gz"):
        return gzip.open(path, "rt", newline="")
    return open(path, "rt", newline="")


def parse_time(date_s, time_s):
    return datetime.strptime(
        date_s.strip() + " " + time_s.strip(),
        "%Y-%m-%d %H:%M:%S",
    )


def palette_extended(x):
    stops = np.array([
        [0.00,   0,   0,   0],
        [0.10,   0,   0,  60],
        [0.24,   0,   0, 180],
        [0.38,   0, 120, 255],
        [0.52,   0, 240, 220],
        [0.64,   0, 255,  50],
        [0.76, 255, 255,   0],
        [0.88, 255,  40,   0],
        [1.00, 255, 255, 255],
    ], dtype=np.float64)

    flat = np.asarray(x, dtype=np.float64).ravel()
    rgb = np.empty((flat.size, 3), dtype=np.float64)

    for c in range(3):
        rgb[:, c] = np.interp(flat, stops[:, 0], stops[:, c + 1])

    return rgb.reshape(x.shape + (3,)).astype(np.uint8)


def reduce_peak(values, width):
    values = np.asarray(values, dtype=np.float32)
    n = values.size

    if n == 0:
        return np.full(width, np.nan, dtype=np.float32)

    if n == width:
        return values.copy()

    if n < width:
        x = np.arange(n, dtype=np.float64)
        xo = np.linspace(0.0, n - 1.0, width)
        good = np.isfinite(values)

        if good.sum() == 0:
            return np.full(width, np.nan, dtype=np.float32)

        if good.sum() == 1:
            return np.full(width, values[good][0], dtype=np.float32)

        return np.interp(
            xo, x[good], values[good]
        ).astype(np.float32)

    edges = np.linspace(0, n, width + 1, dtype=np.int64)
    out = np.full(width, np.nan, dtype=np.float32)

    for i in range(width):
        a = int(edges[i])
        b = int(edges[i + 1])

        if b <= a:
            b = a + 1

        block = values[a:min(b, n)]
        good = block[np.isfinite(block)]

        if good.size:
            out[i] = np.max(good)

    return out


def reduce_values(values, width, mode="peak"):
    values = np.asarray(values, dtype=np.float32)
    n = values.size

    if mode == "peak":
        return reduce_peak(values, width)

    if n == 0:
        return np.full(width, np.nan, dtype=np.float32)

    if n == width:
        return values.copy()

    if n < width:
        # Upscaling remains interpolation regardless of reducer.  No reducer can
        # create new measured RF bins.
        return reduce_peak(values, width)

    edges = np.linspace(0, n, width + 1, dtype=np.int64)
    out = np.full(width, np.nan, dtype=np.float32)

    for i in range(width):
        a = int(edges[i])
        b = int(edges[i + 1])

        if b <= a:
            b = a + 1

        block = values[a:min(b, n)]
        good = block[np.isfinite(block)]

        if not good.size:
            continue

        if mode == "mean":
            # Average in linear power, not logarithmic dB.
            out[i] = 10.0 * np.log10(np.mean(10.0 ** (good / 10.0)))
        elif mode == "median":
            out[i] = float(np.median(good))
        else:
            raise ValueError("unknown frequency reducer: %s" % mode)

    return out


def fill_frequency_holes(matrix):
    x = np.arange(matrix.shape[1], dtype=np.float64)

    for y in range(matrix.shape[0]):
        row = matrix[y]
        good = np.isfinite(row)

        if good.all():
            continue

        count = int(good.sum())

        if count >= 2:
            row[~good] = np.interp(
                x[~good], x[good], row[good]
            )
        elif count == 1:
            row[~good] = row[good][0]

    return matrix


def scale_time(matrix, height, mode="peak", percentile=95.0):
    source_h, width = matrix.shape

    if source_h == height:
        return matrix

    if source_h == 1:
        return np.repeat(matrix, height, axis=0)

    if source_h < height:
        yi = np.floor(
            np.linspace(0, source_h, height, endpoint=False)
        ).astype(np.int64)

        yi = np.clip(yi, 0, source_h - 1)
        return matrix[yi]

    edges = np.linspace(
        0, source_h, height + 1, dtype=np.int64
    )

    out = np.full(
        (height, width), np.nan, dtype=np.float32
    )

    for y in range(height):
        a = int(edges[y])
        b = int(edges[y + 1])

        if b <= a:
            b = a + 1

        block = matrix[a:min(b, source_h)]

        with np.errstate(all="ignore"):
            if mode == "peak":
                out[y] = np.nanmax(block, axis=0)
            elif mode == "mean":
                linear = 10.0 ** (block / 10.0)
                out[y] = 10.0 * np.log10(np.nanmean(linear, axis=0))
            elif mode == "median":
                out[y] = np.nanmedian(block, axis=0)
            elif mode == "percentile":
                out[y] = np.nanpercentile(block, percentile, axis=0)
            else:
                raise ValueError("unknown time reducer: %s" % mode)

    return out



def _nice_step(span, target_ticks=12):
    import math
    raw = float(span) / max(1, int(target_ticks))
    if raw <= 0:
        return 1.0
    decade = 10.0 ** math.floor(math.log10(raw))
    q = raw / decade
    if q <= 1.0:
        nice = 1.0
    elif q <= 2.0:
        nice = 2.0
    elif q <= 5.0:
        nice = 5.0
    else:
        nice = 10.0
    return nice * decade


def _format_frequency(hz):
    hz = float(hz)
    if abs(hz) >= 1e9:
        return "%.3g GHz" % (hz / 1e9)
    if abs(hz) >= 1e6:
        return "%.4g MHz" % (hz / 1e6)
    if abs(hz) >= 1e3:
        return "%.4g kHz" % (hz / 1e3)
    return "%.4g Hz" % hz


def add_spectrum_overlay(
        image,
        low_hz,
        high_hz,
        start_time=None,
        end_time=None,
        bin_width_hz=None,
        sample_rate_hz=None,
        bandwidth_hz=None,
        sweep_count=None,
        db_min=None,
        db_max=None,
    title="bladeRF Spectrum Survey"):

    from PIL import Image, ImageDraw, ImageFont
    import math

    if image.mode != "RGB":
        image = image.convert("RGB")

    src_w, src_h = image.size

    left = max(105, int(src_w * 0.055))
    right = max(90, int(src_w * 0.045))
    top = max(105, int(src_h * 0.080))
    bottom = max(115, int(src_h * 0.095))

    out_w = src_w + left + right
    out_h = src_h + top + bottom

    out = Image.new("RGB", (out_w, out_h), (8, 10, 14))
    out.paste(image, (left, top))

    draw = ImageDraw.Draw(out, "RGBA")

    try:
        font = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            max(12, int(src_h * 0.014))
        )
        font_small = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            max(10, int(src_h * 0.011))
        )
        font_title = ImageFont.truetype(
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            max(16, int(src_h * 0.020))
        )
    except Exception:
        font = ImageFont.load_default()
        font_small = font
        font_title = font

    x0 = left
    y0 = top
    x1 = left + src_w - 1
    y1 = top + src_h - 1

    span = float(high_hz - low_hz)

    major = _nice_step(span, 12)
    minor = major / 5.0

    first_minor = math.ceil(low_hz / minor) * minor
    f = first_minor

    while f <= high_hz + minor * 0.01:
        x = x0 + int(round((f - low_hz) / span * (src_w - 1)))

        ratio = f / major
        is_major = abs(ratio - round(ratio)) < 1e-6

        if is_major:
            draw.line((x, y0, x, y1), fill=(255,255,255,46), width=1)
            tick = max(10, int(top * 0.14))

            draw.line((x, y0-tick, x, y0), fill=(230,235,245,230), width=2)
            draw.line((x, y1, x, y1+tick), fill=(230,235,245,230), width=2)

            label = _format_frequency(f)
            box = draw.textbbox((0,0), label, font=font)
            tw = box[2] - box[0]

            draw.text(
                (x - tw/2, y0-tick-26),
                label,
                font=font,
                fill=(235,240,248,255)
            )
            draw.text(
                (x - tw/2, y1+tick+5),
                label,
                font=font,
                fill=(235,240,248,255)
            )
        else:
            draw.line((x, y0, x, y1), fill=(255,255,255,17), width=1)
            tick = max(5, int(top * 0.07))
            draw.line((x, y0-tick, x, y0), fill=(190,200,215,180), width=1)
            draw.line((x, y1, x, y1+tick), fill=(190,200,215,180), width=1)

        f += minor

    time_span = None
    if start_time is not None and end_time is not None:
        try:
            time_span = float(end_time) - float(start_time)
        except Exception:
            time_span = None

    if time_span is not None and time_span > 0:
        tmajor = _nice_step(time_span, 8)
        tminor = tmajor / 5.0
        t = 0.0

        while t <= time_span + 1e-9:
            y = y0 + int(round(t / time_span * (src_h - 1)))
            is_major = abs(t / tmajor - round(t / tmajor)) < 1e-6

            if is_major:
                draw.line((x0, y, x1, y), fill=(255,255,255,38), width=1)
                tick = 12
                draw.line((x0-tick, y, x0, y), fill=(230,235,245,230), width=2)
                draw.line((x1, y, x1+tick, y), fill=(230,235,245,230), width=2)

                label = "+%.1fs" % t if t < 60 else "+%.1fm" % (t/60.0)
                box = draw.textbbox((0,0), label, font=font_small)
                tw = box[2]-box[0]
                th = box[3]-box[1]

                draw.text(
                    (x0-tick-tw-7, y-th/2),
                    label,
                    font=font_small,
                    fill=(220,228,240,255)
                )
                draw.text(
                    (x1+tick+7, y-th/2),
                    label,
                    font=font_small,
                    fill=(220,228,240,255)
                )
            else:
                draw.line((x0, y, x1, y), fill=(255,255,255,12), width=1)

            t += tminor

    draw.rectangle(
        (x0, y0, x1, y1),
        outline=(240,244,250,255),
        width=2
    )

    title_box = draw.textbbox((0,0), title, font=font_title)
    title_w = title_box[2]-title_box[0]

    draw.text(
        ((out_w-title_w)/2, 12),
        title,
        font=font_title,
        fill=(245,248,252,255)
    )

    meta = [
        "%s - %s" % (
            _format_frequency(low_hz),
            _format_frequency(high_hz)
        )
    ]

    if bin_width_hz is not None:
        meta.append("bin %s" % _format_frequency(bin_width_hz))

    if sample_rate_hz is not None:
        meta.append("Fs %s" % _format_frequency(sample_rate_hz))

    if bandwidth_hz is not None:
        meta.append("BW %s" % _format_frequency(bandwidth_hz))

    if sweep_count is not None:
        meta.append("%d sweeps" % int(sweep_count))

    metadata = " | ".join(meta)

    box = draw.textbbox((0,0), metadata, font=font_small)
    mw = box[2]-box[0]

    draw.text(
        ((out_w-mw)/2, 43),
        metadata,
        font=font_small,
        fill=(190,202,218,255)
    )

    if db_min is not None and db_max is not None:
        legend = "%.1f .. %.1f dB" % (float(db_min), float(db_max))
        box = draw.textbbox((0,0), legend, font=font_small)
        lw = box[2]-box[0]

        draw.text(
            (x1-lw, out_h-bottom+58),
            legend,
            font=font_small,
            fill=(215,225,238,255)
        )

    draw.text(
        (x0, out_h-bottom+58),
        "Frequency ->",
        font=font_small,
        fill=(215,225,238,255)
    )

    return out

def main():
    p = argparse.ArgumentParser(
        description=(
            "Fast wideband heatmap renderer for bladerf-power CSV. "
            "Reconstructs sweeps by RF-frequency wrap rather than "
            "timestamp changes."
        )
    )

    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--low", default="237.5M")
    p.add_argument("--high", default="3.8G")
    p.add_argument("--width", type=int, default=3840)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--db", nargs=2, type=float, metavar=("MIN", "MAX"))
    p.add_argument(
        "--percentile",
        nargs=2,
        type=float,
        default=(1.0, 99.9),
        metavar=("LOW", "HIGH"),
    )
    p.add_argument(
        "--min-coverage",
        type=float,
        default=0.80,
        help="Minimum fraction of RF range required for a reconstructed sweep",
    )
    p.add_argument(
        "--frequency-reducer",
        choices=("peak", "mean", "median"),
        default="peak",
        help="How native RF bins are reduced to output pixels",
    )
    p.add_argument(
        "--time-reducer",
        choices=("peak", "mean", "median", "percentile"),
        default="peak",
        help="How multiple sweeps are reduced into output rows",
    )
    p.add_argument(
        "--time-percentile",
        type=float,
        default=95.0,
        help="Percentile used when --time-reducer percentile is selected",
    )
    p.add_argument(
        "--overlap-mode",
        choices=("peak", "mean"),
        default="peak",
        help="How overlapping LO measurements are combined inside one sweep",
    )
    p.add_argument(
        "--no-fill-holes",
        action="store_true",
        help="Leave missing RF bins dark instead of interpolating visual holes",
    )
    p.add_argument(
        "--no-overlay",
        action="store_true",
        help="Save only the heatmap raster without rulers/metadata",
    )

    args = p.parse_args()

    low = parse_freq(args.low)
    high = parse_freq(args.high)

    if high <= low:
        raise SystemExit("ERROR: --high must be greater than --low")

    if args.width < 1 or args.height < 1:
        raise SystemExit("ERROR: width/height must be positive")

    if not (0.0 < args.min_coverage <= 1.0):
        raise SystemExit("ERROR: --min-coverage must be in (0,1]")

    if not (0.0 <= args.time_percentile <= 100.0):
        raise SystemExit("ERROR: --time-percentile must be in [0,100]")

    native_bin = None
    record_count = 0
    data_min = math.inf
    data_max = -math.inf

    print("Pass 1/2: validating CSV...")

    with open_csv(args.input) as f:
        reader = csv.reader(f)

        for row in reader:
            if len(row) < 7:
                continue

            try:
                step = float(row[4])
                values = np.asarray(row[6:], dtype=np.float32)
            except (ValueError, TypeError):
                continue

            if step <= 0 or values.size == 0:
                continue

            if native_bin is None:
                native_bin = step
            elif not math.isclose(
                step,
                native_bin,
                rel_tol=1e-6,
                abs_tol=1e-6,
            ):
                raise SystemExit(
                    f"ERROR: inconsistent bin width: "
                    f"{step} vs {native_bin}"
                )

            good = values[np.isfinite(values)]

            if good.size:
                data_min = min(data_min, float(good.min()))
                data_max = max(data_max, float(good.max()))

            record_count += 1

    if native_bin is None or record_count == 0:
        raise SystemExit("ERROR: no valid RF records")

    nfreq = int(math.ceil((high - low) / native_bin))

    print(f"Records:              {record_count:,}")
    print(f"RF range:             {low/1e6:.6f} - {high/1e6:.6f} MHz")
    print(f"RF span:              {(high-low)/1e6:.6f} MHz")
    print(f"Native bin:           {native_bin:.3f} Hz")
    print(f"Native RF bins:       {nfreq:,}")
    print(f"Raw data range:       {data_min:.2f} .. {data_max:.2f} dB")
    print(f"Output raster:        {args.width} x {args.height}")

    sweeps = []
    sweep_times = []
    sweep_coverages = []

    current = np.full(nfreq, np.nan, dtype=np.float32)
    current_sum = np.zeros(nfreq, dtype=np.float64)
    current_weight = np.zeros(nfreq, dtype=np.float64)
    current_time = None
    previous_start = None

    def finish_sweep():
        nonlocal current, current_sum, current_weight, current_time

        if args.overlap_mode == "mean":
            measured = current_weight > 0
            current[:] = np.nan
            current[measured] = (
                10.0 * np.log10(current_sum[measured] / current_weight[measured])
            ).astype(np.float32)

        occupied = int(np.count_nonzero(np.isfinite(current)))
        coverage = occupied / float(nfreq)

        if coverage >= args.min_coverage:
            sweeps.append(reduce_values(current, args.width, args.frequency_reducer))
            sweep_times.append(current_time)
            sweep_coverages.append(coverage)

        current = np.full(nfreq, np.nan, dtype=np.float32)
        current_sum = np.zeros(nfreq, dtype=np.float64)
        current_weight = np.zeros(nfreq, dtype=np.float64)
        current_time = None

    print("Pass 2/2: reconstructing full RF sweeps...")

    with open_csv(args.input) as f:
        reader = csv.reader(f)

        for row in reader:
            if len(row) < 7:
                continue

            try:
                timestamp = parse_time(row[0], row[1])
                start = float(row[2])
                step = float(row[4])
                values = np.asarray(row[6:], dtype=np.float32)
            except (ValueError, TypeError):
                continue

            if step <= 0 or values.size == 0:
                continue

            if (
                previous_start is not None
                and start < previous_start - native_bin
            ):
                finish_sweep()

            previous_start = start

            if current_time is None:
                current_time = timestamp

            frequencies = (
                start
                + np.arange(values.size, dtype=np.float64) * step
            )

            mask = (
                (frequencies >= low)
                & (frequencies < high)
                & np.isfinite(values)
            )

            if not np.any(mask):
                continue

            ff = frequencies[mask]
            vv = values[mask]

            indices = np.floor(
                (ff - low) / native_bin + 1e-9
            ).astype(np.int64)

            valid = (
                (indices >= 0)
                & (indices < nfreq)
            )

            indices = indices[valid]
            vv = vv[valid]

            if indices.size == 0:
                continue

            if args.overlap_mode == "mean":
                np.add.at(current_sum, indices, 10.0 ** (vv / 10.0))
                np.add.at(current_weight, indices, 1.0)
            else:
                old = current[indices]

                replace = (
                    ~np.isfinite(old)
                    | (vv > old)
                )

                if np.any(replace):
                    current[indices[replace]] = vv[replace]

    finish_sweep()

    if not sweeps:
        raise SystemExit(
            "ERROR: no complete sweeps reconstructed. "
            "Try --min-coverage 0.5 for diagnosis."
        )

    matrix = np.asarray(sweeps, dtype=np.float32)

    print(f"Reconstructed sweeps: {matrix.shape[0]:,}")
    print(
        f"Sweep coverage:       "
        f"{min(sweep_coverages)*100:.2f}% .. "
        f"{max(sweep_coverages)*100:.2f}%"
    )

    finite = matrix[np.isfinite(matrix)]

    if finite.size == 0:
        raise SystemExit("ERROR: reconstructed matrix contains no data")

    p_low, p_high = args.percentile

    if not (0 <= p_low < p_high <= 100):
        raise SystemExit("ERROR: invalid percentile range")

    auto_lo, auto_hi = np.percentile(
        finite, [p_low, p_high]
    )

    if args.db is None:
        db_lo = float(auto_lo)
        db_hi = float(auto_hi)

        db_lo = max(-180.0, db_lo)
        db_hi = min(0.0, db_hi)

        if db_hi - db_lo < 20.0:
            centre = (db_lo + db_hi) * 0.5
            db_lo = centre - 10.0
            db_hi = centre + 10.0
    else:
        db_lo, db_hi = map(float, args.db)

    if not math.isfinite(db_lo) or not math.isfinite(db_hi):
        raise SystemExit("ERROR: non-finite dB limits")

    if db_hi <= db_lo:
        raise SystemExit("ERROR: dB maximum must exceed minimum")

    print(
        f"Auto percentiles:     "
        f"P{p_low:g}={auto_lo:.2f}, "
        f"P{p_high:g}={auto_hi:.2f} dB"
    )
    print(f"Display range:        {db_lo:.2f} .. {db_hi:.2f} dB")

    if not args.no_fill_holes:
        matrix = fill_frequency_holes(matrix)
    display = scale_time(matrix, args.height, args.time_reducer,
                         args.time_percentile)

    normalized = (display - db_lo) / (db_hi - db_lo)

    normalized = np.nan_to_num(
        normalized,
        nan=0.0,
        posinf=1.0,
        neginf=0.0,
    )

    normalized = np.clip(normalized, 0.0, 1.0)

    rgb = palette_extended(normalized)

    image = Image.fromarray(rgb, mode="RGB")

    saved_image = image
    if not args.no_overlay:
        start_ts = sweep_times[0].timestamp() if sweep_times else None
        end_ts = sweep_times[-1].timestamp() if sweep_times else None
        saved_image = add_spectrum_overlay(
            image,
            low,
            high,
            start_time=start_ts,
            end_time=end_ts,
            bin_width_hz=native_bin,
            sweep_count=len(sweeps),
            db_min=db_lo,
            db_max=db_hi,
        )

    saved_image.save(args.output)

    print()
    print("DONE")
    print(f"Input:                {args.input}")
    print(f"Output:               {args.output}")
    print(f"Image size:           {saved_image.width} x {saved_image.height}")
    print(f"Frequency reducer:    {args.frequency_reducer}")
    print(f"Time reducer:         {args.time_reducer}")
    print(f"Overlap mode:         {args.overlap_mode}")
    print(f"Hole interpolation:   {'off' if args.no_fill_holes else 'on'}")
    print(f"Overlay:              {'off' if args.no_overlay else 'on'}")

    if sweep_times:
        print(f"First sweep:          {sweep_times[0]}")
        print(f"Last sweep:           {sweep_times[-1]}")


if __name__ == "__main__":
    main()
