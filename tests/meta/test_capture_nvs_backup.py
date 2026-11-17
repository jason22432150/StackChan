from __future__ import annotations

import hashlib
import os
import stat
import struct
import subprocess
from pathlib import Path

import pytest

from firmware import capture_nvs_backup as capture


def _table(offset: int) -> bytes:
    entry = struct.pack("<2sBBII16sI", b"\xaa\x50", 1, 2, offset, 0x4000, b"nvs", 0)
    checksum = b"\xeb\xeb" + b"\xff" * 14 + hashlib.md5(entry, usedforsecurity=False).digest()
    return (entry + checksum).ljust(0x1000, b"\xff")


def test_capture_uses_verified_extent_and_three_read_only_commands(monkeypatch, tmp_path):
    commands = []
    contents = b"fixture" + b"\xff" * (0x4000 - len(b"fixture"))

    def read(command, *, check, timeout, stdout, stderr):
        assert check and timeout == 45
        assert stdout == stderr == subprocess.DEVNULL
        assert command[1:-3] == [
            "-m", "esptool", "--chip", "esp32s3", "--port", "fixture-port",
            "--before", "no-reset", "--after", "no-reset", "--no-stub",
            "read-flash", "--no-progress",
        ]
        commands.append(tuple(command[-3:-1]))
        Path(command[-1]).write_bytes(_table(0xB000) if len(commands) == 1 else contents)

    monkeypatch.setattr(capture.subprocess, "run", read)
    directory, offset, size, digest = capture.capture_nvs_backup("fixture-port", 0x8000, tmp_path)
    assert commands == [("0x8000", "0x1000"), ("0xb000", "0x4000"), ("0xb000", "0x4000")]
    assert (offset, size, digest) == (0xB000, 0x4000, hashlib.sha256(contents).hexdigest())
    assert {path.name for path in directory.iterdir()} == {"partition-table.bin", "capture-1.bin", "capture-2.bin"}
    if os.name == "posix":
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
        assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in directory.iterdir())


@pytest.mark.parametrize(
    ("table", "message"), [(b"\xff" * 0x1000, "no MD5"), (_table(0x8000), "overlaps")],
)
def test_capture_rejects_invalid_extent_before_reading_nvs(monkeypatch, tmp_path, table, message):
    offsets = []

    def read(port, offset, size, destination):
        offsets.append(offset)
        destination.write_bytes(table)

    monkeypatch.setattr(capture, "_read_flash", read)
    with pytest.raises(ValueError, match=message):
        capture.capture_nvs_backup("fixture-port", 0x8000, tmp_path)
    assert offsets == [0x8000]
    assert list(tmp_path.iterdir()) == []


def test_capture_discards_mismatched_or_partial_backup(monkeypatch, tmp_path):
    contents = b"\x01" * 0x4000

    def read(port, offset, size, destination):
        if offset == 0x8000:
            destination.write_bytes(_table(0x9000))
        elif destination.name == "capture-1.bin":
            destination.write_bytes(contents)
        else:
            destination.write_bytes(b"\x02" * 0x4000)

    monkeypatch.setattr(capture, "_read_flash", read)
    with pytest.raises(ValueError, match="copies do not match"):
        capture.capture_nvs_backup("fixture-port", 0x8000, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_capture_discards_partial_output_after_esptool_timeout(monkeypatch, tmp_path):
    def timeout(command, **kwargs):
        Path(command[-1]).write_bytes(b"partial")
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(capture.subprocess, "run", timeout)
    with pytest.raises(RuntimeError, match="read-flash failed at offset 0x8000"):
        capture.capture_nvs_backup("fixture-port", 0x8000, tmp_path)
    assert list(tmp_path.iterdir()) == []
