from scripts.check_governed_engineering_rules import violations


def test_gateway_engineering_rules_have_one_source_and_no_drift():
    assert violations() == []