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


def init_j1939db():
    with open("J1939db.json", 'r') as j1939_file:
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


def is_bam_cts_message(message_bytes):
    return message_bytes[0] == 32


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


def lookup_all_spn_params(callback, spn, pgn):
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

    return spn_start


def get_spn_bytes(message_data_bitstring, spn, pgn):
    spn_object = get_spn_object(spn)
    spn_length = spn_object["SPNLength"]
    spn_start = lookup_spn_startbit(spn_object, spn, pgn)

    if type(spn_length) is str and spn_length.startswith("Variable"):
        delimiter = spn_object.get("Delimiter")
        pgn_object = get_pgn_object(pgn)
        spn_list = pgn_object["SPNs"]
        if delimiter is None:
            if len(spn_list) == 1:
                spn_end = len(message_data_bitstring.bytes) * 8 - 1
                cut_data = message_data_bitstring[spn_start:spn_end + 1]
                return cut_data
            else:
                print("Warning: skipping SPN %d in non-delimited and multi-spn and variable-length PGN %d"
                      " (this is most-likely a problem in the JSONdb or source DA)" % (spn, pgn), file=sys.stderr)
                return bitstring.Bits(bytes=b'')  # no way to handle multi-spn messages without a delimiter
        else:
            spn_ordinal = spn_list.index(spn)

            delimiter = delimiter.replace('0x', '')
            delimiter = bytes.fromhex(delimiter)
            spn_fields = message_data_bitstring.bytes.split(delimiter)

            if spn_start != -1:  # variable-len field with defined start; must be first variable-len field
                spn_end = len(spn_fields[0]) * 8 - 1
                cut_data = bitstring.Bits(bytes=spn_fields[0])[spn_start:spn_end + 1]
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
        spn_end = spn_start + spn_length - 1
        cut_data = message_data_bitstring[spn_start:spn_end + 1]
        return cut_data


def is_spn_bitencoded(spn_units):
    return spn_units.lower() in ("bit", "binary",)


def is_spn_numerical_values(spn_units):
    norm_units = spn_units.lower()
    return norm_units not in ("manufacturer determined", "byte", "", "request dependent", "ascii")


# returns a float in units of the SPN, or None if the value if the SPN value is not available in the message_data
#   if validate == True, raises a ValueError if the value is present in message_data but is beyond the operational range
def get_spn_value(message_data_bitstring, spn, pgn, validate=True):
    spn_object = get_spn_object(spn)
    units = spn_object["Units"]

    offset = spn_object["Offset"]
    scale = spn_object["Resolution"]
    if scale <= 0:
        scale = 1

    cut_data = bitstring.BitArray(get_spn_bytes(message_data_bitstring, spn, pgn))
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


def describe_message_data(pgn, message_data_bitstring, include_na=False):
    description = OrderedDict()
    if is_transport_pgn(pgn):  # transport messages can't be accurately parsed by the DA description
        return description

    pgn_object = get_pgn_object(pgn)
    for spn in pgn_object["SPNs"]:
        spn_name = get_spn_name(spn)
        spn_units = get_spn_object(spn)["Units"]

        try:
            if is_spn_numerical_values(spn_units):
                spn_value = get_spn_value(message_data_bitstring, spn, pgn)
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
                spn_bytes = get_spn_bytes(message_data_bitstring, spn, pgn)
                if spn_units.lower() in ("request dependent",):
                    description[spn_name] = "%s (%s)" % (spn_bytes, spn_units)
                elif spn_units.lower() in ("ascii",):
                    description[spn_name] = "%s" % spn_bytes.bytes.decode(encoding="utf-8")
                else:
                    description[spn_name] = "%s" % spn_bytes

        except ValueError:
            description[spn_name] = "%s (%s)" % (get_spn_bytes(message_data_bitstring, spn, pgn), "Out of range")

    return description


def get_bam_processor(process_bam_found):
    new_pgn = {}
    new_data = {}
    new_packets = {}
    new_length = {}

    def process_for_bams(message_bytes, message_id):
        sa = get_sa(message_id)
        if is_connection_management_message(message_id):
            if is_bam_cts_message(message_bytes):  # BAM,CTS
                new_pgn[sa] = (message_bytes[7] << 16) + (message_bytes[6] << 8) + message_bytes[5]
                new_length[sa] = (message_bytes[2] << 8) + message_bytes[1]
                new_packets[sa] = message_bytes[3]
                new_data[sa] = [0xFF for i in range(7 * new_packets[sa])]

        elif is_data_transfer_message(message_id):
            if sa in new_data.keys():
                for b, i in zip(message_bytes[1:], range(7)):
                    try:
                        new_data[sa][i + 7 * (message_bytes[0] - 1)] = b
                    except Exception as e:
                        print(e)
                if message_bytes[0] == new_packets[sa]:
                    data_bytes = bytes(new_data[sa][0:new_length[sa]])
                    process_bam_found(data_bytes, sa, new_pgn[sa])

    return process_for_bams


def get_describer(describe_pgns=True, describe_spns=True,
                  describe_link_layer=True, describe_transport_layer=True,
                  include_transport_rawdata=True, include_na=False):

    transport_messages = list()

    def process_bam_found(data_bytes, sa, pgn):
        transport_found = dict()
        transport_found['PGN'] = pgn
        transport_found['SA'] = sa
        transport_found['data'] = data_bytes
        transport_messages.append(transport_found)

    bam_processor = get_bam_processor(process_bam_found)

    def describer(message_data_bytes, message_id_uint):
        transport_messages.clear()
        bam_processor(message_data_bytes, message_id_uint)

        description = OrderedDict()

        if describe_link_layer:
            if describe_pgns:
                description.update(describe_message_id(message_id_uint))

            if describe_spns:
                pgn, _, _ = parse_j1939_id(message_id_uint)
                description.update(describe_message_data(pgn, bitstring.Bits(bytes=message_data_bytes), include_na=include_na))

        if describe_transport_layer and len(transport_messages) > 0:
            if describe_pgns:
                description.update({'Transport PGN': get_pgn_description(transport_messages[0]['PGN'])})

            if include_transport_rawdata:
                description.update({'Transport Data': str(bitstring.Bits(bytes=transport_messages[0]['data']))})

            if describe_spns:
                pgn = transport_messages[0]['PGN']
                description.update(describe_message_data(pgn, bitstring.Bits(bytes=transport_messages[0]['data'])))

        return description

    return describer
