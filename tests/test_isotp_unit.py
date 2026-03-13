import pytest
from pretty_j1939.core.isotp import IsoTpTracker


def test_isotp_reassembly_58_bytes():
    tracker = IsoTpTracker(real_time=False)
    found_data = []

    def on_found(data, sa, pgn, is_last_packet):
        if is_last_packet:
            found_data.append(data)

    # FF: 10 3A + first 6 bytes (58 bytes = 0x3A)
    pdu = bytes(range(58))
    tracker.process(on_found, b"\x10\x3a" + pdu[0:6], 0x18DAF100)

    # CF1-CF7: 7 bytes each
    for i in range(1, 8):
        tracker.process(
            on_found,
            bytes([0x20 | (i & 0x0F)]) + pdu[6 + (i - 1) * 7 : 6 + i * 7],
            0x18DAF100,
        )

    # CF8: last 3 bytes
    tracker.process(on_found, b"\x28" + pdu[55:58], 0x18DAF100)

    assert len(found_data) == 1
    assert found_data[0] == pdu


def test_isotp_reassembly_large_pdu_standard():
    tracker = IsoTpTracker(real_time=False)
    found_data = []

    def on_found(data, sa, pgn, is_last_packet):
        if is_last_packet:
            found_data.append(data)

    # 1000 bytes fits in 12-bit length (0x03E8)
    length = 1000
    pdu = bytes([i % 256 for i in range(length)])

    # FF: 13 E8 + first 6 bytes
    ff = b"\x13\xe8" + pdu[0:6]
    tracker.process(on_found, ff, 0x18DAF100)

    # Remaining 994 bytes in CFs. 994 / 7 = 142 frames.
    for i in range(1, 143):
        start = 6 + (i - 1) * 7
        end = min(start + 7, length)
        tracker.process(
            on_found, bytes([0x20 | (i & 0x0F)]) + pdu[start:end], 0x18DAF100
        )

    assert len(found_data) == 1
    assert found_data[0] == pdu


def test_isotp_sf_standard():
    tracker = IsoTpTracker(real_time=False)
    found_data = []

    def on_found(data, sa, pgn, is_last_packet):
        if is_last_packet:
            found_data.append(data)

    # SF: 07 + 7 bytes (Standard CAN 2.0B)
    pdu = b"1234567"
    sf = b"\x07" + pdu
    tracker.process(on_found, sf, 0x18DAF100)

    assert len(found_data) == 1
    assert found_data[0] == pdu
