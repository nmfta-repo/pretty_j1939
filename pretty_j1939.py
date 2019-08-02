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
parser.add_argument('--transport', type=str2bool, const=True, default=True, nargs='?',
                    help='print details of transport-layer streams found')
parser.add_argument('--link', type=str2bool, const=True, default=True, nargs='?',
                    help='print details of link-layer frames found')
parser.add_argument('--format',  type=str2bool, const=True, default=False, nargs='?',
                    help='format each structure (otherwise single-line)')

args = parser.parse_args()

transport_messages = list()


def process_bam_found(data_bytes, sa, pgn):
    transport_found = dict()
    transport_found['PGN'] = pgn
    transport_found['data'] = data_bytes
    transport_messages.append(transport_found)


def add_separator(desc_line):
    if args.format:
        desc_line = desc_line + '\n'
    else:
        desc_line = desc_line + " // "
    return desc_line


def add_description(desc_line, json_object):
    if args.format:
        json_description = str(json.dumps(json_object, indent=4))
    else:
        json_description = str(json_object)
    desc_line = desc_line + json_description
    return desc_line


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

        any_described = False
        transport_messages.clear()
        bam_processor(message_data.bytes, message_id.uint)
        desc_line = ''

        if args.link:
            if args.pgn:
                pgn_desc = pretty_j1939.parse.describe_message_id(message_id.uint)
                desc_line = add_description(desc_line, pgn_desc)
                any_described = True

            if args.spn:
                pgn, _, _ = pretty_j1939.parse.parse_j1939_id(message_id.uint)
                spn_desc = pretty_j1939.parse.describe_message_data(pgn, message_data.bytes)
                if any_described:
                    desc_line = add_separator(desc_line)
                desc_line = add_description(desc_line, spn_desc)
                any_described = True

        if args.transport and len(transport_messages) > 0:
            if args.pgn:
                transport_pgn_description = dict()
                transport_pgn_description['Transport PGN'] = pretty_j1939.parse.get_pgn_description(transport_messages[0]['PGN'])
                if any_described:
                    desc_line = add_separator(desc_line)
                desc_line = add_description(desc_line, transport_pgn_description)
                any_described = True

            if args.candata:
                transport_data_description = dict()
                transport_data_description['Transport Data'] = str(bitstring.BitString(transport_messages[0]['data']))
                if any_described:
                    desc_line = add_separator(desc_line)
                desc_line = add_description(desc_line, transport_data_description)
                any_described = True

            if args.spn:
                pgn = transport_messages[0]['PGN']
                spn_desc = pretty_j1939.parse.describe_message_data(pgn, transport_messages[0]['data'])
                if any_described:
                    desc_line = add_separator(desc_line)
                desc_line = add_description(desc_line, spn_desc)
                any_described = True

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
