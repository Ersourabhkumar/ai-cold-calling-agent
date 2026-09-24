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


def test_rejects_11_digit_indian_number():
    result = validate_phone("+9196718898122")
    assert result.valid is False
    assert "10 digits" in (result.reason or "")


def test_rejects_indian_number_with_bad_start_digit():
    assert validate_phone("+915665035514").valid is False
    assert validate_phone("+911234567890").valid is False


def test_valid_indian_mobiles():
    for phone in (
        "+917665035514",
        "+919876543210",
        "+918045695073",
        "+916789012345",
    ):
        result = validate_phone(phone)
        assert result.valid is True, phone


def test_non_indian_numbers_keep_generic_rules():
    assert validate_phone("+14155552671").valid is True