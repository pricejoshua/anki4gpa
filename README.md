# Anki Deck Creator

A Streamlit web application that automatically creates Anki flashcard decks from Word documents and audio files.

## Features

- **Extract Images**: Extract numbered images from Word documents (.docx)
- **Extract Audio**: Use AI (Whisper) to transcribe audio and extract numbered vocabulary clips
- **Automatic Pairing**: Match audio clips with images by number
- **Export to Anki**: Generate .apkg files for direct import into Anki

## Installation

### Prerequisites

- Python 3.8 or higher
- ffmpeg (required for audio processing)

#### Install ffmpeg

**Windows:**
```bash
# Using chocolatey
choco install ffmpeg

# Or download from https://ffmpeg.org/download.html
```

**Mac:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt install ffmpeg
```

### Install Python Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### 1. Start the Application

```bash
streamlit run app.py
```

The app will open in your default web browser at `http://localhost:8501`

### 2. Workflow

#### Tab 1: Extract Images
1. Upload a Word document (.docx) with numbered paragraphs and images
2. Click "Extract Images"
3. Preview the extracted images

#### Tab 2: Extract Audio
1. Upload an audio file (MP3, AAC, M4A, or WAV)
2. Select Whisper API:
   - **Local (faster-whisper)**: Free, runs on your computer, no API key needed
   - **Groq API**: Fastest (~10 sec), requires free API key from [groq.com](https://console.groq.com)
   - **OpenAI API**: Fast, requires API key from [openai.com](https://platform.openai.com)
3. Configure settings:
   - For **Local**: Choose model size (tiny/base/small/medium/large)
   - For **Groq/OpenAI**: Enter API key (or set GROQ_API_KEY/OPENAI_API_KEY environment variable)
   - Set buffer time (milliseconds to add before/after each clip)
4. Click "Extract Audio Clips"
5. Wait for processing (time varies by API choice)
6. Preview the extracted audio clips

#### Tab 3: Pair Files
1. Click "Pair Files" to match audio and images by number
2. Review the paired cards
3. Check for any mismatches (warnings will appear)

#### Tab 4: Export Deck
1. **Choose card style:**
   - **Two Cards: Audio→Image & Image→Audio** (Recommended) - Creates 2 cards per item for comprehensive practice
   - **One Card: Audio on front, Image on back** - Focus on audio recognition
   - **One Card: Image on front, Audio on back** - Focus on visual recall
   - **One Card: Audio + Image on front** - Both clues on front side
2. **Enter deck details:**
   - Deck name (e.g., "Farsi Vocabulary")
   - Note type (e.g., "Vocabulary")
   - Tags (comma-separated, e.g., "vocab,unit1")
   - Unit/Session prefix (e.g., "Unit_1_Session_1")
3. Click "Generate Anki Deck (.apkg)"
4. Download the .apkg file
5. Import into Anki (File > Import)

## File Format Requirements

### Word Documents
- Images should be in numbered paragraphs (1., 2., 3., etc.)
- Each numbered paragraph should contain one image
- Word's automatic numbering is also supported

### Audio Files
- Supported formats: MP3, AAC, M4A, WAV
- Should contain spoken numbers followed by vocabulary words
- Format: "Number one [word]... Number two [word]..." or "One [word]... Two [word]..."
- Numbers can be spoken as:
  - "number one", "number two"
  - "one", "two", "three"
  - "1", "2", "3"

## Technical Details

### How It Works

1. **Image Extraction**: Uses `python-docx` to parse Word documents and extract images associated with numbered paragraphs
2. **Audio Extraction**:
   - Uses OpenAI's Whisper model for speech-to-text transcription
   - Detects spoken numbers in the transcription
   - Extracts audio segments for each numbered vocabulary item
   - Uses `pydub` for audio manipulation
3. **Pairing**: Matches files by number (1.png with 1.mp3, etc.)
4. **Export**: Uses `genanki` to create Anki packages (.apkg) with embedded media

### Whisper API Selection

You can choose between three Whisper backends for audio transcription:

#### Local (faster-whisper)
- **Pros**: Free, works offline, no API limits
- **Cons**: Slower (2-5 minutes for 1 minute audio), requires good CPU
- **Best for**: Privacy, offline use, no budget
- **Model sizes**: tiny (fastest) → base → small (recommended) → medium → large (most accurate)

#### Groq API
- **Pros**: Fastest (5-15 seconds for 1 minute audio), uses Whisper Large V3 (best accuracy)
- **Cons**: Requires API key, rate limits on free tier
- **Best for**: Speed, best accuracy, batch processing
- **Cost**: Free tier available at [console.groq.com](https://console.groq.com)

#### OpenAI API
- **Pros**: Fast, reliable, official Whisper API
- **Cons**: Requires API key, costs $0.006/minute of audio
- **Best for**: Production use, reliability
- **Cost**: Pay-per-use at [platform.openai.com](https://platform.openai.com)

**Recommendation**: Try **Groq API** first (free & fastest), fall back to **Local** if you hit rate limits.

## Troubleshooting

### Audio extraction fails
- Ensure ffmpeg is installed and in your PATH
- Check that the audio file is not corrupted
- Try a smaller Whisper model (tiny or base)

### Images not extracted correctly
- Verify the Word document has numbered paragraphs
- Check that images are embedded (not linked)
- Ensure images are near numbered paragraphs

### Mismatched audio/image counts
- Check that your source materials have the same number of items
- Review the numbered sequences in both files
- Some items may not have been detected correctly

### Memory issues
- Use a smaller Whisper model (tiny or base)
- Process shorter audio files
- Close other applications

## Advanced Usage

### Custom Note Types

To use a custom Anki note type:
1. Create the note type in Anki first
2. Note the exact field names
3. Modify the `create_anki_deck()` function in app.py to match your fields

### Batch Processing

To process multiple files:
1. Process images from first document
2. Process audio from first file
3. Export deck
4. Click "Clear All Data" in sidebar
5. Repeat for next set

## Deployment

### Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub account
4. Deploy the app

**Note**: Whisper processing can be slow on Streamlit Cloud's free tier. Consider using smaller models or deploying to a server with more resources.

### Local Network

To allow other devices on your network to access the app:

```bash
streamlit run app.py --server.address 0.0.0.0
```

Then access from other devices using your computer's IP address.

## Credits

This app integrates and improves upon several scripts:
- Pictures.py: Image extraction from Word documents
- ExtractAudioUpdated.py: Whisper-based audio extraction
- Renaming.py: File pairing and cleanup
- Auto.py: Anki deck creation concept

Built with:
- [Streamlit](https://streamlit.io)
- [Faster Whisper](https://github.com/guillaumekln/faster-whisper)
- [genanki](https://github.com/kerrickstaley/genanki)
- [pydub](https://github.com/jiaaro/pydub)

## Legacy Scripts

The `old_scripts/` directory contains the original Python scripts that this app is based on. These are kept for reference but the Streamlit app provides a more user-friendly interface.

## License

MIT License - Feel free to modify and distribute
