import os
import zipfile
from io import BytesIO

from PIL import Image

from image_extractor import extract_numbered_images

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ' \
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" ' \
    'xmlns:v="urn:schemas-microsoft-com:vml"'

RED, GREEN, BLUE = (255, 0, 0), (0, 255, 0), (0, 0, 255)


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


def _rgb_media():
    return {
        "rId1": ("r.png", _png(RED)),
        "rId2": ("g.png", _png(GREEN)),
        "rId3": ("b.png", _png(BLUE)),
    }


def _run(tmp_path, body, media):
    docx = _make_docx(tmp_path / "d.docx", body, media)
    out = tmp_path / "out"
    result = extract_numbered_images(docx, str(out))
    return result, out


def test_grid_table_labels_row_above(tmp_path):
    body = (
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
        '<w:r><w:t>item</w:t></w:r></w:p>'
        '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
        '<w:r><w:t>item</w:t></w:r></w:p>'
        + _table(
            _row(_cell(_text("1")), _cell(_text("2")), _cell(_text("3"))),
            _row(_cell(_img("rId1")), _cell(_img("rId2")), _cell(_img("rId3"))),
        )
    )
    _, out = _run(tmp_path, body, _rgb_media())
    assert sorted(os.listdir(out)) == ["1.png", "2.png", "3.png"]
    assert _color_of(out / "1.png") == RED
    assert _color_of(out / "2.png") == GREEN
    assert _color_of(out / "3.png") == BLUE


def test_label_and_image_in_same_cell(tmp_path):
    body = _table(_row(
        _cell(_text("7"), _img("rId1")),
        _cell(_text("8"), _img("rId2")),
    ))
    _, out = _run(tmp_path, body, _rgb_media())
    assert sorted(os.listdir(out)) == ["7.png", "8.png"]
    assert _color_of(out / "7.png") == RED
    assert _color_of(out / "8.png") == GREEN


def test_grid_walks_past_rows_without_labels(tmp_path):
    body = _table(
        _row(_cell(_text("4")), _cell(_text("5"))),
        _row(_cell(_text("x")), _cell(_text("y"))),
        _row(_cell(_img("rId1")), _cell(_img("rId2"))),
    )
    _, out = _run(tmp_path, body, _rgb_media())
    assert sorted(os.listdir(out)) == ["4.png", "5.png"]
    assert _color_of(out / "4.png") == RED
    assert _color_of(out / "5.png") == GREEN


def test_grid_span_column_alignment(tmp_path):
    body = _table(
        _row(_cell(_text("1"), span=2), _cell(_text("3"))),
        _row(_cell(_img("rId1")), _cell(_img("rId2")), _cell(_img("rId3"))),
    )
    _, out = _run(tmp_path, body, _rgb_media())
    assert sorted(os.listdir(out)) == ["1.png", "1_2.png", "3.png"]
    assert _color_of(out / "1.png") == RED
    assert _color_of(out / "1_2.png") == GREEN
    assert _color_of(out / "3.png") == BLUE


def test_bare_number_paragraph_outside_table(tmp_path):
    _, out = _run(tmp_path, _text("5") + _img("rId1"), _rgb_media())
    assert os.listdir(out) == ["5.png"]
    assert _color_of(out / "5.png") == RED


def test_existing_dot_label_still_works(tmp_path):
    _, out = _run(tmp_path, _text("3.") + _img("rId1"), _rgb_media())
    assert os.listdir(out) == ["3.png"]
    assert _color_of(out / "3.png") == RED


def test_unconvertible_image_skipped_and_reported(tmp_path):
    emf = b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF" + b"\x00" * 60
    media = {"rId1": ("image1.emf", emf), "rId2": ("r.png", _png(RED))}
    body = _text("1.") + _img("rId1") + _img("rId2")
    result, out = _run(tmp_path, body, media)
    assert result == {"count": 1, "skipped_unconvertible": ["image1.emf"]}
    assert os.listdir(out) == ["1.png"]
    assert _color_of(out / "1.png") == RED


def test_returns_count_dict(tmp_path):
    body = _text("1.") + _img("rId1") + _text("2.") + _img("rId2")
    result, out = _run(tmp_path, body, _rgb_media())
    assert result["count"] == len(os.listdir(out)) == 2
    assert result["skipped_unconvertible"] == []
