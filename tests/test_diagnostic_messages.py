import bitstring
import pytest
from pretty_j1939.core.describe import get_describer


def test_dm1_dm2_parsing_single_packet():
    """Verify that both DM1 and DM2 are parsed correctly when in a single packet."""
    describer = get_describer()

    # DM1 (Active DTCs) - PGN 65226 (0xFECA)
    # Data: 40 FF 5B 00 03 01 FF FF
    # MIL On, other lamps off. DTC 1: SPN 91, FMI 3, OC 1.
    dm1_id = 0x18FECA00
    dm1_data = bitstring.Bits(hex="40FF5B000301FFFF")
    desc1 = describer(dm1_data, dm1_id)
    assert desc1["PGN"] == "DM1(65226)"
    assert desc1["Malfunction Indicator Lamp Status"] == "On"
    assert "SPN 91" in desc1["DTC 1"]
    assert "FMI 3" in desc1["DTC 1"]

    # DM2 (Previously Active DTCs) - PGN 65227 (0xFECB)
    # Same data structure
    dm2_id = 0x18FECB00
    dm2_data = bitstring.Bits(hex="00FF5B000301FFFF")  # MIL Off
    desc2 = describer(dm2_data, dm2_id)
    assert desc2["PGN"] == "DM2(65227)"
    assert desc2["Malfunction Indicator Lamp Status"] == "Off"
    assert "SPN 91" in desc2["DTC 1"]
    assert "FMI 3" in desc2["DTC 1"]


def test_dm1_multi_packet_reassembly():
    """Verify that multi-packet DM1 (via BAM) is parsed correctly."""
    describer = get_describer(real_time=False)  # Wait for full reassembly

    # 4 DTCs = 2 bytes (lamps) + 4 * 4 bytes (DTCs) = 18 bytes.
    # Needs 3 packets (7 bytes each in DT).
    # Data:
    # 00 FF (lamps)
    # 5B 00 03 01 (DTC 1: SPN 91, FMI 3, OC 1)
    # 5C 00 04 02 (DTC 2: SPN 92, FMI 4, OC 2)
    # 5D 00 05 03 (DTC 3: SPN 93, FMI 5, OC 3)
    # 5E 00 06 04 (DTC 4: SPN 94, FMI 6, OC 4)
    full_payload = bitstring.Bits(hex="00FF5B0003015C0004025D0005035E000604")

    # TP.CM_BAM: 18ECFF00#20120003FFCAFE00 (18 bytes, 3 packets, PGN 65226)
    # TP.DT 1:   18EBFF00#0100FF5B0003015C
    # TP.DT 2:   18EBFF00#020004025D000503
    # TP.DT 3:   18EBFF00#035E000604FFFFFF

    describer(bitstring.Bits(hex="20120003FFCAFE00"), 0x18ECFF00)
    describer(bitstring.Bits(hex="0100FF5B0003015C"), 0x18EBFF00)
    describer(bitstring.Bits(hex="020004025D000503"), 0x18EBFF00)
    result = describer(bitstring.Bits(hex="035E000604FFFFFF"), 0x18EBFF00)

    assert result["PGN"] == "DM1(65226)"
    assert "DTC 1" in result
    assert "DTC 2" in result
    assert "DTC 3" in result
    assert "DTC 4" in result
    assert "SPN 94" in result["DTC 4"]
