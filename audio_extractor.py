"""
Audio extraction using Whisper AI
Based on ExtractAudioUpdated.py - transcribes audio and extracts numbered vocabulary clips
"""

import os
import re
from faster_whisper import WhisperModel
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


def extract_audio_clips(input_file, output_dir, model_size="medium", buffer_ms=400,
                       use_vad=False, progress_callback=None, debug=False):
    """
    Extract numbered audio clips using Whisper transcription.

    Args:
        input_file: Path to input audio file
        output_dir: Directory to save extracted clips
        model_size: Whisper model size (tiny, base, small, medium, large)
        buffer_ms: Buffer time in milliseconds to add before/after each clip
        use_vad: Use Voice Activity Detection filter
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

    if progress_callback:
        progress_callback(20, "Loading Whisper model...")

    # Load Whisper model
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    if progress_callback:
        progress_callback(30, "Transcribing audio...")

    # Detailed debug info
    debug_info = {
        'total_words': 0,
        'transcription': '',
        'first_20_words': [],
        'detected_numbers': [],
        'whisper_info': {},
        'segment_count': 0,
        'errors': [],
        'audio_duration': len(audio) / 1000.0,  # Convert to seconds
        'audio_format': str(audio),
    }

    try:
        # Transcribe with Whisper
        segments, info = model.transcribe(
            input_file,
            word_timestamps=True,
            vad_filter=use_vad,
            language="en"
        )

        # Capture info object details
        debug_info['whisper_info'] = {
            'language': getattr(info, 'language', 'unknown'),
            'language_probability': getattr(info, 'language_probability', 0),
            'duration': getattr(info, 'duration', 0),
            'all_language_probs': getattr(info, 'all_language_probs', None)
        }

        # Convert generator to list and count segments
        segments_list = list(segments)
        debug_info['segment_count'] = len(segments_list)

        if progress_callback:
            progress_callback(40, f"Found {len(segments_list)} segments...")

        # Flatten words from all segments
        words = []
        full_transcription = []

        for idx, seg in enumerate(segments_list):
            try:
                seg_text = seg.text if hasattr(seg, 'text') else ""
                full_transcription.append(seg_text)

                # Check if segment has words attribute
                if not hasattr(seg, 'words'):
                    debug_info['errors'].append(f"Segment {idx} has no 'words' attribute")
                    continue

                seg_words = list(seg.words) if seg.words else []

                for w in seg_words:
                    words.append({
                        'start': w.start,
                        'end': w.end,
                        'raw': w.word,
                        'norm': norm_token(w.word)
                    })
            except Exception as e:
                debug_info['errors'].append(f"Error processing segment {idx}: {str(e)}")

        debug_info['total_words'] = len(words)
        debug_info['transcription'] = ' '.join(full_transcription)
        debug_info['first_20_words'] = [f"{w['raw']} (norm: {w['norm']})" for w in words[:20]]

    except Exception as e:
        debug_info['errors'].append(f"Transcription error: {str(e)}")
        import traceback
        debug_info['errors'].append(traceback.format_exc())
        words = []

    if not words:
        return (0, debug_info) if debug else 0

    if progress_callback:
        progress_callback(50, "Extracting audio clips...")

    # Extract audio clips for each detected number
    counters = {}
    i = 0
    saved = 0

    while i < len(words):
        num, skip = detect_number_at(words, i)
        if not num:
            i += 1
            continue

        debug_info['detected_numbers'].append({
            'number': num,
            'position': i,
            'word': words[i]['raw']
        })

        # Find the block of words after this number until the next number
        block_start = i + skip
        j = block_start
        while j < len(words):
            nxt_num, _ = detect_number_at(words, j)
            if nxt_num:
                break
            j += 1
        block_end = j - 1

        # If there are words in this block, extract the audio
        if block_end >= block_start:
            start_time = words[block_start]['start'] * 1000 - buffer_ms
            end_time = words[block_end]['end'] * 1000 + buffer_ms

            start_time = max(0, start_time)
            end_time = min(len(audio), end_time)

            clip = audio[start_time:end_time]

            # Handle duplicate numbers
            counters[num] = counters.get(num, 0) + 1
            occ = counters[num]

            out_name = f"{num}_{occ}.mp3" if occ > 1 else f"{num}.mp3"
            clip.export(os.path.join(output_dir, out_name), format="mp3")
            saved += 1

            if progress_callback:
                progress_callback(50 + int(40 * saved / len(words)), f"Extracted clip {saved}...")

        i = j if j < len(words) else len(words)

    if progress_callback:
        progress_callback(100, f"Extracted {saved} clips!")

    return (saved, debug_info) if debug else saved


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python audio_extractor.py <input_audio> <output_folder> [model_size] [buffer_ms]")
        print("\nModel sizes: tiny, base, small, medium, large")
        print("Default model: small")
        print("Default buffer: 400ms")
        print("\nExample:")
        print("  python audio_extractor.py recording.aac output/ small 400")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]
    model_size = sys.argv[3] if len(sys.argv) > 3 else "small"
    buffer_ms = int(sys.argv[4]) if len(sys.argv) > 4 else 400

    print(f"Input file: {input_file}")
    print(f"Output folder: {output_dir}")
    print(f"Whisper model: {model_size}")
    print(f"Buffer: {buffer_ms}ms")
    print(f"VAD filter: False")
    print("-" * 50)

    def progress(percent, message):
        print(f"[{percent:3d}%] {message}")

    count, debug_info = extract_audio_clips(
        input_file,
        output_dir,
        model_size=model_size,
        buffer_ms=buffer_ms,
        use_vad=False,
        progress_callback=progress,
        debug=True
    )

    print("\n" + "=" * 50)
    print("DEBUG INFORMATION")
    print("=" * 50)
    print(f"Audio duration: {debug_info['audio_duration']:.2f} seconds")
    print(f"Audio format: {debug_info['audio_format']}")
    print(f"\nWhisper Info:")
    print(f"  Language detected: {debug_info['whisper_info']['language']}")
    print(f"  Language probability: {debug_info['whisper_info']['language_probability']:.2f}")
    print(f"  Duration: {debug_info['whisper_info']['duration']:.2f}s")
    print(f"\nSegments found: {debug_info['segment_count']}")
    print(f"Total words transcribed: {debug_info['total_words']}")
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
