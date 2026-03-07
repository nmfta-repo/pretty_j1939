import pytest
from pretty_j1939.describe import get_describer


def run_decode_test(length, start_bit, payload_hex):
    # Create in-memory DB for this specific SPN
    spn_id = 9999
    pgn_id = 61184  # PropA (0xEF00) - PDU1

    da_json = {
        "J1939PGNdb": {
            str(pgn_id): {
                "Label": "TEST",
                "Name": "Test PGN",
                "PGNLength": "8",
                "SPNs": [spn_id],
                "SPNStartBits": [[start_bit]],
            }
        },
        "J1939SPNdb": {
            str(spn_id): {
                "Name": "Test SPN",
                "Units": "bit",  # Force numerical path
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
    }

    describer = get_describer(da_json=da_json, include_na=True)

    # CAN ID for PropA (0xEF00), SA 0x05, DA 0x33, Priority 6
    # 0x18EF3305
    can_id = 0x18EF3305

    payload = bytes.fromhex(payload_hex)
    description = describer(payload, can_id)

    return description.get("Test SPN")


@pytest.mark.parametrize(
    "length, start_bit, payload_hex, expected",
    [
        # 2 bits (Byte 1, bits 0-1)
        (2, 0, "0200000000000000", "Error"),
        (2, 0, "0300000000000000", "N/A"),
        # 4 bits (Byte 1, bits 4-7)
        (4, 4, "E000000000000000", "Error"),
        (4, 4, "F000000000000000", "N/A"),
        # 5 bits (Byte 1, bits 0-4)
        (5, 0, "1E00000000000000", "Error"),
        (5, 0, "1F00000000000000", "N/A"),
        # 7 bits (Byte 1, bits 0-6)
        (7, 0, "7E00000000000000", "Error"),
        (7, 0, "7F00000000000000", "N/A"),
        # 8 bits (Byte 2)
        (8, 8, "00FB000000000000", "Parameter specific"),
        (8, 8, "00FC000000000000", "Reserved"),
        (8, 8, "00FD000000000000", "Reserved"),
        (8, 8, "00FE000000000000", "Error"),
        (8, 8, "00FF000000000000", "N/A"),
        # 16 bits (Bytes 3-4, Intel order)
        (16, 16, "000000FB00000000", "Parameter specific"),  # 0xFB00
        (16, 16, "0000FFFB00000000", "Parameter specific"),  # 0xFBFF
        (16, 16, "000000FC00000000", "Reserved"),  # 0xFC00
        (16, 16, "0000FFFD00000000", "Reserved"),  # 0xFDFF
        (16, 16, "000000FE00000000", "Error"),  # 0xFE00
        (16, 16, "0000FFFE00000000", "Error"),  # 0xFEFF
        (16, 16, "000000FF00000000", "N/A"),  # 0xFF00
        (16, 16, "0000FFFF00000000", "N/A"),  # 0xFFFF
        # 32 bits (Bytes 5-8, Intel order)
        (32, 32, "00000000000000FB", "Parameter specific"),  # 0xFB000000
        (32, 32, "00000000FFFFFFFB", "Parameter specific"),  # 0xFBFFFFFF
        (32, 32, "00000000000000FC", "Reserved"),  # 0xFC000000
        (32, 32, "00000000FFFFFFFD", "Reserved"),  # 0xFDFFFFFF
        (32, 32, "00000000000000FE", "Error"),  # 0xFE000000
        (32, 32, "00000000FFFFFFFE", "Error"),  # 0xFEFFFFFF
        (32, 32, "00000000000000FF", "N/A"),  # 0xFF000000
        (32, 32, "00000000FFFFFFFF", "N/A"),  # 0xFFFFFFFF
    ],
)
def test_comprehensive_indicators(length, start_bit, payload_hex, expected):
    actual = run_decode_test(length, start_bit, payload_hex)
    assert actual == expected


def test_64bit_ignores_indicators():
    # 64-bit field should NOT treat special values as indicators
    payload_all_ff = "FFFFFFFFFFFFFFFF"
    res = run_decode_test(64, 0, payload_all_ff)
    assert res == "18446744073709551615 (Unknown)"
