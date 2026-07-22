from audio_extractor import word_forms_for, fuzzy_score_for


def test_word_forms_for_simple_number():
    assert word_forms_for(7) == ["seven"]


def test_word_forms_for_compound_number():
    assert word_forms_for(21) == ["twentyone", "twenty-one"]


def test_word_forms_for_out_of_range_returns_empty():
    assert word_forms_for(31) == []


def test_fuzzy_score_high_for_close_misspelling():
    assert fuzzy_score_for("sevven", 7) >= 85


def test_fuzzy_score_low_for_unrelated_word():
    assert fuzzy_score_for("banana", 7) < 85


def test_fuzzy_score_zero_for_short_token():
    assert fuzzy_score_for("hi", 7) == 0


def test_fuzzy_score_zero_for_digit_token():
    assert fuzzy_score_for("7", 7) == 0
