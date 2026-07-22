# Robust Number Detection — Design

## Problem

`audio_extractor.py` splits a recording into numbered vocab clips by scanning
Whisper's word timestamps for spoken number cues ("one", "number two", "7",
...) via `detect_number_at`, matched against the static `WORD2DIGIT` table
(0–30). The primary failure mode is **missed numbers**: when Whisper
mishears a number word, there's no fallback, so that clip's boundary is lost
and everything downstream shifts.

Scope note: sessions typically stay under 30 items, so the existing 0–30
range is sufficient — this design does not extend the numeric range.

## Approach

Three-tier detection in `detect_number_at`, in order, stopping at the first
hit:

1. **Exact match** (existing logic, unchanged) — digit tokens, `WORD2DIGIT`
   entries, "number X" prefix handling.
2. **Static misrecognition map** — a hardcoded dict of known ASR confusions
   (e.g. `"won"→"1"`, `"too"→"2"`, `"ate"→"8"`), still an exact lookup
   against a second vocabulary. Seeded from the old script's
   `MISRECOG_NUMBER_MAP`.
3. **Sequence-aware fuzzy match** — only reached if tiers 1–2 miss. The
   algorithm already knows what number is valid next (strictly increasing
   from `last_accepted_number`, or a reset to 1), so instead of fuzzy-matching
   against the full 0–30 vocabulary, it only compares the current token
   against the word form(s) of the *specific* expected-next number (and "1"
   if a reset is legal at this point). This keeps false-positive risk low
   despite loosening the match — a random unrelated word is unlikely to
   closely resemble the one or two numbers that are actually valid right now.

This was chosen over (a) a purely static expanded misrecognition table
(doesn't generalize to unseen mishearings) and (b) an LLM post-processing
pass (adds latency/cost/non-determinism disproportionate to the problem).

## Components

- `MISRECOGNITION_MAP: dict[str, str]` — new module-level constant, token →
  digit string.
- `word_forms_for(number: int) -> list[str]` — returns spoken form(s) for a
  candidate number (e.g. `21 → ["twenty one", "twentyone"]`), built from
  `WORD2DIGIT` plus a compound generator for 21–30 (avoids hand-maintaining
  two parallel tables).
- `fuzzy_match_number(token: str, candidate_number: int, threshold: int) -> bool`
  — wraps `rapidfuzz.fuzz.ratio`. Only invoked on alphabetic tokens of length
  ≥ 3 (skips digits/punctuation/single letters, where fuzzy scoring is
  unreliable).
- `detect_number_at(words, i, last_accepted_number=0)` — signature gains
  `last_accepted_number`. Tiers 1–2 unchanged. Tier 3 added at the end.
  Return value gains a third element: `match_type`
  (`"exact" | "misrecognition" | "fuzzy"`).

## Data flow / thresholds

- Expected-next candidate: fuzzy threshold **85** (ratio 0–100).
- Reset-to-"1" candidate: fuzzy threshold **92** — stricter, because a false
  reset is destructive (deletes every clip accepted so far in the current
  sequence).
- Both call sites in `extract_audio_clips` (the main forward scan and the
  lookahead that finds where the current clip ends) already track
  `last_accepted_number` in the enclosing loop, so threading it into
  `detect_number_at` calls is a small, local change — no new state needed.
- `debug_info['detected_numbers']` gains `match_type` and (for fuzzy hits)
  `score`, so the Streamlit debug panel shows why each number was accepted.

## Error handling

No new failure modes — `rapidfuzz` is a pure scoring function with no I/O.
Add `rapidfuzz` to `requirements.txt`.

## Testing

New `tests/test_audio_extractor.py` (pytest, matching the style of the
existing `tests/test_image_extractor.py` — no audio fixtures needed since
`detect_number_at`/helpers operate on plain word-dict lists, not real audio):

- Exact-match cases (regression coverage — currently untested at all).
- Static misrecognition map hits (e.g. "won" → accepted as "1").
- Fuzzy match accepts a near-miss spelling of the expected-next number.
- Fuzzy match rejects an unrelated word sharing some letters (false-positive
  guard).
- Reset-to-1 fuzzy threshold: a middling-similarity word should NOT trigger
  a reset (higher bar than a normal advance).
- `word_forms_for` compound generation for 21–30.
