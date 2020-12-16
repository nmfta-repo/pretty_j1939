#
# Copyright (c) 2019 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import json
import bitstring
import sys
from collections import OrderedDict

DA_MASK = 0x0000FF00
SA_MASK = 0x000000FF
PF_MASK = 0x00FF0000
TM_MASK = 0x00EB0000
CM_MASK = 0x00EC0000
ACK_MASK = 0x0E80000

pgn_objects = dict()
spn_objects = dict()
address_names = dict()
bit_encodings = dict()


def init_j1939db(jsondb):
    with open(jsondb, 'r') as j1939_file:
        j1939db = json.load(j1939_file)
        for pgn_label, pgn_object in j1939db['J1939PGNdb'].items():
            pgn_objects.update({int(pgn_label): pgn_object})  # TODO check for all expected fields on each object

        for spn_label, spn_object in j1939db['J1939SPNdb'].items():
            spn_objects.update({int(spn_label): spn_object})  # TODO check for all expected fields on each object

        for address, address_name in j1939db['J1939SATabledb'].items():
            address_names.update({int(address): address_name})  # TODO check for all expected fields on each object

        for spn_label, bit_encoding in j1939db['J1939BitDecodings'].items():
            bit_encodings.update({int(spn_label): bit_encoding})  # TODO check for all expected fields on each object


def get_pgn_object(pgn):
    return pgn_objects.get(pgn)


def get_spn_object(spn):
    return spn_objects.get(spn)


def get_address_name(address):
    return address_names.get(address)


def get_bitencodings_object(spn):
    return bit_encodings.get(spn)


def get_sa(can_id):
    return SA_MASK & can_id


# used for transport reassembly and not called in parse_j1939_id below for speed
def get_da(can_id):
    pf = (PF_MASK & can_id) >> 16
    if pf >= 240:  # PDU2 format
        return 0xFF
    else:
        return (DA_MASK & can_id) >> 8


def parse_j1939_id(can_id):
    sa = get_sa(can_id)
    pf = (PF_MASK & can_id) >> 16
    da = (DA_MASK & can_id) >> 8

    if pf >= 240:  # PDU2 format
        pgn = pf * 256 + da
        da = 0xFF
    else:
        pgn = pf * 256
    return pgn, da, sa


def is_connection_management_message(message_id):
    return (message_id & PF_MASK) == CM_MASK


def is_connection_management_pgn(pgn):
    return pgn == CM_MASK >> 8


def is_data_transfer_message(message_id):
    return (message_id & PF_MASK) == TM_MASK


def is_data_transfer_pgn(pgn):
    return pgn == TM_MASK >> 8


def is_ack_message(message_id):
    return (message_id & PF_MASK) == ACK_MASK


def is_ack_pgn(pgn):
    return pgn == ACK_MASK >> 8


def is_transport_message(message_id):
    return is_data_transfer_message(message_id) or \
           is_connection_management_message(message_id) or \
           is_ack_message(message_id)


def is_transport_pgn(pgn):
    return is_data_transfer_pgn(pgn) or is_connection_management_pgn(pgn) or is_ack_pgn(pgn)


def is_bam_rts_cts_message(message_bytes):
    return (message_bytes[0] == 32 or
            message_bytes[0] == 16)


def get_pgn_acronym(pgn):
    pgn_object = get_pgn_object(pgn)
    if pgn_object is None:
        return "Unknown"
    acronym = pgn_object["Label"]
    if acronym == '':
        acronym = "Unknown"
    return acronym


def get_spn_name(spn):
    spn_object = get_spn_object(spn)
    if spn_object is None:
        return "Unknown"
    return spn_object["Name"]


def get_formatted_address_and_name(address):
    if address == 255:
        formatted_address = "(255)"
        address_name = "All"
    else:
        formatted_address = "({:3d})".format(address)
        address_name = get_address_name(address)
        if address_name is None:
            address_name = "Unknown"
    return formatted_address, address_name


def describe_message_id(message_id):
    description = {}

    pgn, da, sa = parse_j1939_id(message_id)
    da_formatted_address, da_address_name = get_formatted_address_and_name(da)
    sa_formatted_address, sa_address_name = get_formatted_address_and_name(sa)

    description['PGN'] = get_pgn_description(pgn)
    description['DA'] = "%s%s" % (da_address_name, da_formatted_address)
    description['SA'] = "%s%s" % (sa_address_name, sa_formatted_address)
    return description


def get_pgn_description(pgn):
    pgn_acronym = get_pgn_acronym(pgn)
    pgn_description = "%s(%s)" % (pgn_acronym, pgn)
    return pgn_description


def lookup_all_spn_params(_, spn, pgn):
    # look up items in the database
    name = get_spn_name(spn)
    spn_object = get_spn_object(spn)
    units = spn_object["Units"]
    spn_length = spn_object["SPNLength"]
    offset = spn_object["Offset"]

    spn_start = lookup_spn_startbit(spn_object, spn, pgn)

    scale = spn_object["Resolution"]
    if scale <= 0:
        scale = 1

    spn_end = spn_start + spn_length - 1

    return name, offset, scale, spn_end, spn_length, spn_start, units


def lookup_spn_startbit(spn_object, spn, pgn):
    # support earlier versions of J1939db.json which did not include PGN-to-SPN mappings at the PGN
    spn_start = spn_object.get("StartBit")
    if spn_start is None:  # otherwise, use the SPN bit position information at the PGN
        pgn_object = get_pgn_object(pgn)
        spns_in_pgn = pgn_object["SPNs"]
        startbits_in_pgn = pgn_object["SPNStartBits"]
        spn_start = startbits_in_pgn[spns_in_pgn.index(spn)]

        # support earlier versions of J1939db.json which did not include multi-startbit SPNs
        if not type(spn_start) is list:
            spn_start = [spn_start]

    return spn_start


def get_spn_cut_bytes(spn_start, spn_length, message_data_bitstring, last_packet):
    spn_end = spn_start[0] + spn_length - 1
    if not last_packet and spn_end > message_data_bitstring.length:
        return bitstring.Bits(bytes=b'')

    cut_data = message_data_bitstring[spn_start[0]:spn_end + 1]
    if len(spn_start) > 1:
        lsplit = int(spn_start[1] / 8) * 8 - spn_start[0]
        rsplit = spn_length - lsplit
        cut_data = bitstring.BitArray(message_data_bitstring[spn_start[0]:spn_start[0] + lsplit]).append(
            message_data_bitstring[spn_start[1]:spn_start[1] + rsplit])
    return cut_data


def get_spn_bytes(message_data_bitstring, spn, pgn, last_packet):
    spn_object = get_spn_object(spn)
    spn_length = spn_object["SPNLength"]
    spn_start = lookup_spn_startbit(spn_object, spn, pgn)

    if type(spn_length) is str and spn_length.startswith("Variable"):
        delimiter = spn_object.get("Delimiter")
        pgn_object = get_pgn_object(pgn)
        spn_list = pgn_object["SPNs"]
        if delimiter is None:
            if len(spn_list) == 1:
                if last_packet:
                    return get_spn_cut_bytes(spn_start, len(message_data_bitstring.bytes) * 8, message_data_bitstring,
                                             last_packet)
                else:
                    return bitstring.Bits(bytes=b'')
            else:
                print("Warning: skipping SPN %d in non-delimited and multi-spn and variable-length PGN %d"
                      " (this is most-likely a problem in the JSONdb or source DA)" % (spn, pgn), file=sys.stderr)
                return bitstring.Bits(bytes=b'')  # no way to handle multi-spn messages without a delimiter
        else:
            spn_ordinal = spn_list.index(spn)

            delimiter = delimiter.replace('0x', '')
            delimiter = bytes.fromhex(delimiter)
            spn_fields = message_data_bitstring.bytes.split(delimiter)

            if not last_packet and len(spn_fields) == 1:  # delimiter is not found
                return bitstring.Bits(bytes=b'')

            if spn_start != [-1]:  # variable-len field with defined start; must be first variable-len field
                spn_end = len(spn_fields[0]) * 8 - 1
                cut_data = bitstring.Bits(bytes=spn_fields[0])[spn_start[0]:spn_end + 1]
                return cut_data
            else:  # variable-len field with unspecified start; requires field counting
                startbits_list = pgn_object["SPNStartBits"]
                num_fixedlen_spn_fields = sum(1 for s in startbits_list if s != -1)
                variable_spn_ordinal = spn_ordinal - num_fixedlen_spn_fields
                if num_fixedlen_spn_fields > 0:
                    variable_spn_fields = spn_fields[1:]
                else:
                    variable_spn_fields = spn_fields
                try:
                    cut_data = bitstring.Bits(bytes=variable_spn_fields[variable_spn_ordinal])
                except IndexError:
                    cut_data = bitstring.Bits(bytes=b'')
                return cut_data
    else:
        return get_spn_cut_bytes(spn_start, spn_length, message_data_bitstring, last_packet)


def is_spn_bitencoded(spn_units):
    return spn_units.lower() in ("bit", "binary",)


def is_spn_numerical_values(spn_units):
    norm_units = spn_units.lower()
    return norm_units not in ("manufacturer determined", "byte", "", "request dependent", "ascii")


# returns a float in units of the SPN, or None if the value if the SPN value is not available in the message_data
#   if validate == True, raises a ValueError if the value is present in message_data but is beyond the operational range
def get_spn_value(message_data_bitstring, spn, pgn, last_packet, validate=True):
    spn_object = get_spn_object(spn)
    units = spn_object["Units"]

    offset = spn_object["Offset"]
    scale = spn_object["Resolution"]
    if scale <= 0:
        scale = 1

    cut_data = bitstring.BitArray(get_spn_bytes(message_data_bitstring, spn, pgn, last_packet))
    if cut_data.length == 0:  # incomplete SPN
        return []

    if cut_data.all(True):  # value unavailable in message_data
        return None

    cut_data.byteswap()
    if is_spn_bitencoded(units):
        value = cut_data.uint
    else:
        value = cut_data.uint * scale + offset

        if validate:
            operational_min = spn_object["OperationalLow"]
            operational_max = spn_object["OperationalHigh"]
            if value < operational_min or value > operational_max:
                raise ValueError

    return value


def describe_message_data(pgn, message_data_bitstring, last_packet, include_na=False, spn_coverage=None):
    if spn_coverage is None:
        spn_coverage = {}
    description = OrderedDict()
    if is_transport_pgn(pgn):  # transport messages can't be accurately parsed by the DA description
        return description

    pgn_object = get_pgn_object(pgn)
    for spn in pgn_object["SPNs"]:
        if spn_coverage.get(spn, ()) != ():  # skip any SPNs that have already been processed.
            continue
        spn_name = get_spn_name(spn)
        spn_units = get_spn_object(spn)["Units"]
        spn_not_covered_yet = False

        try:
            if is_spn_numerical_values(spn_units):
                spn_value = get_spn_value(message_data_bitstring, spn, pgn, last_packet)
                if not spn_value:
                    spn_not_covered_yet = True
                else:
                    if spn_value is None:
                        if include_na:
                            description[spn_name] = "N/A"
                        else:
                            continue
                    elif is_spn_bitencoded(spn_units):
                        try:
                            enum_descriptions = get_bitencodings_object(spn)
                            if enum_descriptions is None:
                                description[spn_name] = "%d (Unknown)" % spn_value
                                continue
                            spn_value_description = enum_descriptions[str(int(spn_value))].strip()
                            description[spn_name] = "%d (%s)" % (spn_value, spn_value_description)
                        except KeyError:
                            description[spn_name] = "%d (Unknown)" % spn_value
                    else:
                        description[spn_name] = "%s [%s]" % (spn_value, spn_units)
            else:
                spn_bytes = get_spn_bytes(message_data_bitstring, spn, pgn, last_packet)
                if spn_bytes.length == 0:
                    spn_not_covered_yet = True
                else:
                    if spn_units.lower() in ("request dependent",):
                        description[spn_name] = "%s (%s)" % (spn_bytes, spn_units)
                    elif spn_units.lower() in ("ascii",):
                        description[spn_name] = "%s" % spn_bytes.bytes.decode(encoding="utf-8")
                    else:
                        description[spn_name] = "%s" % spn_bytes

        except ValueError:
            description[spn_name] = "%s (%s)" % (
                get_spn_bytes(message_data_bitstring, spn, pgn, last_packet), "Out of range")

        if not spn_not_covered_yet:
            spn_coverage[spn] = (spn_name, description[spn_name])

    return description


def get_bam_processor(process_bam_found, is_real_time):
    new_pgn = {}
    new_data = {}
    new_count = {}
    new_length = {}
    spn_coverage = {}

    def process_for_bams(message_bytes, message_id):
        sa = get_sa(message_id)
        da = get_da(message_id)
        if is_connection_management_message(message_id) and is_bam_rts_cts_message(message_bytes):  # track new conn
            new_pgn[(da, sa)] = (message_bytes[7] << 16) + (message_bytes[6] << 8) + message_bytes[5]
            new_length[(da, sa)] = (message_bytes[2] << 8) + message_bytes[1]
            new_count[(da, sa)] = message_bytes[3]
            new_data[(da, sa)] = [None for _ in range(7 * new_count[(da, sa)])]
        elif is_data_transfer_message(message_id):
            if (da, sa) in new_data.keys():
                packet_number = message_bytes[0]
                for b, i in zip(message_bytes[1:], range(7)):
                    try:
                        new_data[(da, sa)][7 * (packet_number - 1) + i] = b
                    except Exception as e:
                        print(e)
                is_last_packet = packet_number == new_count[(da, sa)]

                if is_real_time:
                    data_bytes = new_data[(da, sa)][0:packet_number * 7]
                    if None not in data_bytes:
                        data_bytes = bytes(data_bytes)
                        process_bam_found(data_bytes, sa, new_pgn[(da, sa)],
                                          spn_coverage=spn_coverage,
                                          is_last_packet=is_last_packet)
                elif is_last_packet:
                    data_bytes = new_data[(da, sa)][0:new_length[(da, sa)]]
                    if None not in data_bytes:
                        data_bytes = bytes(data_bytes)
                        process_bam_found(data_bytes, sa, new_pgn[(da, sa)],
                                          is_last_packet=True)
    return process_for_bams


def get_describer(describe_pgns=True, describe_spns=True, describe_link_layer=True, describe_transport_layer=True,
                  include_transport_rawdata=True, include_na=False, real_time=False):
    transport_messages = list()

    def process_bam_found(data_bytes, sa, pgn, spn_coverage=None, is_last_packet=False):
        if spn_coverage is None:
            spn_coverage = {}
        transport_found = dict()
        transport_found['PGN'] = pgn
        transport_found['SA'] = sa
        transport_found['data'] = data_bytes
        transport_found['spn_coverage'] = spn_coverage
        transport_found['is_last_packet'] = is_last_packet
        transport_messages.append(transport_found)

    bam_processor = get_bam_processor(process_bam_found, real_time)

    def describer(message_data_bytes: bitstring.Bits, message_id_uint: bitstring.Bits):
        transport_messages.clear()
        bam_processor(message_data_bytes, message_id_uint)

        description = OrderedDict()

        if describe_link_layer:
            if describe_pgns:
                description.update(describe_message_id(message_id_uint))

            if describe_spns:
                pgn, _, _ = parse_j1939_id(message_id_uint)
                description.update(
                    describe_message_data(pgn, bitstring.Bits(bytes=message_data_bytes), last_packet=True,
                                          include_na=include_na))

        if describe_transport_layer and len(transport_messages) > 0:
            if describe_pgns:
                description.update({'Transport PGN': get_pgn_description(transport_messages[0]['PGN'])})

            if include_transport_rawdata:
                description.update({'Transport Data': str(bitstring.Bits(bytes=transport_messages[0]['data']))})

            if describe_spns:
                pgn = transport_messages[0]['PGN']
                description.update(describe_message_data(pgn, bitstring.Bits(bytes=transport_messages[0]['data']),
                                                         last_packet=transport_messages[0]['is_last_packet'],
                                                         spn_coverage=transport_messages[0]['spn_coverage']))

        return description

    return describer
