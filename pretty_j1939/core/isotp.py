#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import bitstring
from .parse import parse_j1939_id, DIAG3_PGN

# PCI Types
PCI_SF = 0x00  # Single Frame
PCI_FF = 0x10  # First Frame
PCI_CF = 0x20  # Consecutive Frame
PCI_FC = 0x30  # Flow Control


from typing import Callable, Any


class IsoTpTracker:
    def __init__(self, real_time: bool):
        self.is_real_time = real_time
        self.sessions = {}

    def cleanup(self, transport_found_processor: Callable[..., Any]):
        for (da, sa), session in self.sessions.items():
            if not self.is_real_time:
                transport_found_processor(
                    bytes(session["data"]), sa, session["pgn"], is_last_packet=True
                )
        self.sessions.clear()

    def _process_single_frame(
        self,
        transport_found_processor: Callable[..., Any],
        message_bytes: bytes,
        sa: int,
        pgn: int,
    ) -> None:
        # Single Frame
        pci_byte = message_bytes[0]
        length = pci_byte & 0x0F
        if len(message_bytes) >= 1 + length:
            data = message_bytes[1 : 1 + length]
            transport_found_processor(bytes(data), sa, pgn, is_last_packet=True)

    def _process_first_frame(
        self,
        transport_found_processor: Callable[..., Any],
        message_bytes: bytes,
        sa: int,
        da: int,
        pgn: int,
    ) -> None:
        pci_byte = message_bytes[0]
        # First Frame
        # Length is 12 bits: lower nibble of byte 0 + all of byte 1
        if len(message_bytes) < 2:
            return

        total_length = ((pci_byte & 0x0F) << 8) + message_bytes[1]

        # Start new session
        current_payload = message_bytes[2:]

        self.sessions[(da, sa)] = {
            "total_length": total_length,
            "data": bytearray(current_payload),
            "next_sn": 1,
            "pgn": pgn,
        }

        if self.is_real_time:
            transport_found_processor(
                bytes(current_payload), sa, pgn, is_last_packet=False
            )

    def _process_consecutive_frame(
        self,
        transport_found_processor: Callable[..., Any],
        message_bytes: bytes,
        sa: int,
        da: int,
        pgn: int,
    ) -> None:
        if (da, sa) not in self.sessions:
            return  # No active session

        session = self.sessions[(da, sa)]
        sn = self._get_sn(message_bytes)

        if sn != (session["next_sn"] & 0x0F):
            self._handle_sequence_error(da, sa)
            return

        # Append payload
        payload = message_bytes[1:]

        # Truncate if we have more data than needed
        bytes_needed = session["total_length"] - len(session["data"])
        if len(payload) > bytes_needed:
            payload = payload[:bytes_needed]

        session["data"].extend(payload)
        session["next_sn"] += 1

        is_complete = len(session["data"]) >= session["total_length"]

        if self.is_real_time:
            transport_found_processor(
                bytes(payload), sa, pgn, is_last_packet=is_complete
            )
        elif is_complete:
            transport_found_processor(
                bytes(session["data"]), sa, pgn, is_last_packet=True
            )

        if is_complete:
            del self.sessions[(da, sa)]

    def _get_sn(self, message_bytes: bytes) -> int:
        pci_byte = message_bytes[0]
        return pci_byte & 0x0F

    def _handle_sequence_error(self, da: int, sa: int) -> None:
        # Sequence error, abort session
        del self.sessions[(da, sa)]

    def _get_pci_type(self, message_bytes: bytes) -> int:
        pci_byte = message_bytes[0]
        return pci_byte & 0xF0

    def process(
        self,
        transport_found_processor: Callable[..., Any],
        message_bytes: bytes,
        message_id: int,
    ) -> None:
        pgn, da, sa = parse_j1939_id(message_id)

        # Only process DIAG3 PGN (0xDA00 / 55808)
        if pgn != DIAG3_PGN:
            return

        if len(message_bytes) < 1:
            return

        pci_type = self._get_pci_type(message_bytes)

        if pci_type == PCI_SF:
            self._process_single_frame(
                transport_found_processor, message_bytes, sa, pgn
            )

        elif pci_type == PCI_FF:
            self._process_first_frame(
                transport_found_processor, message_bytes, sa, da, pgn
            )

        elif pci_type == PCI_CF:
            self._process_consecutive_frame(
                transport_found_processor, message_bytes, sa, da, pgn
            )

        elif pci_type == PCI_FC:
            pass
