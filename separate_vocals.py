"""
Vocal Separator using Demucs (free, local, GPU)
Separates vocals from instrumentals so Whisper syncs to the vocal track only.
Output: stems/{song}/vocals.wav + no_vocals.wav

Usage:
    python separate_vocals.py --song "Love is a battlefield ( the death of me)"
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import BASE_DIR, all_songs, VENV_PYTHON if hasattr(__import__('config'), 'VENV_PYTHON') else None

VENV_PYTHON = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
STEMS_DIR   = BASE_DIR / "stems"
STEMS_DIR.mkdir(exist_ok=True)

def separate(song_name, audio_path):
    out_dir = STEMS_DIR / song_name
    vocal_path = out_dir / "htdemucs" / audio_path.stem / "vocals.wav"

    if vocal_path.exists():
        print(f"Vocals already separated → {vocal_path}")
        return vocal_path

    print(f"Separating vocals from: {audio_path.name}")
    print("This takes 2-5 minutes on first run (downloads ~1GB model)...")

    cmd = [
        VENV_PYTHON, "-m", "demucs",
        "--two-stems=vocals",
        "-o", str(out_dir),
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print("ERROR: Demucs failed.")
        sys.exit(1)

    # Find output
    matches = list(out_dir.rglob("vocals.wav"))
    if matches:
        print(f"Vocals saved → {matches[0]}")
        return matches[0]
    print("ERROR: Could not find vocals.wav output.")
    sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--song", required=True)
    args = parser.parse_args()

    songs = {s["name"]: s for s in all_songs()}
    if args.song not in songs:
        print(f"ERROR: Song '{args.song}' not found.")
        sys.exit(1)

    s = songs[args.song]
    if not s["has_audio"]:
        print(f"ERROR: No audio found for '{args.song}'.")
        sys.exit(1)

    vocal_path = separate(args.song, s["audio_path"])
    print(f"\nNow run sync_lyrics.py with --use-vocals to get better timestamps.")
    print(f"Vocal file: {vocal_path}")
