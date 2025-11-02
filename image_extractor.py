"""
Image extraction from Word documents (.docx files)
Based on Pictures.py - extracts numbered images from Word documents
"""

import os
import re
import zipfile
from xml.etree import ElementTree as ET
from io import BytesIO
from PIL import Image
from docx import Document


def extract_numbered_images(docx_path, output_folder):
    """Extract images from .docx file associated with numbered paragraphs"""

    ns = {
        'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
        'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
        'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
        'v': 'urn:schemas-microsoft-com:vml',
        'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture'
    }

    os.makedirs(output_folder, exist_ok=True)
    doc = Document(docx_path)

    # Extract media files
    media_dict = {}
    with zipfile.ZipFile(docx_path, 'r') as z:
        for item in z.namelist():
            if item.startswith('word/media/'):
                fname = os.path.basename(item)
                media_dict[fname] = z.read(item)

    # Process paragraphs
    saved = {}
    for para in doc.paragraphs:
        text = para.text.strip()

        # Try to extract a number
        m = re.match(r'^\s*(\d+)[\.\):]?\s*', text)
        if not m:
            continue

        number = int(m.group(1))

        # Look for image relationships in this paragraph
        para_elem = para._element

        # Modern image format (blip)
        for blip in para_elem.findall('.//a:blip', ns):
            embed = blip.get('{%s}embed' % ns['r'])
            if not embed:
                continue

            rel = doc.part.rels.get(embed)
            if not rel:
                continue

            img_name = os.path.basename(rel.target_ref)
            if img_name not in media_dict:
                continue

            if number not in saved:
                data = media_dict[img_name]
                filename = f"{number}.png"
                save_image(data, os.path.join(output_folder, filename))
                saved[number] = True

        # Legacy VML format (imagedata)
        for img in para_elem.findall('.//v:imagedata', ns):
            rid = img.get('{%s}id' % ns['r'])
            if not rid:
                continue

            rel = doc.part.rels.get(rid)
            if not rel:
                continue

            img_name = os.path.basename(rel.target_ref)
            if img_name not in media_dict:
                continue

            if number not in saved:
                data = media_dict[img_name]
                filename = f"{number}.png"
                save_image(data, os.path.join(output_folder, filename))
                saved[number] = True

    return len(saved)


def save_image(data, filepath):
    """Save image data to file, converting to PNG if needed"""
    try:
        with Image.open(BytesIO(data)) as img:
            img.convert("RGBA").save(filepath, format="PNG")
    except:
        # If PIL fails, just save raw data
        with open(filepath, "wb") as f:
            f.write(data)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python image_extractor.py <input.docx> <output_folder>")
        sys.exit(1)

    docx_path = sys.argv[1]
    output_folder = sys.argv[2]

    print(f"Extracting images from: {docx_path}")
    print(f"Output folder: {output_folder}")

    count = extract_numbered_images(docx_path, output_folder)

    print(f"\nExtracted {count} images!")
    print(f"Files saved to: {output_folder}")
