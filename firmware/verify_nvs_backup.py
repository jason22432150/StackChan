"""Verify two copies of a CoreS3 NVS partition backup offline."""

from __future__ import annotations

import argparse
import csv
import hashlib
import struct
from pathlib import Path
from typing import Sequence

DEFAULT_PARTITION_TABLE = Path(__file__).with_name("partitions.csv")
_TABLE_BYTES = 0xC00
_SECTOR_BYTES = 0x1000
_ENTRY = struct.Struct("<2sBBII16sI")
_MD5_MARKER = b"\xeb\xeb" + b"\xff" * 14


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
    return _validate_nvs_extent(offset, size)


def _validate_nvs_extent(offset: int, size: int) -> tuple[int, int]:
    if offset <= 0 or size <= 0 or offset % _SECTOR_BYTES or size % _SECTOR_BYTES:
        raise ValueError("NVS offset and size must be positive and sector-aligned")
    if offset + size > 1 << 32:
        raise ValueError("NVS extent exceeds the partition address range")
    return offset, size


def binary_nvs_partition_extent(table: Path) -> tuple[int, int]:
    """Read a checksummed ESP-IDF table or its enclosing flash sector."""
    with table.open("rb") as source:
        data = source.read(_SECTOR_BYTES + 1)
    if len(data) not in (_TABLE_BYTES, _SECTOR_BYTES):
        raise ValueError("expected a 0xc00-byte partition table or a 0x1000-byte sector")
    data = data[:_TABLE_BYTES]
    entries = []
    for position in range(0, len(data), _ENTRY.size):
        record = data[position:position + _ENTRY.size]
        if record.startswith(_MD5_MARKER):
            expected = hashlib.md5(data[:position], usedforsecurity=False).digest()
            if record[len(_MD5_MARKER):] != expected:
                raise ValueError("partition table MD5 does not match")
            padding = data[position + _ENTRY.size:]
            if not padding or padding != b"\xff" * len(padding):
                raise ValueError("unexpected data after partition table checksum")
            break
        if record == b"\xff" * _ENTRY.size:
            raise ValueError("partition table has no MD5 checksum")
        magic, kind, subtype, offset, size, name, _ = _ENTRY.unpack(record)
        if magic != b"\xaa\x50":
            raise ValueError("invalid partition table entry")
        entries.append((kind, subtype, offset, size, name.split(b"\0", 1)[0]))
    else:
        raise ValueError("partition table has no MD5 checksum")

    matches = [entry for entry in entries if entry[4] == b"nvs"]
    if len(matches) != 1 or matches[0][:2] != (1, 2):
        raise ValueError("partition table must declare one nvs data partition")
    nvs = matches[0]
    offset, size = _validate_nvs_extent(nvs[2], nvs[3])
    for entry in entries:
        if entry is not nvs and entry[2] < offset + size and offset < entry[2] + entry[3]:
            raise ValueError("another partition overlaps the NVS extent")
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


def verify_nvs_backups(
    table: Path, first: Path, second: Path, *, binary_table: bool = False,
) -> tuple[int, int, str]:
    """Check the partition extent and compare SHA-256 without exposing NVS contents."""
    offset, size = binary_nvs_partition_extent(table) if binary_table else nvs_partition_extent(table)
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
    parser.add_argument("first", nargs="?", type=Path, help="first raw NVS partition capture")
    parser.add_argument("second", nargs="?", type=Path, help="second raw NVS partition capture")
    tables = parser.add_mutually_exclusive_group()
    tables.add_argument("--partition-table", type=Path, default=DEFAULT_PARTITION_TABLE,
                        help="CSV matching the device partition table, with explicit byte offset and size")
    tables.add_argument("--binary-partition-table", type=Path,
                        help="checksummed ESP-IDF partition table or full sector capture")
    parser.add_argument("--show-partition", action="store_true",
                        help="report the NVS extent without reading any NVS backup")
    args = parser.parse_args(argv)
    binary = args.binary_partition_table is not None
    table = args.binary_partition_table or args.partition_table
    try:
        if args.show_partition:
            if args.first is not None or args.second is not None:
                parser.error("--show-partition doesn't take backup files")
            offset, size = binary_nvs_partition_extent(table) if binary else nvs_partition_extent(table)
            print(f"NVS partition: offset={offset:#x} size={size:#x}")
            return 0
        if args.first is None or args.second is None:
            parser.error("provide two backup files or use --show-partition")
        offset, size, digest = verify_nvs_backups(table, args.first, args.second, binary_table=binary)
    except (ValueError, csv.Error) as exc:
        parser.error(str(exc))
    except OSError:
        parser.error("could not read the partition table or backup files")
    print(f"NVS copies match: offset={offset:#x} size={size:#x} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
