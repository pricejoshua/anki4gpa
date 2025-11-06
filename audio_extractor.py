"""
Audio extraction using Whisper AI
Based on ExtractAudioUpdated.py - transcribes audio and extracts numbered vocabulary clips
Supports: Local (faster-whisper), Groq API, OpenAI API
"""

import os
import re
from pydub import AudioSegment


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


def norm_token(s):
    """Normalize a token by removing non-alphanumeric characters"""
    return re.sub(r"[^a-z0-9\-]+", "", (s or "").lower())


def detect_number_at(words, i):
    """
    Detect if a number appears at position i in the words list.
    Returns (number_string, tokens_consumed) or (None, 0)
    """
    if i >= len(words):
        return None, 0

    raw = words[i]['raw'].lower()
    token = words[i]['norm']

    # Check for "number X" pattern
    if token == "number" and i + 1 < len(words):
        nxt = words[i + 1]['norm']
        if nxt in WORD2DIGIT:
            return WORD2DIGIT[nxt], 2
        if nxt.isdigit():
            return nxt, 2

    # Check if current token is a number word or digit
    if token in WORD2DIGIT:
        return WORD2DIGIT[token], 1
    if token.isdigit():
        return token, 1

    # Check normalized version of raw word
    combo = norm_token(raw)
    if combo in WORD2DIGIT:
        return WORD2DIGIT[combo], 1

    return None, 0


def transcribe_with_local_whisper(audio_path, model_size="small", use_vad=False):
    """Transcribe using local faster-whisper model"""
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        vad_filter=use_vad,
        language="en"
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


def transcribe_with_groq(audio_path, api_key=None):
    """Transcribe using Groq Whisper API"""
    from groq import Groq

    if not api_key:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY not found. Set it as environment variable or pass as parameter.")

    client = Groq(api_key=api_key)

    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"]
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


def transcribe_with_openai(audio_path, api_key=None):
    """Transcribe using OpenAI Whisper API"""
    from openai import OpenAI

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not found. Set it as environment variable or pass as parameter.")

    client = OpenAI(api_key=api_key)

    with open(audio_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="verbose_json",
            timestamp_granularities=["word"]
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
                       progress_callback=None, debug=False):
    """
    Extract numbered audio clips using Whisper transcription.

    Args:
        input_file: Path to input audio file
        output_dir: Directory to save extracted clips
        model_size: Whisper model size (tiny, base, small, medium, large) - only for local
        buffer_ms: Buffer time in milliseconds to add before/after each clip
        use_vad: Use Voice Activity Detection filter - only for local
        api_type: "local" (faster-whisper), "groq" (Groq API), or "openai" (OpenAI API)
        api_key: API key for Groq/OpenAI (if not set in environment)
        progress_callback: Optional callback(percent, message)
        debug: Return detailed debug information

    Returns:
        Number of clips extracted, or (count, debug_info) if debug=True
    """

    os.makedirs(output_dir, exist_ok=True)

    if progress_callback:
        progress_callback(10, "Loading audio file...")

    # Load audio
    audio = AudioSegment.from_file(input_file)

    # Convert to WAV for better compatibility
    import tempfile
    temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    temp_wav_path = temp_wav.name
    temp_wav.close()
    audio.export(temp_wav_path, format='wav')

    if progress_callback:
        progress_callback(30, f"Transcribing audio with {api_type.upper()} Whisper...")

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

    try:
        # Transcribe based on API type
        if api_type == "local":
            words, transcription, info = transcribe_with_local_whisper(
                temp_wav_path,
                model_size=model_size,
                use_vad=use_vad
            )
        elif api_type == "groq":
            words, transcription, info = transcribe_with_groq(temp_wav_path, api_key=api_key)
        elif api_type == "openai":
            words, transcription, info = transcribe_with_openai(temp_wav_path, api_key=api_key)
        else:
            raise ValueError(f"Invalid api_type: {api_type}. Must be 'local', 'groq', or 'openai'")

        debug_info['whisper_info'] = info
        debug_info['total_words'] = len(words)
        debug_info['transcription'] = transcription
        debug_info['first_20_words'] = [f"{w['raw']} (norm: {w['norm']})" for w in words[:20]]

        if progress_callback:
            progress_callback(40, f"Found {len(words)} words...")

    except Exception as e:
        debug_info['errors'].append(f"Transcription error: {str(e)}")
        import traceback
        debug_info['errors'].append(traceback.format_exc())
        words = []

    if not words:
        # Clean up temporary WAV file
        try:
            os.unlink(temp_wav_path)
        except:
            pass
        return (0, debug_info) if debug else 0

    if progress_callback:
        progress_callback(50, "Extracting audio clips...")

    # Extract audio clips for each detected number (in increasing order starting at 1)
    last_accepted_number = 0  # Track last accepted number (start at 0 so 1 is accepted first)
    created_files = []  # Track files created in current sequence
    i = 0
    saved = 0

    while i < len(words):
        num, skip = detect_number_at(words, i)
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
            'word': words[i]['raw']
        })

        # Find the block of words: from the number itself until the next number
        block_start = i  # Start from the number word itself
        block_end_idx = i + skip  # First word after the number marker

        # Find where the next number starts
        j = block_end_idx
        while j < len(words):
            nxt_num, _ = detect_number_at(words, j)
            if nxt_num:
                break
            j += 1

        # Extract up to (but not including) the next number
        # Include at least the number word(s) themselves
        block_end = max(i + skip - 1, j - 1)

        # Extract the audio for this block
        if block_end >= block_start:
            start_time = words[block_start]['start'] * 1000 - buffer_ms
            end_time = words[block_end]['end'] * 1000 + buffer_ms

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

    if progress_callback:
        progress_callback(100, f"Extracted {saved} clips!")

    # Clean up temporary WAV file
    try:
        os.unlink(temp_wav_path)
    except:
        pass

    return (saved, debug_info) if debug else saved


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
