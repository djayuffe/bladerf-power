"""Validation and installation helpers for Nuand bladeRF DC RX tables."""

from __future__ import annotations

import hashlib
import os
import platform
import re
import shutil
from pathlib import Path


TABLE_MAGIC = b"bladeRF0"
TABLE_NAME = re.compile(r"^[A-Za-z0-9._-]+_dc_(?:rx|tx)\.tbl$")


def calibration_dirs() -> list[Path]:
    """Return libbladeRF's documented per-user/system search directories."""
    home = Path.home()
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA")
        return [Path(appdata) / "Nuand" / "bladeRF"] if appdata else []
    return [home / ".config" / "Nuand" / "bladeRF",
            home / ".Nuand" / "bladeRF",
            home / "etc" / "Nuand" / "bladeRF",
            home / "usr" / "share" / "Nuand" / "bladeRF",
            Path("/etc/Nuand/bladeRF")]


def inspect_calibration(path: str | os.PathLike) -> dict:
    """Validate a binary table and return safe provenance metadata."""
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if not TABLE_NAME.match(source.name):
        raise ValueError("calibration filename must end in <serial>_dc_rx.tbl or _dc_tx.tbl")
    data = source.read_bytes()
    if len(data) < 64 or not data.startswith(TABLE_MAGIC):
        raise ValueError("not a Nuand bladeRF calibration table")
    return {"path": str(source), "filename": source.name, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "direction": "rx" if "_dc_rx.tbl" in source.name else "tx"}


def install_calibration(path: str | os.PathLike, destination: str | os.PathLike | None = None,
                        overwrite: bool = False) -> dict:
    """Install a validated table in a libbladeRF search directory."""
    info = inspect_calibration(path)
    target_dir = Path(destination).expanduser() if destination else calibration_dirs()[0]
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / info["filename"]
    if target.exists() and not overwrite:
        raise FileExistsError("calibration table exists; pass overwrite=True to replace it")
    shutil.copy2(info["path"], target)
    info["installed_path"] = str(target)
    return info

