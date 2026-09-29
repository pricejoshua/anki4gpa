import os
from io import BytesIO

from pydub import AudioSegment
from pydub.generators import Sine

from audio_extractor import save_numbered_audio


def _audio_bytes(fmt="wav", ms=300, freq=440):
    buf = BytesIO()
    Sine(freq).to_audio_segment(duration=ms).export(buf, format=fmt)
    return buf.getvalue()


def test_saves_valid_uploads_as_numbered_mp3(tmp_path):
    uploads = [
        ("1.wav", _audio_bytes("wav", ms=500)),
        ("2.mp3", _audio_bytes("mp3", ms=500)),
    ]

    result = save_numbered_audio(uploads, str(tmp_path))

    assert result["saved"] == [1, 2]
    assert result["skipped_no_number"] == []
    assert result["skipped_duplicate"] == []
    assert result["skipped_unreadable"] == []
    assert sorted(os.listdir(tmp_path)) == ["1.mp3", "2.mp3"]
    for name in ("1.mp3", "2.mp3"):
        clip = AudioSegment.from_file(str(tmp_path / name))
        assert abs(len(clip) - 500) <= 100


def test_mp3_upload_is_written_unchanged(tmp_path):
    data = _audio_bytes("mp3")

    save_numbered_audio([("1.MP3", data)], str(tmp_path))

    assert (tmp_path / "1.mp3").read_bytes() == data


def test_extracts_number_from_anywhere_in_filename(tmp_path):
    uploads = [("vocab-3-final.ogg", _audio_bytes("ogg"))]

    result = save_numbered_audio(uploads, str(tmp_path))

    assert result["saved"] == [3]
    assert os.path.exists(tmp_path / "3.mp3")


def test_skips_files_without_number(tmp_path):
    result = save_numbered_audio([("intro.wav", _audio_bytes())], str(tmp_path))

    assert result["saved"] == []
    assert result["skipped_no_number"] == ["intro.wav"]
    assert os.listdir(tmp_path) == []


def test_duplicate_number_keeps_alphabetically_first(tmp_path):
    uploads = [
        ("1_dup.wav", _audio_bytes(ms=900, freq=880)),
        ("1.wav", _audio_bytes(ms=300, freq=440)),
    ]

    result = save_numbered_audio(uploads, str(tmp_path))

    assert result["saved"] == [1]
    assert result["skipped_duplicate"] == ["1_dup.wav"]
    assert os.listdir(tmp_path) == ["1.mp3"]
    kept = AudioSegment.from_file(str(tmp_path / "1.mp3"))
    assert abs(len(kept) - 300) <= 100


def test_skips_unreadable_audio(tmp_path):
    result = save_numbered_audio([("1.mp3", b"not audio")], str(tmp_path))

    assert result["saved"] == []
    assert result["skipped_unreadable"] == ["1.mp3"]
    assert os.listdir(tmp_path) == []


def test_creates_missing_output_folder(tmp_path):
    output_folder = str(tmp_path / "nested" / "out")

    result = save_numbered_audio([("1.wav", _audio_bytes())], output_folder)

    assert result["saved"] == [1]
    assert os.path.exists(os.path.join(output_folder, "1.mp3"))


def test_digits_in_extension_are_not_card_numbers(tmp_path):
    uploads = [
        ("intro.mp3", _audio_bytes("mp3")),
        ("intro.m4a", _audio_bytes("wav")),
    ]

    result = save_numbered_audio(uploads, str(tmp_path))

    assert sorted(result["skipped_no_number"]) == ["intro.m4a", "intro.mp3"]
    assert result["saved"] == []
    assert os.listdir(tmp_path) == []


def test_number_taken_from_stem_with_digit_extension(tmp_path):
    result = save_numbered_audio([("clip_3.m4a", _audio_bytes("wav"))], str(tmp_path))

    assert result["saved"] == [3]
    assert os.listdir(tmp_path) == ["3.mp3"]


def test_partial_output_removed_when_export_fails(tmp_path, monkeypatch):
    data = _audio_bytes("wav")

    def bad_export(self, out_f, *a, **kw):
        with open(out_f, "wb") as f:
            f.write(b"junk")
        raise RuntimeError("boom")

    monkeypatch.setattr(AudioSegment, "export", bad_export)

    result = save_numbered_audio([("5.wav", data)], str(tmp_path))

    assert result["skipped_unreadable"] == ["5.wav"]
    assert result["saved"] == []
    assert os.listdir(tmp_path) == []
