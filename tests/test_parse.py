import pytest
from pretty_j1939.parse import parse_j1939_id, is_bam_rts_cts_message


def test_parse_j1939_id_pdu1():
    # PGN 0xEF00 (61184), DA 0x33, SA 0x05, Priority 6 (0x18...)
    can_id = 0x18EF3305
    pgn, da, sa = parse_j1939_id(can_id)
    assert pgn == 61184
    assert da == 0x33
    assert sa == 0x05


def test_parse_j1939_id_pdu2():
    # PGN 0xFF00 (65280), SA 0x21, Priority 6 (0x18...)
    can_id = 0x18FF0021
    pgn, da, sa = parse_j1939_id(can_id)
    assert pgn == 65280
    assert da == 0xFF
    assert sa == 0x21


def test_is_bam_rts_cts_message():
    # BAM (0x20 = 32)
    assert is_bam_rts_cts_message([32, 0, 0, 0, 0, 0, 0, 0]) is True
    # RTS (0x10 = 16)
    assert is_bam_rts_cts_message([16, 0, 0, 0, 0, 0, 0, 0]) is True
    # CTS (0x11 = 17)
    assert is_bam_rts_cts_message([17, 0, 0, 0, 0, 0, 0, 0]) is True
    # EOM (0x13 = 19)
    assert is_bam_rts_cts_message([19, 0, 0, 0, 0, 0, 0, 0]) is True
    # Abort (0xFF = 255)
    assert is_bam_rts_cts_message([255, 0, 0, 0, 0, 0, 0, 0]) is True

    # Non-TP control bytes
    assert is_bam_rts_cts_message([0, 0, 0, 0, 0, 0, 0, 0]) is False
    assert is_bam_rts_cts_message([1, 0, 0, 0, 0, 0, 0, 0]) is False


def test_is_spn_numerical_values():
    from pretty_j1939.parse import is_spn_numerical_values

    assert is_spn_numerical_values("rpm") is True
    assert is_spn_numerical_values("km/h") is True
    assert is_spn_numerical_values("ASCII") is False
    assert is_spn_numerical_values("Byte") is False
    assert is_spn_numerical_values("") is False
    assert is_spn_numerical_values(None) is False
