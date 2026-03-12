import re
import sys

with open("pretty_j1939/create_j1939db_json.py", "r") as f:
    content = f.read()

new_methods = """
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
        from collections import OrderedDict
        import unidecode
        
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
        from collections import OrderedDict
        import unidecode
        import sys

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
            print("Warning: changed details of SPN %s:\\n %s vs previous:\\n %s" % (spn_label, existing_spn, spn_object), file=sys.stderr)
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
        from collections import OrderedDict
        from . import describe
        import unidecode
        import sys
        
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
"""

# Find the start and end of process_spns_and_pgns_tab
pattern = re.compile(r"^[ \\t]*def process_spns_and_pgns_tab\(self, sheet\):.*?(?=^[ \\t]*def get_any_header_column)", re.DOTALL | re.MULTILINE)

match = pattern.search(content)
if not match:
    print("Could not find process_spns_and_pgns_tab method!")
    sys.exit(1)

new_content = content[:match.start()] + new_methods + "\n" + content[match.end():]

with open("pretty_j1939/create_j1939db_json.py", "w") as f:
    f.write(new_content)
print("File successfully refactored.")
