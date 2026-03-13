import re
import math
import sys
import functools
import operator
import unidecode
from defusedxml.common import EntitiesForbidden
import xlrd
import openpyxl
import asteval

ENUM_SINGLE_LINE_RE = r"[ ]*([0-9bxXA-F]+)[ ]*[-=:]?[ ]*(.*)"
ENUM_RANGE_LINE_RE = (
    r"[ ]*([0-9bxXA-F]+)[ ]*(\-|to|thru)[ ]*([0-9bxXA-F]+)[ ]+[-=:]?[ ]*(.*)"
)

def secure_open_workbook(filename, **kwargs):
    """Secure open workbook operation.
    
    Args:
        filename: The filename parameter.
        **kwargs: The **kwargs parameter.
    
    Returns:
        The result of the operation.
    """
    try:
        if filename.endswith(".xlsx"):
            return openpyxl.load_workbook(filename, data_only=True)
        else:
            return xlrd.open_workbook(filename=filename, **kwargs)
    except EntitiesForbidden:
        raise ValueError("Please use an excel file without XEE")

# returns a string of number of bits, or 'Variable', or ''
def get_pgn_data_len(contents):
    """Gets pgn data len.
    
    Args:
        contents: The contents parameter.
    
    Returns:
        The result of the operation.
    """
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

# returns an int number of bits, or 'Variable'
def get_spn_len(contents):
    """Gets spn len.
    
    Args:
        contents: The contents parameter.
    
    Returns:
        The result of the operation.
    """
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

# returns a single-byte delimiter or None
def get_spn_delimiter(contents):
    """Gets spn delimiter.
    
    Args:
        contents: The contents parameter.
    
    Returns:
        The result of the operation.
    """
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

def just_numeric_expr(contents):
    """Just numeric expr operation.
    
    Args:
        contents: The contents parameter.
    
    Returns:
        The result of the operation.
    """
    contents = str(contents)
    contents = re.sub(r"[^0-9\.\-/]", "", contents)  # remove all but number and '.'
    contents = re.sub(
        r"[/-]+[ ]*$", "", contents
    )  # remove trailing '/' or '-' that are sometimes left
    return contents

def get_spn_units(contents, raw_spn_resolution):
    """Gets spn units.
    
    Args:
        contents: The contents parameter.
        raw_spn_resolution: The raw spn resolution parameter.
    
    Returns:
        The result of the operation.
    """
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

# returns a float in X per bit or int(0)
def get_spn_resolution(contents):
    """Gets spn resolution.
    
    Args:
        contents: The contents parameter.
    
    Returns:
        The result of the operation.
    """
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
        expr = just_numeric_expr(norm_contents)
        return asteval_eval(expr)
    elif "bit" in norm_contents and "/" in norm_contents:
        left, right = str(contents).split("/")
        left = just_numeric_expr(left)
        right = just_numeric_expr(right)
        return asteval_eval("(%s)/(%s)" % (left, right))
    elif (
        "microsiemens/mm" in norm_contents
        or "usiemens/mm" in norm_contents
        or "kw/s" in norm_contents
    ):  # special handling for this weirdness
        return float(str(contents).split(" ")[0])
    raise ValueError('unknown spn resolution "%s"' % contents)

def asteval_eval(expr):
    """Asteval eval operation.
    
    Args:
        expr: The expr parameter.
    
    Returns:
        The result of the operation.
    """
    interpreter = asteval.Interpreter()
    ret = interpreter(expr)
    if len(interpreter.error) > 0:
        raise interpreter.error[0]
    return ret

# returns a float in 'units' of the SPN or int(0)
def get_spn_offset(contents):
    """Gets spn offset.
    
    Args:
        contents: The contents parameter.
    
    Returns:
        The result of the operation.
    """
    norm_contents = unidecode.unidecode(str(contents)).lower()
    if (
        "manufacturer defined" in norm_contents
        or "not defined" in norm_contents
        or norm_contents.strip() == ""
    ):
        return int(0)
    else:
        first = just_numeric_expr(contents)
        return asteval_eval(first)

# returns a pair of floats (low, high) in 'units' of the SPN or (-1, -1) for undefined operational ranges
def get_operational_hilo(contents, units, spn_length):
    """Gets operational hilo.
    
    Args:
        contents: The contents parameter.
        units: The units parameter.
        spn_length: The spn length parameter.
    
    Returns:
        The result of the operation.
    """
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
        left = just_numeric_expr(left)
        right = just_numeric_expr(right)

        range_units = norm_contents.split(" ")
        range_units = range_units[len(range_units) - 1]
        lo = float(asteval_eval(left))
        hi = float(asteval_eval(right))
        if range_units == "km" and units == "m":
            return lo * 1000, hi * 1000
        else:
            return lo, hi
    raise ValueError('unknown operational range from "%s","%s"' % (contents, units))

# return a list of int of the start bits ([some_bit_pos] or [some_bit_pos,some_other_bit_pos]) of the SPN; or [
# -1] (if unknown or variable).
def get_spn_start_bit(contents):
    """Gets spn start bit.
    
    Args:
        contents: The contents parameter.
    
    Returns:
        The result of the operation.
    """
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

    firsts = [just_numeric_expr(first) for first in firsts]
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

def is_enum_line(line):
    """Checks if enum line.
    
    Args:
        line: The line parameter.
    
    Returns:
        The result of the operation.
    """
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

def get_enum_lines(description_lines):
    """Gets enum lines.
    
    Args:
        description_lines: The description lines parameter.
    
    Returns:
        The result of the operation.
    """
    enum_lines = list()

    def add_enum_line(test_line):
        """Add enum line operation.
        
        Args:
            test_line: The test line parameter.
        
        Returns:
            The result of the operation.
        """
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
        is_enum = is_enum_line(line)
        if is_enum:
            if any_found:
                add_enum_line(line)
            else:
                if match_single_enum_line(
                    line
                ):  # special handling: first enum must use single assignment
                    any_found = add_enum_line(line)
    return enum_lines

def is_enum_lines_binary(enum_lines_only):
    """Checks if enum lines binary.
    
    Args:
        enum_lines_only: The enum lines only parameter.
    
    Returns:
        The result of the operation.
    """
    all_ones_and_zeroes = True
    for line in enum_lines_only:
        match = match_single_enum_line(line)
        if not match:
            all_ones_and_zeroes = False
            break
        first = match.groups()[0]
        if re.sub(r"[^10b]", "", first) != first:
            all_ones_and_zeroes = False
            break

    return all_ones_and_zeroes

# returns a pair of inclusive, inclusive range boundaries or None if this line is not a range
def get_enum_line_range(line):
    """Gets enum line range.
    
    Args:
        line: The line parameter.
    
    Returns:
        The result of the operation.
    """
    match = re.match(ENUM_RANGE_LINE_RE, line)
    if match:
        groups = match.groups()
        return groups[0], groups[2]
    else:
        return None

def match_single_enum_line(line):
    """Match single enum line operation.
    
    Args:
        line: The line parameter.
    
    Returns:
        The result of the operation.
    """
    line = re.sub(r"[ ]+", " ", line)
    line = re.sub(r"[ ]?\-\-[ ]?", " = ", line)
    return re.match(ENUM_SINGLE_LINE_RE, line)

# returns the description part (just that part) of an enum line
def get_enum_line_description(line):
    # Additional cleanup for artifacts that might be in multiline descriptions
    """Gets enum line description.
    
    Args:
        line: The line parameter.
    
    Returns:
        The result of the operation.
    """
    line = re.sub(r"_x[0-9a-fA-F]{4}_", " ", line)
    line = re.sub(r"[ ]+", " ", line)
    line = re.sub(r"[ ]?\-\-[ ]?", " = ", line)
    match = re.match(ENUM_RANGE_LINE_RE, line)
    if match:
        line = match.groups()[-1]
    else:
        match = match_single_enum_line(line)
        if match:
            line = match.groups()[-1]
    line = line.strip()
    line = line.lower()
    line = line.replace("sae", "SAE").replace("iso", "ISO")
    return line

def create_bit_object_from_description(spn_description, bit_object):
    """Create bit object from description operation.
    
    Args:
        spn_description: The spn description parameter.
        bit_object: The bit object parameter.
    
    Returns:
        The result of the operation.
    """
    description_lines = spn_description.splitlines()
    enum_lines = get_enum_lines(description_lines)
    is_binary = is_enum_lines_binary(enum_lines)

    for line in enum_lines:
        enum_description = get_enum_line_description(line)

        range_boundaries = get_enum_line_range(line)
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

def is_spn_likely_bitmapped(spn_description):
    """Checks if spn likely bitmapped.
    
    Args:
        spn_description: The spn description parameter.
    
    Returns:
        The result of the operation.
    """
    return len(get_enum_lines(spn_description.splitlines())) > 2


def fix_omittedlen_spns(j1939_pgn_db, j1939_spn_db):
    """Fix omittedlen spns operation.
    
    Args:
        j1939_pgn_db: The j1939 pgn db parameter.
        j1939_spn_db: The j1939 spn db parameter.
    
    Returns:
        The result of the operation.
    """
    modified_spns = dict()
    for pgn, pgn_object in j1939_pgn_db.items():
        spn_list = pgn_object.get("SPNs")
        spn_startbit_list = pgn_object.get("SPNStartBits")
        spn_order_list = pgn_object.get("Temp_SPN_Order")

        spn_in_pgn_list = list(zip(spn_list, spn_startbit_list, spn_order_list))
        if all_spns_positioned(spn_startbit_list):
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
                    if is_length_variable(current_spn_length):
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

def is_length_variable(spn_length):
    """Checks if length variable.
    
    Args:
        spn_length: The spn length parameter.
    
    Returns:
        The result of the operation.
    """
    return type(spn_length) is str and spn_length.startswith("Variable")

def remove_startbitsunknown_spns(j1939_pgn_db, j1939_spn_db):
    """Remove startbitsunknown spns operation.
    
    Args:
        j1939_pgn_db: The j1939 pgn db parameter.
        j1939_spn_db: The j1939 spn db parameter.
    
    Returns:
        The result of the operation.
    """
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
                    and not is_length_variable(prev_spn_len)
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

def remove_underspecd_spns(j1939_pgn_db, j1939_spn_db):
    """Remove underspecd spns operation.
    
    Args:
        j1939_pgn_db: The j1939 pgn db parameter.
        j1939_spn_db: The j1939 spn db parameter.
    
    Returns:
        The result of the operation.
    """
    for pgn, pgn_object in j1939_pgn_db.items():
        spn_list = pgn_object.get("SPNs")
        if len(spn_list) > 1:
            spn_list = pgn_object.get("SPNs")
            spn_startbit_list = pgn_object.get("SPNStartBits")
            spn_order_list = pgn_object.get("Temp_SPN_Order")

            spn_in_pgn_list = zip(spn_list, spn_startbit_list, spn_order_list)

            def should_remove(tup):
                """Should remove operation.
                
                Args:
                    tup: The tup parameter.
                
                Returns:
                    The result of the operation.
                """
                spn = tup[0]
                spn_obj = j1939_spn_db.get(str(spn))
                current_spn_length = spn_obj.get("SPNLength")
                current_spn_delimiter = spn_obj.get("Delimiter")
                if (
                    is_length_variable(current_spn_length)
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

def sort_spns_by_order(j1939_pgn_db):
    """Sort spns by order operation.
    
    Args:
        j1939_pgn_db: The j1939 pgn db parameter.
    
    Returns:
        The result of the operation.
    """
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

def all_spns_positioned(spn_startbit_list):
    """All spns positioned operation.
    
    Args:
        spn_startbit_list: The spn startbit list parameter.
    
    Returns:
        The result of the operation.
    """
    if len(spn_startbit_list) == 0:
        return True
    else:
        is_positioned = map(
            lambda spn_startbit: int(spn_startbit[0]) != -1, spn_startbit_list
        )
        return functools.reduce(lambda a, b: a and b, is_positioned)

