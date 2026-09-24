"""Phone normalisation to E.164, assuming India (+91) for bare 10-digit numbers."""

from __future__ import annotations

import phonenumbers


def normalize_phone(raw: str, default_region: str = "IN") -> str | None:
    """Return the E.164 form (`+919876543210`) or None if the number is invalid."""
    cleaned = raw.strip()
    if not cleaned or len(cleaned) > 20:
        return None
    try:
        parsed = phonenumbers.parse(cleaned, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return str(phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164))
