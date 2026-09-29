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

---

## Revision after Task 1 (controller experiments on the real recording, all four local model sizes)

Always prompting is harmful on small models: with `NUMBER_PROMPT`, `tiny` and `base` transcripts collapse (46 words; whole sections skipped, hallucinated repeated "Four."), yielding only 5–6 clips. Without the prompt they do much better. `small`/`medium` need the prompt (without it `small` misses 9 and `medium` misses 7–8). Two more clip-cutting defects surfaced on the no-prompt transcripts:

- **Empty clips:** when Whisper repeats a number ("Twelve@77 Twelve@78") or emits a spurious one, the clip-end search stops at *any* detected number, including ones that would never be accepted (≤ current), producing 0-length clips.
- **False jumps:** `tiny`/`medium` without prompt hear the Farsi vocab word "naan naan" (card 6) as "Nine Nine", which is accepted (9 > 6) and silently skips 7 and 8, even though "Seven" and "Eight" appear right after.

A prototype of the rules below produced a complete 1–12 with no empty clips on **every** model size (tiny, base, small, medium).

## Revised Global Constraints (supersede "No new function parameters" above)

- The three `transcribe_with_*` functions take a keyword argument `prompt=None`; they pass it through (`initial_prompt=prompt` locally, `prompt=prompt` on Groq/OpenAI) and **omit the kwarg entirely for the APIs when `prompt` is None**. `NUMBER_PROMPT` stays as the module constant; it is no longer hard-wired inside the transcribers.
- New pure function `plan_clip_spans(words, audio_len_ms, clip_duration_ms)` → list of dicts `{'number': str, 'start_ms': float, 'end_ms': float, 'position': int, 'word': str, 'match_type': str, 'score': int|float}` for the **final** sequence (a "1" reset discards earlier spans). It contains all sequencing logic currently inline in `extract_audio_clips`, plus:
  - **Acceptance rule** (one helper, used for both accepting a number and for finding a clip's end): candidate `m` after last accepted `n` is acceptable iff `m == 1`, or `m > n` and NOT (`m > n + 1` and `n + 1` is detected later — scanning forward with `detect_number_at(words, j, n)` from just after the candidate — before any number greater than `m`).
  - **Clip end** = start of the next *acceptable* number (per the rule above, relative to the current number); if none, `number_end + clip_duration_ms`; clamp to `[0, audio_len_ms]`.
- New helper `score_spans(spans)` → `(complete: bool, good: int)` where `good` = spans with `end_ms - start_ms >= 300`, and `complete` = spans non-empty, numbers are exactly `1..len(spans)` in order, and every span is good.
- `extract_audio_clips` flow:
  1. Transcribe with `prompt=NUMBER_PROMPT`; plan spans; score.
  2. If not `complete`: transcribe again with `prompt=None`; plan; score. Keep the no-prompt result only if its `good` is strictly greater; otherwise keep the prompted one.
  3. Write one `{number}.mp3` per final span (no write-then-delete). Return value = number of files written.
  4. Debug info: `detected_numbers` comes from the chosen spans; `transcription`, `total_words`, `first_20_words`, `whisper_info` describe the chosen pass; add `debug_info['whisper_info']['pass'] = "number prompt"` or `"no prompt (fallback)"`. If a transcription pass raises, record the error as today; if the first pass fails, still try the second.
- `app.py`: in the debug expander, after the "Duration" line, add `st.write(f"  - Transcription pass: {whisper_info.get('pass', 'n/a')}")`. Nothing else in the app changes.
- Last-clip duration (`clip_duration_ms` fallback) is **unchanged** in this plan.

---

### Task 2: Prompt-then-fallback transcription and robust clip spans

**Files:**
- Modify: `audio_extractor.py`, `app.py` (one debug line)
- Modify/extend tests: `tests/test_whisper_prompt.py`; new `tests/test_plan_clip_spans.py`

**Reference prototype** (validated on real transcripts; adapt to the spec above, don't copy blindly): `.superpowers/sdd/2026-09-29-whisper-number-prompt/proto.py` in this worktree.

- [ ] **Step 1: Failing tests** for `plan_clip_spans` using synthetic word lists (helper building `{'start','end','raw','norm'}` dicts from `(text, start_s)` pairs, each word 0.5 s long):
  1. Simple sequence `one a b two c d three e` → numbers `1,2,3`; span 1 ends at `two`'s start; last span ends at `three.end + clip_duration_ms`.
  2. Repeated number: `one a two b twelve…`-style — `one a two two b three c` → spans `1,2,3`, span 2 starts after the **first** `two` and ends at `three`, and no span has zero length.
  3. False jump skipped: `one a two b six c nine nine d seven e eight f nine g` (with last=… build so 3–5 exist too, or simply `five a nine nine b six c seven d`) → the early `nine`s are rejected because the expected next number appears later before anything > 9; result is consecutive and the span before the rejected `nine` ends at the real next number, not at the `nine`.
  4. Genuine skip still accepted: `one a two b four c five d` → `1,2,4,5` (3 never appears).
  5. Reset: `2025 x one a two b` → `1,2` only.
  6. `score_spans`: complete for 1..N all ≥300 ms; not complete with a gap; not complete with a 0-length span; `good` counts correctly.
  Plus `extract_audio_clips` tests (monkeypatch `audio_extractor.transcribe_with_local_whisper` with a fake recording each call's `prompt` kwarg and returning scripted word lists; silent WAV input as in Task 1's reset test):
  7. Prompted pass complete → transcriber called once with `prompt=NUMBER_PROMPT`; files match; `whisper_info['pass'] == "number prompt"`.
  8. Prompted pass incomplete, no-prompt pass better → called twice (`NUMBER_PROMPT`, then `None`); files from the second; `pass == "no prompt (fallback)"`.
  9. Prompted pass incomplete, no-prompt not strictly better → keeps prompted.
  10. Return value equals files on disk (keep/adapt Task 1's reset test).
  Update Task 1's backend tests: with `prompt=X` the kwarg is passed; for Groq/OpenAI with `prompt=None` the `prompt` kwarg is absent.
- [ ] **Step 2:** Run, confirm failures.
- [ ] **Step 3:** Implement per Revised Global Constraints. Keep `detect_number_at` unchanged.
- [ ] **Step 4:** Full suite green.
- [ ] **Step 5:** Commit `"Fall back to unprompted Whisper when needed; skip false jumps and empty clips"`.
