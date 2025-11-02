# Testing Individual Modules

The application has been refactored into separate modules that can be tested independently from the command line.

## Module Structure

```
anki4gpa/
├── image_extractor.py   # Extract images from Word documents
├── audio_extractor.py   # Extract audio clips using Whisper
├── file_pairer.py       # Pair audio and image files by number
├── deck_creator.py      # Create Anki .apkg decks
└── app.py               # Streamlit web interface
```

## Testing Audio Extraction (Most Important for Debugging)

The audio extractor supports three Whisper backends:

### 1. Local (faster-whisper) - Default

```bash
python audio_extractor.py test_data/recording/2025-09-03-MA-Farsi-U01-S01-People.aac output_audio/ --model small
```

### 2. Groq API (Fastest, requires API key)

```bash
# Set API key as environment variable
export GROQ_API_KEY="your_api_key_here"
python audio_extractor.py test_data/recording/2025-09-03-MA-Farsi-U01-S01-People.aac output_audio/ --api groq

# Or pass API key directly
python audio_extractor.py test_data/recording/2025-09-03-MA-Farsi-U01-S01-People.aac output_audio/ --api groq --api-key YOUR_KEY
```

### 3. OpenAI API (requires API key)

```bash
# Set API key as environment variable
export OPENAI_API_KEY="your_api_key_here"
python audio_extractor.py test_data/recording/2025-09-03-MA-Farsi-U01-S01-People.aac output_audio/ --api openai

# Or pass API key directly
python audio_extractor.py test_data/recording/2025-09-03-MA-Farsi-U01-S01-People.aac output_audio/ --api openai --api-key YOUR_KEY
```

**Options:**
- `--api <local|groq|openai>` - Whisper API to use (default: local)
- `--model <size>` - Model size for local: tiny/base/small/medium/large (default: small)
- `--buffer <ms>` - Buffer time in milliseconds (default: 400)
- `--api-key <key>` - API key for groq/openai (or set environment variable)

**Output:** All modes display comprehensive debug information including:
- API type used
- Audio duration
- Whisper language detection
- Number of segments/words found
- Full transcription text
- First 20 words with normalized forms
- All detected numbers
- Any errors encountered

**Performance Comparison:**
- **Groq API**: Fastest (usually <10 seconds), requires API key, uses Whisper Large V3
- **OpenAI API**: Fast, requires API key, uses Whisper V2
- **Local**: Slower but free, model size affects speed (tiny fastest, large slowest)

## Testing Image Extraction

```bash
python image_extractor.py <path_to_docx> output_images/
```

**Example:**
```bash
python image_extractor.py test_data/vocabulary.docx output_images/
```

**Output:** Shows how many images were extracted and where they were saved.

## Testing File Pairing

```bash
python file_pairer.py <image_dir> <audio_dir> output_paired/
```

**Example:**
```bash
python file_pairer.py output_images/ output_audio/ output_paired/
```

**Output:**
- Shows paired numbers
- Lists images without matching audio
- Lists audio without matching images
- Copies paired files to output directory

## Testing Deck Creation

```bash
python deck_creator.py <media_dir> "Deck Name" "tag1,tag2"
```

**Example:**
```bash
python deck_creator.py output_paired/ "Farsi Vocabulary" "farsi,vocab,unit1"
```

**Requirements:** The media directory must contain paired files: `1.png`, `1.mp3`, `2.png`, `2.mp3`, etc.

**Output:** Creates a `.apkg` file in the media directory that can be imported into Anki.

## Debugging Whisper Transcription Issues

If you're getting 0 words transcribed, run the audio extractor directly:

```bash
python audio_extractor.py test_data/recording/2025-09-03-MA-Farsi-U01-S01-People.aac debug_output/ tiny
```

Check the debug output for:

1. **Audio Duration** - Should be > 0 seconds
   - If 0, the audio file might be corrupted or in an unsupported format

2. **Whisper Duration** - Should match audio duration
   - If 0, Whisper couldn't read the file

3. **Segments Found** - Should be > 0
   - If 0, Whisper didn't detect any speech
   - Try disabling VAD filter (it's already disabled by default)

4. **Total Words** - Should be > 0
   - If 0 but segments > 0, the segments don't have word timestamps
   - This could indicate a Whisper model issue

5. **Full Transcription** - Should contain text
   - If empty, Whisper didn't transcribe anything
   - Check if ffmpeg is properly installed

6. **Errors** - Any Python exceptions
   - These will show the exact failure point

## Common Issues

### ffmpeg not found
```
Error: ffmpeg not found
```
**Solution:** Install ffmpeg:
- Windows: `choco install ffmpeg` or download from ffmpeg.org
- Mac: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

### No words transcribed
```
Total words transcribed: 0
```
**Possible causes:**
1. Audio file is silent or very quiet
2. ffmpeg can't decode the audio format
3. VAD filter is too aggressive (already disabled)
4. Whisper model not properly loaded

**Debug steps:**
1. Check audio file plays correctly in a media player
2. Try converting to WAV: `ffmpeg -i input.aac output.wav`
3. Test with the WAV file
4. Try different Whisper models (tiny, base, small)

### Module import errors
```
ModuleNotFoundError: No module named 'faster_whisper'
```
**Solution:** Install dependencies:
```bash
pip install -r requirements.txt
```

## Full Workflow Test

Test the complete pipeline from the command line:

```bash
# 1. Extract images
python image_extractor.py test_data/vocabulary.docx step1_images/

# 2. Extract audio
python audio_extractor.py test_data/recording.aac step2_audio/ small 400

# 3. Pair files
python file_pairer.py step1_images/ step2_audio/ step3_paired/

# 4. Create deck
python deck_creator.py step3_paired/ "My Deck" "vocab,test"

# Result: step3_paired/My_Deck.apkg ready to import into Anki
```

## Streamlit App

The web interface still works the same:

```bash
streamlit run app.py
```

The app now imports functions from the separate modules, making it easier to maintain and debug.
