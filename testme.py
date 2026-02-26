#!/usr/bin/env python3
import os
import sys
import subprocess
import glob
import json
from pathlib import Path
import re
from collections import defaultdict


def die(message):
    print(message, file=sys.stderr)
    sys.exit(1)


def run_command(command, input_data=None):
    try:
        result = subprocess.run(
            command, input=input_data, capture_output=True, text=True, check=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error output:\n{e.stderr}", file=sys.stderr)
        die(f"Command failed with exit code {e.returncode}")


def parse_decoding(output_text):
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    clean_text = ansi_escape.sub("", output_text)

    decoded_messages = []
    for line in clean_text.splitlines():
        if ";" in line:
            parts = line.split(";", 1)
            json_str = parts[1].strip()
            try:
                data = json.loads(json_str)
                if "PGN" in data:
                    decoded_messages.append(data)
            except (json.JSONDecodeError, IndexError):
                continue
    return decoded_messages


def normalize_value(v):
    """
    Normalizes decoded strings to treat equivalent units/labels as identical.
    """
    if not isinstance(v, str):
        return v

    # Treat [c] and [degc] as identical
    v = re.sub(r"\[c\]", "[degc]", v, flags=re.IGNORECASE)
    # Treat [kph] and [km/h] as identical
    v = re.sub(r"\[kph\]", "[km/h]", v, flags=re.IGNORECASE)
    # Standardize SA/source address labels
    v = re.sub(r"\[source address\]", "[SA]", v, flags=re.IGNORECASE)
    v = re.sub(r"\[sa\]", "[SA]", v)  # Case sensitive for [sa] vs [SA]

    return v


def compare_decodings(old_messages, new_messages):
    changes = {
        "pgn_label_changes": 0,
        "node_name_changes": 0,
        "spn_changes": 0,
        "new_fields": 0,
        "lost_fields": 0,
        "details": [],
    }

    for i, (old, new) in enumerate(zip(old_messages, new_messages)):
        msg_diffs = []
        if normalize_value(old.get("PGN")) != normalize_value(new.get("PGN")):
            changes["pgn_label_changes"] += 1
            msg_diffs.append(f"PGN: '{old.get('PGN')}' -> '{new.get('PGN')}'")
        if normalize_value(old.get("SA")) != normalize_value(new.get("SA")):
            changes["node_name_changes"] += 1
            msg_diffs.append(f"SA: '{old.get('SA')}' -> '{new.get('SA')}'")
        if normalize_value(old.get("DA")) != normalize_value(new.get("DA")):
            changes["node_name_changes"] += 1
            msg_diffs.append(f"DA: '{old.get('DA')}' -> '{new.get('DA')}'")

        old_keys = set(old.keys()) - {
            "PGN",
            "SA",
            "DA",
            "Bytes",
            "Transport PGN",
            "Summary",
        }
        new_keys = set(new.keys()) - {
            "PGN",
            "SA",
            "DA",
            "Bytes",
            "Transport PGN",
            "Summary",
        }

        added = new_keys - old_keys
        removed = old_keys - new_keys

        if added:
            changes["new_fields"] += len(added)
            msg_diffs.append(f"Added SPNs: {added}")
        if removed:
            changes["lost_fields"] += len(removed)
            msg_diffs.append(f"Removed SPNs: {removed}")

        for key in old_keys & new_keys:
            if normalize_value(old[key]) != normalize_value(new[key]):
                changes["spn_changes"] += 1
                msg_diffs.append(f"SPN '{key}': '{old[key]}' -> '{new[key]}'")

        if msg_diffs:
            changes["details"].append(f"Msg #{i}: " + " | ".join(msg_diffs))
    return changes


def main():
    tmp_dir = Path("tmp")
    official_dir = tmp_dir / "official"
    official_dir.mkdir(exist_ok=True)
    output_base = Path("test_outputs")
    output_base.mkdir(exist_ok=True)

    python_exe = sys.executable

    # Phase 1: Create JSON DAs from official XLS/XLSX
    # Avoid collisions by including extension in json name
    xls_files = list(official_dir.glob("*.xls")) + list(official_dir.glob("*.xlsx"))
    print("--- Phase 1: Creating Official JSON DAs ---")
    official_jsons = []
    for xls_file in xls_files:
        # Use filename with extension to avoid collision between J1939DA_DEC2020.xls and .xlsx
        json_file = xls_file.parent / (xls_file.name + ".json")
        cmd = [
            python_exe,
            "-m",
            "pretty_j1939.create_j1939db_json",
            "-f",
            str(xls_file),
            "-w",
            str(json_file),
        ]
        print(f"Generating {json_file.name}...")
        run_command(cmd)
        official_jsons.append(json_file)

    # Phase 1.5: Regression Sweep for _x000d_ artifacts
    print("\n--- Phase 1.5: Regression Sweep for _x000d_ artifacts ---")
    artifact_found = False
    for json_file in official_jsons:
        with open(json_file, "r", encoding="utf-8") as f:
            content = f.read()
            # Case-insensitive search for _x000d_
            matches = re.findall(r"_x000[dD]_", content)
            if matches:
                print(
                    f"  [FAIL] Artifacts found in {json_file.name}: {len(matches)} occurrences."
                )
                artifact_found = True
            else:
                print(f"  [PASS] No artifacts in {json_file.name}")

    if not artifact_found:
        print("  All official JSONs are clean of _x000d_ artifacts.")

    # Find other JSON DAs in tmp/
    other_jsons = [f for f in tmp_dir.glob("*.json") if f.is_file()]

    groups = {"OFFICIAL": sorted(official_jsons), "OTHER": sorted(other_jsons)}

    log_files = sorted(list(tmp_dir.glob("*.log")) + list(Path("tests").glob("*.log")))
    argument_sets = [["--candata", "--link"]]

    results = {}  # group -> log -> args_slug -> da_name -> messages

    print("\n--- Phase 2: Running Decodings ---")
    for group_name, da_list in groups.items():
        if not da_list:
            continue
        results[group_name] = {}
        for da_json in da_list:
            print(f"Using {group_name} DA: {da_json.name}")
            for args in argument_sets:
                args_slug = "_".join(args).replace("--", "")
                for log in log_files:
                    if log.name not in results[group_name]:
                        results[group_name][log.name] = {}
                    if args_slug not in results[group_name][log.name]:
                        results[group_name][log.name][args_slug] = {}

                    output_name = (
                        f"{group_name}_{log.stem}_{da_json.stem}_{args_slug}.txt"
                    )
                    output_path = output_base / output_name

                    cmd = (
                        [python_exe, "-m", "pretty_j1939"]
                        + args
                        + ["--da-json", str(da_json), str(log)]
                    )
                    res = run_command(cmd)

                    with open(output_path, "w", encoding="utf-8") as f:
                        f.write(res.stdout)

                    msgs = parse_decoding(res.stdout)
                    results[group_name][log.name][args_slug][da_json.name] = msgs

    # Phase 3: Detailed Comparison WITHIN Groups
    print("\n--- Phase 3: Intra-Group Comparison ---")
    for group_name, log_data in results.items():
        print(f"\n===== GROUP: {group_name} =====")
        for log_name, arg_data in log_data.items():
            for args_slug, da_data in arg_data.items():
                da_names = sorted(da_data.keys())
                if len(da_names) < 2:
                    continue

                print(f"\nLOG: {log_name} ({args_slug})")
                for i in range(len(da_names) - 1):
                    old_da = da_names[i]
                    new_da = da_names[i + 1]

                    diffs = compare_decodings(da_data[old_da], da_data[new_da])

                    if any(
                        [
                            diffs["pgn_label_changes"],
                            diffs["node_name_changes"],
                            diffs["spn_changes"],
                            diffs["new_fields"],
                            diffs["lost_fields"],
                        ]
                    ):
                        print(f"  {old_da} -> {new_da}:")
                        if diffs["pgn_label_changes"]:
                            print(
                                f"    - PGN Labels changed: {diffs['pgn_label_changes']}"
                            )
                        if diffs["node_name_changes"]:
                            print(
                                f"    - Node Names changed: {diffs['node_name_changes']}"
                            )
                        if diffs["spn_changes"]:
                            print(f"    - SPN Values changed: {diffs['spn_changes']}")
                        if diffs["new_fields"]:
                            print(f"    - New SPNs added: {diffs['new_fields']}")
                        if diffs["lost_fields"]:
                            print(f"    - SPNs lost: {diffs['lost_fields']}")

                        for detail in diffs["details"][:3]:
                            print(f"      {detail}")
                        if len(diffs["details"]) > 3:
                            print(
                                f"      ... and {len(diffs['details']) - 3} more differences."
                            )
                    else:
                        print(f"  {old_da} -> {new_da}: [STABLE]")

    print(f"\nAll decoding outputs saved in '{output_base}/'.")


if __name__ == "__main__":
    main()
