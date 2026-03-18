# 0.0.5
* added a curses-based terminal viewer for real-time
* expanded support for various logfile formats (including candump with timestamps)
* track J1939 NAMEs and label SA/DA names dynamically based on Address Claimed messages
* fixed warnings and maintained compatibility with older database schemas
* improved Not Available (NA) and Error indicator detection for all SPN lengths
* improved decoding of edge cases in ISO-TP and J1939 Transport Layer reassembly
* expanded default J1939 database with more PGNs and SPNs
* optimized rendering performance with `HighPerformanceRenderer`
* automated summary generation for large logfiles
* added Digital Annex (DA) parsing support to `create_j1939db_json.py`
* extensive codebase refactoring and significant increase in test coverage

# 0.0.4
* restore support for old J1939db.json schema

# 0.0.3

* Improved error handling for invalid input
* Enhanced performance
* support for DM1, TP, NAME, ISO-TP
* implemented a public-domain default J1939 database based on community-sourced information.
* support for --filter-* and --highlight-*
* support for --theme
* added direct live CAN capture support via `python-can` (using `-i`, `-c`, `-b`)
* added colorized JSON output support using `pygments` (via `--color`)
* fixed live streaming/piping support by enabling line-buffered input and output flushing
* optimized `.xlsx` processing performance with row caching
* improved header detection in Digital Annexes (content-aware instead of fixed indices)
* improved unknown PGN description to include hex value and PDU format (Fixes #20)
* fixed PGN extraction to include Data Page (DP) and Extended Data Page (EDP) bits
* ensured PDU1 messages preserve destination address (DA)
* restructured package with relative imports to avoid module shadowing (Fixes #35)
* tested on J1939DA_201311.xls, J1939DA_201611.xls, J1939DA_201910.xls, and J1939DA_DEC2020.xlsx

# 0.0.2

* support for non-contiguous SPNs (thanks @j4l)
* can describe SPNs in transport layer in real-time (as their bytes are received) (thanks @j4l)
* correctly reassembles  RTS-CTS transport sessions as well (thanks @j4l)
* can specify J1939 JSON db on command line (thanks @j4l)
* default to describing transport PGNs as first-class PGN
* default to omitting description of incomplete frames
