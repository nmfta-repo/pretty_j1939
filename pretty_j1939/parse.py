#
# Copyright (c) 2019 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

DA_MASK = 0x0000FF00
SA_MASK = 0x000000FF
PF_MASK = 0x00FF0000
DP_MASK = 0x01000000
EDP_MASK = 0x02000000
TM_MASK = 0x00EB0000
CM_MASK = 0x00EC0000
ACK_MASK = 0x0E80000


def parse_j1939_id(can_id):
    sa = SA_MASK & can_id
    pf = (can_id >> 16) & 0xFF
    ps = (can_id >> 8) & 0xFF
    dp = (can_id >> 24) & 1
    edp = (can_id >> 25) & 1

    if pf < 240:  # PDU1 format
        pgn = (edp << 17) | (dp << 16) | (pf << 8)
        da = ps
    else:  # PDU2 format
        pgn = (edp << 17) | (dp << 16) | (pf << 8) | ps
        da = 0xFF
    return pgn, da, sa


def is_connection_management_message(message_id):
    return (message_id & PF_MASK) == CM_MASK


def is_connection_management_pgn(pgn):
    return pgn == CM_MASK >> 8


def is_data_transfer_message(message_id):
    return (message_id & PF_MASK) == TM_MASK


def is_data_transfer_pgn(pgn):
    return pgn == TM_MASK >> 8


def is_ack_message(message_id):
    return (message_id & PF_MASK) == ACK_MASK


def is_ack_pgn(pgn):
    return pgn == ACK_MASK >> 8


def is_transport_message(message_id):
    return (
        is_data_transfer_message(message_id)
        or is_connection_management_message(message_id)
        or is_ack_message(message_id)
    )


def is_transport_pgn(pgn):
    return (
        is_data_transfer_pgn(pgn)
        or is_connection_management_pgn(pgn)
        or is_ack_pgn(pgn)
    )


def is_bam_rts_cts_message(message_bytes):
    return message_bytes[0] == 32 or message_bytes[0] == 16


def is_spn_bitencoded(spn_units):
    return spn_units.lower() in (
        "bit",
        "binary",
    )


def is_spn_numerical_values(spn_units):
    norm_units = spn_units.lower()
    return norm_units not in (
        "manufacturer determined",
        "byte",
        "",
        "request dependent",
        "ascii",
    )
