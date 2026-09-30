"""Streaming raw and SigMF writers for captured SC16_Q11 frames."""

from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np


class CaptureWriter:
    """Write little-endian interleaved SC16_Q11 and optional SigMF metadata."""

    def __init__(self, path: str, sample_rate: float, center_frequency: float,
                 sigmf_prefix: str | None = None):
        self.path = Path(path)
        self.sample_rate = float(sample_rate)
        self.center_frequency = float(center_frequency)
        self.sigmf_prefix = Path(sigmf_prefix) if sigmf_prefix else None
        self.data_path = (self.sigmf_prefix.with_suffix('.sigmf-data')
                          if self.sigmf_prefix else self.path)
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.data_path.open('wb')
        self.sample_count = 0
        self.captures = []
        self._last_frequency = None

    def _capture_record(self, frequency: float):
        frequency = float(frequency)
        if self._last_frequency != frequency:
            self.captures.append({"sample_start": self.sample_count,
                                  "frequency": frequency})
            self._last_frequency = frequency

    def write_frames(self, frames, frequency: float):
        values = np.asarray(frames, dtype=np.int16)
        if values.ndim == 1:
            values = values.reshape(1, -1)
        if values.ndim != 2 or values.shape[1] % 2:
            raise ValueError("raw capture frames must be interleaved even-length int16 arrays")
        self._capture_record(frequency)
        # Explicit little-endian output makes files portable across hosts.
        little = np.asarray(values, dtype='<i2')
        self._file.write(little.tobytes(order='C'))
        self.sample_count += int(values.shape[0] * values.shape[1] // 2)

    def close(self):
        if self._file.closed:
            return
        self._file.flush()
        self._file.close()
        if self.sigmf_prefix:
            metadata = {
                "global": {
                    "core:datatype": "ci16_le",
                    "core:sample_rate": self.sample_rate,
                    "core:version": "1.0.0",
                    "core:description": "bladeRF SC16_Q11 receive capture",
                    "core:recorder": "bladerf-power",
                    "core:hw": "Nuand bladeRF",
                    "core:datetime": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                },
                "captures": self.captures,
            }
            meta_path = self.sigmf_prefix.with_suffix('.sigmf-meta')
            meta_path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

