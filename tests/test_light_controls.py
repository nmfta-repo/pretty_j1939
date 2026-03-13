import pytest
import bitstring
from pretty_j1939.core.describe import get_describer


def test_light_controls_decoding():
    """Verify decoding of SPN 2875 and 2874 in PGN 64972 with original layout."""
    pgn_id = 64972
    db = {
        "J1939PGNdb": {
            str(pgn_id): {
                "Label": "OEL",
                "Name": "Operators External Light Controls Message",
                "PGNLength": "8",
                "SPNs": [
                    2873,
                    2872,
                    2876,
                    2875,
                    2874,
                    2878,
                    2877,
                    4004,
                    12308,
                    12964,
                    20787,
                ],
                "SPNStartBits": [
                    [0],
                    [4],
                    [8],
                    [12],
                    [14],
                    [16],
                    [24],
                    [40],
                    [42],
                    [44],
                    [46],
                ],
            }
        },
        "J1939SPNdb": {
            "2873": {
                "Name": "Work Light Switch",
                "SPNLength": 4,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 15,
            },
            "2872": {
                "Name": "Main Light Switch",
                "SPNLength": 4,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 15,
            },
            "2876": {
                "Name": "Turn Signal Switch",
                "SPNLength": 4,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 15,
            },
            "2875": {
                "Name": "Hazard Light Switch",
                "SPNLength": 2,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 3,
            },
            "2874": {
                "Name": "High-Low Beam Switch",
                "SPNLength": 2,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 3,
            },
            "2878": {
                "Name": "Operators Desired Back-light",
                "SPNLength": 8,
                "Units": "%",
                "Resolution": 0.4,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 100,
            },
            "2877": {
                "Name": "Operators Desired - Delayed Lamp Off Time",
                "SPNLength": 16,
                "Units": "s",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 64255,
            },
            "4004": {
                "Name": "Exterior Lamp Check Switch",
                "SPNLength": 2,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 3,
            },
            "12308": {
                "Name": "Headlamp Emergency Flash Switch",
                "SPNLength": 2,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 3,
            },
            "12964": {
                "Name": "Auxiliary Lamp Group Switch",
                "SPNLength": 2,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 3,
            },
            "20787": {
                "Name": "Auto High/Low Beam Enable Switch",
                "SPNLength": 2,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 3,
            },
        },
        "J1939SATabledb": {"5": "Shift Console - Primary"},
        "J1939BitDecodings": {
            "2875": {
                "0": "Not Available",
                "1": "Hazard Light Switch Off",
                "2": "Hazard Light Switch On",
                "3": "Not             Available",
            },
            "2874": {
                "0": "Low Beam Position",
                "1": "High Beam Position",
                "2": "Error",
                "3": "Not Available",
            },
        },
    }

    describer = get_describer(da_json=db, include_na=True)
    can_id = 0x0CFDCC05
    # Byte 2: 2F -> bits 0-3: 0xF (15) [SPN 2876], bits 4-5: 0x2 (2) [SPN 2875], bits 6-7: 0x0 (0) [SPN 2874]
    payload = bytes.fromhex("FF2FFFFFFFFFFFFF")

    description = describer(payload, can_id)

    assert description["PGN"] == "OEL(64972)"
    assert "2 (Hazard Light Switch On)" in description["Hazard Light Switch"]
    assert "0 (Low Beam Position)" in description["High-Low Beam Switch"]
    assert description["Turn Signal Switch"] == "N/A"


def test_na_decoupling_with_bit_encodings():
    """Verify that N/A is flagged even if J1939BitDecodings has a mapping."""
    pgn_id = 64972
    db = {
        "J1939PGNdb": {
            str(pgn_id): {"Label": "OEL", "SPNs": [2876], "SPNStartBits": [[8]]}
        },
        "J1939SPNdb": {
            "2876": {
                "Name": "Turn Signal Switch",
                "SPNLength": 4,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 15,
            }
        },
        "J1939BitDecodings": {"2876": {"15": "don't care (mapped N/A)"}},
    }

    # Case 1: include_na=True -> Should show "N/A" (ignoring "don't care")
    describer_show_na = get_describer(da_json=db, include_na=True)
    payload_na = bytes.fromhex("000F000000000000")  # Byte 2 lower nibble is 15 (0xF)
    description_na = describer_show_na(payload_na, 0x18FDCC00)
    assert description_na["Turn Signal Switch"] == "N/A"

    # Case 2: include_na=False -> Should omit the field entirely
    describer_hide_na = get_describer(da_json=db, include_na=False)
    description_hide = describer_hide_na(payload_na, 0x18FDCC00)
    assert "Turn Signal Switch" not in description_hide


def test_turn_indicator_repositioned():
    """Verify SPN 2876 repositioned to Byte 2 bits 5-8 as per user's C code fix."""
    pgn_id = 64972
    db = {
        "J1939PGNdb": {
            str(pgn_id): {
                "Label": "OEL",
                "SPNs": [2876],
                "SPNStartBits": [
                    [12]
                ],  # Byte 2 bits 5-8 (J1939 bit 12 is the 5th bit of Byte 2)
            }
        },
        "J1939SPNdb": {
            "2876": {
                "Name": "Turn Signal Switch",
                "SPNLength": 4,
                "Units": "bit",
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 15,
            }
        },
        "J1939BitDecodings": {
            "2876": {
                "0": "No Action",
                "1": "Left Turn",
                "2": "Right Turn",
                "3": "Hazard Warning",
                "15": "Not Available",
            }
        },
    }

    describer = get_describer(da_json=db, include_na=True)

    # Test "Hazard Warning" (value 3)
    # The C code: payload[1] = (payload[1] & 0x0F) | (3 << 4)
    # 3 << 4 results in 0x30 in Byte 2.
    payload = bytes.fromhex("FF3FFFFFFFFFFFFF")
    description = describer(payload, 0x18FDCC00)
    assert "3 (Hazard Warning)" in description["Turn Signal Switch"]

    # Test "Left Turn" (value 1) -> 1 << 4 = 0x10
    payload = bytes.fromhex("FF1FFFFFFFFFFFFF")
    description = describer(payload, 0x18FDCC00)
    assert "1 (Left Turn)" in description["Turn Signal Switch"]

    # Test "Right Turn" (value 2) -> 2 << 4 = 0x20
    payload = bytes.fromhex("FF2FFFFFFFFFFFFF")
    description = describer(payload, 0x18FDCC00)
    assert "2 (Right Turn)" in description["Turn Signal Switch"]
