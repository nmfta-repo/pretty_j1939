#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
from collections import OrderedDict
from pretty_j1939.describe import get_describer


def test_reorder_description_sanitization():
    """Verify that reorder_description sanitizes keys and values."""
    describer = get_describer()

    # Create a description with non-printable characters
    description = OrderedDict(
        [
            ("NormalKey", "NormalValue"),
            ("Bad\x00Key", "Bad\x01Value"),
            ("Embedded\nNewline", "Another\rValue"),
            ("PGN", "EEC1(61444)"),
            ("SA", "Engine(0)"),
        ]
    )

    sanitized = describer.reorder_description(description)

    # Check that keys and values are sanitized
    assert "Bad.Key" in sanitized
    assert sanitized["Bad.Key"] == "Bad.Value"
    assert "Embedded.Newline" in sanitized
    assert sanitized["Embedded.Newline"] == "Another.Value"

    # Check that PGN and SA are at the beginning
    keys = list(sanitized.keys())
    assert keys[0] == "PGN"
    assert keys[1] == "SA"


def test_reorder_description_noprintable_keys():
    """Verify that reorder_description handles non-printable keys correctly."""
    describer = get_describer()

    # Use a key that is entirely non-printable
    description = OrderedDict(
        [
            ("\x01\x02\x03", "Value"),
        ]
    )

    sanitized = describer.reorder_description(description)
    assert "..." in sanitized
    assert sanitized["..."] == "Value"


def test_reorder_description_noprintable_values():
    """Verify that reorder_description handles non-printable values correctly."""
    describer = get_describer()

    # Use a value that is entirely non-printable
    description = OrderedDict(
        [
            ("Key", "\x01\x02\x03"),
        ]
    )

    sanitized = describer.reorder_description(description)
    assert sanitized["Key"] == "..."
