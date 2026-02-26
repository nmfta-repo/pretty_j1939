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
    with patch("os.path.exists") as mock_exists, \
         patch("os.environ.get") as mock_env, \
         patch("sys.platform", "win32"):
        
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
        "SPNStartBits": [0]
    }
    describer.da_describer.spn_objects[8888] = {
        "Name": "Text SPN",
        "Units": "ASCII",
        "SPNLength": "Variable",
        "Resolution": 1.0,
        "Offset": 0
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
        "SPNStartBits": [4]
    }
    describer.da_describer.spn_objects[6666] = {
        "Name": "Bit SPN",
        "Units": "rpm",
        "SPNLength": 4,
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 15
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
        "SPNStartBits": [0]
    }
    describer.da_describer.spn_objects[5555] = {
        "Name": "NA SPN",
        "Units": "rpm",
        "SPNLength": 8,
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 250
    }
    describer.da_describer._spn_cache.clear()
    message_data = bitstring.Bits(hex="FF00000000000000")
    message_id = 0x18FF0639
    description = describer(message_data, message_id)
    assert "NA SPN" not in description
    describer_na = get_describer(include_na=True)
    describer_na.da_describer.pgn_objects[pgn_id] = describer.da_describer.pgn_objects[pgn_id]
    describer_na.da_describer.spn_objects[5555] = describer.da_describer.spn_objects[5555]
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
        "SPNStartBits": [6] # Use bits 6-7 (LSB nibble)
    }
    describer.da_describer.spn_objects[spn_id] = {
        "Name": "State SPN",
        "Units": "bit",
        "SPNLength": 2,
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 3
    }
    describer.da_describer.bit_encodings[spn_id] = {
        "0": "Off",
        "1": "On",
        "2": "Error",
        "3": "Not Available"
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
        "SPNStartBits": [0, 8]
    }
    describer.da_describer.spn_objects[1111] = {
        "Name": "Req SPN",
        "Units": "Request Dependent",
        "SPNLength": 8,
        "Resolution": 1.0,
        "Offset": 0
    }
    describer.da_describer.spn_objects[2222] = {
        "Name": "ASCII SPN",
        "Units": "ASCII",
        "SPNLength": 16,
        "Resolution": 1.0,
        "Offset": 0
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
        "SPNStartBits": [0]
    }
    describer.da_describer.spn_objects[3333] = {
        "Name": "3-byte SPN",
        "Units": "rpm",
        "SPNLength": 24, # 3 bytes
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 0xFFFFFF
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
        "SPNStartBits": [0]
    }
    describer.da_describer.spn_objects[7777] = {
        "Name": "Limited SPN",
        "Units": "rpm",
        "SPNLength": 8,
        "Resolution": 1.0,
        "Offset": 0,
        "OperationalLow": 0,
        "OperationalHigh": 100
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
                "SPNStartBits": [24]
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
                "OperationalHigh": 1e12
            }
        },
        "J1939BitDecodings": {}
    }
    
    # Initialize describer with the dict directly
    describer = get_describer(da_json=pretty_dict)
    
    # Verify it works
    message_id = 0x0CF00400 # EEC1 from SA 0
    message_data = bitstring.Bits(hex="0000000000400000") # Engine Speed bits
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
