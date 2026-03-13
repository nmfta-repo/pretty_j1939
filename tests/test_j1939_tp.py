import pytest
from pretty_j1939.core.describe import J1939TransportTracker


def test_j1939_tp_bam_reassembly():
    """Verify BAM reassembly (PGN 65226 / DM1, 10 bytes)."""
    tracker = J1939TransportTracker(real_time=False)
    results = []

    def processor(data, sa, pgn, **kwargs):
        results.append((data, sa, pgn))

    # TP.CM BAM (Control=32, Length=10, Packets=2, PGN=65226)
    # 65226 is 0xFECA. Byte 5=0xCA, Byte 6=0xFE, Byte 7=0x00.
    cm_bam = bytes([32, 10, 0, 2, 255, 0xCA, 0xFE, 0])
    tracker.process(processor, cm_bam, 0x18ECFF00)  # DA=255, SA=0

    # TP.DT Packet 1 (Seq=1, Data=01 02 03 04 05 06 07)
    dt1 = bytes([1, 1, 2, 3, 4, 5, 6, 7])
    tracker.process(processor, dt1, 0x18EBFF00)
    assert len(results) == 0

    # TP.DT Packet 2 (Seq=2, Data=08 09 0A FF FF FF FF)
    dt2 = bytes([2, 8, 9, 10, 255, 255, 255, 255])
    tracker.process(processor, dt2, 0x18EBFF00)

    assert len(results) == 1
    data, sa, pgn = results[0]
    assert sa == 0
    assert pgn == 65226
    assert data == bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])


def test_j1939_tp_rts_cts_reassembly():
    """Verify RTS/CTS reassembly (PGN 65226, 10 bytes)."""
    tracker = J1939TransportTracker(real_time=False)
    results = []

    def processor(data, sa, pgn, **kwargs):
        results.append((data, sa, pgn))

    # TP.CM RTS (Control=16, Length=10, Packets=2, PGN=65226)
    # DA=1 (Engine), SA=0
    cm_rts = bytes([16, 10, 0, 2, 255, 0xCA, 0xFE, 0])
    tracker.process(processor, cm_rts, 0x18EC0100)

    # TP.DT Packet 1
    dt1 = bytes([1, 1, 2, 3, 4, 5, 6, 7])
    tracker.process(processor, dt1, 0x18EB0100)

    # TP.DT Packet 2
    dt2 = bytes([2, 8, 9, 10, 255, 255, 255, 255])
    tracker.process(processor, dt2, 0x18EB0100)

    # In RTS/CTS, it should NOT be finished yet (waiting for EOM)
    assert len(results) == 0

    # TP.CM EOM (Control=19, Length=10, Packets=2, PGN=65226)
    cm_eom = bytes([19, 10, 0, 2, 255, 0xCA, 0xFE, 0])
    tracker.process(processor, cm_eom, 0x18EC0100)

    assert len(results) == 1
    data, sa, pgn = results[0]
    assert data == bytes([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])


def test_j1939_tp_abort():
    """Verify session is cleared on Abort."""
    tracker = J1939TransportTracker(real_time=False)
    results = []

    def processor(data, sa, pgn, **kwargs):
        results.append((data, sa, pgn))

    cm_rts = bytes([16, 10, 0, 2, 255, 0xCA, 0xFE, 0])
    tracker.process(processor, cm_rts, 0x18EC0100)

    # Abort
    cm_abort = bytes([255, 255, 255, 255, 255, 0xCA, 0xFE, 0])
    tracker.process(processor, cm_abort, 0x18EC0100)

    # Send DT (should be ignored as session is gone)
    dt1 = bytes([1, 1, 2, 3, 4, 5, 6, 7])
    tracker.process(processor, dt1, 0x18EB0100)

    assert len(results) == 0
    assert (1, 0) not in tracker.sessions


def test_j1939_tp_vin_bam():
    """Verify BAM reassembly of a 17-byte VIN (PGN 65259)."""
    tracker = J1939TransportTracker(real_time=False)
    results = []

    def processor(data, sa, pgn, **kwargs):
        results.append((data, sa, pgn))

    vin_str = "12345678901234567"
    vin_bytes = vin_str.encode("ascii")

    # TP.CM BAM (Control=32, Length=17, Packets=3, PGN=65259 / 0xFEEB)
    cm_bam = bytes([32, 17, 0, 3, 255, 0xEB, 0xFE, 0])
    tracker.process(processor, cm_bam, 0x18ECFF00)

    # DT 1
    tracker.process(processor, bytes([1]) + vin_bytes[0:7], 0x18EBFF00)
    # DT 2
    tracker.process(processor, bytes([2]) + vin_bytes[7:14], 0x18EBFF00)
    # DT 3
    tracker.process(
        processor, bytes([3]) + vin_bytes[14:17] + b"\xff\xff\xff\xff", 0x18EBFF00
    )

    assert len(results) == 1
    data, sa, pgn = results[0]
    assert pgn == 65259
    assert data == vin_bytes


def test_j1939_tp_commanded_address():
    """Verify reassembly of Commanded Address (PGN 65240, 9 bytes)."""
    tracker = J1939TransportTracker(real_time=False)
    results = []

    def processor(data, sa, pgn, **kwargs):
        results.append((data, sa, pgn))

    # NAME (8 bytes) + New Address (1 byte)
    ca_payload = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x30])

    # TP.CM BAM (Control=32, Length=9, Packets=2, PGN=65240 / 0xFED8)
    cm_bam = bytes([32, 9, 0, 2, 255, 0xD8, 0xFE, 0])
    tracker.process(processor, cm_bam, 0x18ECFF00)

    # DT 1
    tracker.process(processor, bytes([1]) + ca_payload[0:7], 0x18EBFF00)
    # DT 2
    tracker.process(
        processor, bytes([2]) + ca_payload[7:9] + b"\xff\xff\xff\xff\xff", 0x18EBFF00
    )

    assert len(results) == 1
    data, sa, pgn = results[0]
    assert pgn == 65240
    assert data == ca_payload
