# Table-Aware Image Numbering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `extract_numbered_images()` number pictures correctly in lesson-plan documents whose "picture dictionary" is a Word table with plain-number labels, and stop it from writing images Pillow can't convert as fake `.png` files (which crashed `st.image` with `OSError: cannot find loader for this WMF file`).

**Spec (inline — no separate spec file):** Observed on a real user document (`570_Unit 1 session 1 lesson plan Fall 2026.docx`, not committed):

- The picture dictionary is one or more tables. Two layouts occur, sometimes in the same table:
  - **Grid:** a row of label cells `[1] [2] [3]`, then a row of picture cells `[img] [img] [img]` below it — picture's number is the label in the same column of the nearest row above.
  - **Same cell:** one cell holds a paragraph `7` and then the picture — picture's number is that label.
- Labels are plain text paragraphs `1`, `2`, … — **not** Word list numbering and **not** `N.`. The current code only recognises `N.` and `w:numPr`, so every picture was attached to the last list item before the table (all 21 images became `2.png`, `2_2.png`, …).
- The document also contained two accidental Word ink dots (VML shapes whose image is a 504-byte EMF). Pillow opens EMF/WMF headers on Linux but can't rasterise them, so `.convert()` raises; the current `except` then writes the raw EMF bytes as `N.png`.

**Architecture:** All changes are in `image_extractor.py::extract_numbered_images` plus a small reporting change in `app.py` Tab 1. Numbering priority for each image:
1. Image inside a table cell and a *plain-number paragraph* exists earlier in the same cell → that number (nearest preceding one).
2. Image inside a table cell → walk up the rows of the same table; the first cell at the same grid column that contains a plain-number paragraph → that number.
3. Otherwise → existing behaviour (nearest labelled paragraph backwards, then forwards, using `N.`/`N`/`N)` literals and `w:numPr` counters).

**Tech Stack:** Python 3, `xml.etree.ElementTree`, Pillow, pytest. No new dependencies.

## Global Constraints

- "Plain-number paragraph" = paragraph whose joined `w:t` text, stripped, fully matches `^(\d+)[.)]?$` (so `7`, `7.`, `7)`; not `3 mins`, not `1) asking what…`).
- The existing literal-label regex in Pass 1 (`^\s*(\d+)\.\s*$`) is broadened to that same pattern so bare `N` paragraphs outside tables also count.
- Grid columns account for `w:gridSpan` (a cell's column = sum of preceding cells' spans in that row). Rows are the table's **direct** `w:tr` children and cells the row's **direct** `w:tc` children; for an image inside a nested table, the **innermost** table is used.
- Rule 2 only accepts a label cell whose plain-number paragraph is found; it keeps walking up past rows whose same-column cell has none. If the top of the table is reached with no label, fall through to rule 3.
- If `convert_to_png=True` and Pillow fails to open **or** convert an image, **do not write any file** for it and **do not consume a number/suffix** (the `_2`, `_3` counter only advances on a successful write). Record the media filename (e.g. `image1.emf`) — once per occurrence — in a skipped list.
- Return value changes from `int` to `dict`: `{'count': <int images written>, 'skipped_unconvertible': <list[str] media filenames>}`. Update the `__main__` block accordingly.
- `convert_to_png=False` behaviour (raw bytes, original extension) is unchanged.
- `save_numbered_photos()`, `file_pairer.py`, `deck_creator.py`: untouched.

---

### Task 1: Table-aware numbering, skip unconvertible images, report skips in the app

**Files:**
- Modify: `image_extractor.py`
- Modify: `app.py` (Tab 1 docx branch only, around the `extract_numbered_images(...)` call and the `st.success(f"Extracted ...")` line)
- Create: `tests/test_extract_numbered_images.py`

- [ ] **Step 1: Write failing tests** in `tests/test_extract_numbered_images.py`. Build synthetic `.docx` files with `zipfile` (no python-docx). Suggested helper:

```python
import os
import zipfile
from io import BytesIO

from PIL import Image

from image_extractor import extract_numbered_images

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ' \
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ' \
    'xmlns:v="urn:schemas-microsoft-com:vml"'


def _png(color):
    buf = BytesIO()
    Image.new("RGB", (10, 10), color).save(buf, format="PNG")
    return buf.getvalue()


def _text(t):
    return f'<w:p><w:r><w:t>{t}</w:t></w:r></w:p>'


def _img(rid):
    return f'<w:p><w:r><w:drawing><a:blip r:embed="{rid}"/></w:drawing></w:r></w:p>'


def _cell(*paras, span=None):
    tcpr = f'<w:tcPr><w:gridSpan w:val="{span}"/></w:tcPr>' if span else ''
    return f'<w:tc>{tcpr}{"".join(paras) or "<w:p/>"}</w:tc>'


def _row(*cells):
    return f'<w:tr>{"".join(cells)}</w:tr>'


def _table(*rows):
    return f'<w:tbl>{"".join(rows)}</w:tbl>'


def _make_docx(path, body, media):
    """media: dict rId -> (filename, bytes)"""
    rels = "".join(
        f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>'
        for rid, (name, _) in media.items()
    )
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document {W}><w:body>{body}</w:body></w:document>')
        z.writestr("word/_rels/document.xml.rels",
                   f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for name, data in media.values():
            z.writestr(f"word/media/{name}", data)
    return str(path)


def _color_of(path):
    with Image.open(path) as img:
        return img.convert("RGB").getpixel((0, 0))
```

Note the rels regex in `extract_numbered_images` expects `Id="rIdN"` to come before `Target=` — keep that attribute order in the helper.

Required test cases (assert on filenames **and** pixel colours so mis-assignment is caught):

1. `test_grid_table_labels_row_above` — list item `2.` before the table (reproduces the bug), then table rows `[1][2][3]` / `[img r][img g][img b]` → files `1.png`, `2.png`, `3.png` with red/green/blue respectively; no `2_2.png`.
2. `test_label_and_image_in_same_cell` — table row `[ "7" + img ]` `[ "8" + img ]` → `7.png`, `8.png` with matching colours.
3. `test_grid_walks_past_rows_without_labels` — rows `[4][5]`, `[text "x"][text "y"]`, `[img][img]` → `4.png`, `5.png` (the middle row's cells hold non-number text, so the walk continues up).
4. `test_grid_span_column_alignment` — rows `[1 span=2][3]` / `[img][img][img]`: column 0 and 1 are both covered by label `1` (so images become `1.png`, `1_2.png`), column 2 → `3.png`.
5. `test_bare_number_paragraph_outside_table` — paragraph `5` then an image paragraph (no table) → `5.png`.
6. `test_existing_dot_label_still_works` — paragraph `3.` then image → `3.png` (regression).
7. `test_unconvertible_image_skipped_and_reported` — paragraph `1.`, image rId1 = `("image1.emf", b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF" + b"\x00" * 60)` (Pillow will open-or-fail; either way it must not be written), then image rId2 = valid red PNG → result `{'count': 1, 'skipped_unconvertible': ['image1.emf']}`, directory contains exactly `['1.png']`, and `1.png` is red (the skipped image did not consume the `1` slot).
8. `test_returns_count_dict` — any simple doc → `result['count']` equals number of files written.

- [ ] **Step 2: Run tests, confirm they fail for the expected reasons**

```bash
.venv/bin/python -m pytest tests/test_extract_numbered_images.py -q
```

- [ ] **Step 3: Implement in `image_extractor.py`** per the Architecture and Global Constraints. Guidance:
  - Build a parent map (`{child: parent for parent in root.iter() for child in parent}`) to find, for each image paragraph, its nearest ancestor `w:tc`, that cell's `w:tr`, and that row's `w:tbl`.
  - Helper `_plain_number(p)` returning the label string or `None`, reused by Pass 1.
  - Keep the per-image loop structure; compute `assigned` via rule 1 → rule 2 → existing search.
  - Replace the raw-bytes fallback with skip-and-record; advance `counter[display_num]` only after a successful save (compute the suffix from `counter[display_num] + 1`, increment after writing).
  - Update the docstring and the `__main__` block (`print` count and any skipped names).

- [ ] **Step 4: Update `app.py` Tab 1 docx branch**: capture `result = extract_numbered_images(...)`; after the existing `st.success(...)`, if `result['skipped_unconvertible']` is non-empty show
  `st.warning("Skipped (image format can't be converted — e.g. Word ink or WMF/EMF drawings): " + ", ".join(result['skipped_unconvertible']))`, matching the style of the photo branch's warnings.

- [ ] **Step 5: Run the full suite** — `.venv/bin/python -m pytest -q` — all pass, no new warnings.

- [ ] **Step 6: Commit** — `git add image_extractor.py app.py tests/test_extract_numbered_images.py && git commit -m "Number table picture-dictionary images by their cell labels; skip unconvertible images"`
