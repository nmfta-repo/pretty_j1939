#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
import pytest
import bitstring
from pretty_j1939.describe import get_describer, decode_j1939_name


def test_name_decoding_backward_compatibility():
    """Verify that name decoding works with both new (dependent) and old (independent) vehicle system schemas."""
    mock_db = {
        "J1939Manufacturerdb": {"123": "Test Mfr"},
        "J1939IndustryGroupdb": {"1": "On-Highway Equipment"},
        "J1939Functiondb": {"1": "Engine"},
        "J1939VehicleSystemdb": {
            "1_1": "Tractor",  # New schema (dependent: {ig}_{vs})
            "2": "Trailer",  # Old schema (independent: {vs})
        },
        "J1939PGNdb": {},
        "J1939SPNdb": {},
        "J1939SATabledb": {},
        "J1939BitDecodings": {},
    }

    # 1. Test Dependent Lookup (New Schema)
    # IG: bits 60-62 = 1, VS: bits 49-55 = 1
    name_val_dep = (1 << 60) | (1 << 49)
    payload_dep = name_val_dep.to_bytes(8, byteorder="little")

    decoded_dep = decode_j1939_name(
        payload_dep,
        industry_db=mock_db["J1939IndustryGroupdb"],
        vehicle_db=mock_db["J1939VehicleSystemdb"],
    )
    assert decoded_dep["Industry Group"] == "1 (On-Highway Equipment)"
    assert decoded_dep["Vehicle System"] == "1 (Tractor)"

    # 2. Test Independent Fallback (Old Schema)
    # IG: bits 60-62 = 1, VS: bits 49-55 = 2
    name_val_indep = (1 << 60) | (2 << 49)
    payload_indep = name_val_indep.to_bytes(8, byteorder="little")

    decoded_indep = decode_j1939_name(
        payload_indep,
        industry_db=mock_db["J1939IndustryGroupdb"],
        vehicle_db=mock_db["J1939VehicleSystemdb"],
    )
    assert decoded_indep["Industry Group"] == "1 (On-Highway Equipment)"
    assert decoded_indep["Vehicle System"] == "2 (Trailer)"

    # 3. Test Unknown (Graceful Failure)
    # IG: bits 60-62 = 1, VS: bits 49-55 = 3
    name_val_unk = (1 << 60) | (3 << 49)
    payload_unk = name_val_unk.to_bytes(8, byteorder="little")

    decoded_unk = decode_j1939_name(
        payload_unk,
        industry_db=mock_db["J1939IndustryGroupdb"],
        vehicle_db=mock_db["J1939VehicleSystemdb"],
    )
    assert "Unknown Vehicle System 3" in decoded_unk["Vehicle System"]


def test_describer_with_old_schema_db():
    """Verify the J1939Describer still works with a database using the old independent schema."""
    old_db = {
        "J1939IndustryGroupdb": {"1": "On-Highway"},
        "J1939VehicleSystemdb": {"1": "Tractor (Independent)"},
        "J1939Manufacturerdb": {},
        "J1939Functiondb": {},
        "J1939PGNdb": {},
        "J1939SPNdb": {},
        "J1939SATabledb": {},
        "J1939BitDecodings": {},
    }

    describer = get_describer(da_json=old_db)
    # Address Claimed PGN 60928, SA 0x80
    # NAME: IG=1, VS=1
    message_id = 0x18EEFF80
    message_data = bitstring.Bits(
        hex="0000000000002210"
    )  # IG=1 (0x1), VS=1 (0x22 >> 1 = 0x11? no)
    # bits 49-55 is VS.
    # Let's construct a cleaner payload
    name_val = (1 << 60) | (1 << 49)
    message_data = bitstring.Bits(uint=name_val, length=64)
    # wait, bitstring.Bits(uint=...) is big-endian by default in terms of how it packs.
    # J1939 is little-endian.
    message_data = bitstring.Bits(bytes=name_val.to_bytes(8, byteorder="little"))

    description = describer(message_data, message_id)
    assert "Tractor (Independent)" in description["Vehicle System"]
