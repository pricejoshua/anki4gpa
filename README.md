---
title: Anki Deck Creator
emoji: 📚
colorFrom: blue
colorTo: green
sdk: docker
pinned: false
license: mit
---

# Anki Deck Creator

A Streamlit web application that automatically creates Anki flashcard decks from Word documents and audio files.

## Features

- **Extract Images**: Extract numbered images from Word documents (.docx)
- **Extract Audio**: Use AI (Whisper) to transcribe audio and extract numbered vocabulary clips
- **Automatic Pairing**: Match audio clips with images by number
- **Export to Anki**: Generate .apkg files for direct import into Anki

## Usage

1. **Extract Images** (Tab 1): Upload a Word document with numbered paragraphs and images
2. **Extract Audio** (Tab 2): Upload an audio file and choose a Whisper API (Local, Groq, or OpenAI)
3. **Pair Files** (Tab 3): Match audio and images automatically
4. **Export Deck** (Tab 4): Generate and download your Anki deck

## Whisper API Options

- **Local (faster-whisper)**: Free, runs on the server, no API key needed
- **Groq API**: Fastest (~10 sec), requires free API key from [groq.com](https://console.groq.com)
- **OpenAI API**: Fast and reliable, requires API key from [openai.com](https://platform.openai.com)

## File Format Requirements

### Word Documents
- Images should be in numbered paragraphs (1., 2., 3., etc.)
- Each numbered paragraph should contain one image

### Audio Files
- Supported formats: MP3, AAC, M4A, WAV
- Should contain spoken numbers followed by vocabulary words
- Format: "Number one [word]... Number two [word]..."

## Embedding in iframes

If you're embedding this app in an iframe on your website, make sure to include these attributes for full drag-and-drop functionality:

```html
<iframe
    src="YOUR_HF_SPACE_URL"
    width="100%"
    height="800"
    frameborder="0"
    allow="clipboard-read; clipboard-write"
></iframe>
```

**Note**: Due to browser security restrictions, drag-and-drop may not work in all iframe configurations. Users can always use the "Browse files" button as an alternative.

## License

MIT License - Feel free to modify and distribute

## Credits

Built with Streamlit, Faster Whisper, genanki, and pydub.
