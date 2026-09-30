import types
import unittest

from bladerf_backend import ModernDeviceAdapter


class _Channel:
    def __init__(self):
        self.frequency = 100_000_000
        self.bandwidth = 2_000_000
        self.sample_rate = 2_400_000
        self.enable = False
        self.gain = 0


class _Sdr:
    def __init__(self, identifier=None):
        self.channel = _Channel()
        self.config = None

    def Channel(self, _channel_id):
        return self.channel

    def sync_config(self, **kwargs):
        self.config = kwargs

    def sync_rx(self, buffer, count):
        buffer[:] = b"\0" * (count * 4)


class BackendTests(unittest.TestCase):
    def test_modern_adapter_exposes_legacy_stream_contract(self):
        module = types.SimpleNamespace(
            BladeRF=_Sdr,
            CHANNEL_RX=lambda index: index,
            ChannelLayout=types.SimpleNamespace(RX_X1="rx_x1"),
            Format=types.SimpleNamespace(SC16_Q11="sc16"),
            GainMode=types.SimpleNamespace(Manual="manual"),
        )
        device = ModernDeviceAdapter(module)
        self.assertEqual(device.rx.sample_rate, 2_400_000)
        device.rx.sample_rate = 1_000_000
        self.assertEqual(device.rx.sample_rate, 1_000_000)
        seen = []
        user_data = {'running': True, 'data': None}

        def callback(_device, stream, _meta, _samples, count, _user):
            seen.append((len(stream.current_as_buffer()), count))
            stream.stop()

        stream = device.rx.stream(callback, 4, module.Format.SC16_Q11, 8, 2,
                                  user_data=user_data)
        stream.run()
        self.assertEqual(seen, [(32, 8)])


if __name__ == '__main__':
    unittest.main()
