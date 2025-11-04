"""
Anki Deck Creator - Streamlit Web Application
Creates Anki flashcard decks from Word documents and audio files
"""

import streamlit as st
import os
import re
import shutil
import tempfile
import zipfile
from io import BytesIO

# Import our custom modules
from image_extractor import extract_numbered_images
from audio_extractor import extract_audio_clips
from file_pairer import pair_files
from deck_creator import create_anki_deck


# ============================================================================
# STREAMLIT APP
# ============================================================================

# Page config
st.set_page_config(
    page_title="Anki Deck Creator",
    page_icon="📚",
    layout="wide"
)

# Fix drag-and-drop for iframe embedding
st.markdown("""
    <script>
        // Fix drag and drop in iframes
        window.addEventListener('dragover', function(e) {
            e.preventDefault();
        });
        window.addEventListener('drop', function(e) {
            e.preventDefault();
        });
    </script>
    <style>
        /* Ensure file uploader is visible and functional */
        [data-testid="stFileUploader"] {
            border: 2px dashed #ccc;
            border-radius: 5px;
            padding: 20px;
            text-align: center;
        }
        [data-testid="stFileUploader"]:hover {
            border-color: #888;
            background-color: #f9f9f9;
        }
    </style>
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

# Header
st.title("📚 Anki Deck Creator")
st.markdown("Create Anki flashcard decks from Word documents and audio files")
st.markdown("---")

# === TAB SETUP ===
tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Extract Images",
    "2️⃣ Extract Audio",
    "3️⃣ Pair Files",
    "4️⃣ Export Deck"
])

# ============================================================================
# TAB 1: EXTRACT IMAGES
# ============================================================================
with tab1:
    st.header("Extract Images from Word Document")
    st.markdown("Upload a .docx file with numbered paragraphs and images")

    docx_file = st.file_uploader(
        "Upload Word Document (.docx)",
        type=['docx'],
        key='docx',
        help="Drag and drop a file here, or click 'Browse files' to select"
    )

    if st.button("Extract Images", key='extract_images_btn'):
        if docx_file is None:
            st.error("Please upload a Word document first")
        else:
            try:
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
                    extract_numbered_images(temp_docx.name, st.session_state.temp_images)

                    # Clean up temp docx
                    os.unlink(temp_docx.name)

                    # Get list of extracted files
                    st.session_state.image_files = sorted(
                        [f for f in os.listdir(st.session_state.temp_images) if f.endswith('.png')],
                        key=lambda x: int(m.group()) if (m := re.search(r'\d+', x)) else 999
                    )

                    st.success(f"Extracted {len(st.session_state.image_files)} images!")
            except Exception as e:
                st.error(f"Error extracting images: {str(e)}")

    # Display extracted images
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
            model_size = st.selectbox("Model Size", ["tiny", "base", "small", "medium", "large"], index=2)
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
        help="Drag and drop a file here, or click 'Browse files' to select"
    )


    if st.button("Extract Audio Clips", key='extract_audio_btn'):
        if audio_file is None:
            st.error("Please upload an audio file first")
        else:
            try:
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
                        debug=debug_mode
                    )

                    if debug_mode and isinstance(result, tuple):
                        clip_count, debug_info = result
                    else:
                        clip_count = result if isinstance(result, int) else result[0]
                        debug_info = None

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
                                    st.text(f"Number {num_info['number']} at position {num_info['position']}: '{num_info['word']}'")
                            else:
                                st.error("No numbers detected! Check if the audio contains spoken numbers like 'one', 'two', 'number one', etc.")

            except Exception as e:
                st.error(f"Error extracting audio: {str(e)}")
                import traceback
                st.code(traceback.format_exc())

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
                    st.success(f"Paired {len(paired)} files!")
            except Exception as e:
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

        # Display sample pairs
        for num, audio_path, image_path in st.session_state.paired_files[:5]:
            with st.expander(f"Card {num}"):
                col1, col2 = st.columns(2)
                with col1:
                    st.image(image_path, caption=f"Image {num}", use_container_width=True)
                with col2:
                    st.audio(audio_path)

        if len(st.session_state.paired_files) > 5:
            st.info(f"Showing first 5 of {len(st.session_state.paired_files)} pairs")

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
                    
                    apkg_path = create_anki_deck(
                        st.session_state.paired_files,
                        st.session_state.temp_final,
                        deck_name,
                        model_name,
                        tags.split(','),
                        unit_session,
                        card_style=card_style
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

    with st.expander("⚙️ Settings & Tips", expanded=False):
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
        - Try using the "Browse files" button instead of drag-and-drop
        - If embedded in iframe, drag-and-drop may not work
        - Check file size is under 200MB

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
st.markdown(
    """
    <div style='text-align: center; color: #555; padding: 20px 0;'>
        <p>Made with ❤️ by Brennan and Price</p>
        <p>Contact <a href='mailto:joshuajangprice@gmail.com' style='color: #1f77b4; text-decoration: none;'>joshuajangprice@gmail.com</a> for any bugs or issues</p>
    </div>
    """,
    unsafe_allow_html=True
)
