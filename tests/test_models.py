from models import PowerEnum


def test_power_name_aliases():
    # Test all aliases defined in _POWER_ALIASES
    assert PowerEnum("UK") == PowerEnum.ENGLAND
    assert PowerEnum("BRIT") == PowerEnum.ENGLAND
    assert PowerEnum("EGMANY") == PowerEnum.GERMANY
    assert PowerEnum("GERMAN") == PowerEnum.GERMANY

    # Test direct enum values (no alias needed)
    assert PowerEnum("AUSTRIA") == PowerEnum.AUSTRIA
    assert PowerEnum("FRANCE") == PowerEnum.FRANCE

    # Test case insensitivity
    assert PowerEnum("france") == PowerEnum.FRANCE
    assert PowerEnum("iTaLy") == PowerEnum.ITALY

    # Test with whitespace
    assert PowerEnum(" RUSSIA ") == PowerEnum.RUSSIA
    assert PowerEnum("TURKEY  ") == PowerEnum.TURKEY
