import argparse
import json
import sys

import bitstring

from pretty_j1939.prettify import Prettyfier


parser = argparse.ArgumentParser(description='pretty-printing J1939 candump logs')
parser.add_argument('candump', help='candump log')

parser.add_argument('--candata',    dest='candata', action='store_true',  help='print input can data')
parser.add_argument('--no-candata', dest='candata', action='store_false', help='(default)')
parser.set_defaults(candata=False)

parser.add_argument('--pgn',    dest='pgn', action='store_true', help='(default) print source/destination/type '
                                                                      'description')
parser.add_argument('--no-pgn', dest='pgn', action='store_false')
parser.set_defaults(pgn=True)

parser.add_argument('--spn',    dest='spn', action='store_true', help='(default) print signals description')
parser.add_argument('--no-spn', dest='spn', action='store_false')
parser.set_defaults(spn=True)

parser.add_argument('--transport',    dest='transport', action='store_true',  help='print details of transport-layer '
                                                                                   'streams found')
parser.add_argument('--no-transport', dest='transport', action='store_false', help='(default)')
parser.set_defaults(transport=False)

parser.add_argument('--link',    dest='link', action='store_true', help='(default) print details of link-layer frames '
                                                                        'found')
parser.add_argument('--no-link', dest='link', action='store_false')
parser.set_defaults(link=True)

parser.add_argument('--include_na',    dest='include_na', action='store_true',  help='include not-available (0xff) SPN '
                                                                                     'values')
parser.add_argument('--no-include_na', dest='include_na', action='store_false', help='(default)')
parser.set_defaults(include_na=False)

parser.add_argument('--format',    dest='format', action='store_true',  help='format each structure (otherwise '
                                                                             'single-line)')
parser.add_argument('--no-format', dest='format', action='store_false', help='(default)')
parser.set_defaults(format=False)

parser.add_argument('--da-json', type=str, const=True, required=True, nargs='?',
                    help='absolute path to the input JSON DA is required')  # Changed added new argument to take DA-JSON

parser.add_argument('--real_time',    dest='real_time', action='store_true',  help='prettify SPNs as they are seen in '
                                                                                   'transport sessions') # Changed to
# transport interpretation per TP.DT
parser.add_argument('--no-real_time', dest='real_time', action='store_false', help='(default)')
parser.set_defaults(real_time=False)

args = parser.parse_args()

if __name__ == '__main__':
    prettyfier = Prettyfier(args.da_json, real_time=args.real_time, describe_pgns=args.pgn, describe_spns=args.spn,
                            describe_link_layer=args.link, describe_transport_layer=args.transport,
                            include_transport_rawdata=args.candata,
                            include_na=args.include_na)
    with open(args.candump, 'r') as f:
        for candump_line in f.readlines():
            if candump_line == '\n':
                continue
            try:
                timestamp = float(candump_line.split()[0].lstrip('(').rstrip(')'))
                message = candump_line.split()[2]
                message_id = bitstring.Bits(hex=message.split('#')[0])
                message_data = bitstring.Bits(hex=message.split('#')[1])
            except (IndexError, ValueError):
                print("Warning: error in line '%s'" % candump_line, file=sys.stderr)
                continue

            desc_line = ''

            description = prettyfier.describer(message_data.bytes, message_id.uint)
            print('RAW: ', json.loads(json.dumps(description)))
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
