#!/usr/bin/env python3

import bitstring
import argparse
import sys
import json
import pretty_j1939.parse

pretty_j1939.parse.init_j1939db()


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


parser = argparse.ArgumentParser(description='pretty-printing J1939 candump logs')
parser.add_argument('candump', help='candump log')
parser.add_argument('--candata', type=str2bool, const=True, default=False, nargs='?',
                    help='print input can data')
parser.add_argument('--pgn',     type=str2bool, const=True, default=True, nargs='?',
                    help='print source/destination/type description')
parser.add_argument('--spn',     type=str2bool, const=True, default=True, nargs='?',
                    help='print signals description')
parser.add_argument('--transport', type=str2bool, const=True, default=True, nargs='?',
                    help='print details of transport-layer streams found')
parser.add_argument('--link', type=str2bool, const=True, default=True, nargs='?',
                    help='print details of link-layer frames found')
parser.add_argument('--include-na', type=str2bool, const=True, default=False, nargs='?',
                    help='inlude not-available (0xff) SPN values')
parser.add_argument('--format',  type=str2bool, const=True, default=False, nargs='?',
                    help='format each structure (otherwise single-line)')

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
                message_id = bitstring.BitString(hex=candump_line.split(' ')[2].split('#')[0])
                message_data = bitstring.BitString(hex=candump_line.split(' ')[2].split('#')[1])

            except IndexError:
                print("Warning: error in line '%s'" % candump_line, file=sys.stderr)
                continue
            except ValueError:
                print("Warning: error in line '%s'" % candump_line, file=sys.stderr)
                continue

            desc_line = ''

            description = describer(message_data.bytes, message_id.uint)
            if args.format:
                json_description = str(json.dumps(description, indent=4))
            else:
                json_description = str(json.dumps(description, separators=(',', ':')))
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
                        desc_line = desc_line + '\n' + ' '*len(candump_line) + "; " + line

            if len(desc_line) > 0:
                print(desc_line)
