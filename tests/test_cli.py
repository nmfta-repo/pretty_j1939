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
        ["-", "--da-json", db_path], stdin_content=stdin_data
    )

    assert code == 0
    assert '"PGN":"EEC1(61444)"' in stdout


def test_cli_short_format():
    """Verify CLI parsing of 'ID#DATA' format without timestamps/interface."""
    # Using PGN 61444 (EEC1)
    stdin_data = "0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")

    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path], stdin_content=stdin_data
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
        ["-", "--da-json", db_path], stdin_content=stdin_data
    )

    assert code == 0
    assert '"PGN":"EEC1(61444)"' in stdout


def test_cli_indexed_format():
    """Verify CLI parsing of indexed candump format."""
    stdin_data = "1 (1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")

    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path], stdin_content=stdin_data
    )

    assert code == 0
    assert '"PGN":"EEC1(61444)"' in stdout


def test_cli_interface_format():
    """Verify CLI parsing of 'interface ID#DATA' format."""
    stdin_data = "vcan0 0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")

    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path], stdin_content=stdin_data
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
            [log_file, "--filter-pgn", "61444", "--da-json", db_path]
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
            [log_file, "--filter-sa", "engine", "--da-json", db_path]
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
        ["-", "--da-json", db_path], stdin_content=stdin_data
    )
    assert code == 0
    assert '"Summary"' not in stdout


def test_cli_summary_default_show():
    """Verify summary is shown by default for > 8 messages."""
    stdin_data = "0CF00400#0041FF20481400F0\n" * 9
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--da-json", db_path], stdin_content=stdin_data
    )
    assert code == 0
    assert '"Summary"' in stdout


def test_cli_summary_override_show():
    """Verify --summary override always shows summary."""
    stdin_data = "0CF00400#0041FF20481400F0\n"
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--summary", "--da-json", db_path], stdin_content=stdin_data
    )
    assert code == 0
    assert '"Summary"' in stdout


def test_cli_summary_override_hide():
    """Verify --no-summary override always hides summary."""
    stdin_data = "0CF00400#0041FF20481400F0\n" * 10
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    stdout, stderr, code = run_cli(
        ["-", "--no-summary", "--da-json", db_path], stdin_content=stdin_data
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
            ["-", "--da-json", db_filename], stdin_content=stdin_data
        )
        assert code == 0
        # Check if the VIN is decoded. If there's reversal, we'll see it here.
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
            ["-", "--da-json", db_filename], stdin_content=stdin_data
        )
        assert code == 0
        assert '"New Address":"0x30"' in stdout
    finally:
        if os.path.exists(db_filename):
            os.remove(db_filename)
