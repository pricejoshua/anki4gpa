from audio_extractor import word_forms_for


def test_word_forms_for_simple_number():
    assert word_forms_for(7) == ["seven"]


def test_word_forms_for_compound_number():
    assert word_forms_for(21) == ["twentyone", "twenty-one"]


def test_word_forms_for_out_of_range_returns_empty():
    assert word_forms_for(31) == []
