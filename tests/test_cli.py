#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
import pytest
import sys
import os
from io import StringIO
from pretty_j1939.__main__ import main

def run_cli(args):
    """Helper to run CLI and capture output."""
    original_argv = sys.argv
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    sys.argv = ["pretty_j1939"] + args
    sys.stdout = StringIO()
    sys.stderr = StringIO()
    
    try:
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

def test_cli_filter_pgn():
    """Verify CLI PGN filtering."""
    # Use test_tp_frames.txt which contains PGN 0
    stdout, stderr, code = run_cli(["tests/test_tp_frames.txt", "--filter-pgn", "0"])
    assert code == 0
    assert '"PGN":"???(0/0x00000)"' in stdout

def test_cli_filter_sa_string():
    """Verify CLI Source Address filtering using string lookup."""
    # "engine" resolves to 0 and 1. test_tp_frames.txt has SA 0.
    stdout, stderr, code = run_cli(["tests/test_tp_frames.txt", "--filter-sa", "engine"])
    assert code == 0
    assert "Resolving Source Address filter 'engine' to addresses: 0, 1" in stderr
    assert '"SA":"Engine #1(  0)"' in stdout

def test_cli_highlight_pgn():
    """Verify CLI highlighting for PGNs."""
    stdout, stderr, code = run_cli(["tests/test_tp_frames.txt", "--highlight-pgn", "0", "--color", "always"])
    assert code == 0
    # Check for bright white highlight color (255;255;255)
    assert "255;255;255" in stdout

def test_cli_invalid_filter():
    """Verify CLI failure on invalid filter string."""
    stdout, stderr, code = run_cli(["test_tp_frames.txt", "--filter-pgn", "nonexistent_pgn_label"])
    assert code != 0
    assert "Error: 'nonexistent_pgn_label' did not match any PGN" in stderr

def test_cli_summary_order():
    """Verify summary order (broadcast edges last)."""
    # Create a temp log with PDU1 and PDU2
    log_file = "test_summary_temp.log"
    with open(log_file, "w") as f:
        f.write("(1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n") # PDU2 (Broadcast)
        f.write("(1612543138.001000) vcan0 18EF000B#0000001B000000B4\n") # PDU1 (Point-to-point)
    
    try:
        stdout, stderr, code = run_cli([log_file, "--summary"])
        assert code == 0
        summary_line = [line for line in stdout.splitlines() if '"Summary"' in line][0]
        # PropA (PDU1) should come before EEC1 (PDU2/Broadcast)
        assert summary_line.find("PropA") < summary_line.find("EEC1")
    finally:
        if os.path.exists(log_file):
            os.remove(log_file)
