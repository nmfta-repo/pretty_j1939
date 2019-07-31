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
import pretty_j1939.parse

parser = argparse. ArgumentParser()
parser.add_argument('-f', '--digital_annex_xls', type=str,
                    default='J1939DA_201311.xls',
                    help="the J1939 Digital Annex excel sheet used as input")
parser.add_argument('-w', '--write-json', type=str,
                    default='-', help="where to write the output. defaults to stdout")
args = parser.parse_args()

class J1939daConverter:
    def __init__(self):
        defusedxml.defuse_stdlib()
        self.j1939db = OrderedDict()

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
        if 'to' in contents.lower() or contents.strip() == '' or 'variable' in contents.lower():
            return 'Variable'
        elif 'byte' in contents.lower():
            return int(contents.split(' ')[0]) * 8
        elif 'bit' in contents.lower():
            return int(contents.split(' ')[0])
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
             'not defined' in norm_contents or contents.strip() == '':
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
        elif 'microsiemens/mm' in norm_contents:  # special handling for this weirdness
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
             'not defined' in norm_contents or contents.strip() == '':
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
    # return an int of the start bit of the SPN; or -1 (if unknown or variable)
    # TODO: encode SPN ordering when all SPNs in a PGN are all -1 -- otherwise there's no way to parse by '*' delimiters
    def get_spn_start_bit(contents):
        norm_contents = contents.lower()

        if ';' in norm_contents:  # special handling for e.g. '0x00;2'
            return -1

        if ',' in norm_contents:
            contents = contents.split(',')[0]  # TODO handle multi-startbit SPNs
            norm_contents = contents.lower()

        if '-' in norm_contents:
            first = norm_contents.split('-')[0]
        elif ' to ' in norm_contents:
            first = norm_contents.split(' to ')[0]
        else:
            first = norm_contents

        first = J1939daConverter.just_numerals(first)
        if first.strip() == '':
            return -1

        if '.' in first:
            byte_index, bit_index = list(map(int, first.split('.')))
        else:
            bit_index = 1
            byte_index = int(first)

        return (byte_index - 1)*8 + (bit_index - 1)

    @staticmethod
    # return an int of SPN length or; -1 (if unknown or variable)
    def get_spn_end_bit(start, length):
        if start == -1 or length == 'Variable':
            return -1
        else:
            return start + length - 1

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

        header_row_num = 3
        header_row = sheet.row_values(header_row_num)
        pgn_col = header_row.index('PGN')
        spn_col = header_row.index('SPN')
        acronym_col = header_row.index('Acronym')
        pgn_label_col = header_row.index('Parameter Group Label')
        pgn_data_length_col = header_row.index('PGN Data Length')
        transmission_rate_col = header_row.index('Transmission Rate')
        spn_position_in_pgn_col = header_row.index('SPN Position in PGN')
        spn_name_col = header_row.index('SPN Name')
        offset_col = header_row.index('Offset')
        data_range_col = header_row.index('Data Range')
        resolution_col = header_row.index('Resolution')
        spn_length_col = header_row.index('SPN Length')
        units_col = header_row.index('Units')
        operational_range_col = header_row.index('Operational Range')
        spn_description_col = header_row.index('SPN Description')

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

                pgn_object.update({'Label':     unidecode.unidecode(row[acronym_col])})
                pgn_object.update({'Name':      unidecode.unidecode(row[pgn_label_col])})
                pgn_object.update({'PGNLength': pgn_data_len})
                pgn_object.update({'Rate':      row[transmission_rate_col]})
                pgn_object.update({'SPNs':      list()})

                j1939_pgn_db.update({pgn_label: pgn_object})

            if pretty_j1939.parse.is_transport_pgn(int(pgn)):  # skip all SPNs for transport PGNs
                continue

            if not spn == '':
                j1939_pgn_db.get(pgn_label).get('SPNs').append(int(spn))

            if not spn == '' and j1939_spn_db.get(str(int(spn))) is None:
                spn_label = str(int(spn))
                spn_object = OrderedDict()

                spn_start_bit = self.get_spn_start_bit(row[spn_position_in_pgn_col])
                spn_length = self.get_spn_len(row[spn_length_col])
                if type(spn_length) == str and spn_length.startswith("Variable"):
                    spn_delimiter = self.get_spn_delimiter(row[spn_length_col])
                    if spn_start_bit == -1:
                        spn_order = row[spn_position_in_pgn_col].strip()
                    else:
                        spn_order = None
                else:
                    spn_delimiter = None
                    spn_order = None

                spn_end_bit = self.get_spn_end_bit(spn_start_bit, spn_length)
                spn_units = row[units_col]
                low, high = self.get_operational_hilo(row[data_range_col], spn_units, spn_length)

                spn_object.update({'DataRange':        unidecode.unidecode(row[data_range_col])})
                spn_object.update({'EndBit':           spn_end_bit})
                spn_object.update({'Name':             unidecode.unidecode(row[spn_name_col])})
                spn_object.update({'Offset':           self.get_spn_offset(row[offset_col])})
                spn_object.update({'OperationalHigh':  high})
                spn_object.update({'OperationalLow':   low})
                spn_object.update({'OperationalRange': unidecode.unidecode(row[operational_range_col])})
                spn_object.update({'Resolution':       self.get_spn_resolution(unidecode.unidecode(row[resolution_col]))})
                spn_object.update({'SPNLength':        spn_length})
                if spn_delimiter is not None:
                    spn_object.update({'Delimiter':    '0x%s' % spn_delimiter.hex()})
                if spn_order is not None:
                    spn_object.update({'Order':        spn_order})
                spn_object.update({'StartBit':         spn_start_bit})
                spn_object.update({'Units':            spn_units})

                j1939_spn_db.update({spn_label: spn_object})

                spn_description = unidecode.unidecode(row[spn_description_col])
                if row[units_col] == 'bit' or self.is_spn_likely_bitmapped(spn_description):
                    bit_object = OrderedDict()
                    self.create_bit_object_from_description(spn_description, bit_object)
                    if len(bit_object) > 0:
                        j1939_bit_decodings.update({spn_label: bit_object})

        return

    def process_any_source_addresses_sheet(self, sheet):
        if self.j1939db.get('J1939SATabledb') is None:
            self.j1939db.update({'J1939SATabledb': OrderedDict()})
        j1939_sa_tabledb = self.j1939db.get('J1939SATabledb')

        header_row_num = 3
        header_row = sheet.row_values(header_row_num)
        source_address_id_col = header_row.index('Source Address ID')
        name_col = header_row.index('Name')

        for i in range(header_row_num+1, sheet.nrows):
            row = sheet.row_values(i)

            name = row[name_col]
            if name.startswith('thru'):
                continue

            val = str(int(row[source_address_id_col]))
            name = name.strip()

            j1939_sa_tabledb.update({val: name})
        return

    def convert(self, input_file, output_file):
        self.j1939db = OrderedDict()

        with self.secure_open_workbook(filename=input_file, on_demand=True) as j1939_da:
            self.process_spns_and_pgns_tab(j1939_da.sheet_by_name('SPNs & PGNs'))
            self.process_any_source_addresses_sheet(j1939_da.sheet_by_name('Global Source Addresses (B2)'))
            self.process_any_source_addresses_sheet(j1939_da.sheet_by_name('IG1 Source Addresses (B3)'))

        out = open(output_file, 'w') if output_file != '-' else sys.stdout

        try:
            out.write(json.dumps(self.j1939db, indent=2, sort_keys=False))
        except BrokenPipeError:
            pass

        if out is not sys.stdout:
            out.close()

        return


J1939daConverter().convert(args.digital_annex_xls, args.write_json)
