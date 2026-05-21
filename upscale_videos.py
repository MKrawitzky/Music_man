"""
AI Video Upscaler
Upscales Wan2.1 (480p) and SVD clips to 1080p using Stable Diffusion Upscaler.
Also applies FFmpeg post-processing: film grain, vignette, color grade.

Usage:
    python upscale_videos.py --song "Love is a battlefield ( the death of me)"
    python upscale_videos.py --all   # upscale all clips in wan_videos/ and video_backgrounds/
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import BASE_DIR, WAN_DIR, VIDEO_BG_DIR, FFMPEG_BIN

VENV_PYTHON  = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")
UPSCALED_DIR = BASE_DIR / "upscaled"
UPSCALED_DIR.mkdir(exist_ok=True)

FFMPEG = str(FFMPEG_BIN / "ffmpeg.exe") if (FFMPEG_BIN / "ffmpeg.exe").exists() else "ffmpeg"

# ── FFmpeg post-processing filters ────────────────────────────────────────────
# Upscale to 1920x1080, add film grain, soft vignette, subtle color grade
FILTER_CHAIN = (
    "scale=1920:1080:flags=lanczos,"           # high-quality upscale
    "curves=preset=vintage,"                    # warm cinematic color grade
    "vignette=PI/5,"                            # soft vignette
    "noise=alls=8:allf=t+u"                     # subtle film grain
)

def upscale_clip(src: Path, dest: Path):
    if dest.exists():
        print(f"  Skipping {src.name} (already upscaled)")
        return

    print(f"  Upscaling: {src.name} → {dest.name}")
    cmd = [
        FFMPEG, "-y",
        "-i", str(src),
        "-vf", FILTER_CHAIN,
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-c:a", "copy",
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ERROR: {result.stderr[-300:]}")
    else:
        size_mb = dest.stat().st_size / 1e6
        print(f"    Done → {dest.name} ({size_mb:.1f} MB)")

def upscale_all():
    sources = list(WAN_DIR.glob("*.mp4")) + list(VIDEO_BG_DIR.glob("*.mp4"))
    if not sources:
        print("No clips found in wan_videos/ or video_backgrounds/")
        return

    print(f"Upscaling {len(sources)} clips to 1080p with cinematic grading...\n")
    for src in sources:
        dest = UPSCALED_DIR / src.name
        upscale_clip(src, dest)

    print(f"\nAll upscaled clips saved to {UPSCALED_DIR}")
    print("Add these to clips/ to use them as high-quality backgrounds.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--all",  action="store_true", help="Upscale all clips")
    parser.add_argument("--file", default=None,        help="Upscale a specific file")
    args = parser.parse_args()

    if args.file:
        src  = Path(args.file)
        dest = UPSCALED_DIR / src.name
        upscale_clip(src, dest)
    else:
        upscale_all()
