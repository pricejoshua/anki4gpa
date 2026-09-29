# Whisper Number Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Stop Whisper from dropping spoken English card numbers in mixed English/Farsi recordings, and fix the clip count reported after a sequence reset.

**Spec (inline, from investigation on a real recording `U02S09.mp3`, not committed):**
- Baseline (`small`, `language="en"`, no prompt): Whisper transcribed the spoken "nine" as `naan` (`eight pudresir pudresir naan panir ten`), so card 9 was never detected and clip 8 swallowed it. It also dropped several repeated vocab words.
- Passing an `initial_prompt` listing the number words (`"One, two, three, … thirty."`) made Whisper output `Nine.` at the same timestamp, recovered the dropped repeats, and the unchanged clip-cutting pipeline produced clips 1–12 with sensible lengths. A 1–20 prompt and a 1–30 prompt both worked.
- Separate bug seen in the same run: `extract_audio_clips` returned 13 for 12 files on disk. A spurious early number (`2025` from "October 23rd, 2025") creates a clip, then "one" resets the sequence and deletes it, but `saved` is not decremented.

**Architecture:** `audio_extractor.py` only.

## Global Constraints

- Add a module-level constant `NUMBER_PROMPT` built from the existing number vocabulary (not hand-typed): the spoken forms for 1..30 in order, comma-separated, first letter capitalised, ending with a period — i.e. `"One, two, three, …, twenty, twenty-one, …, twenty-nine, thirty."`. Use `word_forms_for(n)` so 21–29 use the hyphenated form (`word_forms_for` returns `[compact, hyphenated]` for 21–29; use the hyphenated one, which is the last element).
- Pass it on every backend:
  - local: `model.transcribe(..., initial_prompt=NUMBER_PROMPT)`
  - Groq: `client.audio.transcriptions.create(..., prompt=NUMBER_PROMPT)`
  - OpenAI: `client.audio.transcriptions.create(..., prompt=NUMBER_PROMPT)`
- No new function parameters / UI settings (YAGNI).
- Reset bug: when a "1" resets the sequence and previously created files are deleted, the returned clip count must equal the number of clip files actually on disk. (Simplest: derive the final count from `len(created_files)` of the surviving sequence, or decrement `saved` by the number deleted — implementer's choice; progress messages may keep using a running counter.)
- Nothing else in `extract_audio_clips` changes (clip boundaries, last-clip duration, detection tiers).

---

### Task 1: Number prompt on all backends + correct count after reset

**Files:**
- Modify: `audio_extractor.py`
- Create: `tests/test_whisper_prompt.py` (or add to `tests/test_audio_extractor.py` if it reads better — implementer's choice)

- [ ] **Step 1: Failing tests** (no network, no real Whisper model):
  1. `NUMBER_PROMPT` starts with `"One, two, three"`, contains `"nine"`, `"twenty-one"`, ends with `"thirty."`, and has exactly 30 comma-separated items.
  2. Local backend passes the prompt: monkeypatch `faster_whisper.WhisperModel` (the function imports it inside) with a fake whose `transcribe` records kwargs and returns `([], info)`; assert `initial_prompt == NUMBER_PROMPT`. Skip cleanly with `pytest.importorskip("faster_whisper")` if not installed.
  3. Groq and OpenAI pass `prompt=NUMBER_PROMPT`: monkeypatch `groq.Groq` / `openai.OpenAI` with fakes whose `.audio.transcriptions.create(**kw)` records kwargs and returns an object with `words=[]`, `text=""`. Use `importorskip` for each package. Use a tiny temp file as `audio_path`.
  4. Reset count: monkeypatch `audio_extractor.transcribe_with_local_whisper` to return a word list like `2025@1s, one@2s, apple@3s, two@4s, pear@5s` (dicts with `start`, `end`, `raw`, `norm`), feed a short generated silent WAV (pydub `AudioSegment.silent(7000)` exported to tmp), call `extract_audio_clips(wav, out_dir)`; assert return value `== 2` and `sorted(os.listdir(out_dir)) == ["1.mp3", "2.mp3"]`. (Needs ffmpeg for mp3 export; root `conftest.py` already adds static-ffmpeg to PATH.)
- [ ] **Step 2:** Run the new tests, confirm the expected failures.
- [ ] **Step 3:** Implement per Global Constraints.
- [ ] **Step 4:** `.venv/bin/python -m pytest -q` — all pass.
- [ ] **Step 5:** Commit `"Prompt Whisper with number words; fix clip count after sequence reset"`.
