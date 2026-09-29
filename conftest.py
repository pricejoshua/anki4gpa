import shutil

if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
    except ImportError:
        pass
