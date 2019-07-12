#!/usr/bin/env python3

import bitstring
import argparse
import json
import pretty_j1939.parse

pretty_j1939.parse.init_j1939db()


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument('candump', help='candump log')
parser.add_argument('--candata', type=str2bool, const=True, default=False, nargs='?',
                    help='print input can data')
parser.add_argument('--pgn',     type=str2bool, const=True, default=True, nargs='?',
                    help='print source/destination/type description')
parser.add_argument('--spn',     type=str2bool, const=True, default=True, nargs='?',
                    help='print signals description')
parser.add_argument('--format',  type=str2bool, const=True, default=False, nargs='?',
                    help='format each structure (otherwise single-line)')

args = parser.parse_args()

bam_descriptions = list()


def process_bam_found(data_bytes, sa, pgn, timestamp):
    bam_descriptions.append(pretty_j1939.parse.describe_data_transfer_complete(data_bytes, sa, pgn, timestamp))


bam_processor = pretty_j1939.parse.get_bam_processor(process_bam_found)

with open(args.candump, 'r') as f:
    for candump_line in f.readlines():
        try:
            timestamp = float(candump_line.split(' ')[0].replace('(', '').replace(')', ''))
            message_id = bitstring.BitString(hex=candump_line.split(' ')[2].split('#')[0])
            message_data = bitstring.BitString(hex=candump_line.split(' ')[2].split('#')[1])

        except IndexError:
            continue
        except ValueError:
            continue

        desc_line = ''

        if args.pgn:
            pgn_desc = pretty_j1939.parse.describe_message_id(message_id.uint)
            if args.format:
                pgn_desc = str(json.dumps(pgn_desc, indent=4))
            else:
                pgn_desc = str(pgn_desc)

            desc_line = desc_line + pgn_desc

        if args.pgn and args.spn:
            if args.format:
                desc_line = desc_line + '\n'
            else:
                desc_line = desc_line + " // "

        if args.spn:
            spn_desc = pretty_j1939.parse.describe_message_data(message_id.uint, message_data.bytes)
            if args.format:
                spn_desc = str(json.dumps(spn_desc, indent=4))
            else:
                spn_desc = str(spn_desc)

            desc_line = desc_line + spn_desc

            pgn, da, sa = pretty_j1939.parse.parse_j1939_id(message_id.uint)
            bam_processor(message_data, message_id.uint, sa, timestamp)
            if len(bam_descriptions) > 0:
                bam_description = bam_descriptions.pop()
                if args.format:
                    bam_description = str(json.dumps(bam_description, indent=4))
                else:
                    bam_description = str(bam_description)

                if args.format:
                    desc_line = desc_line + '\n'
                else:
                    desc_line = desc_line + " // "

                desc_line = desc_line + bam_description

        if args.candata:
            can_line = candump_line.rstrip() + " ; "
            if not args.format:
                desc_line = can_line + desc_line
            else:
                formatted_lines = desc_line.splitlines()
                first_line = formatted_lines[0]
                desc_line = can_line + first_line + '\n'
                formatted_lines.remove(first_line)

                for line in formatted_lines:
                    desc_line = desc_line + ' '*len(candump_line) + "; " + line + '\n'

        print(desc_line)
