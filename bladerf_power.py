#!/usr/bin/env python
"""\
bladeRF Receiver
Usage:
  bladerf_power.py <lower:upper:bin_width> [options]
  bladerf_power.py (-h | --help)
  bladerf_power.py --version

Arguments:
  <lower:upper:bin_width>  Frequency sweep parameters, e.g. <900M:1.2G:10K>

Options:
  -h --help                Show this screen.
  -v --version             Show version.
  -f --file=<f>            File to write to [default: output.csv].
  -z --compress            Compress output with gzip on-the-fly [default: False]
  -e --exit-timer=<et>     Set capture time (example: 5h23m2s) [default: 0]
  -b --bandwidth=<bw>      Capture bandwidth [default: 28M].
  -M --filter-margin=<fm>  Anti-aliasing filter margin [default: .85]. This value
                           is combined with bandwidth to view only a portion of
                           the captured signal to combat leaky anti-aliasing
                           filters. Actual useful signal bandwidth is fm*bw/2.
  -W --window-type=<wt>    Set FFT analysis windowing function [default: hann]
  -g --lna-gain=<g>        Set LNA gain [default: LNA_GAIN_MAX]
  -o --rx-vga1=<g>         Set vga1 gain [default: RXVGA1_GAIN_MIN]
  -w --rx-vga2=<g>         Set vga2 gain [default: RXVGA2_GAIN_MIN]
  -d --device=<d>          Device identifier [default: ]
  -n --num-buffers=<nb>    Number of transfer buffers [default: 16].
  -t --num-transfers=<nt>  Number of transfers [default: 16].
  -l --num-samples=<ns>    Numper of samples per transfer buffer [default: 8192].
  -P --num-workers=<p>     Set number of FFT workers [default: 2]
  --dry-run                Validate the sweep and print its plan without opening hardware.
"""
import sys
import argparse
SC16_Q11_FULL_SCALE = 2048.0
try:
    from numpy import *
except ImportError:  # allow --help and --version without DSP dependencies
    pass


################################################################################
## OPTION PARSING
################################################################################

def get_args():
    parser = argparse.ArgumentParser(description='Receive-only bladeRF spectrum survey')
    parser.add_argument('range', metavar='LOWER:UPPER:BIN_WIDTH')
    parser.add_argument('-v', '--version', action='version', version='bladerf-power 0.4.0')
    parser.add_argument('-f', '--file', default='output.csv')
    parser.add_argument('-z', '--compress', action='store_true')
    parser.add_argument('-e', '--exit-timer', default='0')
    parser.add_argument('-b', '--bandwidth', default='28M')
    parser.add_argument('-M', '--filter-margin', default='.85')
    parser.add_argument('-W', '--window-type', default='hann')
    parser.add_argument('-g', '--lna-gain', default='LNA_GAIN_MAX')
    parser.add_argument('-o', '--rx-vga1', default='RXVGA1_GAIN_MIN')
    parser.add_argument('-w', '--rx-vga2', default='RXVGA2_GAIN_MIN')
    parser.add_argument('-d', '--device', default='')
    parser.add_argument('-n', '--num-buffers', default='16')
    parser.add_argument('-t', '--num-transfers', default='16')
    parser.add_argument('-l', '--num-samples', default='8192')
    parser.add_argument('-P', '--num-workers', default='2')
    parser.add_argument('--sample-rate', default=None,
                        help='ADC sample rate; defaults to capture bandwidth')
    parser.add_argument('--settle-time', type=float, default=0.01,
                        help='seconds to wait after each retune (default: 0.01)')
    parser.add_argument('--settle-frames', type=int, default=1,
                        help='complete frames to discard after settling (default: 1)')
    parser.add_argument('--average-frames', type=int, default=1,
                        help='valid frames to average per view (default: 1)')
    parser.add_argument('--metric', choices=('amplitude', 'power', 'psd'), default='amplitude')
    parser.add_argument('--full-scale', type=float, default=2048.0,
                        help='SC16_Q11 full-scale reference (default: 2048)')
    parser.add_argument('--no-dc-notch', action='store_true')
    parser.add_argument('--iq-gain', type=float, default=1.0)
    parser.add_argument('--iq-phase', type=float, default=0.0,
                        help='IQ phase correction in degrees')
    parser.add_argument('--calibration-db', type=float, default=0.0,
                        help='absolute calibration offset added to results')
    parser.add_argument('--dry-run', action='store_true')
    parsed = parser.parse_args()
    return {
        '<lower:upper:bin_width>': parsed.range,
        '--file': parsed.file, '--compress': parsed.compress,
        '--exit-timer': parsed.exit_timer, '--bandwidth': parsed.bandwidth,
        '--filter-margin': parsed.filter_margin, '--window-type': parsed.window_type,
        '--lna-gain': parsed.lna_gain, '--rx-vga1': parsed.rx_vga1,
        '--rx-vga2': parsed.rx_vga2, '--device': parsed.device,
        '--num-buffers': parsed.num_buffers, '--num-transfers': parsed.num_transfers,
        '--num-samples': parsed.num_samples, '--num-workers': parsed.num_workers,
        '--sample-rate': parsed.sample_rate or parsed.bandwidth,
        '--settle-time': parsed.settle_time,
        '--settle-frames': parsed.settle_frames,
        '--average-frames': parsed.average_frames,
        '--metric': parsed.metric, '--full-scale': parsed.full_scale,
        '--no-dc-notch': parsed.no_dc_notch, '--iq-gain': parsed.iq_gain,
        '--iq-phase': parsed.iq_phase, '--calibration-db': parsed.calibration_db,
        '--dry-run': parsed.dry_run,
    }

def isdigit(x):
    try:
        int(x)
        return True
    except:
        return False

def suffix(x):
    x = x.lower()
    if x == 'k':
        return 1000
    elif x == 'm':
        return 1000000
    elif x == 'g':
        return 1000000000
    elif x == 't':
        return 1000000000000
    elif x == 'p':
        return 1000000000000000
    elif x == 'e':
        return 1000000000000000000
    else:
        return 1

def suffixed(x):
    if x == 0:
        return '0'
    tricade = int(log10(abs(x)))//3
    tricade = max(0, min(tricade, 6))
    mapping = {0: '', 1:'K', 2:'M', 3:'G', 4:'T', 5:'P', 6:'E'}
    return "%.1f%s"%(x/(1000**tricade), mapping[tricade])

def floatish(x):
    sfx = 1
    if not isdigit(x[-1]):
        sfx = suffix(x[-1])
        x = x[:-1]
    return float(x)*sfx

def intish(x):
    return int(floatish(x))

def int_or_attr(x):
    import bladeRF
    try:
        return int(x)
    except:
        return getattr(bladeRF, x)

def timeish(x):
    # First off, if this is just an integer with no suffixes, then return it!
    try:
        return int(x)
    except:
        pass

    time_units = {'d':24*60*60, 'h':60*60, 'm':60, 's':1}
    if x[-1] in time_units:
        j = len(x) - 2
        while isdigit(x[j-1]) and j > 0:
            j -= 1
        val = time_units[x[-1]] * intish(x[j:-1])
        if j > 0:
            return val + timeish(x[:j])
        else:
            return val
    return 0

################################################################################
## DATA ANALYSIS
################################################################################
import datetime, sys
from multiprocessing import Process, Manager, Pool
import queue

def file_worker(q_file, outfile, compress):
    import gzip
    binary = False
    if outfile == '-':
        if compress:
            f = gzip.GzipFile(fileobj=sys.stdout.buffer, mode='wb', compresslevel=9)
            binary = True
        else:
            f = sys.stdout
    else:
        if compress:
            f = gzip.open(outfile, 'wt', encoding='utf-8', compresslevel=9)
        else:
            f = open(outfile, 'w', encoding='utf-8')

    try:
        while True:
            try:
                data = q_file.get(True, .1)
                if data == "I'm sorry dave, it's time to die":
                    break
                f.write(data.encode('utf-8') if binary else data)
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        pass

    if not (outfile == "-" and compress):
        f.close()
    print("Gracefully exited file_worker")

def start_worker_pool(num_workers, outfile, compress):
    manager = Manager()
    pool = Pool(processes=max(1, num_workers))
    q_file = manager.Queue()
    file_process = Process(target=file_worker, args=(q_file, outfile, compress))
    file_process.start()
    return manager, pool, file_process, q_file

def stop_worker_pool(manager, pool, file_process, q_file):
    print("Closing worker pool...")
    pool.close()

    print("Joining worker pool...")
    pool.join()

    print("Joining file process...")
    q_file.put("I'm sorry dave, it's time to die")
    file_process.join(timeout=10)
    if file_process.is_alive():
        file_process.terminate()
    manager.shutdown()

def db(x):
    from numpy import log10, abs
    return 20*log10(abs(x))


def fft_dbfs(data, window_func, full_scale=SC16_Q11_FULL_SCALE):
    """Return window-corrected amplitude dBFS for interleaved SC16 samples.

    SC16_Q11 has 11 fractional bits, so a full-scale complex sample is
    represented by approximately 2048. Dividing by the window coherent gain
    makes a bin-centred full-scale tone read close to 0 dBFS rather than
    changing level with FFT length or window choice.
    """
    from numpy.fft import fft
    samples = data[::2].astype(float) + 1j * data[1::2].astype(float)
    samples /= float(full_scale)
    window = window_func(len(samples))
    coherent_gain = float(window.sum())
    if coherent_gain <= 0:
        raise ValueError("FFT window has no coherent gain")
    spectrum = fft(samples * window) / coherent_gain
    magnitude = maximum(abs(spectrum), 1e-15)
    return 20 * log10(magnitude)

def analyze_view(data, window_func, lower_sideband, center_freq, analysis_bandwidth, bin_width, start_freq, end_freq, timestamp, metric='amplitude', full_scale=2048.0, dc_notch=True, iq_gain=1.0, iq_phase_deg=0.0, calibration_db=0.0):
    """
    Perform power spectral analysis on data of length fft_len, passing it off to
    be written to file afterward.

    Parameters
    ----------
    data : array (real/complex interleaved)
        Incoming SC16 interleaved data samples of length fft_len

    window_func : function
        FFT windowing function, such as scipy.signal.hann()

    lower_sideband : bool
        Whether the lower or upper sideband of this view should be analyzed

    center_freq : float (Hz)
        Center frequency of this view

    analysis_bandwidth : float (Hz)
        The effective bandwidth we analyze in each view

    bin_width : float (Hz)
        The width of each FFT bin, in Hertz

    start_freq : float (Hz)
        The lower edge of the region of interest in frequency

    end_freq : float (Hz)
        The upper edge of the region of interest in frequency

    timestamp : float (seconds)
        The timestamp for this buffer

    """
    from spectrum_math import analyze_sc16, analyze_sc16_frames
    import numpy as np
    array = np.asarray(data)
    sample_count = array.shape[-1] // 2
    sample_rate = bin_width * sample_count
    window = window_func(sample_count)
    analyzer = analyze_sc16_frames if array.ndim == 2 else analyze_sc16
    result = analyzer(array, sample_rate, center_freq, window, metric,
                      full_scale, dc_notch, iq_gain, iq_phase_deg,
                      calibration_db)

    # Find start/end frequencies that we get from this FFT, and which bins we
    # want to slice out of the DATA array
    if lower_sideband:
        view_start = max(center_freq - analysis_bandwidth, start_freq)
        view_end = min(center_freq - bin_width, end_freq)

        selected = (result.frequencies_hz >= view_start) & (result.frequencies_hz <= view_end)
    else:
        view_start = max(center_freq + bin_width, start_freq)
        view_end = min(center_freq + analysis_bandwidth, end_freq)

        selected = (result.frequencies_hz >= view_start) & (result.frequencies_hz <= view_end)

    values = result.values_db[selected]

    # Prepare data for CSV-ification
    datestr = datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d, %H:%M:%S')
    csv_str = "%s, %d, %d, %.2f, %d, "%(datestr, view_start, view_end, bin_width, sample_count)

    csv_str += ", ".join(["%.2f" % x for x in values]) + "\n"

    return csv_str


def retune_and_settle(device, frequency, settle_time):
    """Set RX frequency, verify readback when available, then settle."""
    import time
    started = time.monotonic()
    device.rx.frequency = frequency
    deadline = started + min(settle_time, 0.25)
    while time.monotonic() < deadline:
        try:
            if abs(float(device.rx.frequency) - frequency) <= 1.0:
                break
        except (AttributeError, TypeError, ValueError):
            break
        time.sleep(0.001)
    remaining = settle_time - (time.monotonic() - started)
    if remaining > 0:
        time.sleep(remaining)


################################################################################
## RX CALLBACK
################################################################################

# The receiver callback, which fills up queued_data, and sends it on its merry way
def rx_callback(device, stream, meta_data, samples, num_samples, user_data):
    data = user_data['data']
    data_idx = user_data['data_idx']
    fft_len = user_data['fft_len']
    q_data = user_data['q_data']
    in_data = fromstring(stream.current_as_buffer(), dtype=int16)

    # Are we supposed to quit?
    if user_data['running'] == False:
        return None

    # Do not let samples collected while the LO is settling form a frame.
    import time
    if time.monotonic() < user_data.get('discard_until', 0):
        user_data['data_idx'] = 0
        return stream.next()

    # Are we full already?  Then let's just keep on keeping on
    if data_idx == fft_len:
        return stream.current()

    if num_samples*2 + data_idx < fft_len*2:
        # Are we only partially filled?  Then fill in and return
        data[data_idx:num_samples*2 + data_idx] = in_data
        user_data['data_idx'] += num_samples*2
        return stream.next()
    else:
        # Have we filled completely?  Then take what we need from this buffer, and discard the rest
        data[data_idx:] = in_data[0:(fft_len*2 - data_idx)]
        user_data['data_idx'] = fft_len
        if user_data.get('discard_frames', 0):
            user_data['discard_frames'] -= 1
            user_data['data_idx'] = 0
        else:
            q_data.put(user_data['epoch'])
        return stream.next()


def freq_planning(start_freq, end_freq, bin_width, fmbw2, min_tune_freq=0):
    """
    Given frequency parameters, returns a list of (center_frequency,
    lower_sideband) tuples, denoting the center frequency of each tuning view,
    and whether we should pay attention to the lower sideband or upper sideband
    when tuning to a particular frequency.

    Parameters
    ----------
    start_freq : float (Hz)
        Beginning of desired frequency range

    end_freq : float (Hz)
        End of desired frequency range, must be greater than start_freq

    bin_width : float (Hz)
        Width of analysis FFT bins

    analysis_bandwidth : float (Hz)
        Width of analysis window in Hz, equal to filter_margin * bandwidth/2

    Returns
    -------
    freqs : list of (center_frequency, lower_sideband) tuples
        A list of views describing a center frequency to tune to and which
        sideband to observe, upper or lower (true signifies lower sideband).
    """
    from math import ceil
    if not (end_freq > start_freq > min_tune_freq and bin_width > 0 and fmbw2 > 0):
        raise ValueError("invalid frequency plan parameters")
    # First frequency is always the same; either just below start_freq or at
    # start_freq + bandwidth/2 - binwidth, in the case that start_freq is really
    # close to the minimum frequency we can tune to:
    if start_freq - bin_width >= min_tune_freq:
        # Put center_freq just below start_freq if we are not at the minimum frequency
        freqs = [(start_freq - bin_width, False)]
    else:
        # Otherwise, put center_freq just above start_freq + bandwidth/2
        freqs = [(start_freq + fmbw2, True)]

    # Can we get this done with just a single view?
    if end_freq - start_freq < fmbw2:
        return freqs

    # Otherwise, let's figure out how many views we need after the first one
    num_views = int(ceil((end_freq - start_freq)/fmbw2 - 1))
    freqs += [(start_freq + fmbw2 - bin_width + idx*fmbw2, False) for idx in range(num_views)]

    # Return these frequencies!
    return freqs



################################################################################
## MAIN LOOP
################################################################################

def main():
    from time import time, sleep, monotonic
    import threading
    from queue import Queue
    args = get_args()
    freq_arg = args['<lower:upper:bin_width>']
    try:
        start_freq, end_freq, bin_width = [floatish(x) for x in freq_arg.split(':')]
        if end_freq <= start_freq or bin_width <= 0:
            raise ValueError
    except (ValueError, IndexError):
        sys.stderr.write("ERROR: expected lower:upper:positive_bin_width\n")
        return 2
    if args['--average-frames'] < 1:
        sys.stderr.write("ERROR: average frames must be positive\n")
        return 2
    if args['--dry-run']:
        print("validated sweep: %.0fHz..%.0fHz, %.3fHz bins, metric=%s, settle=%gs/%d frames, average=%d" % (start_freq, end_freq, bin_width, args['--metric'], args['--settle-time'], args['--settle-frames'], args['--average-frames']))
        return 0
    if not 0 < float(args['--filter-margin']) <= 1:
        sys.stderr.write("ERROR: filter margin must be greater than 0 and at most 1\n")
        return 2
    if args['--settle-time'] < 0:
        sys.stderr.write("ERROR: settle time cannot be negative\n")
        return 2
    if args['--settle-frames'] < 0:
        sys.stderr.write("ERROR: settle frames cannot be negative\n")
        return 2
    if args['--full-scale'] <= 0 or args['--iq-gain'] <= 0:
        sys.stderr.write("ERROR: full-scale and IQ gain must be positive\n")
        return 2
    import scipy.signal
    import bladeRF
    try:
        device = bladeRF.Device(args['--device'])
    except:
        if args['--device'] == '':
            print("ERROR: No bladeRF devices available!")
        else:
            print("ERROR: Could not open bladeRF device %s" % args['--device'])
        return
    device.rx.enabled = True
    bandwidth = intish(args['--bandwidth'])
    device.rx.bandwidth = bandwidth
    device.rx.sample_rate = intish(args['--sample-rate'])

    filter_margin = float(args['--filter-margin'])
    start_freq = max(start_freq, bladeRF.FREQUENCY_MIN)
    end_freq = min(end_freq, bladeRF.FREQUENCY_MAX)

    if end_freq <= start_freq:
        sys.stderr.write("ERROR: end frequency must be greater than start frequency!\n")
        return

    # fft_len is the minimum length FFT that guarantees us bins of less than or
    # equal width as requested through bin_width:
    from scipy.fft import next_fast_len
    fft_len = next_fast_len(int(ceil(bandwidth/bin_width)))

    # Now that we know our actual fft length, find the true bin width:
    bin_width = bandwidth/fft_len

    # fmbw2 is the amount of spectrum we get with each view, we quantize to our
    # effective bin_width given our bandwidth and number of bins
    fmbw2 = round(filter_margin*(bandwidth/2)*fft_len)/fft_len

    freqs = freq_planning(start_freq, end_freq, bin_width, fmbw2, bladeRF.FREQUENCY_MIN)
    num_views = len(freqs)

    device.lna_gain = int_or_attr(args['--lna-gain'])
    device.rx.vga1 = int_or_attr(args['--rx-vga1'])
    device.rx.vga2 = int_or_attr(args['--rx-vga2'])

    num_buffers = int(args['--num-buffers'])
    num_samples = int(args['--num-samples'])
    num_transfers = int(args['--num-transfers'])

    # Start FFT worker pool
    num_workers = int(args['--num-workers'])
    if num_workers < 1:
        sys.stderr.write("ERROR: number of workers must be positive\n")
        return 2
    if int(args['--num-buffers']) < 1 or int(args['--num-transfers']) < 1 or int(args['--num-samples']) < 1:
        sys.stderr.write("ERROR: buffer, transfer, and sample counts must be positive\n")
        return 2
    try:
        scipy.signal.get_window(args['--window-type'], 8)
    except ValueError as exc:
        sys.stderr.write("ERROR: unknown FFT window %r\n" % args['--window-type'])
        return 2
    window_func = lambda n: scipy.signal.get_window(args['--window-type'], n, fftbins=True)
    outfile = args['--file']
    compress = bool(args['--compress'])
    manager, pool, file_process, q_file = start_worker_pool(num_workers, outfile, compress)

    # Timing stuffage
    start_time = time()
    curr_time = start_time
    exit_timer = timeish(args['--exit-timer'])

    # This is the thread that runs the stream.  So exciting, la
    def run_stream(stream):
        stream.run()

    try:
        q_data = Queue()
        rx_data = {
            'data': empty(fft_len*2, dtype=int16),
            'data_idx': 0,
            'fft_len': fft_len,
            'q_data': q_data,
            'running': True,
            'epoch': 0,
            'discard_frames': args['--settle-frames'],
        }

        # Initialize device.rx.frequency, then start the stream doing its thing
        rx_data['discard_until'] = monotonic() + args['--settle-time']
        retune_and_settle(device, freqs[0][0], args['--settle-time'])
        stream = device.rx.stream(rx_callback, num_buffers, bladeRF.FORMAT_SC16_Q11, num_samples, num_transfers, user_data=rx_data)
        stream_thread = threading.Thread(target=run_stream, args=(stream,), daemon=True)
        stream_thread.start()

        sys.stderr.write("Scanning from %sHz to %sHz, using %d views of %sHz with %d bins %sHz wide\n"%(suffixed(start_freq), suffixed(end_freq), num_views, suffixed(fmbw2), fft_len/2, suffixed(bin_width)))

        # Now zoom through frequencies like it's your day off
        freq_idx = 0
        pending = []
        while exit_timer == 0 or curr_time - start_time <= exit_timer:
            frame_batch = []
            while len(frame_batch) < args['--average-frames']:
                while True:
                    frame_epoch = q_data.get()
                    if frame_epoch == rx_data['epoch']:
                        break
                # The callback owns and reuses this buffer after the event.
                frame_batch.append(rx_data['data'].copy())
                rx_data['data_idx'] = 0

            # Now that we have the data, apply it to the pool
            # The callback reuses its buffer; copy before handing it to a worker.
            analysis_data = frame_batch[0] if len(frame_batch) == 1 else array(frame_batch)
            analysis_args = (analysis_data, window_func, freqs[freq_idx][1], device.rx.frequency, fmbw2, bin_width, start_freq, end_freq, curr_time, args['--metric'], args['--full-scale'], not args['--no-dc-notch'], args['--iq-gain'], args['--iq-phase'], args['--calibration-db'])
            pending.append(pool.apply_async(analyze_view, analysis_args))
            if len(pending) >= num_workers:
                q_file.put(pending.pop(0).get())

            # If not, move on to the next frequency
            freq_idx = (freq_idx + 1)%len(freqs)
            rx_data['epoch'] += 1
            rx_data['data_idx'] = 0
            rx_data['discard_until'] = monotonic() + args['--settle-time']
            rx_data['discard_frames'] = args['--settle-frames']
            retune_and_settle(device, freqs[freq_idx][0], args['--settle-time'])
            if freq_idx == 0:
                curr_time = time()

            total_space = 40
            num_space = int((total_space - 1)*freq_idx/len(freqs))
            tct = time()
            status_line = "[" + " "*num_space + "." + " "*(total_space - num_space - 1) + "]"

            if exit_timer > 0:
                pct_done = "%.1f%%"%(min(100*(tct - start_time)/exit_timer, 100))
            else:
                pct_done = u"\u221e"

            status_line += " %.1fs/%s\r"%(tct - start_time, pct_done)
            sys.stderr.write(status_line)
            sys.stderr.flush()
    except KeyboardInterrupt:
        pass
    finally:
        print() # Clear out the status_line stuffage
        rx_data['running'] = False
        if 'stream' in locals() and hasattr(stream, 'stop'):
            stream.stop()
        if 'stream_thread' in locals():
            stream_thread.join(timeout=2)
        for result in pending if 'pending' in locals() else []:
            q_file.put(result.get())
        stop_worker_pool(manager, pool, file_process, q_file)
        print("Done stopping the worker pool!")

    print("done!")

if __name__ == '__main__':
    raise SystemExit(main())
