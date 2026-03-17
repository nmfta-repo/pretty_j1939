from pretty_j1939 import describe


def test_reserved_abbreviation_case_insensitive():
    """Verify that both uppercase and lowercase long Reserved strings are abbreviated."""

    # Database with both cases
    db = {
        "J1939SATabledb": {
            "128": "reserved for future assignment by SAE but available for use by self configurable ECUs Used for dynamic address assignment",
            "129": "Reserved for future assignment by SAE but available for use by self configurable ECUs Used for dynamic address assignment",
        }
    }

    describer = describe.get_describer(da_json=db)

    # Test lowercase
    _, name128 = describer.da_describer.get_formatted_address_and_name(128)
    assert name128 == "Reserved"

    # Test uppercase
    _, name129 = describer.da_describer.get_formatted_address_and_name(129)
    assert name129 == "Reserved"


def test_global_abbreviation():
    """Verify that 'Global, applies to all' is abbreviated to 'Global'."""
    db = {"J1939SATabledb": {"255": "Global, applies to all"}}
    describer = describe.get_describer(da_json=db)
    # 255 is hardcoded in get_formatted_address_and_name as "All",
    # but _clean_name still handles the string if it appeared elsewhere.
    assert describer.da_describer._clean_name("Global, applies to all") == "Global"
