import re

with open("pretty_j1939/__main__.py", "r") as f:
    content = f.read()

get_parser_str = """def _add_input_options(parser):
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


def _add_filter_options(parser):
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


def _add_highlight_options(parser):
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


def _add_database_options(parser):
    da_group = parser.add_argument_group("Database Options")
    da_group.add_argument(
        "--da-json",
        type=str,
        default=describe.DEFAULT_DA_JSON,
        help='absolute path to the input JSON DA (default: "%(default)s")',
    )


def _add_display_options(parser):
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
        default=None,
        help="(default) Print summary at end if more than 8 lines of input",
    )
    display_group.add_argument("--no-summary", dest="summary", action="store_false")

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


def _add_output_options(parser):
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


def get_parser():
    parser = argparse.ArgumentParser(description="pretty-printing J1939 candump logs")
    _add_input_options(parser)
    _add_filter_options(parser)
    _add_highlight_options(parser)
    _add_database_options(parser)
    _add_display_options(parser)
    _add_output_options(parser)
    return parser
"""

start_idx = content.find("def get_parser():")
end_idx = content.find("def main():", start_idx)

new_content = content[:start_idx] + get_parser_str + "\n\n" + content[end_idx:]

with open("pretty_j1939/__main__.py", "w") as f:
    f.write(new_content)
