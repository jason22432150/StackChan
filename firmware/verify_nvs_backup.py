"""Verify two copies of a CoreS3 NVS partition backup offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
from typing import Sequence

DEFAULT_PARTITION_TABLE = Path(__file__).with_name("partitions.csv")


def nvs_partition_extent(table: Path) -> tuple[int, int]:
    with table.open(encoding="utf-8", newline="") as source:
        rows = csv.reader(line for line in source if line.strip() and not line.lstrip().startswith("#"))
        matches = []
        for row in rows:
            fields = [field.strip() for field in row]
            if fields and fields[0] == "nvs":
                matches.append(fields)
    if len(matches) != 1 or matches[0][1:3] != ["data", "nvs"] or len(matches[0]) < 5:
        raise ValueError("partition table must declare one nvs data partition")
    try:
        offset, size = (int(field, 0) for field in matches[0][3:5])
    except ValueError:
        raise ValueError("NVS partition needs an explicit byte offset and size") from None
    if offset <= 0 or size <= 0 or offset % 4096 or size % 4096:
        raise ValueError("NVS offset and size must be positive and sector-aligned")
    return offset, size


def _backup_digest(path: Path, expected_size: int) -> str:
    digest = hashlib.sha256()
    nonzero = False
    unerased = False
    remaining = expected_size
    with path.open("rb") as backup:
        while remaining:
            data = backup.read(min(remaining, 65536))
            if not data:
                raise ValueError("backup size does not match the NVS partition")
            digest.update(data)
            nonzero |= data.count(0) != len(data)
            unerased |= data.count(255) != len(data)
            remaining -= len(data)
        if backup.read(1):
            raise ValueError("backup size does not match the NVS partition")
    if not (nonzero and unerased):
        raise ValueError("backup contains only erased or zero bytes")
    return digest.hexdigest()


def verify_nvs_backups(table: Path, first: Path, second: Path) -> tuple[int, int, str]:
    """Check the partition extent and compare SHA-256 without exposing NVS contents."""
    offset, size = nvs_partition_extent(table)
    if not first.is_file() or not second.is_file():
        raise ValueError("provide two regular backup files")
    if first.samefile(second):
        raise ValueError("provide two distinct backup files")
    digest = _backup_digest(first, size)
    if digest != _backup_digest(second, size):
        raise ValueError("backup copies do not match")
    return offset, size, digest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("first", type=Path, help="first raw NVS partition capture")
    parser.add_argument("second", type=Path, help="second raw NVS partition capture")
    parser.add_argument("--partition-table", type=Path, default=DEFAULT_PARTITION_TABLE,
                        help="CSV matching the device partition table, with explicit byte offset and size")
    args = parser.parse_args(argv)
    try:
        offset, size, digest = verify_nvs_backups(args.partition_table, args.first, args.second)
    except (ValueError, csv.Error) as exc:
        parser.error(str(exc))
    except OSError:
        parser.error("could not read the partition table or backup files")
    print(f"NVS copies match: offset={offset:#x} size={size:#x} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
