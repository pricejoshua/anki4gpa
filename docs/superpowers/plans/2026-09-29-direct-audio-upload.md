# Direct Audio Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users in Tab 2 upload individual numbered audio clips (`1.mp3`, `2.m4a`, …) directly, as an alternative to extracting clips from one long recording with Whisper — mirroring the existing "🖼️ Upload Photos Directly" option in Tab 1.

**Spec:** Mirrors `docs/superpowers/specs/2026-07-17-direct-photo-upload-design.md` (read it — same UX, naming rule, skip buckets, and non-fail-fast behaviour), with audio substituted for images:

| Photo feature | Audio equivalent |
|---|---|
| `save_numbered_photos(uploads, output_folder)` in `image_extractor.py` | `save_numbered_audio(uploads, output_folder)` in `audio_extractor.py` |
| Pillow open → `.convert("RGBA").save(..., "PNG")` → `{num}.png` | pydub `AudioSegment.from_file` decode → `{num}.mp3` |
| `temp_images` / `image_files` | `temp_audio` / `audio_files` |
| radio `"📄 Extract from Word Document"` / `"🖼️ Upload Photos Directly"` | radio `"🎙️ Extract from Recording"` / `"🔊 Upload Audio Clips Directly"` |
| button "Use These Photos" | button "Use These Audio Files" |

Downstream (`file_pairer.py`, `deck_creator.py`, Tab 2's existing clip list/download/preview block, Tabs 3–4) already consume numbered `.mp3` files in `temp_audio` and need **no changes**.

**Tech Stack:** Python 3, Streamlit, pydub (+ ffmpeg/ffprobe, already in the Dockerfile). Dev-only: `static-ffmpeg` so tests can run on machines without system ffmpeg.

## Global Constraints

- Accepted upload types: `mp3, m4a, aac, wav, ogg, flac`.
- Filename → card number: first `re.search(r'\d+', os.path.splitext(filename)[0])` match (filename stem, extension excluded), as `int` (same as photos).
- Process uploads sorted by filename; duplicate numbers keep the alphabetically-first file.
- Check order per file: no number → `skipped_no_number`; number already used → `skipped_duplicate`; decode fails (any exception from `AudioSegment.from_file`) → `skipped_unreadable`. Not fail-fast.
- Output is always `{num}.mp3` in `output_folder` (created if missing). If the upload's extension is `.mp3` (case-insensitive) and it decodes, write the **original bytes unchanged** (no re-encode). Otherwise export the decoded segment with `format="mp3"` (same call style as `extract_audio_clips`' `clip.export(out_path, format="mp3")`).
- Return dict keys exactly: `'saved'` (sorted `list[int]`), `'skipped_no_number'`, `'skipped_duplicate'`, `'skipped_unreadable'` (`list[str]` filenames).
- The Whisper "Settings" popover and the single-file recording uploader/button appear **only** in the "🎙️ Extract from Recording" branch; that branch's behaviour is otherwise unchanged. The existing clip display block (header "Extracted Audio Clips", download-all zip, previews) stays shared below both branches.

---

### Task 1: `save_numbered_audio()` + unit tests + test ffmpeg setup

**Files:**
- Modify: `audio_extractor.py` (add function; nothing else changes)
- Modify: `requirements-dev.txt` (add `static-ffmpeg>=2.5`)
- Modify: `conftest.py` (currently empty)
- Create: `tests/test_save_numbered_audio.py`

- [ ] **Step 1: `conftest.py`** — make ffmpeg/ffprobe available for tests when the system lacks them:

```python
import shutil

if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass
```

and add `static-ffmpeg>=2.5` to `requirements-dev.txt`. (It is already installed in `.venv`.)

- [ ] **Step 2: Write failing tests** in `tests/test_save_numbered_audio.py`. Generate fixtures with pydub, e.g.:

```python
from io import BytesIO
from pydub import AudioSegment
from pydub.generators import Sine

def _audio_bytes(fmt="wav", ms=300, freq=440):
    buf = BytesIO()
    Sine(freq).to_audio_segment(duration=ms).export(buf, format=fmt)
    return buf.getvalue()
```

Required cases (mirror `tests/test_image_extractor.py`):
1. wav + mp3 uploads (`1.wav`, `2.mp3`) → `saved == [1, 2]`, files `1.mp3`, `2.mp3`; each decodes with `AudioSegment.from_file(path)` to roughly the input length (±100 ms).
2. `.mp3` upload is written byte-for-byte identical to the input.
3. Number extracted from anywhere in filename (`vocab-3-final.m4a` or `.ogg` fixture → `3.mp3`).
4. No number → `skipped_no_number`, nothing written.
5. Duplicate number keeps alphabetically-first (`1.wav` vs `1_dup.wav`, different freqs — assert the kept file is the `1.wav` one, e.g. compare to `1.wav`'s decoded length or use different durations).
6. Undecodable bytes (`b"not audio"`, name `1.mp3`) → `skipped_unreadable`, nothing written.
7. Creates missing nested output folder.

- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/test_save_numbered_audio.py -q` — fails (ImportError).
- [ ] **Step 4: Implement** `save_numbered_audio` in `audio_extractor.py` (place after `extract_audio_clips`, before `__main__`), with a docstring in the style of `save_numbered_photos`. Use `BytesIO` for decoding.
- [ ] **Step 5: Run** full suite `.venv/bin/python -m pytest -q` — all pass.
- [ ] **Step 6: Commit** `"Add save_numbered_audio for direct numbered clip uploads"`.

---

### Task 2: Tab 2 source toggle wired to `save_numbered_audio`

**Files:**
- Modify: `app.py` (Tab 2 only, plus import line)

**Interfaces:** consumes `save_numbered_audio(uploads: list[tuple[str, bytes]], output_folder: str) -> dict` from Task 1.

- [ ] **Step 1:** Import `save_numbered_audio` alongside `extract_audio_clips`.
- [ ] **Step 2:** At the top of `with tab2:` (after `st.header`), add:

```python
    audio_source = st.radio(
        "Audio source",
        ["🎙️ Extract from Recording", "🔊 Upload Audio Clips Directly"],
        key="audio_source_mode",
        horizontal=True,
    )
```

Wrap the existing description markdown, Settings popover, `audio_file` uploader, and "Extract Audio Clips" button handling in `if audio_source == "🎙️ Extract from Recording":` (re-indent only; no logic changes). Leave the shared display block (`if st.session_state.audio_files:` …) outside the if/else, as Tab 1 does.

- [ ] **Step 3:** `else:` branch, mirroring Tab 1's photo branch:
  - `st.markdown` explaining naming: "Upload individual audio clips named with their card number, e.g. `1.mp3`, `2.mp3` — the first number found anywhere in the filename is used, so `clip_3.m4a` or `word-3.wav` both become card 3. Non-MP3 files are converted to MP3."
  - `st.file_uploader("Upload Audio Clips", type=['mp3', 'm4a', 'aac', 'wav', 'ogg', 'flac'], accept_multiple_files=True, key='audio_clips', help="Drag and drop files or click Browse files")`
  - Button `"Use These Audio Files"`, `key='use_audio_clips_btn'`. Empty → `st.error("Please upload audio files first")`. Else, inside `try` / `st.spinner("Processing audio files...")`: rmtree old `temp_audio` if set, `tempfile.mkdtemp(prefix="anki_audio_")`, call `save_numbered_audio([(f.name, f.getvalue()) for f in files], ...)`, rebuild `st.session_state.audio_files` with the same `.mp3` filter + sort lambda the recording branch uses, `st.success(f"Loaded {len(result['saved'])} audio clips!")`, then one `st.warning` per non-empty skip bucket with the same wording pattern as the photo branch ("Skipped (no number found in filename): …", "Skipped (duplicate number, first one kept): …", "Skipped (unreadable audio file): …"). `except Exception as e: st.error(f"Error processing audio files: {str(e)}")`.
- [ ] **Step 4: Verify** `python -c "import ast,sys; ast.parse(open('app.py').read())"` and full test suite pass. If practical, run `.venv/bin/streamlit run app.py --server.headless true --server.port 8599` briefly and confirm it starts without exceptions (then stop it); skip if streamlit isn't installed in `.venv` and say so in the report.
- [ ] **Step 5: Commit** `"Add direct audio clip upload option to Tab 2"`.
