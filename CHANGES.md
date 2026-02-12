# 0.0.3

* added support for modern Digital Annex (.xlsx) files using `openpyxl`
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