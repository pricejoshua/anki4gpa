# Tutorial Tab Design

## Purpose

New users of the Anki Deck Creator Streamlit app (`app.py`) currently have to learn the
required Word-document and audio-file formats from the sidebar "Quick Start Guide" text
alone, with no visual or audible reference. This adds a dedicated tutorial screen that
uses the real example files already in the repo (`examples/Unit 2 Session 9 Lesson Plan
2025.docx` and `examples/U02-S09.aac`) to show, not just tell, what a valid input looks
like.

## Placement

Add a new first tab, "📘 Tutorial", before the existing four workflow tabs. The tab bar
becomes:

```
["📘 Tutorial", "1️⃣ Extract Images", "2️⃣ Extract Audio", "3️⃣ Pair Files", "4️⃣ Export Deck"]
```

The existing sidebar "Quick Start Guide" / "Advanced Settings & Tips" / "Troubleshooting"
expanders stay as-is — the tutorial tab is a richer, example-driven companion, not a
replacement.

## Content

### 1. Overview

One short paragraph plus a simple numbered list restating the 4-step pipeline (Extract
Images → Extract Audio → Pair Files → Export Deck), so a first-time user knows what's
coming before diving into format details.

### 2. Word Document Format

Explains, in this order:

- Images must appear in (or immediately near) a **numbered list item**. Both forms are
  supported and detected automatically: literal text like `1.` `2.` at the start of a
  paragraph, and Word's built-in automatic numbered-list formatting (`numPr`/`numId` in
  the docx XML) — the bundled example file actually uses the automatic-numbering form,
  not literal digits, confirming both paths matter in practice.
- The rest of the document can contain anything else (lesson objectives, activity
  tables, timing notes, etc.) — the extractor only looks at numbered-list paragraphs and
  ignores everything else. Users don't need to strip the doc down to just the vocab list.
- **Edge case warning:** if some *other* part of the document also uses numbered lists or
  literal digit-paragraphs (e.g., a numbered activity step), those images/paragraphs can
  be mistaken for vocabulary items. Recommend keeping the vocab image list as the only
  numbered list in the doc, or reviewing the extracted image count/filenames in Tab 1
  before proceeding.
- A `st.download_button` offering the actual example docx, so the user can open it in
  Word and see the real structure firsthand.

### 3. Audio File Format

Explains, in this order:

- Record any preamble/intro first — it's ignored entirely.
- Then say "1", then the vocabulary word, then "2", then the next vocabulary word, and so
  on. Numbers must appear in increasing order; saying "1" again at any point resets the
  sequence and discards previously extracted clips for that take (supports re-recording
  without editing the file).
- Supported formats: MP3, AAC, M4A, WAV. Mentions the buffer-time setting (Tab 2) for
  trimming clip boundaries if clips are cut off or include extra silence.
- An inline `st.audio` player loading the real example `examples/U02-S09.aac`, so the
  user can hear the actual preamble → "1" → word → "2" → word pattern.

## Implementation Notes

- Content lives directly in `app.py` as a new `with tab0:` block (matching the existing
  per-tab structure), not a separate module — the content is static markdown/UI, not
  logic, and keeping it inline matches how the other tabs are already organized in this
  file.
- Reference the example files by relative path from the project root:
  `examples/Unit 2 Session 9 Lesson Plan 2025.docx` and `examples/U02-S09.aac`.
- Guard both the download button and the audio player with `os.path.exists(...)` checks.
  If a file is missing in some deployment (e.g., a slimmed-down Docker image that
  excludes `examples/`), show `st.info("Example file not bundled in this deployment.")`
  instead of raising an error.
- No new session state, no new dependencies — this is static content plus two file reads.

## Out of Scope

- No change to the actual extraction logic (`image_extractor.py`, `audio_extractor.py`).
- No interactive "try it yourself with the example files" flow that pre-fills Tabs 1–2 —
  the tutorial is read/watch/listen only; users still upload their own files to run the
  pipeline.
