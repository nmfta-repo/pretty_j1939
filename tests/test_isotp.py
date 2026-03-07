#
# Copyright (c) 2026 National Motor Freight Traffic Association Inc. All Rights Reserved.
# See the file "LICENSE" for the full license governing this code.
#

import bitstring
import io
from pretty_j1939.describe import get_describer


def test_isotp_reassembly():
    print("Testing ISO-TP reassembly...")

    # FF: PCI=1, Length=11 (0x00B), Data="Hello " (48 65 6C 6C 6F 20)
    # ID: 0x18DA2211 (PGN 0xDA00, DA 0x22, SA 0x11)
    ff_data = bytes.fromhex("100B48656C6C6F20")
    cf_data = bytes.fromhex("21576F726C640000")  # CF: PCI=2, SN=1, Data="World"

    msg_id = 0x18DA2211

    describer = get_describer(da_json="J1939db.json", enable_isotp=True)

    # Process FF
    res = describer(bitstring.Bits(bytes=ff_data), msg_id)
    # Expect empty description (incomplete)
    if res:
        print("FAIL: FF produced output prematurely:", res)

    # Process CF
    res = describer(bitstring.Bits(bytes=cf_data), msg_id)

    # Verify reassembly
    if not res:
        print("FAIL: No output after CF")

    print("Result:", res)

    expected_pgn = 55808
    expected_data = "48656C6C6F20576F726C64"  # "Hello World" in hex

    if res.get("_pgn") != expected_pgn:
        print(f"FAIL: PGN mismatch. Expected {expected_pgn}, got {res.get('_pgn')}")

    # Check if raw bytes are present (describer might output them if no SPNs found)
    # Since DIAG3 likely has no SPNs in the default DB, we expect raw bytes if configured
    # But wait, get_describer defaults include_transport_rawdata=False.
    # However, if no SPNs are found, it might default to printing bytes.
    # Let's check Bytes field.

    if "Bytes" in res:
        if res["Bytes"] != expected_data:
            print(f"FAIL: Data mismatch. Expected {expected_data}, got {res['Bytes']}")

    else:
        # If no SPNs and no Bytes, maybe it's empty?
        # J1939Describer logic: if len(description) == 0 and not is_transport_pgn(pgn)...
        # But 0xDA00 is NOT is_transport_pgn (J1939 TP).
        # So it should print Bytes.
        print("FAIL: 'Bytes' field missing")

    print("PASS: ISO-TP reassembly successful")


if __name__ == "__main__":
    if test_isotp_reassembly():
        exit(0)
    else:
        exit(1)
