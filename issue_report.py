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
