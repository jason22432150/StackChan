import binascii
import struct

import pytest

from firmware.verify_ota_selection import inspect_ota_selection


def metadata(first=None, second=None):
    data = bytearray(b"\xff" * 0x2000)
    for base, entry in ((0, first), (0x1000, second)):
        if entry is not None:
            seq, state, crc = entry
            packed = struct.pack("<I", seq)
            if crc is None:
                crc = binascii.crc32(packed, 0xFFFFFFFF) & 0xFFFFFFFF
            data[base:base + 32] = struct.pack("<I20xII", seq, state, crc)
    return bytes(data)


def test_known_crc_vector_and_sequence_mapping():
    # seq=1 CRC used by ESP-IDF's otatool.py (initial CRC 0xffffffff).
    result = inspect_ota_selection(metadata((1, 2, 0x4743989A)), 2)
    assert result["slot"] == 0 and result["stable_metadata"]
    assert result["entries"][0]["crc_valid"]
    assert inspect_ota_selection(metadata((5, 2, None), (6, 2, None)), 2)["slot"] == 1


@pytest.mark.parametrize("bad", [(8, 3, None), (8, 4, None), (8, 2, 0), (0xFFFFFFFF, 2, None)])
def test_invalid_newer_record_does_not_override_valid_record(bad):
    result = inspect_ota_selection(metadata((1, 2, None), bad), 2)
    assert result["selected_entry"] == 0 and result["slot"] == 0


def test_tie_selects_first_and_single_valid_second_selects_second():
    assert inspect_ota_selection(metadata((2, 2, None), (2, 2, None)), 2)["selected_entry"] == 0
    assert inspect_ota_selection(metadata(None, (2, 2, None)), 2)["selected_entry"] == 1


@pytest.mark.parametrize("sequence,state", [(1, 0), (1, 1), (1, 42), (0, 2)])
def test_transitional_or_unknown_metadata_is_not_marked_stable(sequence, state):
    result = inspect_ota_selection(metadata((sequence, state, None)), 2)
    assert result["stable_metadata"] is False
    assert result["slot"] == (((sequence - 1) & 0xFFFFFFFF) % 2)


def test_erased_records_are_only_a_fallback_candidate():
    result = inspect_ota_selection(metadata(), 2)
    assert result["slot"] == 0 and result["selected_entry"] is None
    assert not result["stable_metadata"]
    with pytest.raises(ValueError):
        inspect_ota_selection(metadata(), 2, has_factory=True)
    with pytest.raises(ValueError):
        inspect_ota_selection(metadata((1, 3, None), (2, 4, None)), 2)


@pytest.mark.parametrize("data,slots", [(b"", 2), (b"\xff" * 0x1000, 2), (metadata(), 0), (metadata(), 17), (metadata(), True)])
def test_invalid_lengths_and_slot_counts_are_refused(data, slots):
    with pytest.raises(ValueError):
        inspect_ota_selection(data, slots)
