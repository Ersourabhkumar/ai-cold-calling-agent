import pytest

from app.core.phone_validation import mask_phone, validate_phone


def test_valid_e164_indian_number():
    result = validate_phone("+917665035514")
    assert result.valid is True
    assert result.normalized == "+917665035514"


def test_missing_plus_is_rejected():
    result = validate_phone("917665035514")
    assert result.valid is False
    assert "country code" in (result.reason or "")


def test_rejects_garbage():
    assert validate_phone("abc").valid is False
    assert validate_phone("").valid is False
    assert validate_phone("+").valid is False


def test_rejects_short_number():
    assert validate_phone("+123").valid is False


def test_mask_hides_all_but_last_four():
    masked = mask_phone("+917665035514")
    assert masked.endswith("5514")
    assert "7660" not in masked
    assert masked.startswith("+***")


def test_mask_short_number():
    assert mask_phone("123") == "***"
    assert mask_phone("") == "empty"