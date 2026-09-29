"""
Audio extraction using Whisper AI
Based on ExtractAudioUpdated.py - transcribes audio and extracts numbered vocabulary clips
Supports: Local (faster-whisper), Groq API, OpenAI API
"""

import os
import re
from io import BytesIO
from pydub import AudioSegment
from rapidfuzz import fuzz


# Number word to digit mapping
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


# Spoken forms of 1..30, used to bias Whisper toward transcribing card numbers
# (otherwise e.g. "nine" in mixed English/Farsi audio is often misheard).
# Local models too small to benefit from the number prompt (it derails them)
UNPROMPTED_MODEL_SIZES = ("tiny", "base")
NUMBER_PROMPT = ", ".join(word_forms_for(n)[-1] for n in range(1, 31)).capitalize() + "."


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


MIN_GOOD_CLIP_MS = 1000
LAST_CLIP_PAUSE_MS = 1000
LAST_CLIP_TAIL_MS = 300
LAST_CLIP_MAX_LEAD_MS = 5000


def _is_acceptable(words, j, skip, candidate, last):
    """
    Whether a candidate number detected at words[j] (consuming skip tokens)
    may follow last in the sequence: "1" always may (a reset); otherwise it
    must be greater than last. A jump past last + 1 is rejected when
    last + 1 is still detected later, before any number greater than the
    candidate (e.g. a vocab word heard as "nine" right before "six").
    """
    if candidate == 1:
        return True
    if candidate <= last:
        return False
    if candidate == last + 1:
        return True

    k = j + skip
    while k < len(words):
        num, num_skip, _, _ = detect_number_at(words, k, last)
        if num:
            if int(num) == last + 1:
                return False
            if int(num) > candidate:
                return True
        k += max(num_skip, 1)
    return True


def plan_clip_spans(words, audio_len_ms, clip_duration_ms):
    """
    Decide which detected numbers become clips and where each clip starts/ends.

    Numbers must increase from 1; a "1" restarts the sequence and discards
    earlier spans. A clip runs from the end of its number word to the start
    of the next acceptable number. If there is none (the last clip), it runs
    to the end of the last word before a pause longer than LAST_CLIP_PAUSE_MS
    (walking the words after the number), plus LAST_CLIP_TAIL_MS. The gap
    between the number and the first following word is not checked for a
    pause, but if it exceeds LAST_CLIP_MAX_LEAD_MS the walk is skipped.
    clip_duration_ms past the number word is used only when no words follow
    it or that lead is too long. All clamped to the audio.

    Returns a list of dicts with keys number, start_ms, end_ms, position,
    word, match_type, score.
    """
    spans = []
    last = 0
    i = 0

    while i < len(words):
        num, skip, match_type, score = detect_number_at(words, i, last)
        if not num or not _is_acceptable(words, i, skip, int(num), last):
            i += max(skip, 1)
            continue

        n = int(num)
        if n == 1:
            spans = []

        start_ms = words[i + skip - 1]['end'] * 1000

        # Find the next number that could follow this one
        j = i + skip
        while j < len(words):
            nxt, nxt_skip, _, _ = detect_number_at(words, j, n)
            if nxt and _is_acceptable(words, j, nxt_skip, int(nxt), n):
                break
            j += max(nxt_skip, 1)

        if j < len(words):
            end_ms = words[j]['start'] * 1000
        else:
            following = words[i + skip:]
            if following and (following[0]['start'] * 1000 - start_ms) <= LAST_CLIP_MAX_LEAD_MS:
                kept = following[0]
                for w in following[1:]:
                    if (w['start'] - kept['end']) * 1000 > LAST_CLIP_PAUSE_MS:
                        break
                    kept = w
                end_ms = kept['end'] * 1000 + LAST_CLIP_TAIL_MS
            else:
                end_ms = start_ms + clip_duration_ms

        spans.append({
            'number': num,
            'start_ms': min(max(0, start_ms), audio_len_ms),
            'end_ms': min(max(0, end_ms), audio_len_ms),
            'position': i,
            'word': words[i]['raw'],
            'match_type': match_type,
            'score': score
        })
        last = n
        i = j

    return spans


def score_spans(spans):
    """
    Returns (complete, good): good is the number of spans at least
    MIN_GOOD_CLIP_MS long; complete means the spans are exactly 1..N in
    order and all of them are good.
    """
    good = sum(1 for s in spans if s['end_ms'] - s['start_ms'] >= MIN_GOOD_CLIP_MS)
    complete = (bool(spans)
                and [int(s['number']) for s in spans] == list(range(1, len(spans) + 1))
                and good == len(spans))
    return complete, good


def transcribe_with_local_whisper(audio_path, model_size="small", use_vad=False, prompt=None):
    """Transcribe using local faster-whisper model"""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=use_vad,
        language="en",
        initial_prompt=prompt
    )

    # Convert to list and extract words
    segments_list = list(segments)
    words = []
    full_transcription = []

    for seg in segments_list:
        if hasattr(seg, 'text'):
            full_transcription.append(seg.text)

        if hasattr(seg, 'words') and seg.words:
            for w in seg.words:
                words.append({
                    'start': w.start,
                    'end': w.end,
                    'raw': w.word,
                    'norm': norm_token(w.word)
                })

    return words, ' '.join(full_transcription), {
        'language': getattr(info, 'language', 'en'),
        'duration': getattr(info, 'duration', 0),
        'segments': len(segments_list)
    }


def transcribe_with_groq(audio_path, api_key=None, prompt=None):
    """Transcribe using Groq Whisper API"""
    from groq import Groq

    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found. Set it as environment variable or pass as parameter.")

    client = Groq(api_key=api_key)

    # Omit the kwarg without a prompt (the SDK would otherwise send an explicit null)
    prompt_kwargs = {"prompt": prompt} if prompt is not None else {}
    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"],
            **prompt_kwargs
        )

    # Extract words with timestamps
    words = []
    if hasattr(transcription, 'words') and transcription.words:
        for w in transcription.words:
            words.append({
                'start': w.start,
                'end': w.end,
                'raw': w.word,
                'norm': norm_token(w.word)
            })

    return words, transcription.text, {
        'language': getattr(transcription, 'language', 'en'),
        'duration': getattr(transcription, 'duration', 0),
        'segments': len(words)
    }


def transcribe_with_openai(audio_path, api_key=None, prompt=None):
    """Transcribe using OpenAI Whisper API"""
    from openai import OpenAI

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found. Set it as environment variable or pass as parameter.")

    client = OpenAI(api_key=api_key)

    # Omit the kwarg without a prompt (the SDK would otherwise send an explicit null)
    prompt_kwargs = {"prompt": prompt} if prompt is not None else {}
    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"],
            **prompt_kwargs
        )

    # Extract words with timestamps
    words = []
    if hasattr(transcription, 'words') and transcription.words:
        for w in transcription.words:
            words.append({
                'start': w.start,
                'end': w.end,
                'raw': w.word,
                'norm': norm_token(w.word)
            })

    return words, transcription.text, {
        'language': getattr(transcription, 'language', 'en'),
        'duration': getattr(transcription, 'duration', 0),
        'segments': len(words)
    }


def extract_audio_clips(input_file, output_dir, model_size="small", buffer_ms=400,
                       use_vad=False, api_type="local", api_key=None,
                       progress_callback=None, debug=False, clip_duration_ms=3000):
    """
    Extract numbered audio clips using Whisper transcription.

    Args:
        input_file: Path to input audio file
        output_dir: Directory to save extracted clips
        model_size: Whisper model size (tiny, base, small, medium, large) - only for local
        buffer_ms: Buffer time in milliseconds to add before each clip
        use_vad: Use Voice Activity Detection filter - only for local
        api_type: "local" (faster-whisper), "groq" (Groq API), or "openai" (OpenAI API)
        api_key: API key for Groq/OpenAI (if not set in environment)
        progress_callback: Optional callback(percent, message)
        debug: Return detailed debug information
        clip_duration_ms: Fallback length in milliseconds for the last clip, used when no words
            follow its number or they start more than LAST_CLIP_MAX_LEAD_MS
            later (default: 3000ms)

    Returns:
        Number of clips extracted, or (count, debug_info) if debug=True
    """

    os.makedirs(output_dir, exist_ok=True)

    if api_type not in ("local", "groq", "openai"):
        debug_info = {
            'total_words': 0, 'transcription': '', 'first_20_words': [],
            'detected_numbers': [], 'whisper_info': {},
            'errors': [f"Invalid api_type: {api_type}. Must be 'local', 'groq', or 'openai'"],
            'audio_duration': 0.0, 'api_type': api_type
        }
        return (0, debug_info) if debug else 0

    if progress_callback:
        progress_callback(10, "Loading audio file...")

    # Load audio
    audio = AudioSegment.from_file(input_file)

    # Convert to WAV for better compatibility
    import tempfile
    temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_wav_path = temp_wav.name
    temp_wav.close()
    best = None
    try:
        audio.export(temp_wav_path, format='wav')

        # Detailed debug info
        debug_info = {
            'total_words': 0,
            'transcription': '',
            'first_20_words': [],
            'detected_numbers': [],
            'whisper_info': {},
            'errors': [],
            'audio_duration': len(audio) / 1000.0,
            'api_type': api_type
        }

        def transcribe(prompt):
            if api_type == "local":
                return transcribe_with_local_whisper(
                    temp_wav_path,
                    model_size=model_size,
                    use_vad=use_vad,
                    prompt=prompt
                )
            elif api_type == "groq":
                return transcribe_with_groq(temp_wav_path, api_key=api_key, prompt=prompt)
            elif api_type == "openai":
                return transcribe_with_openai(temp_wav_path, api_key=api_key, prompt=prompt)

        # The number prompt helps larger models hear card numbers but can derail
        # small ones, so retry without it unless the prompted pass found a
        # complete sequence, and keep whichever pass yields more usable clips.
        if api_type == "local" and model_size in UNPROMPTED_MODEL_SIZES:
            passes = (("no prompt (model too small for prompt)", None),)
        else:
            passes = (("number prompt", NUMBER_PROMPT), ("no prompt (fallback)", None))
        for pass_name, prompt in passes:
            if progress_callback:
                progress_callback(30, f"Transcribing audio with {api_type.upper()} Whisper ({pass_name})...")

            try:
                words, transcription, info = transcribe(prompt)
            except Exception as e:
                debug_info['errors'].append(f"Transcription error ({pass_name}): {str(e)}")
                import traceback
                debug_info['errors'].append(traceback.format_exc())
                continue

            if progress_callback:
                progress_callback(40, f"Found {len(words)} words...")

            spans = plan_clip_spans(words, len(audio), clip_duration_ms)
            complete, good = score_spans(spans)
            if best is None or good > best['good']:
                best = {'pass': pass_name, 'words': words, 'transcription': transcription,
                        'info': info, 'spans': spans, 'good': good}
            if complete:
                break

    finally:
        try:
            os.unlink(temp_wav_path)
        except OSError:
            pass

    if best is None:
        return (0, debug_info) if debug else 0

    words = best['words']
    debug_info['whisper_info'] = {**best['info'], 'pass': best['pass']}
    debug_info['total_words'] = len(words)
    debug_info['transcription'] = best['transcription']
    debug_info['first_20_words'] = [f"{w['raw']} (norm: {w['norm']})" for w in words[:20]]

    if progress_callback:
        progress_callback(50, "Extracting audio clips...")

    spans = best['spans']
    saved = 0
    for span in spans:
        debug_info['detected_numbers'].append({
            key: span[key] for key in ('number', 'position', 'word', 'match_type', 'score')
        })

        clip = audio[span['start_ms']:span['end_ms']]
        clip.export(os.path.join(output_dir, f"{span['number']}.mp3"), format="mp3")
        saved += 1

        if progress_callback:
            progress_callback(50 + int(40 * saved / len(spans)), f"Extracted clip {saved}...")

    if progress_callback:
        progress_callback(100, f"Extracted {saved} clips!")

    return (saved, debug_info) if debug else saved


def save_numbered_audio(uploads, output_folder):
    """
    Saves directly-uploaded audio clips as numbered MP3s, mirroring the
    output format of extract_audio_clips() so downstream pairing/export
    code needs no source-specific handling.

    Uploads with an .mp3 extension are written unchanged (no re-encode);
    other formats are decoded and exported as MP3.

    Args:
        uploads: list of (filename, bytes) tuples
        output_folder: directory to write numbered MP3s into (created if missing)

    Returns:
        dict with keys:
            'saved': sorted list of int card numbers successfully written
            'skipped_no_number': list of filenames with no digit in the
                filename (excluding extension)
            'skipped_duplicate': list of filenames whose number was already
                claimed by an earlier (alphabetically-first) file
            'skipped_unreadable': list of filenames pydub/ffmpeg could not decode
    """
    os.makedirs(output_folder, exist_ok=True)

    result = {
        'saved': [],
        'skipped_no_number': [],
        'skipped_duplicate': [],
        'skipped_unreadable': [],
    }

    used_numbers = set()

    for filename, data in sorted(uploads, key=lambda u: u[0]):
        match = re.search(r'\d+', os.path.splitext(filename)[0])
        if not match:
            result['skipped_no_number'].append(filename)
            continue

        num = int(match.group())
        if num in used_numbers:
            result['skipped_duplicate'].append(filename)
            continue

        out_path = os.path.join(output_folder, f"{num}.mp3")
        try:
            clip = AudioSegment.from_file(BytesIO(data))
            if filename.lower().endswith(".mp3"):
                with open(out_path, "wb") as f:
                    f.write(data)
            else:
                clip.export(out_path, format="mp3")
        except Exception:
            try:
                if os.path.exists(out_path):
                    os.remove(out_path)
            except OSError:
                pass
            result['skipped_unreadable'].append(filename)
            continue

        used_numbers.add(num)
        result['saved'].append(num)

    result['saved'].sort()
    return result


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python audio_extractor.py <input_audio> <output_folder> [options]")
        print("\nOptions:")
        print("  --api <local|groq|openai>  Whisper API to use (default: local)")
        print("  --model <size>             Model size for local: tiny/base/small/medium/large (default: small)")
        print("  --buffer <ms>              Buffer time in milliseconds (default: 400)")
        print("  --api-key <key>            API key for groq/openai (or set GROQ_API_KEY/OPENAI_API_KEY env var)")
        print("\nExamples:")
        print("  # Local (faster-whisper)")
        print("  python audio_extractor.py recording.aac output/ --model small")
        print("\n  # Groq API (fastest, requires API key)")
        print("  python audio_extractor.py recording.aac output/ --api groq --api-key YOUR_KEY")
        print("\n  # OpenAI API")
        print("  python audio_extractor.py recording.aac output/ --api openai")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    # Parse optional arguments
    api_type = "local"
    model_size = "small"
    buffer_ms = 400
    api_key = None

    i = 3
    while i < len(sys.argv):
        if sys.argv[i] == "--api" and i + 1 < len(sys.argv):
            api_type = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--model" and i + 1 < len(sys.argv):
            model_size = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--buffer" and i + 1 < len(sys.argv):
            buffer_ms = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--api-key" and i + 1 < len(sys.argv):
            api_key = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    print(f"Input file: {input_file}")
    print(f"Output folder: {output_dir}")
    print(f"API type: {api_type}")
    if api_type == "local":
        print(f"Whisper model: {model_size}")
    print(f"Buffer: {buffer_ms}ms")
    print("-" * 50)

    def progress(percent, message):
        print(f"[{percent:3d}%] {message}")

    count, debug_info = extract_audio_clips(
        input_file,
        output_dir,
        model_size=model_size,
        buffer_ms=buffer_ms,
        use_vad=False,
        api_type=api_type,
        api_key=api_key,
        progress_callback=progress,
        debug=True
    )

    print("\n" + "=" * 50)
    print("DEBUG INFORMATION")
    print("=" * 50)
    print(f"API Type: {debug_info['api_type']}")
    print(f"Audio duration: {debug_info['audio_duration']:.2f} seconds")
    print(f"\nWhisper Info:")
    print(f"  Language detected: {debug_info['whisper_info'].get('language', 'unknown')}")
    print(f"  Duration: {debug_info['whisper_info'].get('duration', 0):.2f}s")
    print(f"\nTotal words transcribed: {debug_info['total_words']}")
    print(f"Detected numbers: {len(debug_info['detected_numbers'])}")

    if debug_info['errors']:
        print(f"\nERRORS ({len(debug_info['errors'])}):")
        for error in debug_info['errors']:
            print(f"  - {error}")

    print(f"\nFull Transcription:")
    print("-" * 50)
    print(debug_info['transcription'])
    print("-" * 50)

    if debug_info['first_20_words']:
        print(f"\nFirst 20 words (with normalized form):")
        for word in debug_info['first_20_words']:
            print(f"  {word}")

    if debug_info['detected_numbers']:
        print(f"\nDetected Numbers:")
        for num_info in debug_info['detected_numbers']:
            print(f"  Number {num_info['number']} at position {num_info['position']}: '{num_info['word']}'")
    else:
        print("\nWARNING: No numbers detected!")
        print("Make sure the audio contains spoken numbers like 'one', 'two', 'number one', etc.")

    print("\n" + "=" * 50)
    print(f"RESULT: Extracted {count} audio clips")
    print(f"Files saved to: {output_dir}")
    print("=" * 50)
