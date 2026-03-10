#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
import pytest
import sys
import os
from io import StringIO
from pretty_j1939.__main__ import main
from unittest.mock import patch


def run_cli(args, stdin_content=None):
    """Helper to run CLI and capture output."""
    original_argv = sys.argv
    original_stdout = sys.stdout
    original_stderr = sys.stderr

    sys.argv = ["pretty_j1939"] + args
    sys.stdout = StringIO()
    sys.stderr = StringIO()

    try:
        if stdin_content is not None:
            with patch("sys.stdin", StringIO(stdin_content)):
                main()
        else:
            main()
        return sys.stdout.getvalue(), sys.stderr.getvalue(), 0
    except SystemExit as e:
        return sys.stdout.getvalue(), sys.stderr.getvalue(), e.code
    except Exception as e:
        return sys.stdout.getvalue(), sys.stderr.getvalue() + str(e), 1
    finally:
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        sys.argv = original_argv


def test_cli_stdin():
    """Verify CLI reading from stdin via '-'."""
    # Using PGN 61444 (EEC1) which is in the default database
    stdin_data = "(1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")

    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )

    assert code == 0
    assert '"PGN":"EEC1(61444)"' in stdout


def test_cli_short_format():
    """Verify CLI parsing of 'ID#DATA' format without timestamps/interface."""
    # Using PGN 61444 (EEC1)
    stdin_data = "0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")

    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )

    assert code == 0
    assert '"PGN":"EEC1(61444)"' in stdout


def test_cli_timestamp_format():
    """Verify CLI parsing of 'Timestamp: ...' format."""
    stdin_data = (
        "Timestamp: 1612543138.000000 ID: 0CF00400 DL: 8 00 41 FF 20 48 14 00 F0\n"
    )
    db_path = os.path.join("pretty_j1939", "J1939db.json")

    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )

    assert code == 0
    assert '"PGN":"EEC1(61444)"' in stdout


def test_cli_indexed_format():
    """Verify CLI parsing of indexed candump format."""
    stdin_data = "1 (1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")

    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )

    assert code == 0
    assert '"PGN":"EEC1(61444)"' in stdout


def test_cli_interface_format():
    """Verify CLI parsing of 'interface ID#DATA' format."""
    stdin_data = "vcan0 0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")

    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )

    assert code == 0
    assert '"PGN":"EEC1(61444)"' in stdout


def test_cli_filter_pgn():
    """Verify CLI PGN filtering."""
    # Create a temp log with PGN 61444
    log_file = "test_filter_pgn_temp.log"
    with open(log_file, "w") as f:
        f.write("(1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n")

    # Explicitly use the project's database to avoid environment-specific failures
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    try:
        stdout, stderr, code = run_cli(
            [log_file, "--filter-pgn", "61444", "--da-json", db_path, "--json"]
        )
        assert code == 0
        assert '"PGN":"EEC1(61444)"' in stdout
    finally:
        if os.path.exists(log_file):
            os.remove(log_file)


def test_cli_filter_sa_string():
    """Verify CLI Source Address filtering using string lookup."""
    # Create a temp log with SA 0
    log_file = "test_filter_sa_temp.log"
    with open(log_file, "w") as f:
        f.write("(1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n")

    # Explicitly use the project's database to avoid environment-specific failures
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    # "engine" resolves to 0 and 1 in the standard database
    try:
        stdout, stderr, code = run_cli(
            [log_file, "--filter-sa", "engine", "--da-json", db_path, "--json"]
        )
        assert code == 0
        assert "Resolving Source Address filter 'engine' to addresses: 0, 1" in stderr
        assert '"SA":"Engine #1(  0)"' in stdout
    finally:
        if os.path.exists(log_file):
            os.remove(log_file)


def test_cli_highlight_pgn():
    """Verify CLI highlighting for PGNs."""
    # Create a temp log with PGN 61444
    log_file = "test_highlight_pgn_temp.log"
    with open(log_file, "w") as f:
        f.write("(1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n")

    # Explicitly use the project's database to avoid environment-specific failures
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    try:
        stdout, stderr, code = run_cli(
            [
                log_file,
                "--highlight-pgn",
                "61444",
                "--color",
                "always",
                "--da-json",
                db_path,
            ]
        )
        assert code == 0
        # Check for bright white highlight color (255;255;255)
        assert "255;255;255" in stdout
    finally:
        if os.path.exists(log_file):
            os.remove(log_file)


def test_cli_invalid_filter():
    """Verify CLI failure on invalid filter string."""
    # Explicitly use the project's database to avoid environment-specific failures
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        [
            "tests/test_tp_frames.txt",
            "--filter-pgn",
            "nonexistent_pgn_label",
            "--da-json",
            db_path,
        ]
    )
    assert code != 0
    assert "Error: 'nonexistent_pgn_label' did not match any PGN" in stderr


def test_cli_summary_default_hide():
    """Verify summary is hidden by default for <= 8 messages."""
    stdin_data = "0CF00400#0041FF20481400F0\n" * 8
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )
    assert code == 0
    assert '"Summary"' not in stdout


def test_cli_summary_default_show():
    """Verify summary is shown by default for > 8 messages."""
    stdin_data = "0CF00400#0041FF20481400F0\n" * 9
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )
    assert code == 0
    assert '"Summary"' in stdout


def test_cli_summary_override_show():
    """Verify --summary override always shows summary."""
    stdin_data = "0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--summary", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )
    assert code == 0
    assert '"Summary"' in stdout


def test_cli_summary_override_hide():
    """Verify --no-summary override always hides summary."""
    stdin_data = "0CF00400#0041FF20481400F0\n" * 10
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--no-summary", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )
    assert code == 0
    assert '"Summary"' not in stdout


def test_cli_tp_vin_integration():
    """Verify CLI reassembly and decoding of a 17-byte VIN via BAM."""
    # Custom DB for VIN
    db = {
        "J1939PGNdb": {
            "65259": {"Label": "VI", "Name": "Vehicle Identification", "SPNs": [237]}
        },
        "J1939SPNdb": {
            "237": {
                "Name": "VIN",
                "Units": "ASCII",
                "SPNLength": 136,
                "Resolution": 1,
                "Offset": 0,
                "StartBit": 0,
            }
        },
    }
    import json

    db_filename = "tmp_tp_db.json"
    with open(db_filename, "w") as f:
        json.dump(db, f)

    vin_str = "12345678901234567"
    vin_hex = vin_str.encode("ascii").hex().upper()

    # BAM Setup
    stdin_data = (
        "18ECFF00#20110003FFEBFE00\n"
        f"18EBFF00#01{vin_hex[0:14]}\n"
        f"18EBFF00#02{vin_hex[14:28]}\n"
        f"18EBFF00#03{vin_hex[28:34]}FFFFFFFF\n"
    )

    try:
        stdout, stderr, code = run_cli(
            ["-", "--da-json", db_filename, "--json"], stdin_content=stdin_data
        )
        assert code == 0
        # Check if the VIN is decoded.
        assert f'"VIN":"{vin_str}"' in stdout
    finally:
        if os.path.exists(db_filename):
            os.remove(db_filename)


def test_cli_tp_commanded_address_integration():
    """Verify CLI reassembly and decoding of Commanded Address via BAM."""
    db = {
        "J1939PGNdb": {
            "65240": {"Label": "CA", "Name": "Commanded Address", "SPNs": [2849, 2850]}
        },
        "J1939SPNdb": {
            "2849": {
                "Name": "NAME",
                "Units": "byte",
                "SPNLength": 64,
                "Resolution": 1,
                "Offset": 0,
                "StartBit": 0,
            },
            "2850": {
                "Name": "New Address",
                "Units": "byte",
                "SPNLength": 8,
                "Resolution": 1,
                "Offset": 0,
                "StartBit": 64,
            },
        },
    }
    import json

    db_filename = "tmp_ca_db.json"
    with open(db_filename, "w") as f:
        json.dump(db, f)

    # NAME (8 bytes) + New Address (1 byte)
    ca_payload_hex = "010203040506070830"

    stdin_data = (
        "18ECFF00#20090002FFD8FE00\n"  # BAM: Len=9, Pkts=2, PGN=65240
        f"18EBFF00#01{ca_payload_hex[0:14]}\n"
        f"18EBFF00#02{ca_payload_hex[14:18]}FFFFFFFFFF\n"
    )

    try:
        stdout, stderr, code = run_cli(
            ["-", "--da-json", db_filename, "--json"], stdin_content=stdin_data
        )
        assert code == 0
        assert '"New Address":"0x30"' in stdout
    finally:
        if os.path.exists(db_filename):
            os.remove(db_filename)


def test_cli_uds_isotp_reassembly():
    """Verify CLI reassembly of a 55-byte UDS response via ISO-TP (PGN 0xDA00)."""
    # 55-byte De Bruijn sequence (k=10, n=2)
    debruijn_55 = "00102030405060708091121314151617181922324252627282933435363738394454647484955657585966768697787988990"[
        :55
    ]
    debruijn_hex = debruijn_55.encode("ascii").hex().upper()

    # PDU: 62 00 77 + debruijn
    pdu_hex = "620077" + debruijn_hex

    def get_cf(sn, start_byte, length):
        data = pdu_hex[start_byte * 2 : (start_byte + length) * 2]
        # Pad with 00 to 7 bytes (14 hex chars)
        data = data.ljust(14, "0")
        return f"18DAF100#{ (0x20 | (sn & 0x0F)):02X}{data}\n"

    stdin_data = (
        "18DA00F1#0322007700000000\n"  # Request RDID 0x0077
        f"18DAF100#103A{pdu_hex[0:12]}\n"  # First Frame (6 bytes of PDU)
    )
    for i in range(1, 8):
        stdin_data += get_cf(i, 6 + (i - 1) * 7, 7)
    stdin_data += get_cf(8, 6 + 7 * 7, 3)

    # Add filler messages to ensure we exceed any threshold and have enough activity
    filler = "0CF00400#0000000000000000\n"
    stdin_data += filler * 10

    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--no-summary", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )

    assert code == 0
    # The reassembled payload hex should be present (case insensitive)
    assert pdu_hex in stdout.upper()


def test_cli_help_content():
    """Verify that the CLI help command works."""
    stdout, stderr, code = run_cli(["--help"])
    assert code == 0
    assert "usage:" in stdout.lower()
    assert "pretty_j1939" in stdout.lower()


def test_cli_filter_sa_sa0():
    """Verify that Source Address filtering works."""
    candump_data = (
        " (1615397400.1) can0 0CF00400#0000002048000000\n"  # SA 0
        " (1615397400.2) can0 0CF00401#0000002048000000\n"  # SA 1
    )
    # Filter only for SA 0
    stdout, stderr, code = run_cli(
        ["-", "--filter-sa", "0", "--no-summary", "--json"], stdin_content=candump_data
    )
    assert code == 0
    assert '"SA":"Engine #1(  0)"' in stdout
    assert '"SA":"???(  1)"' not in stdout


def test_cli_custom_da_json_wellknown(tmp_path):
    """Verify that a custom DA JSON file can be used."""
    import json

    db = {
        "J1939SATabledb": {"123": "Custom Controller"},
        "J1939PGNdb": {
            "61444": {  # Use a well-known PDU2 PGN to avoid any parsing surprises
                "Label": "CST",
                "Name": "Custom PGN",
                "SPNs": [54321],
                "SPNStartBits": [0],
            }
        },
        "J1939SPNdb": {
            "54321": {
                "Name": "Custom SPN",
                "Units": "units",
                "SPNLength": 8,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 250,
            }
        },
        "J1939BitDecodings": {},
    }
    db_path = tmp_path / "custom_db.json"
    db_path.write_text(json.dumps(db))

    # EEC1: PGN 61444 (0xF004). SA 123 (0x7B).
    # can_id = 0x0CF0047B (Priority 3)
    can_id_hex = "0CF0047B"
    candump_line = f" (1615397400.1) can0 {can_id_hex}#2A00000000000000\n"

    stdout, stderr, code = run_cli(
        ["-", "--da-json", str(db_path), "--no-summary", "--json"],
        stdin_content=candump_line,
    )
    assert code == 0
    assert '"SA":"Custom Controller(123)"' in stdout
    assert "Custom PGN" in stdout or "CST" in stdout


def test_cli_interleaved_tp_sessions():
    """Verify CLI reassembly when J1939-TP and ISO-TP sessions are interleaved."""
    # 1. J1939-TP (BAM) - PGN 65226 (DM1), 10 bytes

    # 2. ISO-TP - PGN 0xDA00 (DIAG3), 10 bytes
    isotp_data = "62007701020304050607"

    stdin_lines = [
        "18ECFF00#200A0002FFCAFE00",  # TP.CM_BAM (DM1)
        "18DAF100#100A620077010203",  # ISO-TP FF
        "18EBFF00#0140FF5B000301FF",  # TP.DT 1
        "18DAF100#2104050607000000",  # ISO-TP CF
        "18EBFF00#02FF0000FFFFFFFF",  # TP.DT 2
    ]
    stdin_data = "\n".join(stdin_lines) + "\n"

    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--no-summary", "--da-json", db_path, "--json"], stdin_content=stdin_data
    )

    assert code == 0
    # Both reassembled payloads should be described
    assert isotp_data.upper() in stdout.upper()
    assert '"PGN":"DM1(65226)"' in stdout
    assert '"Malfunction Indicator Lamp Status"' in stdout
