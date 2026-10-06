"""
Base62 Encoding and Decoding Module.

Base62 is a positional numeral system that uses 62 distinct alphanumeric characters:
- 0-9 (10 digits)
- a-z (26 lowercase letters)
- A-Z (26 uppercase letters)

Why Base62 for URL Shorteners?
1. URL-safe: Contains only [0-9a-zA-Z], requiring no percent-encoding in URLs.
2. Compact representation: 62^6 ≈ 56.8 billion distinct short codes with just 6 characters.
   62^7 ≈ 3.52 trillion distinct short codes with 7 characters.
3. Deterministic & Bijective: Every positive integer maps uniquely to a Base62 string
   and vice versa, ensuring zero hash collisions when backed by an atomic counter.
"""

from typing import Final

BASE62_ALPHABET: Final[str] = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE: Final[int] = len(BASE62_ALPHABET)  # 62
CHAR_TO_INDEX: Final[dict[str, int]] = {char: idx for idx, char in enumerate(BASE62_ALPHABET)}


def encode_base62(num: int) -> str:
    """
    Encodes a non-negative integer into a Base62 string.

    Args:
        num: Non-negative integer to encode.

    Returns:
        Deterministic Base62 string representation.

    Raises:
        ValueError: If num is negative.
    """
    if num < 0:
        raise ValueError(f"Cannot encode negative integer to Base62: {num}")
    if num == 0:
        return BASE62_ALPHABET[0]

    digits: list[str] = []
    current = num
    while current > 0:
        remainder = current % BASE
        digits.append(BASE62_ALPHABET[remainder])
        current //= BASE

    # Digits were appended least-significant first, so reverse them
    return "".join(reversed(digits))


def decode_base62(code: str) -> int:
    """
    Decodes a Base62 string back into its original integer.

    Args:
        code: Base62 encoded string.

    Returns:
        The decoded non-negative integer.

    Raises:
        ValueError: If code is empty or contains characters not in BASE62_ALPHABET.
    """
    if not code:
        raise ValueError("Cannot decode empty Base62 string")

    decoded = 0
    for char in code:
        if char not in CHAR_TO_INDEX:
            raise ValueError(f"Invalid Base62 character: '{char}' in code '{code}'")
        decoded = decoded * BASE + CHAR_TO_INDEX[char]

    return decoded
