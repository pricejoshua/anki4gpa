import os
import re
from faster_whisper import WhisperModel
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

# ---------- CONFIG ----------
INPUT_FILE = "Unit 2 session 9 picture dictionaryextra.mp3"
OUTPUT_DIR = "words_out"
MODEL_SIZE = "medium"
DEVICE = "cpu"
BUFFER_MS = 400
# --- Silence-based tuning (Option B) ---
MIN_SILENCE_LEN_MS = 40     # detect very short pauses
SILENCE_THRESH_DB = 10      # how far below avg loudness counts as silence
MERGE_GAP_MS = 470          # merge close nonsilent chunks
NUMBER_TRIM_MS = 10         # trim off “number” transitions
# ----------------------------

# English number words up to 30
WORD2DIGIT = {
    "zero":"0","one":"1","two":"2","three":"3","four":"4","five":"5",
    "six":"6","seven":"7","eight":"8","nine":"9","ten":"10","eleven":"11",
    "twelve":"12","thirteen":"13","fourteen":"14","fifteen":"15","sixteen":"16",
    "seventeen":"17","eighteen":"18","nineteen":"19","twenty":"20",
    "twentyone":"21","twentytwo":"22","twentythree":"23","twentyfour":"24",
    "twentyfive":"25","twentysix":"26","twentyseven":"27","twentyeight":"28",
    "twentynine":"29","thirty":"30"
}
NUM_WORDS = set(WORD2DIGIT.keys())

def norm_token(s: str) -> str:
    return re.sub(r"[^a-z0-9\-]+", "", (s or "").lower())

def safe_filename_token(s: str) -> str:
    s2 = re.sub(r"[^A-Za-z0-9\-]+", "-", s)
    s2 = re.sub(r"-{2,}", "-", s2).strip("-")
    return s2[:40]

def detect_number_at(words, i):
    if i >= len(words):
        return None, 0
    raw = words[i]['raw'].lower()
    token = words[i]['norm']

    # detect “number” prefix
    if token == "number" and i + 1 < len(words):
        nxt = words[i + 1]['norm']
        if nxt in WORD2DIGIT:
            return WORD2DIGIT[nxt], 2
        if nxt.isdigit():
            return nxt, 2

    # direct number word
    if token in WORD2DIGIT:
        return WORD2DIGIT[token], 1
    # digit like “8”
    if token.isdigit():
        return token, 1

    # concatenated forms like "number-one", "twenty-one"
    combo = norm_token(raw)
    if combo in WORD2DIGIT:
        return WORD2DIGIT[combo], 1

    return None, 0

# --- Helper: silence-based utterance splitter (Option B) ---
def split_region_on_silence(region, offset_ms):
    """Return absolute [start_ms, end_ms] pairs for each voiced interval."""
    if region.dBFS == float("-inf"):
        return []
    silence_thresh = max(region.dBFS - SILENCE_THRESH_DB, -50)
    nonsilent = detect_nonsilent(region,
                                 min_silence_len=MIN_SILENCE_LEN_MS,
                                 silence_thresh=silence_thresh)
    # merge close intervals
    merged = []
    if nonsilent:
        s0, e0 = nonsilent[0]
        for s, e in nonsilent[1:]:
            if s - e0 <= MERGE_GAP_MS:
                e0 = e
            else:
                merged.append([s0 + offset_ms, e0 + offset_ms])
                s0, e0 = s, e
        merged.append([s0 + offset_ms, e0 + offset_ms])
    return merged


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    audio = AudioSegment.from_file(INPUT_FILE)
    model = WhisperModel(MODEL_SIZE, device=DEVICE)
    segments, info = model.transcribe(INPUT_FILE, word_timestamps=True, vad_filter=True)

    # flatten words
    words = []
    for seg in segments:
        for w in seg.words:
            words.append({
                'start': w.start,
                'end': w.end,
                'raw': w.word,
                'norm': norm_token(w.word)
            })

    if not words:
        print("No words found in transcription.")
        return

    counters = {}
    i = 0
    saved = 0

    while i < len(words):
        num, skip = detect_number_at(words, i)
        if not num:
            i += 1
            continue

        block_start = i + skip
        j = block_start
        while j < len(words):
            nxt_num, _ = detect_number_at(words, j)
            if nxt_num:
                break
            j += 1
        block_end = j - 1
        i = j

        if block_start > block_end:
            print(f"Number {num} had no following words — skipping.")
            continue

        first_start = words[block_start]['start']
        first_end = words[block_end]['end']

        # --- Option B: Split region by real pauses ---
        region_start_ms = int(first_start * 1000)
        region_end_ms = int(first_end * 1000)
        region = audio[region_start_ms:region_end_ms]
        utterances = split_region_on_silence(region, region_start_ms)

        # fallback if nothing detected
        if not utterances:
            utterances = [[region_start_ms, region_end_ms]]

        counters[num] = counters.get(num, 0) + 1
        occ = counters[num]

        for u_idx, (s_ms, e_ms) in enumerate(utterances, start=1):
            s_ms = max(0, s_ms - BUFFER_MS)
            e_ms = min(len(audio), e_ms + BUFFER_MS)
            clip = audio[s_ms:e_ms]

            out_name = f"{num}_word_{occ}_{u_idx}.mp3"
            clip.export(os.path.join(OUTPUT_DIR, out_name), format="mp3")
            print(f"Saved {out_name} ({s_ms/1000:.2f}-{e_ms/1000:.2f}s)")
            saved += 1

    print(f"\nDone — saved {saved} files to '{OUTPUT_DIR}'.")


if __name__ == "__main__":
    main()
