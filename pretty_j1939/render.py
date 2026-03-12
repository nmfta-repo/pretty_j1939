#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import json
import re
import os
import sys
import importlib.resources
from io import StringIO
from rich.console import Console
from rich.theme import Theme

NUM_IN_PARENS_RE = re.compile(r"(\()([^)]*[0-9/x][^)]*)(\))")


class HighPerformanceRenderer:
    DEFAULT_THEME = {
        "keys": "#3465a4",
        "strings": "default",
        "numbers": "#f57900",
        "disabled_bytes": "#555753",
        "zero_bytes": "#babdb6",
        "ascii_bytes": "#75507b",
        "normal_bytes": "default",
        "highlight": "#ffffff",
    }

    def __init__(self, theme_dict=None, color_system="truecolor", da_describer=None):
        self.color_system = color_system
        self.da_describer = da_describer
        if isinstance(theme_dict, str):
            self.theme_dict = self.load_theme(theme_dict)
        else:
            self.theme_dict = theme_dict or self.DEFAULT_THEME.copy()

        if color_system:
            # Initialize a rich console just to extract ANSI sequences from the theme
            console = Console(
                theme=Theme(self.theme_dict),
                force_terminal=True,
                color_system=color_system,
                legacy_windows=False,
            )

            # Pre-calculate ANSI sequences for high-performance manual string building
            self.ansi_esc = {}
            for style_name in self.theme_dict.keys():
                if style_name in ("default", "reset"):
                    continue
                style = console.get_style(style_name)
                codes = style._make_ansi_codes(console.color_system)
                self.ansi_esc[style_name] = f"\x1b[{codes}m" if codes else ""

            self.ansi_esc["default"] = "\x1b[0m"
            self.ansi_esc["reset"] = "\x1b[0m"
        else:
            self.ansi_esc = {
                k: "" for k in self.theme_dict.keys() if k not in ("default", "reset")
            }
            self.ansi_esc["default"] = ""
            self.ansi_esc["reset"] = ""

    @staticmethod
    def load_theme(theme_name_or_path):
        """Loads a theme dictionary from a name or file path."""
        theme_dict = HighPerformanceRenderer.DEFAULT_THEME.copy()
        if theme_name_or_path is None:
            return theme_dict

        theme_path = theme_name_or_path

        if not os.path.exists(theme_path):
            # Try to find in package resources
            if not theme_path.endswith(".json"):
                theme_path += "-theme.json"

            try:
                if hasattr(importlib.resources, "files"):
                    ref = importlib.resources.files("pretty_j1939") / theme_path
                    if ref.is_file():
                        with ref.open("r") as f:
                            theme_dict.update(json.load(f))
                            theme_path = None
                else:
                    if importlib.resources.is_resource("pretty_j1939", theme_path):
                        with importlib.resources.open_text(
                            "pretty_j1939", theme_path
                        ) as f:
                            theme_dict.update(json.load(f))
                            theme_path = None
            except Exception as e:
                logger.debug(f"Failed to load built-in theme {theme_path}: {e}")

        if theme_path and os.path.exists(theme_path):
            try:
                with open(theme_path, "r") as f:
                    theme_dict.update(json.load(f))
            except Exception as e:
                print(
                    f"Warning: Failed to load theme file '{theme_path}': {e}",
                    file=sys.stderr,
                )
        elif theme_path is not None:
            print(
                f"Warning: Could not find theme '{theme_name_or_path}' as file or package resource.",
                file=sys.stderr,
            )

        return theme_dict

    @staticmethod
    def format_can_line(timestamp, interface, can_id, data_bytes):
        """Formats a CAN message into the standardized candump format."""
        if hasattr(data_bytes, "hex"):
            data_hex = data_bytes.hex().upper()
        else:
            data_hex = "".join(f"{b:02X}" for b in data_bytes)
        return f"({timestamp:17.6f}) {interface} {can_id:08X}#{data_hex}"

    def _render_json_output(self, filtered_desc, indent, can_line):
        json_str = json.dumps(filtered_desc, indent=4 if indent else None, separators=(",", ":") if not indent else None)
        if can_line:
            if indent:
                spacer = (" " * (len(can_line) - 3) + " ; " if can_line.endswith(" ; ") else " " * len(can_line))
                lines = json_str.splitlines()
                res = can_line + lines[0]
                for line in lines[1:]:
                    res += "\n" + spacer + line
                return res
            else:
                return can_line + json_str
        return json_str

    def _format_bytes_value(self, value, highlight):
        res_parts = ['"']
        clean_value = value[2:] if value.lower().startswith("0x") else value
        esc = self.ansi_esc
        h_style = esc.get("highlight", "") if highlight else ""
        reset = esc["default"]

        last_style = None
        batch = []
        for i in range(0, len(clean_value), 2):
            byte = clean_value[i : i + 2]
            if byte == "00":
                style = "zero_bytes"
            elif byte == "FF" or byte == "ff":
                style = "disabled_bytes"
            else:
                byte_int = int(byte, 16)
                style = (
                    "ascii_bytes" if 32 <= byte_int <= 126 else "normal_bytes"
                )

            if style == last_style:
                batch.append(byte)
            else:
                if batch:
                    effective_style = h_style if highlight else esc[last_style]
                    res_parts.append(f'{effective_style}{"".join(batch)}')
                batch = [byte]
                last_style = style
        if batch:
            effective_style = h_style if highlight else esc[last_style]
            res_parts.append(f'{effective_style}{"".join(batch)}')
        res_parts.append(f'{reset}"')
        return "".join(res_parts)

    def _format_other_value(self, value, highlight):
        res_parts = []
        val_json = json.dumps(value)
        esc = self.ansi_esc
        h_style = esc.get("highlight", "") if highlight else ""
        reset = esc["default"]

        # performance optimization: fast-path check for parentheses
        if "(" in val_json:
            last_end = 0
            style_str = h_style if highlight else esc["strings"]
            style_num = h_style if highlight else esc["numbers"]
            res_parts.append(style_str)
            for match in NUM_IN_PARENS_RE.finditer(val_json):
                res_parts.append(val_json[last_end : match.start(2)])
                res_parts.append(f"{style_num}{match.group(2)}{style_str}")
                last_end = match.end(2)
            res_parts.append(val_json[last_end:])
            res_parts.append(reset)
        else:
            style_str = h_style if highlight else esc["strings"]
            res_parts.append(f"{style_str}{val_json}{reset}")
        return "".join(res_parts)

    def render(self, description, indent=False, can_line=None, highlight=False):
        """
        Renders a J1939 description dictionary into a colorized ANSI string.

        performance optimization: use manual string building with pre-calculated ANSI sequences
        instead of rich.Text/Console. This reduces line-processing time by over 90%.
        """
        # Filter internal metadata
        filtered_desc = {k: v for k, v in description.items() if not k.startswith("_")}

        if not self.color_system:
            return self._render_json_output(filtered_desc, indent, can_line)

        res_parts = []
        if can_line:
            res_parts.append(can_line)

        res_parts.append("{")

        indent_str = ""
        spacer = ""
        if indent:
            indent_str = "\n    "
            if can_line:
                prefix_len = len(can_line)
                sep = " ; "
                if can_line.endswith(sep):
                    spacer_len = prefix_len - len(sep)
                    spacer = " " * spacer_len + sep
                    indent_str = "\n" + spacer + "    "
                else:
                    spacer = " " * prefix_len
                    indent_str = "\n" + spacer + "    "
            res_parts.append(indent_str)

        first = True
        esc = self.ansi_esc
        reset = esc["default"]
        h_style = esc.get("highlight", "") if highlight else ""

        for key, value in filtered_desc.items():
            if not first:
                res_parts.append(",")
                if indent:
                    res_parts.append(indent_str)

            style_key = h_style if highlight else esc["keys"]
            res_parts.append(f'{style_key}"{key}"{reset}:')
            if indent:
                res_parts.append(" ")

            if (
                key in ("Bytes", "Transport Data")
                or "Manufacturer Specific Information" in key
                or "Manufacturer Defined Usage" in key
            ):
                res_parts.append(self._format_bytes_value(value, highlight))
            else:
                res_parts.append(self._format_other_value(value, highlight))

            first = False

        if indent:
            res_parts.append("\n")
            res_parts.append(spacer)
        res_parts.append("}")

        return "".join(res_parts)

    def render_summary(self, summary_data, indent=False):
        """
        Renders a J1939 network summary into a colorized Mermaid-style graph.

        Returns a string (potentially with ANSI color codes).
        """
        if not summary_data:
            return ""

        def get_node_id(addr):
            return "All" if addr == 255 else f"N{addr}"

        def get_node_label(addr):
            if self.da_describer:
                fmt, name = self.da_describer.get_formatted_address_and_name(addr)
                return f"{name}{fmt.replace(' ', '')}"
            return f"{addr}"

        nodes = set()
        edges = []
        for (sa, da), data in sorted(summary_data.items()):
            nodes.add(sa)
            nodes.add(da)
            src, dst = get_node_id(sa), get_node_id(da)

            sent_pgns = []
            req_pgns = []

            if self.da_describer:
                sent_pgns = [
                    self.da_describer.get_pgn_description(p)
                    for p in sorted(list(data["sent"]))
                ]
                req_pgns = [
                    self.da_describer.get_pgn_description(p)
                    for p in sorted(list(data["req"]))
                ]
            else:
                sent_pgns = [str(p) for p in sorted(list(data["sent"]))]
                req_pgns = [str(p) for p in sorted(list(data["req"]))]

            if sent_pgns:
                edges.append((src, "-->", ", ".join(sent_pgns), dst))
            if req_pgns:
                edges.append((src, "-.->", "Req: " + ", ".join(req_pgns), dst))

        # Sort edges: non-"All" destinations first, then "All" destinations last
        edges.sort(key=lambda x: (x[3] == "All", x[0], x[3]))

        esc = self.ansi_esc
        reset = esc["default"]

        # We'll build the mermaid graph string
        m_parts = []
        m_parts.append(f"{esc['ascii_bytes']}graph LR{reset}")
        sep = "\n" if indent else "; "
        m_parts.append(sep)

        for i, addr in enumerate(sorted(list(nodes))):
            prefix = "    " if indent else ""
            m_parts.append(f"{prefix}{esc['numbers']}{get_node_id(addr)}{reset}")
            m_parts.append(f"{esc['strings']}[\"{get_node_label(addr)}\"]{reset}")
            if i < len(nodes) - 1 or edges:
                m_parts.append(sep)

        for i, (src, arrow, label, dst) in enumerate(edges):
            prefix = "    " if indent else ""
            m_parts.append(f"{prefix}{esc['numbers']}{src}{reset}")

            # Colorize label with numbers in parens
            processed_label = label
            if "(" in label:
                processed_label_str = ""
                last_end = 0
                for match in NUM_IN_PARENS_RE.finditer(label):
                    processed_label_str += (
                        f"{esc['strings']}{label[last_end : match.start(2)]}{reset}"
                    )
                    processed_label_str += f"{esc['numbers']}{match.group(2)}{reset}"
                    last_end = match.end(2)
                processed_label_str += f"{esc['strings']}{label[last_end:]}{reset}"
                processed_label = processed_label_str
            else:
                processed_label = f"{esc['strings']}{label}{reset}"

            if arrow == "-->":
                m_parts.append(f"{esc['strings']} -- {reset}")
                m_parts.append(processed_label)
                m_parts.append(f" {esc['keys']}-->{reset}")
            else:
                m_parts.append(f" {esc['keys']}-.{reset}")
                m_parts.append(processed_label)
                m_parts.append(f"{esc['keys']}.->{reset}")

            m_parts.append(f" {esc['numbers']}{dst}{reset}")
            if i < len(edges) - 1:
                m_parts.append(sep)

        res = "".join(m_parts)

        if indent:
            final_parts = []
            final_parts.append("{")
            final_parts.append(
                f"\n    {esc['keys']}\"Summary\"{reset}: {esc['strings']}\""
            )

            # Indent each line of the mermaid graph
            lines = res.split("\n")
            for i, line in enumerate(lines):
                if i != 0:
                    final_parts.append("\n               ")
                final_parts.append(line)

                # Important: In JSON strings, literal newlines must be escaped as \n
                # However, in --format mode the visual is more important than legal JSON

            final_parts.append(f'"{reset}')
            final_parts.append("\n}")
            return "".join(final_parts)
        else:
            return (
                f"{{{esc['keys']}\"Summary\"{reset}:{esc['strings']}\"{res}\"{reset}}}"
            )
