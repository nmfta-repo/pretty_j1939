import bitstring
import pytest
from pretty_j1939.describe import get_describer


def test_steering_wheel_turn_counter_na():
    """Observation: Steering Wheel Turn Counter: 0b111111 (Out of range) -- should be Not Available.
    This is SPN 1812 (6 bits). 0x3F (all 1s) should be Not Available.
    """
    db = {
        "J1939SATabledb": {"19": "Steering Controller"},
        "J1939PGNdb": {
            "61449": {
                "Label": "VDC2",
                "Name": "Vehicle Dynamic Control 2",
                "SPNs": [1812],
                "SPNStartBits": [8],  # Byte 2, bits 0-5 => bit 8-13
            }
        },
        "J1939SPNdb": {
            "1812": {
                "Name": "Steering Wheel Turn Counter",
                "Units": "bit",
                "SPNLength": 6,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 62,
            }
        },
        "J1939BitDecodings": {},
    }
    describer = get_describer(da_json=db)
    # VDC2 from SA 19
    message_id = 0x18F00913
    # 0x3F (111111) at bit 8 (LSB of Byte 2)
    # Byte 1: 00, Byte 2: 3F
    message_data = bitstring.Bits(hex="003F000000000000")
    description = describer(message_data, message_id)

    # If it's correctly identified as NA, and include_na is False, it should NOT be in description
    assert "Steering Wheel Turn Counter" not in description


def test_transmission_actual_gear_ratio_na():
    """Observation: Transmission Actual Gear Ratio: 0xffff -- should be Not Available.
    If it's treated as non-numerical (e.g. units="byte"), it should still be checkable for NA.
    """
    db = {
        "J1939SATabledb": {"5": "Shift Console - Primary"},
        "J1939PGNdb": {
            "61445": {
                "Label": "ETC2",
                "Name": "Electronic Transmission Controller 2",
                "SPNs": [526],
                "SPNStartBits": [0],
            }
        },
        "J1939SPNdb": {
            "526": {
                "Name": "Transmission Actual Gear Ratio",
                "Units": "byte",  # Non-numerical
                "SPNLength": 16,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 0xFFFF,
            }
        },
        "J1939BitDecodings": {},
    }
    describer = get_describer(da_json=db)
    message_id = 0x18F00505
    message_data = bitstring.Bits(hex="FFFF000000000000")
    description = describer(message_data, message_id)

    # Should be omitted if NA and include_na=False
    assert "Transmission Actual Gear Ratio" not in description


def test_transmission_requested_range_error():
    """Observation: Transmission Requested Range: 0x7eff -- should be Error.
    This implies SPN 161 is 7 bits and 0x7E is the error indicator.
    """
    db = {
        "J1939SATabledb": {"5": "Shift Console - Primary"},
        "J1939PGNdb": {
            "61445": {
                "Label": "ETC2",
                "Name": "Electronic Transmission Controller 2",
                "SPNs": [161],
                "SPNStartBits": [16],  # Bit 16
            }
        },
        "J1939SPNdb": {
            "161": {
                "Name": "Transmission Requested Range",
                "Units": "bit",
                "SPNLength": 7,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 125,
            }
        },
        "J1939BitDecodings": {},
    }
    describer = get_describer(da_json=db)
    message_id = 0x18F00505
    # 0x7E (1111110) at bit 16 (LSB of Byte 3)
    # Byte 1: 00, Byte 2: 00, Byte 3: 7E
    message_data = bitstring.Bits(hex="00007E0000000000")
    description = describer(message_data, message_id)

    assert "Transmission Requested Range" in description
    assert "Error" in str(description["Transmission Requested Range"])


def test_dm1_lamp_status_omission():
    """Observation: Red Stop Lamp Status: Not Available -- these should be omitted from display."""
    describer = get_describer()  # Use default DB which has DM1 support
    message_id = 0x18FECA21  # DM1 from SA 33
    # Lamp status is byte 0.
    # Malfunction: Off (00), Red Stop: Not Available (11), Amber: Not Available (11), Protect: Not Available (11)
    # 00 11 11 11 => 0x3F
    message_data = bitstring.Bits(hex="3FFFFFFFFFFFFFFF")
    description = describer(message_data, message_id)

    assert "Malfunction Indicator Lamp Status" in description
    assert description["Malfunction Indicator Lamp Status"] == "Off"
    assert "Red Stop Lamp Status" not in description
    assert "Amber Warning Lamp Status" not in description
    assert "Protect Lamp Status" not in description
