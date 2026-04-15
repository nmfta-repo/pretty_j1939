"""Tests for J1939Scanner (parse.py) and priority-range support in describe.py."""

import pytest
import bitstring

from pretty_j1939.parse import J1939Scanner, DEFAULT_PRIORITY, CM_MASK, REQUEST_PGN
from pretty_j1939.describe import J1939Filter, get_describer


# ---------------------------------------------------------------------------
# J1939Scanner – default priority
# ---------------------------------------------------------------------------


def test_scanner_default_priority_is_6():
    """The default priority for all scanner methods must be 6."""
    scanner = J1939Scanner(sa=0x0B)
    assert scanner.priority == DEFAULT_PRIORITY
    assert scanner.priority == 6


def test_scanner_default_priority_explicit():
    """Explicitly passing priority=6 matches the default."""
    scanner = J1939Scanner(sa=0x0B, priority=6)
    assert scanner.priority == 6


def test_scanner_priorities_single_int():
    """A single int priority wraps into a one-element list."""
    scanner = J1939Scanner(sa=0x0B, priority=3)
    assert scanner.priorities == [3]
    assert scanner.priority == 3


def test_scanner_priorities_list():
    """A list of priorities is stored as-is."""
    scanner = J1939Scanner(sa=0x0B, priorities=[3, 4, 5, 6])
    assert scanner.priorities == [3, 4, 5, 6]
    assert scanner.priority == 3


def test_scanner_priorities_range():
    """A range() is converted to a list."""
    scanner = J1939Scanner(sa=0x0B, priorities=range(3, 7))
    assert scanner.priorities == [3, 4, 5, 6]


# ---------------------------------------------------------------------------
# J1939Scanner.build_can_id
# ---------------------------------------------------------------------------


def test_build_can_id_pdu2_priority_6():
    """PDU2 PGN (PF >= 240) with default priority 6."""
    scanner = J1939Scanner(sa=0x00)
    # PGN 0xF004 = EEC1, PF = 0xF0 (>= 240) → PDU2 (broadcast)
    can_id = scanner.build_can_id(0xF004)
    assert (can_id >> 26) & 0x7 == 6
    assert can_id == 0x18F00400


def test_build_can_id_pdu1_priority_6():
    """PDU1 PGN (PF < 240) with default priority 6 and explicit DA."""
    scanner = J1939Scanner(sa=0x0B)
    # PGN 0xEA00 = Request, PF = 0xEA = 234 (< 240) → PDU1
    can_id = scanner.build_can_id(0xEA00, da=0xFF)
    assert (can_id >> 26) & 0x7 == 6
    assert (can_id >> 8) & 0xFF == 0xFF  # DA byte
    assert can_id & 0xFF == 0x0B         # SA byte


def test_build_can_id_priority_override():
    """Per-call priority override works independently of scanner default."""
    scanner = J1939Scanner(sa=0x00)
    can_id_p3 = scanner.build_can_id(0xF004, priority=3)
    assert (can_id_p3 >> 26) & 0x7 == 3
    can_id_p6 = scanner.build_can_id(0xF004)
    assert (can_id_p6 >> 26) & 0x7 == 6


# ---------------------------------------------------------------------------
# J1939Scanner.request
# ---------------------------------------------------------------------------


def test_request_method_default_priority_6():
    """request() uses priority 6 by default."""
    scanner = J1939Scanner(sa=0x0B)
    can_id = scanner.request(0xFECA, da=0xFF)
    assert (can_id >> 26) & 0x7 == 6
    # PGN field: 0xEA00 << 8 → bits 23-8
    assert (can_id >> 8) & 0xFFFF == (REQUEST_PGN | 0xFF)


def test_request_method_priority_override():
    """request() priority can be overridden per call."""
    scanner = J1939Scanner(sa=0x0B)
    can_id = scanner.request(0xFECA, da=0xFF, priority=3)
    assert (can_id >> 26) & 0x7 == 3


# ---------------------------------------------------------------------------
# J1939Scanner.rts – previously used priority 7, now defaults to 6
# ---------------------------------------------------------------------------


def test_rts_default_priority_is_6():
    """rts() must default to priority 6 (not the J1939-standard 7)."""
    scanner = J1939Scanner(sa=0x0B)
    can_id = scanner.rts(pgn=0xFECA, da=0x01)
    priority = (can_id >> 26) & 0x7
    assert priority == 6, (
        f"rts() priority should be 6 (got {priority}). "
        "The J1939 standard TP priority 7 must not be hard-coded."
    )


def test_rts_priority_override_to_7():
    """rts() accepts an explicit priority=7 for standard J1939 TP usage."""
    scanner = J1939Scanner(sa=0x0B)
    can_id = scanner.rts(pgn=0xFECA, da=0x01, priority=7)
    assert (can_id >> 26) & 0x7 == 7


def test_rts_sa_and_da_encoded():
    """rts() encodes SA and DA correctly in the CAN ID."""
    scanner = J1939Scanner(sa=0x0B)
    da = 0x01
    can_id = scanner.rts(pgn=0xFECA, da=da)
    # PGN 0xEC00 (CM_MASK bits 23-16)
    assert (can_id >> 16) & 0xFF == 0xEC
    assert (can_id >> 8) & 0xFF == da
    assert can_id & 0xFF == 0x0B


def test_rts_scanner_with_priority_7_default():
    """A scanner with priority=7 produces rts() CAN IDs with priority 7."""
    scanner_p7 = J1939Scanner(sa=0x0B, priority=7)
    can_id = scanner_p7.rts(pgn=0xFECA, da=0x01)
    assert (can_id >> 26) & 0x7 == 7


# ---------------------------------------------------------------------------
# J1939Scanner.scan_can_ids – range of priorities
# ---------------------------------------------------------------------------


def test_scan_can_ids_default_single_priority():
    """scan_can_ids with a single default priority yields one ID per PGN."""
    scanner = J1939Scanner(sa=0x0B)
    ids = list(scanner.scan_can_ids([0xFECA]))
    assert len(ids) == 1
    assert (ids[0] >> 26) & 0x7 == 6


def test_scan_can_ids_range_of_priorities():
    """scan_can_ids with priorities range yields one ID per (priority, pgn)."""
    scanner = J1939Scanner(sa=0x0B, priorities=range(3, 7))
    pgns = [0xFECA, 0xF004]
    ids = list(scanner.scan_can_ids(pgns))
    assert len(ids) == 4 * 2  # 4 priorities × 2 PGNs
    priorities_seen = {(can_id >> 26) & 0x7 for can_id in ids}
    assert priorities_seen == {3, 4, 5, 6}


def test_scan_can_ids_list_of_priorities():
    """scan_can_ids with explicit priorities=[6, 7]."""
    scanner = J1939Scanner(sa=0x0B, priorities=[6, 7])
    ids = list(scanner.scan_can_ids([0xFECA]))
    assert len(ids) == 2
    assert {(i >> 26) & 0x7 for i in ids} == {6, 7}


# ---------------------------------------------------------------------------
# J1939Filter – priority support in generate_can_filters
# ---------------------------------------------------------------------------


def _make_filter(describer, pgn_list, priorities=None):
    j1939f = J1939Filter(describer.da_describer, pgn_list=pgn_list, priorities=priorities)
    return j1939f.generate_can_filters()


def test_filter_no_priority_no_priority_bits():
    """Without priorities, generated filters have no priority bits in mask."""
    describer = get_describer()
    filters = _make_filter(describer, pgn_list=["65226"])
    PRIORITY_FIELD_MASK = 0x1C000000
    for f in filters:
        assert (f["can_mask"] & PRIORITY_FIELD_MASK) == 0, (
            f"Filter {f} unexpectedly includes priority bits when priorities=None"
        )


def test_filter_priority_6_only():
    """priorities=[6] generates filters with priority-6 bits in can_id/mask."""
    describer = get_describer()
    filters = _make_filter(describer, pgn_list=["65226"], priorities=[6])
    PRIORITY_FIELD_MASK = 0x1C000000
    for f in filters:
        assert (f["can_mask"] & PRIORITY_FIELD_MASK) == PRIORITY_FIELD_MASK, (
            f"Filter {f} is missing priority mask bits for priorities=[6]"
        )
        assert (f["can_id"] >> 26) & 0x7 == 6


def test_filter_priority_range_6_7():
    """priorities=[6, 7] doubles the number of filters (one set per priority)."""
    describer = get_describer()
    filters_no_prio = _make_filter(describer, pgn_list=["65226"])
    filters_p67 = _make_filter(describer, pgn_list=["65226"], priorities=[6, 7])
    assert len(filters_p67) == 2 * len(filters_no_prio)
    priorities_in_filters = {(f["can_id"] >> 26) & 0x7 for f in filters_p67}
    assert priorities_in_filters == {6, 7}


def test_filter_rts_uses_configured_priority_not_7():
    """Transport (RTS/BAM/DT) filters use the configured priority, not hard-coded 7."""
    describer = get_describer()
    filters = _make_filter(describer, pgn_list=["65226"], priorities=[6])
    # Transport PGNs: 60416 (0xEC00 CM), 60160 (0xEB00 DT), 59392 (0xE800 ACK)
    tp_pf_values = {0xEC, 0xEB, 0xE8}
    transport_filters = [
        f for f in filters if ((f["can_id"] >> 16) & 0xFF) in tp_pf_values
    ]
    assert transport_filters, "Expected transport PGN filters in the output"
    for f in transport_filters:
        priority = (f["can_id"] >> 26) & 0x7
        assert priority == 6, (
            f"Transport filter {f} has priority {priority}, expected 6"
        )


def test_filter_single_int_priority():
    """priorities can be passed as a single integer."""
    describer = get_describer()
    j1939f = J1939Filter(
        describer.da_describer, pgn_list=["65226"], priorities=6
    )
    filters = j1939f.generate_can_filters()
    for f in filters:
        assert (f["can_id"] >> 26) & 0x7 == 6


# ---------------------------------------------------------------------------
# DADescriber – configurable default_priority in describe_message_id
# ---------------------------------------------------------------------------


def test_describe_default_priority_6_hidden():
    """Priority 6 (default) is NOT included in the message description."""
    describer = get_describer()  # default_priority=6
    # 0x18F00400: priority=6, PGN EEC1
    result = describer(bitstring.Bits(hex="0000000000000000"), 0x18F00400)
    assert "Priority" not in result


def test_describe_non_default_priority_shown():
    """Priority 3 (non-default) IS included in the message description."""
    describer = get_describer()
    # 0x0CF00400: priority=3
    result = describer(bitstring.Bits(hex="0000000000000000"), 0x0CF00400)
    assert result.get("Priority") == "3"


def test_describe_rts_priority_7_shown_with_default_6():
    """Priority 7 (J1939 standard TP) is shown when default_priority=6."""
    describer = get_describer()
    # 0x1CF00400: priority=7
    result = describer(bitstring.Bits(hex="0000000000000000"), 0x1CF00400)
    assert result.get("Priority") == "7"


def test_describe_configurable_default_priority_7():
    """With default_priority=7, priority-7 messages omit the Priority field."""
    describer = get_describer(default_priority=7)
    result = describer(bitstring.Bits(hex="0000000000000000"), 0x1CF00400)
    assert "Priority" not in result
    # Priority 6 with default=7 should appear
    result6 = describer(bitstring.Bits(hex="0000000000000000"), 0x18F00400)
    assert result6.get("Priority") == "6"


def test_describe_default_priority_range():
    """default_priority=[6, 7] suppresses both priority 6 and 7."""
    describer = get_describer(default_priority=[6, 7])
    result6 = describer(bitstring.Bits(hex="0000000000000000"), 0x18F00400)
    result7 = describer(bitstring.Bits(hex="0000000000000000"), 0x1CF00400)
    assert "Priority" not in result6
    assert "Priority" not in result7
    # Priority 3 should still appear
    result3 = describer(bitstring.Bits(hex="0000000000000000"), 0x0CF00400)
    assert result3.get("Priority") == "3"
