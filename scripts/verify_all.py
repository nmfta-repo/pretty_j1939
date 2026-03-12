#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
import subprocess
import sys
import os


def run_test(name, cmd, expected_output=None):
    print(f"--- Running Test: {name} ---")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"FAIL: {name} (Return code {result.returncode})")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return False

        if expected_output:
            if isinstance(expected_output, str):
                expected_output = [expected_output]

            for expected in expected_output:
                if expected not in result.stdout:
                    print(
                        f"FAIL: {name} (Expected string '{expected}' not found in output)"
                    )
                    print("STDOUT:", result.stdout)
                    return False

        print(f"PASS: {name}")
        return True
    except Exception as e:
        print(f"ERROR: {name} - {e}")
        return False


def ensure_test_file(filename, content):
    if not os.path.exists(filename):
        print(f"Creating synthetic test file: {filename}")
        with open(filename, "w") as f:
            f.write(content)


# Synthetic data for missing files
TEST_FILES = {
    "tests/test_tp_frames.txt": "(1612543138.000000) vcan0 18ECFF00#10090002FF000000\n(1612543138.001000) vcan0 18EBFF00#0101020304050607\n(1612543138.002000) vcan0 18EBFF00#0201020304050607\n",
    "tests/test_mfr_spec.log": "1 (1612543138.000000) vcan0 18EF000B#0000001B000000B4\n",
    "tests/test_propa2.log": "1 (1612543138.000000) vcan0 19EF000B#0000001B000000B4\n",
    "tests/test_unknown_real.log": "1 (1612543138.000000) vcan0 19E2400B#FFFFFFFFFFFFFFFF\n",
    "tests/test_priority.log": "1 (1612543138.000000) vcan0 0CF00400#0041FF20481400F0\n2 (1612543138.001000) vcan0 18F00400#0041FF20481400F0\n3 (1612543138.002000) vcan0 1CF00400#0041FF20481400F0\n",
    "tests/test_requests.log": "(1612543138.000000) vcan0 18EAFF0B#ECFE00\n",
}

# Extensive tests that rely on external/large databases
# These are adjusted dynamically based on available databases
python_exe = f'"{sys.executable}"'
extensive_tests_config = [
    {
        "name": "Integration Test",
        "cmd": f"{python_exe} tests/test_integration.py",
        "expected": None,
    },
    {
        "name": "DA Integration Test",
        "cmd": "powershell -Command .\\run_da_integration.ps1",
        "expected": None,
    },
    {
        "name": "Streaming Producer",
        "cmd": f"{python_exe} -u tests/test_streaming_producer.py | {python_exe} -m pretty_j1939 - --da-json tmp\\J1939db.json --color always --candata",
        "expected": ['"Engine Speed"'],
    },
    {
        "name": "TP Frames",
        "cmd": f"{python_exe} -m pretty_j1939 --da-json tmp\\J1939db.json tests/test_tp_frames.txt",
        "expected": ['"PGN":"TSC1(0)"'],
        "expected_fallback": ['"PGN":"???(0/0x00000)"'],
    },
    {
        "name": "TP Frames Format",
        "cmd": f"{python_exe} -m pretty_j1939 --da-json tmp\\J1939db.json --candata --format tests/test_tp_frames.txt",
        "expected": ['"PGN": "TSC1(0)"', '"Bytes": "010203040506070102"'],
        "expected_fallback": [
            '"PGN": "???(0/0x00000)"',
            '"Bytes": "010203040506070102"',
        ],
    },
    {
        "name": "Mfr Spec",
        "cmd": f"{python_exe} -m pretty_j1939 --da-json tmp\\J1939db.json tests/test_mfr_spec.log",
        "expected": ['"PropA(61184)"'],
        "expected_fallback": ['"PropA(61184)"'],
    },
    {
        "name": "PropA2",
        "cmd": f"{python_exe} -m pretty_j1939 --da-json tmp\\J1939db.json tests/test_propa2.log",
        "expected": ['"PropA2(126720)"'],
        "expected_fallback": ['"PropA2(126720)"'],
    },
    {
        "name": "Unknown PGN",
        "cmd": f"{python_exe} -m pretty_j1939 --da-json tmp\\J1939db.json tests/test_unknown_real.log",
        "expected": ['"???(123392/0x1E200)"'],
    },
    {
        "name": "Priority",
        "cmd": f"{python_exe} -m pretty_j1939 --da-json tmp\\J1939db.json tests/test_priority.log",
        "expected": ['"Priority":"3"'],
    },
    {
        "name": "PGN Requests",
        "cmd": f"{python_exe} -m pretty_j1939 --da-json tmp\\J1939db.json tests/test_requests.log",
        "expected": ['"Request(59904)"', '"Requested:":"VI(65260)"'],
        "expected_fallback": ['"Request(59904)"', '"Requested:":"???(65260/0x0FEEC)"'],
    },
]


def main():
    success = True

    print("=== Running Pytest Suite (Default DB) ===")
    # Ensure pytest is available
    try:
        import pytest
    except ImportError:
        print("pytest not found. Installing test dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", ".[test]"], check=True, timeout=300)

    # Use sys.executable -m pytest to ensure we use the same python and include CWD in sys.path
    res = subprocess.run([sys.executable, "-m", "pytest"], timeout=300)
    if res.returncode != 0:
        success = False
        print("Pytest suite FAILED")
    else:
        print("Pytest suite PASSED")

    # Ensure synthetic files are present
    for filename, content in TEST_FILES.items():
        ensure_test_file(filename, content)

    print("\n=== Running Extensive Tests (Detailed DB preferred) ===")
    detailed_db_path = os.path.join("tmp", "J1939db.json")
    has_detailed_db = os.path.exists(detailed_db_path)

    for test in extensive_tests_config:
        name = test["name"]
        cmd = test["cmd"]

        # Check for missing run scripts
        if "run_da_integration.ps1" in cmd and not os.path.exists(
            "run_da_integration.ps1"
        ):
            print(f"--- Skipping Test: {name} (Missing run_da_integration.ps1) ---")
            continue

        # Adjust command and expectations if detailed DB is missing
        actual_cmd = cmd
        expected = test["expected"]
        if "--da-json tmp\\J1939db.json" in cmd and not has_detailed_db:
            actual_cmd = cmd.replace(" --da-json tmp\\J1939db.json", "")
            if "expected_fallback" in test:
                expected = test["expected_fallback"]

        if not run_test(name, actual_cmd, expected):
            # We don't necessarily fail the whole script if these fail,
            # but we report them.
            print(f"Notice: Extensive test {name} failed")

    if success:
        print("\nIN-TREE CORE TESTS PASSED")
        sys.exit(0)
    else:
        print("\nCORE TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
