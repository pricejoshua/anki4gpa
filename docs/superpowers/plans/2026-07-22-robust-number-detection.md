# Robust Number Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `detect_number_at` in `audio_extractor.py` recover spoken number cues that Whisper mishears, without introducing new false positives, by adding a static misrecognition map and a sequence-aware fuzzy-matching fallback.

**Architecture:** `detect_number_at` gains a `last_accepted_number` parameter and tries three tiers in order, stopping at the first hit: (1) exact match — unchanged existing logic; (2) a static misrecognition map (e.g. "won"→1), gated to only the number(s) that would legitimately come next in the sequence; (3) sequence-aware fuzzy matching (`rapidfuzz`) against just those same candidate number(s). Gating tiers 2 and 3 to the specific expected-next number (plus "1" for a reset) is what keeps common English words from being misread as numbers.

**Tech Stack:** Python, pytest, rapidfuzz (new dependency).

## Global Constraints

- Number range stays 0–30 — do not extend `WORD2DIGIT` or add support for numbers above 30 (confirmed out of scope; sessions typically stay under 30 items).
- `rapidfuzz` is an approved new dependency (added to `requirements.txt`).
- Tiers 2 (misrecognition map) and 3 (fuzzy match) must be gated by `last_accepted_number` — never do an unconditional/global lookup against common English words, since that risks false positives on ordinary spoken content (e.g. "for", "too" appearing naturally in an answer).
- `detect_number_at`'s return signature changes from a 2-tuple `(number, skip)` to a 4-tuple `(number, skip, match_type, score)`. Both call sites in `extract_audio_clips` must be updated together (Task 4) — do not leave one on the old signature.
- New tests live in `tests/test_audio_extractor.py`, following the existing style in `tests/test_image_extractor.py` (plain pytest functions, no special fixtures beyond what's needed).

---

## Notes on two refinements vs. the design doc

1. **Misrecognition map is sequence-gated.** The design doc describes the misrecognition map as "still an exact lookup, just a second vocabulary" without specifying gating. While writing this plan, verifying the map's actual token list ("for"/"to"/"too" are common English words, not rare tokens) showed that an *unconditional* lookup would risk misreading ordinary speech as a number cue. This plan gates tier 2 by `last_accepted_number` exactly like tier 3, which preserves the three-tier architecture and detection goal while removing that risk.

2. **`fuzzy_score_for` returns the numeric score, not a bool.** The design doc names the tier-3 helper `fuzzy_match_number(token, candidate_number, threshold) -> bool`. This plan instead has `fuzzy_score_for(token, candidate_number) -> int` return the raw rapidfuzz ratio, with the threshold comparison left to `detect_number_at`. This is needed regardless of naming, since the design doc's own "Data flow" section requires surfacing the numeric `score` in `debug_info` for fuzzy hits — a bool-returning helper would have to be called twice (once for the bool, once for the score) or discard the score entirely.

Both are implementation-level refinements in service of the approved design's stated goals, not scope changes — flagging them here for visibility rather than re-opening brainstorming.

---

## File Structure

- **Modify:** `audio_extractor.py` — add `DIGIT2WORD`/`word_forms_for`, `MISRECOGNITION_MAP`/`_MISRECOGNITION_LOOKUP`, `fuzzy_score_for`, rewrite `detect_number_at`, update both call sites in `extract_audio_clips`.
- **Modify:** `requirements.txt` — add `rapidfuzz`.
- **Create:** `tests/test_audio_extractor.py` — unit tests for `word_forms_for`, `fuzzy_score_for`, and `detect_number_at` (exact/misrecognition/fuzzy/reset-threshold/false-positive-guard cases).

---

### Task 1: `word_forms_for` helper

**Files:**
- Modify: `audio_extractor.py` (add after the `WORD2DIGIT` dict, around line 21)
- Test: `tests/test_audio_extractor.py` (new file)

**Interfaces:**
- Consumes: `WORD2DIGIT` (existing module-level dict in `audio_extractor.py`)
- Produces: `DIGIT2WORD: dict[str, str]`, `word_forms_for(number: int) -> list[str]` — later tasks use `word_forms_for` to build fuzzy-match candidates.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_audio_extractor.py`:

```python
from audio_extractor import word_forms_for


def test_word_forms_for_simple_number():
    assert word_forms_for(7) == ["seven"]


def test_word_forms_for_compound_number():
    assert word_forms_for(21) == ["twentyone", "twenty-one"]


def test_word_forms_for_out_of_range_returns_empty():
    assert word_forms_for(31) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_audio_extractor.py -v`
Expected: FAIL — `ImportError: cannot import name 'word_forms_for' from 'audio_extractor'`

- [ ] **Step 3: Implement `DIGIT2WORD` and `word_forms_for`**

In `audio_extractor.py`, immediately after the `WORD2DIGIT` dict definition (after its closing `}`, currently line 21), add:

```python
DIGIT2WORD = {v: k for k, v in WORD2DIGIT.items()}


def word_forms_for(number):
    """Return known spoken word forms for a number 0-30, for fuzzy matching."""
    compact = DIGIT2WORD.get(str(number))
    if compact is None:
        return []
    forms = [compact]
    if 21 <= number <= 29:
        ones_word = DIGIT2WORD[str(number - 20)]
        forms.append(f"twenty-{ones_word}")
    return forms
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_audio_extractor.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add audio_extractor.py tests/test_audio_extractor.py
git commit -m "Add word_forms_for helper for number fuzzy-matching candidates"
```

---

### Task 2: `fuzzy_score_for` helper + `rapidfuzz` dependency

**Files:**
- Modify: `audio_extractor.py` (add import near top, add function after `word_forms_for`)
- Modify: `requirements.txt`
- Test: `tests/test_audio_extractor.py`

**Interfaces:**
- Consumes: `word_forms_for(number: int) -> list[str]` (Task 1)
- Produces: `fuzzy_score_for(token: str, candidate_number: int) -> int` — later tasks (3) use this inside `detect_number_at`'s fuzzy tier.

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, add a line after `pydub>=0.25.1`:

```
rapidfuzz>=3.0.0
```

Install it into the project's virtualenv:

Run: `pip install rapidfuzz>=3.0.0`
Expected: Successfully installed rapidfuzz-<version>

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_audio_extractor.py`:

```python
from audio_extractor import fuzzy_score_for


def test_fuzzy_score_high_for_close_misspelling():
    assert fuzzy_score_for("sevven", 7) >= 85


def test_fuzzy_score_low_for_unrelated_word():
    assert fuzzy_score_for("banana", 7) < 85


def test_fuzzy_score_zero_for_short_token():
    assert fuzzy_score_for("hi", 7) == 0


def test_fuzzy_score_zero_for_digit_token():
    assert fuzzy_score_for("7", 7) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_audio_extractor.py -v`
Expected: FAIL — `ImportError: cannot import name 'fuzzy_score_for' from 'audio_extractor'`

- [ ] **Step 4: Implement `fuzzy_score_for`**

In `audio_extractor.py`, add the import near the top with the other imports (after `from pydub import AudioSegment`, currently line 9):

```python
from rapidfuzz import fuzz
```

Then add this function immediately after `word_forms_for`:

```python
def fuzzy_score_for(token, candidate_number):
    """Best rapidfuzz similarity ratio (0-100) between token and candidate_number's
    known spoken forms. Returns 0 if token is too short or purely numeric to be a
    meaningful fuzzy-match candidate (digits are handled by the exact-match tier).
    """
    if len(token) < 3 or token.isdigit():
        return 0
    forms = word_forms_for(candidate_number)
    if not forms:
        return 0
    return max(fuzz.ratio(token, form) for form in forms)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_audio_extractor.py -v`
Expected: PASS (7 passed)

- [ ] **Step 6: Commit**

```bash
git add audio_extractor.py requirements.txt tests/test_audio_extractor.py
git commit -m "Add fuzzy_score_for helper and rapidfuzz dependency"
```

---

### Task 3: Rewrite `detect_number_at` with misrecognition + fuzzy tiers

**Files:**
- Modify: `audio_extractor.py:13-59` (the `WORD2DIGIT` block through the end of `detect_number_at`)
- Test: `tests/test_audio_extractor.py`

**Interfaces:**
- Consumes: `word_forms_for` (Task 1), `fuzzy_score_for` (Task 2), existing `WORD2DIGIT`/`norm_token`.
- Produces: `detect_number_at(words, i, last_accepted_number=0) -> (str | None, int, str | None, int | None)` — a 4-tuple `(number_string, tokens_consumed, match_type, score)`, or `(None, 0, None, None)` if no number is detected. `match_type` is one of `"exact"`, `"misrecognition"`, `"fuzzy"`. This is a breaking signature change from the current 2-tuple — Task 4 updates the only two call sites.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_audio_extractor.py`:

```python
from audio_extractor import detect_number_at, norm_token


def _word(raw, start=0.0, end=0.5):
    return {'start': start, 'end': end, 'raw': raw, 'norm': norm_token(raw)}


def test_exact_match_word_number():
    words = [_word("seven")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == ("7", 1, "exact", 100)


def test_exact_match_digit_token():
    words = [_word("7")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == ("7", 1, "exact", 100)


def test_exact_match_number_prefix():
    words = [_word("number"), _word("seven")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == ("7", 2, "exact", 100)


def test_misrecognition_map_hit_when_expected():
    # "won" is a known misrecognition of "one", and last_accepted_number=0
    # means "1" is the expected-next number.
    words = [_word("won")]
    result = detect_number_at(words, 0, last_accepted_number=0)
    assert result == ("1", 1, "misrecognition", 100)


def test_misrecognition_map_gated_by_expected_number():
    # "for" is a known misrecognition of "four", but the sequence here is
    # expecting "7" next (last_accepted_number=6) - "for" must NOT be
    # treated as a number, since it's also just a common English word.
    words = [_word("for")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == (None, 0, None, None)


def test_misrecognition_map_hit_for_common_word_when_expected():
    # Same token "for", but now the sequence is expecting "4" next
    # (last_accepted_number=3), so the misrecognition should fire.
    words = [_word("for")]
    result = detect_number_at(words, 0, last_accepted_number=3)
    assert result == ("4", 1, "misrecognition", 100)


def test_fuzzy_match_accepts_near_miss_spelling():
    # "sevven" is a garbled spelling of "seven"; last_accepted_number=6
    # means "7" is the expected-next number.
    words = [_word("sevven")]
    num, skip, match_type, score = detect_number_at(words, 0, last_accepted_number=6)
    assert num == "7"
    assert skip == 1
    assert match_type == "fuzzy"
    assert score >= 85


def test_fuzzy_match_rejects_unrelated_word():
    words = [_word("banana")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == (None, 0, None, None)


def test_fuzzy_reset_requires_higher_threshold_than_advance():
    # "onne" scores ~85.7 against "one" - enough to pass the advance
    # threshold (85) if "1" were the expected-next number, but here
    # last_accepted_number=6 (expecting "7", which "onne" doesn't
    # resemble), so this exercises the reset-to-1 fuzzy path, which
    # requires a stricter threshold (92) given how destructive a false
    # reset is (it deletes every clip accepted so far).
    words = [_word("onne")]
    result = detect_number_at(words, 0, last_accepted_number=6)
    assert result == (None, 0, None, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_audio_extractor.py -v`
Expected: FAIL — the exact-match tests fail with something like
`AssertionError: assert ('7', 1) == ('7', 1, 'exact', 100)` (current 2-tuple
return doesn't match the new 4-tuple expectation), and the misrecognition/
fuzzy tests fail because those tokens currently return `(None, 0)`.

- [ ] **Step 3: Rewrite `detect_number_at`**

Replace the entire block from `WORD2DIGIT = {` (currently line 13) through
the end of `detect_number_at` (currently line 59) with:

```python
WORD2DIGIT = {
    "zero":"0","one":"1","two":"2","three":"3","four":"4","five":"5",
    "six":"6","seven":"7","eight":"8","nine":"9","ten":"10","eleven":"11",
    "twelve":"12","thirteen":"13","fourteen":"14","fifteen":"15","sixteen":"16",
    "seventeen":"17","eighteen":"18","nineteen":"19","twenty":"20",
    "twentyone":"21","twentytwo":"22","twentythree":"23","twentyfour":"24",
    "twentyfive":"25","twentysix":"26","twentyseven":"27","twentyeight":"28",
    "twentynine":"29","thirty":"30"
}

DIGIT2WORD = {v: k for k, v in WORD2DIGIT.items()}


def word_forms_for(number):
    """Return known spoken word forms for a number 0-30, for fuzzy matching."""
    compact = DIGIT2WORD.get(str(number))
    if compact is None:
        return []
    forms = [compact]
    if 21 <= number <= 29:
        ones_word = DIGIT2WORD[str(number - 20)]
        forms.append(f"twenty-{ones_word}")
    return forms


def fuzzy_score_for(token, candidate_number):
    """Best rapidfuzz similarity ratio (0-100) between token and candidate_number's
    known spoken forms. Returns 0 if token is too short or purely numeric to be a
    meaningful fuzzy-match candidate (digits are handled by the exact-match tier).
    """
    if len(token) < 3 or token.isdigit():
        return 0
    forms = word_forms_for(candidate_number)
    if not forms:
        return 0
    return max(fuzz.ratio(token, form) for form in forms)


# Known ASR misrecognitions, keyed by the digit they should map to.
# Gated by last_accepted_number in detect_number_at (not a global lookup)
# because several of these tokens (e.g. "for", "too") are also common
# English words that could appear in ordinary speech.
MISRECOGNITION_MAP = {
    "1": ["won"],
    "2": ["too", "to"],
    "4": ["for", "fore"],
    "8": ["ate"],
}

_MISRECOGNITION_LOOKUP = {
    token: digit
    for digit, tokens in MISRECOGNITION_MAP.items()
    for token in tokens
}

FUZZY_THRESHOLD_ADVANCE = 85
FUZZY_THRESHOLD_RESET = 92


def norm_token(s):
    """Normalize a token by removing non-alphanumeric characters"""
    return re.sub(r"[^a-z0-9\-]+", "", (s or "").lower())


def detect_number_at(words, i, last_accepted_number=0):
    """
    Detect if a number appears at position i in the words list.

    last_accepted_number is the most recently accepted number in the
    current sequence (0 if none accepted yet). It narrows tiers 2 and 3
    to the specific number(s) that would legitimately come next (the
    expected-next number, and "1" if a reset is currently legal), which
    keeps false positives low on common English words that happen to
    resemble a number.

    Returns (number_string, tokens_consumed, match_type, score) or
    (None, 0, None, None). match_type is one of "exact", "misrecognition",
    "fuzzy". score is 100 for "exact"/"misrecognition", or the rapidfuzz
    ratio (0-100) for "fuzzy".
    """
    if i >= len(words):
        return None, 0, None, None

    raw = words[i]['raw'].lower()
    token = words[i]['norm']

    # Check for "number X" pattern - the "number" prefix already
    # disambiguates intent, so this branch checks the full vocabulary
    # unconditionally (not sequence-gated).
    if token == "number" and i + 1 < len(words):
        nxt = words[i + 1]['norm']
        if nxt in WORD2DIGIT:
            return WORD2DIGIT[nxt], 2, "exact", 100
        if nxt.isdigit():
            return nxt, 2, "exact", 100
        if nxt in _MISRECOGNITION_LOOKUP:
            return _MISRECOGNITION_LOOKUP[nxt], 2, "misrecognition", 100

    # Check if current token is a number word or digit
    if token in WORD2DIGIT:
        return WORD2DIGIT[token], 1, "exact", 100
    if token.isdigit():
        return token, 1, "exact", 100

    # Check normalized version of raw word
    combo = norm_token(raw)
    if combo in WORD2DIGIT:
        return WORD2DIGIT[combo], 1, "exact", 100

    # Tiers 2 and 3 are sequence-gated: only the number(s) that would
    # legitimately come next are considered.
    expected_next = last_accepted_number + 1

    if expected_next <= 30 and token in MISRECOGNITION_MAP.get(str(expected_next), ()):
        return str(expected_next), 1, "misrecognition", 100
    if last_accepted_number > 0 and token in MISRECOGNITION_MAP.get("1", ()):
        return "1", 1, "misrecognition", 100

    if expected_next <= 30:
        score = fuzzy_score_for(token, expected_next)
        if score >= FUZZY_THRESHOLD_ADVANCE:
            return str(expected_next), 1, "fuzzy", score
    if last_accepted_number > 0:
        score = fuzzy_score_for(token, 1)
        if score >= FUZZY_THRESHOLD_RESET:
            return "1", 1, "fuzzy", score

    return None, 0, None, None
```

Note: `word_forms_for` and `fuzzy_score_for` are redefined here in place —
delete the copies added in Tasks 1 and 2 so there's exactly one definition
of each (this task's block replaces the region containing them).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_audio_extractor.py -v`
Expected: PASS (16 passed). Note: this only covers `detect_number_at`
directly — `extract_audio_clips` still calls it with the old 2-tuple
unpacking and will raise `ValueError` at runtime until Task 4. That's
expected at this point; Task 4 fixes it next.

- [ ] **Step 5: Commit**

```bash
git add audio_extractor.py tests/test_audio_extractor.py
git commit -m "Add misrecognition map and sequence-aware fuzzy tier to detect_number_at"
```

---

### Task 4: Wire `last_accepted_number`/`match_type`/`score` into `extract_audio_clips`

**Files:**
- Modify: `audio_extractor.py:271-344` (the clip-extraction loop inside `extract_audio_clips`)

**Interfaces:**
- Consumes: `detect_number_at(words, i, last_accepted_number=0)` returning `(number_string, tokens_consumed, match_type, score)` (Task 3).
- Produces: no new public interface — this task makes `extract_audio_clips` compatible with the Task 3 signature change and surfaces `match_type`/`score` in `debug_info['detected_numbers']`.

- [ ] **Step 1: Update the two call sites and debug info**

In `audio_extractor.py`, inside `extract_audio_clips`, replace the `while i < len(words):` loop (currently lines 271-344) with:

```python
    while i < len(words):
        num, skip, match_type, score = detect_number_at(words, i, last_accepted_number)
        if not num:
            i += 1
            continue

        # Convert num to integer for comparison
        try:
            num_int = int(num)
        except ValueError:
            i += skip
            continue

        # Accept "1" at any point (resets counter), otherwise numbers must be increasing
        if num_int == 1:
            # If this is a reset (not the first "one"), delete all previous clips
            if created_files:
                for file_path in created_files:
                    try:
                        os.remove(file_path)
                    except:
                        pass
                created_files = []
            # Reset counter when we encounter "1" (allows multiple takes)
            last_accepted_number = 0
        elif num_int <= last_accepted_number:
            i += skip  # Skip numbers that are not increasing
            continue

        debug_info['detected_numbers'].append({
            'number': num,
            'position': i,
            'word': words[i]['raw'],
            'match_type': match_type,
            'score': score
        })

        # Get the timestamp where this number ends
        number_end_time = words[i + skip - 1]['end'] * 1000

        # Find the start time of the next number (if any)
        j = i + skip
        next_number_start_time = None
        while j < len(words):
            nxt_num, nxt_skip, _, _ = detect_number_at(words, j, num_int)
            if nxt_num:
                next_number_start_time = words[j]['start'] * 1000
                break
            j += 1

        # Extract audio from end of current number to start of next number
        start_time = number_end_time

        if next_number_start_time is not None:
            # Extract up to the next number
            end_time = next_number_start_time
        else:
            # No next number - extract fixed duration after the number word ends
            end_time = number_end_time + clip_duration_ms

        start_time = max(0, start_time)
        end_time = min(len(audio), end_time)

        clip = audio[start_time:end_time]

        out_name = f"{num}.mp3"
        out_path = os.path.join(output_dir, out_name)
        clip.export(out_path, format="mp3")
        created_files.append(out_path)  # Track created file
        saved += 1
        last_accepted_number = num_int  # Update last accepted number

        if progress_callback:
            progress_callback(50 + int(40 * saved / len(words)), f"Extracted clip {saved}...")

        i = j if j < len(words) else len(words)
```

Note the lookahead call (`nxt_num, nxt_skip, _, _ = detect_number_at(words, j, num_int)`)
passes `num_int` (the number just accepted this iteration), not
`last_accepted_number` — at this point in the loop `last_accepted_number`
still holds the *previous* value, but the lookahead is searching for
whatever comes after the number we just found, so its sequence context
should be `num_int`.

- [ ] **Step 2: Run the full test suite**

Run: `pytest -v`
Expected: PASS (all tests in `tests/test_audio_extractor.py` and
`tests/test_image_extractor.py` pass; no `ValueError` from tuple
unpacking).

- [ ] **Step 3: Confirm no other call sites were missed**

Run: `grep -n "detect_number_at" audio_extractor.py`
Expected: three matches — the `def detect_number_at(...)` line, and the
two call sites just edited, both now unpacking 4 values.

- [ ] **Step 4: Commit**

```bash
git add audio_extractor.py
git commit -m "Wire sequence-aware number detection into extract_audio_clips"
```

---

## Post-plan manual check

`extract_audio_clips` itself has no automated tests (pre-existing gap, out
of scope for this plan) since it requires real audio + a Whisper backend.
After all four tasks are merged, sanity-check with a real recording via the
Streamlit app or the CLI (`python audio_extractor.py <file> <output> --api
local`) and check `debug_info['detected_numbers']` in the debug panel/output
for `match_type`/`score` on any previously-missed numbers.
