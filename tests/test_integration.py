#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#
import subprocess
import sys
import time
import os
import signal


def run_with_timeout(command, timeout_sec):
    print(f"Running: {command}")
    process = subprocess.Popen(command, shell=True)
    try:
        process.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        print(
            f"Command timed out after {timeout_sec}s (as expected for infinite processes). Killing..."
        )
        # On Windows, terminate() might not be enough if it's a shell process
        process.terminate()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
    except Exception as e:
        print(f"Error running command: {e}")

    return process.returncode


def ensure_candump_log_exists(filename):
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        print(f"'{filename}' missing or empty. Creating mock data.")
        with open(filename, "w") as f:
            f.write("(1543509533.000838) can0 10FDA300#FFFF07FFFFFFFFFF\n")
            f.write("(1543509533.000915) can0 18FEE000#FFFFFFFFB05C6800\n")
            f.write("(1543509533.001145) can0 0CF00400#207D87481400F087\n")
    else:
        print(f"'{filename}' exists and has data.")


def ensure_truckdevil_log_exists(filename):
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        print(f"'{filename}' missing or empty. Creating mock data.")
        with open(filename, "w") as f:
            f.write(
                "(0.001232) 18F0090B    06 F009 0B --> FF [0008] FFFFFFFFFFFFFFFF\n"
            )
            f.write(
                "(0.002661) 18F0010B    06 F001 0B --> FF [0008] C0FFF0FFFF400B3F\n"
            )
    else:
        print(f"'{filename}' exists and has data.")


def run_verification(command):
    print(f"Verifying: {command}")
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"FAILED. Return code: {result.returncode}")
        print("Stderr:", result.stderr)
    else:
        print("SUCCESS.")
        print("Output snippet:", result.stdout[:200].replace("\n", " ") + "...")
    print("-" * 20)


def main():
    print("=== Integration Test: multiple log formats & pretty_j1939 ===")

    log_file = "tests/candump.log"
    ensure_candump_log_exists(log_file)

    td_log_file = "tests/truckdevil-forcompare.txt"
    ensure_truckdevil_log_exists(td_log_file)

    # 4. Verify pretty_j1939 invocation
    print("\n[Step 4] Verifying pretty_j1939 with standard candump...")
    cmd_basic = f"pretty_j1939 {log_file}"
    run_verification(cmd_basic)

    print("\n[Step 5] Verifying pretty_j1939 with TruckDevil format...")
    cmd_td = f"pretty_j1939 {td_log_file}"
    run_verification(cmd_td)

    print("\nIntegration test complete.")


if __name__ == "__main__":
    main()
