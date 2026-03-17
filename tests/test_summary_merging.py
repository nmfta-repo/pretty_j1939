import bitstring
from pretty_j1939 import describe
from pretty_j1939.render import HighPerformanceRenderer


def test_summary_merging_and_abbreviation():
    """Verify that double nodes are merged and long descriptions are abbreviated in summaries."""

    # Minimal database with the problematic long SA 144 description
    db = {
        "J1939SATabledb": {
            "144": "Reserved for future assignment by SAE but available for use by self configurable ECUs Used for dynamic address assignment"
        },
        "J1939PGNdb": {
            "59904": {
                "Label": "Request",
                "Name": "Request",
                "SPNs": [2540],
                "SPNStartBits": [0],
            },
            "60928": {
                "Label": "Address Claimed",
                "Name": "Address Claimed",
                "SPNs": [],
                "SPNStartBits": [],
            },
        },
        "J1939SPNdb": {
            "2540": {
                "Name": "Requested PGN",
                "Units": "Request Dependent",
                "SPNLength": 24,
                "Resolution": 1,
                "Offset": 0,
                "OperationalLow": 0,
                "OperationalHigh": 16777215,
            }
        },
        "J1939IndustryGroupdb": {"0": "Global, applies to all"},
        "J1939Functiondb": {"0_0_144": "Throttle"},
        "J1939Manufacturerdb": {"630": "Unknown Manufacturer 630"},
    }

    describer = describe.get_describer(da_json=db)

    # 1. Message from SA 144 before address claim (PGN 59904 Request)
    msg1_id = 0x18EAFF90  # Priority 6, PGN 59904, DA 255, SA 144
    msg1_data = bitstring.Bits(hex="00EE00")  # Requesting PGN 60928 (Address Claimed)
    describer(msg1_data, msg1_id)

    # 2. Address Claimed message from SA 144 (PGN 60928)
    # Construct a NAME payload: IG=0, Function=144, Mfr=630, ID=1
    name_val = (0 << 60) | (144 << 40) | (630 << 21) | (1 << 0)
    msg2_id = 0x18EEFF90
    msg2_data = bitstring.Bits(uint=name_val, length=64).bytes[::-1]  # Little Endian
    describer(msg2_data, msg2_id)

    # 3. Message after address claim
    describer(msg1_data, msg1_id)

    # Get summary
    summary_data = describer.get_summary()

    # There should only be ONE entry for SA 144 -> DA 255
    # The key in final_summary is (sa, da, sa_name, da_name)
    # Since DA 255 (All) has None as name in the merged summary:
    keys = list(summary_data.keys())
    # We expect only one key for (144, 255, ...)
    sa144_keys = [k for k in keys if k[0] == 144]
    assert len(sa144_keys) == 1, f"Should have merged nodes, but got: {sa144_keys}"

    best_name = sa144_keys[0][2]
    # Check for abbreviation: "Global, applies to all" -> "[Global]"
    assert "[Global]" in best_name
    assert "Global, applies to all" not in best_name

    # Check for abbreviation: "Reserved for future assignment..." -> "Reserved"
    # In DADescriber.get_formatted_address_and_name, if static_name is not in dynamic_name, it joins them.
    # static_name is the long Reserved string, which should be cleaned to "Reserved".
    # dynamic_name is the decoded NAME, which should also be cleaned.
    assert "Reserved" in best_name
    assert "future assignment" not in best_name

    # Render to check final Mermaid output
    # Use color_system=None to avoid ANSI escape codes in tests
    renderer = HighPerformanceRenderer(
        {}, color_system=None, da_describer=describer.da_describer
    )
    json_output = renderer.render_summary(summary_data, indent=True)
    # Parse the JSON since color_system=None now returns JSON
    import json
    summary_obj = json.loads(json_output)
    graph = summary_obj["Summary"]

    # The node ID should be derived from the cleaned name
    # "Reserved [[Global] Throttle [Unknown Manufacturer 630] ID:1]" -> slug starts with Reserved
    assert "N144_Reserved" in graph
    # Check that there is only one N144 node definition
    assert graph.count('N144_Reserved["') == 1
    # Check that "All" is still there
    assert 'All["All(255)"]' in graph


if __name__ == "__main__":
    test_summary_merging_and_abbreviation()
