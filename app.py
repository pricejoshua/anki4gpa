"""
Anki Deck Creator - Streamlit Web Application
Creates Anki flashcard decks from Word documents and audio files
"""

import streamlit as st
import hmac
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from io import BytesIO

# Import our custom modules
from image_extractor import extract_numbered_images, save_numbered_photos
from audio_extractor import extract_audio_clips, save_numbered_audio
from file_pairer import pair_files
from deck_creator import create_anki_deck
import issue_report
import usage_log
from tools import summarize_log


# ============================================================================
# STREAMLIT APP
# ============================================================================

# Page config
st.set_page_config(
    page_title="Anki Deck Creator",
    page_icon="📚",
    layout="wide"
)

# Enable drag-and-drop for iframe embedding
st.markdown("""
    <script>
        // Improve drag and drop functionality in iframes
        window.addEventListener('dragover', function(e) {
            e.preventDefault();
        });
        window.addEventListener('drop', function(e) {
            e.preventDefault();
        });
    </script>
""", unsafe_allow_html=True)

# Log configuration for debugging (check browser console)
print(f"[CONFIG] XSRF Protection: {st.get_option('server.enableXsrfProtection')}")
print(f"[CONFIG] CORS Enabled: {st.get_option('server.enableCORS')}")

# Initialize session state
if 'temp_images' not in st.session_state:
    st.session_state.temp_images = None
if 'temp_audio' not in st.session_state:
    st.session_state.temp_audio = None
if 'temp_final' not in st.session_state:
    st.session_state.temp_final = None
if 'image_files' not in st.session_state:
    st.session_state.image_files = []
if 'audio_files' not in st.session_state:
    st.session_state.audio_files = []
if 'paired_files' not in st.session_state:
    st.session_state.paired_files = []
if 'issue_report' not in st.session_state:
    st.session_state.issue_report = issue_report.new_report_state()
if 'usage_session' not in st.session_state:
    st.session_state.usage_session = usage_log.new_session_id()
    usage_log.log_event(st.session_state.usage_session, "session_start")


def _admin_token_ok(entered):
    """True if `entered` matches the non-empty ADMIN_TOKEN env var (constant-time)."""
    token = os.environ.get("ADMIN_TOKEN", "")
    return bool(token) and hmac.compare_digest(entered.encode(), token.encode())


def _usage_summary_text():
    """Summary report of the usage log, or None if the log is missing/empty."""
    events = summarize_log.load(usage_log.log_path())
    if not events:
        return None
    return summarize_log.report(events, 30, datetime.now(timezone.utc))


def _usage(fn, args):
    """Forward a recorder call to the anonymous usage log."""
    name = fn.__name__
    if name == "record_upload":
        usage_log.log_event(st.session_state.usage_session, "upload",
                            usage_log.file_fingerprint(*args))
    elif name == "record_event":
        step, settings, *rest = args
        data = {}
        if settings:
            data["settings"] = usage_log.summarize_settings(settings)
        debug = usage_log.summarize_debug(rest[0] if rest else None)
        if debug:
            data["debug"] = debug
        usage_log.log_event(st.session_state.usage_session, step, data)
    elif name == "record_error":
        step, exc = args
        usage_log.log_event(st.session_state.usage_session, "error",
                            {"in": step, "type": type(exc).__name__})


def _report(fn, *args):
    """Call an issue_report recorder; diagnostics must never break the app."""
    try:
        fn(st.session_state.issue_report, *args)
        # A prepared zip is stale once more steps are recorded.
        st.session_state.pop("issue_report_zip", None)
    except Exception as e:
        print(f"[issue_report] {fn.__name__} failed: {e}")
    try:
        _usage(fn, args)
    except Exception as e:
        print(f"[usage_log] {fn.__name__} failed: {e}")


# Header
st.title("📚 Anki Deck Creator")
st.markdown("Create Anki flashcard decks from Word documents and audio files")
st.markdown("---")

# === TAB SETUP ===
tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "📘 Tutorial",
    "1️⃣ Extract Images",
    "2️⃣ Extract Audio",
    "3️⃣ Pair Files",
    "4️⃣ Export Deck"
])

# ============================================================================
# TAB 0: TUTORIAL
# ============================================================================
with tab0:
    st.header("How This Tool Works")
    st.markdown("""
    This tool builds an Anki deck from two source files: a **Word document**
    containing numbered images, and an **audio file** with numbered vocabulary
    recordings. The pipeline has four steps:

    1. **Extract Images** — pull numbered images out of the Word document
    2. **Extract Audio** — transcribe the audio and cut out numbered vocabulary clips
    3. **Pair Files** — match images and audio clips by number
    4. **Export Deck** — generate the final `.apkg` file for Anki

    The sections below explain exactly how each source file needs to be
    structured, using real example files you can preview.
    """)

    st.markdown("---")

    # --- Word Document Format ---
    st.subheader("📄 Word Document Format")
    st.markdown("""
    Images must appear in (or right next to) a **numbered list item**. Two
    numbering styles are both detected automatically:

    - **Literal text numbers**, like a paragraph that just says `1.`
    - **Word's automatic numbered-list formatting** (the bulleted/numbered
      list button in Word's toolbar) — the example file below actually uses
      this style, not literal digits

    The rest of the document can contain anything else — lesson objectives,
    activity tables, timing notes, whatever your lesson plan needs. The
    extractor only looks at numbered-list paragraphs and ignores everything
    else, so you don't need to strip the document down to just the vocab list.

    **⚠️ Watch out for:** if some *other* part of the document also uses a
    numbered list or a literal digit paragraph (like a numbered activity
    step), its image could get mistaken for a vocabulary item. Keep the vocab
    image list as the only numbered list in the document if possible, or
    double-check the extracted image count and filenames in Tab 1 before
    moving on.
    """)

    docx_example_path = "examples/Unit 2 Session 9 Lesson Plan 2025.docx"
    if os.path.exists(docx_example_path):
        with open(docx_example_path, "rb") as f:
            st.download_button(
                label="📥 Download Example Word Document",
                data=f.read(),
                file_name="example_lesson_plan.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="download_example_docx"
            )
        st.caption("Open this in Word to see the numbered image list in context.")
    else:
        st.info("Example file not bundled in this deployment.")

    st.markdown("---")

    # --- Audio File Format ---
    st.subheader("🔊 Audio File Format")
    st.markdown("""
    Record any preamble or introduction first — it's ignored entirely. Then:

    - Say **"1"**, then the vocabulary word
    - Say **"2"**, then the next vocabulary word
    - ...and so on, in increasing order

    Saying **"1" again** at any point resets the sequence and discards
    previously extracted clips for that take — handy if you want to redo a
    recording without editing the audio file.

    Supported formats: MP3, AAC, M4A, WAV. If clips come out cut off or with
    extra silence, adjust the buffer-time setting in Tab 2.
    """)

    audio_example_path = "examples/U02-S09.mp3"
    if os.path.exists(audio_example_path):
        st.audio(audio_example_path)
        st.caption("Example recording: preamble, then \"1\", vocab word, \"2\", vocab word, ...")
    else:
        st.info("Example file not bundled in this deployment.")

# ============================================================================
# TAB 1: EXTRACT IMAGES
# ============================================================================
with tab1:
    st.header("Add Images")

    image_source = st.radio(
        "Image source",
        ["📄 Extract from Word Document", "🖼️ Upload Photos Directly"],
        key="image_source_mode",
        horizontal=True,
    )

    if image_source == "📄 Extract from Word Document":
        st.markdown("Upload a .docx file with numbered paragraphs and images")

        docx_file = st.file_uploader(
            "Upload Word Document (.docx)",
            type=['docx'],
            key='docx',
            help="Drag and drop a file or click Browse files"
        )

        if st.button("Extract Images", key='extract_images_btn'):
            if docx_file is None:
                st.error("Please upload a Word document first")
            else:
                try:
                    _report(issue_report.record_upload, docx_file.name, docx_file.getvalue())
                    _report(issue_report.record_event, "extract_images", {"file": docx_file.name})
                    with st.spinner("Extracting images..."):
                        # Create temp directory for images
                        if st.session_state.temp_images:
                            shutil.rmtree(st.session_state.temp_images, ignore_errors=True)
                        st.session_state.temp_images = tempfile.mkdtemp(prefix="anki_images_")

                        # Save uploaded file temporarily
                        temp_docx = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
                        temp_docx.write(docx_file.getvalue())
                        temp_docx.close()

                        # Extract images
                        result = extract_numbered_images(temp_docx.name, st.session_state.temp_images)

                        # Clean up temp docx
                        os.unlink(temp_docx.name)

                        # Get list of extracted files
                        st.session_state.image_files = sorted(
                            [f for f in os.listdir(st.session_state.temp_images) if f.endswith('.png')],
                            key=lambda x: int(m.group()) if (m := re.search(r'\d+', x)) else 999
                        )

                        _report(issue_report.record_event, "extract_images_result", {},
                            {"count": result["count"],
                             "skipped_unconvertible": result["skipped_unconvertible"],
                             "files": st.session_state.image_files},
                        )

                        st.success(f"Extracted {len(st.session_state.image_files)} images!")
                        if result['skipped_unconvertible']:
                            st.warning(
                                "Skipped (image format can't be converted — e.g. Word ink or WMF/EMF drawings): "
                                + ", ".join(result['skipped_unconvertible'])
                            )
                except Exception as e:
                    _report(issue_report.record_error, "extract_images", e)
                    st.error(f"Error extracting images: {str(e)}")
    else:
        st.markdown(
            "Upload individual photo files named with their card number, e.g. "
            "`1.jpg`, `2.jpg` — the first number found anywhere in the filename "
            "is used, so `img_3.jpg` or `vocab-3-final.png` both become card 3."
        )

        photo_files = st.file_uploader(
            "Upload Photos",
            type=['jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'webp', 'ppm'],
            accept_multiple_files=True,
            key='photos',
            help="Drag and drop files or click Browse files"
        )

        if st.button("Use These Photos", key='use_photos_btn'):
            if not photo_files:
                st.error("Please upload photo files first")
            else:
                try:
                    with st.spinner("Processing photos..."):
                        if st.session_state.temp_images:
                            shutil.rmtree(st.session_state.temp_images, ignore_errors=True)
                        st.session_state.temp_images = tempfile.mkdtemp(prefix="anki_images_")

                        uploads = [(f.name, f.getvalue()) for f in photo_files]
                        for _n, _d in uploads:
                            _report(issue_report.record_upload, _n, _d)
                        _report(issue_report.record_event, "use_photos", {"files": [n for n, _ in uploads]})
                        result = save_numbered_photos(uploads, st.session_state.temp_images)
                        _report(issue_report.record_event, "use_photos_result", {}, result)

                        st.session_state.image_files = sorted(
                            [f for f in os.listdir(st.session_state.temp_images) if f.endswith('.png')],
                            key=lambda x: int(m.group()) if (m := re.search(r'\d+', x)) else 999
                        )

                        st.success(f"Loaded {len(result['saved'])} photos!")
                        if result['skipped_no_number']:
                            st.warning(
                                "Skipped (no number found in filename): "
                                + ", ".join(result['skipped_no_number'])
                            )
                        if result['skipped_duplicate']:
                            st.warning(
                                "Skipped (duplicate number, first one kept): "
                                + ", ".join(result['skipped_duplicate'])
                            )
                        if result['skipped_unreadable']:
                            st.warning(
                                "Skipped (unreadable image file): "
                                + ", ".join(result['skipped_unreadable'])
                            )
                except Exception as e:
                    _report(issue_report.record_error, "use_photos", e)
                    st.error(f"Error processing photos: {str(e)}")

    # Display extracted images (shared by both image sources above)
    if st.session_state.image_files:
        st.subheader(f"Extracted Images ({len(st.session_state.image_files)})")
        cols = st.columns(4)
        for idx, img_file in enumerate(st.session_state.image_files[:20]):  # Show first 20
            with cols[idx % 4]:
                img_path = os.path.join(st.session_state.temp_images, img_file)
                st.image(img_path, caption=img_file, use_container_width=True)
        if len(st.session_state.image_files) > 20:
            st.info(f"Showing first 20 of {len(st.session_state.image_files)} images")

# ============================================================================
# TAB 2: EXTRACT AUDIO
# ============================================================================
with tab2:
    st.header("Extract Audio Clips")
    audio_source = st.radio(
        "Audio source",
        ["🎙️ Extract from Recording", "🔊 Upload Audio Clips Directly"],
        key="audio_source_mode",
        horizontal=True,
    )

    if audio_source == "🎙️ Extract from Recording":
        st.markdown("Upload an audio file (MP3/AAC/M4A) to extract numbered vocabulary clips")
        with st.popover("Settings"):

            # API Type Selection
            api_type = st.selectbox(
                "Whisper API",
                ["local", "groq", "openai"],
                format_func=lambda x: {
                    "local": "Local (faster-whisper)",
                    "groq": "Groq API (fastest)",
                    "openai": "OpenAI API"
                }[x],
                help="Choose which Whisper API to use for transcription"
            )

            # Model size only for local
            if api_type == "local":
                model_size = st.selectbox("Model Size", ["tiny", "base", "small", "medium", "large"], index=3)
                use_vad = st.checkbox("Use VAD Filter", value=False, help="Voice Activity Detection - disable if getting 0 words transcribed")
            else:
                model_size = "small"  # Default, not used for API
                use_vad = False
                api_key = st.text_input(
                    f"{api_type.upper()} API Key",
                    type="password",
                    help=f"Enter your {api_type.upper()} API key or set {api_type.upper()}_API_KEY environment variable"
                )

            buffer_ms = st.number_input("Buffer (ms)", min_value=0, max_value=1000, value=400, step=50)
            debug_mode = st.checkbox("Show Debug Info", value=True, help="Display transcription details for troubleshooting")
        

        audio_file = st.file_uploader(
            "Upload Audio File",
            type=['mp3', 'aac', 'm4a', 'wav'],
            key='audio',
            help="Drag and drop a file or click Browse files"
        )


        if st.button("Extract Audio Clips", key='extract_audio_btn'):
            if audio_file is None:
                st.error("Please upload an audio file first")
            else:
                try:
                    _report(issue_report.record_upload, audio_file.name, audio_file.getvalue())
                    _report(issue_report.record_event, "extract_audio",
                        {"file": audio_file.name, "api_type": api_type, "model_size": model_size,
                         "use_vad": use_vad, "buffer_ms": buffer_ms,
                         "api_key": api_key if api_type != "local" else None},
                    )
                    api_label = {"local": f"Local Whisper ({model_size})", "groq": "Groq API", "openai": "OpenAI API"}[api_type]
                    with st.spinner(f"Processing audio with {api_label}... This may take a few minutes."):
                        # Create temp directory for audio
                        if st.session_state.temp_audio:
                            shutil.rmtree(st.session_state.temp_audio, ignore_errors=True)
                        st.session_state.temp_audio = tempfile.mkdtemp(prefix="anki_audio_")

                        # Save uploaded file temporarily
                        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(audio_file.name)[1])
                        temp_audio.write(audio_file.getvalue())
                        temp_audio.close()

                        # Extract audio clips
                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        # Get API key if using API
                        current_api_key = api_key if api_type != "local" else None

                        result = extract_audio_clips(
                            temp_audio.name,
                            st.session_state.temp_audio,
                            model_size=model_size,
                            buffer_ms=buffer_ms,
                            use_vad=use_vad,
                            api_type=api_type,
                            api_key=current_api_key,
                            progress_callback=lambda p, s: (progress_bar.progress(p), status_text.text(s)),
                            debug=True  # always collect debug info for the issue report
                        )

                        clip_count, debug_info = result

                        _report(issue_report.record_event, "extract_audio_result", {},
                            debug_info,
                        )

                        # Clean up temp audio file
                        os.unlink(temp_audio.name)

                        # Get list of extracted files
                        st.session_state.audio_files = sorted(
                            [f for f in os.listdir(st.session_state.temp_audio) if f.endswith('.mp3')],
                            key=lambda x: int(m.group()) if (m := re.search(r'\d+', x)) else 999
                        )

                        progress_bar.progress(100)
                        status_text.text("Complete!")

                        if clip_count == 0:
                            st.warning(f"Extracted 0 audio clips!")
                        else:
                            st.success(f"Extracted {len(st.session_state.audio_files)} audio clips!")

                        # Display debug info
                        if debug_mode and debug_info:
                            with st.expander("Debug Information", expanded=(clip_count == 0)):
                                st.write(f"**API Type:** {debug_info.get('api_type', 'unknown').upper()}")
                                st.write(f"**Audio Duration:** {debug_info.get('audio_duration', 0):.2f} seconds")

                                st.write("**Whisper Info:**")
                                whisper_info = debug_info.get('whisper_info', {})
                                st.write(f"  - Language detected: {whisper_info.get('language', 'unknown')}")
                                st.write(f"  - Duration: {whisper_info.get('duration', 0):.2f}s")
                                st.write(f"  - Transcription pass: {whisper_info.get('pass', 'n/a')}")

                                st.write(f"**Segments found:** {debug_info.get('segment_count', 0)}")
                                st.write(f"**Total words transcribed:** {debug_info['total_words']}")
                                st.write(f"**Detected numbers:** {len(debug_info['detected_numbers'])}")

                                if debug_info.get('errors'):
                                    st.error("**Errors:**")
                                    for error in debug_info['errors']:
                                        st.text(error)

                                st.write("**Full Transcription:**")
                                st.text_area("Transcription", debug_info['transcription'], height=100)

                                if debug_info['first_20_words']:
                                    st.write("**First 20 words (with normalized form):**")
                                    for word in debug_info['first_20_words']:
                                        st.text(word)

                                if debug_info['detected_numbers']:
                                    st.write("**Detected Numbers:**")
                                    for num_info in debug_info['detected_numbers']:
                                        st.text(f"Number {num_info['number']} at position {num_info['position']}: '{num_info['word']}' ({num_info['match_type']}, score {num_info['score']})")
                                else:
                                    st.error("No numbers detected! Check if the audio contains spoken numbers like 'one', 'two', 'number one', etc.")

                except Exception as e:
                    _report(issue_report.record_error, "extract_audio", e)
                    st.error(f"Error extracting audio: {str(e)}")
                    import traceback
                    st.code(traceback.format_exc())
    else:
        st.markdown(
            "Upload individual audio clips named with their card number, e.g. `1.mp3`, `2.mp3` — "
            "the first number found anywhere in the filename is used, so `clip_3.m4a` or "
            "`word-3.wav` both become card 3. Non-MP3 files are converted to MP3."
        )

        audio_clip_files = st.file_uploader(
            "Upload Audio Clips",
            type=['mp3', 'm4a', 'aac', 'wav', 'ogg', 'flac'],
            accept_multiple_files=True,
            key='audio_clips',
            help="Drag and drop files or click Browse files"
        )

        if st.button("Use These Audio Files", key='use_audio_clips_btn'):
            if not audio_clip_files:
                st.error("Please upload audio files first")
            else:
                try:
                    with st.spinner("Processing audio files..."):
                        if st.session_state.temp_audio:
                            shutil.rmtree(st.session_state.temp_audio, ignore_errors=True)
                        st.session_state.temp_audio = tempfile.mkdtemp(prefix="anki_audio_")

                        uploads = [(f.name, f.getvalue()) for f in audio_clip_files]
                        for _n, _d in uploads:
                            _report(issue_report.record_upload, _n, _d)
                        _report(issue_report.record_event, "use_audio_clips", {"files": [n for n, _ in uploads]})
                        result = save_numbered_audio(uploads, st.session_state.temp_audio)
                        _report(issue_report.record_event, "use_audio_clips_result", {}, result)

                        st.session_state.audio_files = sorted(
                            [f for f in os.listdir(st.session_state.temp_audio) if f.endswith('.mp3')],
                            key=lambda x: int(m.group()) if (m := re.search(r'\d+', x)) else 999
                        )

                        st.success(f"Loaded {len(result['saved'])} audio clips!")
                        if result['skipped_no_number']:
                            st.warning(
                                "Skipped (no number found in filename): "
                                + ", ".join(result['skipped_no_number'])
                            )
                        if result['skipped_duplicate']:
                            st.warning(
                                "Skipped (duplicate number, first one kept): "
                                + ", ".join(result['skipped_duplicate'])
                            )
                        if result['skipped_unreadable']:
                            st.warning(
                                "Skipped (unreadable audio file): "
                                + ", ".join(result['skipped_unreadable'])
                            )
                except Exception as e:
                    _report(issue_report.record_error, "use_audio_clips", e)
                    st.error(f"Error processing audio files: {str(e)}")

    # Display extracted audio clips
    if st.session_state.audio_files:
        st.subheader(f"Extracted Audio Clips ({len(st.session_state.audio_files)})")

        # Create ZIP file download button
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for audio_file_name in st.session_state.audio_files:
                audio_path = os.path.join(st.session_state.temp_audio, audio_file_name)
                zip_file.write(audio_path, audio_file_name)
        zip_buffer.seek(0)

        st.download_button(
            label=f"📥 Download All Audio Files ({len(st.session_state.audio_files)} clips)",
            data=zip_buffer,
            file_name="audio_clips.zip",
            mime="application/zip",
            key='download_audio_zip'
        )

        with st.expander("➕ Add or replace a clip", expanded=False):
            st.caption(
                "Upload one clip named with its card number (e.g. `9.mp3`). "
                "It fills in a missing card or replaces the existing clip with that number."
            )
            add_clip_file = st.file_uploader(
                "Clip",
                type=['mp3', 'm4a', 'aac', 'wav', 'ogg', 'flac'],
                key='add_clip'
            )
            if st.button("Add to clips", key='add_clip_btn'):
                if add_clip_file is None:
                    st.error("Please choose an audio file first")
                else:
                    try:
                        clip_bytes = add_clip_file.getvalue()
                        existing = set(st.session_state.audio_files)
                        _report(issue_report.record_upload, add_clip_file.name, clip_bytes)
                        _report(issue_report.record_event, "add_clip", {"file": add_clip_file.name})
                        result = save_numbered_audio(
                            [(add_clip_file.name, clip_bytes)], st.session_state.temp_audio
                        )
                        _report(issue_report.record_event, "add_clip_result", {}, result)
                        if result['saved']:
                            num = result['saved'][0]
                            verb = "Replaced" if f"{num}.mp3" in existing else "Added"
                            st.session_state.audio_files = sorted(
                                [f for f in os.listdir(st.session_state.temp_audio) if f.endswith('.mp3')],
                                key=lambda x: int(m.group()) if (m := re.search(r'\d+', x)) else 999
                            )
                            st.session_state.add_clip_message = (
                                f"{verb} card {num}."
                                + (" Run Pair Files again (Tab 3) to use it." if st.session_state.paired_files else "")
                            )
                            st.rerun()
                        elif result['skipped_no_number']:
                            st.warning(f"No card number found in the filename: {add_clip_file.name}")
                        else:
                            st.warning(f"Couldn't read that audio file: {add_clip_file.name}")
                    except Exception as e:
                        _report(issue_report.record_error, "add_clip", e)
                        st.error(f"Error adding clip: {str(e)}")
            if st.session_state.get("add_clip_message"):
                st.success(st.session_state.pop("add_clip_message"))

        st.markdown("---")

        # Display audio clips
        for audio_file_name in st.session_state.audio_files[:10]:  # Show first 10
            audio_path = os.path.join(st.session_state.temp_audio, audio_file_name)
            col1, col2 = st.columns([1, 3])
            with col1:
                st.text(audio_file_name)
            with col2:
                st.audio(audio_path)
        if len(st.session_state.audio_files) > 10:
            st.info(f"Showing first 10 of {len(st.session_state.audio_files)} clips")

# ============================================================================
# TAB 3: PAIR FILES
# ============================================================================
with tab3:
    st.header("Pair Audio and Images")
    st.markdown("Match audio clips with images by number")

    if st.button("Pair Files", key='pair_btn'):
        if not st.session_state.image_files:
            st.error("Please extract images first (Tab 1)")
        elif not st.session_state.audio_files:
            st.error("Please extract audio clips first (Tab 2)")
        else:
            try:
                with st.spinner("Pairing files..."):
                    # Create final directory
                    if st.session_state.temp_final:
                        shutil.rmtree(st.session_state.temp_final, ignore_errors=True)
                    st.session_state.temp_final = tempfile.mkdtemp(prefix="anki_final_")

                    # Pair files
                    paired = pair_files(
                        st.session_state.temp_images,
                        st.session_state.temp_audio,
                        st.session_state.temp_final
                    )

                    st.session_state.paired_files = paired
                    _report(issue_report.record_event, "pair_files", {},
                        {"pairs": [(n, os.path.basename(a), os.path.basename(i))
                                   for n, a, i in st.session_state.paired_files]},
                    )
                    st.success(f"Paired {len(paired)} files!")
            except Exception as e:
                _report(issue_report.record_error, "pair_files", e)
                st.error(f"Error pairing files: {str(e)}")

    # Display paired files
    if st.session_state.paired_files:
        st.subheader(f"Paired Files ({len(st.session_state.paired_files)})")

        # Show warnings for unpaired files
        image_nums = {int(m.group()) for f in st.session_state.image_files if (m := re.search(r'\d+', f))}
        audio_nums = {int(m.group()) for f in st.session_state.audio_files if (m := re.search(r'\d+', f))}

        missing_audio = image_nums - audio_nums
        missing_images = audio_nums - image_nums

        if missing_audio:
            st.warning(f"Images without audio: {sorted(missing_audio)}")
        if missing_images:
            st.warning(f"Audio without images: {sorted(missing_images)}")

        # Management controls
        st.markdown("**Manage Paired Cards:**")

        # Display all pairs with management options
        for idx, (num, audio_path, image_path) in enumerate(st.session_state.paired_files):
            with st.expander(f"Card {num}", expanded=False):
                col1, col2 = st.columns(2)
                with col1:
                    st.image(image_path, caption=f"Image {num}", use_container_width=True)
                with col2:
                    st.audio(audio_path)

                # Management buttons
                st.markdown("---")
                mgmt_col1, mgmt_col2, mgmt_col3 = st.columns([1, 1, 1])

                with mgmt_col1:
                    if st.button(f"🗑️ Remove", key=f"remove_{idx}_{num}"):
                        # Remove from session state
                        st.session_state.paired_files.pop(idx)
                        # Remove files from temp_final directory
                        try:
                            if os.path.exists(audio_path):
                                os.remove(audio_path)
                            if os.path.exists(image_path):
                                os.remove(image_path)
                        except Exception as e:
                            _report(issue_report.record_error, "remove_pair", e)
                            st.error(f"Error removing files: {str(e)}")
                        _report(issue_report.record_event, "remove_pair", {"number": num, "target": None})
                        st.rerun()

                with mgmt_col2:
                    # Get list of other card numbers for swapping
                    other_cards = [n for i, (n, _, _) in enumerate(st.session_state.paired_files) if i != idx]
                    if other_cards:
                        swap_audio_target = st.selectbox(
                            "Swap Audio with Card:",
                            options=[None] + other_cards,
                            key=f"swap_audio_{idx}_{num}",
                            format_func=lambda x: "Select card..." if x is None else f"Card {x}"
                        )
                        if swap_audio_target is not None:
                            if st.button(f"↔️ Swap Audio", key=f"swap_audio_btn_{idx}_{num}"):
                                # Find the target pair
                                target_idx = next(i for i, (n, _, _) in enumerate(st.session_state.paired_files) if n == swap_audio_target)
                                # Swap audio files in session state
                                pairs = st.session_state.paired_files
                                pairs[idx] = (pairs[idx][0], pairs[target_idx][1], pairs[idx][2])
                                pairs[target_idx] = (pairs[target_idx][0], audio_path, pairs[target_idx][2])
                                st.session_state.paired_files = pairs
                                _report(issue_report.record_event, "swap_audio",
                                    {"number": num, "target": swap_audio_target})
                                st.success(f"Swapped audio between Card {num} and Card {swap_audio_target}")
                                st.rerun()

                with mgmt_col3:
                    if other_cards:
                        swap_image_target = st.selectbox(
                            "Swap Image with Card:",
                            options=[None] + other_cards,
                            key=f"swap_image_{idx}_{num}",
                            format_func=lambda x: "Select card..." if x is None else f"Card {x}"
                        )
                        if swap_image_target is not None:
                            if st.button(f"↔️ Swap Image", key=f"swap_image_btn_{idx}_{num}"):
                                # Find the target pair
                                target_idx = next(i for i, (n, _, _) in enumerate(st.session_state.paired_files) if n == swap_image_target)
                                # Swap image files in session state
                                pairs = st.session_state.paired_files
                                pairs[idx] = (pairs[idx][0], pairs[idx][1], pairs[target_idx][2])
                                pairs[target_idx] = (pairs[target_idx][0], pairs[target_idx][1], image_path)
                                st.session_state.paired_files = pairs
                                _report(issue_report.record_event, "swap_image",
                                    {"number": num, "target": swap_image_target})
                                st.success(f"Swapped image between Card {num} and Card {swap_image_target}")
                                st.rerun()

        st.info(f"💡 Tip: You can remove unwanted pairs or swap audio/images between cards before exporting.")

# ============================================================================
# TAB 4: EXPORT ANKI DECK
# ============================================================================
with tab4:
    st.header("Export Anki Deck")
    st.markdown("Generate an .apkg file for direct import into Anki")

    # Card Style Selection
    st.subheader("Card Style")
    card_style = st.radio(
        "Choose card template:",
        options=["audio_to_image", "audio_only", "image_only", "both_sides"],
        index=0,
        format_func=lambda x: {
            "audio_to_image": "Two Cards: Audio→(Image+Sound) & Image→(Image+Sound) (Recommended)",
            "audio_only": "One Card: Audio→(Image+Sound)",
            "image_only": "One Card: Image→(Image+Sound)",
            "both_sides": "One Card: Audio + Image on front"
        }[x],
        help="Determines how many cards are created and what appears on each side"
    )

    # Show preview of selected style
    with st.expander("ℹ️ Card Style Preview"):
        if card_style == "audio_to_image":
            st.markdown("""
            **Creates 2 cards per item:**
            - Card 1: 🔊 Audio → (� Audio + �🖼️ Image)
            - Card 2: 🖼️ Image → (🔊 Audio + 🖼️ Image)

            Best for active recall and comprehensive learning!
            The answer side always shows both audio and image.
            """)
        elif card_style == "audio_only":
            st.markdown("""
            **Creates 1 card per item:**
            - Front: 🔊 Audio
            - Back: � Audio + �🖼️ Image

            Focus on audio recognition with complete feedback.
            """)
        elif card_style == "image_only":
            st.markdown("""
            **Creates 1 card per item:**
            - Front: 🖼️ Image
            - Back: 🔊 Audio + 🖼️ Image

            Focus on visual recognition with complete feedback.
            """)
        else:  # both_sides
            st.markdown("""
            **Creates 1 card per item:**
            - Front: 🔊 Audio + 🖼️ Image
            - Back: Card number

            Shows both clues on front side for review.
            """)

    st.markdown("---")

    # Deck Settings
    st.subheader("Deck Settings")
    col1, col2 = st.columns(2)

    with col1:
        deck_name = st.text_input("Deck Name", value="My Vocabulary Deck")

    with col2:
        tags = st.text_input("Tags (comma-separated)", value="auto,vocab")
        unit_session = st.text_input("Unit/Session Prefix", value="Unit_1_Session_1")

    if st.button("Generate Anki Deck (.apkg)", key='export_btn'):
        if not st.session_state.paired_files:
            st.error("Please pair files first (Tab 3)")
        else:
            try:
                with st.spinner("Creating Anki deck..."):
                    # Create deck with appropriate note type name
                    if card_style == "audio_to_image":
                        model_name = "Vocabulary (Audio/Image → Both)"
                    elif card_style == "audio_only":
                        model_name = "Vocabulary (Audio → Both)"
                    elif card_style == "image_only":
                        model_name = "Vocabulary (Image → Both)"
                    else:  # both_sides
                        model_name = "Vocabulary (Both on Front)"
                    
                    _report(issue_report.record_event, "create_deck",
                        {"card_style": card_style, "deck_name": deck_name, "tags": tags,
                         "unit_session": unit_session},
                    )
                    apkg_path = create_anki_deck(
                        st.session_state.paired_files,
                        st.session_state.temp_final,
                        deck_name,
                        model_name,
                        tags.split(','),
                        unit_session,
                        card_style=card_style
                    )

                    _report(issue_report.record_event, "create_deck_result", {},
                        {"pairs": len(st.session_state.paired_files)},
                    )

                    # Read file for download
                    with open(apkg_path, 'rb') as f:
                        apkg_data = f.read()

                    # Calculate total cards based on style
                    if card_style == "audio_to_image":
                        total_cards = len(st.session_state.paired_files) * 2
                        st.success(f"Deck created successfully! {total_cards} cards ({len(st.session_state.paired_files)} items × 2 cards each)")
                    else:
                        st.success(f"Deck created successfully! {len(st.session_state.paired_files)} cards")

                    # Download button
                    st.download_button(
                        label="Download .apkg File",
                        data=apkg_data,
                        file_name=f"{deck_name.replace(' ', '_')}.apkg",
                        mime="application/apkg"
                    )
            except Exception as e:
                _report(issue_report.record_error, "create_deck", e)
                st.error(f"Error creating deck: {str(e)}")

# Sidebar with documentation and utilities
with st.sidebar:
    st.header("📖 How to Use")

    with st.expander("🎯 Quick Start Guide", expanded=False):
        st.markdown("""
        ### Step-by-Step Instructions

        **1️⃣ Extract Images**
        - Upload a `.docx` Word document containing numbered paragraphs and images
        - Click "Extract Images" to extract all images
        - Images will be automatically numbered based on the document structure

        **2️⃣ Extract Audio**
        - Upload an audio file (MP3, AAC, M4A, or WAV)
        - Configure Whisper API settings (Local, Groq, or OpenAI)
        - Click "Extract Audio Clips" to transcribe and extract numbered vocabulary
        - The system detects spoken numbers (e.g., "one", "two", "number one")

        **3️⃣ Pair Files**
        - Click "Pair Files" to match audio clips with images by number
        - Review matched pairs and check for any warnings

        **4️⃣ Export Deck**
        - Choose your preferred card style
        - Set deck name and tags
        - Click "Generate Anki Deck" and download the .apkg file
        - Import the .apkg file into Anki
        """)

    with st.expander("⚙️ Advanced Settings & Tips", expanded=False):
        st.markdown("""
        ### Whisper API Options

        **Local (faster-whisper)**
        - Runs on your machine
        - No API key needed
        - Slower but free
        - Adjust model size for speed/accuracy tradeoff

        **Groq API** (Recommended)
        - Fastest option
        - Requires API key
        - Very accurate

        **OpenAI API**
        - High quality
        - Requires API key and credits
        - Good for complex audio

        ### Audio Format Tips
        - Speak numbers clearly: "one", "two", "three"
        - Or say "number one", "number two", etc.
        - Pause between items for best results
        - Adjust buffer time (default 400ms) if clips are cut off

        ### Card Styles
        - **Audio→Image (Recommended)**: Creates 2 cards for maximum practice
        - **Audio Only**: Focus on listening comprehension
        - **Image Only**: Focus on visual recognition
        - **Both Sides**: Review mode with everything visible
        """)

    with st.expander("🐛 Troubleshooting", expanded=False):
        st.markdown("""
        ### Common Issues

        **No audio clips extracted?**
        - Enable "Show Debug Info" to see what was transcribed
        - Try disabling "VAD Filter" if using local Whisper
        - Check if numbers are spoken clearly in the audio
        - Try a different Whisper API (Groq is most reliable)

        **Images not extracting?**
        - Ensure document is in .docx format (not .doc)
        - Check that images are properly embedded in Word

        **File upload not working?**
        - If drag-and-drop doesn't work, use the "Browse files" button
        - Check file size is under 200MB
        - Ensure your browser allows file uploads
        - If embedded in iframe, some browsers may limit drag-and-drop

        **Cards not importing into Anki?**
        - Make sure you're using Anki Desktop (not AnkiWeb)
        - Try different deck/note type names if conflicts exist
        """)

    st.markdown("---")

    st.header("🛠️ Utilities")
    if st.button("Clear All Data", help="Remove all extracted files and reset the session"):
        for temp_dir in [st.session_state.temp_images, st.session_state.temp_audio, st.session_state.temp_final]:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

        st.session_state.temp_images = None
        st.session_state.temp_audio = None
        st.session_state.temp_final = None
        st.session_state.image_files = []
        st.session_state.audio_files = []
        st.session_state.paired_files = []
        st.session_state.issue_report = issue_report.clear_report(st.session_state.issue_report)
        st.session_state.pop("issue_report_zip", None)
        usage_log.log_event(st.session_state.usage_session, "reset")
        st.success("All data cleared!")
        st.rerun()

    st.markdown("---")

    st.header("ℹ️ About")
    st.markdown("""
    **Anki Deck Creator** automatically generates Anki flashcard decks from Word documents and audio files.

    Perfect for language learning, vocabulary building, and spaced repetition study.

    Version 1.0
    """)

    st.markdown("---")

    # Current session info
    st.header("📊 Session Info")
    if st.session_state.image_files:
        st.info(f"🖼️ {len(st.session_state.image_files)} images extracted")
    if st.session_state.audio_files:
        st.info(f"🔊 {len(st.session_state.audio_files)} audio clips extracted")
    if st.session_state.paired_files:
        st.success(f"✅ {len(st.session_state.paired_files)} pairs ready")

# Footer
st.markdown("---")
_, report_col, _ = st.columns([1, 2, 1])
with report_col:
    with st.expander("🐞 Report an issue", expanded=False):
        st.caption(
            "Downloads a zip with your uploaded files (documents, recordings, photos), "
            "the app's outputs and debug logs. Send it to the email below. "
            "Prepare again after trying more steps."
        )
        report_note = st.text_area("What went wrong?", key="report_note")
        if st.button("Prepare report", key="prepare_report_btn"):
            try:
                st.session_state.issue_report_zip = issue_report.build_report_zip(
                    st.session_state.issue_report,
                    report_note,
                    {
                        "images": st.session_state.temp_images,
                        "audio": st.session_state.temp_audio,
                        "final": st.session_state.temp_final,
                    },
                    {"version": issue_report.app_version()},
                )
                st.session_state.issue_report_name = datetime.now().strftime("anki-report-%Y-%m-%d-%H%M.zip")
            except Exception as e:
                st.error(f"Couldn't prepare the report: {e}")
        if st.session_state.get("issue_report_zip"):
            st.download_button(
                "Download report (.zip)",
                data=st.session_state.issue_report_zip,
                file_name=st.session_state.issue_report_name,
                mime="application/zip",
                key="download_report_btn",
            )
    st.caption("Anonymous usage stats (file names, sizes, step outcomes and settings such as model or card style) are logged to improve the app.")

    if os.environ.get("ADMIN_TOKEN") and st.query_params.get("admin") == "1":
        entered = st.text_input("Admin password", type="password")
        if entered:
            st.session_state.admin_ok = _admin_token_ok(entered)
            if not st.session_state.admin_ok:
                st.error("Incorrect password")
        else:
            st.session_state.admin_ok = False
        if st.session_state.admin_ok:
            summary = _usage_summary_text()
            if summary is None:
                st.info("No usage log yet.")
            else:
                try:
                    with open(usage_log.log_path(), "rb") as f:
                        raw = f.read()
                except OSError:
                    raw = None
                if raw is None:
                    st.info("No usage log yet.")
                else:
                    st.code(summary, language=None)
                    st.download_button("Download usage.jsonl", data=raw, file_name="usage.jsonl",
                                       mime="application/x-ndjson", key="download_usage_btn")

st.markdown(
    """
    <div style='text-align: center; color: #555; padding: 20px 0;'>
        <p>Made with ❤️ by Brennan and Price</p>
        <p>Contact <a href='mailto:joshuajangprice@gmail.com' style='color: #1f77b4; text-decoration: none;'>joshuajangprice@gmail.com</a> for any bugs or issues</p>
    </div>
    """,
    unsafe_allow_html=True
)
