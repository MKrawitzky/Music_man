"""
Lyric Video Generator
Combines song audio + lyrics + AI-generated backgrounds into a YouTube-ready MP4.
Output: 1920x1080, 16:9, H.264
"""

import re
from pathlib import Path
from mutagen.wave import WAVE
from PIL import Image, ImageDraw, ImageFont
from moviepy import AudioFileClip, ImageClip, VideoFileClip, concatenate_videoclips, CompositeVideoClip

# ── Config (resolved per-song via --song arg) ─────────────────────────────────
import sys, argparse
sys.path.insert(0, str(Path(__file__).parent))
from config import LYRICS_DIR, TS_DIR, OUTPUTS_DIR, BG_DIR, VIDEO_BG_DIR, find_audio, all_songs, find_background

def resolve_song(song_name):
    songs = {s["name"]: s for s in all_songs()}
    if song_name not in songs:
        print(f"ERROR: Song '{song_name}' not found.")
        sys.exit(1)
    s = songs[song_name]
    return s["lyrics_path"], s["audio_path"], OUTPUTS_DIR / f"{song_name}.mp4"

parser = argparse.ArgumentParser()
parser.add_argument("--song", required=True)
_args = parser.parse_args()

LYRICS_PATH, AUDIO_PATH, OUTPUT_PATH = resolve_song(_args.song)
BACKGROUNDS_DIR = BG_DIR

WIDTH, HEIGHT = 1920, 1080
FPS = 24

BG_COLOR      = (10, 10, 18)
TEXT_COLOR    = (255, 255, 255)
SECTION_COLOR = (180, 140, 200)

def get_font(size):
    candidates = [
        "C:/Windows/Fonts/Georgia.ttf",
        "C:/Windows/Fonts/times.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()

FONT_LYRICS  = get_font(72)
FONT_SECTION = get_font(36)

# ── Lyric parsing ─────────────────────────────────────────────────────────────
SECTION_PATTERN  = re.compile(r"^\[(.+?)\]")
STAGE_DIRECTION  = re.compile(r"^\(.*\)$")

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
            lines.append(("blank", "", None))
        elif SECTION_PATTERN.match(line):
            label = SECTION_PATTERN.match(line).group(1).strip()
            lines.append(("section", label.upper(), label.upper()))
        elif STAGE_DIRECTION.match(line):
            pass
        else:
            lines.append(("lyric", line, None))
    return lines

def assign_timings(lines, duration, timestamps_path=None):
    """
    If a timestamps.json file exists (from sync_lyrics.py), use those exact timings.
    Otherwise distribute lyrics evenly across the song duration.
    """
    import json

    if timestamps_path and Path(timestamps_path).exists():
        print("  Using Whisper-synced timestamps.")
        data = json.loads(Path(timestamps_path).read_text(encoding="utf-8"))
        timings = []
        for i, entry in enumerate(data):
            start = entry["start"]
            end   = entry["end"]
            # Duration is gap to next line's start (not just end-start)
            if i + 1 < len(data):
                dur = data[i + 1]["start"] - start
            else:
                dur = end - start
            timings.append(max(dur, 0.2))
        return timings

    print("  No timestamps found — distributing evenly.")
    lyric_count   = sum(1 for t, _, _ in lines if t == "lyric")
    section_count = sum(1 for t, _, _ in lines if t == "section")
    blank_count   = sum(1 for t, _, _ in lines if t == "blank")

    section_time = section_count * 1.5
    blank_time   = blank_count * 0.4
    lyric_time   = max(duration - section_time - blank_time, duration * 0.6)
    per_lyric    = lyric_time / max(lyric_count, 1)

    timings = []
    for ltype, text, _ in lines:
        if ltype == "lyric":
            timings.append(per_lyric)
        elif ltype == "section":
            timings.append(1.5)
        else:
            timings.append(0.4)
    return timings

# ── Background loading ────────────────────────────────────────────────────────
SECTION_TO_BG = {
    "VERSE 1":      "verse_1",
    "VERSE 2":      "verse_2",
    "PRE-CHORUS":   "pre-chorus",
    "CHORUS":       "chorus",
    "VERSE 3":      "verse_3",
    "BRIDGE":       "bridge",
    "FINAL CHORUS": "final_chorus",
    "OUTRO":        "outro",
}

def load_background_clip(section_label, duration):
    """
    Returns (MoviePy clip, is_video) using Option 4 priority:
    own clips > Wan2.1 > SVD > SD still image > solid color
    """
    from moviepy import concatenate_videoclips as _cat

    if section_label:
        bg_path, bg_type = find_background(section_label)
    else:
        bg_path, bg_type = None, None

    if bg_path and bg_type in ("clip", "wan", "svd"):
        clip = VideoFileClip(str(bg_path)).resized((WIDTH, HEIGHT))
        # Loop to fill duration
        if clip.duration < duration:
            loops = int(duration / clip.duration) + 1
            clip = _cat([clip] * loops).subclipped(0, duration)
        else:
            clip = clip.subclipped(0, duration)
        print(f"    BG [{bg_type.upper()}] {bg_path.name}")
        return clip, True

    if bg_path and bg_type == "image":
        img = Image.open(bg_path).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
        overlay = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        img = Image.blend(img, overlay, 0.45)
        print(f"    BG [IMAGE] {bg_path.name}")
        return ImageClip(img, duration=duration), False

    # Fallback: solid dark background
    return ImageClip(Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR), duration=duration), False

# ── Frame rendering ───────────────────────────────────────────────────────────
def wrap_text(text, font, max_width, draw):
    words = text.split()
    lines, current = [], ""
    for word in words:
        test = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def make_frame(text, ltype, bg_img):
    img = bg_img.copy()
    if not text:
        return img

    draw = ImageDraw.Draw(img)
    font  = FONT_SECTION if ltype == "section" else FONT_LYRICS
    color = SECTION_COLOR if ltype == "section" else TEXT_COLOR
    max_w = int(WIDTH * 0.8)

    wrapped     = wrap_text(text, font, max_w, draw)
    line_height = font.size + 16
    total_h     = len(wrapped) * line_height
    y           = (HEIGHT - total_h) // 2

    for line in wrapped:
        bbox   = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x      = (WIDTH - line_w) // 2
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=color)
        y += line_height

    return img

# ── Text overlay rendering ────────────────────────────────────────────────────
def make_text_overlay(text, ltype, duration):
    """Creates a transparent text overlay clip to composite over video background."""
    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    if not text:
        return ImageClip(np.array(img.convert("RGB")), duration=duration).with_opacity(0)

    draw  = ImageDraw.Draw(img)
    font  = FONT_SECTION if ltype == "section" else FONT_LYRICS
    color = SECTION_COLOR if ltype == "section" else TEXT_COLOR
    max_w = int(WIDTH * 0.8)

    wrapped     = wrap_text(text, font, max_w, draw)
    line_height = font.size + 16
    total_h     = len(wrapped) * line_height
    y           = (HEIGHT - total_h) // 2

    for line in wrapped:
        bbox   = draw.textbbox((0, 0), line, font=font)
        line_w = bbox[2] - bbox[0]
        x      = (WIDTH - line_w) // 2
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 200))  # shadow
        draw.text((x, y), line, font=font, fill=(*color, 255))
        y += line_height

    return ImageClip(np.array(img.convert("RGB")), duration=duration)

# ── Build video ───────────────────────────────────────────────────────────────
def build_video(lines, durations, audio_path, output_path):
    import numpy as np
    clips = []
    current_section = None

    print(f"Building {len(lines)} clips...")
    for i, ((ltype, text, section_label), dur) in enumerate(zip(lines, durations)):
        if ltype == "section":
            current_section = text

        bg_clip, is_video = load_background_clip(current_section, dur)
        text_content = text if ltype != "blank" else ""
        fade = min(0.3, dur * 0.25)

        if is_video:
            # Darken video background, composite text on top
            bg_clip = bg_clip.with_effects([])
            text_clip = make_text_overlay(text_content, ltype, dur)
            clip = CompositeVideoClip([bg_clip, text_clip]).crossfadein(fade).crossfadeout(fade)
        else:
            # Static image path (original behavior)
            bg_img = bg_clip.get_frame(0)
            from PIL import Image as _Image
            bg_pil = _Image.fromarray(bg_img)
            frame = make_frame(text_content, ltype, bg_pil)
            clip = ImageClip(np.array(frame), duration=dur).crossfadein(fade).crossfadeout(fade)

        clips.append(clip)
        if i % 10 == 0:
            print(f"  {i}/{len(lines)}")

    print("Concatenating...")
    video = concatenate_videoclips(clips, method="compose")

    print("Adding audio...")
    audio = AudioFileClip(str(audio_path))
    if video.duration < audio.duration:
        pad = ImageClip(Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR), duration=audio.duration - video.duration)
        video = concatenate_videoclips([video, pad], method="compose")
    video = video.subclipped(0, audio.duration).with_audio(audio)

    print(f"Writing → {output_path}")
    video.write_videofile(str(output_path), fps=FPS, codec="libx264", audio_codec="aac", threads=4, logger="bar")
    print("Done!")

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Parsing lyrics...")
    lines = parse_lyrics(LYRICS_PATH)

    print("Getting audio duration...")
    audio_info = WAVE(str(AUDIO_PATH))
    duration   = audio_info.info.length
    print(f"  {duration:.1f}s ({duration/60:.1f} min)")

    timestamps_path = TS_DIR / f"{_args.song}.json"
    durations = assign_timings(lines, duration, timestamps_path)
    build_video(lines, durations, AUDIO_PATH, OUTPUT_PATH)
