"""Capture and verify a CoreS3 NVS backup from its ROM bootloader."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from firmware.verify_nvs_backup import binary_nvs_partition_extent, verify_nvs_backups

_SECTOR_SIZE = 0x1000


def _read_flash(port: str, offset: int, size: int, destination: Path) -> None:
    try:
        subprocess.run(
            [
                sys.executable, "-m", "esptool", "--chip", "esp32s3", "--port", port,
                "--before", "no-reset", "--after", "no-reset", "--no-stub",
                "read-flash", "--no-progress", hex(offset), hex(size), str(destination),
            ],
            check=True, timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"esptool read-flash failed at offset {offset:#x}") from exc
    destination.chmod(0o600)


def capture_nvs_backup(port: str, table_offset: int, output_parent: Path) -> tuple[Path, int, int, str]:
    if not port:
        raise ValueError("provide the CoreS3 serial port explicitly")
    if not 0 < table_offset <= (1 << 32) - _SECTOR_SIZE or table_offset % _SECTOR_SIZE:
        raise ValueError("partition table offset must be positive and sector-aligned")

    directory = Path(tempfile.mkdtemp(prefix="cores3-nvs-", dir=output_parent))
    complete = False
    try:
        table = directory / "partition-table.bin"
        _read_flash(port, table_offset, _SECTOR_SIZE, table)
        offset, size = binary_nvs_partition_extent(table)
        if offset < table_offset + _SECTOR_SIZE and table_offset < offset + size:
            raise ValueError("NVS overlaps the partition table sector")
        first, second = directory / "capture-1.bin", directory / "capture-2.bin"
        _read_flash(port, offset, size, first)
        _read_flash(port, offset, size, second)
        _, _, digest = verify_nvs_backups(table, first, second, binary_table=True)
        complete = True
        return directory, offset, size, digest
    finally:
        if not complete:
            shutil.rmtree(directory)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="serial port of the CoreS3 already in ROM download mode")
    parser.add_argument("--table-offset", required=True, type=lambda value: int(value, 0),
                        help="confirmed byte offset of that device's partition table")
    parser.add_argument("--output-parent", required=True, type=Path,
                        help="existing private directory for the verified backup")
    args = parser.parse_args(argv)
    try:
        directory, offset, size, digest = capture_nvs_backup(args.port, args.table_offset, args.output_parent)
    except (ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    except OSError:
        parser.error("could not create or read the local backup files")
    print(f"NVS backup verified: offset={offset:#x} size={size:#x} sha256={digest}")
    print(f"Saved under: {directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
