"""
Central configuration — all paths defined here.
"""
import os
from pathlib import Path

# Ensure ffmpeg is available for Whisper and MoviePy
FFMPEG_BIN = Path("C:/ProgramData/chocolatey/lib/ffmpeg/tools/ffmpeg/bin")
if FFMPEG_BIN.exists() and str(FFMPEG_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")

BASE_DIR    = Path(__file__).parent
LYRICS_DIR  = Path("E:/Music/song lyrics")   # all .txt lyric files
AUDIO_DIR   = Path("E:/Music/music")         # .mp3 files
WAVE_DIR    = Path("E:/Music/music/Wave")    # .wav files (higher quality)
OUTPUTS_DIR  = BASE_DIR / "outputs"
BG_DIR       = BASE_DIR / "backgrounds"
VIDEO_BG_DIR = BASE_DIR / "video_backgrounds"  # SVD animated clips
WAN_DIR      = BASE_DIR / "wan_videos"          # Wan2.1 text-to-video clips
CLIPS_DIR    = BASE_DIR / "clips"               # your own footage (drop MP4s here)
TS_DIR       = BASE_DIR / "timestamps"
HF_CACHE     = "E:/hf-cache"

for d in [OUTPUTS_DIR, BG_DIR, VIDEO_BG_DIR, WAN_DIR, CLIPS_DIR, TS_DIR]:
    d.mkdir(exist_ok=True)

# ── Section key helper ────────────────────────────────────────────────────────
def section_key(label: str) -> str:
    """Normalize section label to filename key. e.g. 'FINAL CHORUS' -> 'final_chorus'"""
    return label.lower().strip().replace(" ", "_").replace("-", "_")

# ── Background priority system (Option 4) ─────────────────────────────────────
def find_background(section_label: str):
    """
    Returns (path, type) for the best available background for a section.
    Priority: own clips > Wan2.1 > SVD animated > SD still image > None
    """
    key = section_key(section_label)
    candidates = [
        (CLIPS_DIR    / f"{key}.mp4",  "clip"),   # your own footage
        (WAN_DIR      / f"{key}.mp4",  "wan"),    # Wan2.1 text-to-video
        (VIDEO_BG_DIR / f"{key}.mp4",  "svd"),    # SVD animated
        (BG_DIR       / f"{key}.png",  "image"),  # SD still image
    ]
    for path, bg_type in candidates:
        if path.exists():
            return path, bg_type
    return None, None

WIDTH, HEIGHT = 1920, 1080
FPS = 24

def find_audio(song_stem: str) -> Path | None:
    """Find audio file matching a lyric filename.
    Prefers WAV (higher quality), falls back to MP3.
    Checks exact match first, then partial match."""
    stem = song_stem.lower().strip()

    search_dirs = [
        (WAVE_DIR, "wav"),
        (AUDIO_DIR, "wav"),
        (AUDIO_DIR, "mp3"),
    ]

    # Exact match
    for folder, ext in search_dirs:
        if not folder.exists():
            continue
        for f in folder.glob(f"*.{ext}"):
            if f.stem.lower().strip() == stem:
                return f

    # Partial match (first 15 chars)
    for folder, ext in search_dirs:
        if not folder.exists():
            continue
        for f in folder.glob(f"*.{ext}"):
            if stem[:15] in f.stem.lower() or f.stem.lower()[:15] in stem:
                return f

    return None

def all_songs():
    """Return list of dicts for every song that has a lyrics file."""
    songs = []
    for txt in sorted(LYRICS_DIR.glob("*.txt")):
        audio = find_audio(txt.stem)
        ts    = TS_DIR / f"{txt.stem}.json"
        songs.append({
            "name":           txt.stem,
            "lyrics_path":    txt,
            "audio_path":     audio,
            "has_audio":      audio is not None,
            "has_timestamps": ts.exists(),
            "output_path":    OUTPUTS_DIR / f"{txt.stem}.mp4",
            "has_output":     (OUTPUTS_DIR / f"{txt.stem}.mp4").exists(),
        })
    return songs
