# 0.0.3

* tested on J1939DA_201311.xls, J1939DA_201611.xls, J1939DA_201910.xls, and J1939DA_DEC2020.xls
* fixed incorrectly dropping almost all multi byte SPNs thank you @s5y3XZpGvQPApqR
* can read from stdin with '-' argument now
* expands source addresses in DAs
* fixed module collision by moving scripts into package and using entry points
* re-introduced `pretty_j1939.parse` for backward compatibility and better code structure
* fixed `get_spn_start_bit` in `create_j1939db_json.py` to handle mixed delimiters (comma and dash)
* added support for 'N/A' in PGN and SPN fields in `create_j1939db_json.py` (Fixes #33)
* updated `bitstring.ConstBitArray` to `bitstring.Bits` for compatibility with newer versions (Fixes #34)

# 0.0.2

* support for non-contiguous SPNs (thanks @j4l)
* can describe SPNs in transport layer in real-time (as their bytes are received) (thanks @j4l)
* correctly reassembles  RTS-CTS transport sessions as well (thanks @j4l)
* can specify J1939 JSON db on command line (thanks @j4l)
* default to describing transport PGNs as first-class PGN
* default to omitting description of incomplete frames
