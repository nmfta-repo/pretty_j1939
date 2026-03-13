import bitstring
import pytest
from pretty_j1939.describe import get_describer


def test_dynamic_name_tracking():
    """Verify that ECU names are tracked dynamically from Address Claimed messages."""
    db = {
        "J1939SATabledb": {"0": "Engine #1", "3": "Transmission #1"},
        "J1939PGNdb": {
            "61444": {
                "Label": "EEC1",
                "Name": "Electronic Engine Controller 1",
                "SPNs": [190],
                "SPNStartBits": [24],
            }
        },
        "J1939SPNdb": {
            "190": {
                "Name": "Engine Speed",
                "Units": "rpm",
                "SPNLength": 16,
                "Resolution": 0.125,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 8031.875,
            }
        },
        "J1939BitDecodings": {},
    }
    describer = get_describer(da_json=db)

    # 1. Message from unknown SA 128
    msg1_id = 0x0CF00480  # PGN 61444, SA 128
    msg1_data = bitstring.Bits(hex="0000002048000000")
    desc1 = describer(msg1_data, msg1_id)
    assert desc1["SA"] == "???(128)"

    # 2. Address Claimed from SA 128
    # NAME payload (8 bytes). Let's use a NAME that corresponds to something recognizable.
    # 0x3930A002000302A0 -> decoded identity number 12345, etc.
    # We want the tracker to associate a name with this SA.
    # For simplicity, we might just use the "Function ID" or similar as part of the name if not in static DB.
    # Actually, the user suggested "NAME (XX)".
    # If the tracker sees an Address Claimed, it should store the NAME and use it for subsequent lookups.

    # Address Claimed PGN 60928 (0xEE00)
    ac_id = 0x18EEFF80  # PGN 60928, SA 128, DA 255
    ac_data = bitstring.Bits(hex="3930A002000302A0")
    desc_ac = describer(ac_data, ac_id)

    # 3. Subsequent message from SA 128 should now have a tracked name
    desc2 = describer(msg1_data, msg1_id)
    # The expected name format for tracked names: "ID:12345,MFG:3,..." or similar based on NAME decode
    # The user said "NAME (XX)" like usual SA/DA.
    # decode_j1939_name returns a dict. We should probably stringify it or pick a key.
    # "Function ID" might be good.
    assert "12345" in desc2["SA"]
    assert "(128)" in desc2["SA"]
