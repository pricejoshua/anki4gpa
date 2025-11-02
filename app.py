"""
Anki Deck Creator - Streamlit Web Application
Creates Anki flashcard decks from Word documents and audio files
"""

import streamlit as st
import os
import re
import shutil
import tempfile

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

    docx_file = st.file_uploader("Upload Word Document (.docx)", type=['docx'], key='docx')

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

    col1, col2 = st.columns([2, 1])

    with col1:
        audio_file = st.file_uploader(
            "Upload Audio File",
            type=['mp3', 'aac', 'm4a', 'wav'],
            key='audio'
        )

    with col2:
        st.subheader("Settings")
        model_size = st.selectbox("Whisper Model", ["tiny", "base", "small", "medium", "large"], index=2)
        buffer_ms = st.number_input("Buffer (ms)", min_value=0, max_value=1000, value=400, step=50)
        use_vad = st.checkbox("Use VAD Filter", value=False, help="Voice Activity Detection - disable if getting 0 words transcribed")
        debug_mode = st.checkbox("Show Debug Info", value=True, help="Display transcription details for troubleshooting")

    if st.button("Extract Audio Clips", key='extract_audio_btn'):
        if audio_file is None:
            st.error("Please upload an audio file first")
        else:
            try:
                with st.spinner(f"Processing audio with Whisper {model_size} model... This may take a few minutes."):
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

                    result = extract_audio_clips(
                        temp_audio.name,
                        st.session_state.temp_audio,
                        model_size=model_size,
                        buffer_ms=buffer_ms,
                        use_vad=use_vad,
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
                            st.write(f"**Audio Duration:** {debug_info.get('audio_duration', 0):.2f} seconds")
                            st.write(f"**Audio Format:** {debug_info.get('audio_format', 'unknown')}")

                            st.write("**Whisper Info:**")
                            whisper_info = debug_info.get('whisper_info', {})
                            st.write(f"  - Language detected: {whisper_info.get('language', 'unknown')}")
                            st.write(f"  - Language probability: {whisper_info.get('language_probability', 0):.2f}")
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

    col1, col2 = st.columns(2)

    with col1:
        deck_name = st.text_input("Deck Name", value="My Vocabulary Deck")
        model_name = st.text_input("Note Type", value="Vocabulary")

    with col2:
        tags = st.text_input("Tags (comma-separated)", value="auto,vocab")
        unit_session = st.text_input("Unit/Session Prefix", value="Unit_1_Session_1")

    if st.button("Generate Anki Deck (.apkg)", key='export_btn'):
        if not st.session_state.paired_files:
            st.error("Please pair files first (Tab 3)")
        else:
            try:
                with st.spinner("Creating Anki deck..."):
                    # Create deck
                    apkg_path = create_anki_deck(
                        st.session_state.paired_files,
                        st.session_state.temp_final,
                        deck_name,
                        model_name,
                        tags.split(','),
                        unit_session
                    )

                    # Read file for download
                    with open(apkg_path, 'rb') as f:
                        apkg_data = f.read()

                    st.success("Deck created successfully!")

                    # Download button
                    st.download_button(
                        label="Download .apkg File",
                        data=apkg_data,
                        file_name=f"{deck_name.replace(' ', '_')}.apkg",
                        mime="application/apkg"
                    )
            except Exception as e:
                st.error(f"Error creating deck: {str(e)}")

# Add cleanup button in sidebar
with st.sidebar:
    st.header("Utilities")
    if st.button("Clear All Data"):
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
