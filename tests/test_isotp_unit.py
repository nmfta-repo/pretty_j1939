import pytest
from pretty_j1939.isotp import IsoTpTracker


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


def test_isotp_reassembly_large_pdu_32bit_length():
    tracker = IsoTpTracker(real_time=False)
    found_data = []

    def on_found(data, sa, pgn, is_last_packet):
        if is_last_packet:
            found_data.append(data)

    # 5000 bytes needs 32-bit length (0x1388)
    pdu = bytes([i % 256 for i in range(5000)])

    # FF: 10 00 00 00 13 88 + first 2 bytes of data
    ff = b"\x10\x00\x00\x00\x13\x88" + pdu[0:2]
    tracker.process(on_found, ff, 0x18DAF100)

    # CFs: 5000 - 2 = 4998 bytes. 4998 / 7 = 714 frames.
    for i in range(1, 715):
        start = 2 + (i - 1) * 7
        end = start + 7
        tracker.process(
            on_found, bytes([0x20 | (i & 0x0F)]) + pdu[start:end], 0x18DAF100
        )

    assert len(found_data) == 1
    assert found_data[0] == pdu


def test_isotp_sf_canfd_length():
    tracker = IsoTpTracker(real_time=False)
    found_data = []

    def on_found(data, sa, pgn, is_last_packet):
        if is_last_packet:
            found_data.append(data)

    # SF: 00 0A + 10 bytes (CAN FD style)
    pdu = b"0123456789"
    sf = b"\x00\x0a" + pdu
    tracker.process(on_found, sf, 0x18DAF100)

    assert len(found_data) == 1
    assert found_data[0] == pdu
