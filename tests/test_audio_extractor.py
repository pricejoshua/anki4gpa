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


from audio_extractor import detect_number_at, norm_token


def _word(raw, start=0.0, end=0.5):
    return {'start': start, 'end': end, 'raw': raw, 'norm': norm_token(raw)}


def test_exact_match_word_number():
    words = [_word("seven")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == ("7", 1, "exact", 100)


def test_exact_match_digit_token():
    words = [_word("7")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == ("7", 1, "exact", 100)


def test_exact_match_number_prefix():
    words = [_word("number"), _word("seven")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == ("7", 2, "exact", 100)


def test_misrecognition_map_hit_when_expected():
    # "won" is a known misrecognition of "one", and last_accepted_number=0
    # means "1" is the expected-next number.
    words = [_word("won")]
    result = detect_number_at(words, 0, last_accepted_number=0)
    assert result == ("1", 1, "misrecognition", 100)


def test_misrecognition_map_gated_by_expected_number():
    # "for" is a known misrecognition of "four", but the sequence here is
    # expecting "7" next (last_accepted_number=6) - "for" must NOT be
    # treated as a number, since it's also just a common English word.
    words = [_word("for")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == (None, 0, None, None)


def test_misrecognition_map_hit_for_common_word_when_expected():
    # Same token "for", but now the sequence is expecting "4" next
    # (last_accepted_number=3), so the misrecognition should fire.
    words = [_word("for")]
    result = detect_number_at(words, 0, last_accepted_number=3)
    assert result == ("4", 1, "misrecognition", 100)


def test_fuzzy_match_accepts_near_miss_spelling():
    # "sevven" is a garbled spelling of "seven"; last_accepted_number=6
    # means "7" is the expected-next number.
    words = [_word("sevven")]
    num, skip, match_type, score = detect_number_at(words, 0, last_accepted_number=6)
    assert num == "7"
    assert skip == 1
    assert match_type == "fuzzy"
    assert score >= 85


def test_fuzzy_match_rejects_unrelated_word():
    words = [_word("banana")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == (None, 0, None, None)


def test_fuzzy_reset_requires_higher_threshold_than_advance():
    # "onne" scores ~85.7 against "one" - enough to pass the advance
    # threshold (85) if "1" were the expected-next number, but here
    # last_accepted_number=6 (expecting "7", which "onne" doesn't
    # resemble), so this exercises the reset-to-1 fuzzy path, which
    # requires a stricter threshold (92) given how destructive a false
    # reset is (it deletes every clip accepted so far).
    words = [_word("onne")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == (None, 0, None, None)
