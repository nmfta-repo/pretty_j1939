#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import json
import bitstring
import sys
import math
import os
import importlib.resources
from collections import OrderedDict
from .parse import (
    parse_j1939_id,
    is_connection_management_message,
    is_data_transfer_message,
    is_spn_bitencoded,
    is_spn_numerical_values,
    is_transport_message,
    is_transport_pgn,
    DIAG3_MASK,
    PF_MASK,
)
from .isotp import IsoTpTracker


def get_spn_indicator_byte(value, length):
    """Returns the most significant byte of a parameter field for indicator checking.

    Args:
        value (int): The parameter value.
        length (int): The parameter length in bits.

    Returns:
        int: The most significant byte.
    """
    if length <= 8:
        return value
    # For multi-byte, the indicator is in the highest byte
    return value >> (length - 8)


def is_spn_error(value, length):
    """Checks if a raw SPN value is in the Error Indicator range.

    Args:
        value (int): The raw SPN value.
        length (int): The parameter length in bits.

    Returns:
        bool: True if the value is in the Error Indicator range.
    """
    if length >= 64:
        return False
    if length < 8:
        if length <= 1:
            return False
        return value == (1 << length) - 2
    ib = get_spn_indicator_byte(value, length)
    return ib == 0xFE


def is_spn_na(value, length):
    """Checks if a raw SPN value is in the Not Available range.

    Args:
        value (int): The raw SPN value.
        length (int): The parameter length in bits.

    Returns:
        bool: True if the value is in the Not Available range.
    """
    if length >= 64:
        return False
    if length < 8:
        if length <= 1:
            return False
        return value == (1 << length) - 1
    # Standard J1939: 0xFF in the MSB indicates Not Available for lengths >= 8
    ib = get_spn_indicator_byte(value, length)
    return ib == 0xFF


def is_spn_specific(value, length):
    """Checks if a raw SPN value is in the Parameter-specific range.

    Args:
        value (int): The raw SPN value.
        length (int): The parameter length in bits.

    Returns:
        bool: True if the value is in the Parameter-specific range.
    """
    if length < 8 or length >= 64:
        return False
    ib = get_spn_indicator_byte(value, length)
    return ib == 0xFB


def is_spn_reserved(value, length):
    """Checks if a raw SPN value is in the Reserved range.

    Args:
        value (int): The raw SPN value.
        length (int): The parameter length in bits.

    Returns:
        bool: True if the value is in the Reserved range.
    """
    if length < 8 or length >= 64:
        return False
    ib = get_spn_indicator_byte(value, length)
    return 0xFC <= ib <= 0xFD


ERROR_VAL = float("inf")  # Internal sentinel for Error
SPECIFIC_VAL = float("-inf")  # Internal sentinel for Specific
RESERVED_VAL = -1e18  # Internal sentinel for Reserved
PGN_LABEL = "PGN"
NA_NAN = float("nan")
EMPTY_BITS = bitstring.Bits(bytes=b"")


class NameTracker:
    """Tracks J1939 ECU names dynamically from Address Claimed (PGN 60928) messages."""

    def __init__(
        self, manufacturer_db=None, industry_db=None, function_db=None, vehicle_db=None
    ):
        self.dynamic_names = {}  # SA -> Decoded NAME dict
        self.manufacturer_db = manufacturer_db
        self.industry_db = industry_db
        self.function_db = function_db
        self.vehicle_db = vehicle_db

    def update(self, sa, decoded_name):
        self.dynamic_names[sa] = decoded_name

    def get_name(self, sa):
        decoded = self.dynamic_names.get(sa)
        if decoded:
            # The decoded name already contains the translated strings if the databases were provided.
            # Manufacturer Code: "4 (Dearborn Group Inc.)"
            # Function ID: "3 (Unknown Function)" or "129 (On-Highway Engine)"
            # Let's extract the translated part or fall back to the raw value.
            def get_pretty(val):
                if "(" in str(val) and ")" in str(val):
                    return str(val).split("(")[1].split(")")[0]
                return str(val)

            mfr = get_pretty(decoded.get("Manufacturer Code", "???"))
            func = get_pretty(decoded.get("Function ID", "???"))
            ident = decoded.get("Identity Number", "???")
            return f"{mfr} {func} ID:{ident}"
        return None


class DADescriber:
    def __init__(
        self,
        da_json,
        describe_pgns,
        describe_spns,
        describe_link_layer,
        describe_transport_layer,
        real_time,
        include_transport_rawdata,
        include_na,
        include_raw_data,
    ):
        self.pgn_objects = {}
        self.spn_objects = {}
        self.address_names = {}
        self.bit_encodings = {}
        self.manufacturer_db = {}
        self.industry_db = {}
        self.function_db = {}
        self.vehicle_db = {}

        if isinstance(da_json, dict):
            j1939db = da_json
        else:
            with open(da_json, "r") as j1939_file:
                j1939db = json.load(j1939_file)

        for pgn_label, pgn_object in j1939db.get("J1939PGNdb", {}).items():
            # TODO check for all expected fields on each object
            self.pgn_objects.update({int(pgn_label): pgn_object})

        for spn_label, spn_object in j1939db.get("J1939SPNdb", {}).items():
            # TODO check for all expected fields on each object
            self.spn_objects.update({int(spn_label): spn_object})

        for address, address_name in j1939db.get("J1939SATabledb", {}).items():
            # TODO check for all expected fields on each object
            self.address_names.update({int(address): address_name})

        for spn_label, bit_encoding in j1939db.get("J1939BitDecodings", {}).items():
            # TODO check for all expected fields on each object
            self.bit_encodings.update({int(spn_label): bit_encoding})

        self.manufacturer_db = j1939db.get("J1939Manufacturerdb", {})
        self.industry_db = j1939db.get("J1939IndustryGroupdb", {})
        self.function_db = j1939db.get("J1939Functiondb", {})
        self.vehicle_db = j1939db.get("J1939VehicleSystemdb", {})

        self.name_tracker = NameTracker(
            self.manufacturer_db, self.industry_db, self.function_db, self.vehicle_db
        )

        self.da_json = da_json if isinstance(da_json, str) else "in-memory"
        self.describe_pgns = describe_pgns
        self.describe_spns = describe_spns
        self.describe_link_layer = describe_link_layer
        self.describe_transport_layer = describe_transport_layer
        self.real_time = real_time
        self.include_transport_rawdata = include_transport_rawdata
        self.include_na = include_na
        self.include_raw_data = include_raw_data
        # performance optimization: cache SPN properties to avoid redundant dictionary lookups and pre-calculate
        # fixed values like start bits and lengths. This significantly reduces CPU time during the main decoding loop.
        self._spn_cache = (
            {}
        )  # Cache for (name, units, bitencoded, numerical, start, length, spn_obj)

    def get_pgn_acronym(self, pgn):
        if pgn == 59904:
            return "Request"
        if pgn == 60928:
            return "Address Claimed"
        if pgn == 65226:
            return "DM1"
        if pgn == 65227:
            return "DM2"
        if pgn == 61184:
            return "PropA"
        if pgn == 126720:
            return "PropA2"
        if 65280 <= pgn <= 65535:
            return "PropB"
        if 130816 <= pgn <= 131071:
            return "PropB2"
        pgn_object = self.pgn_objects.get(pgn)
        if pgn_object is None:
            return None
        acronym = pgn_object["Label"]
        if acronym == "":
            return None
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
            # Try dynamic name tracker first for dynamic range or if not in static DB
            address_name = self.name_tracker.get_name(address)
            if address_name is None:
                address_name = self.address_names.get(address)
            if address_name is None:
                address_name = "???"
        return formatted_address, address_name

    def resolve_pgn(self, query):
        """Find PGNs matching query string (case-insensitive substring match).

        Args:
            query (str): The search query.

        Returns:
            set: A set of matching PGN items.
        """
        query = query.lower()
        results = set()

        # 1. Check hardcoded acronyms
        hardcoded_pgns = [59904, 60928, 65226, 61184, 126720]
        for p in hardcoded_pgns:
            acr = self.get_pgn_acronym(p)
            if acr and query in acr.lower():
                results.add(p)

        # 2. Check database PGNs
        for pgn, obj in self.pgn_objects.items():
            label = obj.get("Label", "").lower()
            name = obj.get("Name", "").lower()
            if query in label or query in name:
                results.add(pgn)

        return sorted(list(results))

    def resolve_address(self, query):
        """Find addresses matching query string (case-insensitive substring match).

        Args:
            query (str): The search query.

        Returns:
            set: A set of matching address items.
        """
        query = query.lower()
        results = set()

        # Include hardcoded "All"
        if query in "all" or query in "global":
            results.add(255)

        for addr, name in self.address_names.items():
            if query in name.lower():
                results.add(addr)

        return sorted(list(results))

    def describe_message_id(self, message_id):
        description = OrderedDict()

        pgn, da, sa = parse_j1939_id(message_id)
        # Priority is bits 26-28 of the 29-bit ID
        priority = (message_id >> 26) & 0x7
        da_formatted_address, da_address_name = self.get_formatted_address_and_name(da)
        sa_formatted_address, sa_address_name = self.get_formatted_address_and_name(sa)

        if priority != 6:  # 6 is 0x18 shifted
            description["Priority"] = str(priority)
        description["PGN"] = self.get_pgn_description(pgn)
        description["SA"] = "%s%s" % (sa_address_name, sa_formatted_address)
        description["DA"] = "%s%s" % (da_address_name, da_formatted_address)

        description["_pgn"] = pgn
        description["_sa"] = sa
        description["_da"] = da

        return description

    def get_pgn_description(self, pgn):
        pgn_acronym = self.get_pgn_acronym(pgn)
        if pgn_acronym is None:
            return "???(%d/0x%05X)" % (pgn, pgn)
        else:
            return "%s(%s)" % (pgn_acronym, pgn)

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

        if not isinstance(spn_start, list):
            spn_start = [spn_start]

        spn_end = spn_start[0] + spn_length - 1

        return name, offset, scale, spn_end, spn_length, spn_start, units

    def lookup_spn_startbit(self, spn_object, spn, pgn):
        pgn_object = self.pgn_objects.get(pgn, {})
        spns_in_pgn = pgn_object.get("SPNs", [])
        startbits_in_pgn = pgn_object.get("SPNStartBits")

        if startbits_in_pgn is not None:
            if spn in spns_in_pgn:
                idx = spns_in_pgn.index(spn)
                if idx < len(startbits_in_pgn):
                    spn_start = startbits_in_pgn[idx]
                else:
                    spn_start = -1
            else:
                spn_start = -1
        else:
            # support earlier versions of J1939db.json which did not include PGN-to-SPN mappings at the PGN
            spn_start = spn_object.get("StartBit")
            if spn_start is not None:
                import warnings

                warnings.warn(
                    "Database uses old schema (StartBit in SPN). Please update to new schema (SPNStartBits in PGN).",
                    DeprecationWarning,
                    stacklevel=2,
                )
            else:
                spn_start = -1  # Unknown start bit

        # finally, support earlier versions of J1939db.json which did not include multi-startbit SPNs
        if not isinstance(spn_start, list):
            spn_start = [spn_start]

        return spn_start

    def get_spn_bytes(self, message_data_bitstring, spn, pgn, is_complete_message):
        # Use cached properties
        cache_key = (pgn, spn)
        if cache_key not in self._spn_cache:
            # Defensive: populate cache if missing
            spn_obj = self.spn_objects.get(spn)
            if not spn_obj:
                return EMPTY_BITS
            spn_name = spn_obj["Name"]
            spn_units = spn_obj["Units"]
            is_num = is_spn_numerical_values(spn_units)
            is_bit = is_spn_bitencoded(spn_units)
            spn_start = self.lookup_spn_startbit(spn_obj, spn, pgn)
            spn_length = spn_obj["SPNLength"]
            self._spn_cache[cache_key] = (
                spn_name,
                spn_units,
                is_num,
                is_bit,
                spn_start,
                spn_length,
                spn_obj,
            )

        spn_name, spn_units, is_num, is_bit, spn_start, spn_length, spn_obj = (
            self._spn_cache[cache_key]
        )

        if not isinstance(spn_start, list):
            spn_start = [spn_start]

        if type(spn_length) is str and spn_length.startswith("Variable"):
            delimiter = spn_obj.get("Delimiter")
            pgn_object = self.pgn_objects.get(pgn, {})
            spn_list = pgn_object["SPNs"]
            if delimiter is None:
                if len(spn_list) == 1:
                    effective_start = spn_start
                    if effective_start == [-1]:
                        effective_start = [0]
                    # Always return what's available for ASCII in real-time, even if incomplete
                    return get_spn_cut_bytes(
                        effective_start,
                        len(message_data_bitstring.bytes) * 8,
                        message_data_bitstring,
                        is_complete_message, # Still pass, but logic in get_spn_cut_bytes will be lenient for ASCII
                    )
                else:
                    print(
                        "Warning: skipping SPN %d in non-delimited and multi-spn and variable-length PGN %d"
                        " (this is most-likely a problem in the JSONdb or source DA)"
                        % (spn, pgn),
                        file=sys.stderr,
                    )
                    return EMPTY_BITS  # no way to handle multi-spn messages without a delimiter
            else:
                spn_ordinal = spn_list.index(spn)

                delimiter = delimiter.replace("0x", "")
                delimiter = bytes.fromhex(delimiter)
                spn_fields = message_data_bitstring.bytes.split(delimiter)

                if (
                    not is_complete_message and len(spn_fields) == 1
                ):  # delimiter is not found
                    return EMPTY_BITS

                if spn_start != [
                    -1
                ]:  # variable-len field with defined start; must be first variable-len field
                    spn_end = len(spn_fields[0]) * 8 - 1
                    cut_data = bitstring.Bits(bytes=spn_fields[0])[
                        spn_start[0] : spn_end + 1
                    ]
                    return cut_data
                else:  # variable-len field with unspecified start; requires field counting
                    startbits_list = pgn_object.get("SPNStartBits")
                    if startbits_list is None:
                        # Old schema: derive start bits from SPN objects
                        startbits_list = [
                            self.spn_objects.get(s, {}).get("StartBit", -1)
                            for s in spn_list
                        ]
                    num_fixedlen_spn_fields = sum(1 for s in startbits_list if s != -1)
                    variable_spn_ordinal = spn_ordinal - num_fixedlen_spn_fields
                    if num_fixedlen_spn_fields > 0:
                        variable_spn_fields = spn_fields[1:]
                    else:
                        variable_spn_fields = spn_fields
                    try:
                        cut_data = bitstring.Bits(
                            bytes=variable_spn_fields[variable_spn_ordinal]
                        )
                    except IndexError:
                        cut_data = EMPTY_BITS
                    return cut_data
        else:
            return get_spn_cut_bytes(
                spn_start, spn_length, message_data_bitstring, is_complete_message
            )

    # returns a float in units of the SPN, or NaN if the value of the SPN value is not available in the message_data, or
    #   None if the message is incomplete and SPN data is not available.
    #   if validate == True, raises a ValueError if the value is present in message_data but is beyond the operational
    #   range.
    #   if raw == True, returns the raw integer value without scaling or indicator checking.
    def get_spn_value(
        self,
        message_data_bitstring,
        spn,
        pgn,
        is_complete_message,
        validate=True,
        raw=False,
    ):
        # Use cached properties
        cache_key = (pgn, spn)
        if cache_key not in self._spn_cache:
            # Defensive: populate cache if missing
            spn_obj = self.spn_objects.get(spn)
            if not spn_obj:
                return NA_NAN
            spn_name = spn_obj["Name"]
            spn_units = spn_obj["Units"]
            is_num = is_spn_numerical_values(spn_units)
            is_bit = is_spn_bitencoded(spn_units)
            spn_start = self.lookup_spn_startbit(spn_obj, spn, pgn)
            spn_length = spn_obj["SPNLength"]
            self._spn_cache[cache_key] = (
                spn_name,
                spn_units,
                is_num,
                is_bit,
                spn_start,
                spn_length,
                spn_obj,
            )

        spn_name, spn_units, is_num, is_bit, spn_start, spn_length, spn_obj = (
            self._spn_cache[cache_key]
        )

        if isinstance(spn_start, int):
            spn_start = [spn_start]
        offset = spn_obj["Offset"]
        scale = spn_obj["Resolution"]
        if scale <= 0:
            scale = 1

        # performance optimization: fast path for byte-aligned SPNs using direct byte access and int.from_bytes.
        # This bypasses the overhead of the bitstring library for the majority of standard J1939 data fields.
        if len(spn_start) == 1 and spn_start[0] % 8 == 0 and spn_length % 8 == 0:
            start_byte = spn_start[0] // 8
            byte_len = spn_length // 8
            data_bytes = message_data_bitstring.bytes
            if start_byte + byte_len <= len(data_bytes):
                cut_bytes = data_bytes[start_byte : start_byte + byte_len]

                # Check for special J1939 indicators BEFORE scaling
                if byte_len == 1:
                    value = cut_bytes[0]
                elif byte_len == 2:
                    value = cut_bytes[0] | (cut_bytes[1] << 8)
                elif byte_len == 4:
                    value = (
                        cut_bytes[0]
                        | (cut_bytes[1] << 8)
                        | (cut_bytes[2] << 16)
                        | (cut_bytes[3] << 24)
                    )
                else:
                    value = int.from_bytes(cut_bytes, byteorder="little")

                if raw:
                    return value

                # Check for special J1939 indicators BEFORE scaling
                if is_spn_na(value, spn_length):
                    return NA_NAN
                if is_spn_error(value, spn_length):
                    return ERROR_VAL
                if is_spn_specific(value, spn_length):
                    return SPECIFIC_VAL
                if is_spn_reserved(value, spn_length):
                    return RESERVED_VAL

                if not is_bit:
                    value = value * scale + offset
                    if validate:
                        if (
                            value < spn_obj["OperationalLow"]
                            or value > spn_obj["OperationalHigh"]
                        ):
                            raise ValueError
                return value

        cut_data = self.get_spn_bytes(
            message_data_bitstring, spn, pgn, is_complete_message
        )
        if (not is_complete_message) and cut_data.length == 0:  # incomplete SPN
            return None

        if cut_data.length > 0:
            value = cut_data.uint
        else:
            value = 0

        if raw:
            return value

        if is_spn_na(value, spn_length):
            return NA_NAN
        if is_spn_error(value, spn_length):
            return ERROR_VAL
        if is_spn_reserved(value, spn_length):
            return RESERVED_VAL
        if not is_bit:
            value = value * scale + offset

            if validate:
                operational_min = spn_obj["OperationalLow"]
                operational_max = spn_obj["OperationalHigh"]
                if value < operational_min or value > operational_max:
                    raise ValueError

        return value

    def describe_diagnostic_message(self, data, description):
        """Helper to parse DM1/DM2 style diagnostic messages.

        Args:
            data (list): The message data bytes.
            description (dict): The dictionary to append parsed values to.
            
        Returns:
            None
        """
        if len(data) >= 2:
            lamp_status = data[0]

            def add_lamp_status(label, val):
                if val != "Not Available" or self.include_na:
                    description[label] = val

            add_lamp_status(
                "Malfunction Indicator Lamp Status",
                [
                    "Off",
                    "On",
                    "Error",
                    "Not Available",
                ][(lamp_status >> 6) & 0x03],
            )
            add_lamp_status(
                "Red Stop Lamp Status",
                [
                    "Off",
                    "On",
                    "Error",
                    "Not Available",
                ][(lamp_status >> 4) & 0x03],
            )
            add_lamp_status(
                "Amber Warning Lamp Status",
                [
                    "Off",
                    "On",
                    "Error",
                    "Not Available",
                ][(lamp_status >> 2) & 0x03],
            )
            add_lamp_status(
                "Protect Lamp Status",
                [
                    "Off",
                    "On",
                    "Error",
                    "Not Available",
                ][lamp_status & 0x03],
            )

            # DTCs start at byte 3 (index 2), 4 bytes each
            for i in range(2, len(data) - 3, 4):
                spn_val = data[i] | (data[i + 1] << 8) | ((data[i + 2] & 0xE0) << 11)
                fmi = data[i + 2] & 0x1F
                cm = (data[i + 3] >> 7) & 0x01
                oc = data[i + 3] & 0x7F

                if spn_val == 0 and fmi == 0 and oc == 0:
                    continue  # Skip "No DTCs" filler if present

                dtc_idx = (i - 2) // 4 + 1
                spn_name = self.get_spn_name(spn_val)

                desc_str = f"SPN {spn_val} ({spn_name}), FMI {fmi}, OC {oc}"
                if cm == 1:
                    desc_str += " (CM=1, J1587)"

                description[f"DTC {dtc_idx}"] = desc_str

    def describe_message_data(
        self,
        pgn,
        message_data_bitstring,
        is_complete_message=True,
        skip_spns=None,
        sa=None,
    ):
        if skip_spns is None:  # TODO have one default for skip_spns
            skip_spns = {}
        description = OrderedDict()
        return description

    def _describe_special_pgn_types(
        self, pgn, message_data_bitstring, description, sa, include_raw_data
    ):
        if is_transport_pgn(pgn):
            return True  # Indicate that it was a transport PGN and processing should stop

        if pgn == 59904:  # Request
            if len(message_data_bitstring.bytes) >= 3:
                requested_pgn = (
                    message_data_bitstring.bytes[0]
                    + (message_data_bitstring.bytes[1] << 8)
                    + (message_data_bitstring.bytes[2] << 16)
                )
                requested_pgn_desc = self.get_pgn_description(requested_pgn)
                description["Requested:"] = requested_pgn_desc
                description["_requested_pgn"] = requested_pgn
            if not include_raw_data:
                return True  # Indicate that special PGN was handled

        if pgn == 60928:  # Address Claimed
            name_decoded = decode_j1939_name(
                message_data_bitstring.bytes,
                manufacturer_db=self.manufacturer_db,
                industry_db=self.industry_db,
                function_db=self.function_db,
                vehicle_db=self.vehicle_db,
            )
            if name_decoded:
                description.update(name_decoded)
                if sa is not None:
                    self.name_tracker.update(sa, name_decoded)

            if not include_raw_data:
                return True  # Indicate that special PGN was handled

        if pgn in (65226, 65227):  # DM1, DM2
            self.describe_diagnostic_message(message_data_bitstring.bytes, description)

            if not include_raw_data:
                # If we have something, return it now
                if len(description) > 0:
                    return True  # Indicate that special PGN was handled
        return False # Indicate that no special PGN was handled or not fully handled without raw data

    def _get_spn_cached_properties(self, pgn, spn):
        cache_key = (pgn, spn)
        if cache_key in self._spn_cache:
            return self._spn_cache[cache_key]

        spn_obj = self.spn_objects.get(spn)
        if not spn_obj:
            return None

        spn_name = spn_obj["Name"]
        spn_units = spn_obj["Units"]
        is_num = is_spn_numerical_values(spn_units)
        is_bit = is_spn_bitencoded(spn_units)
        spn_start = self.lookup_spn_startbit(spn_obj, spn, pgn)
        spn_length = spn_obj["SPNLength"]
        
        cached_properties = (
            spn_name,
            spn_units,
            is_num,
            is_bit,
            spn_start,
            spn_length,
            spn_obj,
        )
        self._spn_cache[cache_key] = cached_properties
        return cached_properties

    def _mark_spn_covered(self, new_spn, new_spn_name, new_spn_description, skip_spns):
        skip_spns[new_spn] = (
            new_spn_name,
            new_spn_description,
        )  # TODO: move this closer to real-time handling

    def _add_spn_description(self, new_spn, new_spn_name, new_spn_description, description, skip_spns):
        description[new_spn_name] = new_spn_description
        self._mark_spn_covered(new_spn, new_spn_name, new_spn_description, skip_spns)

    def describe_message_data(
        self,
        pgn,
        message_data_bitstring,
        is_complete_message=True,
        skip_spns=None,
        sa=None,
    ):
        if skip_spns is None:  # TODO have one default for skip_spns
            skip_spns = {}
        description = OrderedDict()

        # Handle special PGN types (Request, Address Claimed, DM1/DM2)
        # If it's a transport PGN, or a special PGN handled completely, return early.
        special_pgn_handled = self._describe_special_pgn_types(
            pgn, message_data_bitstring, description, sa, self.include_raw_data
        )
        if special_pgn_handled:
            return description

        pgn_object = self.pgn_objects.get(pgn, {})
        spn_list = pgn_object.get("SPNs", [])
        if not spn_list:
            if (
                len(description) == 0 and not is_transport_pgn(pgn)
            ) or self.include_raw_data:
                description["Bytes"] = message_data_bitstring.hex.upper()
            return description

        for spn in spn_list:
            spn_properties = self._get_spn_cached_properties(pgn, spn)
            if spn_properties is None:
                continue
            spn_name, spn_units, is_num, is_bit, spn_start, spn_length, spn_obj = spn_properties

            if (
                skip_spns.get(spn, ()) != ()
            ):  # skip any SPNs that have already been processed.
                continue

            try:
                # ASCII consolidated logic
                should_decode_as_ascii = spn_units.lower() == "ascii"
                if should_decode_as_ascii:
                    spn_bytes = self.get_spn_bytes(
                        message_data_bitstring, spn, pgn, is_complete_message
                    )
                    if spn_bytes.length == 0:
                        continue

                    # NEW: Implement ASCII indicator rules from J1939/71 Table 7.5.
                    # Not available or not requested: 255 (0xFF)
                    # Error indicator: 0 (0x00)
                    # Valid Signal: 1 to 254 (0x01 to 0xFE)

                    raw_bytes = spn_bytes.bytes
                    if len(raw_bytes) > 0:
                        if all(b == 0xFF for b in raw_bytes):
                            if self.include_na:
                                self._add_spn_description(spn, spn_name, "N/A", description, skip_spns)
                            else:
                                self._mark_spn_covered(spn, spn_name, "N/A", skip_spns)
                            continue
                        elif all(b == 0x00 for b in raw_bytes):
                            self._add_spn_description(spn, spn_name, "Error", description, skip_spns)
                            continue

                    # J1939 ASCII is delimited by '*' and padded with nulls. Non-ASCII are replaced by '.'.
                    ascii_str = raw_bytes.decode(encoding="ascii", errors="replace").replace('\ufffd', '.').rstrip('*\x00')
                    self._add_spn_description(spn, spn_name, ascii_str, description, skip_spns)
                    continue

                if is_num:
                    raw_spn_value = self.get_spn_value(
                        message_data_bitstring,
                        spn,
                        pgn,
                        is_complete_message,
                        raw=True,
                    )
                    if (not is_complete_message) and (
                        raw_spn_value is None
                    ):  # incomplete message
                        continue

                    # Standard J1939 N/A check is decoupled from formatting and takes precedence.
                    # Even if J1939BitDecodings has a mapping, we flag it as N/A if it matches the mask.
                    # NEW: Skip indicator checks for ASCII units as per J1939-71.
                    # is_ascii = spn_units.lower() == "ascii" # This is now handled by should_decode_as_ascii
                    if not should_decode_as_ascii and is_spn_na(raw_spn_value, spn_length):
                        if self.include_na:
                            self._add_spn_description(spn, spn_name, "N/A", description, skip_spns)
                        else:
                            self._mark_spn_covered(spn, spn_name, "N/A", skip_spns)
                        continue

                    # Priority 1: Check if this explicit value is defined in J1939BitDecodings
                    # This allows Digital Annex functional states (like '2' for SPN 2875)
                    # to override standard indicators (except for N/A).
                    spn_value_description = None
                    if is_bit:
                        enum_descriptions = self.bit_encodings.get(spn)
                        if enum_descriptions:
                            spn_value_description = enum_descriptions.get(
                                str(raw_spn_value)
                            )

                    # Priority 2: If no explicit DA mapping, check remaining standard J1939 Indicators
                    if not should_decode_as_ascii and spn_value_description is None:
                        if is_spn_error(raw_spn_value, spn_length):
                            self._add_spn_description(spn, spn_name, "Error", description, skip_spns)
                            continue
                        elif is_spn_reserved(raw_spn_value, spn_length):
                            self._add_spn_description(spn, spn_name, "Reserved", description, skip_spns)
                            continue
                        elif is_spn_specific(raw_spn_value, spn_length):
                            self._add_spn_description(spn, spn_name, "Parameter specific", description, skip_spns)
                            continue

                    # Priority 3: Final decoding (scaling or enum lookup)
                    if is_bit:
                        # J1939/71 default for discrete values if not explicitly defined by DA
                        if spn_value_description is None:
                            if spn_length == 2:
                                spn_value_description = [
                                    "Disabled",
                                    "Enabled",
                                    "Error",
                                    "N/A",
                                ][raw_spn_value]
                            elif spn_length == 4:
                                if raw_spn_value == 14:
                                    spn_value_description = "Error"
                                elif raw_spn_value == 15:
                                    spn_value_description = "N/A"

                        if spn_value_description:
                            val_desc = "%d (%s)" % (
                                raw_spn_value,
                                spn_value_description.strip(),
                            )
                            self._add_spn_description(spn, spn_name, val_desc, description, skip_spns)
                        else:
                            self._add_spn_description(
                                spn, spn_name, "%d (Unknown)" % raw_spn_value, description, skip_spns
                            )
                    elif should_decode_as_ascii: # This else-if is technically redundant due to the initial if, but kept for clarity
                        # NEW: Handle ASCII SPNs correctly if they were categorized as is_num
                        # (e.g. if is_spn_numerical_values didn't catch it)
                        spn_bytes = self.get_spn_bytes(
                            message_data_bitstring, spn, pgn, is_complete_message
                        )
                        ascii_str = spn_bytes.bytes.decode(encoding="ascii", errors="replace").replace('\ufffd', '.').rstrip('*\x00')
                        self._add_spn_description(spn, spn_name, ascii_str, description, skip_spns)
                    else:
                        # Numerical scaling
                        spn_value = self.get_spn_value(
                            message_data_bitstring, spn, pgn, is_complete_message
                        )
                        self._add_spn_description(
                            spn, spn_name, "%s [%s]" % (spn_value, spn_units), description, skip_spns
                        )
                else:
                    spn_bytes = self.get_spn_bytes(
                        message_data_bitstring, spn, pgn, is_complete_message
                    )
                    if spn_bytes.length == 0 and not is_complete_message:
                        continue
                    else:
                        # NEW: check for NA/Error even if not numerical
                        # SKIP if ASCII as per J1939-71
                        # is_ascii = spn_units.lower() == "ascii" # This is now handled by should_decode_as_ascii
                        raw_val = None
                        if not should_decode_as_ascii and 0 < spn_bytes.length <= 64:
                            if spn_bytes.length % 8 == 0 and spn_bytes.length > 8:
                                raw_val = spn_bytes.uintle
                            else:
                                raw_val = spn_bytes.uint

                        if raw_val is not None:
                            if is_spn_na(raw_val, spn_bytes.length):
                                if self.include_na:
                                    self._add_spn_description(spn, spn_name, "N/A", description, skip_spns)
                                else:
                                    self._mark_spn_covered(spn, spn_name, "N/A", skip_spns)
                                continue
                            elif is_spn_error(raw_val, spn_bytes.length):
                                self._add_spn_description(spn, spn_name, "Error", description, skip_spns)
                                continue

                        if spn == 2540:
                            requested_pgn = spn_bytes.bytes
                            # Fix: Ensure we have enough bytes
                            if len(requested_pgn) >= 3:
                                requested_pgn_val = (
                                    requested_pgn[0]
                                    + (requested_pgn[1] << 8)
                                    + (requested_pgn[2] << 16)
                                )
                                requested_pgn_acronym = self.get_pgn_acronym(
                                    requested_pgn_val
                                )
                                self._add_spn_description(
                                    spn,
                                    spn_name,
                                    "%s (%d)"
                                    % (requested_pgn_acronym, requested_pgn_val),
                                    description, skip_spns
                                )
                            else:
                                self._add_spn_description(spn, spn_name, "%s" % spn_bytes, description, skip_spns)
                        elif spn_units.lower() in ("request dependent",):
                            self._add_spn_description(
                                spn, spn_name, "%s (%s)" % (spn_bytes, spn_units), description, skip_spns
                            )
                        elif spn_units.lower() in ("ascii",):
                            self._add_spn_description(
                                spn,
                                spn_name,
                                "%s" % spn_bytes.bytes.decode(encoding="ascii", errors="replace").replace('\ufffd', '.').rstrip('*\x00'),
                                description, skip_spns
                            )
                        else:
                            self._add_spn_description(spn, spn_name, "%s" % spn_bytes, description, skip_spns)

            except ValueError:
                self._add_spn_description(
                    spn,
                    spn_name,
                    "%s (%s)"
                    % (
                        self.get_spn_bytes(
                            message_data_bitstring, spn, pgn, is_complete_message
                        ),
                        "Out of range",
                    ),
                    description, skip_spns
                )

        if (
            len(description) == 0 and not is_transport_pgn(pgn)
        ) or self.include_raw_data:
            description["Bytes"] = message_data_bitstring.hex.upper()

        return description


def get_spn_cut_bytes(
    spn_start, spn_length, message_data_bitstring, is_complete_message
):
    if isinstance(spn_start, int):
        spn_start = [spn_start]

    # To convert J1939 bit position 'b' to bitstring index 'i':
    def j1939_to_bitstring_idx(b):
        # bitstring indexing is big-endian by default (index 0 is MSB of Byte 1).
        # J1939 bit 0 is LSB of Byte 1.
        # So bit 0 -> index 7, bit 7 -> index 0, bit 8 -> index 15, bit 15 -> index 8.
        byte_idx = b // 8
        bit_in_byte = b % 8
        return byte_idx * 8 + (7 - bit_in_byte)

    # If it's a single start bit
    if len(spn_start) == 1:
        start_bit = spn_start[0]

        # Fast path for byte-aligned SPNs (standard byte-order preserved)
        if start_bit % 8 == 0 and spn_length % 8 == 0:
            spn_end = start_bit + spn_length - 1
            if not is_complete_message and spn_end > message_data_bitstring.length:
                # For incomplete messages, return the available portion for display
                return message_data_bitstring[start_bit : message_data_bitstring.length]
            return message_data_bitstring[start_bit : spn_end + 1]

        # Non-aligned fields (always small, so we build a big-endian integer bitstring)
        bits = bitstring.BitArray()
        # For Intel bit order, logical MSB has highest J1939 bit position.
        # bitstring indexing is big-endian (index 0 is MSB).
        # We build 'bits' by appending from logical MSB to LSB.
        for b in range(start_bit + spn_length - 1, start_bit - 1, -1):
            if b >= message_data_bitstring.length:
                if not is_complete_message:
                    return EMPTY_BITS
                continue
            idx = j1939_to_bitstring_idx(b)
            # Append 1 bit at a time
            bits.append(message_data_bitstring[idx : idx + 1])
        return bits

    # Multi-startbit handling
    # For now, we assume a two-part split.
    # In J1939, this is typically used for 16-bit SPNs split into two 8-bit bytes.
    # We split the total length into two equal halves.
    lsplit = spn_length // 2
    rsplit = spn_length - lsplit

    def get_part_mapped(start, length):
        part = bitstring.BitArray()
        # MSB-to-LSB order for big-endian integer bitstring
        for b in range(start + length - 1, start - 1, -1):
            if b >= message_data_bitstring.length:
                continue
            idx = j1939_to_bitstring_idx(b)
            part.append(message_data_bitstring[idx : idx + 1])
        return part

    b = get_part_mapped(spn_start[1], rsplit)  # Logical high part first
    b.append(get_part_mapped(spn_start[0], lsplit))
    return b


def decode_j1939_name(
    payload, manufacturer_db=None, industry_db=None, function_db=None, vehicle_db=None
):
    if len(payload) != 8:
        return None

    # Convert bytes to a single 64-bit integer (Little Endian)
    name_value = int.from_bytes(payload, byteorder="little")

    ig_val = (name_value >> 60) & 0x07
    vs_val = (name_value >> 49) & 0x7F
    func_val = (name_value >> 40) & 0xFF
    mfr_val = (name_value >> 21) & 0x7FF
    ident_val = (name_value >> 0) & 0x1FFFFF

    def lookup(db, key, default):
        if db is None:
            return default
        return db.get(str(key), default)

    # Industry Group Lookup
    ig_name = lookup(industry_db, ig_val, "Unknown Industry Group")

    # Vehicle System Lookup
    vs_name = lookup(vehicle_db, vs_val, "Unknown Vehicle System")

    # Function Lookup
    if func_val <= 127:
        # Independent lookup
        func_name = lookup(function_db, func_val, "Unknown Function")
    else:
        # Dependent lookup: f"{industry_group}_{vehicle_system}_{function}"
        dep_key = f"{ig_val}_{vs_val}_{func_val}"
        func_name = lookup(function_db, dep_key, "Unknown Function")

    # Manufacturer Lookup
    mfr_name = lookup(manufacturer_db, mfr_val, "Unknown Manufacturer")

    decoded = {
        "Identity Number": ident_val,
        "Manufacturer Code": f"{mfr_val} ({mfr_name})",
        "ECU Instance": (name_value >> 32) & 0x07,
        "Function Instance": (name_value >> 35) & 0x1F,
        "Function ID": f"{func_val} ({func_name})",
        "Reserved": (name_value >> 48) & 0x01,
        "Vehicle System": f"{vs_val} ({vs_name})",
        "Vehicle System Instance": (name_value >> 56) & 0x0F,
        "Industry Group": f"{ig_val} ({ig_name})",
        "Arbitrary Address Capable": (name_value >> 63) & 0x01,
    }

    return decoded


class J1939TransportTracker:
    def __init__(self, real_time):
        self.is_real_time = real_time
        self.sessions = {}  # (da, sa) -> session_info

    def cleanup(self, transport_found_processor):
        for (da, sa), session in self.sessions.items():
            if not self.is_real_time:
                full_data = session["data"][: session["length"]]
                if None not in full_data:
                    data_bytes = bytes(full_data)
                    transport_found_processor(
                        data_bytes, sa, session["pgn"], is_last_packet=True
                    )
        self.sessions.clear()

    def process(self, transport_found_processor, message_bytes, message_id):
        _, da, sa = parse_j1939_id(message_id)

        if is_connection_management_message(message_id):
            control = message_bytes[0]
            if control == 32 or control == 16:  # BAM or RTS
                pgn = (
                    (message_bytes[7] << 16)
                    + (message_bytes[6] << 8)
                    + message_bytes[5]
                )
                length = (message_bytes[2] << 8) + message_bytes[1]
                count = message_bytes[3]
                self.sessions[(da, sa)] = {
                    "pgn": pgn,
                    "length": length,
                    "count": count,
                    "data": [None] * (count * 7),
                    "type": "BAM" if control == 32 else "RTS",
                    "packets_received": 0,
                }
            elif control == 19:  # EOM (End of Message ACK)
                if (da, sa) in self.sessions:
                    session = self.sessions[(da, sa)]
                    if not self.is_real_time:
                        full_data = session["data"][: session["length"]]
                        if None not in full_data:
                            data_bytes = bytes(full_data)
                            transport_found_processor(
                                data_bytes, sa, session["pgn"], is_last_packet=True
                            )
                    del self.sessions[(da, sa)]
            elif control == 255:  # Connection Abort
                if (da, sa) in self.sessions:
                    del self.sessions[(da, sa)]

        elif is_data_transfer_message(message_id):
            if (da, sa) in self.sessions:
                session = self.sessions[(da, sa)]
                packet_number = message_bytes[0]

                if packet_number > session["count"] or packet_number < 1:
                    return

                for i in range(7):
                    idx = (packet_number - 1) * 7 + i
                    if idx < len(session["data"]) and i + 1 < len(message_bytes):
                        session["data"][idx] = message_bytes[i + 1]

                session["packets_received"] += 1
                is_last_packet = packet_number == session["count"]

                if self.is_real_time:
                    # In real-time mode, we emit data as it arrives
                    payload = message_bytes[1:]
                    transport_found_processor(
                        bytes(payload),
                        sa,
                        session["pgn"],
                        is_last_packet=(is_last_packet and session["type"] == "BAM"),
                    )

                if is_last_packet and session["type"] == "BAM":
                    if not self.is_real_time:
                        full_data = session["data"][: session["length"]]
                        if None not in full_data:
                            data_bytes = bytes(full_data)
                            transport_found_processor(
                                data_bytes, sa, session["pgn"], is_last_packet=True
                            )
                    del self.sessions[(da, sa)]


class J1939Describer:
    da_describer: DADescriber = None

    def __init__(
        self,
        describe_link_layer,
        describe_pgns,
        describe_spns,
        describe_transport_layer,
        include_transport_rawdata,
        include_na,
        include_raw_data,
        enable_isotp=True,
        real_time=False,
    ):
        self.describe_link_layer = describe_link_layer
        self.describe_pgns = describe_pgns
        self.describe_spns = describe_spns
        self.describe_transport_layer = describe_transport_layer
        self.include_transport_rawdata = include_transport_rawdata
        self.include_na = include_na
        self.include_raw_data = include_raw_data
        self.real_time = real_time

        self.transport_messages = list()

        self.trackers = []
        self.trackers.append(J1939TransportTracker(real_time=real_time))
        if enable_isotp:
            self.trackers.append(IsoTpTracker(real_time=real_time))

        self.summary_data = {}

    def get_summary(self):
        return self.summary_data

    def cleanup(self):
        final_descriptions = []

        def on_transport_found(
            data_bytes, found_sa, found_pgn, spn_coverage=None, is_last_packet=False
        ):
            if spn_coverage is None:
                spn_coverage = {}

            # Update summary for transport
            t_key = (found_sa, self.current_da)
            if t_key not in self.summary_data:
                self.summary_data[t_key] = {"sent": set(), "req": set()}
            self.summary_data[t_key]["sent"].add(found_pgn)

            # Create a full description for the reassembled message
            description = OrderedDict()
            if self.describe_pgns:
                transport_pgn_description = self.da_describer.get_pgn_description(
                    found_pgn
                )
                description[PGN_LABEL] = transport_pgn_description
                description["SA"] = "%s(%s)" % (self.da_describer.get_formatted_address_and_name(found_sa)[1], self.da_describer.get_formatted_address_and_name(found_sa)[0])
                # DA is already captured in the outer description or should be derived from the session context

            description["_pgn"] = found_pgn

            transport_bits = bitstring.Bits(bytes=data_bytes)
            if self.describe_spns and is_last_packet:
                message_description = self.da_describer.describe_message_data(
                    found_pgn,
                    transport_bits,
                    is_complete_message=True,
                    skip_spns=spn_coverage,
                    sa=found_sa,
                )
                description.update(message_description)

            if is_last_packet and self.include_transport_rawdata:
                description.update({"Bytes": transport_bits.hex.upper()})

            final_descriptions.append(self.reorder_description(description))

        # Keep track of the DA that was active for the *last* processed message in __call__
        # This is a bit of a hack, but necessary to properly update the summary_data on cleanup
        self.current_da = self.current_da if hasattr(self, 'current_da') else 0

        for tracker in self.trackers:
            tracker.cleanup(on_transport_found)

        return final_descriptions

    def set_da_describer(self, da_describer):
        self.da_describer = da_describer

    def __call__(self, message_data, message_id_uint: int):
        if isinstance(message_data, (bytes, bytearray)):
            message_data = bitstring.Bits(bytes=message_data)
        elif not isinstance(message_data, bitstring.Bits):
            # Fallback for other bitstring types if necessary
            message_data = bitstring.Bits(message_data)

        self.transport_messages.clear()

        pgn, da, sa = parse_j1939_id(message_id_uint)
        self.current_da = da  # Store current DA for cleanup
        summary_key = (sa, da)
        if summary_key not in self.summary_data:
            self.summary_data[summary_key] = {"sent": set(), "req": set()}

        if pgn == 59904:  # Request
            # Request data is 3 bytes (LSB PGN)
            if len(message_data) >= 24:
                req_pgn = (
                    message_data.bytes[0]
                    | (message_data.bytes[1] << 8)
                    | (message_data.bytes[2] << 16)
                )
                self.summary_data[summary_key]["req"].add(req_pgn)

        def on_transport_found(
            data_bytes, found_sa, found_pgn, spn_coverage=None, is_last_packet=False
        ):
            if spn_coverage is None:
                spn_coverage = {}

            # Update summary for transport
            t_key = (found_sa, da)
            if t_key not in self.summary_data:
                self.summary_data[t_key] = {"sent": set(), "req": set()}
            self.summary_data[t_key]["sent"].add(found_pgn)

            transport_found = dict()
            transport_found[PGN_LABEL] = found_pgn
            transport_found["SA"] = found_sa
            transport_found["data"] = data_bytes
            transport_found["spn_coverage"] = spn_coverage
            transport_found["is_last_packet"] = is_last_packet
            self.transport_messages.append(transport_found)

        is_transport_lower_layer_message = (
            is_transport_message(message_id_uint)
            or (message_id_uint & PF_MASK) == DIAG3_MASK
        )

        if self.describe_transport_layer:
            for tracker in self.trackers:
                tracker.process(on_transport_found, message_data.bytes, message_id_uint)

        # Also add the immediate PGN if it's not a transport management PGN
        if not is_transport_pgn(pgn):
            self.summary_data[summary_key]["sent"].add(pgn)

        description = OrderedDict()

        is_describe_this_frame = (
            not is_transport_lower_layer_message
        )  # always print 'complete' J1939 frames
        is_describe_this_frame |= (
            is_transport_lower_layer_message and self.describe_link_layer
        )  # or others when configured to describe 'link layer' frames

        if is_describe_this_frame:
            if self.describe_pgns:
                description.update(
                    self.da_describer.describe_message_id(message_id_uint)
                )

            if self.describe_spns:
                pgn, _, _ = parse_j1939_id(message_id_uint)
                message_description = self.da_describer.describe_message_data(
                    pgn,
                    message_data,
                    is_complete_message=True,
                    sa=sa,
                )
                description.update(message_description)

        if self.describe_transport_layer and len(self.transport_messages) > 0:
            transport_message = self.transport_messages[0]
            transport_pgn = transport_message[PGN_LABEL]
            if self.describe_pgns:
                description.update(
                    self.da_describer.describe_message_id(message_id_uint)
                )
                transport_pgn_description = self.da_describer.get_pgn_description(
                    transport_pgn
                )
                if (
                    self.describe_link_layer
                ):  # when configured to describe 'link layer' don't collide with PGN
                    description.update({"Transport PGN": transport_pgn_description})
                else:  # otherwise (and default) describe the transport PGN as _the_ PGN
                    description.update({PGN_LABEL: transport_pgn_description})
                    description.move_to_end(PGN_LABEL, last=False)

            description["_pgn"] = transport_pgn

            is_complete_message = transport_message["is_last_packet"]
            transport_bits = bitstring.Bits(bytes=transport_message["data"])
            if self.describe_spns and (is_complete_message or not self.real_time):
                pgn = transport_pgn
                message_description = self.da_describer.describe_message_data(
                    pgn,
                    transport_bits,
                    is_complete_message=is_complete_message,
                    skip_spns=transport_message["spn_coverage"],
                    sa=transport_message["SA"],
                )
                description.update(message_description)

            if is_complete_message and self.include_transport_rawdata:
                description.update({"Bytes": transport_bits.hex.upper()})

        return self.reorder_description(description)

    def reorder_description(self, description):
        # We want PGN, SA, DA, Priority to be the first four keys if they exist
        for key in reversed(["PGN", "SA", "DA", "Priority"]):
            if key in description:
                description.move_to_end(key, last=False)
        return description


def get_default_da_json():
    filename = "J1939db.json"

    if os.path.exists(filename):
        return filename

    if sys.platform == "win32":
        config_dir = os.environ.get("APPDATA")
    else:
        config_dir = os.path.expanduser("~/.config")

    if config_dir:
        config_path = os.path.join(config_dir, "pretty_j1939", filename)
        if os.path.exists(config_path):
            return config_path

    try:
        if hasattr(importlib.resources, "files"):
            # For Python 3.9+
            ref = importlib.resources.files("pretty_j1939") / filename
            if ref.is_file():
                return str(ref)
        else:
            # Fallback for older versions
            if importlib.resources.is_resource("pretty_j1939", filename):
                with importlib.resources.path("pretty_j1939", filename) as p:
                    return str(p)
    except Exception as e:
        logger.debug(f"Failed to resolve built-in database path: {e}")

    return filename  # Final fallback to just the name


DEFAULT_DA_JSON = "J1939db.json"
DEFAULT_CANDATA = False
DEFAULT_PGN = True
DEFAULT_SPN = True
DEFAULT_TRANSPORT = True
DEFAULT_LINK = False
DEFAULT_INCLUDE_NA = False
DEFAULT_REAL_TIME = False
DEFAULT_INCLUDE_RAW_DATA = False


def get_describer(da_json=None, **kwargs):
    if da_json is None or da_json == DEFAULT_DA_JSON:
        da_json = get_default_da_json()

    # Apply default configuration values to kwargs
    kwargs.setdefault("describe_pgns", DEFAULT_PGN)
    kwargs.setdefault("describe_spns", DEFAULT_SPN)
    kwargs.setdefault("describe_link_layer", DEFAULT_LINK)
    kwargs.setdefault("describe_transport_layer", DEFAULT_TRANSPORT)
    kwargs.setdefault("real_time", DEFAULT_REAL_TIME)
    kwargs.setdefault("include_transport_rawdata", DEFAULT_CANDATA)
    kwargs.setdefault("include_na", DEFAULT_INCLUDE_NA)
    kwargs.setdefault("include_raw_data", DEFAULT_INCLUDE_RAW_DATA)

    # enable_isotp is only used by J1939Describer
    enable_isotp = kwargs.pop("enable_isotp", True)

    describer = J1939Describer(enable_isotp=enable_isotp, **kwargs)

    da_describer = DADescriber(da_json=da_json, **kwargs)
    describer.set_da_describer(da_describer)

    return describer
