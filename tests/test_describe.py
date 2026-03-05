#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
from unittest.mock import patch, MagicMock
import pytest
import bitstring
import pretty_j1939.describe
from pretty_j1939.describe import get_describer


def test_config_dir_fallback():
    """Verify that get_default_da_json correctly looks in the user config directory."""
    from pretty_j1939.describe import get_default_da_json

    # Mock os.path.exists to return False for local file but True for config file
    # Mock os.environ to provide APPDATA (Windows)
    with patch("os.path.exists") as mock_exists, patch(
        "os.environ.get"
    ) as mock_env, patch("sys.platform", "win32"):

        def exists_side_effect(path):
            if "AppData" in path and "J1939db.json" in path:
                return True
            return False

        mock_exists.side_effect = exists_side_effect
        mock_env.return_value = "C:\\Users\\Test\\AppData\\Roaming"

        path = get_default_da_json()
        assert "AppData" in path
        assert "pretty_j1939" in path
        assert "J1939db.json" in path


def test_dm1_decoding():
    """Verify DM1 (PGN 65226) decoding with the hardcoded logic."""
    describer = get_describer()
    message_id = 0x18FECA00
    message_data = bitstring.Bits(hex="40FF5B000301FFFF")
    description = describer(message_data, message_id)
    assert description["PGN"] == "DM1(65226)"
    assert description["Malfunction Indicator Lamp Status"] == "On"
    assert "DTC 1" in description


def test_dm1_cm_bit():
    """Verify DM1 decoding correctly identifies the CM (Conversion Method) bit."""
    describer = get_describer()
    message_id = 0x18FECA00
    message_data = bitstring.Bits(hex="00FFD2040381FFFF")
    description = describer(message_data, message_id)
    assert "(CM=1, J1587)" in description["DTC 1"]


def test_address_claim_decoding():
    """Verify Address Claim (PGN 60928) NAME decoding."""
    describer = get_describer()
    message_id = 0x18EEFF80
    message_data = bitstring.Bits(hex="3930A002000302A0")
    description = describer(message_data, message_id)
    assert description["PGN"] == "Address Claimed(60928)"
    assert description["Identity Number"] == 12345


def test_isotp_reassembly():
    """Verify ISO-TP (ISO 15765-2) multi-frame reassembly."""
    describer = get_describer(enable_isotp=True)
    ff_data = bitstring.Bits(hex="100B48656C6C6F20")
    cf_data = bitstring.Bits(hex="21576F726C640000")
    msg_id = 0x18DA2211
    describer(ff_data, msg_id)
    res2 = describer(cf_data, msg_id)
    assert res2["Bytes"] == "48656C6C6F20576F726C64"


def test_variable_length_spn_ascii():
    """Verify decoding of a variable-length ASCII SPN."""
    describer = get_describer()
    pgn_id = 65024
    describer.da_describer.pgn_objects[pgn_id] = {
        "Label": "VAR",
        "Name": "Variable PGN",
        "SPNs": [8888],
        "SPNStartBits": [0],
    }
    describer.da_describer.spn_objects[8888] = {
        "Name": "Text SPN",
        "Units": "ASCII",
        "SPNLength": "Variable",
        "Resolution": 1.0,
        "Offset": 0,
    }
    describer.da_describer._spn_cache.clear()
    message_data = bitstring.Bits(bytes=b"J1939")
    message_id = 0x18FE0039
    description = describer(message_data, message_id)
    assert description["Text SPN"] == "J1939"


def test_bit_aligned_spn():
    """Verify decoding of an SPN that is not byte-aligned."""
    describer = get_describer()
    pgn_id = 65285
    describer.da_describer.pgn_objects[pgn_id] = {
        "Label": "BIT",
        "Name": "Bit PGN",
        "SPNs": [6666],
        "SPNStartBits": [4],
    }
    describer.da_describer.spn_objects[6666] = {
        "Name": "Bit SPN",
        "Units": "rpm",
        "SPNLength": 4,
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 15,
    }
    describer.da_describer._spn_cache.clear()
    message_data = bitstring.Bits(hex="5A00000000000000")
    message_id = 0x18FF0539
    description = describer(message_data, message_id)
    assert "10.0 [rpm]" in description["Bit SPN"]


def test_spn_unavailable():
    """Verify handling of 'Unavailable' SPN values (all bits set)."""
    describer = get_describer()
    pgn_id = 65286
    describer.da_describer.pgn_objects[pgn_id] = {
        "Label": "NA",
        "Name": "NA PGN",
        "SPNs": [5555],
        "SPNStartBits": [0],
    }
    describer.da_describer.spn_objects[5555] = {
        "Name": "NA SPN",
        "Units": "rpm",
        "SPNLength": 8,
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 250,
    }
    describer.da_describer._spn_cache.clear()
    message_data = bitstring.Bits(hex="FF00000000000000")
    message_id = 0x18FF0639
    description = describer(message_data, message_id)
    assert "NA SPN" not in description
    describer_na = get_describer(include_na=True)
    describer_na.da_describer.pgn_objects[pgn_id] = describer.da_describer.pgn_objects[
        pgn_id
    ]
    describer_na.da_describer.spn_objects[5555] = describer.da_describer.spn_objects[
        5555
    ]
    description_na = describer_na(message_data, message_id)
    assert description_na["NA SPN"] == "N/A"


def test_spn_bit_encoding():
    """Verify decoding of enumerated bit-encodings."""
    describer = get_describer()
    pgn_id = 65287
    spn_id = 4444
    describer.da_describer.pgn_objects[pgn_id] = {
        "Label": "ENUM",
        "Name": "Enum PGN",
        "SPNs": [spn_id],
        "SPNStartBits": [6],  # Use bits 6-7 (LSB nibble)
    }
    describer.da_describer.spn_objects[spn_id] = {
        "Name": "State SPN",
        "Units": "bit",
        "SPNLength": 2,
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 3,
    }
    describer.da_describer.bit_encodings[spn_id] = {
        "0": "Off",
        "1": "On",
        "2": "Error",
        "3": "Not Available",
    }
    describer.da_describer._spn_cache.clear()

    # 0x01 (binary 0000 0001). bitstring bits 6-7 are 01 (1).
    message_data = bitstring.Bits(hex="0100000000000000")
    message_id = 0x18FF0739
    description = describer(message_data, message_id)
    assert "1 (On)" in description["State SPN"]


def test_spn_special_units():
    """Verify handling of 'Request Dependent' and 'ASCII' unit types."""
    describer = get_describer()
    pgn_id = 65288
    describer.da_describer.pgn_objects[pgn_id] = {
        "Label": "SPECIAL",
        "Name": "Special PGN",
        "SPNs": [1111, 2222],
        "SPNStartBits": [0, 8],
    }
    describer.da_describer.spn_objects[1111] = {
        "Name": "Req SPN",
        "Units": "Request Dependent",
        "SPNLength": 8,
        "Resolution": 1.0,
        "Offset": 0,
    }
    describer.da_describer.spn_objects[2222] = {
        "Name": "ASCII SPN",
        "Units": "ASCII",
        "SPNLength": 16,
        "Resolution": 1.0,
        "Offset": 0,
    }
    describer.da_describer._spn_cache.clear()
    message_data = bitstring.Bits(hex="424F4B0000000000")
    message_id = 0x18FF0839
    description = describer(message_data, message_id)
    assert "0x42" in description["Req SPN"]
    assert description["ASCII SPN"] == "OK"


def test_spn_uintle_fallback():
    """Verify decoding of multi-byte SPNs that don't hit the 1,2,4 byte fast path."""
    describer = get_describer()
    pgn_id = 65289
    describer.da_describer.pgn_objects[pgn_id] = {
        "Label": "FALLBACK",
        "Name": "Fallback PGN",
        "SPNs": [3333],
        "SPNStartBits": [0],
    }
    describer.da_describer.spn_objects[3333] = {
        "Name": "3-byte SPN",
        "Units": "rpm",
        "SPNLength": 24,  # 3 bytes
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 0xFFFFFF,
    }
    describer.da_describer._spn_cache.clear()
    message_data = bitstring.Bits(hex="1122330000000000")
    message_id = 0x18FF0939
    description = describer(message_data, message_id)
    assert "3351057.0 [rpm]" in description["3-byte SPN"]


def test_spn_out_of_range():
    """Verify handling of SPN values that are beyond operational range."""
    describer = get_describer()
    pgn_id = 65025
    describer.da_describer.pgn_objects[pgn_id] = {
        "Label": "RANGE",
        "Name": "Range PGN",
        "SPNs": [7777],
        "SPNStartBits": [0],
    }
    describer.da_describer.spn_objects[7777] = {
        "Name": "Limited SPN",
        "Units": "rpm",
        "SPNLength": 8,
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 100,
    }
    describer.da_describer._spn_cache.clear()
    message_data = bitstring.Bits(hex="7F00000000000000")
    message_id = 0x18FE0139
    description = describer(message_data, message_id)
    assert "Limited SPN" in description
    assert "Out of range" in description["Limited SPN"]


def test_in_memory_db_usage():
    """Verify that a generic dict can be used as an in-memory database."""
    # Define a generic J1939db schema dict
    pretty_dict = {
        "J1939SATabledb": {"0": "Engine #1"},
        "J1939PGNdb": {
            "61444": {
                "Label": "EEC1",
                "Name": "Engine #1",
                "SPNs": [190],
                "SPNStartBits": [24],
            }
        },
        "J1939SPNdb": {
            "190": {
                "Name": "Engine Speed",
                "Resolution": 0.125,
                "Offset": 0,
                "Units": "rpm",
                "SPNLength": 16,
                "OperationalLow": -1e12,
                "OperationalHigh": 1e12,
            }
        },
        "J1939BitDecodings": {},
    }

    # Initialize describer with the dict directly
    describer = get_describer(da_json=pretty_dict)

    # Verify it works
    message_id = 0x0CF00400  # EEC1 from SA 0
    message_data = bitstring.Bits(hex="0000000000400000")  # Engine Speed bits
    description = describer(message_data, message_id)

    assert description["PGN"] == "EEC1(61444)"
    assert "Engine Speed" in description
    assert description["SA"] == "Engine #1(  0)"


def test_resolve_pgn_engine():
    describer = get_describer()
    pgns = describer.da_describer.resolve_pgn("eec1")
    assert 61444 in pgns


def test_resolve_address_engine():
    describer = get_describer()
    addrs = describer.da_describer.resolve_address("engine")
    assert 0 in addrs


# --------------------------------------------------------------------------- #
# Old schema support tests
#
# Older J1939db.json files (e.g. from TruckCapeProjects) have a different
# structure:
#   - SPN start bit is stored in the SPN entry ("StartBit") not in the PGN
#   - PGN entries have no "SPNStartBits" key
#   - No "J1939BitDecodings" top-level key
# The following tests verify that these older schemas are still supported.
# --------------------------------------------------------------------------- #


def _make_old_schema_db():
    """Return a minimal old-schema-style J1939 database dict."""
    return {
        "J1939SATabledb": {"0": "Engine #1", "11": "Brakes - System Controller"},
        "J1939PGNdb": {
            "61444": {
                "Label": "EEC1",
                "Name": "Electronic Engine Controller 1",
                "PGNLength": "8",
                "Rate": "engine speed dependent",
                "SPNs": [899, 190],
            }
        },
        "J1939SPNdb": {
            "899": {
                "Acronym": "EEC1",
                "Name": "Engine Torque Mode",
                "Offset": 0.0,
                "OperationalHigh": 15.0,
                "OperationalLow": 0.0,
                "Resolution": 1,
                "SPN": 899,
                "SPNLength": 4,
                "StartBit": 0,
                "Units": "bit",
            },
            "190": {
                "Acronym": "EEC1",
                "Name": "Engine Speed",
                "Offset": 0.0,
                "OperationalHigh": 8031.875,
                "OperationalLow": 0.0,
                "Resolution": 0.125,
                "SPN": 190,
                "SPNLength": 16,
                "StartBit": 24,
                "Units": "rpm",
            },
        },
        # Note: no J1939BitDecodings key
    }


def test_old_schema_startbit_in_spn():
    """Old schema: SPN start bit is in the SPN entry, not the PGN."""
    db = _make_old_schema_db()
    describer = get_describer(da_json=db)

    message_id = 0x0CF00400  # EEC1 from SA 0
    # Engine Speed at bits 24-39 (bytes 3-4): 0x20 0x48 => little-endian 0x4820 = 18464
    # 18464 * 0.125 = 2308.0 rpm
    message_data = bitstring.Bits(hex="0041FF20481400F0")
    description = describer(message_data, message_id)

    assert description["PGN"] == "EEC1(61444)"
    assert "Engine Speed" in description
    assert "2308.0" in str(description["Engine Speed"])


def test_old_schema_no_spnstartbits_in_pgn():
    """Old schema: PGN entries have no 'SPNStartBits' key; start bits come from SPNs."""
    db = _make_old_schema_db()
    # Verify our test db matches the old schema pattern
    assert "SPNStartBits" not in db["J1939PGNdb"]["61444"]
    assert "StartBit" in db["J1939SPNdb"]["190"]

    describer = get_describer(da_json=db)
    message_id = 0x0CF00400
    message_data = bitstring.Bits(hex="0041FF20481400F0")
    description = describer(message_data, message_id)

    assert description["PGN"] == "EEC1(61444)"
    assert description["SA"] == "Engine #1(  0)"


def test_old_schema_no_bit_decodings():
    """Old schema: no J1939BitDecodings key; bit-encoded SPNs show 'Unknown'."""
    db = _make_old_schema_db()
    assert "J1939BitDecodings" not in db

    describer = get_describer(da_json=db)
    message_id = 0x0CF00400
    # Byte 0 bits 0-3 = Engine Torque Mode = 0x01 => value 1
    message_data = bitstring.Bits(hex="0100000000000000")
    description = describer(message_data, message_id)

    # Without J1939BitDecodings, bit-encoded SPNs should show "Unknown"
    assert "Engine Torque Mode" in description
    assert "Unknown" in description["Engine Torque Mode"]


def test_old_schema_sa_table():
    """Old schema: J1939SATabledb still works for address resolution."""
    db = _make_old_schema_db()
    describer = get_describer(da_json=db)

    message_id = 0x0CF00400  # SA = 0 = Engine #1
    message_data = bitstring.Bits(hex="0000000000000000")
    description = describer(message_data, message_id)

    assert description["SA"] == "Engine #1(  0)"


def test_old_schema_variable_spn_with_delimiter():
    """Old schema: variable-length SPNs with delimiter work without SPNStartBits in PGN."""
    db = {
        "J1939SATabledb": {},
        "J1939PGNdb": {
            "65282": {"Label": "DLM", "Name": "Delimited PGN", "SPNs": [9001, 9002]}
        },
        "J1939SPNdb": {
            "9001": {
                "Name": "Field1",
                "Offset": 0,
                "OperationalHigh": 255,
                "OperationalLow": 0,
                "Resolution": 1,
                "SPNLength": "Variable",
                "StartBit": 0,
                "Units": "ASCII",
                "Delimiter": "0x2A",
            },
            "9002": {
                "Name": "Field2",
                "Offset": 0,
                "OperationalHigh": 255,
                "OperationalLow": 0,
                "Resolution": 1,
                "SPNLength": "Variable",
                "StartBit": -1,
                "Units": "ASCII",
                "Delimiter": "0x2A",
            },
        },
    }
    describer = get_describer(da_json=db)
    message_data = bitstring.Bits(bytes=b"HELLO*WORLD")
    message_id = 0x18FF0200  # PGN 65282
    description = describer(message_data, message_id)

    assert description["Field1"] == "HELLO"
    assert description["Field2"] == "WORLD"


def test_old_schema_single_variable_spn():
    """Old schema: single variable-length SPN without delimiter works."""
    db = {
        "J1939SATabledb": {},
        "J1939PGNdb": {
            "65259": {"Label": "VI", "Name": "Vehicle Identification", "SPNs": [237]}
        },
        "J1939SPNdb": {
            "237": {
                "Name": "Vehicle Identification Number",
                "Offset": 0,
                "OperationalHigh": 0,
                "OperationalLow": 0,
                "Resolution": 1,
                "SPNLength": "Variable",
                "StartBit": 0,
                "Units": "ASCII",
            }
        },
    }
    describer = get_describer(da_json=db)
    vin = b"1HGCM82633A123456"
    message_data = bitstring.Bits(bytes=vin)
    message_id = 0x18FEEB00  # PGN 65259, SA 0
    description = describer(message_data, message_id)

    assert description["Vehicle Identification Number"] == "1HGCM82633A123456"


def test_old_schema_extra_fields_ignored():
    """Old schema: extra fields like Acronym, DataRange, EndBit are gracefully ignored."""
    db = {
        "J1939SATabledb": {},
        "J1939PGNdb": {
            "65265": {
                "Label": "CCVS",
                "Name": "Cruise Control/Vehicle Speed",
                "PGNLength": "8",
                "Rate": "100 ms",
                "SPNs": [84],
            }
        },
        "J1939SPNdb": {
            "84": {
                "Acronym": "CCVS",
                "DataRange": "0 to 250.996 km/h",
                "EndBit": 23,
                "Name": "Wheel-Based Vehicle Speed",
                "Offset": 0.0,
                "OperationalHigh": 250.996,
                "OperationalLow": 0.0,
                "OperationalRange": "",
                "PGNLength": "8",
                "Resolution": 0.00390625,
                "SPN": 84,
                "SPNLength": 16,
                "StartBit": 8,
                "TransmissionRate": "100 ms",
                "Units": "km/h",
            }
        },
    }
    describer = get_describer(da_json=db)
    # Byte 1-2 (bits 8-23): Vehicle Speed
    # 0x00C8 = 200, 200 * 0.00390625 = 0.78125 km/h
    message_data = bitstring.Bits(hex="00C8000000000000")
    message_id = 0x18FEF100  # PGN 65265
    description = describer(message_data, message_id)

    assert "Wheel-Based Vehicle Speed" in description
    assert "km/h" in description["Wheel-Based Vehicle Speed"]


def test_old_schema_full_file(tmp_path):
    """Old schema: can load and use an old-schema-style J1939db.json file from disk."""
    import json

    db = _make_old_schema_db()
    db_path = tmp_path / "old_J1939db.json"
    db_path.write_text(json.dumps(db))

    describer = get_describer(da_json=str(db_path))

    # EEC1 from Engine #1
    message_id = 0x0CF00400
    message_data = bitstring.Bits(hex="0041FF20481400F0")
    description = describer(message_data, message_id)

    assert description["PGN"] == "EEC1(61444)"
    assert description["SA"] == "Engine #1(  0)"
    assert "Engine Speed" in description


def test_pgn_spn_cache_uniqueness():
    """Verify that SPN cache is unique per (PGN, SPN) pair."""
    # Define a database where SPN 100 has different start bits in two PGNs
    db = {
        "J1939PGNdb": {
            "61441": {
                "Label": "PGN1",
                "Name": "PGN One",
                "SPNs": [100],
                "SPNStartBits": [0],
            },
            "61442": {
                "Label": "PGN2",
                "Name": "PGN Two",
                "SPNs": [100],
                "SPNStartBits": [16],
            },
        },
        "J1939SPNdb": {
            "100": {
                "Name": "Reused SPN",
                "Units": "rpm",
                "SPNLength": 16,
                "Resolution": 1.0,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 65535,
            }
        },
    }
    describer = get_describer(da_json=db)

    # Message 1: PGN 61441, SPN at bits 0-15 (value 0x1234 = 4660)
    msg1_id = 0x18F00100  # PDU2 PGN 61441
    msg1_data = bitstring.Bits(hex="3412000000000000")
    desc1 = describer(msg1_data, msg1_id)
    assert desc1["Reused SPN"] == "4660.0 [rpm]"

    # Message 2: PGN 61442, SPN at bits 16-31 (value 0x5678 = 22136)
    msg2_id = 0x18F00200  # PDU2 PGN 61442
    msg2_data = bitstring.Bits(hex="0000785600000000")
    desc2 = describer(msg2_data, msg2_id)
    assert desc2["Reused SPN"] == "22136.0 [rpm]"


def test_old_schema_list_startbit():
    """Verify support for old-style databases where StartBit in SPN is already a list."""
    db = {
        "J1939PGNdb": {"61444": {"Label": "EEC1", "Name": "Engine 1", "SPNs": [190]}},
        "J1939SPNdb": {
            "190": {
                "Name": "Engine Speed",
                "Units": "rpm",
                "SPNLength": 16,
                "Resolution": 0.125,
                "Offset": 0,
                "StartBit": [24],
                "OperationalLow": 0,
                "OperationalHigh": 8031.875,
            }
        },
    }
    describer = get_describer(da_json=db)
    msg_id = 0x0CF00400
    msg_data = bitstring.Bits(hex="0000002048000000")  # 0x4820 = 18464 * 0.125 = 2308.0
    desc = describer(msg_data, msg_id)
    assert desc["Engine Speed"] == "2308.0 [rpm]"


def test_lookup_spn_startbit_unknown():
    """Verify lookup_spn_startbit returns [-1] for unknown mappings instead of crashing."""
    db = {
        "J1939PGNdb": {"61444": {"Label": "EEC1", "Name": "Engine 1", "SPNs": [190]}},
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
    }
    describer = get_describer(da_json=db)
    # This SPN is in PGN list but has no StartBit in SPN and no SPNStartBits in PGN
    start = describer.da_describer.lookup_spn_startbit(
        describer.da_describer.spn_objects[190], 190, 61444
    )
    assert start == [-1]


def test_cache_population_even_if_skipped():
    """Verify that SPN cache is populated even if the SPN is in skip_spns."""
    db = {
        "J1939PGNdb": {
            "61440": {
                "Label": "ERC1",
                "Name": "ERC1",
                "SPNs": [900],
                "SPNStartBits": [0],
            }
        },
        "J1939SPNdb": {
            "900": {
                "Name": "Retarder Torque Mode",
                "Units": "bit",
                "SPNLength": 4,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 15,
            }
        },
    }
    describer = get_describer(da_json=db)

    # Call describe_message_data with skip_spns={900: ...}
    # This should still populate the cache for (61440, 900)
    describer.da_describer.describe_message_data(
        61440, bitstring.Bits(hex="00"), skip_spns={900: ("Name", "Desc")}
    )

    assert (61440, 900) in describer.da_describer._spn_cache

    # Subsequent call to get_spn_value should not crash
    val = describer.da_describer.get_spn_value(
        bitstring.Bits(hex="00"), 900, 61440, True
    )
    assert val == 0


def test_missing_spn_in_db_fallback_to_bytes():
    """Verify that a PGN with SPNs missing from the DB falls back to showing Bytes."""
    db = {
        "J1939PGNdb": {
            "65248": {"Label": "VD", "Name": "Vehicle Distance", "SPNs": [244, 245]}
        },
        "J1939SPNdb": {},  # Missing both 244 and 245
    }
    describer = get_describer(da_json=db)
    message_id = 0x18FEE000  # PGN 65248
    message_data = bitstring.Bits(hex="1BC9A8001BC9A800")
    description = describer(message_data, message_id)

    assert description["PGN"] == "VD(65248)"
    assert "Bytes" in description
    assert description["Bytes"] == "1BC9A8001BC9A800"
    # Ensure no individual SPNs were added
    assert "Distance" not in str(description)
