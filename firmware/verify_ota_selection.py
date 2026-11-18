"""Read-only OTA metadata inspection; selection is not proof of a running app.

Matches ESP-IDF 6.1 bootloader_common_loader.c sequence CRC and max selection.
Does not emulate anti-rollback, image validation, or bootloader fallback scans.
"""

from __future__ import annotations

import binascii
import struct


def inspect_ota_selection(data: bytes, ota_slots: int, *, has_factory: bool = False) -> dict:
    if len(data) != 0x2000 or type(ota_slots) is not int or not 1 <= ota_slots <= 16:
        raise ValueError("require two complete OTA sectors and a valid slot count")
    records = [data[base:base + 32] for base in (0, 0x1000)]
    entries = []
    for record in records:
        sequence, state, stored_crc = struct.unpack("<I20xII", record)
        crc_valid = stored_crc == (binascii.crc32(record[:4], 0xFFFFFFFF) & 0xFFFFFFFF)
        entries.append({
            "sequence": sequence, "state": state, "crc_valid": crc_valid,
            "sdk_selectable": sequence != 0xFFFFFFFF and state not in (3, 4) and crc_valid,
        })
    valid = [index for index, entry in enumerate(entries) if entry["sdk_selectable"]]
    if not valid:
        if has_factory or not all(record == b"\xff" * 32 for record in records):
            raise ValueError("no validated OTA selection; separate fallback analysis required")
        return {"entries": entries, "selected_entry": None, "slot": 0,
                "basis": "erased_records_without_factory_fallback", "stable_metadata": False}
    selected = max(valid, key=lambda index: entries[index]["sequence"])
    entry = entries[selected]
    return {
        "entries": entries, "selected_entry": selected,
        "slot": ((entry["sequence"] - 1) & 0xFFFFFFFF) % ota_slots,
        "basis": "highest_valid_sequence",
        "stable_metadata": entry["sequence"] != 0 and entry["state"] in (2, 0xFFFFFFFF),
    }
