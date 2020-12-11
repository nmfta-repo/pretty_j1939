# `pretty_j1939`

python3 libs and scripts for pretty-printing J1939 candump logs.

This package can:
1. pretty-print J1939 traffic captured in candump logs AND
1. convert a J1939 Digital Annex (Excel) file into a JSON structure for use in the above 

## Some examples of pretty printing

*Formatted* content (one per line) next to candump data:

```bash
$ pretty_j1939.py --candata --format --transport example.candump.txt | head
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
$ pretty_j1939.py --candata --transport example.candump.txt | head
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

*Formatted* contents of the transport SPNs only.

```bash
$ pretty_j1939.py --format --no-link --transport example.candump.txt | head
{
    "Transport PGN": "AT1HI1(64920)",
    "Aftertreatment 1 Total Fuel Used": "227.5 [liters]",
    "Aftertreatment 1 DPF Average Time Between Active Regenerations": "173933 [Seconds]",
    "Aftertreatment 1 DPF Average Distance Between Active Regenerations": "1460.5 [m]"
}
{
    "Transport PGN": "AT1HI1(64920)",
    "Aftertreatment 1 Total Fuel Used": "227.5 [liters]",
    "Aftertreatment 1 DPF Average Time Between Active Regenerations": "173933 [Seconds]",
```

## HOWTO

First, obtain a copy of the digital annex, see https://www.sae.org/standards/content/j1939da_201907/ for details.

Then, use the `create_j1939db-json.py` script to convert that Digital Annex into a JSON file e.g.

```bash
create_j1939db-json.py -f tmp/J1939DA_201611.xls -w tmp/J1939DA_201611.json
```

Place the resulting JSON file at `J1939db.json` in your working directory and use the pretty-printing script e.g.

```bash
pretty_j1939.py example.candump.txt
```

The `pretty_j1939.py` script (and the `describer` in `pretty_j1939/parse.py` that it builds-on) has various levels of
verbosity available when describing J1939 traffic in candump logs:

```bash
usage: pretty_j1939.py [-h] [--candata] [--no-candata] [--pgn] [--no-pgn] [--spn] [--no-spn] [--transport] [--no-transport] [--link] [--no-link] [--include_na] [--no-include_na]
                       [--format] [--no-format]
                       candump

pretty-printing J1939 candump logs

positional arguments:
  candump          candump log

optional arguments:
  -h, --help       show this help message and exit
  --candata        print input can data
  --no-candata     (default)
  --pgn            (default) print source/destination/type description
  --no-pgn
  --spn            (default) print signals description
  --no-spn
  --transport      print details of transport-layer streams found
  --no-transport   (default)
  --link           (default) print details of link-layer frames found
  --no-link
  --include_na     include not-available (0xff) SPN values
  --no-include_na  (default)
  --format         format each structure (otherwise single-line)
  --no-format      (default)
```

## Installing

```bash
pip3 install pretty_j1939
```

## Notes on Digital Annex Sources

You need to obtain a J1939 Digital Annex from the SAE to create a JSON file that can be used by `pretty_j1939.py` see
https://www.sae.org/standards/content/j1939da_201907/ for details.

There are multiple releases; here are a couple notes to consider when purchasing your copy of the Digital Annex.
* the 201611 Digital Annex has fewer defined SPNs in it than the 201311 Digital Annex; at some point the owners of the
DA started migrating 'technical' SPNs (e.g. DMs) to other documents and out of the DA
* the 201311 Digital Annex has a couple bugs in it that the `create_j1939db-json.py` has workarounds for
* the `create_j1939db-json.py` can also handle the XLS Export from isobus.net by supplying multiple excel sheets
as input (with multiple `-f` arguments); however, the isobus.net definitions omit almost all of the commercial vehicle
SPNs and PGNs so the resulting `J1939db.json` file may not be of great use in examining candump captures from commercial
vehicles.

## Future Work

* port this functionality to the [python-j1939](https://github.com/milhead2/python-j1939) and 
[python-can](https://github.com/hardbyte/python-can/) projects
* support for discontiguous SPN fields
* default JSON database (of limited content) based on public information
* support for J1939 aspects not encoded in the Digital Annex (ever, or anymore) e.g. Address Claim, DMs

