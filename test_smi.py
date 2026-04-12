import calculate_tama


def test_calculate_smi_mm2_to_cm2_and_height_squared():
    # 10_000 mm² = 100 cm²; bei 2.0 m => 100 / 4 = 25
    assert calculate_tama.calculate_smi(10_000, 2.0) == 25.0


def test_calculate_smi_handles_missing_or_invalid_height():
    assert calculate_tama.calculate_smi(1000, None) is None
    assert calculate_tama.calculate_smi(1000, 0) is None
    assert calculate_tama.calculate_smi(None, 1.7) is None


def test_parse_sex():
    assert calculate_tama.parse_sex('F') == 'F'
    assert calculate_tama.parse_sex('f') == 'F'
    assert calculate_tama.parse_sex('M') == 'M'
    assert calculate_tama.parse_sex('') is None
    assert calculate_tama.parse_sex(None) is None
    assert calculate_tama.parse_sex('x') is None

