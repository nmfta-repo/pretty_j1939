import re

with open("pretty_j1939/__main__.py", "r") as f:
    content = f.read()

new_methods = r"""    def _parse_candump_line(self, candump_line):
        timestamp = 0.0
        interface = "can"
        message_id = None
        message_data = None

        if not candump_line.strip():
            return None

        if candump_line.strip().startswith("Timestamp:"):
            parts = candump_line.split()
            try:
                if "Timestamp:" in parts:
                    ts_idx = parts.index("Timestamp:") + 1
                    timestamp = float(parts[ts_idx])
                id_idx = parts.index("ID:") + 1
                msg_id_str = parts[id_idx]
                dl_idx = parts.index("DL:") + 1
                length = int(parts[dl_idx])
                data_start_idx = dl_idx + 1
                data_hex_list = parts[data_start_idx : data_start_idx + length]
                data_hex_str = "0x" + "".join(data_hex_list)
                message_id = bitstring.Bits(hex=msg_id_str)
                message_data = bitstring.Bits(hex=data_hex_str)
            except (ValueError, IndexError) as e:
                logger.debug(f"Skipping malformed message due to decoding error: {e}")
                return None
        else:
            parts = candump_line.split()
            if not parts:
                return None
            if parts[0].isdigit() and len(parts) > 1 and parts[1].startswith("("):
                parts = parts[1:]

            if len(parts) < 1:
                return None
            try:
                if len(parts) >= 3 and parts[0].startswith("(") and parts[0].endswith(")"):
                    timestamp = float(parts[0][1:-1])
                    interface = parts[1]
                    message = parts[2]
                elif len(parts) >= 2:
                    interface = parts[0]
                    message = parts[1]
                else:
                    message = parts[0]
                    interface = "can"

                if "#" not in message:
                    return None
                msg_id_str, msg_data_str = message.split("#", 1)
                message_id = bitstring.Bits(hex=msg_id_str)
                message_data = bitstring.Bits(hex=msg_data_str)
            except (ValueError, IndexError) as e:
                logger.debug(f"Skipping candump line due to decoding error: {e}")
                return None

        return timestamp, interface, message_id, message_data

    def _parse_can_message(self, item):
        message_id = bitstring.Bits(uint=item.arbitration_id, length=32)
        message_data = bitstring.Bits(bytes=item.data)
        timestamp = item.timestamp
        interface = str(item.channel)
        return timestamp, interface, message_id, message_data

    def _matches_can_filters(self, message_id_uint, filters):
        if not filters:
            return True
        for f in filters:
            if (message_id_uint & f["can_mask"]) == (f["can_id"] & f["can_mask"]):
                return True
        return False

    def _matches_j1939_filters(self, description):
        if not (self.pgn_list or self.sa_list or self.da_list or self.ca_list):
            return True

        msg_pgn = description.get("_pgn")
        msg_sa = description.get("_sa")
        msg_da = description.get("_da")

        if self.pgn_list and msg_pgn not in self.pgn_list:
            return False
        if self.sa_list and msg_sa not in self.sa_list:
            return False
        if self.da_list and msg_da not in self.da_list:
            return False
        if self.ca_list and msg_sa not in self.ca_list and msg_da not in self.ca_list:
            return False

        return True

    def _check_highlight(self, description):
        if not (self.highlight_pgns or self.highlight_sas or self.highlight_das or self.highlight_cas):
            return False

        msg_pgn = description.get("_pgn")
        msg_sa = description.get("_sa")
        msg_da = description.get("_da")

        if (self.highlight_pgns and msg_pgn in self.highlight_pgns) \
            or (self.highlight_sas and msg_sa in self.highlight_sas) \
            or (self.highlight_das and msg_da in self.highlight_das) \
            or (self.highlight_cas and (msg_sa in self.highlight_cas or msg_da in self.highlight_cas)):
            return True

        return False

    def _render_and_output(self, timestamp, interface, message_id, message_data, candump_line, description, is_highlight):
        can_prefix = None
        if self.args.candata:
            if self.args.candata == "candump":
                prefix_content = f"({timestamp:17.6f}) {interface} {message_id.hex.upper()}#{message_data.hex.upper()}"
            else:
                prefix_content = candump_line.rstrip()

            can_prefix = prefix_content.ljust(80) + " ; "

        desc_line = self.render_description(
            description,
            indent=self.args.format,
            can_line=can_prefix,
            highlight=is_highlight,
        )
        if len(desc_line) > 0:
            print(desc_line, flush=True)

        if self.write_f:
            prefix_f = (
                f"({timestamp:17.6f}) {interface} {message_id.hex.upper()}#{message_data.hex.upper()}".ljust(80)
                + " ; "
            )
            desc_f = self.render_description(
                description,
                indent=self.args.format,
                can_line=prefix_f,
                force_colorize=False,
                highlight=is_highlight,
            )
            if len(desc_f) > 0:
                self.write_f.write(desc_f + "\n")
                self.write_f.flush()

    def process_messages(self, source, filters=None):
        for item in source:
            try:
                if isinstance(item, str):
                    parsed = self._parse_candump_line(item)
                    if not parsed:
                        continue
                    timestamp, interface, message_id, message_data = parsed
                    candump_line = item
                elif can and isinstance(item, can.Message):
                    timestamp, interface, message_id, message_data = self._parse_can_message(item)
                    candump_line = str(item)
                else:
                    continue
            except (IndexError, ValueError):
                if isinstance(item, str):
                    print("Warning: error in line '%s'" % item, file=sys.stderr)
                continue

            message_id_uint = message_id.uint

            if not self._matches_can_filters(message_id_uint, filters):
                continue

            description = self.describe_obj(message_data, message_id_uint)
            if not description:
                continue

            self.message_count += 1

            if not self._matches_j1939_filters(description):
                continue

            is_highlight = self._check_highlight(description)

            self._render_and_output(
                timestamp, interface, message_id, message_data, candump_line, description, is_highlight
            )
"""

start_str = "    def process_messages(self, source, filters=None):\n"
end_str = "    def print_summary(self):\n"

start_idx = content.find(start_str)
end_idx = content.find(end_str)

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + new_methods + "\n" + content[end_idx:]
    with open("pretty_j1939/__main__.py", "w") as f:
        f.write(new_content)
    print("Replaced successfully")
else:
    print("Could not find start or end index")
