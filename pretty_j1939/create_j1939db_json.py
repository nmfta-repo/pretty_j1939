#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
from collections import OrderedDict
from . import describe
import unidecode
import sys

import defusedxml
from defusedxml.common import EntitiesForbidden
import xlrd
import openpyxl
import re
import asteval
import json
import argparse
import functools
import operator
import itertools

ENUM_SINGLE_LINE_RE = r"[ ]*([0-9bxXA-F]+)[ ]*[-=:]?[ ]*(.*)"
ENUM_RANGE_LINE_RE = (
    r"[ ]*([0-9bxXA-F]+)[ ]*(\-|to|thru)[ ]*([0-9bxXA-F]+)[ ]+[-=:]?[ ]*(.*)"
)


class SheetWrapper:
    def __init__(self, sheet):
        self.sheet = sheet

    @property
    def nrows(self):
        raise NotImplementedError()

    def row_values(self, row_num):
        raise NotImplementedError()

    def _clean_value(self, v):
        if isinstance(v, str):
            # Clean up XML artifacts like _x000d_ (case-insensitive)
            # Use a more robust regex that catches all xNNNN artifacts commonly found in Excel/XML
            v = re.sub(r"_x[0-9a-fA-F]{4}_", " ", v)
            # Collapse multiple spaces, but PRESERVE newlines
            # We only collapse horizontal whitespace (space and tab)
            v = re.sub(r"[ \t]+", " ", v)
            return v.strip()
        return v


class XlsSheetWrapper(SheetWrapper):
    @property
    def nrows(self):
        return self.sheet.nrows

    def row_values(self, row_num):
        row = self.sheet.row_values(row_num)
        return [self._clean_value(v) for v in row]


class XlsxSheetWrapper(SheetWrapper):
    def __init__(self, sheet):
        super().__init__(sheet)
        # Cache all rows as a list of tuples of values for performance
        self._rows = list(sheet.values)

    @property
    def nrows(self):
        return len(self._rows)

    def row_values(self, row_num):
        row = list(self._rows[row_num])
        return [self._clean_value(v) for v in row]


class J1939daConverter:
    def __init__(self, digital_annex_xls_list):
        defusedxml.defuse_stdlib()
        self.j1939db = OrderedDict()
        self.digital_annex_xls_list = []
        for da in digital_annex_xls_list:
            book = self.secure_open_workbook(filename=da, on_demand=True)
            self.digital_annex_xls_list.append(book)

    @staticmethod
    def secure_open_workbook(filename, **kwargs):
        try:
            if filename.endswith(".xlsx"):
                return openpyxl.load_workbook(filename, data_only=True)
            else:
                return xlrd.open_workbook(filename=filename, **kwargs)
        except EntitiesForbidden:
            raise ValueError("Please use an excel file without XEE")

    @staticmethod
    # returns a string of number of bits, or 'Variable', or ''
    def get_pgn_data_len(contents):
        if contents is None:
            return ""
        if type(contents) is float or type(contents) is int:
            return str(int(contents))
        contents = str(contents)
        if "bytes" not in contents.lower() and "variable" not in contents.lower():
            return str(contents)
        elif "bytes" in contents.lower():
            return str(int(contents.split(" ")[0]) * 8)
        elif "variable" in contents.lower():
            return "Variable"
        elif contents.strip() == "":
            return ""
        raise ValueError('unknown PGN Length "%s"' % contents)

    @staticmethod
    # returns an int number of bits, or 'Variable'
    def get_spn_len(contents):
        if contents is None:
            return "Variable"
        if type(contents) is int:
            return contents
        if type(contents) is float:
            return int(contents)
        contents = str(contents)
        if (
            "to" in contents.lower()
            or contents.strip() == ""
            or "variable" in contents.lower()
        ):
            return "Variable"
        elif re.match(r"max [0-9]+ bytes", contents):
            return "Variable"
        elif "byte" in contents.lower():
            return int(contents.split(" ")[0]) * 8
        elif "bit" in contents.lower():
            return int(contents.split(" ")[0])
        elif re.match(r"^[0-9]+$", contents):
            return int(contents)
        raise ValueError('unknown SPN Length "%s"' % contents)

    @staticmethod
    # returns a single-byte delimiter or None
    def get_spn_delimiter(contents):
        contents = str(contents)
        if "delimiter" in contents.lower():
            if "*" in contents:
                return b"*"
            elif "NULL" in contents:
                return b"\x00"
            else:
                raise ValueError('unknown SPN delimiter "%s"' % contents)
        else:
            return None

    @staticmethod
    def just_numeric_expr(contents):
        contents = str(contents)
        contents = re.sub(r"[^0-9\.\-/]", "", contents)  # remove all but number and '.'
        contents = re.sub(
            r"[/-]+[ ]*$", "", contents
        )  # remove trailing '/' or '-' that are sometimes left
        return contents

    @staticmethod
    def get_spn_units(contents, raw_spn_resolution):
        norm_contents = unidecode.unidecode(str(contents)).lower().strip()
        raw_spn_resolution_norm = (
            unidecode.unidecode(str(raw_spn_resolution)).lower().strip()
        )
        if norm_contents == "":
            if "states" in raw_spn_resolution_norm:
                norm_contents = "bit"
            elif "bit-mapped" in raw_spn_resolution_norm:
                norm_contents = "bit-mapped"
            elif "binary" in raw_spn_resolution_norm:
                norm_contents = "binary"
            elif "ascii" in raw_spn_resolution_norm:
                norm_contents = "ascii"
        return norm_contents

    @staticmethod
    # returns a float in X per bit or int(0)
    def get_spn_resolution(contents):
        norm_contents = unidecode.unidecode(str(contents)).lower()
        if (
            "0 to 255 per byte" in norm_contents
            or " states" in norm_contents
            or norm_contents == "data specific"
        ):
            return 1.0
        elif (
            "bit-mapped" in norm_contents
            or "binary" in norm_contents
            or "ascii" in norm_contents
            or "not defined" in norm_contents
            or "variant determined" in norm_contents
            or "7 bit iso latin 1 characters" in norm_contents
            or norm_contents.strip() == ""
        ):
            return int(0)
        elif "per bit" in norm_contents or "/bit" in norm_contents:
            expr = J1939daConverter.just_numeric_expr(norm_contents)
            return J1939daConverter.asteval_eval(expr)
        elif "bit" in norm_contents and "/" in norm_contents:
            left, right = str(contents).split("/")
            left = J1939daConverter.just_numeric_expr(left)
            right = J1939daConverter.just_numeric_expr(right)
            return J1939daConverter.asteval_eval("(%s)/(%s)" % (left, right))
        elif (
            "microsiemens/mm" in norm_contents
            or "usiemens/mm" in norm_contents
            or "kw/s" in norm_contents
        ):  # special handling for this weirdness
            return float(str(contents).split(" ")[0])
        raise ValueError('unknown spn resolution "%s"' % contents)

    @staticmethod
    def asteval_eval(expr):
        interpreter = asteval.Interpreter()
        ret = interpreter(expr)
        if len(interpreter.error) > 0:
            raise interpreter.error[0]
        return ret

    @staticmethod
    # returns a float in 'units' of the SPN or int(0)
    def get_spn_offset(contents):
        norm_contents = unidecode.unidecode(str(contents)).lower()
        if (
            "manufacturer defined" in norm_contents
            or "not defined" in norm_contents
            or norm_contents.strip() == ""
        ):
            return int(0)
        else:
            first = J1939daConverter.just_numeric_expr(contents)
            return J1939daConverter.asteval_eval(first)

    @staticmethod
    # returns a pair of floats (low, high) in 'units' of the SPN or (-1, -1) for undefined operational ranges
    def get_operational_hilo(contents, units, spn_length):
        norm_contents = str(contents).lower()
        if str(contents).strip() == "" and str(units).strip() == "":
            if type(spn_length) is int:
                return 0, 2**spn_length - 1
            else:
                return -1, -1
        elif (
            "manufacturer defined" in norm_contents
            or "bit-mapped" in norm_contents
            or "not defined" in norm_contents
            or "variant determined" in norm_contents
            or str(contents).strip() == ""
        ):
            return -1, -1
        elif " to " in norm_contents:
            left, right = norm_contents.split(" to ")[0:2]
            left = J1939daConverter.just_numeric_expr(left)
            right = J1939daConverter.just_numeric_expr(right)

            range_units = norm_contents.split(" ")
            range_units = range_units[len(range_units) - 1]
            lo = float(J1939daConverter.asteval_eval(left))
            hi = float(J1939daConverter.asteval_eval(right))
            if range_units == "km" and units == "m":
                return lo * 1000, hi * 1000
            else:
                return lo, hi
        raise ValueError('unknown operational range from "%s","%s"' % (contents, units))

    @staticmethod
    # return a list of int of the start bits ([some_bit_pos] or [some_bit_pos,some_other_bit_pos]) of the SPN; or [
    # -1] (if unknown or variable).
    def get_spn_start_bit(contents):
        norm_contents = str(contents).lower().strip()

        if norm_contents == "":
            return [0]

        if (
            norm_contents == "n/a" or ";" in norm_contents
        ):  # special handling for e.g. '0x00;2'
            return [-1]

        # Explanation of multi-startbit (from J4L): According to 1939-71, "If the data length is larger than 1 byte
        # or the data spans a byte boundary, then the Start Position consists of two numerical values separated by a
        # comma or dash." Therefore , and - may be treated in the same way, multi-startbit. To account for
        # multi-startbit we will introduce the following: 1> an SPN position is now a pair of bit positions (R,S),
        # where S = None if not multibit 2> the SPN length is now a pair (Rs, Ss), where Ss = None if not multibit,
        # else net Rs = (S - R + 1) and Ss = (Length - Rs)

        delim = ""
        firsts = [norm_contents]
        if "," in norm_contents:
            delim = ","
        if "-" in norm_contents:
            delim = "-"
        elif " to " in norm_contents:
            delim = " to "

        if len(delim) > 0:
            firsts = norm_contents.split(delim)

        if any(re.match(r"^[a-z]\+[0-9]", first) for first in firsts):
            return [-1]

        firsts = [J1939daConverter.just_numeric_expr(first) for first in firsts]
        if any(first.strip() == "" for first in firsts):
            return [-1]

        pos_pair = []
        for first in firsts:
            if "." in first:
                byte_index, bit_index = list(map(int, first.split(".")))
            else:
                bit_index = 1
                byte_index = int(first)
            pos_pair.append((byte_index - 1) * 8 + (bit_index - 1))

        # If we have a range like 1-2, it's often just a contiguous multi-byte field.
        # If it's contiguous, we only need the first start bit.
        # A range is contiguous if SPNLength is (pos_pair[-1] - pos_pair[0] + 8) or similar,
        # but here we don't have SPNLength yet.
        # However, for J1939, if bit_index is 1 for all parts of a range, it's byte-aligned contiguous.
        if len(pos_pair) > 1:
            # Check if it's a simple byte range like [0, 8, 16]
            is_simple_byte_range = True
            for i in range(len(pos_pair) - 1):
                if pos_pair[i + 1] != pos_pair[i] + 8:
                    is_simple_byte_range = False
                    break
            if is_simple_byte_range:
                return [pos_pair[0]]

        return pos_pair

    @staticmethod
    def is_enum_line(line):
        line_norm = line.lower().strip()
        if line_norm.startswith("bit state"):
            return True
        # Match "00b =", "01b =", "10b =", "11b =", "00 =", "0x1 =" etc.
        if re.match(r"^[ ]*[0-9bxXA-F\-:]+[ ]*[-=:]", line):
            return True
        # Fallback for old style
        elif re.match(r"^[ ]*[0-9][0-9bxXA-F\-:]*[ ]+[^ ]+", line):
            return True
        return False

    @staticmethod
    def get_enum_lines(description_lines):
        enum_lines = list()

        def add_enum_line(test_line):
            test_line = re.sub(
                r"(Bit States|Bit State)", "", test_line, flags=re.IGNORECASE
            )
            if any(
                e in test_line
                for e in [
                    ":  Tokyo",
                    " SPN 8846 ",
                    " SPN 8842 ",
                    " SPN 3265 ",
                    " SPN 3216 ",
                    "13 preprogrammed intermediate ",
                    "3 ASCII space characters",
                ]
            ):
                return False
            enum_lines.append(test_line)
            return True

        any_found = False
        for line in description_lines:
            is_enum = J1939daConverter.is_enum_line(line)
            if is_enum:
                if any_found:
                    add_enum_line(line)
                else:
                    if J1939daConverter.match_single_enum_line(
                        line
                    ):  # special handling: first enum must use single assignment
                        any_found = add_enum_line(line)
        return enum_lines

    @staticmethod
    def is_enum_lines_binary(enum_lines_only):
        all_ones_and_zeroes = True
        for line in enum_lines_only:
            match = J1939daConverter.match_single_enum_line(line)
            if not match:
                all_ones_and_zeroes = False
                break
            first = match.groups()[0]
            if re.sub(r"[^10b]", "", first) != first:
                all_ones_and_zeroes = False
                break

        return all_ones_and_zeroes

    @staticmethod
    # returns a pair of inclusive, inclusive range boundaries or None if this line is not a range
    def get_enum_line_range(line):
        match = re.match(ENUM_RANGE_LINE_RE, line)
        if match:
            groups = match.groups()
            return groups[0], groups[2]
        else:
            return None

    @staticmethod
    def match_single_enum_line(line):
        line = re.sub(r"[ ]+", " ", line)
        line = re.sub(r"[ ]?\-\-[ ]?", " = ", line)
        return re.match(ENUM_SINGLE_LINE_RE, line)

    @staticmethod
    # returns the description part (just that part) of an enum line
    def get_enum_line_description(line):
        # Additional cleanup for artifacts that might be in multiline descriptions
        line = re.sub(r"_x[0-9a-fA-F]{4}_", " ", line)
        line = re.sub(r"[ ]+", " ", line)
        line = re.sub(r"[ ]?\-\-[ ]?", " = ", line)
        match = re.match(ENUM_RANGE_LINE_RE, line)
        if match:
            line = match.groups()[-1]
        else:
            match = J1939daConverter.match_single_enum_line(line)
            if match:
                line = match.groups()[-1]
        line = line.strip()
        line = line.lower()
        line = line.replace("sae", "SAE").replace("iso", "ISO")
        return line

    @staticmethod
    def create_bit_object_from_description(spn_description, bit_object):
        description_lines = spn_description.splitlines()
        enum_lines = J1939daConverter.get_enum_lines(description_lines)
        is_binary = J1939daConverter.is_enum_lines_binary(enum_lines)

        for line in enum_lines:
            enum_description = J1939daConverter.get_enum_line_description(line)

            range_boundaries = J1939daConverter.get_enum_line_range(line)
            if range_boundaries is not None:
                try:
                    if is_binary:
                        first = re.sub(r"b", "", range_boundaries[0])
                        first_val = int(first, base=2)
                        second = re.sub(r"b", "", range_boundaries[1])
                        second_val = int(second, base=2)
                    elif "x" in range_boundaries[0].lower() or any(
                        c in range_boundaries[0].upper() for c in "ABCDEF"
                    ):
                        first_val = int(
                            range_boundaries[0].lower().replace("0x", ""), base=16
                        )
                        second_val = int(
                            range_boundaries[1].lower().replace("0x", ""), base=16
                        )
                    else:
                        first_val = int(range_boundaries[0], base=10)
                        second_val = int(range_boundaries[1], base=10)

                    for i in range(first_val, second_val + 1):
                        val_str = str(i)
                        if val_str not in bit_object:
                            bit_object.update(({val_str: enum_description}))
                except ValueError as e:
                    print(f"Skipping enum value due to error: {e}")
                    continue
            else:
                match = re.match(r"[ ]*([0-9bxXA-F]+)", line)
                if not match:
                    continue
                first = match.groups()[0]

                try:
                    if is_binary:
                        first = re.sub(r"b", "", first)
                        val = str(int(first, base=2))
                    elif "x" in first.lower() or any(
                        c in first.upper() for c in "ABCDEF"
                    ):
                        val = str(int(first.lower().replace("0x", ""), base=16))
                    else:
                        val = str(int(first, base=10))

                    if val not in bit_object:
                        bit_object.update(({val: enum_description}))
                except ValueError as e:
                    print(f"Skipping enum value due to error: {e}")
                    continue

    @staticmethod
    def is_spn_likely_bitmapped(spn_description):
        return len(J1939daConverter.get_enum_lines(spn_description.splitlines())) > 2


    def _get_column_indices(self, header_row):
        return {
            "pgn": self.get_any_header_column(header_row, "PGN"),
            "spn": self.get_any_header_column(header_row, "SPN"),
            "acronym": self.get_any_header_column(header_row, ["ACRONYM", "PG_ACRONYM"]),
            "pgn_label": self.get_any_header_column(header_row, ["PARAMETER_GROUP_LABEL", "PG_LABEL"]),
            "pgn_data_length": self.get_any_header_column(header_row, ["PGN_DATA_LENGTH", "PG_DATA_LENGTH"]),
            "transmission_rate": self.get_any_header_column(header_row, "TRANSMISSION_RATE"),
            "spn_position_in_pgn": self.get_any_header_column(header_row, ["SPN_POSITION_IN_PGN", "SP_POSITION_IN_PG"]),
            "spn_name": self.get_any_header_column(header_row, ["SPN_NAME", "SP_LABEL"]),
            "offset": self.get_any_header_column(header_row, "OFFSET"),
            "data_range": self.get_any_header_column(header_row, "DATA_RANGE"),
            "resolution": self.get_any_header_column(header_row, ["RESOLUTION", "SCALING"]),
            "spn_length": self.get_any_header_column(header_row, ["SPN_LENGTH", "SP_LENGTH"]),
            "units": self.get_any_header_column(header_row, ["UNITS", "UNIT"]),
            "operational_range": self.get_any_header_column(header_row, "OPERATIONAL_RANGE"),
            "spn_description": self.get_any_header_column(header_row, ["SPN_DESCRIPTION", "SP_DESCRIPTION"])
        }

    def _process_pgn(self, row, cols, pgn, j1939_pgn_db):
        
        pgn_label = str(int(pgn))
        if j1939_pgn_db.get(pgn_label) is not None:
            return pgn_label

        pgn_object = OrderedDict()
        pgn_data_len = self.get_pgn_data_len(row[cols["pgn_data_length"]])

        pgn_object.update({"Label": (unidecode.unidecode(str(row[cols["acronym"]])) if row[cols["acronym"]] is not None else "")})
        pgn_object.update({"Name": (unidecode.unidecode(str(row[cols["pgn_label"]])) if row[cols["pgn_label"]] is not None else "")})
        pgn_object.update({"PGNLength": pgn_data_len})
        pgn_object.update({"Rate": (unidecode.unidecode(str(row[cols["transmission_rate"]])) if row[cols["transmission_rate"]] is not None else "")})
        pgn_object.update({"SPNs": list()})
        pgn_object.update({"SPNStartBits": list()})
        pgn_object.update({"Temp_SPN_Order": list()})

        j1939_pgn_db.update({pgn_label: pgn_object})
        return pgn_label

    def _process_spn(self, row, cols, spn_label, j1939_spn_db):

        spn_object = OrderedDict()
        spn_length = self.get_spn_len(row[cols["spn_length"]])
        if type(spn_length) == str and spn_length.startswith("Variable"):
            spn_delimiter = self.get_spn_delimiter(str(row[cols["spn_length"]]))
        else:
            spn_delimiter = None

        spn_resolution = (self.get_spn_resolution(str(row[cols["resolution"]])) if row[cols["resolution"]] is not None else 0)
        spn_units = self.get_spn_units(
            str(row[cols["units"]]) if row[cols["units"]] is not None else "",
            str(row[cols["resolution"]]) if row[cols["resolution"]] is not None else "",
        )

        data_range = (unidecode.unidecode(str(row[cols["data_range"]])) if row[cols["data_range"]] is not None else "")
        low, high = self.get_operational_hilo(data_range, spn_units, spn_length)

        spn_name = (unidecode.unidecode(str(row[cols["spn_name"]])) if row[cols["spn_name"]] is not None else "")
        operational_range = (unidecode.unidecode(str(row[cols["operational_range"]])) if row[cols["operational_range"]] is not None else "")
        spn_offset = (self.get_spn_offset(str(row[cols["offset"]])) if row[cols["offset"]] is not None else 0)

        spn_object.update({"DataRange": data_range})
        spn_object.update({"Name": spn_name})
        spn_object.update({"Offset": spn_offset})
        spn_object.update({"OperationalHigh": high})
        spn_object.update({"OperationalLow": low})
        spn_object.update({"OperationalRange": operational_range})
        spn_object.update({"Resolution": spn_resolution})
        spn_object.update({"SPNLength": spn_length})
        if spn_delimiter is not None:
            spn_object.update({"Delimiter": "0x%s" % spn_delimiter.hex()})
        spn_object.update({"Units": spn_units})

        existing_spn = j1939_spn_db.get(spn_label)
        if existing_spn is not None and not existing_spn == spn_object:
            print("Warning: changed details of SPN %s:\n %s vs previous:\n %s" % (spn_label, existing_spn, spn_object), file=sys.stderr)
        else:
            j1939_spn_db.update({spn_label: spn_object})
            
        return spn_units

    def _get_spn_startbit(self, spn_label, spn_position_contents):
        spn_startbit_inpgn = self.get_spn_start_bit(spn_position_contents)
        if spn_label == "5998" and spn_position_contents.strip() == "4.4":
            spn_startbit_inpgn = self.get_spn_start_bit("4.5")
        elif spn_label == "3036" and spn_position_contents.strip() == "6-8.6":
            spn_startbit_inpgn = self.get_spn_start_bit("6-7,8.6")
        elif spn_label == "6062" and spn_position_contents.strip() == "4.4":
            spn_startbit_inpgn = self.get_spn_start_bit("4.5")
        elif spn_label == "6030" and spn_position_contents.strip() == "4.4":
            spn_startbit_inpgn = self.get_spn_start_bit("4.5")
        elif spn_label == "1836" and "8.5" in spn_position_contents:
            spn_startbit_inpgn = self.get_spn_start_bit("8.1")
        elif spn_label == "7941" and "8.1" in spn_position_contents:
            spn_startbit_inpgn = self.get_spn_start_bit("8.5")

        if spn_startbit_inpgn == [-1]:
            spn_order_inpgn = spn_position_contents.strip()
        else:
            spn_order_inpgn = spn_startbit_inpgn
        return spn_startbit_inpgn, spn_order_inpgn

    def process_spns_and_pgns_tab(self, sheet):
        
        self.j1939db.update({"J1939PGNdb": OrderedDict()})
        j1939_pgn_db = self.j1939db.get("J1939PGNdb")
        self.j1939db.update({"J1939SPNdb": OrderedDict()})
        j1939_spn_db = self.j1939db.get("J1939SPNdb")
        self.j1939db.update({"J1939BitDecodings": OrderedDict()})
        j1939_bit_decodings = self.j1939db.get("J1939BitDecodings")

        spn_factcheck_map = dict()

        header_row, header_row_num = self.get_header_row(sheet)
        cols = self._get_column_indices(header_row)

        for i in range(header_row_num + 1, sheet.nrows):
            row = sheet.row_values(i)
            pgn = row[cols["pgn"]]
            if pgn is None or pgn == "" or pgn == "N/A":
                continue

            pgn_label = self._process_pgn(row, cols, pgn, j1939_pgn_db)

            if describe.is_transport_pgn(int(pgn)):
                continue

            spn = row[cols["spn"]]
            if not spn == "" and not spn == "N/A" and spn is not None:
                if spn_factcheck_map.get(spn, None) is None:
                    spn_factcheck_map.update({spn: [pgn]})
                else:
                    spn_list = spn_factcheck_map.get(spn)
                    spn_list.append(spn)
                    spn_factcheck_map.update({spn: spn_list})

                spn_label = str(int(spn))
                spn_units = self._process_spn(row, cols, spn_label, j1939_spn_db)

                try:
                    spn_position_contents = (str(row[cols["spn_position_in_pgn"]]) if row[cols["spn_position_in_pgn"]] is not None else "")
                    spn_startbit_inpgn, spn_order_inpgn = self._get_spn_startbit(spn_label, spn_position_contents)
                except ValueError as e:
                    print(f"Skipping enum value due to error: {e}")
                    continue

                if spn_label == "6610" or spn_label == "6815":
                    continue

                j1939_pgn_db.get(pgn_label).get("SPNs").append(int(spn))
                j1939_pgn_db.get(pgn_label).get("SPNStartBits").append([int(s) for s in spn_startbit_inpgn])
                j1939_pgn_db.get(pgn_label).get("Temp_SPN_Order").append(spn_order_inpgn)

                spn_description = (unidecode.unidecode(str(row[cols["spn_description"]])) if row[cols["spn_description"]] is not None else "")
                if spn_units == "bit" or self.is_spn_likely_bitmapped(spn_description):
                    bit_object = OrderedDict()
                    self.create_bit_object_from_description(spn_description, bit_object)
                    if len(bit_object) > 0:
                        j1939_bit_decodings.update({spn_label: bit_object})

        self.sort_spns_by_order(j1939_pgn_db)
        self.remove_startbitsunknown_spns(j1939_pgn_db, j1939_spn_db)
        self.fix_omittedlen_spns(j1939_pgn_db, j1939_spn_db)
        self.remove_underspecd_spns(j1939_pgn_db, j1939_spn_db)

        for pgn, pgn_object in j1939_pgn_db.items():
            pgn_object.pop("Temp_SPN_Order")

        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get("SPNs")
            if len(spn_list) == 0:
                pgn_object.pop("SPNStartBits")

        return

    def get_any_header_column(self, header_row, header_texts):
        if not isinstance(header_texts, list):
            header_texts = [header_texts]
        for t in header_texts:
            try:
                return header_row.index(t)
            except ValueError as e:
                pass
        return -1

    def get_header_row(self, sheet):
        header_row_num = self.lookup_header_row(sheet)

        header_row = sheet.row_values(header_row_num)
        header_row = list(
            map(lambda x: str(x).upper() if x is not None else "", header_row)
        )
        header_row = list(map(lambda x: x.replace(" ", "_"), header_row))
        return header_row, header_row_num

    def lookup_header_row(self, sheet):
        # search for a row containing known headers
        # look in first 10 rows
        for i in range(min(10, sheet.nrows)):
            row = sheet.row_values(i)
            # Use exact match for headers after cleaning
            row_str = [
                str(x).replace(" ", "_").upper() if x is not None else "" for x in row
            ]
            # A valid header row should have multiple columns and match our patterns
            populated_cols = len(
                [x for x in row if x is not None and str(x).strip() != ""]
            )
            if populated_cols < 2:
                continue

            if (
                ("PGN" in row_str and ("SPN" in row_str or "SP" in row_str))
                or ("SOURCE_ADDRESS_ID" in row_str or "SOURCE_ADDRESS" in row_str)
                or (
                    "MANUFACTURER_CODE" in row_str
                    or "MANUFACTURER_ID" in row_str
                    or "MFR_ID" in row_str
                    or "MANUFACTURER" in row_str
                )
                or (
                    "INDUSTRY_GROUP_CODE" in row_str
                    or "INDUSTRY_GROUP_ID" in row_str
                    or "INDUSTRY_GROUP" in row_str
                )
                or (
                    "VEHICLE_SYSTEM_CODE" in row_str
                    or "VEHICLE_SYSTEM_ID" in row_str
                    or "VEHICLE_SYSTEM" in row_str
                )
                or (
                    "FUNCTION_CODE" in row_str
                    or "FUNCTION_ID" in row_str
                    or "FUNCTION" in row_str
                )
            ):
                return i
        return 0

    @staticmethod
    def fix_omittedlen_spns(j1939_pgn_db, j1939_spn_db):
        modified_spns = dict()
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get("SPNs")
            spn_startbit_list = pgn_object.get("SPNStartBits")
            spn_order_list = pgn_object.get("Temp_SPN_Order")

            spn_in_pgn_list = list(zip(spn_list, spn_startbit_list, spn_order_list))
            if J1939daConverter.all_spns_positioned(spn_startbit_list):
                for i in range(0, len(spn_in_pgn_list) - 1):
                    here_startbit = int(spn_in_pgn_list[i][1][0])
                    next_startbit = int(spn_in_pgn_list[i + 1][1][0])
                    calced_spn_length = next_startbit - here_startbit
                    here_spn = spn_in_pgn_list[i][0]

                    if calced_spn_length == 0:
                        continue
                    else:
                        spn_obj = j1939_spn_db.get(str(here_spn))
                        current_spn_length = spn_obj.get("SPNLength")
                        if J1939daConverter.is_length_variable(current_spn_length):
                            spn_obj.update({"SPNLength": calced_spn_length})
                            modified_spns.update({here_spn: True})
                        elif (
                            calced_spn_length < current_spn_length
                            and modified_spns.get(here_spn) is None
                        ):
                            print(
                                "Warning: calculated length for SPN %s (%d) in PGN %s differs from existing SPN "
                                "length %s"
                                % (
                                    here_spn,
                                    calced_spn_length,
                                    pgn,
                                    current_spn_length,
                                ),
                                file=sys.stderr,
                            )

    @staticmethod
    def is_length_variable(spn_length):
        return type(spn_length) is str and spn_length.startswith("Variable")

    @staticmethod
    def remove_startbitsunknown_spns(j1939_pgn_db, j1939_spn_db):
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get("SPNs")
            if len(spn_list) > 1:
                spn_list = pgn_object.get("SPNs")
                spn_startbit_list = pgn_object.get("SPNStartBits")
                spn_order_list = pgn_object.get("Temp_SPN_Order")

                spn_in_pgn_list = list(zip(spn_list, spn_startbit_list, spn_order_list))
                for i in range(0, len(spn_in_pgn_list)):
                    here_startbit = int(spn_in_pgn_list[i][1][0])
                    prev_spn = spn_in_pgn_list[i - 1][0]
                    prev_spn_obj = j1939_spn_db.get(str(prev_spn))
                    prev_spn_len = prev_spn_obj.get("SPNLength")
                    if (
                        here_startbit == -1
                        and not J1939daConverter.is_length_variable(prev_spn_len)
                        and isinstance(prev_spn_len, (int, float))
                    ):
                        if (i - 1) == 0:  # special case for the first field
                            prev_startbit = 0
                            here_startbit = int(prev_spn_len)
                            prev_tuple = list(spn_in_pgn_list[i - 1])
                            prev_tuple[1] = [prev_startbit]
                            spn_in_pgn_list[i - 1] = tuple(prev_tuple)
                        else:
                            prev_startbit = int(spn_in_pgn_list[i - 1][1][0])
                            if prev_startbit != -1:
                                here_startbit = prev_startbit + int(prev_spn_len)
                            else:
                                here_startbit = -1

                        if here_startbit != -1:
                            here_tuple = list(spn_in_pgn_list[i])
                            here_tuple[1] = [here_startbit]
                            spn_in_pgn_list[i] = tuple(here_tuple)

                # update the maps
                pgn_object.update(
                    {"SPNs": list(map(operator.itemgetter(0), spn_in_pgn_list))}
                )
                pgn_object.update(
                    {"SPNStartBits": list(map(operator.itemgetter(1), spn_in_pgn_list))}
                )
                pgn_object.update(
                    {
                        "Temp_SPN_Order": list(
                            map(operator.itemgetter(2), spn_in_pgn_list)
                        )
                    }
                )

    @staticmethod
    def remove_underspecd_spns(j1939_pgn_db, j1939_spn_db):
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get("SPNs")
            if len(spn_list) > 1:
                spn_list = pgn_object.get("SPNs")
                spn_startbit_list = pgn_object.get("SPNStartBits")
                spn_order_list = pgn_object.get("Temp_SPN_Order")

                spn_in_pgn_list = zip(spn_list, spn_startbit_list, spn_order_list)

                def should_remove(tup):
                    spn = tup[0]
                    spn_obj = j1939_spn_db.get(str(spn))
                    current_spn_length = spn_obj.get("SPNLength")
                    current_spn_delimiter = spn_obj.get("Delimiter")
                    if (
                        J1939daConverter.is_length_variable(current_spn_length)
                        and current_spn_delimiter is None
                    ):
                        print(
                            "Warning: removing SPN %s from PGN %s because it "
                            "is variable-length with no delimiter in a multi-SPN PGN. "
                            "This likely an under-specification in the DA."
                            % (spn, pgn),
                            file=sys.stderr,
                        )
                        return True
                    return False

                spn_in_pgn_list = [
                    tup for tup in spn_in_pgn_list if not should_remove(tup)
                ]

                # update the maps
                pgn_object.update(
                    {"SPNs": list(map(operator.itemgetter(0), spn_in_pgn_list))}
                )
                pgn_object.update(
                    {"SPNStartBits": list(map(operator.itemgetter(1), spn_in_pgn_list))}
                )
                pgn_object.update(
                    {
                        "Temp_SPN_Order": list(
                            map(operator.itemgetter(2), spn_in_pgn_list)
                        )
                    }
                )

    @staticmethod
    def sort_spns_by_order(j1939_pgn_db):
        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get("SPNs")
            spn_startbit_list = pgn_object.get("SPNStartBits")
            spn_order_list = pgn_object.get("Temp_SPN_Order")

            spn_in_pgn_list = zip(spn_list, spn_startbit_list, spn_order_list)
            # sort numbers then letters
            spn_in_pgn_list = sorted(
                spn_in_pgn_list, key=lambda obj: (isinstance(obj[2], str), obj[2])
            )

            # update the maps (now sorted by 'Temp_SPN_Order')
            pgn_object.update(
                {"SPNs": list(map(operator.itemgetter(0), spn_in_pgn_list))}
            )
            pgn_object.update(
                {"SPNStartBits": list(map(operator.itemgetter(1), spn_in_pgn_list))}
            )
            pgn_object.update(
                {"Temp_SPN_Order": list(map(operator.itemgetter(2), spn_in_pgn_list))}
            )

    @staticmethod
    def all_spns_positioned(spn_startbit_list):
        if len(spn_startbit_list) == 0:
            return True
        else:
            is_positioned = map(
                lambda spn_startbit: int(spn_startbit[0]) != -1, spn_startbit_list
            )
            return functools.reduce(lambda a, b: a and b, is_positioned)

    def process_any_source_addresses_sheet(self, sheet):
        if self.j1939db.get("J1939SATabledb") is None:
            self.j1939db.update({"J1939SATabledb": OrderedDict()})
        j1939_sa_tabledb = self.j1939db.get("J1939SATabledb")

        header_row, header_row_num = self.get_header_row(sheet)

        source_address_id_col = self.get_any_header_column(
            header_row, ["SOURCE_ADDRESS_ID", "SOURCE_ADDRESS", "ID"]
        )
        name_col = self.get_any_header_column(header_row, "NAME")

        for i in range(header_row_num + 1, sheet.nrows):
            row = sheet.row_values(i)

            name = (
                unidecode.unidecode(str(row[name_col]))
                if row[name_col] is not None
                else ""
            )
            if name.startswith("thru") or name.startswith("through"):
                try:
                    start_range = int(row[source_address_id_col])
                    range_clues = name.replace("thru", "").replace("through", "")
                    range_clues = range_clues.strip()
                    end_range = int(range_clues.split(" ")[0])
                    description = "".join(name.split(str(end_range))[1:]).strip()
                    description = (
                        description
                        + " "
                        + (
                            unidecode.unidecode(str(row[name_col + 1]))
                            if row[name_col + 1] is not None
                            else ""
                        )
                    )
                    description = re.sub(r"^are ", "", description)
                    description = description.strip()
                    for val in range(start_range, end_range + 1):
                        j1939_sa_tabledb.update({str(val): description})
                except (ValueError, TypeError, IndexError) as e:
                    print(f"Skipping SA range due to error: {e}")
                    continue
            elif (
                source_address_id_col != -1
                and row[source_address_id_col] is not None
                and row[source_address_id_col] != ""
            ):
                try:
                    val = str(int(row[source_address_id_col]))
                    name = name.strip()
                    j1939_sa_tabledb.update({val: name})
                except (ValueError, TypeError) as e:
                    print(f"Skipping row due to error: {e}")
                    continue
        return

    def process_manufacturers_sheet(self, sheet):
        if sheet is None:
            return
        if self.j1939db.get("J1939Manufacturerdb") is None:
            self.j1939db.update({"J1939Manufacturerdb": OrderedDict()})
        mfr_db = self.j1939db.get("J1939Manufacturerdb")

        header_row, header_row_num = self.get_header_row(sheet)
        id_col = self.get_any_header_column(
            header_row, ["MANUFACTURER_CODE", "MANUFACTURER_ID", "MFR_ID", "ID"]
        )
        name_col = self.get_any_header_column(
            header_row, ["MANUFACTURER_NAME", "MANUFACTURER", "NAME"]
        )

        for i in range(header_row_num + 1, sheet.nrows):
            row = sheet.row_values(i)
            if (
                id_col != -1
                and name_col != -1
                and row[id_col] is not None
                and row[id_col] != ""
            ):
                try:
                    val = str(int(row[id_col]))
                    name = unidecode.unidecode(str(row[name_col])).strip()
                    mfr_db.update({val: name})
                except (ValueError, TypeError) as e:
                    print(f"Skipping row due to error: {e}")
                    continue

    def process_industry_groups_sheet(self, sheet):
        if sheet is None:
            return
        if self.j1939db.get("J1939IndustryGroupdb") is None:
            self.j1939db.update({"J1939IndustryGroupdb": OrderedDict()})
        ig_db = self.j1939db.get("J1939IndustryGroupdb")

        header_row, header_row_num = self.get_header_row(sheet)
        id_col = self.get_any_header_column(
            header_row, ["INDUSTRY_GROUP_CODE", "INDUSTRY_GROUP_ID", "ID"]
        )
        name_col = self.get_any_header_column(
            header_row, ["INDUSTRY_GROUP_NAME", "INDUSTRY_GROUP_DESCRIPTION", "NAME"]
        )

        for i in range(header_row_num + 1, sheet.nrows):
            row = sheet.row_values(i)
            if (
                id_col != -1
                and name_col != -1
                and row[id_col] is not None
                and row[id_col] != ""
            ):
                try:
                    val = str(int(row[id_col]))
                    name = unidecode.unidecode(str(row[name_col])).strip()
                    ig_db.update({val: name})
                except (ValueError, TypeError) as e:
                    print(f"Skipping row due to error: {e}")
                    continue

    def process_vehicle_systems_sheet(self, sheet, ig_val=None):
        if sheet is None:
            return
        if self.j1939db.get("J1939VehicleSystemdb") is None:
            self.j1939db.update({"J1939VehicleSystemdb": OrderedDict()})
        vs_db = self.j1939db.get("J1939VehicleSystemdb")

        header_row, header_row_num = self.get_header_row(sheet)
        id_col = self.get_any_header_column(
            header_row, ["VEHICLE_SYSTEM_CODE", "VEHICLE_SYSTEM_ID", "ID"]
        )
        name_col = self.get_any_header_column(
            header_row, ["VEHICLE_SYSTEM_NAME", "VEHICLE_SYSTEM_DESCRIPTION", "NAME"]
        )

        for i in range(header_row_num + 1, sheet.nrows):
            row = sheet.row_values(i)
            if (
                id_col != -1
                and name_col != -1
                and row[id_col] is not None
                and row[id_col] != ""
            ):
                try:
                    val = str(int(row[id_col]))
                    name = unidecode.unidecode(str(row[name_col])).strip()
                    if ig_val is not None:
                        key = f"{ig_val}_{val}"
                        vs_db.update({key: name})
                    else:
                        vs_db.update({val: name})
                except (ValueError, TypeError) as e:
                    print(f"Skipping row due to error: {e}")
                    continue

    def process_functions_sheet(self, sheet, ig_val=None, vs_val=None):
        if sheet is None:
            return
        if self.j1939db.get("J1939Functiondb") is None:
            self.j1939db.update({"J1939Functiondb": OrderedDict()})
        func_db = self.j1939db.get("J1939Functiondb")

        header_row, header_row_num = self.get_header_row(sheet)

        ig_id_col = self.get_any_header_column(header_row, ["INDUSTRY_GROUP_ID"])
        vs_id_col = self.get_any_header_column(header_row, ["VEHICLE_SYSTEM_ID"])
        vs_name_col = self.get_any_header_column(
            header_row, ["VEHICLE_SYSTEM_DESCRIPTION"]
        )
        id_col = self.get_any_header_column(
            header_row, ["FUNCTION_CODE", "FUNCTION_ID", "ID"]
        )
        name_col = self.get_any_header_column(
            header_row, ["FUNCTION_NAME", "FUNCTION_DESCRIPTION", "NAME"]
        )

        for i in range(header_row_num + 1, sheet.nrows):
            row = sheet.row_values(i)
            if (
                id_col != -1
                and name_col != -1
                and row[id_col] is not None
                and row[id_col] != ""
            ):
                try:
                    val = int(row[id_col])
                    name = unidecode.unidecode(str(row[name_col])).strip()

                    row_ig_val = ig_val
                    if (
                        ig_id_col != -1
                        and row[ig_id_col] is not None
                        and row[ig_id_col] != ""
                    ):
                        row_ig_val = int(row[ig_id_col])

                    row_vs_val = vs_val
                    if (
                        vs_id_col != -1
                        and row[vs_id_col] is not None
                        and row[vs_id_col] != ""
                    ):
                        row_vs_val = int(row[vs_id_col])

                    if val <= 127:
                        func_db.update({str(val): name})
                    elif row_ig_val is not None and row_vs_val is not None:
                        key = f"{row_ig_val}_{row_vs_val}_{val}"
                        func_db.update({key: name})

                    if vs_id_col != -1 and vs_name_col != -1 and row_ig_val is not None:
                        vs_id = str(int(row[vs_id_col]))
                        vs_name = unidecode.unidecode(str(row[vs_name_col])).strip()
                        if self.j1939db.get("J1939VehicleSystemdb") is None:
                            self.j1939db.update({"J1939VehicleSystemdb": OrderedDict()})
                        self.j1939db["J1939VehicleSystemdb"].update(
                            {f"{row_ig_val}_{vs_id}": vs_name}
                        )

                except (ValueError, TypeError) as e:
                    print(f"Skipping row due to error: {e}")
                    continue

    def convert(self, output_file):
        self.j1939db = OrderedDict()
        sheet_name = ["SPNs & PGNs", "SPs & PGs"]
        pgn_spn_sheet = self.find_first_sheet_by_name(sheet_name)
        if pgn_spn_sheet:
            self.process_spns_and_pgns_tab(pgn_spn_sheet)

        for sa_sheet_name in [
            "Global Source Addresses (B2)",
            "Global Source Addresses",
            "IG1 Source Addresses (B3)",
            "IG1 Source Addresses",
        ]:
            sheet = self.find_first_sheet_by_name(sa_sheet_name)
            if sheet:
                self.process_any_source_addresses_sheet(sheet)

        mfr_sheet = self.find_first_sheet_by_name(
            [
                "Manufacturers (B1)",
                "Manufacturers",
                "Manufacturer IDs (B10)",
                "Manufacturer IDs",
            ]
        )
        if mfr_sheet:
            self.process_manufacturers_sheet(mfr_sheet)

        ig_sheet = self.find_first_sheet_by_name(
            [
                "Global Industry Groups (B4)",
                "Global Industry Groups",
                "Industry Groups (B1)",
                "Industry Groups",
            ]
        )
        if ig_sheet:
            self.process_industry_groups_sheet(ig_sheet)

        vs_sheet = self.find_first_sheet_by_name(
            ["Global Vehicle Systems (B5)", "Global Vehicle Systems", "Vehicle Systems"]
        )
        if vs_sheet:
            self.process_vehicle_systems_sheet(vs_sheet)

        func_sheet = self.find_first_sheet_by_name(
            [
                "Global Functions (B6)",
                "Global Functions",
                "Global NAME Functions (B11)",
                "Global NAME Functions",
            ]
        )
        if func_sheet:
            self.process_functions_sheet(func_sheet)

        for ig in range(1, 6):
            ig_name = f"IG{ig}"
            vs_sheet_names = [
                f"{ig_name} Vehicle Systems",
                f" {ig_name} Vehicle Systems",
            ]
            sheet = self.find_first_sheet_by_name(vs_sheet_names)
            if sheet:
                self.process_vehicle_systems_sheet(sheet, ig_val=ig)

            func_sheet_names = [
                f"{ig_name} Functions",
                f" {ig_name} Functions",
                f"IG Specific NAME Function (B12)",
            ]
            sheet = self.find_first_sheet_by_name(func_sheet_names)
            if sheet:
                self.process_functions_sheet(sheet, ig_val=ig)

        out = open(output_file, "w") if output_file != "-" else sys.stdout

        try:
            out.write(json.dumps(self.j1939db, indent=2, sort_keys=False))
        except BrokenPipeError:
            pass

        if out is not sys.stdout:
            out.close()

        return

    def find_first_sheet_by_name(self, sheet_names):
        if not isinstance(sheet_names, list):
            sheet_names = [sheet_names]
        for sheet_name in sheet_names:
            for book in self.digital_annex_xls_list:
                if isinstance(book, openpyxl.workbook.workbook.Workbook):
                    if sheet_name in book.sheetnames:
                        return XlsxSheetWrapper(book[sheet_name])
                else:
                    if sheet_name in book.sheet_names():
                        return XlsSheetWrapper(book.sheet_by_name(sheet_name))
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f",
        "--digital_annex_xls",
        type=str,
        required=True,
        action="append",
        default=[],
        nargs="+",
        help="the J1939 Digital Annex .xls excel file used as input",
    )
    parser.add_argument(
        "-w",
        "--write-json",
        type=str,
        default="-",
        help="where to write the output. defaults to stdout",
    )
    args = parser.parse_args()

    all_inputs = itertools.chain(*args.digital_annex_xls)
    J1939daConverter(all_inputs).convert(args.write_json)


if __name__ == "__main__":
    main()
