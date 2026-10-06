"""
Validation Utilities for URLs, Custom Aliases, and Timestamps.
"""

import re
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from shared.database.base import get_utc_now
from shared.utilities.errors import ValidationError

# Custom alias pattern: 4 to 30 characters consisting of letters, digits, dash, underscore
CUSTOM_ALIAS_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{4,30}$")
MAX_URL_LENGTH = 2048


def validate_long_url(url: str) -> str:
    """
    Validates long URL string.

    Rules:
    - Non-empty and stripped of leading/trailing whitespace
    - Maximum length <= 2048 characters
    - Must start with http:// or https://
    - Must have a valid network location (domain/host)
    """
    if not url or not isinstance(url, str):
        raise ValidationError("URL must be a non-empty string.")

    cleaned_url = url.strip()

    if len(cleaned_url) > MAX_URL_LENGTH:
        raise ValidationError(f"URL exceeds maximum allowed length of {MAX_URL_LENGTH} characters.")

    try:
        parsed = urlparse(cleaned_url)
    except Exception as e:
        raise ValidationError(f"Invalid URL structure: {e}") from e

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValidationError("URL must use 'http' or 'https' protocol.")

    if not parsed.netloc:
        raise ValidationError("URL must contain a valid domain or host name.")

    return cleaned_url


def validate_custom_alias(alias: Optional[str]) -> Optional[str]:
    """
    Validates custom alias format.

    Rules:
    - If None or empty, returns None.
    - Length between 4 and 30 characters.
    - Contains only alphanumeric characters, dashes, or underscores [a-zA-Z0-9_-].
    - Case-sensitive.
    """
    if alias is None:
        return None

    cleaned_alias = alias.strip()
    if not cleaned_alias:
        return None

    if not CUSTOM_ALIAS_PATTERN.match(cleaned_alias):
        raise ValidationError(
            "Custom alias must be 4-30 characters long and contain only letters, numbers, hyphens, or underscores."
        )

    return cleaned_alias


def validate_expiration_date(
    expires_at: Optional[datetime],
    reference_time: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Validates that the expiration date is strictly in the future.
    """
    if expires_at is None:
        return None

    now = reference_time or get_utc_now()
    # Normalize to UTC comparison
    if expires_at.tzinfo is None:
        now_cmp = now.replace(tzinfo=None)
    else:
        now_cmp = now

    if expires_at <= now_cmp:
        raise ValidationError("Expiration date must be in the future.")

    return expires_at
