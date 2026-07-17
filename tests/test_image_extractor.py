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
