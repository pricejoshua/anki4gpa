import shutil

if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_log_dir(tmp_path_factory, monkeypatch):
    """Keep tests from writing usage logs into the real logs/ directory."""
    monkeypatch.setenv("LOG_DIR", str(tmp_path_factory.mktemp("usage-logs")))
