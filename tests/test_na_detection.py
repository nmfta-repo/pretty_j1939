import pytest
import bitstring
from pretty_j1939.core.describe import get_describer


def test_na_detection_16bit():
    """Verify that a 16-bit SPN with 0xFFFF is detected as Not Available.
    The issue reported is that it shows as 'ÿÿ' (latin-1 decode of 0xFFFF).
    """
    db = {
        "J1939SATabledb": {"3": "Transmission #1"},
        "J1939PGNdb": {
            "61445": {
                "Label": "ETC2",
                "Name": "Electronic Transmission Controller 2",
                "SPNs": [161, 162],
                "SPNStartBits": [
                    16,
                    32,
                ],  # Transmission Requested Range, Transmission Current Range
            }
        },
        "J1939SPNdb": {
            "161": {
                "Name": "Transmission Requested Range",
                "Units": "byte",  # If it was ASCII it would be decoded as such
                "SPNLength": 16,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 0xFFFF,
            },
            "162": {
                "Name": "Transmission Current Range",
                "Units": "byte",
                "SPNLength": 16,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 0xFFFF,
            },
        },
        "J1939BitDecodings": {},
    }
    describer = get_describer(da_json=db)
    # 0x18F00503: PGN 61445, SA 3, DA 255
    message_id = 0x18F00503
    # Data: FFFFFF7CFFFFFFFF
    # Byte 0: FF
    # Byte 1: FF
    # Byte 2: FF (Start of SPN 161)
    # Byte 3: 7C (Part of SPN 161) -> Value 0x7CFF
    # Wait, the user's example: 0x18F00503 FFFFFF7CFFFFFFFF
    # Transmission Current Gear: -1 [gear value]
    # If Transmission Current Gear is SPN 523 (byte 0), 0xFF = -1 offset?
    # Let's see what SPNs are usually in ETC2.

    # Byte 0: FF, Byte 1: FF, Byte 2: FF, Byte 3: FF, Byte 4: FF, Byte 5: FF, ...
    message_data = bitstring.Bits(hex="0000FFFFFFFF0000")
    # SPN 161 (Requested Range) at bit 16 (byte 2), length 16: 0xFFFF
    # SPN 162 (Current Range) at bit 32 (byte 4), length 16: 0xFFFF

    description = describer(message_data, message_id)

    print(f"Description: {description}")

    # Check if they are in description. If include_na=False (default), they should NOT be there.
    assert "Transmission Requested Range" not in description
    assert "Transmission Current Range" not in description


def test_na_detection_ascii_like_units():
    """Verify that SPNs with units that are NOT 'ascii' but might be mistaken for it
    or just fall through to raw byte decoding are handled correctly.
    """
    db = {
        "J1939SATabledb": {"3": "Transmission #1"},
        "J1939PGNdb": {
            "61445": {
                "Label": "ETC2",
                "Name": "Electronic Transmission Controller 2",
                "SPNs": [161],
                "SPNStartBits": [16],
            }
        },
        "J1939SPNdb": {
            "161": {
                "Name": "Transmission Requested Range",
                "Units": "byte",
                "SPNLength": 16,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 0xFFFF,
            }
        },
    }
    describer = get_describer(da_json=db, include_na=True)
    message_id = 0x18F00503
    # SPN 161 starts at bit 16. If bytes 2 and 3 are 0xFF, 0xFF.
    message_data = bitstring.Bits(hex="0000FFFF00000000")
    description = describer(message_data, message_id)

    assert description["Transmission Requested Range"] == "N/A"
