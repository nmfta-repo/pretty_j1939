import pytest
import bitstring
from pretty_j1939.core.describe import get_describer


def run_vector_test(length, start_bit, vector_str):
    # vector_str is CANID#CANPAYLOAD, e.g. "18FF0021#0200000000000000"
    id_str, payload_hex = vector_str.split("#")
    can_id = int(id_str, 16)
    payload = bytes.fromhex(payload_hex)

    # Extract PGN from CAN ID
    pf = (can_id >> 16) & 0xFF
    ps = (can_id >> 8) & 0xFF
    dp = (can_id >> 24) & 0x01
    edp = (can_id >> 25) & 0x01

    if pf < 240:  # PDU1
        pgn_id = (edp << 17) | (dp << 16) | (pf << 8)
    else:  # PDU2
        pgn_id = (edp << 17) | (dp << 16) | (pf << 8) | ps

    spn_id = 9999
    db = {
        "J1939PGNdb": {
            str(pgn_id): {
                "Label": "VEC_PGN",
                "Name": "Vector PGN",
                "PGNLength": "8",
                "SPNs": [spn_id],
                "SPNStartBits": [[start_bit]],
            }
        },
        "J1939SPNdb": {
            str(spn_id): {
                "Name": "Vector SPN",
                "Units": "bit",
                "SPNLength": length,
                "Resolution": 1.0,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": (
                    (1 << length) - 5
                    if isinstance(length, int) and length < 64
                    else 1e18
                ),
            }
        },
        "J1939SATabledb": {"33": "Body Controller"},
        "J1939BitDecodings": {},
    }

    describer = get_describer(da_json=db, include_na=True)
    description = describer(payload, can_id)

    return description.get("Vector SPN")


@pytest.mark.parametrize(
    "length, start_bit, vector_str, expected",
    [
        (2, 0, "18FF0021#0200000000000000", "Error"),
        (2, 0, "18FF0021#0300000000000000", "N/A"),
        (4, 4, "18FF0021#E000000000000000", "Error"),
        (4, 4, "18FF0021#F000000000000000", "N/A"),
        (5, 0, "18FF0021#1E00000000000000", "Error"),
        (5, 0, "18FF0021#1F00000000000000", "N/A"),
        (7, 0, "18FF0021#7E00000000000000", "Error"),
        (7, 0, "18FF0021#7F00000000000000", "N/A"),
        (8, 8, "18FF0021#00FB000000000000", "Parameter specific"),
        (8, 8, "18FF0021#00FC000000000000", "Reserved"),
        (8, 8, "18FF0021#00FD000000000000", "Reserved"),
        (8, 8, "18FF0021#00FE000000000000", "Error"),
        (8, 8, "18FF0021#00FF000000000000", "N/A"),
        (16, 16, "18FF0021#000000FB00000000", "Parameter specific"),
        (16, 16, "18FF0021#0000FFFB00000000", "Parameter specific"),
        (16, 16, "18FF0021#000000FC00000000", "Reserved"),
        (16, 16, "18FF0021#0000FFFD00000000", "Reserved"),
        (16, 16, "18FF0021#000000FE00000000", "Error"),
        (16, 16, "18FF0021#0000FFFE00000000", "Error"),
        (16, 16, "18FF0021#000000FF00000000", "N/A"),
        (16, 16, "18FF0021#0000FFFF00000000", "N/A"),
        # Corrected 32-bit hex strings for Byte 5-8 (start bit 32)
        (32, 32, "18FF0021#00000000000000FB", "Parameter specific"),
        (32, 32, "18FF0021#00000000FFFFFFFB", "Parameter specific"),
        (32, 32, "18FF0021#00000000000000FC", "Reserved"),
        (32, 32, "18FF0021#00000000FFFFFFFD", "Reserved"),
        (32, 32, "18FF0021#00000000000000FE", "Error"),
        (32, 32, "18FF0021#00000000FFFFFFFE", "Error"),
        (32, 32, "18FF0021#00000000000000FF", "N/A"),
        (32, 32, "18FF0021#00000000FFFFFFFF", "N/A"),
    ],
)
def test_vector_indicators(length, start_bit, vector_str, expected):
    actual = run_vector_test(length, start_bit, vector_str)
    assert actual == expected
