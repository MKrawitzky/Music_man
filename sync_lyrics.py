"""
Automatic Lyric Timing using OpenAI Whisper (free, runs locally on GPU)
Transcribes the audio and matches each lyric line to a timestamp.
Outputs a timestamped lyrics file used by lyric_video.py for perfect sync.

Usage:
    python sync_lyrics.py
Output:
    songs/wave/timestamps.json
"""

import json
import os
import re
import torch
import whisper
from pathlib import Path
from difflib import SequenceMatcher

# Ensure ffmpeg is on PATH (installed via Chocolatey)
FFMPEG_BIN = Path("C:/ProgramData/chocolatey/lib/ffmpeg/tools/ffmpeg/bin")
if FFMPEG_BIN.exists() and str(FFMPEG_BIN) not in os.environ.get("PATH", ""):
    os.environ["PATH"] = str(FFMPEG_BIN) + os.pathsep + os.environ.get("PATH", "")

# ── Config ────────────────────────────────────────────────────────────────────
import argparse
import sys
sys.path.insert(0, str(Path(__file__).parent))
from config import LYRICS_DIR, TS_DIR, find_audio, all_songs

def resolve_song(song_name):
    songs = {s["name"]: s for s in all_songs()}
    if song_name not in songs:
        print(f"ERROR: Song '{song_name}' not found in {LYRICS_DIR}")
        sys.exit(1)
    s = songs[song_name]
    if not s["has_audio"]:
        print(f"ERROR: No audio file found for '{song_name}'")
        sys.exit(1)
    return s["lyrics_path"], s["audio_path"], TS_DIR / f"{song_name}.json"

# Whisper model size: tiny/base/small/medium/large
# "medium" gives great accuracy and runs well on RTX 5070
WHISPER_MODEL = "medium"

SECTION_PATTERN = re.compile(r"^\[(.+?)\]")
STAGE_DIRECTION = re.compile(r"^\(.*\)$")

# ── Parse lyrics ──────────────────────────────────────────────────────────────
def parse_lyrics(path):
    lines = []
    raw = path.read_text(encoding="utf-8").splitlines()
    in_header = True
    for line in raw:
        line = line.strip()
        if in_header:
            if re.match(r"^={3,}", line):
                in_header = False
            continue
        if not line:
            lines.append({"type": "blank", "text": ""})
        elif SECTION_PATTERN.match(line):
            label = SECTION_PATTERN.match(line).group(1).strip()
            lines.append({"type": "section", "text": label.upper()})
        elif STAGE_DIRECTION.match(line):
            pass
        else:
            lines.append({"type": "lyric", "text": line})
    return lines

# ── Whisper transcription ─────────────────────────────────────────────────────
def transcribe(audio_path):
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Loading Whisper '{WHISPER_MODEL}' on {device}...")
    model = whisper.load_model(WHISPER_MODEL, device=device, download_root="E:/hf-cache/whisper")

    print("Transcribing audio (this takes a minute)...")
    result = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language="en",
        verbose=False,
    )
    return result

# ── Match lyrics to transcription segments ────────────────────────────────────
def similarity(a, b):
    a = re.sub(r"[^\w\s]", "", a.lower())
    b = re.sub(r"[^\w\s]", "", b.lower())
    return SequenceMatcher(None, a, b).ratio()

def match_lyrics_to_segments(lyric_lines, whisper_result):
    """
    Match each lyric line to the closest Whisper segment by text similarity.
    Returns list of (start_time, end_time) per lyric line.
    """
    segments = whisper_result["segments"]
    lyric_only = [l for l in lyric_lines if l["type"] == "lyric"]
    seg_texts  = [s["text"].strip() for s in segments]

    matched = {}
    used_segs = set()

    for i, lyric in enumerate(lyric_only):
        best_score = 0
        best_seg   = None
        for j, seg in enumerate(segments):
            if j in used_segs:
                continue
            score = similarity(lyric["text"], seg["text"])
            if score > best_score:
                best_score = score
                best_seg   = j

        if best_seg is not None and best_score > 0.3:
            matched[i] = {
                "start": segments[best_seg]["start"],
                "end":   segments[best_seg]["end"],
                "score": round(best_score, 2),
            }
            used_segs.add(best_seg)

    return matched

def build_timestamps(lyric_lines, matched, audio_duration):
    """
    Build full timestamp list for all lines (lyrics, sections, blanks).
    Sections and blanks get interpolated timing between surrounding lyrics.
    """
    lyric_only = [i for i, l in enumerate(lyric_lines) if l["type"] == "lyric"]
    lyric_match_map = {}
    lyric_idx = 0
    for i, line in enumerate(lyric_lines):
        if line["type"] == "lyric":
            if lyric_idx in matched:
                lyric_match_map[i] = matched[lyric_idx]
            lyric_idx += 1

    # Fill in gaps with interpolation
    result = []
    for i, line in enumerate(lyric_lines):
        if i in lyric_match_map:
            m = lyric_match_map[i]
            result.append({
                "type":  line["type"],
                "text":  line["text"],
                "start": m["start"],
                "end":   m["end"],
                "synced": True,
            })
        else:
            # Find nearest surrounding synced lines
            prev_end = 0.0
            next_start = audio_duration
            for j in range(i - 1, -1, -1):
                if j < len(result) and result[j].get("end"):
                    prev_end = result[j]["end"]
                    break
            # Interpolate: give non-lyric lines a short slot
            dur = 0.5 if line["type"] == "blank" else 1.5
            result.append({
                "type":  line["type"],
                "text":  line["text"],
                "start": prev_end,
                "end":   prev_end + dur,
                "synced": False,
            })

    return result

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse, sys
    parser = argparse.ArgumentParser()
    parser.add_argument("--song", required=True, help="Song name matching a .txt in the lyrics folder")
    args = parser.parse_args()

    LYRICS_PATH, AUDIO_PATH, OUTPUT_PATH = resolve_song(args.song)
    print(f"Song   : {args.song}")
    print(f"Lyrics : {LYRICS_PATH}")
    print(f"Audio  : {AUDIO_PATH}\n")

    print("Parsing lyrics...")
    lyric_lines = parse_lyrics(LYRICS_PATH)
    print(f"  {len(lyric_lines)} lines found")

    whisper_result = transcribe(AUDIO_PATH)
    audio_duration = whisper_result["segments"][-1]["end"] if whisper_result["segments"] else 0
    print(f"  Audio duration: {audio_duration:.1f}s")

    print("Matching lyrics to transcription...")
    lyric_only = [l for l in lyric_lines if l["type"] == "lyric"]
    matched = match_lyrics_to_segments(lyric_only, whisper_result)
    print(f"  Synced {len(matched)}/{len(lyric_only)} lyric lines")

    timestamps = build_timestamps(lyric_lines, matched, audio_duration)
    OUTPUT_PATH.write_text(json.dumps(timestamps, indent=2), encoding="utf-8")
    print(f"\nTimestamps saved → {OUTPUT_PATH}")
