"""
Unit Tests for Base62 Encoding and Decoding.
"""

import pytest
from shared.utilities.base62 import BASE62_ALPHABET, decode_base62, encode_base62


def test_base62_zero():
    """Test encoding zero returns the first alphabet character."""
    assert encode_base62(0) == BASE62_ALPHABET[0]
    assert decode_base62(BASE62_ALPHABET[0]) == 0


def test_base62_basic_values():
    """Test basic integer values encode and decode predictably."""
    assert encode_base62(1) == "1"
    assert decode_base62("1") == 1

    assert encode_base62(61) == "Z"
    assert decode_base62("Z") == 61

    assert encode_base62(62) == "10"
    assert decode_base62("10") == 62


def test_base62_bijective_roundtrip():
    """Test that decode(encode(n)) == n for arbitrary integers."""
    test_integers = [
        0,
        1,
        61,
        62,
        100,
        1000,
        1000000,
        1000001,
        987654321,
        56800235583,  # 62^6 - 1
        100000000000,
    ]
    for num in test_integers:
        encoded = encode_base62(num)
        decoded = decode_base62(encoded)
        assert decoded == num, f"Mismatch for {num}: encoded as '{encoded}', decoded as {decoded}"


def test_base62_deterministic():
    """Test that encoding the same integer always returns the exact same string."""
    assert encode_base62(1000001) == encode_base62(1000001)


def test_base62_negative_input_raises_value_error():
    """Test that negative numbers raise ValueError."""
    with pytest.raises(ValueError, match="Cannot encode negative integer"):
        encode_base62(-1)


def test_base62_invalid_characters_raise_value_error():
    """Test that non-Base62 characters raise ValueError upon decoding."""
    invalid_codes = ["abc$", "123@", "hello world", "test!", "code#1"]
    for code in invalid_codes:
        with pytest.raises(ValueError, match="Invalid Base62 character"):
            decode_base62(code)


def test_base62_empty_string_raises_value_error():
    """Test that decoding an empty string raises ValueError."""
    with pytest.raises(ValueError, match="Cannot decode empty Base62 string"):
        decode_base62("")
