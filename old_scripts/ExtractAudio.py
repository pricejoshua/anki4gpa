# split_by_number_phrases_fixed.py
import os
import re
from faster_whisper import WhisperModel
from pydub import AudioSegment

# ---------- CONFIG ----------
INPUT_FILE = "Vocab Unit 1 Session 6.mp3"
OUTPUT_DIR = "words_out"
MODEL_SIZE = "medium"   # medium or large-v2 for better timestamps
DEVICE = "cpu"          # "cuda" if you have a GPU
BUFFER_MS = 300         # padding before/after each saved clip (tune up/down)
# If faster-whisper mis-hears 'e' as '8' you can add {'e':'8'} here, but leave empty 
# unless you need it (it caused trouble before for you).
MISRECOG_NUMBER_MAP = {}   # e.g. {'e':'8'}
# ----------------------------

# canonical english number words -> digit
WORD2DIGIT = {
    "zero":"0","one":"1","two":"2","three":"3","four":"4","five":"5",
    "six":"6","seven":"7","eight":"8","nine":"9","ten":"10","eleven":"11",
    "twelve":"12","thirteen":"13","fourteen":"14","fifteen":"15","sixteen":"16",
    "seventeen":"17","eighteen":"18","nineteen":"19","twenty":"20"
}

NUM_WORDS = set(WORD2DIGIT.keys())

# helper normalizer for token comparisons
def norm_token(s: str) -> str:
    if s is None:
        return ""
    return re.sub(r"[^a-z0-9\-]+", "", s.lower())

def safe_filename_token(s: str) -> str:
    # keep letters, digits and single dash; collapse repeated dashes
    s2 = re.sub(r"[^A-Za-z0-9\-]+", "-", s)
    s2 = re.sub(r"-{2,}", "-", s2).strip("-")
    return s2[:40]  # limit length to avoid filesystem issues

def detect_number_at(words, i):
    """
    words: list of dicts {'start','end','raw','norm'}
    returns (digit_str, skip_count) if number detected at index i, else (None, 0)
    skip_count tells the caller how many tokens to skip (1 or 2 when 'number' + 'one')
    """
    if i >= len(words):
        return None, 0
    raw = words[i]['raw'].lower()
    token = words[i]['norm']

    # exact word like 'one' / 'two'
    if token in WORD2DIGIT:
        return WORD2DIGIT[token], 1

    # a digit like "1"
    if token.isdigit():
        return token, 1

    # 'number' prefix handling: if token is 'number' and next token is a number word, treat together
    if token == 'number':
        if i + 1 < len(words):
            nxt = words[i+1]['norm']
            if nxt in WORD2DIGIT:
                return WORD2DIGIT[nxt], 2
            if nxt.isdigit():
                return nxt, 2
        # just a stray "number" — treat as not-a-number to avoid skipping useful tokens
        return None, 0

    # token might contain both (e.g. "number-one", "numberone", "number_one") or "one."
    # try to extract any number word/digit inside the raw token
    parts = re.findall(r"[A-Za-z]+|\d+", raw)
    for p in parts:
        p_norm = re.sub(r"[^a-z0-9]+", "", p.lower())
        if p_norm in WORD2DIGIT:
            return WORD2DIGIT[p_norm], 1
        if p_norm.isdigit():
            return p_norm, 1

    # check MISRECOG map (optional)
    if token in MISRECOG_NUMBER_MAP:
        return MISRECOG_NUMBER_MAP[token], 1

    return None, 0

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio = AudioSegment.from_file(INPUT_FILE)

    model = WhisperModel(MODEL_SIZE, device=DEVICE)
    segments, info = model.transcribe(INPUT_FILE, word_timestamps=True, vad_filter=True)

    # flatten words into a list for easy sequential processing
    words = []
    for seg in segments:
        for w in seg.words:
            raw = w.word
            words.append({
                'start': w.start,
                'end': w.end,
                'raw': raw,
                'norm': re.sub(r"^[\.\,\!\?\s]+|[\.\,\!\?\s]+$", "", raw.lower())
            })

    if not words:
        print("No words found in transcription.")
        return

    counters = {}   # occurrence counters per number
    i = 0
    saved = 0

    while i < len(words):
        num, skip = detect_number_at(words, i)
        if not num:
            # not a number token → skip until next number (we ignore pre-number words)
            i += 1
            continue

        # found a number at index i; compute block of words that belong to this number:
        # block starts at i + skip, ends right before next number token (or end of words)
        block_start = i + skip
        j = block_start
        while j < len(words):
            nxt_num, _ = detect_number_at(words, j)
            if nxt_num:
                break
            j += 1
        block_end = j - 1  # inclusive, may be < block_start (no words after number)

        # advance the main pointer to j (next number)
        i = j

        # if no words after the number, skip (maybe last number with no following utterance)
        if block_start > block_end:
            print(f"Number {num} at position had no following words; skipping.")
            continue

        # collect the block tokens (raw tokens) and normalized versions
        block_tokens = [words[k]['raw'].strip().lower().replace('.', '') for k in range(block_start, block_end+1)]
        block_norms  = [re.sub(r"[^a-z0-9]+", "", t) for t in block_tokens]

        # attempt to detect an exact repeated-half structure:
        first_tokens = block_tokens
        repeat_tokens = None
        n = len(block_norms)
        if n >= 2 and (n % 2 == 0):
            half = n // 2
            if block_norms[:half] == block_norms[half:half*2]:
                # exact repeated halves -> split into first half + repeat half
                first_tokens = block_tokens[:half]
                repeat_tokens = block_tokens[half:half*2]
                first_start = words[block_start]['start']
                first_end   = words[block_start + half - 1]['end']
                repeat_start = words[block_start + half]['start']
                repeat_end   = words[block_start + 2*half - 1]['end']
        # fallback: if first two tokens are identical and no larger-repeat structure, treat as (single-word) repeat
        elif n >= 2 and block_norms[0] == block_norms[1]:
            first_tokens = [block_tokens[0]]
            repeat_tokens = [block_tokens[1]]
            first_start = words[block_start]['start']
            first_end   = words[block_start]['end']
            repeat_start = words[block_start+1]['start']
            repeat_end   = words[block_start+1]['end']
        else:
            # no repeats detected -> treat entire block as the first phrase
            first_tokens = block_tokens
            first_start = words[block_start]['start']
            first_end   = words[block_end]['end']

        # save first phrase
        counters[num] = counters.get(num, 0) + 1
        occ = counters[num]
        safe_text = "-".join([safe_filename_token(t) for t in first_tokens])
        out_name = f"{num}_word_{occ}_{safe_text}.mp3"
        start_ms = max(0, int(first_start*1000) - BUFFER_MS)
        end_ms   = min(len(audio), int(first_end*1000) + BUFFER_MS)
        clip = audio[start_ms:end_ms]
        clip.export(os.path.join(OUTPUT_DIR, out_name), format="mp3")
        print(f"Saved {out_name} ({first_start:.2f}-{first_end:.2f})")
        saved += 1

        # if we detected a repeat, save it too (use same occ index)
        if repeat_tokens:
            safe_text2 = "-".join([safe_filename_token(t) for t in repeat_tokens])
            out_name2 = f"{num}_word_repeat_{occ}_{safe_text2}.mp3"
            start2_ms = max(0, int(repeat_start*1000) - BUFFER_MS)
            end2_ms   = min(len(audio), int(repeat_end*1000) + BUFFER_MS)
            clip2 = audio[start2_ms:end2_ms]
            clip2.export(os.path.join(OUTPUT_DIR, out_name2), format="mp3")
            print(f"Saved {out_name2} ({repeat_start:.2f}-{repeat_end:.2f})")
            saved += 1

    print(f"\nDone — saved {saved} files to '{OUTPUT_DIR}'.")

if __name__ == "__main__":
    main()
