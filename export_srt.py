"""
SRT Subtitle Exporter
Generates a .srt caption file from Whisper timestamps.
Upload to YouTube for automatic captions, or use in video editors.

Usage:
    python export_srt.py --song "Love is a battlefield ( the death of me)"
Output:
    outputs/{song}.srt
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import BASE_DIR, TS_DIR, OUTPUTS_DIR, all_songs

def seconds_to_srt_time(s):
    h  = int(s // 3600)
    m  = int((s % 3600) // 60)
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

def export_srt(song_name, timestamps):
    out_path = OUTPUTS_DIR / f"{song_name}.srt"
    lyric_entries = [e for e in timestamps if e["type"] == "lyric" and e.get("text")]

    lines = []
    for i, entry in enumerate(lyric_entries, start=1):
        start = entry.get("start", 0)
        end   = entry.get("end",   start + 2.0)
        text  = entry["text"].strip()

        lines.append(str(i))
        lines.append(f"{seconds_to_srt_time(start)} --> {seconds_to_srt_time(end)}")
        lines.append(text)
        lines.append("")

    srt_content = "\n".join(lines)
    out_path.write_text(srt_content, encoding="utf-8")
    print(f"SRT saved → {out_path}")
    print(f"  {len(lyric_entries)} subtitle entries")
    return out_path

def export_chapters(song_name, timestamps):
    """Also export YouTube chapter markers from section labels."""
    out_path = OUTPUTS_DIR / f"{song_name}_chapters.txt"
    sections = [e for e in timestamps if e["type"] == "section" and e.get("text")]

    if not sections:
        print("No section markers found for chapter export.")
        return

    def fmt_time(s):
        m = int(s // 60)
        sec = int(s % 60)
        return f"{m}:{sec:02d}"

    lines = ["Chapters:", "0:00 Intro"]
    for entry in sections:
        t    = entry.get("start", 0)
        name = entry["text"].title()
        lines.append(f"{fmt_time(t)} {name}")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Chapters saved → {out_path}")
    return out_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--song", required=True)
    args = parser.parse_args()

    ts_path = TS_DIR / f"{args.song}.json"
    if not ts_path.exists():
        print(f"ERROR: No timestamps found for '{args.song}'.")
        print("Run sync_lyrics.py first.")
        sys.exit(1)

    timestamps = json.loads(ts_path.read_text(encoding="utf-8"))
    print(f"Exporting SRT + chapters for: {args.song}\n")
    export_srt(args.song, timestamps)
    export_chapters(args.song, timestamps)
    print("\nDone! Upload the .srt to YouTube for captions.")
    print("Copy the chapters text into your YouTube video description.")
