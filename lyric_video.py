"""
Lyric Video Generator
Combines song audio + lyrics + AI-generated backgrounds into a YouTube-ready MP4.
Output: 1920x1080, 16:9, H.264
"""

import re
from pathlib import Path
from mutagen.wave import WAVE
from PIL import Image, ImageDraw, ImageFont
from moviepy import AudioFileClip, ImageClip, concatenate_videoclips

# ── Config ────────────────────────────────────────────────────────────────────
AUDIO_PATH       = Path("songs/wave/Love is a battlefield (the death of me).wav")
LYRICS_PATH      = Path("songs/wave/Love is a battlefield ( the death of me).txt")
BACKGROUNDS_DIR  = Path("backgrounds")
OUTPUT_PATH      = Path("outputs/lyric_video.mp4")

OUTPUT_PATH.parent.mkdir(exist_ok=True)

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

def assign_timings(lines, duration):
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
    "VERSE 1":      "verse_1.png",
    "VERSE 2":      "verse_2.png",
    "PRE-CHORUS":   "pre-chorus.png",
    "CHORUS":       "chorus.png",
    "VERSE 3":      "verse_3.png",
    "BRIDGE":       "bridge.png",
    "FINAL CHORUS": "final_chorus.png",
    "OUTRO":        "outro.png",
}

def load_background(section_label):
    if section_label and section_label in SECTION_TO_BG:
        bg_path = BACKGROUNDS_DIR / SECTION_TO_BG[section_label]
        if bg_path.exists():
            img = Image.open(bg_path).convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
            # darken slightly so text is readable
            overlay = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
            img = Image.blend(img, overlay, 0.45)
            return img
    return Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)

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

# ── Build video ───────────────────────────────────────────────────────────────
def build_video(lines, durations, audio_path, output_path):
    clips = []
    current_section = None
    bg_img = load_background(None)

    print(f"Building {len(lines)} clips...")
    for i, ((ltype, text, section_label), dur) in enumerate(zip(lines, durations)):
        if ltype == "section":
            current_section = text
            bg_img = load_background(current_section)

        frame = make_frame(text if ltype != "blank" else "", ltype, bg_img)
        fade  = min(0.3, dur * 0.25)
        clip  = ImageClip(frame, duration=dur).crossfadein(fade).crossfadeout(fade)
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

    durations = assign_timings(lines, duration)
    build_video(lines, durations, AUDIO_PATH, OUTPUT_PATH)
