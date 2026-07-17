# Direct Photo Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users in Tab 1 of the Anki Deck Creator upload individual numbered photo files (e.g. `1.jpg`, `2.jpg`) directly, as an alternative to extracting images from a Word document.

**Architecture:** A new pure function `save_numbered_photos()` in `image_extractor.py` takes a list of `(filename, bytes)` uploads and a destination folder, converts each to a numbered PNG (matching the existing docx-extraction output format), and returns a dict describing what was saved vs. skipped and why. `app.py`'s Tab 1 gets a radio toggle between the existing docx flow and a new upload flow that calls this function and reports results. Both flows write into the same `st.session_state.temp_images` / `image_files`, so Tabs 3–4 (pairing, export) need no changes.

**Tech Stack:** Python 3, Streamlit, Pillow (PIL) — no new runtime dependencies. `pytest` added as a dev-only dependency for the new pure function's unit tests.

## Global Constraints

- Accepted upload formats: jpg, jpeg, png, bmp, gif, tiff, webp, ppm (Pillow's native set) — no HEIC/HEIF support.
- Filename → card number: the **first number found anywhere in the filename** via `re.search(r'\d+', filename)`, matching the convention already used in `file_pairer.py` and Tab 1's existing sort key.
- All accepted images are converted to PNG and saved as `{number}.png`, matching the existing docx-extraction output so downstream code (`file_pairer.py`, `deck_creator.py`, Tab 1's display block) needs no changes.
- Duplicate numbers within one upload batch: keep the alphabetically-first filename, skip the rest (not an error).
- Unparseable filenames (no number) and unreadable/corrupt image files are skipped with a warning, not a hard error — one bad file must not block the rest of the batch.
- No changes to `image_extractor.py`'s existing `extract_numbered_images()`, `file_pairer.py`, or `deck_creator.py` beyond what's specified here.

---

### Task 1: `save_numbered_photos()` pure function + unit tests

**Files:**
- Modify: `image_extractor.py` (add new function; existing `extract_numbered_images` untouched)
- Create: `tests/test_image_extractor.py`
- Create: `requirements-dev.txt`

**Interfaces:**
- Produces: `save_numbered_photos(uploads: list[tuple[str, bytes]], output_folder: str) -> dict` where the returned dict has keys `'saved'` (sorted `list[int]` of card numbers written), `'skipped_no_number'` (`list[str]` filenames), `'skipped_duplicate'` (`list[str]` filenames), `'skipped_unreadable'` (`list[str]` filenames). Writes `{number}.png` files into `output_folder` (created if missing) for every entry in `'saved'`.

This task only needs `Pillow` and `pytest` — do **not** install the full `requirements.txt` (it pulls in `faster-whisper`/`ctranslate2`, which are slow to install and unrelated to this task).

- [ ] **Step 1: Set up an isolated venv with just the two packages this task needs**

Run:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install "Pillow>=10.0.0" "pytest>=7.4.0"
```
Expected: both packages install without error.

- [ ] **Step 2: Create `requirements-dev.txt`**

```
pytest>=7.4.0
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_image_extractor.py`:

```python
import os
from io import BytesIO

from PIL import Image

from image_extractor import save_numbered_photos


def _image_bytes(color=(255, 0, 0), fmt="PNG"):
    img = Image.new("RGB", (10, 10), color=color)
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def test_saves_valid_uploads_as_numbered_png(tmp_path):
    uploads = [
        ("1.jpg", _image_bytes(fmt="JPEG")),
        ("2.png", _image_bytes(fmt="PNG")),
    ]

    result = save_numbered_photos(uploads, str(tmp_path))

    assert result["saved"] == [1, 2]
    assert result["skipped_no_number"] == []
    assert result["skipped_duplicate"] == []
    assert result["skipped_unreadable"] == []
    assert sorted(os.listdir(tmp_path)) == ["1.png", "2.png"]
    with Image.open(tmp_path / "1.png") as img:
        assert img.format == "PNG"


def test_extracts_number_from_anywhere_in_filename(tmp_path):
    uploads = [("vocab-3-final.jpg", _image_bytes(fmt="JPEG"))]

    result = save_numbered_photos(uploads, str(tmp_path))

    assert result["saved"] == [3]
    assert os.path.exists(tmp_path / "3.png")


def test_skips_file_with_no_number_in_name(tmp_path):
    uploads = [("photo.jpg", _image_bytes(fmt="JPEG"))]

    result = save_numbered_photos(uploads, str(tmp_path))

    assert result["saved"] == []
    assert result["skipped_no_number"] == ["photo.jpg"]
    assert os.listdir(tmp_path) == []


def test_skips_duplicate_number_keeping_alphabetically_first(tmp_path):
    # "1.jpg" sorts before "1_dup.jpg", so "1.jpg" should win.
    uploads = [
        ("1_dup.jpg", _image_bytes(color=(0, 255, 0), fmt="JPEG")),
        ("1.jpg", _image_bytes(color=(255, 0, 0), fmt="JPEG")),
    ]

    result = save_numbered_photos(uploads, str(tmp_path))

    assert result["saved"] == [1]
    assert result["skipped_duplicate"] == ["1_dup.jpg"]
    assert sorted(os.listdir(tmp_path)) == ["1.png"]


def test_skips_unreadable_image_bytes(tmp_path):
    uploads = [("1.jpg", b"not a real image")]

    result = save_numbered_photos(uploads, str(tmp_path))

    assert result["saved"] == []
    assert result["skipped_unreadable"] == ["1.jpg"]
    assert os.listdir(tmp_path) == []


def test_creates_output_folder_if_missing(tmp_path):
    output_folder = str(tmp_path / "nested" / "does_not_exist_yet")
    uploads = [("1.jpg", _image_bytes(fmt="JPEG"))]

    result = save_numbered_photos(uploads, output_folder)

    assert result["saved"] == [1]
    assert os.path.exists(os.path.join(output_folder, "1.png"))
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pytest tests/test_image_extractor.py -v`
Expected: `ImportError: cannot import name 'save_numbered_photos' from 'image_extractor'` (or `ModuleNotFoundError` for the same reason) for every test.

- [ ] **Step 5: Implement `save_numbered_photos()`**

Add to `image_extractor.py`, after the existing `extract_numbered_images` function (before the `if __name__ == "__main__":` block at line 145):

```python
def save_numbered_photos(uploads, output_folder):
    """
    Saves directly-uploaded photo files as numbered PNGs, mirroring the
    output format of extract_numbered_images() so downstream pairing/export
    code needs no source-specific handling.

    Args:
        uploads: list of (filename, bytes) tuples
        output_folder: directory to write numbered PNGs into (created if missing)

    Returns:
        dict with keys:
            'saved': sorted list of int card numbers successfully written
            'skipped_no_number': list of filenames with no digit found
            'skipped_duplicate': list of filenames whose number was already
                claimed by an earlier (alphabetically-first) file
            'skipped_unreadable': list of filenames Pillow could not open
    """
    os.makedirs(output_folder, exist_ok=True)

    result = {
        'saved': [],
        'skipped_no_number': [],
        'skipped_duplicate': [],
        'skipped_unreadable': [],
    }

    used_numbers = set()

    for filename, data in sorted(uploads, key=lambda u: u[0]):
        match = re.search(r'\d+', filename)
        if not match:
            result['skipped_no_number'].append(filename)
            continue

        num = int(match.group())
        if num in used_numbers:
            result['skipped_duplicate'].append(filename)
            continue

        try:
            with Image.open(BytesIO(data)) as img:
                img.convert("RGBA").save(
                    os.path.join(output_folder, f"{num}.png"),
                    format="PNG"
                )
        except Exception:
            result['skipped_unreadable'].append(filename)
            continue

        used_numbers.add(num)
        result['saved'].append(num)

    result['saved'].sort()
    return result
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_image_extractor.py -v`
Expected: all 6 tests `PASS`.

- [ ] **Step 7: Commit**

```bash
git add image_extractor.py tests/test_image_extractor.py requirements-dev.txt
git commit -m "$(cat <<'EOF'
Add save_numbered_photos() for direct photo uploads

Pure, unit-tested function that converts directly-uploaded numbered
photo files into the same numbered-PNG output format
extract_numbered_images() already produces, so the pairing/export
pipeline needs no source-specific handling.
EOF
)"
```

---

### Task 2: Wire direct photo upload into Tab 1

**Files:**
- Modify: `app.py:15` (import), `app.py:165-217` (Tab 1 body)

**Interfaces:**
- Consumes: `save_numbered_photos(uploads: list[tuple[str, bytes]], output_folder: str) -> dict` from Task 1 (`image_extractor.py`).

- [ ] **Step 1: Add the new import**

In `app.py`, change line 15:

```python
from image_extractor import extract_numbered_images
```

to:

```python
from image_extractor import extract_numbered_images, save_numbered_photos
```

- [ ] **Step 2: Replace the Tab 1 body (lines 165–217) with the radio-toggle version**

Replace the entire `with tab1:` block with:

```python
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
                        result = save_numbered_photos(uploads, st.session_state.temp_images)

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
```

- [ ] **Step 3: Byte-compile check**

Run: `python3 -m py_compile app.py`
Expected: no output, exit code 0 (catches syntax errors before launching Streamlit).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "$(cat <<'EOF'
Add direct photo upload option to Tab 1

Adds a radio toggle so users can upload individually-numbered photo
files (e.g. 1.jpg, 2.jpg) instead of extracting images from a Word
document. Both paths write into the same session-state image list, so
pairing and export (Tabs 3-4) work unchanged regardless of source.
EOF
)"
```

---

### Task 3: End-to-end manual verification + README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Install what's needed to actually run the app**

```bash
source .venv/bin/activate
pip install streamlit pydub genanki
```

(Skips `faster-whisper`/`groq`/`openai`/`python-docx` — none are imported at module load time or needed to exercise Tab 1.)

- [ ] **Step 2: Generate sample photo files to upload**

```bash
python3 - <<'EOF'
from PIL import Image
import os

os.makedirs("/tmp/sample_photos", exist_ok=True)
Image.new("RGB", (40, 40), (255, 0, 0)).save("/tmp/sample_photos/1.jpg")
Image.new("RGB", (40, 40), (0, 255, 0)).save("/tmp/sample_photos/vocab-2-final.png")
Image.new("RGB", (40, 40), (0, 0, 255)).save("/tmp/sample_photos/no_number_here.jpg")
with open("/tmp/sample_photos/3.jpg", "wb") as f:
    f.write(b"not a real image")
print("done")
EOF
```

Expected: prints `done`, and `/tmp/sample_photos/` contains `1.jpg`, `vocab-2-final.png`, `no_number_here.jpg`, `3.jpg` (the last one is deliberately corrupt).

- [ ] **Step 3: Launch the app**

```bash
streamlit run app.py --server.headless true --server.port 8501 &
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8501
```

Expected: `200`.

- [ ] **Step 4: Manually verify in a browser**

Open `http://localhost:8501` (or the appropriate forwarded URL) and on **Tab 1**:

1. Confirm the radio toggle shows "📄 Extract from Word Document" and "🖼️ Upload Photos Directly", defaulting to the first option, and the existing docx flow still works unchanged.
2. Switch to "🖼️ Upload Photos Directly". Upload all four files from `/tmp/sample_photos/`. Click "Use These Photos".
3. Confirm: `st.success` reports **2** photos loaded (`1.jpg` and `vocab-2-final.png`); a warning lists `no_number_here.jpg` under "no number found"; a warning lists `3.jpg` under "unreadable image file"; the thumbnail grid below shows exactly 2 images captioned `1.png` and `2.png`.
4. Go to **Tab 2**, extract or upload any audio clips numbered `1` and `2` (or reuse existing example audio if convenient).
5. Go to **Tab 3**, click "Pair Files", confirm cards 1 and 2 pair successfully.
6. Go to **Tab 4**, export the deck, confirm the `.apkg` downloads without error.

- [ ] **Step 5: Stop the server**

```bash
kill %1
```

- [ ] **Step 6: Update README.md**

In `README.md`, change:

```markdown
- **Extract Images**: Extract numbered images from Word documents (.docx)
```

to:

```markdown
- **Extract Images**: Extract numbered images from Word documents (.docx), or upload individually numbered photo files directly
```

And change:

```markdown
1. **Extract Images** (Tab 1): Upload a Word document with numbered paragraphs and images
```

to:

```markdown
1. **Extract Images** (Tab 1): Upload a Word document with numbered paragraphs and images, or switch to "Upload Photos Directly" to upload individually numbered photo files (e.g. `1.jpg`, `2.jpg`)
```

And in the "File Format Requirements" section, after the existing "Word Documents" subsection, add:

```markdown
### Direct Photo Upload
- Name each file with its card number, e.g. `1.jpg`, `2.jpg` (the first number found anywhere in the filename is used, so `img_3.jpg` also works)
- Supported formats: JPG, JPEG, PNG, BMP, GIF, TIFF, WEBP, PPM
```

- [ ] **Step 7: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
Document direct photo upload in README

Covers the new Tab 1 upload option and its filename/format
requirements alongside the existing Word document format docs.
EOF
)"
```
