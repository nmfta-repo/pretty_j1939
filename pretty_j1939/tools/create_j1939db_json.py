from ..core import da_parsers
#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
from collections import OrderedDict
from ..core import describe
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

__all__ = ["SheetWrapper", "XlsSheetWrapper", "XlsxSheetWrapper", "J1939daConverter"]

ENUM_SINGLE_LINE_RE = r"[ ]*([0-9bxXA-F]+)[ ]*[-=:]?[ ]*(.*)"
ENUM_RANGE_LINE_RE = (
    r"[ ]*([0-9bxXA-F]+)[ ]*(\-|to|thru)[ ]*([0-9bxXA-F]+)[ ]+[-=:]?[ ]*(.*)"
)


class SheetWrapper:
    def __init__(self, sheet):
        """  init   operation.
        
        Args:
            sheet: The sheet parameter.
        
        Returns:
            The result of the operation.
        """
        self.sheet = sheet

    @property
    def nrows(self):
        """Nrows operation.
        
        Returns:
            The result of the operation.
        """
        raise NotImplementedError()

    def row_values(self, row_num):
        """Row values operation.
        
        Args:
            row_num: The row num parameter.
        
        Returns:
            The result of the operation.
        """
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
        """Nrows operation.
        
        Returns:
            The result of the operation.
        """
        return self.sheet.nrows

    def row_values(self, row_num):
        """Row values operation.
        
        Args:
            row_num: The row num parameter.
        
        Returns:
            The result of the operation.
        """
        row = self.sheet.row_values(row_num)
        return [self._clean_value(v) for v in row]


class XlsxSheetWrapper(SheetWrapper):
    def __init__(self, sheet):
        """  init   operation.
        
        Args:
            sheet: The sheet parameter.
        
        Returns:
            The result of the operation.
        """
        super().__init__(sheet)
        # Cache all rows as a list of tuples of values for performance
        self._rows = list(sheet.values)

    @property
    def nrows(self):
        """Nrows operation.
        
        Returns:
            The result of the operation.
        """
        return len(self._rows)

    def row_values(self, row_num):
        """Row values operation.
        
        Args:
            row_num: The row num parameter.
        
        Returns:
            The result of the operation.
        """
        row = list(self._rows[row_num])
        return [self._clean_value(v) for v in row]


class J1939daConverter:
    def __init__(self, digital_annex_xls_list):
        """  init   operation.
        
        Args:
            digital_annex_xls_list: The digital annex xls list parameter.
        
        Returns:
            The result of the operation.
        """
        defusedxml.defuse_stdlib()
        self.j1939db = OrderedDict()
        self.digital_annex_xls_list = []
        for da in digital_annex_xls_list:
            book = da_parsers.secure_open_workbook(filename=da, on_demand=True)
            self.digital_annex_xls_list.append(book)

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
        pgn_data_len = da_parsers.get_pgn_data_len(row[cols["pgn_data_length"]])

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
        spn_length = da_parsers.get_spn_len(row[cols["spn_length"]])
        if type(spn_length) == str and spn_length.startswith("Variable"):
            spn_delimiter = da_parsers.get_spn_delimiter(str(row[cols["spn_length"]]))
        else:
            spn_delimiter = None

        spn_resolution = (da_parsers.get_spn_resolution(str(row[cols["resolution"]])) if row[cols["resolution"]] is not None else 0)
        spn_units = da_parsers.get_spn_units(
            str(row[cols["units"]]) if row[cols["units"]] is not None else "",
            str(row[cols["resolution"]]) if row[cols["resolution"]] is not None else "",
        )

        data_range = (unidecode.unidecode(str(row[cols["data_range"]])) if row[cols["data_range"]] is not None else "")
        low, high = da_parsers.get_operational_hilo(data_range, spn_units, spn_length)

        spn_name = (unidecode.unidecode(str(row[cols["spn_name"]])) if row[cols["spn_name"]] is not None else "")
        operational_range = (unidecode.unidecode(str(row[cols["operational_range"]])) if row[cols["operational_range"]] is not None else "")
        spn_offset = (da_parsers.get_spn_offset(str(row[cols["offset"]])) if row[cols["offset"]] is not None else 0)

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
        spn_startbit_inpgn = da_parsers.get_spn_start_bit(spn_position_contents)
        if spn_label == "5998" and spn_position_contents.strip() == "4.4":
            spn_startbit_inpgn = da_parsers.get_spn_start_bit("4.5")
        elif spn_label == "3036" and spn_position_contents.strip() == "6-8.6":
            spn_startbit_inpgn = da_parsers.get_spn_start_bit("6-7,8.6")
        elif spn_label == "6062" and spn_position_contents.strip() == "4.4":
            spn_startbit_inpgn = da_parsers.get_spn_start_bit("4.5")
        elif spn_label == "6030" and spn_position_contents.strip() == "4.4":
            spn_startbit_inpgn = da_parsers.get_spn_start_bit("4.5")
        elif spn_label == "1836" and "8.5" in spn_position_contents:
            spn_startbit_inpgn = da_parsers.get_spn_start_bit("8.1")
        elif spn_label == "7941" and "8.1" in spn_position_contents:
            spn_startbit_inpgn = da_parsers.get_spn_start_bit("8.5")

        if spn_startbit_inpgn == [-1]:
            spn_order_inpgn = spn_position_contents.strip()
        else:
            spn_order_inpgn = spn_startbit_inpgn
        return spn_startbit_inpgn, spn_order_inpgn

    def process_spns_and_pgns_tab(self, sheet):
        
        """Process spns and pgns tab operation.
        
        Args:
            sheet: The sheet parameter.
        
        Returns:
            The result of the operation.
        """
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
                if spn_units == "bit" or da_parsers.is_spn_likely_bitmapped(spn_description):
                    bit_object = OrderedDict()
                    da_parsers.create_bit_object_from_description(spn_description, bit_object)
                    if len(bit_object) > 0:
                        j1939_bit_decodings.update({spn_label: bit_object})

        da_parsers.sort_spns_by_order(j1939_pgn_db)
        da_parsers.remove_startbitsunknown_spns(j1939_pgn_db, j1939_spn_db)
        da_parsers.fix_omittedlen_spns(j1939_pgn_db, j1939_spn_db)
        da_parsers.remove_underspecd_spns(j1939_pgn_db, j1939_spn_db)

        for pgn, pgn_object in j1939_pgn_db.items():
            pgn_object.pop("Temp_SPN_Order")

        for pgn, pgn_object in j1939_pgn_db.items():
            spn_list = pgn_object.get("SPNs")
            if len(spn_list) == 0:
                pgn_object.pop("SPNStartBits")

        return

    def get_any_header_column(self, header_row, header_texts):
        """Gets any header column.
        
        Args:
            header_row: The header row parameter.
            header_texts: The header texts parameter.
        
        Returns:
            The result of the operation.
        """
        if not isinstance(header_texts, list):
            header_texts = [header_texts]
        for t in header_texts:
            try:
                return header_row.index(t)
            except ValueError as e:
                pass
        return -1

    def get_header_row(self, sheet):
        """Gets header row.
        
        Args:
            sheet: The sheet parameter.
        
        Returns:
            The result of the operation.
        """
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
        """Lookup header row operation.
        
        Args:
            sheet: The sheet parameter.
        
        Returns:
            The result of the operation.
        """
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

    def process_any_source_addresses_sheet(self, sheet):
        """Process any source addresses sheet operation.
        
        Args:
            sheet: The sheet parameter.
        
        Returns:
            The result of the operation.
        """
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
        """Process manufacturers sheet operation.
        
        Args:
            sheet: The sheet parameter.
        
        Returns:
            The result of the operation.
        """
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
        """Process industry groups sheet operation.
        
        Args:
            sheet: The sheet parameter.
        
        Returns:
            The result of the operation.
        """
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
        """Process vehicle systems sheet operation.
        
        Args:
            sheet: The sheet parameter.
            ig_val: The ig val parameter.
        
        Returns:
            The result of the operation.
        """
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
        """Process functions sheet operation.
        
        Args:
            sheet: The sheet parameter.
            ig_val: The ig val parameter.
            vs_val: The vs val parameter.
        
        Returns:
            The result of the operation.
        """
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
        """Convert operation.
        
        Args:
            output_file: The output file parameter.
        
        Returns:
            The result of the operation.
        """
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
        """Find first sheet by name operation.
        
        Args:
            sheet_names: The sheet names parameter.
        
        Returns:
            The result of the operation.
        """
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
    """Main operation.
    
    Returns:
        The result of the operation.
    """
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
