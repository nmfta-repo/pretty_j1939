# `pretty_j1939`

python3 libs and scripts for pretty-printing J1939 candump logs.

This package can:
1. pretty-print J1939 traffic captured in candump logs AND
1. convert a J1939 Digital Annex (Excel) file into a JSON structure for use in the above. Support for both legacy `.xls` and modern `.xlsx` formats is included.


## Some examples of pretty printing

*Formatted* content (one per line) next to candump data:

```bash
$ pretty_j1939 --candata --format example.candump.txt | head
(1543509533.000838) can0 10FDA300#FFFF07FFFFFFFFFF ; {
                                                   ;     "DA": "All(255)",
                                                   ;     "PGN": "EEC6(64931)",
                                                   ;     "SA": "Engine #1(  0)",
                                                   ;     "Engine Variable Geometry Turbocharger Actuator #1": "2.8000000000000003 [%]"
                                                   ; }
(1543509533.000915) can0 18FEE000#FFFFFFFFB05C6800 ; {
                                                   ;     "DA": "All(255)",
                                                   ;     "PGN": "VD(65248)",
                                                   ;     "SA": "Engine #1(  0)",
```

Single-line contents next to candump data:

```bash
$ pretty_j1939 --candata example.candump.txt | head
(1543509533.000838) can0 10FDA300#FFFF07FFFFFFFFFF ; {"SA":"Engine #1(  0)","DA":"All(255)","PGN":"EEC6(64931)","Engine Variable Geometry Turbocharger Actuator #1":"2.8000000000000003 [%]"}
(1543509533.000915) can0 18FEE000#FFFFFFFFB05C6800 ; {"SA":"Engine #1(  0)","DA":"All(255)","PGN":"VD(65248)","Total Vehicle Distance":"854934.0 [m]"}
(1543509533.000991) can0 08FE6E0B#0000000000000000 ; {"SA":"Brakes - System Controller( 11)","DA":"All(255)","PGN":"HRW(65134)","Front Axle, Left Wheel Speed":"0.0 [kph]","Front axle, right wheel speed":"0.0 [kph]","Rear axle, left wheel speed":"0.0 [kph]","Rear axle, right wheel speed":"0.0 [kph]"}
(1543509533.001070) can0 18FDB255#FFFFFFFF0100FFFF ; {"SA":"Diesel Particulate Filter Controller( 85)","DA":"All(255)","PGN":"AT1IMG(64946)","Aftertreatment 1 Diesel Particulate Filter Differential Pressure":"0.1 [kPa]"}
(1543509533.001145) can0 0CF00400#207D87481400F087 ; {"SA":"Engine #1(  0)","DA":"All(255)","PGN":"EEC1(61444)","Engine Torque Mode":"2 (Unknown)","Actual Engine - Percent Torque (Fractional)":"0.0 [%]","Driver's Demand Engine - Percent Torque":"0 [%]","Actual Engine - Percent Torque":"10 [%]","Engine Speed":"649.0 [rpm]","Source Address of Controlling Device for Engine Control":"0 [SA]","Engine Demand - Percent Torque":"10 [%]"}
(1543509533.001220) can0 18FF4500#6D00FA00FF00006A ; {"SA":"Engine #1(  0)","DA":"All(255)","PGN":"PropB_45(65349)","Manufacturer Defined Usage (PropB_PDU2)":"0x6d00fa00ff00006a"}
(1543509533.001297) can0 18FEDF00#82FFFFFF7DE70300 ; {"SA":"Engine #1(  0)","DA":"All(255)","PGN":"EEC3(65247)","Nominal Friction - Percent Torque":"5 [%]","Estimated Engine Parasitic Losses - Percent Torque":"0 [%]","Aftertreatment 1 Exhaust Gas Mass Flow Rate":"199.8 [kg/h]","Aftertreatment 1 Intake Dew Point":"0 (00 - Not exceeded the dew point)","Aftertreatment 1 Exhaust Dew Point":"0 (00 - Not exceeded the dew point)","Aftertreatment 2 Intake Dew Point":"0 (00 - Not exceeded the dew point)","Aftertreatment 2 Exhaust Dew Point":"0 (00 - Not exceeded the dew point)"}
(1543509533.001372) can0 1CFE9200#FFFFFFFFFFFFFFFF ; {"SA":"Engine #1(  0)","DA":"All(255)","PGN":"EI1(65170)"}
(1543509533.001447) can0 18F00131#FFFFFF3F00FFFFFF ; {"SA":"Cab Controller - Primary( 49)","DA":"All(255)","PGN":"EBC1(61441)","Accelerator Interlock Switch":"0 (00 - Off)","Engine Retarder Selection":"0.0 [%]"}
(1543509533.001528) can0 18FEF131#F7FFFF07CCFFFFFF ; {"SA":"Cab Controller - Primary( 49)","DA":"All(255)","PGN":"CCVS1(65265)","Cruise Control Pause Switch":"1 (01 - On)","Cruise Control Active":"0 (00 - Cruise control switched off)","Cruise Control Enable Switch":"0 (00 - Cruise control disabled)","Brake Switch":"1 (01 - Brake pedal depressed)","Cruise Control Coast (Decelerate) Switch":"0 (00 - Cruise control activator not in the position \"coast\")","Cruise Control Accelerate Switch":"0 (00 - Cruise control activator not in the position \"accelerate\")"}
```

*Formatted* contents of complete frames only.

```bash
$ pretty_j1939 --format --no-link example.candump.txt | head
{
    "PGN": "AT1HI1(64920)",
    "Aftertreatment 1 Total Fuel Used": "227.5 [liters]",
    "Aftertreatment 1 DPF Average Time Between Active Regenerations": "173933 [Seconds]",
    "Aftertreatment 1 DPF Average Distance Between Active Regenerations": "1460.5 [m]"
}
{
    "PGN": "AT1HI1(64920)",
    "Aftertreatment 1 Total Fuel Used": "227.5 [liters]",
    "Aftertreatment 1 DPF Average Time Between Active Regenerations": "173933 [Seconds]",
```

The JSON output can be used as an input to [`jq`](https://stedolan.github.io/jq/manual/) to filter or format the decoded data. E.g. we can show only messages
from the "Brakes":

```sh
$ pretty_j1939 example.candump.txt --format | jq ". | select(.SA | contains(\"Brakes\"))"
{
  "PGN": "TSC1(0)",
  "DA": "Retarder - Engine( 15)",
  "SA": "Brakes - System Controller( 11)",
  "Engine Requested Speed/Speed Limit": "8031.875 [rpm]",
  "Engine Requested Torque/Torque Limit": "-125 [%]"
}
{
  "PGN": "TSC1(0)",
  "DA": "Retarder - Driveline( 16)",
  "SA": "Brakes - System Controller( 11)",
  "Engine Requested Speed/Speed Limit": "8031.875 [rpm]",
  "Engine Requested Torque/Torque Limit": "-125 [%]"
}
{
  "PGN": "TSC1(0)",
  "DA": "Retarder, Exhaust, Engine #1( 41)",
  "SA": "Brakes - System Controller( 11)",
  "Engine Requested Speed/Speed Limit": "8031.875 [rpm]",
  "Engine Requested Torque/Torque Limit": "-125 [%]"
}
{
  "PGN": "EBC1(61441)",
  "DA": "All(255)",
  "SA": "Brakes - System Controller( 11)",
  "ASR Brake Control Active": "0 (00 - ASR brake control passive but installed)",
  "Anti-Lock Braking (ABS) Active": "0 (00 - ABS passive but installed)",
[...]
```


## Installing

```bash
pip install pretty_j1939
```


## HOWTO

First, obtain a copy of the digital annex, see https://www.sae.org/standards/content/j1939da_201907/ for details.

Then, use the `create_j1939db-json` script to convert that Digital Annex into a JSON file. Both `.xls` and `.xlsx` files are supported:

```bash
create_j1939db-json -f tmp/J1939DA_DEC2020.xlsx -w tmp/J1939DA_DEC2020.json
```

### Storing and Using your J1939db.json

The tool looks for `J1939db.json` in the following locations (in order):
1.  The path provided via `--da-json`
2.  The current working directory
3.  The user's configuration directory:
    *   Windows: `%APPDATA%\pretty_j1939\J1939db.json`
    *   Linux/macOS: `~/.config/pretty_j1939/J1939db.json`
4.  Fallback: A default (very limited) J1939db.json bundled with the package. This .json is built from freely available information only.

To use your own database, simply place it in one of the search locations or specify it on the command line:

```bash
pretty_j1939 example.candump.txt --da-json my_full_db.json
```

### Network Summary

The tool can generate a Mermaid flowchart summary of all captured traffic. This is useful for visualizing the network topology and message flow between Controller Applications.

```bash
pretty_j1939 example.candump.txt --summary
```

The output is a JSON object with a `Summary` key containing the Mermaid syntax:

```json
{
    "Summary": "graph LR; N0[\"Engine #1(0)\"]; All[\"All(255)\"]; N0 -- EEC1(61444) --> All"
}
```

When using `--format`, the summary is printed in a multi-line, human-readable format:

```json
{
    "Summary": "graph LR
                   N0[\"Engine #1(0)\"]
                   All[\"All(255)\"]
                   N0 -- EEC1(61444) --> All"
}
```


### Advanced Filtering

In addition to support for the python-can bitmask filters, you can filter by J1939-specific fields:

- `--filter-pgn`: Filter by PGN (e.g., `61444` or `0xF004`).
- `--filter-sa`: Filter by Source Address.
- `--filter-da`: Filter by Destination Address.
- `--filter-ca`: Filter by Controller Application address (matches either SA or DA).

Example: Show all traffic involving address 11 (Brakes):

```bash
pretty_j1939 example.candump.txt --filter-ca 11
```


### Curses Viewer

For interactive, real-time analysis, the package includes a curses-based terminal viewer. It provides a live-updating table of J1939 messages with color-coded fields and detailed decoding.

Launch the viewer with the `viewer` subcommand:

```bash
pretty_j1939 viewer -i vcan0
```

Key features of the viewer:
- **Interactive Scrolling:** Use arrow keys or Page Up/Down to navigate the message history.
- **Bytes Column:** Displays the raw hex data alongside the decoded PGN and SA/DA information.
- **Real-time Decoding:** Messages are decoded instantly as they arrive, including transport reassembly.
- **Theming:** Supports multiple color themes (e.g., `darcula`, `monokai`, `synthwave`) via the `--theme` flag.
- **Search/Filter:** Press `/` to enter a search term (PGN label or address name) to filter the visible list in real-time.

You can also use the viewer on log files:

```bash
pretty_j1939 viewer example.candump.txt
```


### Highlighting

You can highlight specific messages based on J1939 fields. Highlighting overrides the default theme colors for the entire line with a high-contrast style.

- `--highlight-pgn`: Highlight by PGN.
- `--highlight-sa`: Highlight by Source Address.
- `--highlight-da`: Highlight by Destination Address.
- `--highlight-ca`: Highlight by Controller Application address.

Example: Highlight all engine-related traffic while showing everything:

```bash
pretty_j1939 example.candump.txt --highlight-ca 0 --color always
```

Note: Highlighting requires `--color` to be active (`always` or `auto` when outputting to a terminal).


### Live Capture

pretty-j1939 supports live CAN capture using `python-can`. You can specify the interface, channel, and bitrate:

```bash
pretty_j1939 -i cantact -c 0 -b 500000 --candata
```

Additional driver-specific arguments can be passed using `--key=value` syntax:

```bash
pretty_j1939 -i vector -c 1 --app-name=MyCanApp
```

The script also supports multiple log formats when reading from files or pipes, including standard `candump` and `python-can` logger output. It also accepts stdin using `-`:

```bash
tail -f /var/log/can.log | pretty_j1939 -
```


### CANdump Format

The `--candata` flag supports two modes:
- `--candata=raw` (or just `--candata`): Prints the input line exactly as provided.
- `--candata=candump`: Reformats the input into the standardized `(TIMESTAMP) INTERFACE ID#DATA` format, even when capturing live or reading from different log formats.


### Library Usage

The `pretty_j1939` library is designed for high-performance decoding and rendering in other Python projects.


#### Basic Usage

You can pass the CAN ID as an integer and the message data as either `bytes` or a `bitstring.Bits` object.

```python
import pretty_j1939.describe
import pretty_j1939.render

# 1. Initialize the describer (supports JSON paths or in-memory dicts)
describer = pretty_j1939.describe.get_describer(da_json="J1939db.json")

# 2. Initialize the high-performance renderer with an optional theme and describer for label resolution
theme = pretty_j1939.render.HighPerformanceRenderer.load_theme("darcula")
renderer = pretty_j1939.render.HighPerformanceRenderer(
    theme_dict=theme, 
    color_system="truecolor",
    da_describer=describer.da_describer
)

# 3. Describe and render a frame
can_id = 0x0CF00400
can_data = b"\x00\x41\xFF\x20\x48\x14\x00\xF0"

description = describer(can_data, can_id)
output = renderer.render(description, indent=True)
print(output)
```


#### Transport Reassembly (J1939 TP & ISO-TP)

The library automatically handles multi-packet reassembly for standard J1939 Transport Protocol (BAM and RTS-CTS). ISO-TP (PGN 0xDA00) reassembly works similarly and is enabled by default.

```python
# Feed sequential frames of a J1939 BAM session
# 1. Connection Management (BAM) - PGN 61444 (EEC1), 14 bytes, 2 packets
describer(b"\x20\x0E\x00\x02\xFF\x04\xF0\x00", 0x18ECFF00)
# 2. Data Transfer Packet 1
describer(b"\x01\x01\x02\x03\x04\x05\x06\x07", 0x18EBFF00)
# 3. Data Transfer Packet 2 (Final)
res = describer(b"\x02\x08\x09\x0A\x0B\x0C\x0D\x0E", 0x18EBFF00)

# 'res' will contain the decoded description of the reassembled PGN 61444
print(res["PGN"]) # "EEC1(61444)"
```


#### Generating a Network Summary

At the end of a session, you can generate a Mermaid flowchart representing the network activity.

```python
# 4. Generate and print a network summary
summary_data = describer.get_summary()
summary_output = renderer.render_summary(summary_data, indent=True)
print(summary_output)
```


## Testing

### Core Unit Tests

The package includes an in-tree unit test suite based on `pytest`. These tests verify core reassembly logic, PGN/SPN decoding, and CLI functionality using the bundled default database.

```bash
python -m pytest
```

### Integration Tests

The `verify_all.py` script runs the core `pytest` suite and then attempts additional "extensive" tests that require a full database at `tmp\J1939db.json` (although they should do a cursory job with the default database).

```bash
python verify_all.py
```

## Notes on Digital Annex Sources

You need to obtain a J1939 Digital Annex from the SAE to create a JSON file that can be used by `pretty_j1939` see
https://www.sae.org/standards/content/j1939da_201907/ for details.

There are multiple releases; here are a couple notes to consider when purchasing your copy of the Digital Annex.
* the 201611 Digital Annex has fewer defined SPNs in it than the 201311 Digital Annex; at some point the owners of the
DA started migrating 'technical' SPNs (e.g. DMs) to other documents and out of the DA
* the 201311 Digital Annex has a couple bugs in it that the `create_j1939db-json` has workarounds for
* the `create_j1939db-json` can also handle the XLS Export from isobus.net by supplying multiple excel sheets
as input (with multiple `-f` arguments); however, the isobus.net definitions omit almost all of the commercial vehicle
SPNs and PGNs so the resulting `J1939db.json` file may not be of great use in examining candump captures from commercial
vehicles.


## Future Work

* port this functionality to the [python-j1939](https://github.com/milhead2/python-j1939) and
[python-can](https://github.com/hardbyte/python-can/) projects
* integrate and/or move `create_j1939-db-json.py` to [canmatrix](https://canmatrix.readthedocs.io/en/latest/)

