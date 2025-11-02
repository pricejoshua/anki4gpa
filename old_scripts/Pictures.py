import zipfile
import os
import re
import shutil
import xml.etree.ElementTree as ET
from collections import defaultdict
from PIL import Image
from io import BytesIO

def extract_numbered_images_by_paragraph(docx_path, output_folder, convert_to_png=True):
    """
    Extracts all images from a Word .docx and names them according to
    the nearest numbered paragraph (using Word numbering or explicit numbers like '1.').
    Converts all images to PNG if convert_to_png=True.
    """
    if os.path.exists(output_folder):
        shutil.rmtree(output_folder)
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
        para_labels = [None] * len(paras)
        counters = defaultdict(int)

        # Pass 1: identify paragraph numbers (either explicit or auto-numbered)
        for i, p in enumerate(paras):
            # Check for literal "N." numbers
            texts = [t.text for t in p.findall('.//w:t', ns) if t.text and t.text.strip()]
            joined = " ".join(texts).strip()
            m = re.match(r'^\s*(\d+)\.\s*$', joined)
            if m:
                para_labels[i] = m.group(1)
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
            assigned = None
            for j in range(para_idx, -1, -1):
                if para_labels[j] is not None:
                    assigned = para_labels[j]
                    break
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
        for number, rid, _ in image_map:
            if rid not in rels:
                continue
            target = rels[rid].split('/')[-1]
            data = docx.read(f'word/media/{target}')
            ext = os.path.splitext(target)[1].lower()
            display_num = number if number is not None else "unknown"
            counter[display_num] += 1
            suffix = f"_{counter[display_num]}" if counter[display_num] > 1 else ""

            # Determine final filename
            if convert_to_png:
                filename = f"{display_num}{suffix}.png"
            else:
                filename = f"{display_num}{suffix}{ext}"

            # Convert to PNG if requested
            if convert_to_png:
                try:
                    with Image.open(BytesIO(data)) as img:
                        img.convert("RGBA").save(os.path.join(output_folder, filename), format="PNG")
                except Exception as e:
                    # Fallback: write raw bytes if Pillow can't open
                    with open(os.path.join(output_folder, filename), "wb") as f:
                        f.write(data)
            else:
                with open(os.path.join(output_folder, filename), "wb") as f:
                    f.write(data)

    print(f"✅ Extracted and converted images to '{output_folder}'")
    for num, cnt in sorted(counter.items(), key=lambda x: (int(x[0]) if x[0].isdigit() else 9999)):
        print(f"  {num}: {cnt} image(s)")

# Example usage:
extract_numbered_images_by_paragraph("Unit 1 session  6 lesson plan 2025.docx", "output_images", convert_to_png=True)
