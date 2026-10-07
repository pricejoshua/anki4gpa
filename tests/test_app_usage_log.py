import json

from PIL import Image
from streamlit.testing.v1 import AppTest


def _lines(tmp_path):
    p = tmp_path / "usage.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text().splitlines()]


def _has_key(obj, key):
    if isinstance(obj, dict):
        return key in obj or any(_has_key(v, key) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_key(v, key) for v in obj)
    return False


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    return at


def test_session_start_logged_once_per_session(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    at.run()
    lines = _lines(tmp_path)
    assert [l["step"] for l in lines] == ["session_start"]
    assert lines[0]["session"] == at.session_state["usage_session"]


def test_prepare_report_unaffected(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    at.button(key="prepare_report_btn").click().run()
    assert not at.exception
    assert at.session_state["issue_report_zip"]


def test_notice_shown():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert any("Anonymous usage stats" in c.value for c in at.caption)


def test_pair_files_event_logged_without_traceback(tmp_path, monkeypatch):
    logdir = tmp_path / "log"
    images, audio = tmp_path / "img", tmp_path / "aud"
    images.mkdir()
    audio.mkdir()
    Image.new("RGB", (2, 2)).save(images / "1.png")
    (audio / "1.mp3").write_bytes(b"x")
    monkeypatch.setenv("LOG_DIR", str(logdir))
    at = AppTest.from_file("app.py", default_timeout=60)
    at.session_state["temp_images"] = str(images)
    at.session_state["temp_audio"] = str(audio)
    at.session_state["image_files"] = ["1.png"]
    at.session_state["audio_files"] = ["1.mp3"]
    at.run()
    at.button(key="pair_btn").click().run()
    assert not at.exception
    lines = _lines(logdir)
    assert "pair_files" in [l["step"] for l in lines]
    assert {l["session"] for l in lines} == {at.session_state["usage_session"]}
    assert not any(_has_key(l, "traceback") for l in lines)


def test_clear_all_logs_reset_and_keeps_session(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    sid = at.session_state["usage_session"]
    next(b for b in at.sidebar.button if b.label == "Clear All Data").click().run()
    assert at.session_state["usage_session"] == sid
    lines = _lines(tmp_path)
    assert [l["step"] for l in lines] == ["session_start", "reset"]


_REPORT_SCRIPT = '''
import ast
import streamlit as st
import issue_report, usage_log

ns = {"st": st, "issue_report": issue_report, "usage_log": usage_log}
tree = ast.parse(open("app.py").read())
wanted = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ("_usage", "_report")]
exec(compile(ast.Module(body=wanted, type_ignores=[]), "app.py", "exec"), ns)
if "issue_report" not in st.session_state:
    st.session_state.issue_report = issue_report.new_report_state()
    st.session_state.usage_session = "abc123abc123"
_report = ns["_report"]
_report(issue_report.record_upload, "dir/Lesson.DOCX", b"secret contents")
_report(issue_report.record_event, "extract_audio",
        {"file": "a.mp3", "api_key": "sk-SECRET-VALUE"},
        {"clips": [1, 2, 3], "token": "tok-SECRET", "transcription": "SECRET-TRANSCRIPT words " * 20})
try:
    raise ValueError("boom sk-ERRSECRET /home/x/y")
except ValueError as e:
    _report(issue_report.record_error, "extract_audio", e)
_report(print, "ignored")
'''


def test_report_forwards_to_usage_log_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    at = AppTest.from_string(_REPORT_SCRIPT, default_timeout=60)
    at.run()
    assert not at.exception
    raw = (tmp_path / "usage.jsonl").read_text()
    assert "SECRET" not in raw
    assert "secret contents" not in raw
    lines = [json.loads(l) for l in raw.splitlines()]
    assert [l["step"] for l in lines] == ["upload", "extract_audio", "error"]
    assert lines[0]["data"]["name"] == "Lesson.DOCX"
    assert lines[0]["data"]["ext"] == ".docx"
    assert lines[1]["data"]["debug"]["clips_len"] == 3
    assert lines[1]["data"]["debug"]["transcription_len"] == len("SECRET-TRANSCRIPT words " * 20)
    assert "TRANSCRIPT" not in raw and "words" not in raw
    assert "ERRSECRET" not in raw and "boom" not in raw and "/home/x" not in raw
    assert lines[2]["data"] == {"in": "extract_audio", "type": "ValueError"}
    assert not any(_has_key(l, "traceback") for l in lines)
