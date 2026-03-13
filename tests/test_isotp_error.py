import bitstring
import pytest
from pretty_j1939.describe import get_describer


def test_isotp_out_of_order_sequence():
    """Priority 2: Verify ISO-TP reassembly drops session on out-of-order sequence."""
    describer = get_describer(real_time=False)

    # ISO-TP FF: 10 bytes (0x0A), PDU: 62 00 77 ...
    # ID: 18DAF100 (from SA 0 to DA F1)
    ff = bitstring.Bits(hex="100A620077010203")
    describer(ff, 0x18DAF100)

    # CF with Sequence Number 2 instead of 1
    cf_bad = bitstring.Bits(hex="2204050607000000")
    res = describer(cf_bad, 0x18DAF100)

    # It should not have reassembled successfully
    # Check if PDU hex is in output (it shouldn't be)
    assert "620077" not in str(res)


def test_isotp_invalid_control_byte():
    """Priority 2: Verify ISO-TP reassembly ignores unknown control bytes."""
    describer = get_describer(real_time=False)

    # FF
    ff = bitstring.Bits(hex="100A620077010203")
    describer(ff, 0x18DAF100)

    # Invalid control (0x3X is not standard ISO-TP 15765-2 for CAN 2.0B)
    bad_frame = bitstring.Bits(hex="3000000000000000")
    res = describer(bad_frame, 0x18DAF100)

    assert "620077" not in str(res)


def test_isotp_session_cleanup():
    """Priority 8: Verify ISO-TP session cleanup after successful reassembly."""
    describer = get_describer(real_time=False)

    # Message 1: 10 bytes (FF + CF)
    pdu1_hex = "62007701020304050607"
    describer(bitstring.Bits(hex="100A620077010203"), 0x18DAF100)  # FF
    res1 = describer(bitstring.Bits(hex="2104050607000000"), 0x18DAF100)  # CF
    assert pdu1_hex.upper() in str(res1).upper()

    # Message 2: Fresh start with same IDs
    pdu2_hex = "620088AABBCC"
    # If session wasn't cleaned, this FF might be ignored or seen as out-of-sequence CF
    describer(bitstring.Bits(hex="1006620088AABBCC"), 0x18DAF100)  # Single FF (6 bytes)
    # Since 6 bytes < 7, ISO-TP might treat FF as the whole message if length matches?
    # Actually FF requires CFs if length > payload in FF. 6 bytes fits in FF.
    # Wait, ISO-TP FF is always followed by CFs in many implementations if it's not a SF.
    # Standard ISO-TP: SF (Single Frame) is used for <= 7 bytes.

    # Message 2: Use 8 bytes to force FF+CF
    pdu2_hex = "620088AABBCCDDEE"  # 8 bytes
    describer(bitstring.Bits(hex="1008620088AABBCC"), 0x18DAF100)  # FF (6 bytes)
    res2 = describer(
        bitstring.Bits(hex="21DDEE0000000000"), 0x18DAF100
    )  # CF (remaining 2)

    assert pdu2_hex.upper() in str(res2).upper()
