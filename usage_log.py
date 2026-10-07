"""
Anonymous usage log: appends one JSON line per event to $LOG_DIR/usage.jsonl
so the maintainer can see where sessions stop. Never logs file contents,
transcripts, tracebacks or secrets, and never raises into the app.

Deliberately free of Streamlit so it can be unit-tested directly.
"""

import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone

import issue_report


def log_path():
    return os.path.join(os.environ.get("LOG_DIR", "logs"), "usage.jsonl")


def new_session_id():
    return uuid.uuid4().hex[:12]


def file_fingerprint(name, data):
    """Identify an upload without keeping its contents."""
    base = os.path.basename(name)
    return {"name": base, "sha256": hashlib.sha256(data).hexdigest()[:16],
            "size": len(data), "ext": os.path.splitext(base)[1].lower()}


def summarize_debug(debug):
    """Compact, redacted view of a debug dict: scalars kept; strings and collections only as lengths (never text)."""
    if not isinstance(debug, dict):
        return {}
    out = {}
    for k, v in issue_report.redact(debug).items():
        if v is None or isinstance(v, (bool, int, float)):
            out[k] = v
        elif v == "[redacted]":
            out[k] = v
        elif isinstance(v, (str, list, tuple, dict)):
            out[f"{k}_len"] = len(v)
    return out


def log_event(session, step, data=None):
    """Append one event line; swallows every failure."""
    try:
        line = json.dumps({
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "session": session,
            "version": issue_report.app_version(),
            "step": step,
            "data": data or {},
        }, default=str)
        path = log_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:  # logging must never break the app
        print(f"usage_log: {type(e).__name__}", file=sys.stderr)
