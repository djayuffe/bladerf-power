"""Small compatibility adapter for the current Nuand Python binding.

The original project used the callback API shipped by the historical
``bladeRF`` module. Current Nuand bindings expose ``bladerf.BladeRF`` and
``sync_rx`` instead. This adapter presents the subset of the old stream
contract used by :mod:`bladerf_power`, while keeping DSP and sweep planning
identical.
"""

from __future__ import annotations

import threading


def _binding_attr(module, name):
    """Return a binding enum namespace from either public or native module API."""
    value = getattr(module, name, None)
    if value is not None:
        return value
    native = getattr(module, "_bladerf", None)
    value = getattr(native, name, None) if native is not None else None
    if value is None:
        raise AttributeError("bladeRF binding does not expose %s" % name)
    return value


def _device_identifier(module, identifier):
    """Map a serial string to a devstr when the modern binding exposes devices."""
    if not identifier or not hasattr(module, "get_device_list"):
        return identifier
    for device in module.get_device_list():
        if getattr(device, "serial_str", "") == identifier:
            return getattr(device, "devstr", identifier)
    return identifier


class _ModernStream:
    def __init__(self, sdr, channel, module, callback, user_data, num_samples,
                 num_buffers, num_transfers):
        self._sdr = sdr
        self._channel = channel
        self._module = module
        self._callback = callback
        self._user_data = user_data
        self._num_samples = int(num_samples)
        self._buffer = bytearray(self._num_samples * 4)
        self._stopped = threading.Event()
        self.error = None
        sdr.sync_config(
            layout=_binding_attr(module, 'ChannelLayout').RX_X1,
            fmt=_binding_attr(module, 'Format').SC16_Q11,
            num_buffers=int(num_buffers),
            buffer_size=self._num_samples,
            num_transfers=int(num_transfers),
            stream_timeout=3500,
        )

    def current_as_buffer(self):
        return self._buffer

    def current(self):
        return self

    def next(self):
        return self

    def run(self):
        try:
            while not self._stopped.is_set() and self._user_data.get('running', True):
                self._sdr.sync_rx(self._buffer, self._num_samples)
                self._callback(None, self, None, None, self._num_samples,
                               self._user_data)
        except Exception as exc:  # surfaced to the main loop during shutdown
            self.error = exc
            self._user_data['stream_error'] = exc
            self._user_data['running'] = False

    def stop(self):
        self._stopped.set()


class _ModernRx:
    def __init__(self, parent, channel):
        self._parent = parent
        self._channel = channel

    frequency = property(lambda self: self._channel.frequency,
                         lambda self, value: setattr(self._channel, 'frequency', int(value)))
    bandwidth = property(lambda self: self._channel.bandwidth,
                         lambda self, value: setattr(self._channel, 'bandwidth', int(value)))
    sample_rate = property(lambda self: self._channel.sample_rate,
                            lambda self, value: setattr(self._channel, 'sample_rate', int(value)))
    enabled = property(lambda self: self._channel.enable,
                       lambda self, value: setattr(self._channel, 'enable', bool(value)))

    def stream(self, callback, num_buffers, fmt, num_samples, num_transfers,
               user_data=None):
        return _ModernStream(self._parent._sdr, self._channel,
                             self._parent._module, callback, user_data,
                             num_samples, num_buffers, num_transfers)

    def set_manual_gain(self, gain):
        if hasattr(self._channel, 'gain_mode') and hasattr(self._parent._module, 'GainMode'):
            self._channel.gain_mode = self._parent._module.GainMode.Manual
        self._channel.gain = int(gain)


class ModernDeviceAdapter:
    def __init__(self, module, identifier=''):
        self._module = module
        try:
            self._sdr = module.BladeRF(_device_identifier(module, identifier)) if identifier else module.BladeRF()
        except TypeError:
            self._sdr = module.BladeRF()
        self.rx = _ModernRx(self, self._sdr.Channel(module.CHANNEL_RX(0)))

    def close(self):
        close = getattr(self._sdr, 'close', None)
        if close:
            close()

    @property
    def lna_gain(self):
        return getattr(self.rx._channel, 'gain', 0)

    @lna_gain.setter
    def lna_gain(self, value):
        # Stage-specific gains do not exist on all current models. Treat the
        # legacy LNA setting as a total manual RX gain when numeric.
        if isinstance(value, int):
            self.rx.set_manual_gain(value)
