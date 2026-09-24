"""E.164 outbound phone-number validation.

Used before any real dispatch so we never hand a malformed number to the
telephony provider. Numbers are validated and logged in masked form; the
original lead number is always preserved in the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# E.164: REQUIRED leading '+', then 7..14 digits (country code + national
# number). A leading '+' is mandatory for outbound calls so a local number can
# never be mistaken for an international one.
_E164_PATTERN = re.compile(r"^\+\d{7,14}$")


@dataclass(frozen=True)
class PhoneValidation:
    original: str
    valid: bool
    normalized: str | None = None
    reason: str | None = None


def mask_phone(phone: str) -> str:
    """Mask a phone number for logs without exposing the full value."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return "empty"
    if len(digits) <= 4:
        return "*" * len(digits)
    return f"+{'*' * (len(digits) - 4)}{digits[-4:]}"


def validate_phone(phone: str) -> PhoneValidation:
    """Validate a candidate outbound number against strict E.164 rules."""
    original = (phone or "").strip()
    if not original:
        return PhoneValidation(original=original, valid=False, reason="empty")

    if not _E164_PATTERN.match(original):
        return PhoneValidation(
            original=original,
            valid=False,
            reason=(
                "not a valid international E.164 number; use +<country_code>"
                "<number> with 7-14 digits after '+' (e.g. +917665035514). "
                "Local numbers without a country code are rejected."
            ),
        )

    digits = original[1:]
    if digits.startswith("91"):
        national = digits[2:]
        if len(national) == 10 and national[0] in "6789":
            return PhoneValidation(
                original=original,
                valid=True,
                normalized=original,
            )
        return PhoneValidation(
            original=original,
            valid=False,
            reason=(
                "Invalid Indian mobile number; use +91 followed by exactly "
                "10 digits starting with 6-9 (e.g. +917665035514)."
            ),
        )

    return PhoneValidation(
        original=original,
        valid=True,
        normalized=original,
    )