"""
Lyric Video Generator
Combines song audio + lyrics + AI-generated backgrounds into a YouTube-ready MP4.
Output: 1920x1080, 16:9, H.264
"""

import re
import numpy as np
from pathlib import Path
from mutagen.wave import WAVE
from PIL import Image, ImageDraw, ImageFont
from moviepy import AudioFileClip, ImageClip, VideoFileClip, VideoClip, concatenate_videoclips, CompositeVideoClip

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

FONT_LYRICS  = get_font(72)   # current line
FONT_SMALL   = get_font(44)   # next line preview
FONT_SECTION = get_font(38)   # section labels

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
        return ImageClip(np.array(img), duration=duration), False

    # Fallback: solid dark background
    return ImageClip(np.array(Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)), duration=duration), False

# ── Karaoke renderer ──────────────────────────────────────────────────────────
# Colors
WORD_DEFAULT  = (220, 220, 220)   # unsung words — light grey
WORD_ACTIVE   = (255, 220,  60)   # currently sung word — gold
WORD_SUNG     = (255, 255, 255)   # already sung words — bright white
NEXT_COLOR    = (160, 160, 160)   # next line preview — dimmer
SECTION_COLOR_K = (180, 140, 200) # section label

SHADOW        = (0, 0, 0)

def measure_word(draw, word, font):
    bb = draw.textbbox((0, 0), word, font=font)
    return bb[2] - bb[0], bb[3] - bb[1]

def draw_karaoke_line(draw, words_with_state, font, cy, max_w):
    """
    Draw one line of text with per-word color.
    words_with_state: list of (word_str, color)
    Returns actual y used.
    """
    # Measure total line width
    space_w, _ = measure_word(draw, " ", font)
    total_w = 0
    for word, _ in words_with_state:
        w, _ = measure_word(draw, word, font)
        total_w += w
    total_w += space_w * max(0, len(words_with_state) - 1)
    total_w = min(total_w, max_w)

    x = (WIDTH - total_w) // 2
    for idx, (word, color) in enumerate(words_with_state):
        draw.text((x + 2, cy + 2), word, font=font, fill=(*SHADOW, 200))
        draw.text((x, cy), word, font=font, fill=color)
        w, _ = measure_word(draw, word, font)
        x += w + space_w

def make_karaoke_frame(bg_img, entry, next_entry, t_in_clip):
    """
    Render one video frame with karaoke-style lyrics.
    - entry: current line dict (text, words, start, end)
    - next_entry: next lyric line dict or None
    - t_in_clip: time elapsed within this clip (seconds)
    """
    img  = bg_img.copy()
    draw = ImageDraw.Draw(img)

    ltype = entry.get("type", "lyric")

    if ltype == "section":
        # Section label centered, purple
        text = entry.get("text", "")
        bb = draw.textbbox((0, 0), text, font=FONT_SECTION)
        x = (WIDTH - (bb[2] - bb[0])) // 2
        y = (HEIGHT - (bb[3] - bb[1])) // 2
        draw.text((x + 2, y + 2), text, font=FONT_SECTION, fill=(*SHADOW, 200))
        draw.text((x, y), text, font=FONT_SECTION, fill=SECTION_COLOR_K)
        return img

    if ltype == "blank" or not entry.get("text"):
        return img

    max_w       = int(WIDTH * 0.82)
    line_h_main = FONT_LYRICS.size + 20
    line_h_next = FONT_SMALL.size  + 12

    # ── Current line ──────────────────────────────────────────────────────────
    text        = entry["text"]
    words_ts    = entry.get("words", [])   # [{word, start, end}, ...]
    line_start  = entry.get("start", 0)
    abs_t       = line_start + t_in_clip   # absolute song time at this frame

    # Split text into word tokens matching whisper words
    text_words  = text.split()

    if words_ts:
        # Map each text word to its timing
        states = []
        for i, tw in enumerate(text_words):
            if i < len(words_ts):
                ws = words_ts[i]["start"]
                we = words_ts[i]["end"]
                if abs_t >= we:
                    color = WORD_SUNG
                elif abs_t >= ws:
                    color = WORD_ACTIVE
                else:
                    color = WORD_DEFAULT
            else:
                color = WORD_DEFAULT
            states.append((tw, color))
    else:
        # No word timestamps — highlight whole line after halfway
        color  = WORD_SUNG if t_in_clip > (entry.get("end", 0) - line_start) * 0.5 else WORD_DEFAULT
        states = [(w, color) for w in text_words]

    # Calculate vertical position — current line slightly above center
    total_h = line_h_main + (line_h_next + 10 if next_entry else 0)
    cy = (HEIGHT - total_h) // 2 - 20

    draw_karaoke_line(draw, states, FONT_LYRICS, cy, max_w)

    # ── Next line preview ─────────────────────────────────────────────────────
    if next_entry and next_entry.get("text"):
        ny = cy + line_h_main + 18
        next_words = [(w, NEXT_COLOR) for w in next_entry["text"].split()]
        draw_karaoke_line(draw, next_words, FONT_SMALL, ny, max_w)

    return img

# ── Build video ───────────────────────────────────────────────────────────────
def build_video(lines, durations, timestamps, audio_path, output_path):
    """
    lines      : list of (ltype, text, section_label)
    durations  : seconds per line
    timestamps : list of dicts from timestamps.json (includes word timings)
    """

    clips = []
    current_section = None

    # Build enriched entries for karaoke renderer
    entries = []
    for i, ((ltype, text, section_label), dur) in enumerate(zip(lines, durations)):
        ts = timestamps[i] if timestamps and i < len(timestamps) else {}
        entries.append({
            "type":    ltype,
            "text":    text if ltype != "blank" else "",
            "section": section_label,
            "dur":     dur,
            "start":   ts.get("start", 0),
            "end":     ts.get("end", 0),
            "words":   ts.get("words", []),
        })

    print(f"Building {len(entries)} clips...")
    for i, entry in enumerate(entries):
        if entry["type"] == "section":
            current_section = entry["text"]

        dur  = entry["dur"]
        fade = min(0.25, dur * 0.2)

        # Find next lyric line for preview
        next_lyric = None
        for j in range(i + 1, len(entries)):
            if entries[j]["type"] == "lyric":
                next_lyric = entries[j]
                break

        bg_clip, is_video = load_background_clip(current_section, dur)

        if is_video:
            # Generate karaoke frames on top of video
            def make_frame_fn(t, _entry=entry, _next=next_lyric, _bg=bg_clip):
                bg_frame = _bg.get_frame(min(t, _bg.duration - 0.01))
                bg_pil   = Image.fromarray(bg_frame)
                return np.array(make_karaoke_frame(bg_pil, _entry, _next, t))

            clip = VideoClip(make_frame_fn, duration=dur)
        else:
            # Static background — still render karaoke frames
            bg_frame = np.array(bg_clip.get_frame(0))
            bg_pil   = Image.fromarray(bg_frame)

            def make_frame_fn(t, _entry=entry, _next=next_lyric, _bg_pil=bg_pil):
                return np.array(make_karaoke_frame(_bg_pil, _entry, _next, t))

            clip = VideoClip(make_frame_fn, duration=dur)

        clip = clip.with_fps(FPS).crossfadein(fade).crossfadeout(fade)
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
    import json as _json
    print(f"Song   : {_args.song}")
    print(f"Lyrics : {LYRICS_PATH}")
    print(f"Audio  : {AUDIO_PATH}\n")

    print("Parsing lyrics...")
    lines = parse_lyrics(LYRICS_PATH)

    print("Getting audio duration...")
    from mutagen.mp3 import MP3 as _MP3
    try:
        if str(AUDIO_PATH).endswith(".wav"):
            audio_info = WAVE(str(AUDIO_PATH))
        else:
            audio_info = _MP3(str(AUDIO_PATH))
        duration = audio_info.info.length
    except Exception:
        from moviepy import AudioFileClip as _AFC
        duration = _AFC(str(AUDIO_PATH)).duration
    print(f"  {duration:.1f}s ({duration/60:.1f} min)")

    # Load timestamps (includes word-level data for karaoke)
    timestamps_path = TS_DIR / f"{_args.song}.json"
    timestamps = None
    if timestamps_path.exists():
        timestamps = _json.loads(timestamps_path.read_text(encoding="utf-8"))
        print(f"  Loaded {len(timestamps)} synced entries with word timestamps")
    else:
        print("  No timestamps — lyrics will be evenly distributed")

    durations = assign_timings(lines, duration, timestamps_path)
    build_video(lines, durations, timestamps, AUDIO_PATH, OUTPUT_PATH)
