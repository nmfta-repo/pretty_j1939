#
# Copyright (c) 2019 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

from collections import OrderedDict
import defusedxml
from defusedxml.common import EntitiesForbidden
import xlrd
import sys
import re
import unidecode
import asteval
import json
import argparse
import functools
import operator
import itertools
import pretty_j1939.parse

parser = argparse.ArgumentParser()
parser.add_argument('-f', '--digital_annex_xls', type=str, required=True, action='append',
                    default=[], nargs='+',
                    help="the J1939 Digital Annex excel sheet used as input")
parser.add_argument('-w', '--write-json', type=str, default='-',
                    help="where to write the output. defaults to stdout")
args = parser.parse_args()


class J1939daConverter:
    def __init__(self, digital_annex_xls_list):
        defusedxml.defuse_stdlib()
        self.j1939db = OrderedDict()
        self.digital_annex_xls_list = list(map(lambda da: self.secure_open_workbook(filename=da, on_demand=True),
                                               digital_annex_xls_list))

    @staticmethod
    def secure_open_workbook(**kwargs):
        try:
            return xlrd.open_workbook(**kwargs)
        except EntitiesForbidden:
            raise ValueError('Please use an excel file without XEE')

    @staticmethod
    # returns a string of number of bits, or 'Variable', or ''
    def get_pgn_data_len(contents):
        if type(contents) is float:
            return str(int(contents))
        elif 'bytes' not in contents.lower() and 'variable' not in contents.lower():
            return str(contents)
        elif 'bytes' in contents.lower():
            return str(int(contents.split(' ')[0]) * 8)
        elif 'variable' in contents.lower():
            return 'Variable'
        elif contents.strip() == '':
            return ''
        raise ValueError('unknown PGN Length "%s"' % contents)

    @staticmethod
    # returns an int number of bits, or 'Variable'
    def get_spn_len(contents):
        if 'to' in contents.lower() or \
           contents.strip() == '' or \
           'variable' in contents.lower():
            return 'Variable'
        elif re.match(r'max [0-9]+ bytes', contents):
            return 'Variable'
        elif 'byte' in contents.lower():
            return int(contents.split(' ')[0]) * 8
        elif 'bit' in contents.lower():
            return int(contents.split(' ')[0])
        elif re.match(r'^[0-9]+$', contents):
            return int(contents)
        raise ValueError('unknown SPN Length "%s"' % contents)

    @staticmethod
    # returns a single-byte delimiter or None
    def get_spn_delimiter(contents):
        if 'delimiter' in contents.lower():
            if '*' in contents:
                return b'*'
            elif 'NULL' in contents:
                return b'\x00'
            else:
                raise ValueError('unknown SPN delimiter "%s"' % contents)
        else:
            return None

    @staticmethod
    def just_numerals(contents):
        contents = re.sub(r'[^0-9\.\-/]', '', contents)  # remove all but number and '.'
        contents = re.sub(r'/$', '', contents)  # remove trailing '/' that are sometimes left
        return contents

    @staticmethod
    # returns a float in X per bit or int(0)
    def get_spn_resolution(contents):
        norm_contents = contents.lower()
        if '0 to 255 per byte' in norm_contents or 'states/' in norm_contents:
            return 1.0
        elif 'bit-mapped' in norm_contents or \
             'binary' in norm_contents or \
             'ascii' in norm_contents or \
             'not defined' in norm_contents or \
             'variant determined' in norm_contents or \
             '7 bit iso latin 1 characters' in norm_contents or \
             contents.strip() == '':
            return int(0)
        elif 'per bit' in norm_contents or '/bit' in norm_contents:
            first = contents.split(' ')[0]
            first = first.replace('/bit', '')
            first = J1939daConverter.just_numerals(first)
            return asteval.Interpreter()(first)
        elif 'bit' in norm_contents and '/' in norm_contents:
            left, right = contents.split('/')
            left = J1939daConverter.just_numerals(left.split(' ')[0])
            right = J1939daConverter.just_numerals(right.split(' ')[0])
            return asteval.Interpreter()('%s/%s' % (left, right))
        elif 'microsiemens/mm' in norm_contents or 'usiemens/mm' in norm_contents:  # special handling for this weirdness
            return float(contents.split(' ')[0])
        raise ValueError('unknown spn resolution "%s"' % contents)

    @staticmethod
    # returns a float in 'units' of the SPN or int(0)
    def get_spn_offset(contents):
        norm_contents = contents.lower()
        if 'manufacturer defined' in norm_contents or 'not defined' in norm_contents or contents.strip() == '':
            return int(0)
        else:
            first = contents.split(' ')[0]
            first = J1939daConverter.just_numerals(first)
            return asteval.Interpreter()(first)

    @staticmethod
    # returns a pair of floats (low, high) in 'units' of the SPN or (-1, -1) for undefined operational ranges
    def get_operational_hilo(contents, units, spn_length):
        norm_contents = contents.lower()
        if contents.strip() == '' and units.strip() == '':
            if type(spn_length) is int:
                return 0, 2**spn_length-1
            else:
                return -1, -1
        elif 'manufacturer defined' in norm_contents or\
             'bit-mapped' in norm_contents or\
             'not defined' in norm_contents or\
             'variant determined' in norm_contents or\
             contents.strip() == '':
            return -1, -1
        elif ' to ' in norm_contents:
            left, right = norm_contents.split(' to ')[0:2]
            left = J1939daConverter.just_numerals(left.split(' ')[0])
            right = J1939daConverter.just_numerals(right.split(' ')[0])

            range_units = norm_contents.split(' ')
            range_units = range_units[len(range_units) - 1]
            if range_units == 'km' and units == 'm':
                return float(left)*1000, float(right)*1000
            else:
                return float(left), float(right)
        raise ValueError('unknown operational range from "%s","%s"' % (contents, units))

    @staticmethod
    # return an int of the start bit of the SPN; or -1 (if unknown or variable).
    # Changed: return format is a list of [-1], [some_bit_pos] or [some_bit_pos,some_other_bit_pos]
    def get_spn_start_bit(contents):
        norm_contents = contents.lower()

        if ';' in norm_contents:  # special handling for e.g. '0x00;2'
            return [-1]

        # Changed synopsis below:
        """According to 1939-71, "If the data length is larger than 1 byte or the data spans a byte boundary, 
        then the Start Position consists of two numerical values separated by a comma or dash." Therefore , 
        and - may be treated in the same way, multi-startbit. To account for multi-startbit we will introduce the following:
        1> an SPN position is now a pair of bit positions (R,S), where S = None if not multibit
        2> the SPN length is now a pair (Rs, Ss), where Ss = None if not multibit, else net Rs = (S - R + 1) and Ss = (Length - Rs) 
        """

        delim = ""
        firsts = [norm_contents]
        if ',' in norm_contents:
            # raise ValueError("this SPN not in one contiguous bitfield")  # TODO handle multi-startbit SPNs ex '3-4, 5.6' # Changed
            delim = ","
        if '-' in norm_contents:
            delim = "-"
        elif ' to ' in norm_contents:
            delim = " to "

        if len(delim) > 0:
            firsts = norm_contents.split(delim)

        if any(re.match(r'^[a-z]\+[0-9]', first) for first in firsts):
            return [-1]

        firsts = [J1939daConverter.just_numerals(first) for first in firsts]
        if any(first.strip() == '' for first in firsts):
            return [-1]

        pos_pair = []
        for first in firsts:
            if '.' in first:
                byte_index, bit_index = list(map(int, first.split('.')))
            else:
                bit_index = 1
                byte_index = int(first)
            pos_pair.append((byte_index - 1) * 8 + (bit_index - 1))

        return pos_pair

    @staticmethod
    def get_enum_lines(description_lines):
        enum_lines = list()
        for line in description_lines:
            if line.lower().startswith('bit state'):
                line = re.sub(r'(Bit States|Bit State)', '', line, flags=re.IGNORECASE)
                enum_lines.append(line)
            elif re.match(r'^[ ]*[0-9][0-9bxXA-F\-:]*[ ]+[^ ]+', line):
                enum_lines.append(line)

        return enum_lines

    @staticmethod
    def is_enum_lines_binary(description_lines):
        all_ones_and_zeroes = True
        for line in description_lines:
            first = re.match(r'[ ]*([0-9bxXA-F]+)', line).groups()[0]
            if re.sub(r'[^10b]', '', first) != first:
                all_ones_and_zeroes = False
                break

        return all_ones_and_zeroes

    @staticmethod
    # returns a pair of inclusive, inclusive range boundaries or None if this line is not a range
    def get_enum_line_range(line):
        match = re.match(r'[ ]*([0-9bxXA-F]+)[ ]*(\-|to|thru)[ ]*([0-9bxXA-F]+)[ -=]', line)
        if match:
            groups = match.groups()
            if re.match(r'[01b]', groups[0]) and not re.match(r'[01b]', groups[2]):
                return None
            return groups[0], groups[2]
        else:
            return None

    @staticmethod
    def create_bit_object_from_description(spn_description, bit_object):
        description_lines = spn_description.splitlines()
        enum_lines = J1939daConverter.get_enum_lines(description_lines)
        is_binary = J1939daConverter.is_enum_lines_binary(enum_lines)

        for line in enum_lines:
            enum_description = re.sub(r'[ ]+', ' ', line)

            range_boundaries = J1939daConverter.get_enum_line_range(line)
            if range_boundaries is not None:
                if is_binary:
                    first = re.sub(r'b', '', range_boundaries[0])
                    first_val = int(first, base=2)
                    second = re.sub(r'b', '', range_boundaries[1])
                    second_val = int(second, base=2)
                elif 'x' in range_boundaries[0].lower():
                    first_val = int(range_boundaries[0], base=16)
                    second_val = int(range_boundaries[1], base=16)
                else:
                    first_val = int(range_boundaries[0], base=10)
                    second_val = int(range_boundaries[1], base=10)

                for i in range(first_val, second_val+1):
                    bit_object.update(({str(i): enum_description}))
            else:
                first = re.match(r'[ ]*([0-9bxXA-F]+)', line).groups()[0]

                if is_binary:
                    first = re.sub(r'b', '', first)
                    val = str(int(first, base=2))
                elif 'x' in first.lower():
                    val = str(int(first, base=16))
                else:
                    val = str(int(first, base=10))

                bit_object.update(({val: enum_description}))

    @staticmethod
    def is_spn_likely_bitmapped(spn_description):
        return len(J1939daConverter.get_enum_lines(spn_description.splitlines())) > 2

    def process_spns_and_pgns_tab(self, sheet):
        self.j1939db.update({'J1939PGNdb': OrderedDict()})
        j1939_pgn_db = self.j1939db.get('J1939PGNdb')
        self.j1939db.update({'J1939SPNdb': OrderedDict()})
        j1939_spn_db = self.j1939db.get('J1939SPNdb')
        self.j1939db.update({'J1939BitDecodings': OrderedDict()})
        j1939_bit_decodings = self.j1939db.get('J1939BitDecodings')

        # check for SPNs in multiple PNGs
        spn_factcheck_map = dict()

        header_row, header_row_num = self.get_header_row(sheet)

        pgn_col = header_row.index('PGN')
        spn_col = header_row.index('SPN')
        acronym_col = header_row.index('ACRONYM')
        pgn_label_col = header_row.index('PARAMETER_GROUP_LABEL')
        pgn_data_length_col = header_row.index('PGN_DATA_LENGTH')
        transmission_rate_col = header_row.index('TRANSMISSION_RATE')
        spn_position_in_pgn_col = header_row.index('SPN_POSITION_IN_PGN')
        spn_name_col = header_row.index('SPN_NAME')
        offset_col = header_row.index('OFFSET')
        data_range_col = header_row.index('DATA_RANGE')
        resolution_col = header_row.index('RESOLUTION')
        spn_length_col = header_row.index('SPN_LENGTH')
        units_col = header_row.index('UNITS')
        operational_range_col = header_row.index('OPERATIONAL_RANGE')
        spn_description_col = header_row.index('SPN_DESCRIPTION')

        for i in range(header_row_num+1, sheet.nrows):
            row = sheet.row_values(i)
            pgn = row[pgn_col]
            if pgn == '':
                continue

            pgn_label = str(int(pgn))

            spn = row[spn_col]

            if not j1939_pgn_db.get(pgn_label) is None:
                # TODO assert that PGN values haven't changed across multiple SPN rows
                pass
            else:
                pgn_object = OrderedDict()

                pgn_data_len = self.get_pgn_data_len(row[pgn_data_length_col])

                pgn_object.update({'Label':              unidecode.unidecode(row[acronym_col])})
                pgn_object.update({'Name':               unidecode.unidecode(row[pgn_label_col])})
                pgn_object.update({'PGNLength':          pgn_data_len})
                pgn_object.update({'Rate':               unidecode.unidecode(row[transmission_rate_col])})
                pgn_object.update({'SPNs':               list()})
                pgn_object.update({'SPNStartBits':       list()})
                pgn_object.update({'Temp_SPN_Order':     list()})

                j1939_pgn_db.update({pgn_label: pgn_object})

            if pretty_j1939.parse.is_transport_pgn(int(pgn)):  # skip all SPNs for transport PGNs
                continue

            if not spn == '':
                if spn_factcheck_map.get(spn, None) is None:
                    spn_factcheck_map.update({spn: [pgn, ]})
                else:
                    spn_list = spn_factcheck_map.get(spn)
                    spn_list.append(spn)
                    spn_factcheck_map.update({spn: spn_list})

                spn_label = str(int(spn))
                spn_object = OrderedDict()

                spn_length = self.get_spn_len(row[spn_length_col])
                if type(spn_length) == str and spn_length.startswith("Variable"):
                    spn_delimiter = self.get_spn_delimiter(row[spn_length_col])
                else:
                    spn_delimiter = None

                spn_units = unidecode.unidecode(row[units_col])
                data_range = unidecode.unidecode(row[data_range_col])
                low, high = self.get_operational_hilo(data_range, spn_units, spn_length)

                spn_name = unidecode.unidecode(row[spn_name_col])
                operational_range = unidecode.unidecode(row[operational_range_col])
                spn_resoluion = unidecode.unidecode(row[resolution_col])

                spn_object.update({'DataRange':        data_range})
                spn_object.update({'Name':             spn_name})
                spn_object.update({'Offset':           self.get_spn_offset(row[offset_col])})
                spn_object.update({'OperationalHigh':  high})
                spn_object.update({'OperationalLow':   low})
                spn_object.update({'OperationalRange': operational_range})
                spn_object.update({'Resolution':       self.get_spn_resolution(spn_resoluion)})
                spn_object.update({'SPNLength':        spn_length})
                if spn_delimiter is not None:
                    spn_object.update({'Delimiter':    '0x%s' % spn_delimiter.hex()})
                spn_object.update({'Units':            spn_units})

                existing_spn = j1939_spn_db.get(str(int(spn)))
                if existing_spn is not None and not existing_spn == spn_object:
                    print("Warning: changed details of SPN %s:\n %s vs previous:\n %s" %
                          (spn, existing_spn, spn_object), file=sys.stderr)
                else:
                    j1939_spn_db.update({spn_label: spn_object})

                # record SPN position-in-PGN ('StartBit') in the PGN structure along with the list of SPNs -- or skip
                # this SPN
                try:
                    spn_position_contents = row[spn_position_in_pgn_col]
                    spn_startbit_inpgn = self.get_spn_start_bit(spn_position_contents)
                    if spn_label == '5998' and spn_position_contents.strip() == '4.4':  # bug in 201311 DA
                        spn_startbit_inpgn = self.get_spn_start_bit('4.5')
                    elif spn_label == '3036' and spn_position_contents.strip() == '6-8.6':  # bug in 201311 DA
                        spn_startbit_inpgn = self.get_spn_start_bit('6-7,8.6')
                    elif spn_label == '6062' and spn_position_contents.strip() == '4.4':  # bug in 201311 DA
                        spn_startbit_inpgn = self.get_spn_start_bit('4.5')
                    elif spn_label == '6030' and spn_position_contents.strip() == '4.4':  # bug in 201311 DA
                        spn_startbit_inpgn = self.get_spn_start_bit('4.5')

                    if spn_startbit_inpgn == [-1]:
                        spn_order_inpgn = spn_position_contents.strip()
                    else:
                        spn_order_inpgn = spn_startbit_inpgn
                except ValueError:
                    continue

                if spn_label == '6610' or spn_label == '6815':  # bug in PGN map in 201311 DA
                    continue

                j1939_pgn_db.get(pgn_label).get('SPNs').append(int(spn))
                j1939_pgn_db.get(pgn_label).get('SPNStartBits').append([int(s) for s in spn_startbit_inpgn])
                # the Temp_SPN_Order list will be deleted later
                j1939_pgn_db.get(pgn_label).get('Temp_SPN_Order').append(spn_order_inpgn)

                # If there is a bitfield/enum described in this row, then create a separate object describing the states
                spn_description = unidecode.unidecode(row[spn_description_col])
                if row[units_col] == 'bit' or self.is_spn_likely_bitmapped(spn_description):
                    bit_object = OrderedDict()
                    self.create_bit_object_from_description(spn_description, bit_object)
                    if len(bit_object) > 0:
                        j1939_bit_decodings.update({spn_label: bit_object})

        # Clean-ups are needed:
        # * sort SPN lists in PGNs by the Temp_SPN_Order
        # * fix the starting sequence of -1 startbits in PGNs with fixed-len SPNs mapped
        # * fix incorrectly variable-len SPNs in a sequence known startbits
        # * remove any SPN maps that have variable-len, no-delimiter SPNs in a PGN with >1 SPN mapped
        # * remove Temp_SPN_Order
        # * remove zero-len startbits arrays

        # * sort SPN lists in PGNs by the Temp_SPN_Order
        self.sort_spns_by_order(j1939_pgn_db)

        # * fix the starting sequence of -1 startbits in PGNs with fixed-len SPNs mapped
        self.remove_startbitsunknown_spns(j1939_pgn_db, j1939_spn_db)

        # * fix incorrectly variable-len SPNs in a sequence known startbits
        self.fix_omittedlen_spns(j1939_pgn_db, j1939_spn_db)

        # * remove any SPN maps that have variable-len, no-delimiter SPNs in a PGN with >1 SPN mapped
        self.remove_underspecd_spns(j1939_pgn_db, j1939_spn_db)

        # * remove Temp_SPN_Order
        for pgn, pgn_object in j1939_pgn_db.items():
            pgn_object.pop('Temp_SPN_Order')

        # * remove zero-len startbits arrays
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get('SPNs')
            if len(spn_list) == 0:
                pgn_object.pop('SPNStartBits')

        return

    def get_header_row(self, sheet):
        header_row_num = self.lookup_header_row(sheet)

        header_row = sheet.row_values(header_row_num)
        header_row = list(map(lambda x: x.upper(), header_row))
        header_row = list(map(lambda x: x.replace(' ', '_'), header_row))
        return header_row, header_row_num

    def lookup_header_row(self, sheet):
        if sheet.row_values(0)[3].strip() == '':
            return 3
        else:
            return 0

    @staticmethod
    def fix_omittedlen_spns(j1939_pgn_db, j1939_spn_db):
        modified_spns = dict()
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get('SPNs')
            spn_startbit_list = pgn_object.get('SPNStartBits')
            spn_order_list = pgn_object.get('Temp_SPN_Order')

            spn_in_pgn_list = list(zip(spn_list, spn_startbit_list, spn_order_list))
            if J1939daConverter.all_spns_positioned(spn_startbit_list):
                for i in range(0, len(spn_in_pgn_list) - 1):
                    here_startbit = int(spn_in_pgn_list[i][1][0])
                    next_startbit = int(spn_in_pgn_list[i + 1][1][0])
                    calced_spn_length = next_startbit - here_startbit
                    here_spn = spn_in_pgn_list[i][0]

                    if calced_spn_length == 0:
                        print("Warning: calculated zero-length SPN %s in PGN %s" % (here_spn, pgn), file=sys.stderr)
                        continue
                    else:
                        spn_obj = j1939_spn_db.get(str(here_spn))
                        current_spn_length = spn_obj.get('SPNLength')
                        if J1939daConverter.is_length_variable(current_spn_length):
                            spn_obj.update({'SPNLength': calced_spn_length})
                            modified_spns.update({here_spn: True})
                        elif calced_spn_length < current_spn_length and modified_spns.get(here_spn) is None:
                            print("Warning: calculated length for SPN %s (%d) in PGN %s differs from existing SPN "
                                  "length %s" % (here_spn, calced_spn_length, pgn, current_spn_length), file=sys.stderr)

    @staticmethod
    def is_length_variable(spn_length):
        return type(spn_length) is str and spn_length.startswith('Variable')

    @staticmethod
    def remove_startbitsunknown_spns(j1939_pgn_db, j1939_spn_db):
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get('SPNs')
            if len(spn_list) > 1:
                spn_list = pgn_object.get('SPNs')
                spn_startbit_list = pgn_object.get('SPNStartBits')
                spn_order_list = pgn_object.get('Temp_SPN_Order')

                spn_in_pgn_list = list(zip(spn_list, spn_startbit_list, spn_order_list))
                for i in range(0, len(spn_in_pgn_list)):
                    here_startbit = int(spn_in_pgn_list[i][1][0])
                    prev_spn = spn_in_pgn_list[i - 1][0]
                    prev_spn_obj = j1939_spn_db.get(str(prev_spn))
                    prev_spn_len = prev_spn_obj.get('SPNLength')
                    if here_startbit == -1 and not J1939daConverter.is_length_variable(prev_spn_len):
                        if (i - 1) == 0:  # special case for the first field
                            prev_startbit = 0
                            here_startbit = prev_spn_len
                            prev_tuple = list(spn_in_pgn_list[i - 1])
                            prev_tuple[1] = [prev_startbit]
                            spn_in_pgn_list[i - 1] = tuple(prev_tuple)
                        else:
                            prev_startbit = int(spn_in_pgn_list[i - 1][1][0])
                            here_startbit = prev_startbit + prev_spn_len
                        here_tuple = list(spn_in_pgn_list[i])
                        here_tuple[1] = [here_startbit]
                        spn_in_pgn_list[i] = tuple(here_tuple)

                # update the maps
                pgn_object.update({'SPNs': list(map(operator.itemgetter(0), spn_in_pgn_list))})
                pgn_object.update({'SPNStartBits': list(map(operator.itemgetter(1), spn_in_pgn_list))})
                pgn_object.update({'Temp_SPN_Order': list(map(operator.itemgetter(2), spn_in_pgn_list))})

    @staticmethod
    def remove_underspecd_spns(j1939_pgn_db, j1939_spn_db):
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get('SPNs')
            if len(spn_list) > 1:
                spn_list = pgn_object.get('SPNs')
                spn_startbit_list = pgn_object.get('SPNStartBits')
                spn_order_list = pgn_object.get('Temp_SPN_Order')

                spn_in_pgn_list = zip(spn_list, spn_startbit_list, spn_order_list)

                def should_remove(tup):
                    spn = tup[0]
                    spn_obj = j1939_spn_db.get(str(spn))
                    current_spn_length = spn_obj.get('SPNLength')
                    current_spn_delimiter = spn_obj.get('Delimiter')
                    if J1939daConverter.is_length_variable(current_spn_length) and \
                            current_spn_delimiter is None:
                        print("Warning: removing SPN %s from PGN %s because it "
                              "is variable-length with no delimiter in a multi-SPN PGN. "
                              "This likely an under-specification in the DA." % (spn, pgn), file=sys.stderr)
                        return True
                    return False

                spn_in_pgn_list = [tup for tup in spn_in_pgn_list if not should_remove(tup)]

                # update the maps
                pgn_object.update({'SPNs': list(map(operator.itemgetter(0), spn_in_pgn_list))})
                pgn_object.update({'SPNStartBits': list(map(operator.itemgetter(1), spn_in_pgn_list))})
                pgn_object.update({'Temp_SPN_Order': list(map(operator.itemgetter(2), spn_in_pgn_list))})

    @staticmethod
    def sort_spns_by_order(j1939_pgn_db):
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get('SPNs')
            spn_startbit_list = pgn_object.get('SPNStartBits')
            spn_order_list = pgn_object.get('Temp_SPN_Order')

            spn_in_pgn_list = zip(spn_list, spn_startbit_list, spn_order_list)
            # sort numbers then letters
            spn_in_pgn_list = sorted(spn_in_pgn_list, key=lambda obj: (isinstance(obj[2], str), obj[2]))

            # update the maps (now sorted by 'Temp_SPN_Order')
            pgn_object.update({'SPNs': list(map(operator.itemgetter(0), spn_in_pgn_list))})
            pgn_object.update({'SPNStartBits': list(map(operator.itemgetter(1), spn_in_pgn_list))})
            pgn_object.update({'Temp_SPN_Order': list(map(operator.itemgetter(2), spn_in_pgn_list))})

    @staticmethod
    def all_spns_positioned(spn_startbit_list):
        if len(spn_startbit_list) == 0:
            return True
        else:
            is_positioned = map(lambda spn_startbit: int(spn_startbit[0]) != -1, spn_startbit_list)
            return functools.reduce(lambda a, b: a and b, is_positioned)

    def process_any_source_addresses_sheet(self, sheet):
        if self.j1939db.get('J1939SATabledb') is None:
            self.j1939db.update({'J1939SATabledb': OrderedDict()})
        j1939_sa_tabledb = self.j1939db.get('J1939SATabledb')

        header_row, header_row_num = self.get_header_row(sheet)

        source_address_id_col = header_row.index('SOURCE_ADDRESS_ID')
        name_col = header_row.index('NAME')

        for i in range(header_row_num+1, sheet.nrows):
            row = sheet.row_values(i)

            name = row[name_col]
            if name.startswith('thru'):
                continue

            val = str(int(row[source_address_id_col]))
            name = name.strip()

            j1939_sa_tabledb.update({val: name})
        return

    def convert(self, output_file):
        self.j1939db = OrderedDict()
        sheet_name = 'SPNs & PGNs'
        self.process_spns_and_pgns_tab(self.find_first_sheet_by_name(sheet_name))
        sheet_name = 'Global Source Addresses (B2)'
        self.process_any_source_addresses_sheet(self.find_first_sheet_by_name(sheet_name))
        sheet_name = 'IG1 Source Addresses (B3)'
        self.process_any_source_addresses_sheet(self.find_first_sheet_by_name(sheet_name))

        out = open(output_file, 'w') if output_file != '-' else sys.stdout

        try:
            out.write(json.dumps(self.j1939db, indent=2, sort_keys=False))
        except BrokenPipeError:
            pass

        if out is not sys.stdout:
            out.close()

        return

    def find_first_sheet_by_name(self, sheet_name):
        for book in self.digital_annex_xls_list:
            if sheet_name in book.sheet_names():
                sheet = book.sheet_by_name(sheet_name)
                return sheet
        return None


all_inputs = itertools.chain(*args.digital_annex_xls)
J1939daConverter(all_inputs).convert(args.write_json)
