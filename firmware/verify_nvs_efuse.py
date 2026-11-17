"""Check ESP32-S3 HMAC key metadata from a filtered espefuse JSON summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _unique_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    fields: dict[str, object] = {}
    for name, value in pairs:
        if name in fields:
            raise ValueError("duplicate fields in eFuse summary")
        fields[name] = value
    return fields


def _value(report: dict[str, object], name: str) -> object:
    field = report.get(name)
    if not isinstance(field, dict) or field.get("name") != name or field.get("readable") is not True:
        raise ValueError("missing, invalid, or unreadable eFuse metadata")
    return field.get("value")


def _mask(report: dict[str, object], name: str, width: int) -> int:
    value = _value(report, name)
    if type(value) is not int or not 0 <= value < (1 << width):
        raise ValueError("invalid eFuse protection mask")
    return value


def check_hmac_slot(report: object, key_id: int) -> tuple[str, ...]:
    """Return the unmet requirements for the selected ESP32-S3 key slot."""
    if type(key_id) is not int or not 0 <= key_id <= 5:
        raise ValueError("ESP32-S3 key ID must be between 0 and 5")
    purpose_field = f"KEY_PURPOSE_{key_id}"
    if not isinstance(report, dict) or set(report) != {purpose_field, "RD_DIS", "WR_DIS"}:
        raise ValueError("provide a summary filtered to the selected purpose, RD_DIS, and WR_DIS")
    purpose = _value(report, purpose_field)
    if not isinstance(purpose, str) or not purpose:
        raise ValueError("invalid eFuse key purpose")
    read_mask = _mask(report, "RD_DIS", 7)
    write_mask = _mask(report, "WR_DIS", 32)
    failures = []
    if purpose != "HMAC_UP":
        failures.append("key purpose must be HMAC_UP")
    if not read_mask & (1 << key_id):
        failures.append("key block must be read-protected")
    if not write_mask & (1 << (23 + key_id)):
        failures.append("key block must be write-protected")
    return tuple(failures)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--key-id", type=int, choices=range(6), required=True)
    args = parser.parse_args(argv)
    try:
        with args.summary.open(encoding="utf-8") as source:
            report = json.load(source, object_pairs_hook=_unique_fields)
        failures = check_hmac_slot(report, args.key_id)
    except (OSError, UnicodeError, json.JSONDecodeError):
        parser.error("could not read eFuse summary as UTF-8 JSON")
    except ValueError as exc:
        parser.error(str(exc))
    if failures:
        print(f"ESP32-S3 key ID {args.key_id}: " + "; ".join(failures))
        return 1
    print(f"ESP32-S3 key ID {args.key_id}: HMAC_UP, read-protected, write-protected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
