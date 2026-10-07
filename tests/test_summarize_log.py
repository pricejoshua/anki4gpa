import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import summarize_log as sl

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
F = {"name": "lecture.docx", "sha256": "abc123", "size": 42, "ext": ".docx"}


def ev(session, step, ts, data=None):
    return {"ts": ts, "session": session, "version": "v", "step": step, "data": data or {}}


def write(tmp_path):
    rows = [
        ev("done", "session_start", "2026-01-01T08:00:00Z"),
        ev("done", "upload", "2026-01-01T08:01:00Z", F),
        ev("done", "extract_images_result", "2026-01-01T08:02:00Z"),
        ev("done", "create_deck_result", "2026-01-01T08:03:00Z"),
        ev("aband", "session_start", "2026-01-01T09:00:00Z"),
        ev("aband", "upload", "2026-01-01T09:01:00Z", {**F, "name": "stuck.mp3", "sha256": "dead", "ext": ".mp3"}),
        ev("aband", "extract_audio_result", "2026-01-01T09:02:00Z"),
        ev("aband", "error", "2026-01-01T09:02:30Z", {"in": "extract_audio", "type": "ValueError"}),
        ev("live", "session_start", "2026-01-01T11:50:00Z"),
        ev("live", "upload", "2026-01-01T11:55:00Z", F),
    ]
    p = tmp_path / "usage.jsonl"
    lines = [json.dumps(r) for r in rows]
    lines.insert(3, "{not json")
    lines.insert(5, "")
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_load_skips_corrupt(tmp_path):
    assert len(sl.load(write(tmp_path))) == 10


def test_sessions_classification(tmp_path):
    s = sl.sessions(sl.load(write(tmp_path)), 30, NOW)
    assert s["done"]["completed"] and not s["aband"]["completed"]
    assert s["aband"]["last_step"] == "extract_audio_result"
    assert s["aband"]["errors"] == [{"in": "extract_audio", "type": "ValueError"}]
    assert s["aband"]["files"][0]["name"] == "stuck.mp3"


def test_report(tmp_path):
    out = sl.report(sl.load(write(tmp_path)), 30, NOW)
    assert "Sessions: 3" in out and "Completed: 1" in out
    assert "Abandoned: 1" in out and "Active: 1" in out
    sect = out.split("Abandoned by last step")[1]
    assert "extract_audio_result" in sect
    assert "stuck.mp3" in sect and "dead" in sect
    assert "ValueError" in sect and "extract_audio" in sect
    assert "lecture.docx" not in sect


def test_funnel_counts(tmp_path):
    out = sl.report(sl.load(write(tmp_path)), 30, NOW)
    funnel = out.split("Funnel (sessions reaching step)")[1].split("Abandoned by last step")[0]
    counts = {l.split()[0]: l.split()[1] for l in funnel.splitlines() if l.startswith("  ") and l.split()[0] in sl.FUNNEL}
    assert counts["session_start"] == "3"
    assert counts["upload"] == "3"
    assert counts["extract_images_result"] == "1"
    assert counts["extract_audio_result"] == "1"
    assert counts["create_deck_result"] == "1"
    assert "alternative" in funnel
    assert list(counts)[0] == "session_start"


def test_load_missing_file(tmp_path):
    assert sl.load(str(tmp_path / "nope")) == []


def test_empty():
    assert "Sessions: 0" in sl.report([], 30, NOW)
