import json
import os

import usage_log


def _lines(path):
    with open(path, encoding="utf-8") as f:
        return f.read().splitlines()


def test_line_fields_and_format(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    usage_log.log_event("abc123abc123", "upload", {"x": 1})
    path = usage_log.log_path()
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    assert raw.endswith("\n")
    rec = json.loads(raw)
    assert set(rec) == {"ts", "session", "version", "step", "data"}
    assert rec["ts"].endswith("Z")
    assert rec["session"] == "abc123abc123"
    assert rec["step"] == "upload"
    assert rec["data"] == {"x": 1}


def test_append_and_creates_dir(tmp_path, monkeypatch):
    log_dir = tmp_path / "nested" / "logs"
    monkeypatch.setenv("LOG_DIR", str(log_dir))
    usage_log.log_event("s", "a")
    usage_log.log_event("s", "b")
    lines = _lines(usage_log.log_path())
    assert [json.loads(l)["step"] for l in lines] == ["a", "b"]
    assert json.loads(lines[0])["data"] == {}


def test_unwritable_dir_does_not_raise(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("LOG_DIR", str(blocker / "sub"))
    usage_log.log_event("s", "a", {"x": 1})
    assert not (blocker / "sub").exists()
    assert os.listdir(tmp_path) == ["file"]


def test_non_serialisable_data_is_stringified(tmp_path, monkeypatch):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    usage_log.log_event("s", "a", {"obj": object()})
    rec = json.loads(_lines(usage_log.log_path())[0])
    assert isinstance(rec["data"]["obj"], str)


def test_new_session_id():
    sid = usage_log.new_session_id()
    assert len(sid) == 12 and int(sid, 16) >= 0
    assert sid != usage_log.new_session_id()


def test_file_fingerprint():
    a = usage_log.file_fingerprint("/tmp/dir/Photo.JPG", b"abc")
    assert a == usage_log.file_fingerprint("Photo.JPG", b"abc")
    assert a["name"] == "Photo.JPG"
    assert a["ext"] == ".jpg"
    assert a["size"] == 3
    assert len(a["sha256"]) == 16
    assert a["sha256"] != usage_log.file_fingerprint("Photo.JPG", b"abd")["sha256"]


def test_summarize_debug():
    out = usage_log.summarize_debug({
        "api_key": "SECRET", "n": 3, "flag": True, "none": None,
        "items": list(range(500)), "long": "x" * 500, "d": {"a": 1},
    })
    assert out["api_key"] == "[redacted]"
    assert out["n"] == 3 and out["flag"] is True and out["none"] is None
    assert out["items_len"] == 500 and "items" not in out
    assert out["d_len"] == 1
    assert out["long_len"] == 500 and "long" not in out
    assert usage_log.summarize_debug(None) == {}
    assert usage_log.summarize_debug("nope") == {}


def test_default_log_dir_is_app_relative(monkeypatch, tmp_path):
    monkeypatch.delenv("LOG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    expected = os.path.join(os.path.dirname(os.path.abspath(usage_log.__file__)), "logs", "usage.jsonl")
    assert usage_log.log_path() == expected
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "x"))
    assert usage_log.log_path() == str(tmp_path / "x" / "usage.jsonl")


def test_summarize_settings_no_free_text():
    out = usage_log.summarize_settings({
        "deck_name": "My secret deck", "tags": "tagA tagB", "unit_session": "Unit 7",
        "api_key": "SECRET", "api_type": "local", "model_size": "medium", "card_style": "basic",
        "n": 3, "flag": False, "none": None, "extra": ["a", "b"], "d": {"a": 1, "b": 2},
        "file": "lecture.docx",
    })
    blob = json.dumps(out)
    for t in ("secret deck", "tagA", "Unit 7", "SECRET"):
        assert t not in blob
    assert out["deck_name_len"] == 14 and out["tags_len"] == 9 and out["unit_session_len"] == 6
    assert out["api_key"] == "[redacted]"
    assert out["api_type"] == "local" and out["model_size"] == "medium" and out["card_style"] == "basic"
    assert out["file"] == "lecture.docx"
    assert out["n"] == 3 and out["flag"] is False and out["none"] is None
    assert out["extra_len"] == 2 and out["d_count"] == 2
    assert usage_log.summarize_settings(None) == {}


def test_summarize_settings_caps_files():
    out = usage_log.summarize_settings({"files": [f"f{i}.mp3" for i in range(50)]})
    assert out["files"] == [f"f{i}.mp3" for i in range(20)]
    assert out["files_count"] == 50


def test_version_cached(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(usage_log.issue_report, "app_version", lambda: calls.append(1) or "v1")
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    usage_log._version.cache_clear()
    try:
        usage_log.log_event("s", "a")
        usage_log.log_event("s", "b")
        assert len(calls) == 1
    finally:
        usage_log._version.cache_clear()
