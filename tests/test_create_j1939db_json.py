#
# Copyright (c) 2019-2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import unittest
from pretty_j1939.create_j1939db_json import J1939daConverter, SheetWrapper

class TestJ1939daConverter(unittest.TestCase):
    def setUp(self):
        # SheetWrapper is an abstract base class, we can instantiate a mock for testing _clean_value
        class MockSheet: pass
        self.wrapper = SheetWrapper(MockSheet())

    def test_clean_value_xml_artifacts(self):
        # Test the fix for _x000d_ and similar artifacts
        self.assertEqual(self.wrapper._clean_value("activate_x000d_"), "activate")
        self.assertEqual(self.wrapper._clean_value("de-activate_x000D_"), "de-activate")
        self.assertEqual(self.wrapper._clean_value("line1_x000d_line2"), "line1 line2")
        self.assertEqual(self.wrapper._clean_value("tab_x0009_char"), "tab char")
        self.assertEqual(self.wrapper._clean_value("multiple  spaces"), "multiple spaces")
        self.assertEqual(self.wrapper._clean_value("newlines\r\nstripped"), "newlines stripped")

    def test_get_pgn_data_len(self):
        self.assertEqual(J1939daConverter.get_pgn_data_len(8), "8") # If integer, returns string of int
        self.assertEqual(J1939daConverter.get_pgn_data_len("8 bytes"), "64") # If "bytes" in string, converts to bits
        self.assertEqual(J1939daConverter.get_pgn_data_len("Variable"), "Variable")
        self.assertEqual(J1939daConverter.get_pgn_data_len(None), "")
        self.assertEqual(J1939daConverter.get_pgn_data_len(""), "")

    def test_get_spn_len(self):
        self.assertEqual(J1939daConverter.get_spn_len(16), 16)
        self.assertEqual(J1939daConverter.get_spn_len("2 bytes"), 16)
        self.assertEqual(J1939daConverter.get_spn_len("8 bits"), 8)
        self.assertEqual(J1939daConverter.get_spn_len("Variable"), "Variable")
        self.assertEqual(J1939daConverter.get_spn_len("max 255 bytes"), "Variable")
        self.assertEqual(J1939daConverter.get_spn_len(None), "Variable")

    def test_get_spn_delimiter(self):
        self.assertEqual(J1939daConverter.get_spn_delimiter("delimiter *"), b"*")
        self.assertEqual(J1939daConverter.get_spn_delimiter("NULL delimiter"), b"\x00")
        self.assertIsNone(J1939daConverter.get_spn_delimiter("fixed length"))

    def test_just_numeric_expr(self):
        self.assertEqual(J1939daConverter.just_numeric_expr("123.45 km"), "123.45")
        self.assertEqual(J1939daConverter.just_numeric_expr("-10 to 50"), "-1050")
        self.assertEqual(J1939daConverter.just_numeric_expr("4/5"), "4/5")

    def test_get_spn_resolution(self):
        self.assertEqual(J1939daConverter.get_spn_resolution("0.125 rpm/bit"), 0.125)
        self.assertEqual(J1939daConverter.get_spn_resolution("1 states"), 1.0)
        self.assertEqual(J1939daConverter.get_spn_resolution("bit-mapped"), 0)
        self.assertEqual(J1939daConverter.get_spn_resolution("1/128 km/bit"), 1/128)
        self.assertEqual(J1939daConverter.get_spn_resolution("5 microsiemens/mm"), 5.0)

    def test_get_spn_offset(self):
        self.assertEqual(J1939daConverter.get_spn_offset("-125"), -125.0)
        self.assertEqual(J1939daConverter.get_spn_offset("0"), 0.0)
        self.assertEqual(J1939daConverter.get_spn_offset("not defined"), 0)

    def test_get_operational_hilo(self):
        self.assertEqual(J1939daConverter.get_operational_hilo("0 to 250.5", "km", 16), (0.0, 250.5))
        self.assertEqual(J1939daConverter.get_operational_hilo("0 to 2000 km", "m", 16), (0.0, 2000000.0))
        self.assertEqual(J1939daConverter.get_operational_hilo("not defined", "units", 8), (-1, -1))
        # Default range for bit-fields
        self.assertEqual(J1939daConverter.get_operational_hilo("", "", 2), (0, 3))

    def test_get_spn_start_bit(self):
        # Byte.Bit format
        self.assertEqual(J1939daConverter.get_spn_start_bit("1.1"), [0])
        self.assertEqual(J1939daConverter.get_spn_start_bit("1.5"), [4])
        self.assertEqual(J1939daConverter.get_spn_start_bit("2.1"), [8])
        # Byte range format (non-contiguous bytes: 4 and 6)
        self.assertEqual(J1939daConverter.get_spn_start_bit("4-6"), [24, 40])
        # Discrete bits
        self.assertEqual(J1939daConverter.get_spn_start_bit("1.1, 1.3"), [0, 2])
        # Variable/Complex (returns -1)
        self.assertEqual(J1939daConverter.get_spn_start_bit("a+0"), [-1])

    def test_get_enum_line_description(self):
        self.assertEqual(J1939daConverter.get_enum_line_description("00 - deactivate_x000d_"), "deactivate")
        self.assertEqual(J1939daConverter.get_enum_line_description("01 = activate"), "activate")
        self.assertEqual(J1939daConverter.get_enum_line_description("10: reserved"), "reserved")
        self.assertEqual(J1939daConverter.get_enum_line_description("0-100 -- normal range"), "normal range")

if __name__ == "__main__":
    unittest.main()
