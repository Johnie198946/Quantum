from scripts.check_gateway_bypass import scan


def test_gateway_authority_bypass_scan_is_zero():
    assert scan() == []
