import io
import json
import os
import zipfile

import issue_report as ir


def _zip(state, note="", output_dirs=None, app_info=None):
    data = ir.build_report_zip(state, note, output_dirs or {}, app_info or {"version": "test"})
    return zipfile.ZipFile(io.BytesIO(data))


def test_new_state_has_temp_dir_and_empty_lists():
    state = ir.new_report_state()
    try:
        assert os.path.isdir(state["dir"])
        assert state["events"] == [] and state["errors"] == [] and state["uploads"] == []
    finally:
        ir.clear_report(state)


def test_record_upload_saves_copy_and_dedupes_names():
    state = ir.new_report_state()
    try:
        ir.record_upload(state, "lesson.docx", b"first")
        ir.record_upload(state, "lesson.docx", b"second")
        saved = [u["saved_as"] for u in state["uploads"]]
        assert saved == ["lesson.docx", "2_lesson.docx"]
        with open(os.path.join(state["dir"], "uploads", "2_lesson.docx"), "rb") as f:
            assert f.read() == b"second"
        assert state["uploads"][0]["size"] == 5
    finally:
        ir.clear_report(state)


def test_redact_nested_and_case_insensitive():
    out = ir.redact({"api_key": "sk-1", "Model": "small",
                     "nested": {"GROQ_TOKEN": "t", "Password": "p", "ok": 1}})
    assert out == {"api_key": "[redacted]", "Model": "small",
                   "nested": {"GROQ_TOKEN": "[redacted]", "Password": "[redacted]", "ok": 1}}


def test_record_event_redacts_settings():
    state = ir.new_report_state()
    try:
        ir.record_event(state, "extract_audio", {"api_type": "groq", "api_key": "sk-1"}, {"total_words": 3})
        ev = state["events"][0]
        assert ev["step"] == "extract_audio"
        assert ev["settings"] == {"api_type": "groq", "api_key": "[redacted]"}
        assert ev["debug"] == {"total_words": 3}
        assert "time" in ev
    finally:
        ir.clear_report(state)


def test_record_error_captures_traceback():
    state = ir.new_report_state()
    try:
        try:
            raise ValueError("boom")
        except ValueError as e:
            ir.record_error(state, "extract_images", e)
        err = state["errors"][0]
        assert err["step"] == "extract_images"
        assert err["type"] == "ValueError"
        assert err["message"] == "boom"
        assert "raise ValueError" in err["traceback"]
    finally:
        ir.clear_report(state)


def test_zip_layout(tmp_path):
    images = tmp_path / "imgs"
    images.mkdir()
    (images / "1.png").write_bytes(b"png")
    state = ir.new_report_state()
    try:
        ir.record_upload(state, "rec.mp3", b"mp3")
        ir.record_event(state, "extract_audio", {"model": "small"})
        z = _zip(state, note="card 9 missing",
                 output_dirs={"images": str(images), "audio": None},
                 app_info={"version": "abc123"})
        names = set(z.namelist())
        assert "report.json" in names
        assert "uploads/rec.mp3" in names
        assert "outputs/images/1.png" in names
        report = json.loads(z.read("report.json"))
        assert set(report) == {"created", "note", "app", "uploads", "events", "errors", "skipped"}
        assert report["note"] == "card 9 missing"
        assert report["app"] == {"version": "abc123"}
        assert report["events"][0]["step"] == "extract_audio"
    finally:
        ir.clear_report(state)


def test_missing_output_dir_is_skipped_not_raised(tmp_path):
    state = ir.new_report_state()
    try:
        z = _zip(state, output_dirs={"final": str(tmp_path / "gone")})
        report = json.loads(z.read("report.json"))
        assert report["skipped"] == [{"path": str(tmp_path / "gone"), "reason": "missing"}]
    finally:
        ir.clear_report(state)


def test_non_json_debug_values_are_stringified():
    class Weird:
        def __str__(self):
            return "weird!"

    state = ir.new_report_state()
    try:
        ir.record_event(state, "s", {}, {"obj": Weird(), "nums": (1, 2)})
        report = json.loads(_zip(state).read("report.json"))
        assert report["events"][0]["debug"] == {"obj": "weird!", "nums": [1, 2]}
    finally:
        ir.clear_report(state)


def test_clear_report_removes_dir_and_returns_fresh_state():
    state = ir.new_report_state()
    old_dir = state["dir"]
    ir.record_event(state, "s", {})
    fresh = ir.clear_report(state)
    try:
        assert not os.path.exists(old_dir)
        assert fresh["events"] == [] and os.path.isdir(fresh["dir"])
    finally:
        ir.clear_report(fresh)


def test_app_version_returns_string():
    v = ir.app_version()
    assert isinstance(v, str) and v


def test_redact_recurses_into_lists_and_tuples():
    """Nested list of dicts with secrets should be redacted."""
    out = ir.redact({"providers": [{"api_key": "sk-1"}, {"api_key": "sk-2"}]})
    assert out == {"providers": [{"api_key": "[redacted]"}, {"api_key": "[redacted]"}]}


def test_redact_converts_tuple_to_list():
    """Tuples should be converted to lists during redaction."""
    out = ir.redact({"data": ({"token": "t"}, {"password": "p"})})
    assert out == {"data": [{"token": "[redacted]"}, {"password": "[redacted]"}]}
    assert isinstance(out["data"], list)


def test_record_event_redacts_debug_dict():
    """Debug dict with nested secrets should be redacted."""
    state = ir.new_report_state()
    try:
        ir.record_event(state, "step", {}, {"x": [{"token": "secret"}]})
        ev = state["events"][0]
        assert ev["debug"] == {"x": [{"token": "[redacted]"}]}
    finally:
        ir.clear_report(state)


def test_record_event_deep_copies_debug_to_prevent_mutation():
    """Mutating original debug dict after record_event shouldn't change recorded event."""
    state = ir.new_report_state()
    try:
        debug = {"x": [{"name": "val"}]}
        ir.record_event(state, "step", {}, debug)
        # Mutate the original debug dict
        debug["x"][0]["name"] = "changed"
        debug["y"] = "new"
        # Recorded event should not be affected
        ev = state["events"][0]
        assert ev["debug"] == {"x": [{"name": "val"}]}
        assert "y" not in ev["debug"]
    finally:
        ir.clear_report(state)


def _files(state):
    return sorted(os.listdir(os.path.join(state["dir"], "uploads")))


def test_record_upload_same_name_same_bytes_dedupes_content():
    state = ir.new_report_state()
    try:
        ir.record_upload(state, "a.docx", b"same")
        ir.record_upload(state, "a.docx", b"same")
        assert _files(state) == ["a.docx"]
        assert [u["saved_as"] for u in state["uploads"]] == ["a.docx", "a.docx"]
        assert state["uploads"][0]["sha256"] == state["uploads"][1]["sha256"]
    finally:
        ir.clear_report(state)


def test_record_upload_same_name_different_bytes_still_numbered():
    state = ir.new_report_state()
    try:
        ir.record_upload(state, "a.docx", b"one")
        ir.record_upload(state, "a.docx", b"two")
        assert _files(state) == ["2_a.docx", "a.docx"]
        assert [u["saved_as"] for u in state["uploads"]] == ["a.docx", "2_a.docx"]
    finally:
        ir.clear_report(state)


def test_record_upload_different_name_same_bytes_points_to_first():
    state = ir.new_report_state()
    try:
        ir.record_upload(state, "a.docx", b"same")
        ir.record_upload(state, "b.docx", b"same")
        assert _files(state) == ["a.docx"]
        assert state["uploads"][1]["name"] == "b.docx"
        assert state["uploads"][1]["saved_as"] == "a.docx"
    finally:
        ir.clear_report(state)
