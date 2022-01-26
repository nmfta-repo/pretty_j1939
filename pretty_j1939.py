#!/usr/bin/env python3

import bitstring
import argparse
import sys
import json

import pretty_j1939.describe


parser = argparse.ArgumentParser(description='pretty-printing J1939 candump logs')
parser.add_argument('candump', help='candump log, use - for stdin')

parser.add_argument('--da-json', type=str, const=True, default=pretty_j1939.describe.DEFAULT_DA_JSON, nargs='?',
                    help='absolute path to the input JSON DA (default=\"./J1939db.json\")')

parser.add_argument('--candata',    dest='candata', action='store_true',  help='print input can data')
parser.add_argument('--no-candata', dest='candata', action='store_false', help='(default)')
parser.set_defaults(candata=pretty_j1939.describe.DEFAULT_CANDATA)

parser.add_argument('--pgn',    dest='pgn', action='store_true', help='(default) print source/destination/type '
                                                                      'description')
parser.add_argument('--no-pgn', dest='pgn', action='store_false')
parser.set_defaults(pgn=pretty_j1939.describe.DEFAULT_PGN)

parser.add_argument('--spn',    dest='spn', action='store_true', help='(default) print signals description')
parser.add_argument('--no-spn', dest='spn', action='store_false')
parser.set_defaults(spn=pretty_j1939.describe.DEFAULT_SPN)

parser.add_argument('--transport',    dest='transport', action='store_true',  help='print details of transport-layer '
                                                                                   'streams found (default)')
parser.add_argument('--no-transport', dest='transport', action='store_false', help='')
parser.set_defaults(transport=pretty_j1939.describe.DEFAULT_TRANSPORT)

parser.add_argument('--link',    dest='link', action='store_true',  help='print details of link-layer frames found')
parser.add_argument('--no-link', dest='link', action='store_false', help='(default)')
parser.set_defaults(link=pretty_j1939.describe.DEFAULT_LINK)

parser.add_argument('--include-na',    dest='include_na', action='store_true',  help='include not-available (0xff) SPN '
                                                                                     'values')
parser.add_argument('--no-include-na', dest='include_na', action='store_false', help='(default)')
parser.set_defaults(include_na=pretty_j1939.describe.DEFAULT_INCLUDE_NA)

parser.add_argument('--real-time',    dest='real_time', action='store_true',  help='emit SPNs as they are seen in '
                                                                                   'transport sessions')
parser.add_argument('--no-real-time', dest='real_time', action='store_false', help='(default)')
parser.set_defaults(real_time=pretty_j1939.describe.DEFAULT_REAL_TIME)

parser.add_argument('--format',    dest='format', action='store_true',  help='format each structure (otherwise '
                                                                             'single-line)')
parser.add_argument('--no-format', dest='format', action='store_false', help='(default)')
parser.set_defaults(format=False)


args = parser.parse_args()


def process_lines(candump_file):
    for candump_line in candump_file.readlines():
        if candump_line == '\n':
            continue

        try:
            message = candump_line.split()[2]
            message_id = bitstring.ConstBitArray(hex=message.split('#')[0])
            message_data = bitstring.ConstBitArray(hex=message.split('#')[1])
        except (IndexError, ValueError):
            print("Warning: error in line '%s'" % candump_line, file=sys.stderr)
            continue

        desc_line = ''

        description = describe(message_data.bytes, message_id.uint)
        if args.format:
            json_description = str(json.dumps(description, indent=4))
        else:
            json_description = str(json.dumps(description, separators=(',', ':')))
        if len(description) > 0:
            desc_line = desc_line + json_description

        if args.candata:
            can_line = candump_line.rstrip() + " ; "
            if not args.format:
                desc_line = can_line + desc_line
            else:
                formatted_lines = desc_line.splitlines()
                if len(formatted_lines) == 0:
                    desc_line = can_line
                else:
                    first_line = formatted_lines[0]
                    desc_line = can_line + first_line
                    formatted_lines.remove(first_line)

                for line in formatted_lines:
                    desc_line = desc_line + '\n' + ' ' * len(candump_line) + "; " + line

        if len(desc_line) > 0:
            print(desc_line)


if __name__ == '__main__':
    describe = pretty_j1939.describe.get_describer(
                                da_json=args.da_json,
                                describe_pgns=args.pgn,
                                describe_spns=args.spn,
                                describe_link_layer=args.link,
                                describe_transport_layer=args.transport,
                                real_time=args.real_time,
                                include_transport_rawdata=args.candata,
                                include_na=args.include_na)
    if args.candump == '-':
        f = sys.stdin
    else:
        f = open(args.candump, 'r')
    process_lines(f)
