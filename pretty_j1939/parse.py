#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

DA_MASK = 0x0000FF00
SA_MASK = 0x000000FF
PF_MASK = 0x00FF0000
DP_MASK = 0x01000000
EDP_MASK = 0x02000000
TM_MASK = 0x00EB0000
CM_MASK = 0x00EC0000
ACK_MASK = 0x00E80000
DIAG3_MASK = 0x00DA0000
DIAG3_PGN = 0xDA00


def parse_j1939_id(can_id):
    """Parses a raw CAN ID into J1939 PGN, DA, and SA.
    
        Args:
            can_id (int): The 29-bit CAN ID.
    
        Returns:
            tuple: A tuple containing (pgn, da, sa).
        """
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
    """Checks if a message ID corresponds to Connection Management (CM).
    
        Args:
            message_id (int): The 29-bit message ID.
    
        Returns:
            bool: True if the message is Connection Management, False otherwise.
        """
    return (message_id & PF_MASK) == CM_MASK


def is_connection_management_pgn(pgn):
    """Checks if a PGN corresponds to Connection Management (CM).
    
        Args:
            pgn (int): The Parameter Group Number.
    
        Returns:
            bool: True if the PGN is Connection Management, False otherwise.
        """
    return pgn == CM_MASK >> 8


def is_data_transfer_message(message_id):
    """Checks if a message ID corresponds to Data Transfer (DT).
    
        Args:
            message_id (int): The 29-bit message ID.
    
        Returns:
            bool: True if the message is Data Transfer, False otherwise.
        """
    return (message_id & PF_MASK) == TM_MASK


def is_data_transfer_pgn(pgn):
    """Checks if a PGN corresponds to Data Transfer (DT).
    
        Args:
            pgn (int): The Parameter Group Number.
    
        Returns:
            bool: True if the PGN is Data Transfer, False otherwise.
        """
    return pgn == TM_MASK >> 8


def is_ack_message(message_id):
    """Checks if a message ID corresponds to an Acknowledgement (ACK).
    
        Args:
            message_id (int): The 29-bit message ID.
    
        Returns:
            bool: True if the message is Acknowledgement, False otherwise.
        """
    return (message_id & PF_MASK) == ACK_MASK


def is_ack_pgn(pgn):
    """Checks if a PGN corresponds to an Acknowledgement (ACK).
    
        Args:
            pgn (int): The Parameter Group Number.
    
        Returns:
            bool: True if the PGN is Acknowledgement, False otherwise.
        """
    return pgn == ACK_MASK >> 8


def is_transport_message(message_id):
    """Checks if a message ID is related to the transport protocol.
    
        Args:
            message_id (int): The 29-bit message ID.
    
        Returns:
            bool: True if the message is a transport message, False otherwise.
        """
    return (
        is_data_transfer_message(message_id)
        or is_connection_management_message(message_id)
        or is_ack_message(message_id)
    )


def is_transport_pgn(pgn):
    """Checks if a PGN is related to the transport protocol.
    
        Args:
            pgn (int): The Parameter Group Number.
    
        Returns:
            bool: True if the PGN is a transport PGN, False otherwise.
        """
    return (
        is_data_transfer_pgn(pgn)
        or is_connection_management_pgn(pgn)
        or is_ack_pgn(pgn)
    )


def is_bam_rts_cts_message(message_bytes):
    # 32=BAM, 16=RTS, 17=CTS, 19=EOM, 255=Abort
    """Checks if the message bytes contain BAM, RTS, CTS, EOM, or Abort commands.
    
        Args:
            message_bytes (bytes or list): The data bytes of the message.
    
        Returns:
            bool: True if the first byte represents a known transport protocol command.
        """
    return message_bytes[0] in (32, 16, 17, 19, 255)


def is_spn_bitencoded(spn_units):
    """Checks if the given SPN units indicate a bit-encoded value.
    
        Args:
            spn_units (str): The units string of the SPN.
    
        Returns:
            bool: True if the units are "bit" or "binary", False otherwise.
        """
    return spn_units.lower() in (
        "bit",
        "binary",
    )


def is_spn_numerical_values(spn_units):
    """Checks if the given SPN units represent numerical values.
    
        Args:
            spn_units (str): The units string of the SPN.
    
        Returns:
            bool: True if the units denote a numerical value, False otherwise.
        """
    if spn_units is None:
        return False
    norm_units = spn_units.lower()
    return norm_units not in (
        "manufacturer determined",
        "byte",
        "",
        "request dependent",
        "ascii",
    )
