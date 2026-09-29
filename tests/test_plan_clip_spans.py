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
    assert spans[-1]["start_ms"] == 6500 and spans[-1]["end_ms"] == 9500


def test_last_span_clamped_to_audio_length():
    spans = plan_clip_spans(words_from("one a"), 2000, 3000)
    assert spans[0]["end_ms"] == 2000


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
    assert score_spans([span(1, 0, 1000), span(2, 1000, 1300)]) == (True, 2)
    assert score_spans([span(1, 0, 1000), span(3, 1000, 2000)]) == (False, 2)
    assert score_spans([span(1, 0, 1000), span(2, 1000, 1000)]) == (False, 1)
    assert score_spans([span(2, 0, 1000)]) == (False, 1)
    assert score_spans([]) == (False, 0)
