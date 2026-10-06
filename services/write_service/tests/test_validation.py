"""
Unit Tests for URL, Alias, and Expiration Validation.
"""

from datetime import datetime, timedelta, timezone
import pytest
from shared.database.base import get_utc_now
from shared.utilities.errors import ValidationError
from shared.utilities.validation import (
    validate_custom_alias,
    validate_expiration_date,
    validate_long_url,
)


def test_validate_long_url_valid():
    """Test valid HTTP and HTTPS URLs pass validation."""
    valid_urls = [
        "http://example.com",
        "https://example.com/path/to/resource?query=123&sort=asc#heading",
        "https://sub.domain.org:8080/api/v1/test",
        "https://github.com/fastapi/fastapi",
    ]
    for url in valid_urls:
        assert validate_long_url(url) == url


def test_validate_long_url_invalid():
    """Test invalid URLs raise ValidationError."""
    invalid_urls = [
        "",
        "ftp://example.com",
        "javascript:alert(1)",
        "not_a_url",
        "http://",
        "https://",
        "a" * 2049,  # Exceeds max length
    ]
    for url in invalid_urls:
        with pytest.raises(ValidationError):
            validate_long_url(url)


def test_validate_custom_alias_valid():
    """Test valid custom aliases pass validation."""
    valid_aliases = [
        "valid-alias",
        "my_link_123",
        "Promo2026",
        "abcd",  # 4 chars minimum
        "a" * 30,  # 30 chars maximum
    ]
    for alias in valid_aliases:
        assert validate_custom_alias(alias) == alias

    # None and empty return None
    assert validate_custom_alias(None) is None
    assert validate_custom_alias("  ") is None


def test_validate_custom_alias_invalid():
    """Test invalid custom aliases raise ValidationError."""
    invalid_aliases = [
        "abc",  # Too short (< 4 chars)
        "a" * 31,  # Too long (> 30 chars)
        "invalid alias with spaces",
        "my$link",
        "alias!",
        "link/test",
        "link?query",
    ]
    for alias in invalid_aliases:
        with pytest.raises(ValidationError):
            validate_custom_alias(alias)


def test_validate_expiration_date_valid():
    """Test future expiration dates pass validation."""
    future_date = get_utc_now() + timedelta(days=1)
    assert validate_expiration_date(future_date) == future_date
    assert validate_expiration_date(None) is None


def test_validate_expiration_date_past_raises_error():
    """Test past expiration dates raise ValidationError."""
    past_date = get_utc_now() - timedelta(minutes=5)
    with pytest.raises(ValidationError, match="Expiration date must be in the future"):
        validate_expiration_date(past_date)
