from __future__ import annotations

import hashlib
import struct

import pytest

from firmware.verify_nvs_backup import (
    DEFAULT_PARTITION_TABLE,
    binary_nvs_partition_extent,
    main,
    verify_nvs_backups,
)


@pytest.fixture
def backups(tmp_path):
    contents = b"fixture-only" + b"\xff" * (0x4000 - len(b"fixture-only"))
    first, second = tmp_path / "capture-1.bin", tmp_path / "capture-2.bin"
    first.write_bytes(contents)
    second.write_bytes(contents)
    return first, second, contents


def test_cli_reports_extent_and_hash_without_printing_or_editing_backup(backups, capsys):
    first, second, contents = backups
    assert main([str(first), str(second)]) == 0
    stdout = capsys.readouterr().out
    assert "offset=0x9000 size=0x4000" in stdout
    assert hashlib.sha256(contents).hexdigest() in stdout
    assert "fixture-only" not in stdout
    assert first.read_bytes() == second.read_bytes() == contents


@pytest.mark.parametrize("delta", [-1, 1])
def test_rejects_truncated_and_oversized_reads(backups, delta):
    first, second, contents = backups
    second.write_bytes((contents + b"\xff")[:len(contents) + delta])
    with pytest.raises(ValueError, match="size"):
        verify_nvs_backups(DEFAULT_PARTITION_TABLE, first, second)


@pytest.mark.parametrize("value", [0, 255])
def test_rejects_blank_reads(backups, value):
    first, second, contents = backups
    first.write_bytes(bytes([value]) * len(contents))
    with pytest.raises(ValueError, match="only erased or zero"):
        verify_nvs_backups(DEFAULT_PARTITION_TABLE, first, second)


def test_rejects_one_byte_change_at_the_end(backups):
    first, second, contents = backups
    second.write_bytes(contents[:-1] + b"\x00")
    with pytest.raises(ValueError, match="copies do not match"):
        verify_nvs_backups(DEFAULT_PARTITION_TABLE, first, second)


def test_rejects_file_alias(backups, tmp_path):
    first, _, _ = backups
    alias = tmp_path / "alias.bin"
    alias.hardlink_to(first)
    with pytest.raises(ValueError, match="distinct"):
        verify_nvs_backups(DEFAULT_PARTITION_TABLE, first, alias)


@pytest.mark.parametrize("row", [
    "otadata,data,ota,0x9000,0x4000",
    "nvs,data,nvs,,0x4000",
    "nvs,data,nvs,0x9001,0x4000",
    "nvs,data,nvs,0x9000,0x4000\nnvs,data,nvs,0xd000,0x4000",
])
def test_rejects_ambiguous_or_invalid_partition_tables(backups, tmp_path, row):
    first, second, _ = backups
    table = tmp_path / "partitions.csv"
    table.write_text(row, encoding="utf-8")
    with pytest.raises(ValueError, match="partition|sector-aligned"):
        verify_nvs_backups(table, first, second)


def _partition_record(name: bytes, offset: int, size: int, subtype: int = 2) -> bytes:
    return struct.pack("<2sBBII16sI", b"\xaa\x50", 1, subtype, offset, size, name, 0)


def _binary_table(*entries: bytes, size: int = 0xC00, checksummed: bool = True) -> bytes:
    records = b"".join(entries)
    if checksummed:
        records += b"\xeb\xeb" + b"\xff" * 14 + hashlib.md5(records, usedforsecurity=False).digest()
    return records.ljust(size, b"\xff")


@pytest.mark.parametrize("size", [0xC00, 0x1000])
def test_binary_table_selects_device_extent_before_reading_backups(backups, tmp_path, capsys, size):
    first, second, contents = backups
    table = tmp_path / "partition-table.bin"
    table.write_bytes(_binary_table(_partition_record(b"nvs", 0xB000, len(contents)), size=size))
    args = ["--binary-partition-table", str(table)]
    assert main([*args, "--show-partition"]) == 0
    assert capsys.readouterr().out.strip() == "NVS partition: offset=0xb000 size=0x4000"
    assert main([*args, str(first), str(second)]) == 0
    assert "offset=0xb000 size=0x4000" in capsys.readouterr().out


def test_binary_table_rejects_corruption_even_if_entries_are_aligned(tmp_path):
    table = tmp_path / "partition-table.bin"
    data = bytearray(_binary_table(_partition_record(b"nvs", 0x9000, 0x4000)))
    data[5] ^= 0x10  # Changes the NVS offset by an aligned sector.
    table.write_bytes(data)
    with pytest.raises(ValueError, match="MD5 does not match"):
        binary_nvs_partition_extent(table)


@pytest.mark.parametrize(
    ("records", "checksummed", "message"),
    [
        ([(b"nvs", 0x9000, 0x4000, 2)], False, "no MD5"),
        ([(b"nvs", 0x9000, 0x4000, 1)], True, "one nvs"),
        ([(b"nvs", 0x9000, 0x4000, 2), (b"nvs", 0xD000, 0x4000, 2)], True, "one nvs"),
        ([(b"nvs", 0x9000, 0x4000, 2), (b"other", 0xC000, 0x2000, 3)], True, "overlaps"),
    ],
)
def test_binary_table_rejects_unsafe_partition_layout(tmp_path, records, checksummed, message):
    table = tmp_path / "partition-table.bin"
    table.write_bytes(_binary_table(*(_partition_record(*row) for row in records), checksummed=checksummed))
    with pytest.raises(ValueError, match=message):
        binary_nvs_partition_extent(table)


def test_binary_table_rejects_short_capture(tmp_path):
    table = tmp_path / "partition-table.bin"
    table.write_bytes(_binary_table(_partition_record(b"nvs", 0x9000, 0x4000))[:-1])
    with pytest.raises(ValueError, match="0xc00-byte"):
        binary_nvs_partition_extent(table)


@pytest.mark.parametrize(
    ("target_offset", "target_size", "checksummed", "error"),
    [
        (0x9000, 0x4000, True, None),
        (0xA000, 0x4000, True, "target NVS offset or size differs"),
        (0x9000, 0x5000, True, "target NVS offset or size differs"),
        (0x9000, 0x4000, False, "no MD5"),
    ],
)
def test_target_partition_preflight(
    backups, tmp_path, capsys, target_offset, target_size, checksummed, error,
):
    first, second, contents = backups
    source = tmp_path / "captured-sector.bin"
    target = tmp_path / "target-image-table.bin"
    source.write_bytes(_binary_table(_partition_record(b"nvs", 0x9000, 0x4000), size=0x1000))
    target.write_bytes(_binary_table(
        _partition_record(b"nvs", target_offset, target_size), checksummed=checksummed,
    ))
    args = ["--binary-partition-table", str(source), "--target-binary-partition-table",
            str(target), str(first), str(second)]
    if error:
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert error in captured.err
        assert not captured.out
    else:
        assert main(args) == 0
        stdout = capsys.readouterr().out
        assert hashlib.sha256(contents).hexdigest() in stdout
        assert "Source and target NVS offset and size match." in stdout
        second.write_bytes(contents[:-1] + b"\x00")
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
        captured = capsys.readouterr()
        assert "backup copies do not match" in captured.err
        assert not captured.out


@pytest.mark.parametrize("source_options", [[], ["--binary-partition-table", "source.bin", "--show-partition"]])
def test_target_partition_preflight_requires_binary_source_and_backups(source_options, capsys):
    with pytest.raises(SystemExit) as exc:
        main([*source_options, "--target-binary-partition-table", "target.bin"])
    assert exc.value.code == 2
    assert "requires --binary-partition-table and two backup files" in capsys.readouterr().err
