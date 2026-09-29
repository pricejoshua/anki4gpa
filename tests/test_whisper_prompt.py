import os
from types import SimpleNamespace

import pytest
from pydub import AudioSegment

import audio_extractor
from audio_extractor import NUMBER_PROMPT


def test_number_prompt_shape():
    assert NUMBER_PROMPT.startswith("One, two, three")
    assert "nine" in NUMBER_PROMPT
    assert "twenty-one" in NUMBER_PROMPT
    assert NUMBER_PROMPT.endswith("thirty.")
    assert len(NUMBER_PROMPT.split(", ")) == 30


@pytest.mark.parametrize("prompt", [NUMBER_PROMPT, None], ids=["prompt", "no-prompt"])
def test_local_backend_passes_initial_prompt(monkeypatch, prompt):
    faster_whisper = pytest.importorskip("faster_whisper")
    calls = {}

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, audio_path, **kwargs):
            calls.update(kwargs)
            return [], SimpleNamespace(language="en", duration=0)

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    audio_extractor.transcribe_with_local_whisper("unused.wav", prompt=prompt)
    assert calls["initial_prompt"] == prompt


@pytest.mark.parametrize("prompt", [NUMBER_PROMPT, None], ids=["prompt", "no-prompt"])
@pytest.mark.parametrize("module_name,class_name,func_name", [
    ("groq", "Groq", "transcribe_with_groq"),
    ("openai", "OpenAI", "transcribe_with_openai"),
])
def test_api_backends_pass_prompt(monkeypatch, tmp_path, module_name, class_name, func_name, prompt):
    module = pytest.importorskip(module_name)
    calls = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            def create(**kw):
                calls.update(kw)
                return SimpleNamespace(words=[], text="")
            self.audio = SimpleNamespace(transcriptions=SimpleNamespace(create=create))

    monkeypatch.setattr(module, class_name, FakeClient)
    audio_path = tmp_path / "a.wav"
    audio_path.write_bytes(b"x")
    getattr(audio_extractor, func_name)(str(audio_path), api_key="k", prompt=prompt)
    if prompt is None:
        assert "prompt" not in calls
    else:
        assert calls["prompt"] == prompt


def w(raw, start):
    return {"start": start, "end": start + 0.5, "raw": raw, "norm": audio_extractor.norm_token(raw)}


def words_from(text):
    return [w(t, float(i)) for i, t in enumerate(text.split())]


def run_extract(monkeypatch, tmp_path, *transcripts, **kwargs):
    """Run extract_audio_clips with the local transcriber returning each
    transcript in turn; returns (count, debug_info, prompts seen, files)."""
    prompts = []
    remaining = list(transcripts)

    def fake_transcribe(*args, prompt=None, **kwargs):
        prompts.append(prompt)
        words = remaining.pop(0)
        return words, " ".join(x["raw"] for x in words), {"language": "en", "duration": 0}

    monkeypatch.setattr(audio_extractor, "transcribe_with_local_whisper", fake_transcribe)
    wav = tmp_path / "in.wav"
    AudioSegment.silent(20000).export(str(wav), format="wav")
    out_dir = tmp_path / "out"
    count, debug_info = audio_extractor.extract_audio_clips(str(wav), str(out_dir), debug=True, **kwargs)
    return count, debug_info, prompts, sorted(os.listdir(out_dir))


def test_clip_count_after_sequence_reset(monkeypatch, tmp_path):
    count, _, _, files = run_extract(monkeypatch, tmp_path, words_from("2025 x one apple two pear"))
    assert count == 2
    assert files == ["1.mp3", "2.mp3"]


def test_complete_prompted_pass_is_used_alone(monkeypatch, tmp_path):
    count, debug_info, prompts, files = run_extract(
        monkeypatch, tmp_path, words_from("one a two b three c"))
    assert prompts == [NUMBER_PROMPT]
    assert count == 3
    assert files == ["1.mp3", "2.mp3", "3.mp3"]
    assert debug_info["whisper_info"]["pass"] == "number prompt"
    assert [d["number"] for d in debug_info["detected_numbers"]] == ["1", "2", "3"]


def test_falls_back_when_unprompted_pass_is_better(monkeypatch, tmp_path):
    count, debug_info, prompts, files = run_extract(
        monkeypatch, tmp_path,
        words_from("one a three b"),
        words_from("one a two b three c four d"))
    assert prompts == [NUMBER_PROMPT, None]
    assert count == 4
    assert files == ["1.mp3", "2.mp3", "3.mp3", "4.mp3"]
    assert debug_info["whisper_info"]["pass"] == "no prompt (fallback)"
    assert debug_info["total_words"] == 8
    assert debug_info["transcription"] == "one a two b three c four d"


def test_keeps_prompted_pass_when_fallback_not_better(monkeypatch, tmp_path):
    count, debug_info, prompts, files = run_extract(
        monkeypatch, tmp_path,
        words_from("one a three b"),
        words_from("one a two b"))
    assert prompts == [NUMBER_PROMPT, None]
    assert count == 2
    assert files == ["1.mp3", "3.mp3"]
    assert debug_info["whisper_info"]["pass"] == "number prompt"


def test_falls_back_when_prompted_pass_fails(monkeypatch, tmp_path):
    prompts = []

    def fake_transcribe(*args, prompt=None, **kwargs):
        prompts.append(prompt)
        if prompt is not None:
            raise RuntimeError("boom")
        return words_from("one a two b"), "one a two b", {}

    monkeypatch.setattr(audio_extractor, "transcribe_with_local_whisper", fake_transcribe)
    wav = tmp_path / "in.wav"
    AudioSegment.silent(10000).export(str(wav), format="wav")
    count, debug_info = audio_extractor.extract_audio_clips(str(wav), str(tmp_path / "out"), debug=True)
    assert prompts == [NUMBER_PROMPT, None]
    assert count == 2
    assert any("boom" in e for e in debug_info["errors"])
    assert debug_info["whisper_info"]["pass"] == "no prompt (fallback)"


def test_invalid_api_type_reported_once(tmp_path):
    wav = tmp_path / "in.wav"
    AudioSegment.silent(2000).export(str(wav), format="wav")
    count, debug_info = audio_extractor.extract_audio_clips(
        str(wav), str(tmp_path / "out"), api_type="bogus", debug=True)
    assert count == 0
    assert len([e for e in debug_info["errors"] if "Invalid api_type" in e]) == 1


@pytest.mark.parametrize("size", ["tiny", "base"])
def test_tiny_and_base_skip_prompt_and_fallback(monkeypatch, tmp_path, size):
    count, debug_info, prompts, _ = run_extract(
        monkeypatch, tmp_path, words_from("one a three b"), model_size=size)
    assert prompts == [None]
    assert count == 2
    assert debug_info["whisper_info"]["pass"] == "no prompt (model too small for prompt)"


def test_small_still_prompts_first(monkeypatch, tmp_path):
    _, _, prompts, _ = run_extract(
        monkeypatch, tmp_path, words_from("one a two b"), model_size="small")
    assert prompts == [NUMBER_PROMPT]


def test_short_clip_in_prompted_pass_triggers_fallback(monkeypatch, tmp_path):
    def at(raw, start, end):
        return {"start": start, "end": end, "raw": raw, "norm": audio_extractor.norm_token(raw)}
    # 1..3 in order, but clip 2 (2.0 s -> 2.4 s) is only 400 ms long
    prompted = [at("one", 0.0, 0.5), at("a", 1.0, 1.5), at("two", 1.5, 2.0),
                at("three", 2.4, 2.9), at("c", 4.0, 4.5)]
    _, _, prompts, _ = run_extract(monkeypatch, tmp_path, prompted, words_from("one a two b three c"))
    assert prompts == [NUMBER_PROMPT, None]
