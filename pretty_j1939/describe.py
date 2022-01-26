#
# Copyright (c) 2019 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import json
import bitstring
import sys
import math
from collections import OrderedDict

PGN_LABEL = 'PGN'

NA_NAN = float('nan')
EMPTY_BITS = bitstring.ConstBitArray(bytes=b'')

DA_MASK = 0x0000FF00
SA_MASK = 0x000000FF
PF_MASK = 0x00FF0000
TM_MASK = 0x00EB0000
CM_MASK = 0x00EC0000
ACK_MASK = 0x0E80000


class DADescriber:
    pgn_objects = dict()
    spn_objects = dict()
    address_names = dict()
    bit_encodings = dict()

    def __init__(self, da_json, describe_pgns, describe_spns, describe_link_layer, describe_transport_layer,
                 real_time, include_transport_rawdata, include_na):
        with open(da_json, 'r') as j1939_file:
            j1939db = json.load(j1939_file)
            for pgn_label, pgn_object in j1939db['J1939PGNdb'].items():
                # TODO check for all expected fields on each object
                self.pgn_objects.update({int(pgn_label): pgn_object})

            for spn_label, spn_object in j1939db['J1939SPNdb'].items():
                # TODO check for all expected fields on each object
                self.spn_objects.update({int(spn_label): spn_object})

            for address, address_name in j1939db['J1939SATabledb'].items():
                # TODO check for all expected fields on each object
                self.address_names.update({int(address): address_name})

            for spn_label, bit_encoding in j1939db['J1939BitDecodings'].items():
                # TODO check for all expected fields on each object
                self.bit_encodings.update({int(spn_label): bit_encoding})
        self.da_json = da_json
        self.describe_pgns = describe_pgns
        self.describe_spns = describe_spns
        self.describe_link_layer = describe_link_layer
        self.describe_transport_layer = describe_transport_layer
        self.real_time = real_time
        self.include_transport_rawdata = include_transport_rawdata
        self.include_na = include_na

    def get_pgn_acronym(self, pgn):
        pgn_object = self.pgn_objects.get(pgn)
        if pgn_object is None:
            return "Unknown"
        acronym = pgn_object["Label"]
        if acronym == '':
            acronym = "Unknown"
        return acronym

    def get_spn_name(self, spn):
        spn_object = self.spn_objects.get(spn)
        if spn_object is None:
            return "Unknown"
        return spn_object["Name"]

    def get_formatted_address_and_name(self, address):
        if address == 255:
            formatted_address = "(255)"
            address_name = "All"
        else:
            formatted_address = "({:3d})".format(address)
            address_name = self.address_names.get(address)
            if address_name is None:
                address_name = "Unknown"
        return formatted_address, address_name

    def describe_message_id(self, message_id):
        description = {}

        pgn, da, sa = parse_j1939_id(message_id)
        da_formatted_address, da_address_name = self.get_formatted_address_and_name(da)
        sa_formatted_address, sa_address_name = self.get_formatted_address_and_name(sa)

        description['PGN'] = self.get_pgn_description(pgn)
        description['DA'] = "%s%s" % (da_address_name, da_formatted_address)
        description['SA'] = "%s%s" % (sa_address_name, sa_formatted_address)
        return description

    def get_pgn_description(self, pgn):
        pgn_acronym = self.get_pgn_acronym(pgn)
        pgn_description = "%s(%s)" % (pgn_acronym, pgn)
        return pgn_description

    def lookup_all_spn_params(self, _, spn, pgn):
        # look up items in the database
        name = self.get_spn_name(spn)
        spn_object = self.spn_objects.get(spn, {})
        units = spn_object["Units"]
        spn_length = spn_object["SPNLength"]
        offset = spn_object["Offset"]

        spn_start = self.lookup_spn_startbit(spn_object, spn, pgn)

        scale = spn_object["Resolution"]
        if scale <= 0:
            scale = 1

        spn_end = spn_start + spn_length - 1

        return name, offset, scale, spn_end, spn_length, spn_start, units

    def lookup_spn_startbit(self, spn_object, spn, pgn):
        # support earlier versions of J1939db.json which did not include PGN-to-SPN mappings at the PGN
        spn_start = spn_object.get("StartBit")
        if spn_start is None:  # otherwise, try to use the SPN bit position information at the PGN
            pgn_object = self.pgn_objects.get(pgn, {})
            spns_in_pgn = pgn_object["SPNs"]
            startbits_in_pgn = pgn_object["SPNStartBits"]
            spn_start = startbits_in_pgn[spns_in_pgn.index(spn)]

            # finally, support earlier versions of J1939db.json which did not include multi-startbit SPNs
            if not type(spn_start) is list:
                spn_start = [spn_start]

        return spn_start

    def get_spn_bytes(self, message_data_bitstring, spn, pgn, is_complete_message):
        spn_object = self.spn_objects.get(spn, {})
        spn_length = spn_object["SPNLength"]
        spn_start = self.lookup_spn_startbit(spn_object, spn, pgn)

        if type(spn_length) is str and spn_length.startswith("Variable"):
            delimiter = spn_object.get("Delimiter")
            pgn_object = self.pgn_objects.get(pgn, {})
            spn_list = pgn_object["SPNs"]
            if delimiter is None:
                if len(spn_list) == 1:
                    if is_complete_message:
                        return get_spn_cut_bytes(spn_start, len(message_data_bitstring.bytes) * 8,
                                                 message_data_bitstring, is_complete_message)
                    else:
                        return EMPTY_BITS
                else:
                    print("Warning: skipping SPN %d in non-delimited and multi-spn and variable-length PGN %d"
                          " (this is most-likely a problem in the JSONdb or source DA)" % (spn, pgn), file=sys.stderr)
                    return EMPTY_BITS  # no way to handle multi-spn messages without a delimiter
            else:
                spn_ordinal = spn_list.index(spn)

                delimiter = delimiter.replace('0x', '')
                delimiter = bytes.fromhex(delimiter)
                spn_fields = message_data_bitstring.bytes.split(delimiter)

                if not is_complete_message and len(spn_fields) == 1:  # delimiter is not found
                    return EMPTY_BITS

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
                        cut_data = EMPTY_BITS
                    return cut_data
        else:
            return get_spn_cut_bytes(spn_start, spn_length, message_data_bitstring, is_complete_message)

    # returns a float in units of the SPN, or NaN if the value of the SPN value is not available in the message_data, or
    #   None if the message is incomplete and SPN data is not available.
    #   if validate == True, raises a ValueError if the value is present in message_data but is beyond the operational
    #   range
    def get_spn_value(self, message_data_bitstring, spn, pgn, is_complete_message, validate=True):
        spn_object = self.spn_objects.get(spn, {})
        units = spn_object["Units"]

        offset = spn_object["Offset"]
        scale = spn_object["Resolution"]
        if scale <= 0:
            scale = 1

        cut_data = bitstring.BitArray(self.get_spn_bytes(message_data_bitstring, spn, pgn, is_complete_message))
        if (not is_complete_message) and cut_data.length == 0:  # incomplete SPN
            return None

        if cut_data.all(True):  # value unavailable in message_data
            return NA_NAN

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

    def describe_message_data(self, pgn, message_data_bitstring, is_complete_message=True, skip_spns=None):
        if skip_spns is None:  # TODO have one default for skip_spns
            skip_spns = {}
        description = OrderedDict()
        if is_transport_pgn(pgn):  # transport messages can't be accurately parsed by the DA description
            return description

        pgn_object = self.pgn_objects.get(pgn, {})
        for spn in pgn_object.get("SPNs", []):
            if skip_spns.get(spn, ()) != ():  # skip any SPNs that have already been processed.
                continue
            spn_name = self.get_spn_name(spn)
            spn_units = self.spn_objects.get(spn)["Units"]

            def mark_spn_covered(new_spn, new_spn_name, new_spn_description):
                skip_spns[new_spn] = (new_spn_name, new_spn_description)  # TODO: move this closer to real-time handling

            def add_spn_description(new_spn, new_spn_name, new_spn_description):
                description[new_spn_name] = new_spn_description
                mark_spn_covered(new_spn, new_spn_name, new_spn_description)

            try:
                if is_spn_numerical_values(spn_units):
                    spn_value = self.get_spn_value(message_data_bitstring, spn, pgn, is_complete_message)
                    if (not is_complete_message) and (spn_value is None):  # incomplete message
                        continue
                    elif math.isnan(spn_value):
                        if self.include_na:
                            add_spn_description(spn, spn_name, "N/A")
                        else:
                            mark_spn_covered(spn, spn_name, "N/A")
                    elif is_spn_bitencoded(spn_units):
                        try:
                            enum_descriptions = self.bit_encodings.get(spn)
                            if enum_descriptions is None:
                                add_spn_description(spn, spn_name, "%d (Unknown)" % spn_value)
                                continue
                            spn_value_description = enum_descriptions[str(int(spn_value))].strip()
                            add_spn_description(spn, spn_name, "%d (%s)" % (spn_value, spn_value_description))
                        except KeyError:
                            add_spn_description(spn, spn_name, "%d (Unknown)" % spn_value)
                    else:
                        add_spn_description(spn, spn_name, "%s [%s]" % (spn_value, spn_units))
                else:
                    spn_bytes = self.get_spn_bytes(message_data_bitstring, spn, pgn, is_complete_message)
                    if spn_bytes.length == 0 and not is_complete_message:  # incomplete message
                        continue
                    else:
                        if spn_units.lower() in ("request dependent",):
                            add_spn_description(spn, spn_name, "%s (%s)" % (spn_bytes, spn_units))
                        elif spn_units.lower() in ("ascii",):
                            add_spn_description(spn, spn_name, "%s" % spn_bytes.bytes.decode(encoding="utf-8"))
                        else:
                            add_spn_description(spn, spn_name, "%s" % spn_bytes)

            except ValueError:
                add_spn_description(spn, spn_name, "%s (%s)" % (
                    self.get_spn_bytes(message_data_bitstring, spn, pgn, is_complete_message), "Out of range"))

        return description


def parse_j1939_id(can_id):
    sa = SA_MASK & can_id
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


def get_spn_cut_bytes(spn_start, spn_length, message_data_bitstring, is_complete_message):
    spn_end = spn_start[0] + spn_length - 1
    if not is_complete_message and spn_end > message_data_bitstring.length:
        return bitstring.Bits(bytes=b'')

    cut_data = message_data_bitstring[spn_start[0]:spn_end + 1]
    if len(spn_start) > 1:
        lsplit = int(spn_start[1] / 8) * 8 - spn_start[0]
        rsplit = spn_length - lsplit
        b = bitstring.BitArray(message_data_bitstring[spn_start[0]:spn_start[0] + lsplit])
        b.append(message_data_bitstring[spn_start[1]:spn_start[1] + rsplit])
        cut_data = b
    return cut_data


def is_spn_bitencoded(spn_units):
    return spn_units.lower() in ("bit", "binary",)


def is_spn_numerical_values(spn_units):
    norm_units = spn_units.lower()
    return norm_units not in ("manufacturer determined", "byte", "", "request dependent", "ascii")


class TransportTracker:
    new_pgn = {}
    new_data = {}
    new_count = {}
    new_length = {}
    spn_coverage = {}

    def __init__(self, real_time):
        self.is_real_time = real_time

    def process(self, transport_found_processor, message_bytes, message_id):
        _, da, sa = parse_j1939_id(message_id)
        if is_connection_management_message(message_id) and is_bam_rts_cts_message(message_bytes):  # track new conn
            self.new_pgn[(da, sa)] = (message_bytes[7] << 16) + (message_bytes[6] << 8) + message_bytes[5]
            self.new_length[(da, sa)] = (message_bytes[2] << 8) + message_bytes[1]
            self.new_count[(da, sa)] = message_bytes[3]
            self.new_data[(da, sa)] = [None for _ in range(7 * self.new_count[(da, sa)])]
        elif is_data_transfer_message(message_id):
            if (da, sa) in self.new_data.keys():
                packet_number = message_bytes[0]
                for b, i in zip(message_bytes[1:], range(7)):
                    try:
                        self.new_data[(da, sa)][7 * (packet_number - 1) + i] = b
                    except Exception as e:
                        print(e)
                is_last_packet = packet_number == self.new_count[(da, sa)]

                if self.is_real_time:
                    data_bytes = self.new_data[(da, sa)][0:packet_number * 7]
                    if None not in data_bytes:
                        data_bytes = bytes(data_bytes)
                        transport_found_processor(data_bytes, sa, self.new_pgn[(da, sa)],
                                                  spn_coverage=self.spn_coverage,
                                                  is_last_packet=is_last_packet)
                elif is_last_packet:
                    data_bytes = self.new_data[(da, sa)][0:self.new_length[(da, sa)]]
                    if None not in data_bytes:
                        data_bytes = bytes(data_bytes)
                        transport_found_processor(data_bytes, sa, self.new_pgn[(da, sa)],
                                                  is_last_packet=True)


class J1939Describer:
    da_describer: DADescriber = None
    transport_tracker: TransportTracker = None

    def __init__(self, describe_link_layer, describe_pgns, describe_spns, describe_transport_layer,
                 include_transport_rawdata, include_na):
        self.describe_link_layer = describe_link_layer
        self.describe_pgns = describe_pgns
        self.describe_spns = describe_spns
        self.describe_transport_layer = describe_transport_layer
        self.include_transport_rawdata = include_transport_rawdata
        self.include_na = include_na

        self.transport_messages = list()

    def set_da_describer(self, da_describer):
        self.da_describer = da_describer

    def set_transport_tracker(self, transport_tracker):
        self.transport_tracker = transport_tracker

    def __call__(self, message_data_bytes: bitstring.Bits, message_id_uint: bitstring.Bits):
        self.transport_messages.clear()

        def on_transport_found(data_bytes, found_sa, found_pgn, spn_coverage=None, is_last_packet=False):
            if spn_coverage is None:
                spn_coverage = {}
            transport_found = dict()
            transport_found[PGN_LABEL] = found_pgn
            transport_found['SA'] = found_sa
            transport_found['data'] = data_bytes
            transport_found['spn_coverage'] = spn_coverage
            transport_found['is_last_packet'] = is_last_packet
            self.transport_messages.append(transport_found)

        is_transport_lower_layer_message = is_transport_message(message_id_uint)
        if is_transport_lower_layer_message and self.describe_transport_layer:
            self.transport_tracker.process(on_transport_found, message_data_bytes, message_id_uint)

        description = OrderedDict()

        is_describe_this_frame = (not is_transport_lower_layer_message)  # always print 'complete' J1939 frames
        is_describe_this_frame |= is_transport_lower_layer_message \
            and self.describe_link_layer  # or others when configured to describe 'link layer' frames

        if is_describe_this_frame:
            if self.describe_pgns:
                description.update(self.da_describer.describe_message_id(message_id_uint))

            if self.describe_spns:
                pgn, _, _ = parse_j1939_id(message_id_uint)
                message_description = self.da_describer. \
                    describe_message_data(pgn,
                                          bitstring.Bits(bytes=message_data_bytes),
                                          is_complete_message=True)
                description.update(message_description)

        if self.describe_transport_layer and len(self.transport_messages) > 0:
            transport_message = self.transport_messages[0]
            transport_pgn = transport_message[PGN_LABEL]
            if self.describe_pgns:
                description.update(self.da_describer.describe_message_id(message_id_uint))
                transport_pgn_description = self.da_describer.get_pgn_description(transport_pgn)
                if self.describe_link_layer:  # when configured to describe 'link layer' don't collide with PGN
                    description.update({'Transport PGN': transport_pgn_description})
                else:  # otherwise (and default) describe the transport PGN as _the_ PGN
                    description.update({PGN_LABEL: transport_pgn_description})

            is_complete_message = transport_message['is_last_packet']
            if self.describe_spns:
                pgn = transport_pgn
                message_description = self.da_describer. \
                    describe_message_data(pgn,
                                          bitstring.Bits(bytes=transport_message['data']),
                                          is_complete_message=is_complete_message,
                                          skip_spns=transport_message['spn_coverage'])
                description.update(message_description)

            if is_complete_message and self.include_transport_rawdata:
                transport_data = str(bitstring.Bits(bytes=transport_message['data']))
                description.update({'Transport Data': transport_data})

        return description


DEFAULT_DA_JSON = "J1939db.json"
DEFAULT_CANDATA = False
DEFAULT_PGN = True
DEFAULT_SPN = True
DEFAULT_TRANSPORT = True
DEFAULT_LINK = False
DEFAULT_INCLUDE_NA = False
DEFAULT_REAL_TIME = False


def get_describer(da_json=DEFAULT_DA_JSON,
                  describe_pgns=DEFAULT_PGN,
                  describe_spns=DEFAULT_SPN,
                  describe_link_layer=DEFAULT_LINK,
                  describe_transport_layer=DEFAULT_TRANSPORT,
                  real_time=DEFAULT_REAL_TIME,
                  include_transport_rawdata=DEFAULT_CANDATA,  # TODO: separate show transport data from candata
                  include_na=DEFAULT_INCLUDE_NA):
    describer = J1939Describer(describe_pgns=describe_pgns,
                               describe_spns=describe_spns,
                               describe_link_layer=describe_link_layer,
                               describe_transport_layer=describe_transport_layer,
                               include_transport_rawdata=include_transport_rawdata,
                               include_na=include_na)

    transport_tracker = TransportTracker(real_time=real_time)
    describer.set_transport_tracker(transport_tracker)

    da_describer = DADescriber(da_json=da_json,
                               describe_pgns=describe_pgns,
                               describe_spns=describe_spns,
                               describe_link_layer=describe_link_layer,
                               describe_transport_layer=describe_transport_layer,
                               real_time=real_time,
                               include_transport_rawdata=include_transport_rawdata,
                               include_na=include_na)
    describer.set_da_describer(da_describer)

    return describer
