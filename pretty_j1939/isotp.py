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


class IsoTpTracker:
    def __init__(self, real_time):
        self.is_real_time = real_time
        self.sessions = {}

    def process(self, transport_found_processor, message_bytes, message_id):
        pgn, da, sa = parse_j1939_id(message_id)

        # Only process DIAG3 PGN (0xDA00 / 55808)
        if pgn != DIAG3_PGN:
            return

        if len(message_bytes) < 1:
            return

        pci_byte = message_bytes[0]
        pci_type = pci_byte & 0xF0

        if pci_type == PCI_SF:
            # Single Frame
            length = pci_byte & 0x0F
            if length == 0:
                # CAN FD: byte 1 contains the length
                if len(message_bytes) > 1:
                    length = message_bytes[1]
                    data_start = 2
                else:
                    return
            else:
                data_start = 1

            if len(message_bytes) >= data_start + length:
                data = message_bytes[data_start : data_start + length]
                transport_found_processor(bytes(data), sa, pgn, is_last_packet=True)

        elif pci_type == PCI_FF:
            # First Frame
            # Length is 12 bits: lower nibble of byte 0 + all of byte 1
            if len(message_bytes) < 2:
                return

            total_length = ((pci_byte & 0x0F) << 8) + message_bytes[1]
            data_start = 2

            if total_length == 0:
                # 32-bit length follows in bytes 2-5 (ISO 15765-2:2016)
                if len(message_bytes) >= 6:
                    total_length = (
                        (message_bytes[2] << 24)
                        + (message_bytes[3] << 16)
                        + (message_bytes[4] << 8)
                        + message_bytes[5]
                    )
                    data_start = 6
                else:
                    return

            # Start new session
            current_payload = message_bytes[data_start:]

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

        elif pci_type == PCI_CF:
            # Consecutive Frame
            if (da, sa) not in self.sessions:
                return  # No active session

            session = self.sessions[(da, sa)]
            sn = pci_byte & 0x0F

            if sn != (session["next_sn"] & 0x0F):
                # Sequence error, abort session
                del self.sessions[(da, sa)]
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

        elif pci_type == PCI_FC:
            # Flow Control - useful for active nodes, passive listener just ignores
            pass
