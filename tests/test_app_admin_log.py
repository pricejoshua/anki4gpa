import json

from streamlit.testing.v1 import AppTest

TOKEN = "s3cret-token"


def _app(tmp_path, monkeypatch, token=TOKEN, admin=True, seed=False):
    monkeypatch.setenv("LOG_DIR", str(tmp_path))
    if token is None:
        monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    else:
        monkeypatch.setenv("ADMIN_TOKEN", token)
    if seed:
        (tmp_path / "usage.jsonl").write_text(
            json.dumps({"session": "abc", "step": "session_start", "ts": "2026-01-01T00:00:00Z"}) + "\n")
    at = AppTest.from_file("app.py", default_timeout=60)
    if admin:
        at.query_params["admin"] = "1"
    at.run()
    assert not at.exception
    return at


def _pw(at):
    return [t for t in at.text_input if t.label == "Admin password"]


def _downloads(at):
    return [b for b in at.get("download_button")]


def _enter(at, value):
    _pw(at)[0].input(value).run()
    assert not at.exception


def test_no_token_hides_panel(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch, token=None)
    assert not _pw(at)
    assert not [d for d in _downloads(at) if d.proto.label == "Download usage.jsonl"]


def test_token_without_query_param_renders_nothing(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch, admin=False)
    assert not _pw(at)


def test_wrong_token(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch, seed=True)
    _enter(at, "nope")
    assert [e.value for e in at.error] == ["Incorrect password"]
    assert not [d for d in _downloads(at) if d.proto.label == "Download usage.jsonl"]
    assert not any("Usage log summary" in c.value for c in at.code)


def test_right_token_shows_summary_and_download(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch, seed=True)
    _enter(at, TOKEN)
    assert any("Usage log summary" in c.value for c in at.code)
    assert [d for d in _downloads(at) if d.proto.label == "Download usage.jsonl"]
    assert not at.error


def test_right_token_no_log(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    # session_start is logged on first run; remove it to simulate no log
    (tmp_path / "usage.jsonl").unlink(missing_ok=True)
    _enter(at, TOKEN)
    assert any(i.value == "No usage log yet." for i in at.info)
    assert not [d for d in _downloads(at) if d.proto.label == "Download usage.jsonl"]


def test_password_not_kept_in_session_state(tmp_path, monkeypatch):
    for entered in (TOKEN, "wrong-pw-123"):
        at = _app(tmp_path, monkeypatch, seed=True)
        _enter(at, entered)
        assert "admin_pw" not in at.session_state
        assert entered not in [v for k, v in at.session_state.filtered_state.items()]
