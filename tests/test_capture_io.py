import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from capture_io import CaptureWriter


class CaptureIoTests(unittest.TestCase):
    def test_sigmf_writer_is_little_endian_and_writes_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            prefix = str(Path(directory) / 'capture')
            with CaptureWriter(prefix, 2_400_000, 433_000_000, prefix) as writer:
                writer.write_frames(np.array([[1, -2, 3, -4]], dtype=np.int16),
                                    433_000_000)
            data = Path(prefix + '.sigmf-data').read_bytes()
            self.assertEqual(data, b'\x01\x00\xfe\xff\x03\x00\xfc\xff')
            metadata = json.loads(Path(prefix + '.sigmf-meta').read_text())
            self.assertEqual(metadata['global']['core:datatype'], 'ci16_le')
            self.assertEqual(metadata['captures'][0]['sample_start'], 0)


if __name__ == '__main__':
    unittest.main()
