# Issue Report Zip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sidebar "🐞 Report an issue" control that downloads one zip with the user's uploads, the app's outputs, and structured debug logs/errors.

**Architecture:** A Streamlit-free recorder module `issue_report.py` holds report state in a plain dict (kept by the app in `st.session_state.issue_report`) backed by a temp dir, and builds the zip in memory. `app.py` calls it from each processing handler and error handler, and renders the sidebar control.

**Tech Stack:** Python 3.10+ stdlib (`zipfile`, `json`, `tempfile`, `traceback`, `subprocess`), Streamlit, pytest, `streamlit.testing.v1.AppTest`.

**Spec:** `docs/superpowers/specs/2026-09-29-issue-report-design.md`

## Global Constraints

- Delivery is download only — no network calls, no credentials.
- `issue_report.py` must not import streamlit.
- Redaction: any dict key containing `key`, `token`, `secret` or `password` (case-insensitive) → value `"[redacted]"`, recursively in nested dicts.
- Zip layout: `report.json` (keys exactly `created`, `note`, `app`, `uploads`, `events`, `errors`, `skipped`), `uploads/<files>`, `outputs/<label>/<files>`.
- Building the zip never raises because an output dir is `None`, missing, or has an unreadable file — those go into `skipped` as `{"path": ..., "reason": ...}`.
- Download file name: `anki-report-YYYY-MM-DD-HHMM.zip`, mime `application/zip`.
- Must run on Python 3.10 (Docker image); no 3.11+ syntax/APIs.
- Run tests with `.venv/bin/python -m pytest -q` from the repo root (root `conftest.py` puts static ffmpeg on PATH).

---

### Task 1: `issue_report.py` recorder + unit tests

**Files:**
- Create: `issue_report.py`
- Create: `tests/test_issue_report.py`

**Interfaces:**
- Produces:
  - `new_report_state() -> dict` (keys `dir`, `events`, `errors`, `uploads`)
  - `record_upload(state: dict, name: str, data: bytes) -> None`
  - `record_event(state: dict, step: str, settings: dict, debug: dict | None = None) -> None`
  - `record_error(state: dict, step: str, exc: BaseException) -> None`
  - `redact(d: dict) -> dict`
  - `clear_report(state: dict) -> dict`
  - `build_report_zip(state: dict, note: str, output_dirs: dict, app_info: dict) -> bytes`
  - `app_version() -> str`

- [ ] **Step 1: Write the failing tests** — `tests/test_issue_report.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_issue_report.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'issue_report'`.

- [ ] **Step 3: Implement** — `issue_report.py`:

```python
"""
Issue report recorder: keeps copies of uploads, per-step settings/debug info,
and errors for the current session, and packages them with the app's output
folders into a zip the user can send to the maintainer.

Deliberately free of Streamlit so it can be unit-tested directly.
"""

import io
import json
import os
import shutil
import subprocess
import tempfile
import traceback
import zipfile
from datetime import datetime

_REDACT_MARKERS = ("key", "token", "secret", "password")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def new_report_state():
    """Fresh report state backed by its own temp directory."""
    report_dir = tempfile.mkdtemp(prefix="anki_report_")
    os.makedirs(os.path.join(report_dir, "uploads"), exist_ok=True)
    return {"dir": report_dir, "events": [], "errors": [], "uploads": []}


def redact(d):
    """Copy of d with secret-looking keys (recursively) replaced by "[redacted]"."""
    out = {}
    for k, v in d.items():
        if any(marker in str(k).lower() for marker in _REDACT_MARKERS):
            out[k] = "[redacted]"
        elif isinstance(v, dict):
            out[k] = redact(v)
        else:
            out[k] = v
    return out


def record_upload(state, name, data):
    """Save a copy of an uploaded file; never overwrites an earlier upload."""
    uploads_dir = os.path.join(state["dir"], "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    base = os.path.basename(name) or "upload"
    saved_as, n = base, 1
    while os.path.exists(os.path.join(uploads_dir, saved_as)):
        n += 1
        saved_as = f"{n}_{base}"
    with open(os.path.join(uploads_dir, saved_as), "wb") as f:
        f.write(data)
    state["uploads"].append({"name": name, "saved_as": saved_as, "size": len(data), "time": _now()})


def record_event(state, step, settings, debug=None):
    state["events"].append({"step": step, "time": _now(), "settings": redact(settings), "debug": debug})


def record_error(state, step, exc):
    state["errors"].append({
        "step": step,
        "time": _now(),
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    })


def clear_report(state):
    shutil.rmtree(state["dir"], ignore_errors=True)
    return new_report_state()


def _add_dir(zf, src_dir, arc_prefix, skipped):
    for root, _dirs, files in os.walk(src_dir):
        for fname in sorted(files):
            path = os.path.join(root, fname)
            arcname = os.path.join(arc_prefix, os.path.relpath(path, src_dir))
            try:
                zf.write(path, arcname)
            except OSError as e:
                skipped.append({"path": path, "reason": str(e)})


def build_report_zip(state, note, output_dirs, app_info):
    """Zip bytes: report.json + uploads/ + outputs/<label>/ for each existing output dir."""
    skipped = []
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        _add_dir(zf, os.path.join(state["dir"], "uploads"), "uploads", skipped)
        for label, path in output_dirs.items():
            if not path:
                continue
            if not os.path.isdir(path):
                skipped.append({"path": path, "reason": "missing"})
                continue
            _add_dir(zf, path, os.path.join("outputs", label), skipped)
        report = {
            "created": _now(),
            "note": note,
            "app": app_info,
            "uploads": state["uploads"],
            "events": state["events"],
            "errors": state["errors"],
            "skipped": skipped,
        }
        zf.writestr("report.json", json.dumps(report, indent=2, default=str))
    return buf.getvalue()


def app_version():
    """Short git commit if available, else $APP_VERSION, else "unknown"."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return os.environ.get("APP_VERSION") or "unknown"
```

Note: `json.dumps(..., default=str)` turns unknown objects into `str(obj)`; tuples serialise as lists natively — this satisfies `test_non_json_debug_values_are_stringified`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_issue_report.py -q` → all pass. Then `.venv/bin/python -m pytest -q` → full suite passes.

- [ ] **Step 5: Commit**

```bash
git add issue_report.py tests/test_issue_report.py
git commit -m "Add issue report recorder and zip builder"
```

---

### Task 2: Wire the recorder into the app + sidebar control

**Files:**
- Modify: `app.py` (session init ~line 50-60; handlers in Tabs 1–4; "Clear All Data"; sidebar starting `with st.sidebar:`)
- Create: `tests/test_app_report.py`

**Interfaces:**
- Consumes (from Task 1): `new_report_state`, `record_upload`, `record_event`, `record_error`, `clear_report`, `build_report_zip`, `app_version` from `issue_report`.

- [ ] **Step 1: Write the failing AppTest smoke test** — `tests/test_app_report.py`:

```python
import io
import json
import zipfile

from streamlit.testing.v1 import AppTest


def test_report_sidebar_prepares_downloadable_zip():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    at.sidebar.text_area(key="report_note").input("card 9 missing").run()
    at.sidebar.button(key="prepare_report_btn").click().run()
    assert not at.exception
    data = at.session_state["issue_report_zip"]
    z = zipfile.ZipFile(io.BytesIO(data))
    report = json.loads(z.read("report.json"))
    assert report["note"] == "card 9 missing"
    assert report["app"]["version"]
```

(Keys used by the test: text area `report_note`, button `prepare_report_btn`, session key `issue_report_zip` holding the zip bytes.)

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_app_report.py -q` → fails (no widget with key `report_note`).

- [ ] **Step 3: Session state + import.** Add `import issue_report` beside the other module imports, and next to the other `if '...' not in st.session_state:` initialisers:

```python
if 'issue_report' not in st.session_state:
    st.session_state.issue_report = issue_report.new_report_state()
```

- [ ] **Step 4: Record in each handler.** In each handler, record right after the input is known valid and before processing; record the result/debug after processing; and in each existing `except Exception as e:` call `issue_report.record_error(st.session_state.issue_report, "<step>", e)` as the first line (before the existing `st.error`). Exact calls (use `rep = st.session_state.issue_report` locally if it reads better):

  - **Extract Images** (Tab 1 docx branch, step `"extract_images"`): before extraction `record_upload(rep, docx_file.name, docx_file.getvalue())`; after `result = extract_numbered_images(...)`: `record_event(rep, "extract_images", {"file": docx_file.name}, {"count": result["count"], "skipped_unconvertible": result["skipped_unconvertible"], "files": st.session_state.image_files})`.
  - **Use These Photos** (step `"use_photos"`): `record_upload` for each `(name, data)` in `uploads`; after: `record_event(rep, "use_photos", {"files": [n for n, _ in uploads]}, result)`.
  - **Extract Audio Clips** (step `"extract_audio"`): before: `record_upload(rep, audio_file.name, audio_file.getvalue())`; after extraction: `record_event(rep, "extract_audio", {"file": audio_file.name, "api_type": api_type, "model_size": model_size, "use_vad": use_vad, "buffer_ms": buffer_ms, "api_key": api_key if api_type != "local" else None}, debug_info)`. (Pass `api_key` so redaction is exercised; the recorder redacts it.) If the call is made without `debug=True` in some path, pass `None` for debug.
  - **Use These Audio Files** (step `"use_audio_clips"`): same pattern as photos with `save_numbered_audio`'s result.
  - **Pair Files** (step `"pair_files"`): after pairing: `record_event(rep, "pair_files", {}, {"pairs": [(n, os.path.basename(a), os.path.basename(i)) for n, a, i in st.session_state.paired_files]})`.
  - **Remove / Swap** pair edits (steps `"remove_pair"`, `"swap_audio"`, `"swap_image"`): `record_event(rep, "<step>", {"number": num, "target": <swap target number or None>})` after the change is applied.
  - **Generate Anki Deck** (step `"create_deck"`): after success: `record_event(rep, "create_deck", {"card_style": card_style, "deck_name": deck_name, "tags": tags, "unit_session": unit_session}, {"pairs": len(st.session_state.paired_files)})`.
  - **Clear All Data**: add `st.session_state.issue_report = issue_report.clear_report(st.session_state.issue_report)` and `st.session_state.pop("issue_report_zip", None)`.

- [ ] **Step 5: Sidebar control.** Immediately inside `with st.sidebar:` (before `st.header("📖 How to Use")`):

```python
    with st.expander("🐞 Report an issue", expanded=False):
        st.caption(
            "Downloads a zip with your uploaded files (documents, recordings, photos), "
            "the app's outputs and debug logs. Send it to the maintainer."
        )
        report_note = st.text_area("What went wrong?", key="report_note")
        if st.button("Prepare report", key="prepare_report_btn"):
            try:
                st.session_state.issue_report_zip = issue_report.build_report_zip(
                    st.session_state.issue_report,
                    report_note,
                    {
                        "images": st.session_state.temp_images,
                        "audio": st.session_state.temp_audio,
                        "final": st.session_state.temp_final,
                    },
                    {"version": issue_report.app_version()},
                )
                st.session_state.issue_report_name = datetime.now().strftime("anki-report-%Y-%m-%d-%H%M.zip")
            except Exception as e:
                st.error(f"Couldn't prepare the report: {e}")
        if st.session_state.get("issue_report_zip"):
            st.download_button(
                "Download report (.zip)",
                data=st.session_state.issue_report_zip,
                file_name=st.session_state.issue_report_name,
                mime="application/zip",
                key="download_report_btn",
            )
```

Add `from datetime import datetime` to the imports if not already present.

- [ ] **Step 6: Run tests** — `.venv/bin/python -m pytest tests/test_app_report.py -q` passes; full suite passes. Also run a real smoke check: with `PYTHONPATH=.` and a scratch script using `AppTest`, upload is not simulable, so instead confirm `python -c "import ast; ast.parse(open('app.py').read())"` and a brief headless `streamlit run app.py --server.headless true --server.port 8597 --server.address 127.0.0.1` starts with no exceptions in its log (stop it afterwards).

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_app_report.py
git commit -m "Add Report an issue sidebar and record uploads, steps and errors"
```
