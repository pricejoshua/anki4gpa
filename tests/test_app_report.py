import io
import json
import zipfile

from streamlit.testing.v1 import AppTest


def test_report_section_prepares_downloadable_zip():
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    assert not at.exception
    at.text_area(key="report_note").input("card 9 missing").run()
    at.button(key="prepare_report_btn").click().run()
    assert not at.exception
    data = at.session_state["issue_report_zip"]
    z = zipfile.ZipFile(io.BytesIO(data))
    report = json.loads(z.read("report.json"))
    assert report["note"] == "card 9 missing"
    assert report["app"]["version"]
