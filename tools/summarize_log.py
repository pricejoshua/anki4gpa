#!/usr/bin/env python3
"""Summarize the anonymous usage log: funnel, abandoned sessions, common files/errors.

A "session" is a page load: a browser refresh starts a new one. The funnel
counts sessions reaching each step; extract_images/use_photos and
extract_audio/use_audio_clips are alternative paths, so counts need not
decrease monotonically.
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import usage_log  # noqa: E402

FUNNEL = ["session_start", "upload", "extract_images_result", "use_photos_result", "extract_audio_result",
          "use_audio_clips_result", "pair_files", "create_deck", "create_deck_result"]


def load(path):
    out = []
    try:
        f = open(path, encoding="utf-8")
    except OSError:
        return out
    with f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if isinstance(e, dict) and e.get("session") and e.get("step"):
                out.append(e)
    return out


def _ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def sessions(events, idle_minutes, now):
    out = {}
    for e in events:
        s = out.setdefault(e["session"], {"steps": [], "last_step": None, "last_ts": None,
                                          "files": [], "errors": [], "completed": False})
        data = e.get("data") if isinstance(e.get("data"), dict) else {}
        step = e["step"]
        t = _ts(e.get("ts"))
        if t and (s["last_ts"] is None or t > s["last_ts"]):
            s["last_ts"] = t
        if step == "error":
            s["errors"].append(data)
            continue
        s["steps"].append(step)
        s["last_step"] = step
        if step == "upload":
            s["files"].append(data)
        if step == "create_deck_result":
            s["completed"] = True
    for s in out.values():
        lt = s["last_ts"]
        s["ended"] = lt is None or (now - lt).total_seconds() > idle_minutes * 60
    return out


def _fkey(f):
    return (f.get("name", "?"), f.get("sha256", "?"), f.get("size", "?"))


def report(events, idle_minutes, now):
    ss = sessions(events, idle_minutes, now)
    done = [s for s in ss.values() if s["completed"]]
    aband = [s for s in ss.values() if s["ended"] and not s["completed"]]
    active = [s for s in ss.values() if not s["ended"] and not s["completed"]]
    L = ["Usage log summary",
         f"Sessions: {len(ss)}", f"Completed: {len(done)}",
         f"Abandoned: {len(aband)} (idle > {idle_minutes} min)", f"Active: {len(active)}",
         "", "Funnel (sessions reaching step)"]
    for step in FUNNEL:
        L.append(f"  {step:<24}{sum(1 for s in ss.values() if step in s['steps'])}")
    L.append("  (extract_* and use_* are alternative paths; counts need not decrease)")
    L += ["", "Abandoned by last step"]
    if not aband:
        L.append("  (none)")
    groups = defaultdict(list)
    for s in aband:
        groups[s["last_step"] or "(none)"].append(s)
    for step, grp in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        L.append(f"  {step}: {len(grp)}")
        files = Counter(_fkey(f) for s in grp for f in s["files"])
        for (n, h, z), c in files.most_common(5):
            L.append(f"    file x{c}: {n} sha256={h} size={z}")
        errs = Counter((e.get("in", "?"), e.get("type", "?")) for s in grp for e in s["errors"])
        for (i, t), c in errs.most_common(5):
            L.append(f"    error x{c}: {t} in {i}")
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default=usage_log.log_path())
    ap.add_argument("--idle-minutes", type=int, default=30)
    a = ap.parse_args(argv)
    print(report(load(a.path), a.idle_minutes, datetime.now(timezone.utc)))


if __name__ == "__main__":
    main()
