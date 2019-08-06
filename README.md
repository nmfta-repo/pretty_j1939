# `pretty_j1939`

python3 libs and scripts for pretty-printing J1939 candump logs.

This package can:
1. pretty-print J1939 traffic captured in candump logs AND
1. convert a J1939 Digital Annex (Excel) file into a JSON structure for use in the above 

## HOWTO

First, obtain a copy of the digital annex, see http://subs.sae.org/j1939_dl/ for details.

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
usage: pretty_j1939.py [-h] [--candata [CANDATA]] [--pgn [PGN]] [--spn [SPN]]
                       [--transport [TRANSPORT]] [--link [LINK]]
                       [--include-na [INCLUDE_NA]] [--format [FORMAT]]
                       candump

pretty-printing J1939 candump logs

positional arguments:
  candump               candump log

optional arguments:
  -h, --help            show this help message and exit
  --candata [CANDATA]   print input can data
  --pgn [PGN]           print source/destination/type description
  --spn [SPN]           print signals description
  --transport [TRANSPORT]
                        print details of transport-layer streams found
  --link [LINK]         print details of link-layer frames found
  --include-na [INCLUDE_NA]
                        inlude not-available (0xff) SPN values
  --format [FORMAT]     format each structure (otherwise single-line)
```

## Installing

pip3 install pretty_j1939

## Notes on Digital Annex Sources

You need to obtain a J1939 Digital Annex from the SAE to create a JSON file that can be used by `pretty_j1939.py` see
http://subs.sae.org/j1939_dl/ for details.

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

