import tempfile
import unittest
from pathlib import Path

from calibration import inspect_calibration, install_calibration


class CalibrationTests(unittest.TestCase):
    def test_inspects_bundled_table(self):
        info = inspect_calibration(Path(__file__).parents[1] /
                                   '43697856d8bd507e045e327026d15403_dc_rx.tbl')
        self.assertEqual(info['direction'], 'rx')
        self.assertGreater(info['bytes'], 64)
        self.assertEqual(len(info['sha256']), 64)

    def test_installs_and_refuses_overwrite(self):
        source = Path(__file__).parents[1] / '43697856d8bd507e045e327026d15403_dc_rx.tbl'
        with tempfile.TemporaryDirectory() as directory:
            info = install_calibration(source, directory)
            self.assertTrue(Path(info['installed_path']).is_file())
            with self.assertRaises(FileExistsError):
                install_calibration(source, directory)

    def test_rejects_bad_magic_and_name(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad_dc_rx.tbl'
            path.write_bytes(b'not-a-table' + b'\0' * 100)
            with self.assertRaises(ValueError):
                inspect_calibration(path)


if __name__ == '__main__':
    unittest.main()
