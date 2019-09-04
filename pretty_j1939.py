#!/usr/bin/env python3

import bitstring
import argparse
import sys
import json
import pretty_j1939.parse

pretty_j1939.parse.init_j1939db()


parser = argparse.ArgumentParser(description='pretty-printing J1939 candump logs')
parser.add_argument('candump', help='candump log')
parser.add_argument('--candata', action='store_true', help='print input can data')
parser.add_argument('--pgn', action='store_true', default=True, help='print source/destination/type description')
parser.add_argument('--spn', action='store_true', default=True, help='print signals description')
parser.add_argument('--transport', action='store_true', help='print details of transport-layer streams found')
parser.add_argument('--link', action='store_true', default=True, help='print details of link-layer frames found')
parser.add_argument('--include-na', action='store_true', help='include not-available (0xff) SPN values')
parser.add_argument('--format', action='store_true', help='format each structure (otherwise single-line)')
args = parser.parse_args()

describer = pretty_j1939.parse.get_describer(describe_pgns=args.pgn, describe_spns=args.spn,
                                             describe_link_layer=args.link, describe_transport_layer=args.transport,
                                             include_transport_rawdata=args.candata,
                                             include_na=args.include_na)
if __name__ == '__main__':
    with open(args.candump, 'r') as f:
        for candump_line in f.readlines():
            if candump_line == '\n':
                continue

            try:
                timestamp = float(candump_line.split(' ')[0].replace('(', '').replace(')', ''))
                message_id = bitstring.ConstBitArray(hex=candump_line.split(' ')[2].split('#')[0])
                message_data = bitstring.ConstBitArray(hex=candump_line.split(' ')[2].split('#')[1])
            except (IndexError, ValueError):
                print("Warning: error in line '%s'" % candump_line, file=sys.stderr)
                continue

            desc_line = ''

            description = describer(message_data.bytes, message_id.uint)
            if args.format:
                json_description = str(json.dumps(description, indent=4))
            else:
                json_description = str(json.dumps(description, separators=(',', ':')))
            if len(description) > 0:
                desc_line = desc_line + json_description
            else:
                desc_line = ''

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
                        desc_line = desc_line + '\n' + ' '*len(candump_line) + "; " + line

            if len(desc_line) > 0:
                print(desc_line)
