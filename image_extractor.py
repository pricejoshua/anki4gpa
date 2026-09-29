"""
Image extraction from Word documents (.docx files)
Based on Pictures.py - extracts numbered images from Word documents
Handles both explicit numbering (1., 2., 3.) and Word's automatic numbering
"""

import zipfile
import os
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from PIL import Image
from io import BytesIO


W_NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
_W_NS_MAP = {'w': W_NS}
_PLAIN_NUMBER_RE = re.compile(r'^(\d+)[.)]?$')


def _plain_number(p):
    """Return the label string if paragraph p is just a number ('7', '7.', '7)'), else None."""
    texts = [t.text for t in p.findall('.//w:t', _W_NS_MAP) if t.text and t.text.strip()]
    m = _PLAIN_NUMBER_RE.match(" ".join(texts).strip())
    return m.group(1) if m else None


def _span(tc):
    """Number of grid columns a cell covers."""
    span = tc.find('w:tcPr/w:gridSpan', _W_NS_MAP)
    try:
        return max(int(span.get(f'{{{W_NS}}}val')), 1) if span is not None else 1
    except (TypeError, ValueError):
        return 1


def _cell_columns(row):
    """Map each direct w:tc of a row to its starting grid column (honouring gridSpan)."""
    cols = {}
    col = 0
    for tc in row.findall('w:tc', _W_NS_MAP):
        cols[tc] = col
        col += _span(tc)
    return cols


def _cell_label(tc):
    """First plain-number paragraph in a cell, or None."""
    for p in tc.iter(f'{{{W_NS}}}p'):
        label = _plain_number(p)
        if label is not None:
            return label
    return None


def _table_label(p, parents):
    """
    Label for an image paragraph inside a table cell: a number earlier in the
    same cell, else the nearest number above it in the same grid column.
    Returns None if p isn't in a table or no label is found.
    """
    tc = parents.get(p)
    while tc is not None and tc.tag != f'{{{W_NS}}}tc':
        tc = parents.get(tc)
    if tc is None:
        return None

    # Rule 1: nearest preceding plain-number paragraph in the same cell
    label = None
    for q in tc.iter(f'{{{W_NS}}}p'):
        if q is p:
            break
        found = _plain_number(q)
        if found is not None:
            label = found
    if label is not None:
        return label

    # Rule 2: walk up the rows of the innermost table at the same grid column
    row = parents.get(tc)
    table = parents.get(row)
    if row is None or table is None:
        return None
    col = _cell_columns(row)[tc]
    rows = table.findall('w:tr', _W_NS_MAP)
    for above in reversed(rows[:rows.index(row)]):
        for cell, start in _cell_columns(above).items():
            if start <= col < start + _span(cell):
                label = _cell_label(cell)
                if label is not None:
                    return label
                break
    return None


def extract_numbered_images(docx_path, output_folder, convert_to_png=True):
    """
    Extracts all images from a Word .docx and names them according to
    the nearest number: a label in the same table cell or the same column of a
    table row above, else the nearest numbered paragraph (Word numbering or
    explicit numbers like '1.' / '1').
    Converts all images to PNG if convert_to_png=True; images Pillow can't
    convert are skipped (not written) and reported.

    Returns {'count': images written, 'skipped_unconvertible': [media filenames]}.
    """
    os.makedirs(output_folder, exist_ok=True)

    ns = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
        'v': 'urn:schemas-microsoft-com:vml',
        'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture'
    }

    with zipfile.ZipFile(docx_path, 'r') as docx:
        doc_xml = docx.read('word/document.xml')
        root = ET.fromstring(doc_xml)

        # --- Find all paragraphs in document order ---
        paras = list(root.iterfind('.//w:p', ns))
        parents = {child: parent for parent in root.iter() for child in parent}
        para_labels = [None] * len(paras)
        counters = defaultdict(int)

        # Pass 1: identify paragraph numbers (either explicit or auto-numbered)
        for i, p in enumerate(paras):
            # Check for literal "N." / "N" numbers
            label = _plain_number(p)
            if label is not None:
                para_labels[i] = label
                continue

            # Check for Word's automatic numbering (numPr)
            numId_elem = p.find('.//w:numPr/w:numId', ns)
            ilvl_elem = p.find('.//w:numPr/w:ilvl', ns)
            if numId_elem is not None:
                numId = (
                    numId_elem.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val')
                    or numId_elem.attrib.get('w:val')
                    or numId_elem.attrib.get('val')
                )
                ilvl = (
                    ilvl_elem.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val')
                    if ilvl_elem is not None else '0'
                )
                key = (numId, ilvl)
                counters[key] += 1
                para_labels[i] = str(counters[key])

        # Pass 2: find image relationship IDs in each paragraph
        image_occurrences = []
        for i, p in enumerate(paras):
            for blip in p.findall('.//a:blip', ns):
                rid = (
                    blip.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed')
                    or blip.attrib.get('r:embed')
                )
                if rid:
                    image_occurrences.append((i, rid))
            for im in p.findall('.//v:imagedata', ns):
                rid = (
                    im.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                    or im.attrib.get('r:id')
                )
                if rid:
                    image_occurrences.append((i, rid))

        # Map each image to the nearest numbered paragraph
        image_map = []
        for para_idx, rid in image_occurrences:
            assigned = _table_label(paras[para_idx], parents)
            # Search backwards first
            for j in range(para_idx, -1, -1):
                if assigned is not None:
                    break
                if para_labels[j] is not None:
                    assigned = para_labels[j]
                    break
            # If not found, search forwards
            if assigned is None:
                for j in range(para_idx + 1, len(paras)):
                    if para_labels[j] is not None:
                        assigned = para_labels[j]
                        break
            image_map.append((assigned, rid, para_idx))

        # Read relationship file
        rels_xml = docx.read('word/_rels/document.xml.rels').decode('utf-8')
        rels = dict(re.findall(r'Id="(rId\d+)"[^>]+Target="([^"]+)"', rels_xml))

        # --- Extract and save images ---
        counter = defaultdict(int)
        skipped = []
        for number, rid, _ in image_map:
            if rid not in rels:
                continue
            target = rels[rid].split('/')[-1]
            data = docx.read(f'word/media/{target}')
            ext = os.path.splitext(target)[1].lower()
            display_num = number if number is not None else "unknown"
            n = counter[display_num] + 1
            suffix = f"_{n}" if n > 1 else ""
            path = os.path.join(output_folder, f"{display_num}{suffix}{'.png' if convert_to_png else ext}")

            if convert_to_png:
                try:
                    with Image.open(BytesIO(data)) as img:
                        img.convert("RGBA").save(path, format="PNG")
                except Exception:
                    # e.g. WMF/EMF ink drawings: don't write a fake .png
                    skipped.append(target)
                    continue
            else:
                with open(path, "wb") as f:
                    f.write(data)
            counter[display_num] = n

    return {'count': sum(counter.values()), 'skipped_unconvertible': skipped}


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


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python image_extractor.py <input.docx> <output_folder>")
        sys.exit(1)

    docx_path = sys.argv[1]
    output_folder = sys.argv[2]

    print(f"Extracting images from: {docx_path}")
    print(f"Output folder: {output_folder}")

    result = extract_numbered_images(docx_path, output_folder)

    print(f"\nExtracted {result['count']} images!")
    if result['skipped_unconvertible']:
        print(f"Skipped (unconvertible): {', '.join(result['skipped_unconvertible'])}")
    print(f"Files saved to: {output_folder}")
