from __future__ import annotations

import hashlib

import pytest

from firmware.verify_nvs_backup import DEFAULT_PARTITION_TABLE, main, verify_nvs_backups


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
