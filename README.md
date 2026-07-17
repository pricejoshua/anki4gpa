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

- **Extract Images**: Extract numbered images from Word documents (.docx), or upload individually numbered photo files directly
- **Extract Audio**: Use AI (Whisper) to transcribe audio and extract numbered vocabulary clips
- **Automatic Pairing**: Match audio clips with images by number
- **Export to Anki**: Generate .apkg files for direct import into Anki

## Usage

1. **Extract Images** (Tab 1): Upload a Word document with numbered paragraphs and images, or switch to "Upload Photos Directly" to upload individually numbered photo files (e.g. `1.jpg`, `2.jpg`)
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

### Direct Photo Upload
- Name each file with its card number, e.g. `1.jpg`, `2.jpg` (the first number found anywhere in the filename is used, so `img_3.jpg` also works)
- Supported formats: JPG, JPEG, PNG, BMP, GIF, TIFF, WEBP, PPM

### Audio Files
- Supported formats: MP3, AAC, M4A, WAV
- Should contain spoken numbers followed by vocabulary words
- Format: "Number one [word]... Number two [word]..."

## Embedding in Your Website

To embed this Space in your website using an iframe:

```html
<iframe
    src="https://YOUR-USERNAME-SPACE-NAME.hf.space"
    frameborder="0"
    width="850"
    height="450"
></iframe>
```

Replace `YOUR-USERNAME-SPACE-NAME` with your actual Space subdomain.

**Note**: Drag-and-drop file upload works in most browsers when embedded. If users experience issues, they can use the "Browse files" button instead.

## License

MIT License - Feel free to modify and distribute

## Credits

Built with Streamlit, Faster Whisper, genanki, and pydub.
