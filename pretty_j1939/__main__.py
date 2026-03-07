#!/usr/bin/env python3
#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#


import bitstring
import argparse
import sys
import os
import json
import re
import importlib.resources
from io import StringIO
from rich.console import Console
from rich.theme import Theme
from rich.text import Text

try:
    import can
except ImportError:
    can = None

from . import describe
from .parse import parse_j1939_id
from .render import HighPerformanceRenderer

NUM_IN_PARENS_RE = re.compile(r"(\()([^)]*[0-9/x][^)]*)(\))")


class J1939Runner:
    def __init__(
        self,
        args,
        extra_kwargs,
        can_filters,
        pgn_list,
        sa_list,
        da_list,
        ca_list,
        highlight_pgns=None,
        highlight_sas=None,
        highlight_das=None,
        highlight_cas=None,
    ):
        self.args = args
        self.extra_kwargs = extra_kwargs
        self.can_filters = can_filters
        self.pgn_list = pgn_list
        self.sa_list = sa_list
        self.da_list = da_list
        self.ca_list = ca_list
        self.highlight_pgns = highlight_pgns or []
        self.highlight_sas = highlight_sas or []
        self.highlight_das = highlight_das or []
        self.highlight_cas = highlight_cas or []

        self.summary_data = {}

        self.theme_dict = HighPerformanceRenderer.load_theme(args.theme)

        self.custom_theme = Theme(self.theme_dict)
        # fixed dimensions and disabled legacy windows detection to avoid frequent
        # get_terminal_size system calls which are expensive on some platforms (e.g. Windows).
        self.console = Console(
            theme=self.custom_theme,
            force_terminal=True,
            width=1000,
            height=100,
            legacy_windows=False,
        )
        self.render_buffer = StringIO()
        self.render_console = Console(
            file=self.render_buffer,
            theme=self.custom_theme,
            force_terminal=True,
            width=1000,
            height=100,
            legacy_windows=False,
        )

        self.describe_obj = describe.get_describer(
            da_json=args.da_json,
            describe_pgns=args.pgn,
            describe_spns=args.spn,
            describe_link_layer=args.link,
            describe_transport_layer=args.transport,
            real_time=args.real_time,
            include_transport_rawdata=args.candata,
            include_na=args.include_na,
            include_raw_data=args.include_raw_data,
            enable_isotp=args.enable_isotp,
        )

        self.renderer = HighPerformanceRenderer(
            self.theme_dict,
            color_system=self.console.color_system,
            da_describer=self.describe_obj.da_describer,
        )

        self.should_colorize = args.color == "always" or (
            args.color == "auto" and sys.stdout.isatty()
        )

        # Resolve string-based filters/highlights
        self.pgn_list = self._resolve_pgns(pgn_list)
        self.sa_list = self._resolve_addrs(sa_list, "Source Address")
        self.da_list = self._resolve_addrs(da_list, "Destination Address")
        self.ca_list = self._resolve_addrs(ca_list, "Controller Application")

        self.highlight_pgns = self._resolve_pgns(highlight_pgns)
        self.highlight_sas = self._resolve_addrs(
            highlight_sas, "Source Address highlight"
        )
        self.highlight_das = self._resolve_addrs(
            highlight_das, "Destination Address highlight"
        )
        self.highlight_cas = self._resolve_addrs(
            highlight_cas, "Controller Application highlight"
        )

        # Generate J1939 CAN-level filters
        self._generate_can_filters()

        self.write_f = None
        if args.write:
            try:
                self.write_f = open(args.write, "w")
            except Exception as e:
                print(
                    f"Error: Failed to open output file '{args.write}': {e}",
                    file=sys.stderr,
                )
                sys.exit(1)

    def _resolve_pgns(self, inputs):
        if not inputs:
            return []
        resolved = set()
        for item in inputs:
            if isinstance(item, int):
                resolved.add(item)
                continue

            # Check if it's a numeric string
            try:
                val = int(item, 16) if item.startswith("0x") else int(item)
                resolved.add(val)
            except ValueError:
                # Resolve via database
                matches = self.describe_obj.da_describer.resolve_pgn(item)
                if not matches:
                    print(
                        f"Error: '{item}' did not match any PGN in the database.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                print(
                    f"Resolving PGN filter '{item}' to PGNs: {', '.join(map(str, matches))}",
                    file=sys.stderr,
                )
                resolved.update(matches)
        return list(resolved)

    def _resolve_addrs(self, inputs, category):
        if not inputs:
            return []
        resolved = set()
        for item in inputs:
            if isinstance(item, int):
                resolved.add(item)
                continue

            try:
                val = int(item, 16) if item.startswith("0x") else int(item)
                resolved.add(val)
            except ValueError:
                matches = self.describe_obj.da_describer.resolve_address(item)
                if not matches:
                    print(
                        f"Error: '{item}' did not match any {category} in the database.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                print(
                    f"Resolving {category} filter '{item}' to addresses: {', '.join(map(str, matches))}",
                    file=sys.stderr,
                )
                resolved.update(matches)
        return list(resolved)

    def _generate_can_filters(self):
        """Generate CAN-level filters from J1939 filter criteria."""
        if not (self.pgn_list or self.sa_list or self.da_list or self.ca_list):
            return

        from itertools import product

        pgn_filters = []
        for val in self.pgn_list:
            pf = (val >> 8) & 0xFF
            if pf < 240:
                pgn_filters.append(((val << 8), 0x03FF0000))
            else:
                pgn_filters.append(((val << 8), 0x03FFFF00))

        sa_filters = [(val, 0x000000FF) for val in self.sa_list]
        da_filters = [((val << 8), 0x0000FF00) for val in self.da_list]

        if not self.can_filters:
            self.can_filters = []

        tmp_pgn_filters = pgn_filters if pgn_filters else [(0, 0)]
        tmp_sa_filters = sa_filters if sa_filters else [(0, 0)]
        tmp_da_filters = da_filters if da_filters else [(0, 0)]

        def add_filter(pf, sf, df):
            self.can_filters.append(
                {
                    "can_id": pf[0] | sf[0] | df[0],
                    "can_mask": pf[1] | sf[1] | df[1],
                    "extended": True,
                }
            )

        if not self.ca_list:
            for pf, sf, df in product(tmp_pgn_filters, tmp_sa_filters, tmp_da_filters):
                add_filter(pf, sf, df)
        else:
            for c in self.ca_list:
                # 1. Match SA == c
                sas_to_use = (
                    [(c, 0x000000FF)]
                    if any(
                        s_mask == 0 or (c & s_mask) == (s_val & s_mask)
                        for s_val, s_mask in tmp_sa_filters
                    )
                    else []
                )
                if sas_to_use:
                    for pf, sf, df in product(
                        tmp_pgn_filters, sas_to_use, tmp_da_filters
                    ):
                        add_filter(pf, sf, df)
                # 2. Match DA == c
                das_to_use = (
                    [((c << 8), 0x0000FF00)]
                    if any(
                        d_mask == 0 or ((c << 8) & d_mask) == (d_val & d_mask)
                        for d_val, d_mask in tmp_da_filters
                    )
                    else []
                )
                if das_to_use:
                    for pf, sf, df in product(
                        tmp_pgn_filters, tmp_sa_filters, das_to_use
                    ):
                        add_filter(pf, sf, df)

        # Include transport PGNs if PGN filtering is active
        if self.pgn_list:
            for tp_pgn in [60416, 60160, 59392]:
                tp_pf = (tp_pgn << 8, 0x03FF0000)
                if not self.ca_list:
                    for _, sf, df in product([(0, 0)], tmp_sa_filters, tmp_da_filters):
                        add_filter(tp_pf, sf, df)
                else:
                    for c in self.ca_list:
                        add_filter(tp_pf, (c, 0x000000FF), (0, 0))
                        add_filter(tp_pf, (0, 0), ((c << 8), 0x0000FF00))

    def render_description(
        self,
        description,
        indent=False,
        can_line=None,
        force_colorize=None,
        highlight=False,
    ):
        effective_colorize = (
            self.should_colorize if force_colorize is None else force_colorize
        )

        if not effective_colorize:
            # Filter description once
            filtered_desc = {
                k: v for k, v in description.items() if not k.startswith("_")
            }
            if indent:
                json_str = json.dumps(filtered_desc, indent=4)
                if can_line:
                    spacer = (
                        " " * (len(can_line) - 3) + " ; "
                        if can_line.endswith(" ; ")
                        else " " * len(can_line)
                    )
                    lines = json_str.splitlines()
                    res = can_line + lines[0]
                    for line in lines[1:]:
                        res += "\n" + spacer + line
                    return res
                return json_str
            else:
                json_str = json.dumps(filtered_desc, separators=(",", ":"))
                return (can_line + json_str) if can_line else json_str

        return self.renderer.render(
            description, indent=indent, can_line=can_line, highlight=highlight
        )

    def process_messages(self, source, filters=None):
        for item in source:
            try:
                timestamp = 0.0
                interface = "can"

                if isinstance(item, str):
                    candump_line = item
                    if not candump_line.strip():
                        continue

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
                            data_hex_list = parts[
                                data_start_idx : data_start_idx + length
                            ]
                            data_hex_str = "0x" + "".join(data_hex_list)
                            message_id = bitstring.Bits(hex=msg_id_str)
                            message_data = bitstring.Bits(hex=data_hex_str)
                        except (ValueError, IndexError):
                            continue
                    else:
                        parts = candump_line.split()
                        if not parts:
                            continue
                        # Handle optional leading index (e.g. "1 (1612543138.000000) ...")
                        if (
                            parts[0].isdigit()
                            and len(parts) > 1
                            and parts[1].startswith("(")
                        ):
                            parts = parts[1:]

                        if len(parts) < 1:
                            continue
                        try:
                            if (
                                len(parts) >= 3
                                and parts[0].startswith("(")
                                and parts[0].endswith(")")
                            ):
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
                                continue
                            msg_id_str, msg_data_str = message.split("#", 1)
                            message_id = bitstring.Bits(hex=msg_id_str)
                            message_data = bitstring.Bits(hex=msg_data_str)
                        except (ValueError, IndexError):
                            continue
                elif can and isinstance(item, can.Message):
                    message_id = bitstring.Bits(uint=item.arbitration_id, length=32)
                    message_data = bitstring.Bits(bytes=item.data)
                    timestamp = item.timestamp
                    interface = str(item.channel)
                    candump_line = str(item)
                else:
                    continue
            except (IndexError, ValueError):
                if isinstance(item, str):
                    print("Warning: error in line '%s'" % item, file=sys.stderr)
                continue

            message_id_uint = message_id.uint

            if filters:
                matched = False
                for f in filters:
                    if (message_id_uint & f["can_mask"]) == (
                        f["can_id"] & f["can_mask"]
                    ):
                        matched = True
                        break
                if not matched:
                    continue

            description = self.describe_obj(message_data, message_id_uint)
            if not description:
                continue

            if self.pgn_list or self.sa_list or self.da_list or self.ca_list:
                msg_pgn = description.get("_pgn")
                msg_sa = description.get("_sa")
                msg_da = description.get("_da")

                if self.pgn_list and msg_pgn not in self.pgn_list:
                    continue
                if self.sa_list and msg_sa not in self.sa_list:
                    continue
                if self.da_list and msg_da not in self.da_list:
                    continue
                if (
                    self.ca_list
                    and msg_sa not in self.ca_list
                    and msg_da not in self.ca_list
                ):
                    continue

            is_highlight = False
            if (
                self.highlight_pgns
                or self.highlight_sas
                or self.highlight_das
                or self.highlight_cas
            ):
                msg_pgn = description.get("_pgn")
                msg_sa = description.get("_sa")
                msg_da = description.get("_da")

                if (
                    (self.highlight_pgns and msg_pgn in self.highlight_pgns)
                    or (self.highlight_sas and msg_sa in self.highlight_sas)
                    or (self.highlight_das and msg_da in self.highlight_das)
                    or (
                        self.highlight_cas
                        and (
                            msg_sa in self.highlight_cas or msg_da in self.highlight_cas
                        )
                    )
                ):
                    is_highlight = True

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
                    f"({timestamp:17.6f}) {interface} {message_id.hex.upper()}#{message_data.hex.upper()}".ljust(
                        80
                    )
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

    def print_summary(self):
        summary_data = self.describe_obj.get_summary()
        if not self.args.summary or not summary_data:
            return

        res = self.renderer.render_summary(summary_data, indent=self.args.format)
        if res:
            if self.args.candata:
                res = "\n".join(f"; {line}" for line in res.splitlines())

            print(res, file=sys.stdout)
            if self.write_f:
                f_summary = res
                if self.should_colorize:
                    # Strip ANSI codes for file output
                    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
                    f_summary = ansi_escape.sub("", res)

                # If not already prefixed (it would be if candata was true)
                if not self.args.candata:
                    f_summary = "\n".join(
                        f"; {line}" for line in f_summary.splitlines()
                    )

                self.write_f.write(f_summary + "\n")

    def run(self):
        bus = None
        try:
            if self.args.interface:
                if can is None:
                    print("Error: 'python-can' is not installed", file=sys.stderr)
                    sys.exit(1)
                try:
                    bus_kwargs = {
                        "interface": self.args.interface,
                        "channel": self.args.channel,
                        "bitrate": self.args.bitrate,
                        **self.extra_kwargs,
                    }
                    # Filter out None values to let python-can use its defaults
                    bus_kwargs = {k: v for k, v in bus_kwargs.items() if v is not None}

                    if self.can_filters:
                        bus_kwargs["can_filters"] = self.can_filters

                    bus = can.Bus(**bus_kwargs)
                    print(f"Connected to {bus.__class__.__name__}: {bus.channel_info}")
                    self.process_messages(bus, self.can_filters)
                except can.CanError as e:
                    print(f"CAN error: {e}", file=sys.stderr)
                    if "Unknown interface" in str(e):
                        backends = sorted(list(can.interfaces.BACKENDS.keys()))
                        print(
                            f"Available interfaces: {', '.join(backends)}",
                            file=sys.stderr,
                        )
                    sys.exit(1)
            else:
                f = None
                if self.args.candump == "-":
                    f = sys.stdin
                elif self.args.candump:
                    try:
                        f = open(self.args.candump, "r")
                    except FileNotFoundError:
                        print(
                            f"Error: file '{self.args.candump}' not found",
                            file=sys.stderr,
                        )
                        sys.exit(1)
                else:
                    print(
                        "Error: must specify either a log file or an interface (-i)",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                try:
                    self.process_messages(f, self.can_filters)
                finally:
                    if f is not None and f is not sys.stdin:
                        f.close()
        except KeyboardInterrupt:
            print("\nInterrupted by user", file=sys.stderr)
            sys.exit(0)
        finally:
            if bus:
                try:
                    bus.shutdown()
                except Exception:
                    pass
            self.print_summary()
            if self.write_f:
                self.write_f.close()


def get_parser():
    parser = argparse.ArgumentParser(description="pretty-printing J1939 candump logs")

    input_group = parser.add_argument_group("Input and Interface Options")
    input_group.add_argument(
        "candump",
        nargs="?",
        default=None,
        help="candump log, use - for stdin. (optional if -i is used)",
    )
    input_group.add_argument(
        "-i",
        "--interface",
        help="python-can backend interface to use (e.g. 'socketcan', 'cantact', 'vector'). "
        "Enables live input instead of a log file.",
    )
    input_group.add_argument(
        "-c",
        "--channel",
        help="python-can channel (most backends require this)",
    )
    input_group.add_argument(
        "-b",
        "--bitrate",
        type=int,
        help="Bitrate to use for the python-can interface",
    )

    filter_group = parser.add_argument_group("Filtering Options")
    filter_group.add_argument(
        "--filter",
        nargs="+",
        help="Space separated CAN filters: <can_id>:<can_mask> or <can_id>~<can_mask>",
    )
    filter_group.add_argument(
        "--filter-pgn",
        nargs="+",
        help="Comma or space separated PGN filters (decimal, hex, or string lookup in database)",
    )
    filter_group.add_argument(
        "--filter-sa",
        nargs="+",
        help="Comma or space separated Source Address filters (decimal, hex, or string lookup in database)",
    )
    filter_group.add_argument(
        "--filter-da",
        nargs="+",
        help="Comma or space separated Destination Address filters (decimal, hex, or string lookup in database)",
    )
    filter_group.add_argument(
        "--filter-ca",
        nargs="+",
        help="Comma or space separated Controller Application filters (matches either SA or DA; supports string lookup)",
    )

    highlight_group = parser.add_argument_group("Highlighting Options")
    highlight_group.add_argument(
        "--highlight-pgn",
        "--hilight-pgn",
        nargs="+",
        help="Comma or space separated PGNs to highlight (decimal, hex, or string lookup). Requires --color.",
    )
    highlight_group.add_argument(
        "--highlight-sa",
        "--hilight-sa",
        nargs="+",
        help="Comma or space separated Source Addresses to highlight (decimal, hex, or string lookup). Requires --color.",
    )
    highlight_group.add_argument(
        "--highlight-da",
        "--hilight-da",
        nargs="+",
        help="Comma or space separated Destination Addresses to highlight (decimal, hex, or string lookup). Requires --color.",
    )
    highlight_group.add_argument(
        "--highlight-ca",
        "--hilight-ca",
        nargs="+",
        help="Comma or space separated Controller Application addresses to highlight (supports string lookup). Requires --color.",
    )

    da_group = parser.add_argument_group("Database Options")
    da_group.add_argument(
        "--da-json",
        type=str,
        default=describe.DEFAULT_DA_JSON,
        help='absolute path to the input JSON DA (default: "%(default)s")',
    )

    display_group = parser.add_argument_group("Display and Verbosity Options")
    display_group.add_argument(
        "--pgn",
        action="store_true",
        help="(default) print source/destination/type description",
    )
    display_group.add_argument("--no-pgn", dest="pgn", action="store_false")
    parser.set_defaults(pgn=describe.DEFAULT_PGN)

    display_group.add_argument(
        "--spn",
        action="store_true",
        help="(default) print signals description",
    )
    display_group.add_argument("--no-spn", dest="spn", action="store_false")
    parser.set_defaults(spn=describe.DEFAULT_SPN)

    display_group.add_argument(
        "--transport",
        action="store_true",
        help="(default) print details of transport-layer streams found",
    )
    display_group.add_argument("--no-transport", dest="transport", action="store_false")
    parser.set_defaults(transport=describe.DEFAULT_TRANSPORT)

    display_group.add_argument(
        "--link",
        action="store_true",
        help="print details of link-layer frames found",
    )
    display_group.add_argument("--no-link", dest="link", action="store_false")
    parser.set_defaults(link=describe.DEFAULT_LINK)

    display_group.add_argument(
        "--include-na",
        action="store_true",
        help="include not-available (0xff) SPN values",
    )
    display_group.add_argument(
        "--no-include-na", dest="include_na", action="store_false"
    )
    parser.set_defaults(include_na=describe.DEFAULT_INCLUDE_NA)

    display_group.add_argument(
        "--bytes",
        dest="include_raw_data",
        action="store_true",
        help="always include raw data bytes",
    )
    display_group.add_argument(
        "--no-bytes", dest="include_raw_data", action="store_false"
    )
    parser.set_defaults(include_raw_data=describe.DEFAULT_INCLUDE_RAW_DATA)

    display_group.add_argument(
        "--summary",
        action="store_true",
        help="(default) Print summary at end",
    )
    display_group.add_argument("--no-summary", dest="summary", action="store_false")
    parser.set_defaults(summary=True)

    display_group.add_argument(
        "--real-time",
        action="store_true",
        help="emit SPNs as they are seen in transport sessions",
    )
    display_group.add_argument("--no-real-time", dest="real_time", action="store_false")
    parser.set_defaults(real_time=describe.DEFAULT_REAL_TIME)

    display_group.add_argument(
        "--format",
        action="store_true",
        help="format each structure (otherwise single-line)",
    )
    display_group.add_argument("--no-format", dest="format", action="store_false")
    parser.set_defaults(format=False)

    display_group.add_argument(
        "--theme",
        help="Theme name or JSON file containing theme colors",
    )
    display_group.add_argument(
        "--color",
        choices=["always", "never", "auto"],
        default="auto",
        help="colorize JSON output (default: %(default)s)",
    )
    display_group.add_argument(
        "--no-isotp",
        dest="enable_isotp",
        action="store_false",
        help="Disable ISO-TP (ISO 15765-2) reassembly for PGN 0xDA00",
    )
    parser.set_defaults(enable_isotp=True)

    output_group = parser.add_argument_group("Output and Formatting Options")
    output_group.add_argument(
        "--candata",
        nargs="?",
        const="raw",
        choices=["raw", "candump"],
        help="print input can data (default: raw if flag used)",
    )
    output_group.add_argument("--no-candata", dest="candata", action="store_false")
    parser.set_defaults(candata=False)

    output_group.add_argument(
        "-w",
        "--write",
        help="Write plain-text output to file (uses --candata=candump)",
    )
    return parser


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "viewer":
        from .viewer import main as viewer_main

        sys.argv.pop(1)
        viewer_main()
        return

    parser = get_parser()
    args, unknown_args = parser.parse_known_args()

    extra_kwargs = {}
    for arg in unknown_args:
        if arg.startswith("--"):
            if "=" in arg:
                key, value = arg[2:].split("=", 1)
                extra_kwargs[key.replace("-", "_")] = value
            else:
                extra_kwargs[arg[2:].replace("-", "_")] = True

    can_filters = []
    if args.filter:
        for filt in args.filter:
            if ":" in filt:
                can_id, can_mask = filt.split(":", 1)
                can_filters.append(
                    {"can_id": int(can_id, 16), "can_mask": int(can_mask, 16)}
                )
            elif "~" in filt:
                can_id, can_mask = filt.split("~", 1)
                can_filters.append(
                    {
                        "can_id": int(can_id, 16),
                        "can_mask": int(can_mask, 16),
                        "extended": True,
                    }
                )

    pgn_list, pgn_filters = [], []
    if args.filter_pgn:
        for p in args.filter_pgn:
            for sub_p in p.replace(",", " ").split():
                pgn_list.append(sub_p)

    sa_list = []
    if args.filter_sa:
        for s in args.filter_sa:
            for sub_s in s.replace(",", " ").split():
                sa_list.append(sub_s)

    da_list = []
    if args.filter_da:
        for d in args.filter_da:
            for sub_d in d.replace(",", " ").split():
                da_list.append(sub_d)

    ca_list = []
    if args.filter_ca:
        for c in args.filter_ca:
            for sub_c in c.replace(",", " ").split():
                ca_list.append(sub_c)

    h_pgn_list = []
    if args.highlight_pgn:
        for p in args.highlight_pgn:
            for sub_p in p.replace(",", " ").split():
                h_pgn_list.append(sub_p)

    h_sa_list = []
    if args.highlight_sa:
        for s in args.highlight_sa:
            for sub_s in s.replace(",", " ").split():
                h_sa_list.append(sub_s)

    h_da_list = []
    if args.highlight_da:
        for d in args.highlight_da:
            for sub_d in d.replace(",", " ").split():
                h_da_list.append(sub_d)

    h_ca_list = []
    if args.highlight_ca:
        for c in args.highlight_ca:
            for sub_c in c.replace(",", " ").split():
                h_ca_list.append(sub_c)

    # Note: CAN level filters will be populated inside J1939Runner after string resolution
    runner = J1939Runner(
        args,
        extra_kwargs,
        can_filters,
        pgn_list,
        sa_list,
        da_list,
        ca_list,
        highlight_pgns=h_pgn_list,
        highlight_sas=h_sa_list,
        highlight_das=h_da_list,
        highlight_cas=h_ca_list,
    )
    runner.run()


if __name__ == "__main__":
    main()
