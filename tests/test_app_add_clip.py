from streamlit.testing.v1 import AppTest


def _app_with_clips(tmp_path):
    (tmp_path / "1.mp3").write_bytes(b"x")
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["temp_audio"] = str(tmp_path)
    at.session_state["audio_files"] = ["1.mp3"]
    at.run()
    return at


def test_add_clip_section_shown_when_clips_exist(tmp_path):
    at = _app_with_clips(tmp_path)
    assert not at.exception
    assert any(b.key == "add_clip_btn" for b in at.button)


def test_add_clip_without_file_shows_error(tmp_path):
    at = _app_with_clips(tmp_path)
    at.button(key="add_clip_btn").click().run()
    assert not at.exception
    assert any("Please choose an audio file first" in e.value for e in at.error)


def test_add_clip_section_hidden_without_clips():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not any(b.key == "add_clip_btn" for b in at.button)
