# Issue Report Zip Design

## Purpose

When something goes wrong (e.g. a missing card number, a crash on an unusual Word
document), users currently have to describe it and separately send their files.
The app also discards uploads right after processing, and Whisper debug info and
tracebacks only ever appear on screen. This adds a sidebar **"🐞 Report an issue"**
control that downloads one zip containing everything needed to reproduce what the
user saw, which they send to the maintainer by any means (email, chat, Drive).

Delivery is **download only** — no network upload, no credentials.

## Components

### 1. `issue_report.py` (new, no Streamlit imports)

A recorder whose state is a plain dict (stored by the app in
`st.session_state.issue_report`), backed by a temp directory.

- `new_report_state() -> dict` — creates `{'dir': mkdtemp(prefix="anki_report_"), 'events': [], 'errors': [], 'uploads': []}`; uploads saved under `<dir>/uploads/`.
- `record_upload(state, name, data: bytes) -> None` — saves a copy to `uploads/<name>`; if a file with that name already exists, prefix with a counter (`2_<name>`) rather than overwrite. Appends `{'name', 'saved_as', 'size', 'time'}` to `state['uploads']`.
- `record_event(state, step: str, settings: dict, debug: dict | None = None) -> None` — appends `{'step', 'time', 'settings', 'debug'}`. Settings pass through `redact()`.
- `record_error(state, step: str, exc: BaseException) -> None` — appends `{'step', 'time', 'type', 'message', 'traceback'}` (traceback via `traceback.format_exception`).
- `redact(d)` — returns a copy with any key containing `key`, `token`, `secret` or `password` (case-insensitive) replaced by `"[redacted]"`, recursively for nested dicts.
- `clear_report(state) -> dict` — removes the temp dir and returns a fresh state.
- `build_report_zip(state, note: str, output_dirs: dict[str, str | None], app_info: dict) -> bytes` — builds the zip in memory:
  ```
  report.json                 {"created", "note", "app": app_info, "uploads", "events", "errors", "skipped"}
  uploads/<files>
  outputs/<label>/<files>     for each label -> dir in output_dirs that exists (e.g. images, audio, final)
  ```
  `debug` payloads are made JSON-safe (non-serialisable values → `str`). Any file or directory that can't be read is skipped and listed in `skipped` with the reason; building never raises for missing/unreadable output dirs.
- `app_version() -> str` — `git rev-parse --short HEAD` in the app directory if it works, else env `APP_VERSION`, else `"unknown"` (the Docker image excludes `.git`).

### 2. App hooks (`app.py`)

- Initialise `st.session_state.issue_report = new_report_state()` alongside the other session keys.
- Each processing action records what it used, right before processing:
  - Extract Images: `record_upload` the .docx; `record_event("extract_images", {...})` with the result dict (count, skipped_unconvertible).
  - Use These Photos: `record_upload` each photo; event with the result buckets.
  - Extract Audio Clips: `record_upload` the recording; event with settings (api_type, model_size, use_vad, buffer_ms; api_key redacted) and the full `debug_info`.
  - Use These Audio Files: `record_upload` each clip; event with result buckets.
  - Pair Files: event with pairs (number, audio name, image name).
  - Generate Anki Deck: event with card_style, deck_name, tags, pair count.
  - Pair edits (remove/swap): event with what changed.
- Every existing `except Exception as e:` in these handlers calls `record_error(...)` before its `st.error`.
- "Clear All Data" also calls `clear_report`.

### 3. Sidebar UI

At the top of the sidebar, an expander **"🐞 Report an issue"**:
- One-line explanation: the zip contains your uploaded files (documents, recordings, photos), the app's outputs and debug logs — send it to the maintainer.
- `st.text_area("What went wrong?")`.
- `st.button("Prepare report")` → builds the zip (output_dirs = temp_images/images, temp_audio/audio, temp_final/final) and stores the bytes in session state; then a `st.download_button("Download report (.zip)", file_name="anki-report-YYYY-MM-DD-HHMM.zip", mime="application/zip")` appears. Two steps because building the zip on every rerun would be wasteful.
- If preparing fails anyway, show the error (the report button must not take the app down).

## Out of scope

- Uploading reports anywhere / emailing automatically.
- Capturing stdout/print output.
- Size limits or trimming large recordings.

## Testing

- `tests/test_issue_report.py`: upload saved and de-duplicated; redaction (nested, case-insensitive); error records carry a traceback; zip layout (report.json fields, uploads/, outputs/<label>/); missing output dir → skipped not raised; non-JSON-safe debug values stringified; clear removes the dir.
- Streamlit `AppTest` smoke test: app loads, sidebar expander present, pressing "Prepare report" yields a download button with a valid zip containing report.json.
