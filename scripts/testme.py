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
            command, input=input_data, capture_output=True, text=True, check=True, timeout=300
        )
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error output:
{e.stderr}", file=sys.stderr)
        die(f"Command failed with exit code {e.returncode}")


def parse_decoding(output_text):
    ansi_escape = re.compile(r"\x1B(?:[@-Z\-_]|\[[0-?]*[ -/]*[@-~])")
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
            except (json.JSONDecodeError, IndexError) as e:
                print(f"Skipping malformed JSON in decoding: {e}", file=sys.stderr)
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


def setup_directories():
    """Create temporary and output directories."""
    tmp_dir = Path("tmp")
    official_dir = tmp_dir / "official"
    official_dir.mkdir(parents=True, exist_ok=True)
    output_base = Path("test_outputs")
    output_base.mkdir(exist_ok=True)
    return tmp_dir, official_dir, output_base


def create_json_das_from_official_xls(official_dir, python_exe):
    """Create JSON DAs from official XLS/XLSX files."""
    print("--- Phase 1: Creating Official JSON DAs ---")
    xls_files = list(official_dir.glob("*.xls")) + list(official_dir.glob("*.xlsx"))
    official_jsons = []
    for xls_file in xls_files:
        json_file = xls_file.parent / (xls_file.name + ".json")
        clean_json_file = xls_file.parent / (xls_file.stem + ".json")
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
        if json_file != clean_json_file:
            print(f"Generating {clean_json_file.name}...")
            cmd[-1] = str(clean_json_file)
            run_command(cmd)
        official_jsons.append(json_file)
    return official_jsons


def regression_sweep_xml_artifacts(official_jsons):
    """Regression sweep for XML artifacts."""
    print("
--- Phase 1.5: Regression Sweep for XML artifacts ---")
    artifact_found = False
    for json_file in official_jsons:
        with open(json_file, "r", encoding="utf-8") as f:
            content = f.read()
            matches = re.findall(r"_x[0-9a-fA-F]{4}_", content)
            if matches:
                print(
                    f"  [FAIL] Artifacts found in {json_file.name}: {len(matches)} occurrences."
                )
                artifact_found = True
            else:
                print(f"  [PASS] No artifacts in {json_file.name}")
    if not artifact_found:
        print("  All official JSONs are clean of _x000d_ artifacts.")


def regression_sweep_missing_j1939_bit_decodings(official_jsons):
    """Regression sweep for missing J1939BitDecodings."""
    print("
--- Phase 1.6: Regression Sweep for J1939BitDecodings ---")
    bit_decodings_missing = False
    for json_file in official_jsons:
        with open(json_file, "r", encoding="utf-8") as f:
            da = json.load(f)
            bit_decodings = da.get("J1939BitDecodings", {})
            if len(bit_decodings) == 0:
                print(f"  [FAIL] No J1939BitDecodings in {json_file.name}")
                bit_decodings_missing = True
            else:
                print(
                    f"  [PASS] {json_file.name} has {len(bit_decodings)} bit decodings"
                )
    if bit_decodings_missing:
        die("  FAILED: Some official JSONs are missing J1939BitDecodings entries.")
    elif official_jsons:
        print("  All official JSONs have J1939BitDecodings entries.")


def regression_sweep_name_mapping_dictionaries(official_jsons):
    """Regression sweep for NAME mapping dictionaries."""
    print("
--- Phase 1.7: Regression Sweep for NAME mapping dictionaries ---")
    name_maps_missing = False
    for json_file in official_jsons:
        with open(json_file, "r", encoding="utf-8") as f:
            da = json.load(f)
            missing_in_this_file = []
            for map_key in [
                "J1939Manufacturerdb",
                "J1939IndustryGroupdb",
                "J1939Functiondb",
                "J1939VehicleSystemdb",
            ]:
                if len(da.get(map_key, {})) == 0:
                    missing_in_this_file.append(map_key)
            if missing_in_this_file:
                print(
                    f"  [FAIL] {json_file.name} is missing populated maps: {', '.join(missing_in_this_file)}"
                )
                name_maps_missing = True
            else:
                mfr_count = len(da.get("J1939Manufacturerdb"))
                ig_count = len(da.get("J1939IndustryGroupdb"))
                func_count = len(da.get("J1939Functiondb"))
                vs_count = len(da.get("J1939VehicleSystemdb"))
                print(
                    f"  [PASS] {json_file.name} has NAME maps: Mfr={mfr_count}, IG={ig_count}, Func={func_count}, VS={vs_count}"
                )
    if name_maps_missing:
        print("  WARNING: Some official JSONs are missing some NAME mapping dictionaries.")
    elif official_jsons:
        print("  All official JSONs have populated NAME mapping dictionaries.")


def run_decodings(groups, log_files, argument_sets, output_base, python_exe):
    """Run decodings for different groups and argument sets."""
    print("
--- Phase 2: Running Decodings ---")
    results = {}
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

                    output_name = f"{group_name}_{log.stem}_{da_json.stem}_{args_slug}.txt"
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
    return results


def compare_decodings_within_groups(results):
    """Compare decodings within the same group."""
    print("
--- Phase 3: Intra-Group Comparison ---")
    for group_name, log_data in results.items():
        print(f"
===== GROUP: {group_name} =====")
        for log_name, arg_data in log_data.items():
            for args_slug, da_data in arg_data.items():
                da_names = sorted(da_data.keys())
                if len(da_names) < 2:
                    continue

                print(f"
LOG: {log_name} ({args_slug})")
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


def main():
    """Main function."""
    tmp_dir, official_dir, output_base = setup_directories()
    python_exe = sys.executable

    official_jsons = create_json_das_from_official_xls(official_dir, python_exe)
    regression_sweep_xml_artifacts(official_jsons)
    regression_sweep_missing_j1939_bit_decodings(official_jsons)
    regression_sweep_name_mapping_dictionaries(official_jsons)

    other_jsons = [f for f in tmp_dir.glob("*.json") if f.is_file()]
    groups = {"OFFICIAL": sorted(official_jsons), "OTHER": sorted(other_jsons)}
    log_files = sorted(list(tmp_dir.glob("*.log")) + list(Path("tests").glob("*.log")))
    argument_sets = [["--candata", "--link"]]

    results = run_decodings(groups, log_files, argument_sets, output_base, python_exe)
    compare_decodings_within_groups(results)

    print(f"
All decoding outputs saved in '{output_base}/'.")


if __name__ == "__main__":
    main()
