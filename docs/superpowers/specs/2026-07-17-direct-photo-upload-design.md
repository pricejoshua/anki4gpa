# Direct Photo Upload Design

## Purpose

Today, Tab 1 ("Extract Images") only accepts a Word `.docx` document and parses
numbered images out of it via `image_extractor.py`. Some users already have their
vocabulary photos as loose numbered image files (e.g. `1.jpg`, `2.jpg`) and have no
reason to wrap them in a Word document first. This adds a second way to populate
Tab 1's image set: uploading individual photo files directly, named by card number.

## Placement

Add a radio toggle at the top of Tab 1, above the existing docx uploader:

```
image_source = st.radio(
    "Image source",
    ["📄 Extract from Word Document", "🖼️ Upload Photos Directly"],
    horizontal=True,
)
```

- **"📄 Extract from Word Document"** — the existing flow, byte-for-byte unchanged
  (docx uploader, "Extract Images" button, `extract_numbered_images(...)` call).
- **"🖼️ Upload Photos Directly"** — new flow described below.

Both branches write into the same `st.session_state.temp_images` directory and
`st.session_state.image_files` list. The thumbnail grid currently rendered below the
button (`st.image` in a 4-column layout) is shared by both branches unchanged, since
it only reads from that same session state. Tabs 3 (Pair Files) and 4 (Export Deck)
require **no changes** — they already consume `temp_images`/`image_files` generically.

## Upload Flow

```
photo_files = st.file_uploader(
    "Upload Photos",
    type=['jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'webp', 'ppm'],
    accept_multiple_files=True,
)
```

A caption explains the naming rule: *"Name each file with its card number, e.g.
`1.jpg`, `2.jpg` — the first number found anywhere in the filename is used (so
`img_3.jpg` or `vocab-3-final.png` both become card 3)."*

A "Use These Photos" button triggers processing:

1. If `st.session_state.temp_images` is set, `shutil.rmtree` it first (same
   clear-before-write lifecycle the docx branch already uses), then
   `tempfile.mkdtemp(prefix="anki_images_")` a fresh one.
2. Sort uploaded files by filename (`sorted(photo_files, key=lambda f: f.name)`) for
   deterministic conflict resolution.
3. For each file, in sorted order:
   - Extract the number via `re.search(r'\d+', file.name)`. No match → bucket as
     **"no number found"**, skip.
   - If that number was already claimed by an earlier (alphabetically-first) file in
     this batch → bucket as **"duplicate number"**, skip.
   - Otherwise, open the bytes with `PIL.Image.open(BytesIO(file.getvalue()))`. If
     Pillow raises → bucket as **"unreadable image"**, skip.
   - Otherwise, `img.convert("RGBA").save(os.path.join(temp_images, f"{num}.png"),
     format="PNG")` — same conversion the docx path already performs, so downstream
     code (`file_pairer.py`, `deck_creator.py`) keeps seeing plain numbered `.png`
     files regardless of source.
4. Rebuild `st.session_state.image_files` from the temp dir with the exact same
   sort-by-embedded-number lambda Tab 1 already uses after docx extraction:
   ```
   sorted(
       [f for f in os.listdir(temp_images) if f.endswith('.png')],
       key=lambda x: int(m.group()) if (m := re.search(r'\d+', x)) else 999
   )
   ```
5. Report results: `st.success` with the count loaded, followed by up to three
   `st.warning` calls (one per non-empty bucket) listing the skipped filenames, e.g.
   `st.warning(f"Skipped (no number found in filename): {', '.join(names)}")`.
   Processing is **not** fail-fast — one bad file doesn't block the rest of the batch.

## Formats

Accept Pillow's natively-supported formats requiring no new dependency: **jpg, jpeg,
png, bmp, gif, tiff, webp, ppm**. All are converted to PNG on save, matching the
existing pipeline's assumption (`file_pairer.py` and the Tab 1 display code both
filter on `.png`).

**HEIC/HEIF is explicitly out of scope** (see below) — Pillow cannot open it without
the additional `pillow-heif` dependency.

## Error Handling

All three skip categories (no number, duplicate number, unreadable) are warnings, not
hard errors — the batch still processes as many valid files as possible. If the
`photo_files` uploader is empty when "Use These Photos" is clicked, show
`st.error("Please upload photo files first")`, mirroring the existing docx branch's
`st.error("Please upload a Word document first")` for empty submissions.

## Out of Scope

- No HEIC/HEIF support (would require adding `pillow-heif` to `requirements.txt`).
- No per-photo crop/rotate/edit UI.
- No drag-to-reorder of uploaded photos.
- No change to `image_extractor.py`, `file_pairer.py`, or `deck_creator.py` — this
  only changes *how* numbered `.png` files land in `temp_images`, not anything that
  consumes them afterward.
