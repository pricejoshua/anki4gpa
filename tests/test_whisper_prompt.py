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


def test_local_backend_passes_initial_prompt(monkeypatch):
    faster_whisper = pytest.importorskip("faster_whisper")
    calls = {}

    class FakeModel:
        def __init__(self, *args, **kwargs):
            pass

        def transcribe(self, audio_path, **kwargs):
            calls.update(kwargs)
            return [], SimpleNamespace(language="en", duration=0)

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeModel)
    audio_extractor.transcribe_with_local_whisper("unused.wav")
    assert calls["initial_prompt"] == NUMBER_PROMPT


@pytest.mark.parametrize("module_name,class_name,func_name", [
    ("groq", "Groq", "transcribe_with_groq"),
    ("openai", "OpenAI", "transcribe_with_openai"),
])
def test_api_backends_pass_prompt(monkeypatch, tmp_path, module_name, class_name, func_name):
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
    getattr(audio_extractor, func_name)(str(audio_path), api_key="k")
    assert calls["prompt"] == NUMBER_PROMPT


def test_clip_count_after_sequence_reset(monkeypatch, tmp_path):
    def w(raw, start):
        return {"start": start, "end": start + 0.5, "raw": raw, "norm": audio_extractor.norm_token(raw)}

    words = [w("2025", 1), w("one", 2), w("apple", 3), w("two", 4), w("pear", 5)]
    monkeypatch.setattr(audio_extractor, "transcribe_with_local_whisper",
                        lambda *a, **k: (words, "", {}))
    wav = tmp_path / "in.wav"
    AudioSegment.silent(7000).export(str(wav), format="wav")
    out_dir = tmp_path / "out"

    count = audio_extractor.extract_audio_clips(str(wav), str(out_dir))

    assert count == 2
    assert sorted(os.listdir(out_dir)) == ["1.mp3", "2.mp3"]
