#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import unittest
from collections import OrderedDict
from pretty_j1939.tools.create_j1939db_json import J1939daConverter, SheetWrapper
from pretty_j1939.core import da_parsers


class TestJ1939daConverter(unittest.TestCase):
    def setUp(self):
        # SheetWrapper is an abstract base class, we can instantiate a mock for testing _clean_value
        class MockSheet:
            pass

        self.wrapper = SheetWrapper(MockSheet())

    def test_clean_value_xml_artifacts(self):
        # Test the fix for _x000d_ and similar artifacts
        self.assertEqual(self.wrapper._clean_value("activate_x000d_"), "activate")
        self.assertEqual(self.wrapper._clean_value("de-activate_x000D_"), "de-activate")
        self.assertEqual(self.wrapper._clean_value("line1_x000d_line2"), "line1 line2")
        self.assertEqual(self.wrapper._clean_value("tab_x0009_char"), "tab char")
        self.assertEqual(
            self.wrapper._clean_value("multiple  spaces"), "multiple spaces"
        )
        self.assertEqual(
            self.wrapper._clean_value("newlines\r\nstripped"), "newlines\r\nstripped"
        )

    def test_get_pgn_data_len(self):
        self.assertEqual(
            da_parsers.get_pgn_data_len(8), "8"
        )  # If integer, returns string of int
        self.assertEqual(
            da_parsers.get_pgn_data_len("8 bytes"), "64"
        )  # If "bytes" in string, converts to bits
        self.assertEqual(da_parsers.get_pgn_data_len("Variable"), "Variable")
        self.assertEqual(da_parsers.get_pgn_data_len(None), "")
        self.assertEqual(da_parsers.get_pgn_data_len(""), "")

    def test_get_spn_len(self):
        self.assertEqual(da_parsers.get_spn_len(16), 16)
        self.assertEqual(da_parsers.get_spn_len("2 bytes"), 16)
        self.assertEqual(da_parsers.get_spn_len("8 bits"), 8)
        self.assertEqual(da_parsers.get_spn_len("Variable"), "Variable")
        self.assertEqual(da_parsers.get_spn_len("max 255 bytes"), "Variable")
        self.assertEqual(da_parsers.get_spn_len(None), "Variable")

    def test_get_spn_delimiter(self):
        self.assertEqual(da_parsers.get_spn_delimiter("delimiter *"), b"*")
        self.assertEqual(da_parsers.get_spn_delimiter("NULL delimiter"), b"\x00")
        self.assertIsNone(da_parsers.get_spn_delimiter("fixed length"))

    def test_just_numeric_expr(self):
        self.assertEqual(da_parsers.just_numeric_expr("123.45 km"), "123.45")
        self.assertEqual(da_parsers.just_numeric_expr("-10 to 50"), "-1050")
        self.assertEqual(da_parsers.just_numeric_expr("4/5"), "4/5")

    def test_get_spn_resolution(self):
        self.assertEqual(da_parsers.get_spn_resolution("0.125 rpm/bit"), 0.125)
        self.assertEqual(da_parsers.get_spn_resolution("1 states"), 1.0)
        self.assertEqual(da_parsers.get_spn_resolution("bit-mapped"), 0)
        self.assertEqual(da_parsers.get_spn_resolution("1/128 km/bit"), 1 / 128)
        self.assertEqual(da_parsers.get_spn_resolution("5 microsiemens/mm"), 5.0)

    def test_get_spn_offset(self):
        self.assertEqual(da_parsers.get_spn_offset("-125"), -125.0)
        self.assertEqual(da_parsers.get_spn_offset("0"), 0.0)
        self.assertEqual(da_parsers.get_spn_offset("not defined"), 0)

    def test_get_operational_hilo(self):
        self.assertEqual(
            da_parsers.get_operational_hilo("0 to 250.5", "km", 16), (0.0, 250.5)
        )
        self.assertEqual(
            da_parsers.get_operational_hilo("0 to 2000 km", "m", 16),
            (0.0, 2000000.0),
        )
        self.assertEqual(
            da_parsers.get_operational_hilo("not defined", "units", 8), (-1, -1)
        )
        # Default range for bit-fields
        self.assertEqual(da_parsers.get_operational_hilo("", "", 2), (0, 3))

    def test_get_spn_start_bit(self):
        # Byte.Bit format
        self.assertEqual(da_parsers.get_spn_start_bit("1.1"), [0])
        self.assertEqual(da_parsers.get_spn_start_bit("1.5"), [4])
        self.assertEqual(da_parsers.get_spn_start_bit("2.1"), [8])
        # Byte range format (non-contiguous bytes: 4 and 6)
        self.assertEqual(da_parsers.get_spn_start_bit("4-6"), [24, 40])
        # Discrete bits
        self.assertEqual(da_parsers.get_spn_start_bit("1.1, 1.3"), [0, 2])
        # Variable/Complex (returns -1)
        self.assertEqual(da_parsers.get_spn_start_bit("a+0"), [-1])

    def test_get_enum_line_description(self):
        self.assertEqual(
            da_parsers.get_enum_line_description("00 - deactivate_x000d_"),
            "deactivate",
        )
        self.assertEqual(
            da_parsers.get_enum_line_description("01 = activate"), "activate"
        )
        self.assertEqual(
            da_parsers.get_enum_line_description("10: reserved"), "reserved"
        )
        self.assertEqual(
            da_parsers.get_enum_line_description("0-100 -- normal range"),
            "normal range",
        )


class TestDADescriberDefaults(unittest.TestCase):
    def test_j1939_indicator_ranges(self):
        from pretty_j1939.core.describe import get_describer
        import bitstring

        # DB with 1, 2, 3, 4 byte SPNs on different PGNs to avoid any caching
        describer = get_describer(
            include_na=True,
            da_json={
                "J1939PGNdb": {
                    "100": {"Label": "P1", "SPNs": [10], "SPNStartBits": [0]},
                    "200": {"Label": "P2", "SPNs": [20], "SPNStartBits": [0]},
                    "300": {"Label": "P3", "SPNs": [30], "SPNStartBits": [0]},
                    "400": {"Label": "P4", "SPNs": [40], "SPNStartBits": [0]},
                },
                "J1939SPNdb": {
                    "10": {
                        "Name": "S1",
                        "Units": "units",
                        "SPNLength": 8,
                        "Resolution": 1,
                        "Offset": 0,
                        "OperationalLow": 0,
                        "OperationalHigh": 250,
                    },
                    "20": {
                        "Name": "S2",
                        "Units": "units",
                        "SPNLength": 16,
                        "Resolution": 1,
                        "Offset": 0,
                        "OperationalLow": 0,
                        "OperationalHigh": 64255,
                    },
                    "30": {
                        "Name": "S3",
                        "Units": "units",
                        "SPNLength": 24,
                        "Resolution": 1,
                        "Offset": 0,
                        "OperationalLow": 0,
                        "OperationalHigh": 16449535,
                    },
                    "40": {
                        "Name": "S4",
                        "Units": "units",
                        "SPNLength": 32,
                        "Resolution": 1,
                        "Offset": 0,
                        "OperationalLow": 0,
                        "OperationalHigh": 4211081215,
                    },
                },
                "J1939SATabledb": {},
                "J1939BitDecodings": {},
            },
        )
        da = describer.da_describer

        # Test 2-byte ranges (LE in payload)
        # Parameter Specific: 0xFB00 -> 00 FB
        res = da.describe_message_data(200, bitstring.Bits(hex="00FB"))
        self.assertIn("Parameter specific", res["S2"])

        # Reserved: 0xFC00 -> 00 FC
        res = da.describe_message_data(200, bitstring.Bits(hex="00FC"))
        self.assertIn("Reserved", res["S2"])

        # Error: 0xFE00 -> 00 FE
        res = da.describe_message_data(200, bitstring.Bits(hex="00FE"))
        self.assertIn("Error", res["S2"])

        # N/A: 0xFF00 -> 00 FF
        res = da.describe_message_data(200, bitstring.Bits(hex="00FF"))
        self.assertIn("N/A", res["S2"])

        # Test 4-byte ranges (LE)
        # Valid Max: 0xFAFFFFFF -> FF FF FF FA
        res = da.describe_message_data(400, bitstring.Bits(hex="FFFFFFFA"))
        self.assertIn("4211081215", res["S4"])
        self.assertIn("[units]", res["S4"])

        # Error: 0xFE000000 -> 00 00 00 FE
        res = da.describe_message_data(400, bitstring.Bits(hex="000000FE"))
        self.assertIn("Error", res["S4"])

        # Specific: 0xFB000000 -> 00 00 00 FB
        res = da.describe_message_data(400, bitstring.Bits(hex="000000FB"))
        self.assertIn("Parameter specific", res["S4"])

    def test_continuous_indicator_ranges(self):
        from pretty_j1939.core.describe import get_describer
        import bitstring

        # DB with Accelerator (91) and Brake (521) pedal positions
        # Both are 1 byte, 0.4 resolution, offset 0.
        # Max valid 100% = 250 (0xFA).
        describer = get_describer(
            include_na=True,
            da_json={
                "J1939PGNdb": {
                    "61443": {"Label": "EEC2", "SPNs": [91], "SPNStartBits": [24]},
                    "65265": {"Label": "CCVS", "SPNs": [521], "SPNStartBits": [8]},
                },
                "J1939SPNdb": {
                    "91": {
                        "Name": "Accelerator Pedal Position 1",
                        "Units": "%",
                        "SPNLength": 8,
                        "Resolution": 0.4,
                        "Offset": 0,
                        "OperationalLow": 0,
                        "OperationalHigh": 100,
                    },
                    "521": {
                        "Name": "Brake Pedal Position",
                        "Units": "%",
                        "SPNLength": 8,
                        "Resolution": 0.4,
                        "Offset": 0,
                        "OperationalLow": 0,
                        "OperationalHigh": 100,
                    },
                },
                "J1939SATabledb": {},
                "J1939BitDecodings": {},
            },
        )
        da = describer.da_describer

        # EEC2 Payload: (ignore 3 bytes) + byte 4 (bit 24) is SPN 91
        # Test Valid Max (0xFA = 250)
        res = da.describe_message_data(61443, bitstring.Bits(hex="000000FA"))
        self.assertEqual(res["Accelerator Pedal Position 1"], "100.0 [%]")

        # Test Parameter Specific (0xFB = 251)
        res = da.describe_message_data(61443, bitstring.Bits(hex="000000FB"))
        self.assertIn("Parameter specific", res["Accelerator Pedal Position 1"])

        # Test Reserved (0xFC = 252)
        res = da.describe_message_data(61443, bitstring.Bits(hex="000000FC"))
        self.assertIn("Reserved", res["Accelerator Pedal Position 1"])

        # CCVS Payload: byte 1 (ignore) + byte 2 (bit 8) is SPN 521
        # Test Error (0xFE = 254)
        res = da.describe_message_data(65265, bitstring.Bits(hex="00FE"))
        self.assertIn("Error", res["Brake Pedal Position"])

        # Test Not Available (0xFF = 255)
        res = da.describe_message_data(65265, bitstring.Bits(hex="00FF"))
        self.assertIn("N/A", res["Brake Pedal Position"])


# ---------------------------------------------------------------------------
# J1939BitDecodings creation tests
#
# These tests ensure the bit decoding pipeline that produces
# J1939BitDecodings entries from SPN descriptions continues to work
# after refactoring. The expected output format is:
#   { "<spn_number>": { "<value>": "<description>", ... }, ... }
# ---------------------------------------------------------------------------


class TestIsEnumLine(unittest.TestCase):
    """Tests for da_parsers.is_enum_line."""

    def test_decimal_enum_line(self):
        self.assertTrue(da_parsers.is_enum_line("00 Override disabled"))
        self.assertTrue(da_parsers.is_enum_line("01 Speed control"))
        self.assertTrue(da_parsers.is_enum_line("1 something"))

    def test_binary_enum_line(self):
        self.assertTrue(da_parsers.is_enum_line("00b Off"))
        self.assertTrue(da_parsers.is_enum_line("01b On"))

    def test_hex_enum_line(self):
        self.assertTrue(da_parsers.is_enum_line("0xF0 Reserved"))

    def test_range_enum_line(self):
        self.assertTrue(da_parsers.is_enum_line("2-15 Reserved"))

    def test_bit_state_header(self):
        self.assertTrue(da_parsers.is_enum_line("Bit State descriptions"))
        self.assertTrue(da_parsers.is_enum_line("bit states:"))

    def test_non_enum_line(self):
        self.assertFalse(da_parsers.is_enum_line("This is a description"))
        self.assertFalse(da_parsers.is_enum_line(""))
        self.assertFalse(da_parsers.is_enum_line("The engine speed is measured"))


class TestMatchSingleEnumLine(unittest.TestCase):
    """Tests for da_parsers.match_single_enum_line."""

    def test_simple_decimal(self):
        match = da_parsers.match_single_enum_line("00 Override disabled")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups()[0], "00")

    def test_with_equals(self):
        match = da_parsers.match_single_enum_line("01 = activate")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups()[0], "01")

    def test_with_dash_separator(self):
        match = da_parsers.match_single_enum_line("02 -- reserved")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups()[0], "02")

    def test_binary_value(self):
        match = da_parsers.match_single_enum_line("00b Off")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups()[0], "00b")

    def test_hex_value(self):
        match = da_parsers.match_single_enum_line("0xFF Not available")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups()[0], "0xFF")


class TestGetEnumLineRange(unittest.TestCase):
    """Tests for da_parsers.get_enum_line_range."""

    def test_decimal_range_with_dash(self):
        result = da_parsers.get_enum_line_range("2-15 Reserved")
        self.assertIsNotNone(result)
        self.assertEqual(result, ("2", "15"))

    def test_decimal_range_with_to(self):
        result = da_parsers.get_enum_line_range("4 to 7 SAE reserved")
        self.assertIsNotNone(result)
        self.assertEqual(result, ("4", "7"))

    def test_hex_range(self):
        result = da_parsers.get_enum_line_range("0x10-0x1F Reserved")
        self.assertIsNotNone(result)
        self.assertEqual(result, ("0x10", "0x1F"))

    def test_single_value_not_a_range(self):
        result = da_parsers.get_enum_line_range("00 Override disabled")
        self.assertIsNone(result)

    def test_binary_start_decimal_end_is_range(self):
        # "0b" starts with "0" which matches the guard regex [01b] for both
        # groups[0] and groups[2] ("15" starts with "1"), so the guard
        # doesn't reject this as a non-range
        result = da_parsers.get_enum_line_range("0b-15 some text")
        self.assertEqual(result, ("0b", "15"))


class TestGetEnumLines(unittest.TestCase):
    """Tests for da_parsers.get_enum_lines."""

    def test_simple_enum_description(self):
        description = [
            "00 Override disabled",
            "01 Speed control",
            "02 Torque control",
            "03 Speed/Torque limit control",
        ]
        result = da_parsers.get_enum_lines(description)
        self.assertEqual(len(result), 4)
        self.assertIn("00 Override disabled", result[0])
        self.assertIn("01 Speed control", result[1])

    def test_description_with_preamble(self):
        description = [
            "This SPN controls the engine mode.",
            "00 Override disabled",
            "01 Speed control",
            "02 Torque control",
        ]
        result = da_parsers.get_enum_lines(description)
        self.assertEqual(len(result), 3)

    def test_blocklist_filtering(self):
        description = [
            "00 Override disabled",
            "01 Speed control",
            "3 ASCII space characters pad this field",
            "02 Torque control",
        ]
        result = da_parsers.get_enum_lines(description)
        # "3 ASCII space characters" is in the blocklist so should be excluded
        self.assertTrue(all("ASCII space" not in line for line in result))

    def test_first_line_range_still_starts_enum_collection(self):
        # A range line "2-15 Reserved" also passes match_single_enum_line
        # (matching "2" as single value), so it starts enum collection
        description = [
            "2-15 Reserved",
            "00 Override disabled",
            "01 Speed control",
        ]
        result = da_parsers.get_enum_lines(description)
        self.assertEqual(len(result), 3)

    def test_bit_state_header_included_as_enum_line(self):
        description = [
            "Bit State descriptions:",
            "00 Off",
            "01 On",
            "10 Error",
        ]
        result = da_parsers.get_enum_lines(description)
        # The "Bit State" header line matches is_enum_line (starts with "bit state")
        # and match_single_enum_line ('B' is in regex class [A-F]). After add_enum_line
        # strips the "Bit State" substring via regex, the remaining " descriptions:"
        # is kept as an enum line entry alongside the actual enum values.
        self.assertEqual(len(result), 4)
        self.assertIn("descriptions:", result[0])


class TestIsEnumLinesBinary(unittest.TestCase):
    """Tests for da_parsers.is_enum_lines_binary."""

    def test_binary_lines(self):
        lines = ["00b Off", "01b On", "10b Error", "11b Not Available"]
        self.assertTrue(da_parsers.is_enum_lines_binary(lines))

    def test_decimal_lines(self):
        lines = ["00 Off", "01 On", "02 Error", "03 Not Available"]
        self.assertFalse(da_parsers.is_enum_lines_binary(lines))

    def test_hex_lines(self):
        lines = ["0x00 Off", "0x01 On"]
        self.assertFalse(da_parsers.is_enum_lines_binary(lines))


class TestGetEnumLineDescription(unittest.TestCase):
    """Tests for da_parsers.get_enum_line_description."""

    def test_decimal_with_dash(self):
        result = da_parsers.get_enum_line_description(
            "00 Override disabled - disable any existing control."
        )
        self.assertEqual(result, "override disabled - disable any existing control.")

    def test_decimal_with_equals(self):
        result = da_parsers.get_enum_line_description("01 = activate")
        self.assertEqual(result, "activate")

    def test_range_description(self):
        result = da_parsers.get_enum_line_description("2-15 Reserved")
        self.assertEqual(result, "reserved")

    def test_sae_and_iso_preserved(self):
        result = da_parsers.get_enum_line_description("00 sae reserved value")
        self.assertEqual(result, "SAE reserved value")
        result = da_parsers.get_enum_line_description("01 iso defined protocol")
        self.assertEqual(result, "ISO defined protocol")

    def test_xml_artifact_cleanup(self):
        result = da_parsers.get_enum_line_description("00 deactivate_x000d_")
        self.assertEqual(result, "deactivate")

    def test_lowercase_conversion(self):
        result = da_parsers.get_enum_line_description("01 Speed Control Mode")
        self.assertEqual(result, "speed control mode")


class TestIsSpnLikelyBitmapped(unittest.TestCase):
    """Tests for da_parsers.is_spn_likely_bitmapped."""

    def test_bitmapped_description(self):
        description = (
            "00 Override disabled\n"
            "01 Speed control\n"
            "02 Torque control\n"
            "03 Speed/Torque limit control"
        )
        self.assertTrue(da_parsers.is_spn_likely_bitmapped(description))

    def test_not_bitmapped_numeric(self):
        description = "Engine speed in RPM. Range 0 to 8031.875."
        self.assertFalse(da_parsers.is_spn_likely_bitmapped(description))

    def test_not_bitmapped_two_values(self):
        # Only 2 enum lines, need > 2
        description = "00 Off\n01 On"
        self.assertFalse(da_parsers.is_spn_likely_bitmapped(description))


class TestCreateBitObjectFromDescription(unittest.TestCase):
    """Tests for da_parsers.create_bit_object_from_description.

    These tests verify the end-to-end pipeline that produces J1939BitDecodings
    entries from SPN description text, using descriptions similar to those
    from the J1939 Digital Annex.
    """

    def test_decimal_single_values(self):
        """Test SPN description with decimal single values (like SPN 695)."""
        description = (
            "00 Override disabled - disable any existing control commanded "
            "by the source of this command.\n"
            "01 Speed control - govern speed to the included desired speed value.\n"
            "02 Torque control - control torque to the included desired torque value.\n"
            "03 (Speed/Torque limit control) and the torque limit to a high value (FAh)."
        )
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 4)
        self.assertIn("0", bit_object)
        self.assertIn("1", bit_object)
        self.assertIn("2", bit_object)
        self.assertIn("3", bit_object)
        self.assertIn("override disabled", bit_object["0"])
        self.assertIn("speed control", bit_object["1"])
        self.assertIn("torque control", bit_object["2"])
        self.assertIn("speed/torque limit control", bit_object["3"])

    def test_binary_values(self):
        """Test SPN description with binary values (like 2-bit status fields)."""
        description = "00b Off\n" "01b On\n" "10b Error\n" "11b Not Available"
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 4)
        self.assertEqual(bit_object["0"], "off")
        self.assertEqual(bit_object["1"], "on")
        self.assertEqual(bit_object["2"], "error")
        self.assertEqual(bit_object["3"], "not available")

    def test_decimal_range_expansion(self):
        """Test that ranges like '2-15 Reserved' are expanded."""
        description = (
            "0 1000 ms transmission rate\n"
            "1 500 ms transmission rate\n"
            "2-15 Reserved"
        )
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 16)
        self.assertEqual(bit_object["0"], "1000 ms transmission rate")
        self.assertEqual(bit_object["1"], "500 ms transmission rate")
        for i in range(2, 16):
            self.assertEqual(bit_object[str(i)], "reserved")

    def test_hex_values(self):
        """Test SPN description with hex values."""
        description = "0x00 Disabled\n" "0x01 Enabled\n" "0xFF Not Available"
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 3)
        self.assertEqual(bit_object["0"], "disabled")
        self.assertEqual(bit_object["1"], "enabled")
        self.assertEqual(bit_object["255"], "not available")

    def test_hex_range_expansion(self):
        """Test hex range expansion."""
        description = "0x00 Off\n" "0x01 On\n" "0x02-0x0F Reserved"
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 16)
        self.assertEqual(bit_object["0"], "off")
        self.assertEqual(bit_object["1"], "on")
        for i in range(2, 16):
            self.assertEqual(bit_object[str(i)], "reserved")

    def test_binary_range_expansion(self):
        """Test binary range expansion."""
        description = "00b Off\n" "01b On\n" "10b-11b Reserved"
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 4)
        self.assertEqual(bit_object["0"], "off")
        self.assertEqual(bit_object["1"], "on")
        self.assertEqual(bit_object["2"], "reserved")
        self.assertEqual(bit_object["3"], "reserved")

    def test_override_control_mode_spn695(self):
        """End-to-end test: SPN 695 Override Control Mode description."""
        description = (
            "00 Override disabled - disable any existing control commanded "
            "by the source of this command.\n"
            '01 Speed control - govern speed to the included "desired speed" value.\n'
            '02 Torque control - control torque to the included "desired torque" value.\n'
            "03 (Speed/Torque limit control) and the torque limit to a high value (FAh)."
        )
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 4)
        self.assertIn("override disabled", bit_object["0"])
        self.assertIn("speed control", bit_object["1"])
        self.assertIn("torque control", bit_object["2"])
        self.assertIn("speed/torque limit control", bit_object["3"])

    def test_speed_control_characteristic_spn696(self):
        """End-to-end test: SPN 696 speed control characteristic description."""
        description = (
            "00 This speed governor gain selection is adjusted to provide rapid transition.\n"
            "01 This control has been optimized to minimize rpm overshoot and undershoot.\n"
            "02 This control has been optimized for a more complex plant.\n"
            "03 This speed control is available for applications requiring additional compensation."
        )
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 4)
        self.assertIn("rapid transition", bit_object["0"])
        self.assertIn("minimize rpm overshoot", bit_object["1"])
        self.assertIn("complex plant", bit_object["2"])
        self.assertIn("additional compensation", bit_object["3"])

    def test_priority_spn897(self):
        """End-to-end test: SPN 897 Override Control Mode Priority description."""
        description = (
            "00 Highest priority = used for situations that require immediate action.\n"
            "01 High priority = used for control situations that require prompt action.\n"
            "02 Medium priority = used for powertrain control operations.\n"
            "03 Low priority = used to indicate non-critical function."
        )
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 4)
        self.assertIn("highest priority", bit_object["0"])
        self.assertIn("high priority", bit_object["1"])
        self.assertIn("medium priority", bit_object["2"])
        self.assertIn("low priority", bit_object["3"])

    def test_transmission_rate_spn3349(self):
        """End-to-end test: SPN 3349 with transmission rate values."""
        description = (
            "0 1000 ms transmission rate\n"
            "1 500 ms transmission rate\n"
            "2-15 Reserved"
        )
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(bit_object["0"], "1000 ms transmission rate")
        self.assertEqual(bit_object["1"], "500 ms transmission rate")
        # Range 2-15 should be expanded
        for i in range(2, 16):
            self.assertIn(str(i), bit_object)
            self.assertEqual(bit_object[str(i)], "reserved")

    def test_empty_description_produces_empty_object(self):
        """Empty or non-enum descriptions should produce empty bit objects."""
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description("", bit_object)
        self.assertEqual(len(bit_object), 0)

    def test_numeric_description_produces_empty_object(self):
        """Purely numeric SPN descriptions should not produce bit objects."""
        description = "Engine speed in RPM. Range 0 to 8031.875."
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)
        self.assertEqual(len(bit_object), 0)

    def test_mixed_preamble_and_enums(self):
        """Description with preamble text followed by enums."""
        description = (
            "This parameter indicates the current engine state.\n"
            "The valid states are:\n"
            "00 Engine off\n"
            "01 Engine cranking\n"
            "02 Engine running\n"
            "03 Engine shutting down"
        )
        bit_object = OrderedDict()
        da_parsers.create_bit_object_from_description(description, bit_object)

        self.assertEqual(len(bit_object), 4)
        self.assertEqual(bit_object["0"], "engine off")
        self.assertEqual(bit_object["1"], "engine cranking")
        self.assertEqual(bit_object["2"], "engine running")
        self.assertEqual(bit_object["3"], "engine shutting down")


class TestProcessSpnsAndPgnsTab(unittest.TestCase):
    def setUp(self):
        self.converter = J1939daConverter.__new__(J1939daConverter)
        self.converter.j1939db = OrderedDict()
        self.converter.digital_annex_xls_list = []

    def _create_mock_sheet(self, data_rows):
        header = [
            "PGN",
            "SPN",
            "PG_ACRONYM",
            "PG_LABEL",
            "PG_DATA_LENGTH",
            "TRANSMISSION_RATE",
            "SP_POSITION_IN_PG",
            "SP_LABEL",
            "OFFSET",
            "DATA_RANGE",
            "RESOLUTION",
            "SP_LENGTH",
            "UNITS",
            "OPERATIONAL_RANGE",
            "SP_DESCRIPTION",
        ]

        class MockSheetLocal:
            def __init__(self, rows):
                self.rows = [header] + rows
                self.nrows = len(self.rows)

            def row_values(self, row_num):
                return self.rows[row_num]

        return MockSheetLocal(data_rows)

    def test_process_spns_standard(self):
        row = [
            61444,
            190,
            "EEC1",
            "Electronic Engine Controller 1",
            8,
            "100 ms",
            "4.1",
            "Engine Speed",
            "0",
            "0 to 8031.875 rpm",
            "0.125 rpm/bit",
            16,
            "rpm",
            "0 to 8031.875",
            "Engine speed description.",
        ]
        sheet = self._create_mock_sheet([row])
        self.converter.process_spns_and_pgns_tab(sheet)

        self.assertIn("J1939PGNdb", self.converter.j1939db)
        self.assertIn("J1939SPNdb", self.converter.j1939db)

        pgndb = self.converter.j1939db["J1939PGNdb"]
        spndb = self.converter.j1939db["J1939SPNdb"]

        self.assertIn("61444", pgndb)
        self.assertEqual(pgndb["61444"]["Name"], "Electronic Engine Controller 1")
        self.assertEqual(pgndb["61444"]["SPNs"], [190])
        self.assertEqual(pgndb["61444"]["SPNStartBits"], [[24]])

        self.assertIn("190", spndb)
        self.assertEqual(spndb["190"]["Name"], "Engine Speed")
        self.assertEqual(spndb["190"]["SPNLength"], 16)
        self.assertEqual(spndb["190"]["Resolution"], 0.125)
        self.assertEqual(spndb["190"]["Offset"], 0.0)

    def test_process_spns_enum(self):
        row = [
            61444,
            899,
            "EEC1",
            "Electronic Engine Controller 1",
            8,
            "100 ms",
            "1.1",
            "Engine Torque Mode",
            "0",
            "",
            "4 states",
            4,
            "bit",
            "",
            "00b Low speed\n01b High speed\n10b Error\n11b Not available",
        ]
        sheet = self._create_mock_sheet([row])
        self.converter.process_spns_and_pgns_tab(sheet)

        self.assertIn("J1939BitDecodings", self.converter.j1939db)
        bit_decodings = self.converter.j1939db["J1939BitDecodings"]

        self.assertIn("899", bit_decodings)
        self.assertEqual(bit_decodings["899"]["0"], "low speed")
        self.assertEqual(bit_decodings["899"]["1"], "high speed")
        self.assertEqual(bit_decodings["899"]["2"], "error")
        self.assertEqual(bit_decodings["899"]["3"], "not available")

    def test_process_spns_variable_length(self):
        row = [
            65226,
            1706,
            "DM1",
            "Active Diagnostic Trouble Codes",
            "Variable",
            "1 s",
            "",
            "Active DTCs",
            "0",
            "",
            "",
            "Variable, delimiter *",
            "",
            "",
            "A list of DTCs",
        ]
        sheet = self._create_mock_sheet([row])
        self.converter.process_spns_and_pgns_tab(sheet)

        pgndb = self.converter.j1939db["J1939PGNdb"]
        spndb = self.converter.j1939db["J1939SPNdb"]

        self.assertEqual(pgndb["65226"]["PGNLength"], "Variable")
        self.assertEqual(spndb["1706"]["SPNLength"], "Variable")
        self.assertEqual(spndb["1706"]["Delimiter"], "0x2a")  # '*' is 0x2a

    def test_process_spns_edge_cases(self):
        row1 = [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        row2 = ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]
        row3 = [
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
            "N/A",
        ]
        row4 = [
            65226,
            "",
            "DM1",
            "Active Diagnostic Trouble Codes",
            "Variable",
            "1 s",
            "",
            "",
            "0",
            "",
            "1",
            "Variable",
            "",
            "",
            "",
        ]
        sheet = self._create_mock_sheet([row1, row2, row3, row4])
        self.converter.process_spns_and_pgns_tab(sheet)

        pgndb = self.converter.j1939db["J1939PGNdb"]
        self.assertIn("65226", pgndb)
        self.assertEqual(pgndb["65226"]["SPNs"], [])


if __name__ == "__main__":
    unittest.main()
