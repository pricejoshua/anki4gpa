# Tutorial Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a first "📘 Tutorial" tab to the Streamlit app that teaches the required Word-document and audio-file formats using the real bundled example files.

**Architecture:** A single new `with tab0:` block added inline in `app.py`, following the existing per-tab pattern used by the other four tabs. No new modules, no new session state, no new dependencies — just static markdown content plus a file-download button and an audio player, both guarded by `os.path.exists`.

**Tech Stack:** Streamlit (`st.tabs`, `st.download_button`, `st.audio`, `st.markdown`), Python `os.path`.

## Global Constraints

- Tab order becomes: `["📘 Tutorial", "1️⃣ Extract Images", "2️⃣ Extract Audio", "3️⃣ Pair Files", "4️⃣ Export Deck"]` — Tutorial is first.
- Reference example files by relative path from project root: `examples/Unit 2 Session 9 Lesson Plan 2025.docx` and `examples/U02-S09.aac`.
- Both the docx download button and the audio player must be guarded with `os.path.exists(...)`; if missing, show `st.info("Example file not bundled in this deployment.")` instead of erroring.
- Do not modify `image_extractor.py`, `audio_extractor.py`, `file_pairer.py`, or `deck_creator.py` — this is a display-only addition.
- Do not add a "try it yourself" flow that pre-fills Tabs 1–2 — tutorial is read/watch/listen only.
- No new pip dependencies.

---

### Task 1: Add Tutorial tab to `app.py`

**Files:**
- Modify: `app.py:68-74` (tab setup) and insert new tab content block before the existing `# TAB 1: EXTRACT IMAGES` section (currently starting at `app.py:76`)

**Interfaces:**
- Consumes: nothing from other tabs (no shared session state needed for this tab).
- Produces: nothing consumed by other tabs — this is a leaf addition. `tab0` variable name added to the `st.tabs(...)` unpacking alongside existing `tab1, tab2, tab3, tab4`.

- [ ] **Step 1: Update the tab setup call**

Current code at `app.py:68-74`:

```python
# === TAB SETUP ===
tab1, tab2, tab3, tab4 = st.tabs([
    "1️⃣ Extract Images",
    "2️⃣ Extract Audio",
    "3️⃣ Pair Files",
    "4️⃣ Export Deck"
])
```

Replace with:

```python
# === TAB SETUP ===
tab0, tab1, tab2, tab3, tab4 = st.tabs([
    "📘 Tutorial",
    "1️⃣ Extract Images",
    "2️⃣ Extract Audio",
    "3️⃣ Pair Files",
    "4️⃣ Export Deck"
])
```

- [ ] **Step 2: Insert the Tutorial tab content block**

Insert this new section immediately after the tab setup block (i.e., right before the existing `# TAB 1: EXTRACT IMAGES` comment block at `app.py:76`):

```python
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

    audio_example_path = "examples/U02-S09.aac"
    if os.path.exists(audio_example_path):
        st.audio(audio_example_path)
        st.caption("Example recording: preamble, then \"1\", vocab word, \"2\", vocab word, ...")
    else:
        st.info("Example file not bundled in this deployment.")

```

- [ ] **Step 3: Manually verify with the Streamlit dev server**

Run: `streamlit run app.py`
Expected: App launches, first tab is "📘 Tutorial", it shows the overview text, the Word-document explanation with a working download button that downloads the example `.docx`, and the audio-format explanation with a working inline player for the example `.aac`. The four original tabs still exist and work exactly as before (unpaired functional change).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "$(cat <<'EOF'
Add tutorial tab explaining docx/audio format requirements

Uses the bundled example files so new users can see and hear the
expected input structure before uploading their own.
EOF
)"
```
