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
    # Explicitly use the project's database to avoid environment-specific failures
    db_path = os.path.join("pretty_j1939", "J1939db.json")
    # "engine" resolves to 0 and 1. test_tp_frames.txt has SA 0.
    stdout, stderr, code = run_cli(
        ["tests/test_tp_frames.txt", "--filter-sa", "engine", "--da-json", db_path]
    )
    assert code == 0
    assert "Resolving Source Address filter 'engine' to addresses: 0, 1" in stderr
    assert '"SA":"Engine #1(  0)"' in stdout


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


def test_cli_summary_order():
    """Verify summary order (broadcast edges last)."""
    # Create a temp log with PDU1 and PDU2
    log_file = "test_summary_temp.log"
    with open(log_file, "w") as f:
        f.write(
            "(1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n"
        )  # PDU2 (Broadcast)
        f.write(
            "(1612543138.001000) vcan0 18EF000B#0000001B000000B4\n"
        )  # PDU1 (Point-to-point)

    try:
        stdout, stderr, code = run_cli([log_file, "--summary"])
        assert code == 0
        summary_line = [line for line in stdout.splitlines() if '"Summary"' in line][0]
        # PropA (PDU1) should come before EEC1 (PDU2/Broadcast)
        assert summary_line.find("PropA") < summary_line.find("EEC1")
    finally:
        if os.path.exists(log_file):
            os.remove(log_file)
