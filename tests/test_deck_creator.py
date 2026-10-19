import sqlite3
import zipfile

from deck_creator import create_anki_deck


def _guids(apkg_path, tmp_path):
    with zipfile.ZipFile(apkg_path) as z:
        z.extract("collection.anki2", tmp_path)
    con = sqlite3.connect(tmp_path / "collection.anki2")
    try:
        return {row[0] for row in con.execute("select guid from notes")}
    finally:
        con.close()


def _pairs(tmp_path):
    audio, image = tmp_path / "7.mp3", tmp_path / "7.png"
    audio.write_bytes(b"a")
    image.write_bytes(b"i")
    return [(7, str(audio), str(image))]


def test_same_number_in_different_decks_gets_different_guids(tmp_path):
    pairs = _pairs(tmp_path)
    one = create_anki_deck(pairs, str(tmp_path), deck_name="Unit 1 Session 1")
    two = create_anki_deck(pairs, str(tmp_path), deck_name="Unit 1 Session 2")

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    assert _guids(one, tmp_path / "a").isdisjoint(_guids(two, tmp_path / "b"))


def test_number_field_has_no_prefix(tmp_path):
    path = create_anki_deck(_pairs(tmp_path), str(tmp_path), deck_name="Deck")
    with zipfile.ZipFile(path) as z:
        z.extract("collection.anki2", tmp_path)
    con = sqlite3.connect(tmp_path / "collection.anki2")
    try:
        flds = con.execute("select flds from notes").fetchone()[0]
    finally:
        con.close()
    assert flds.split("\x1f")[0] == "7"
