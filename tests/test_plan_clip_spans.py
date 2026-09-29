from audio_extractor import norm_token, plan_clip_spans, score_spans


def words_from(text):
    """One word per second, each 0.5 s long."""
    return [{"start": float(i), "end": i + 0.5, "raw": t, "norm": norm_token(t)}
            for i, t in enumerate(text.split())]


def numbers(spans):
    return [s["number"] for s in spans]


def test_simple_sequence():
    words = words_from("one a b two c d three e")
    spans = plan_clip_spans(words, 60000, 3000)
    assert numbers(spans) == ["1", "2", "3"]
    assert spans[0]["start_ms"] == 500 and spans[0]["end_ms"] == 3000
    assert spans[-1]["start_ms"] == 6500 and spans[-1]["end_ms"] == 7800  # "e" end + 300


def test_last_span_clamped_to_audio_length():
    spans = plan_clip_spans(words_from("one a"), 1600, 3000)
    assert spans[0]["end_ms"] == 1600


def test_repeated_number_does_not_make_empty_clip():
    words = words_from("one a two two b three c")
    spans = plan_clip_spans(words, 60000, 3000)
    assert numbers(spans) == ["1", "2", "3"]
    assert spans[1]["start_ms"] == 2500  # after the first "two"
    assert spans[1]["end_ms"] == 5000    # at "three"
    assert all(s["end_ms"] > s["start_ms"] for s in spans)


def test_false_jump_is_skipped():
    words = words_from("one a two b three c four d five e nine f nine g "
                       "six h seven i eight j nine k ten l")
    spans = plan_clip_spans(words, 60000, 3000)
    assert numbers(spans) == [str(n) for n in range(1, 11)]
    assert spans[4]["end_ms"] == words[14]["start"] * 1000  # "six", not the first "nine"
    assert spans[8]["position"] == 20  # the late "nine"


def test_genuine_skip_is_accepted():
    spans = plan_clip_spans(words_from("one a two b four c five d"), 60000, 3000)
    assert numbers(spans) == ["1", "2", "4", "5"]


def test_reset_discards_earlier_spans():
    spans = plan_clip_spans(words_from("2025 x one a two b"), 60000, 3000)
    assert numbers(spans) == ["1", "2"]


def test_span_carries_detection_details():
    span = plan_clip_spans(words_from("x one a"), 60000, 3000)[0]
    assert span["position"] == 1
    assert span["word"] == "one"
    assert span["match_type"] == "exact"
    assert span["score"] == 100


def span(n, start, end):
    return {"number": str(n), "start_ms": start, "end_ms": end}


def test_score_spans():
    assert score_spans([span(1, 0, 1000), span(2, 1000, 2000)]) == (True, 2)
    assert score_spans([span(1, 0, 1000), span(2, 1000, 1400)]) == (False, 1)
    assert score_spans([span(1, 0, 1000), span(3, 1000, 2000)]) == (False, 2)
    assert score_spans([span(1, 0, 1000), span(2, 1000, 1000)]) == (False, 1)
    assert score_spans([span(2, 0, 1000)]) == (False, 1)
    assert score_spans([]) == (False, 0)


def words_timed(spec):
    """Words from 'text@start-end' items with explicit seconds."""
    out = []
    for item in spec.split():
        text, times = item.split("@")
        start, end = (float(x) for x in times.split("-"))
        out.append({"start": start, "end": end, "raw": text, "norm": norm_token(text)})
    return out


LAST_PHRASE = ("eleven@9.0-9.5 a@9.5-9.8 twelve@10.0-10.5 inas@12.5-13.0 goje@13.0-13.6 "
               "shude@13.6-14.2 just@15.4-15.8 added@15.8-16.2")


def test_last_clip_ends_at_last_word_before_pause():
    spans = plan_clip_spans(words_timed(LAST_PHRASE), 60000, 3000)
    assert numbers(spans) == ["11", "12"]
    assert spans[-1]["end_ms"] == 14500


def test_gap_after_number_does_not_stop_walk():
    spans = plan_clip_spans(words_timed(LAST_PHRASE), 60000, 3000)
    assert spans[-1]["end_ms"] > 13000  # not cut before "inas"


def test_pause_of_exactly_one_second_continues():
    spans = plan_clip_spans(words_timed("twelve@10-10.5 a@12-12.5 b@13.5-14"), 60000, 3000)
    assert spans[-1]["end_ms"] == 14300


def test_last_clip_with_no_following_words_uses_clip_duration():
    spans = plan_clip_spans(words_timed("twelve@10-10.5"), 60000, 3000)
    assert spans[-1]["end_ms"] == 13500


def test_last_clip_end_clamped_to_audio_length():
    spans = plan_clip_spans(words_timed("twelve@10-10.5 a@11-14.9"), 15000, 3000)
    assert spans[-1]["end_ms"] == 15000


def test_non_last_span_end_unchanged():
    spans = plan_clip_spans(words_timed(LAST_PHRASE), 60000, 3000)
    assert spans[0]["end_ms"] == 10000  # start of "twelve"


def test_last_clip_lead_too_long_uses_clip_duration():
    spans = plan_clip_spans(words_timed("two@2-2.5 just@40-40.5 added@40.5-41"), 60000, 3000)
    assert spans[-1]["start_ms"] == 2500
    assert spans[-1]["end_ms"] == 2500 + 3000


def test_last_clip_lead_under_cap_still_walks():
    spans = plan_clip_spans(words_timed("two@2-2.5 just@7.4-7.9 added@7.9-8.5"), 60000, 3000)
    assert spans[-1]["end_ms"] == 8800


def test_score_spans_min_clip_is_one_second():
    assert score_spans([span(1, 0, 999)]) == (False, 0)
    assert score_spans([span(1, 0, 1000)]) == (True, 1)
