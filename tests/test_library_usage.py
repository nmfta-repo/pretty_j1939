#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
import pretty_j1939.describe
import bitstring
import os
import sys


import json


def test_basic_library_usage(tmp_path):
    print("Running test_basic_library_usage...")
    # Create a minimal mock database
    db = {
        "J1939SATabledb": {"0": "Engine #1"},
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
                "Resolution": 0.125,
                "Offset": 0,
                "Units": "rpm",
                "SPNLength": 16,
                "OperationalLow": 0,
                "OperationalHigh": 8031.875,
            }
        },
        "J1939BitDecodings": {},
    }
    db_path = tmp_path / "J1939db.json"
    db_path.write_text(json.dumps(db))

    # Initialize the describer
    describe = pretty_j1939.describe.get_describer(da_json=str(db_path))

    # Describe a frame (EEC1 from Engine #1)
    message_id = bitstring.Bits(hex="0CF00400")
    message_data = bitstring.Bits(hex="0041FF20481400F0")
    description = describe(message_data, message_id.uint)

    print(f"Description: {description}")

    # Verify key fields
    assert description["PGN"] == "EEC1(61444)"
    assert description["SA"] == "Engine #1(  0)"
    assert "Engine Speed" in description
    assert description["_pgn"] == 61444

    print("test_basic_library_usage PASSED")


def test_dm1_library_usage(tmp_path):
    print("Running test_dm1_library_usage...")
    # DM1 uses hardcoded logic but resolves SPN names from DB
    db = {
        "J1939SATabledb": {"0": "Engine #1"},
        "J1939PGNdb": {},
        "J1939SPNdb": {"1234": {"Name": "Test SPN 1234"}},
        "J1939BitDecodings": {},
    }
    db_path = tmp_path / "J1939db.json"
    db_path.write_text(json.dumps(db))

    describe = pretty_j1939.describe.get_describer(da_json=str(db_path))

    # DM1 message
    message_id = bitstring.Bits(hex="18FECA00")
    message_data = bitstring.Bits(hex="00FFD2040381FFFF")
    description = describe(message_data, message_id.uint)

    print(f"Description: {description}")

    assert description["PGN"] == "DM1(65226)"
    assert "DTC 1" in description
    assert "SPN 1234" in description["DTC 1"]
    assert "(CM=1, J1587)" in description["DTC 1"]

    print("test_dm1_library_usage PASSED")


def test_fallback_library_usage():
    print("Running test_fallback_library_usage...")
    describe_obj = pretty_j1939.describe.get_describer()
    print(f"Using DA JSON: {describe_obj.da_describer.da_json}")
    assert describe_obj.da_describer.da_json is not None
    print("test_fallback_library_usage PASSED")


def test_bytes_input_usage():
    """Verify that the describer accepts bytes directly."""
    describer = pretty_j1939.describe.get_describer()
    # EEC1 from SA 0
    can_id = 0x0CF00400
    can_data = b"\x00\x41\xff\x20\x48\x14\x00\xf0"

    description = describer(can_data, can_id)
    assert description["PGN"] == "EEC1(61444)"
    assert description["SA"] == "Engine #1(  0)"


def test_renderer_usage():
    """Verify renderer initialization and usage as shown in README."""
    import pretty_j1939.render

    describer = pretty_j1939.describe.get_describer()

    # Initialize renderer with theme and describer for label resolution
    theme = pretty_j1939.render.HighPerformanceRenderer.load_theme("darcula")
    renderer = pretty_j1939.render.HighPerformanceRenderer(
        theme_dict=theme, color_system="truecolor", da_describer=describer.da_describer
    )

    can_id = 0x0CF00400
    can_data = b"\x00\x41\xff\x20\x48\x14\x00\xf0"

    description = describer(can_data, can_id)
    output = renderer.render(description, indent=True)

    # Verify output contains expected content
    assert "EEC1" in output
    assert "Engine #1" in output


def test_j1939_tp_reassembly_usage():
    """Verify J1939-TP BAM reassembly example."""
    describer = pretty_j1939.describe.get_describer()

    # Connection Management (BAM) - PGN 61444 (EEC1), 14 bytes, 2 packets
    # PGN 61444 is 0x00F004. In BAM CM (bytes 5,6,7): 04 F0 00
    describer(b"\x20\x0e\x00\x02\xff\x04\xf0\x00", 0x18ECFF00)
    # Data Transfer Packet 1
    describer(b"\x01\x01\x02\x03\x04\x05\x06\x07", 0x18EBFF00)
    # Data Transfer Packet 2 (Final)
    res = describer(b"\x02\x08\x09\x0a\x0b\x0c\x0d\x0e", 0x18EBFF00)

    assert res is not None
    assert res["PGN"] == "EEC1(61444)"
    assert res["_pgn"] == 61444


def test_summary_generation_usage():
    """Verify network summary generation as shown in README."""
    import pretty_j1939.render

    describer = pretty_j1939.describe.get_describer()
    # Pass da_describer to renderer to get labels in summary
    renderer = pretty_j1939.render.HighPerformanceRenderer(
        da_describer=describer.da_describer
    )

    # Feed some data (EEC1 from SA 0)
    describer(b"\x00\x41\xff\x20\x48\x14\x00\xf0", 0x0CF00400)

    summary_data = describer.get_summary()
    assert (0, 255) in summary_data

    summary_output = renderer.render_summary(summary_data, indent=True)
    assert "graph LR" in summary_output
    assert "EEC1" in summary_output
