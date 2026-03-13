import pytest
import bitstring
from pretty_j1939.core.describe import get_describer


def test_na_reproduction_ascii_rules():
    """Verify ASCII N/A and Error rules according to J1939/71 Table 7.5.
    N/A: 0xFF, Error: 0x00.
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
                "Units": "ASCII",
                "SPNLength": 16,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 0xFFFF,
            }
        },
    }

    # Test N/A (all 0xFF)
    describer_na = get_describer(da_json=db, include_na=True)
    message_data_na = bitstring.Bits(hex="0000FFFF00000000")
    description_na = describer_na(message_data_na, 0x18F00503)
    assert description_na["Transmission Requested Range"] == "N/A"

    # Test Error (all 0x00)
    # Note: if the whole field is 0x00, it's an Error for ASCII
    message_data_err = bitstring.Bits(hex="0000000000000000")
    description_err = describer_na(message_data_err, 0x18F00503)
    assert description_err["Transmission Requested Range"] == "Error"

    # Test Valid (e.g. 'A' 0x41)
    message_data_valid = bitstring.Bits(hex="0000414100000000")
    description_valid = describer_na(message_data_valid, 0x18F00503)
    assert description_valid["Transmission Requested Range"] == "AA"


def test_na_omission_ascii():
    """Verify ASCII N/A omission."""
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
                "Units": "ASCII",
                "SPNLength": 16,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 0xFFFF,
            }
        },
    }
    describer = get_describer(da_json=db, include_na=False)
    message_data = bitstring.Bits(hex="0000FFFF00000000")
    description = describer(message_data, 0x18F00503)

    assert "Transmission Requested Range" not in description
