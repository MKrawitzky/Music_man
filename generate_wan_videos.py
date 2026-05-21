"""
Wan2.1 Text-to-Video Generator
Generates cinematic video clips directly from text prompts — no still image needed.
Uses Wan-AI/Wan2.1-T2V-1.3B (fits in 12GB VRAM).

Output: wan_videos/{section}.mp4
These are automatically picked up by lyric_video.py as backgrounds.

Usage:
    python generate_wan_videos.py --song "Love is a battlefield ( the death of me)"
"""

import argparse
import os
import sys
import torch
import numpy as np
from pathlib import Path
from diffusers import WanPipeline
from diffusers.utils import export_to_video

sys.path.insert(0, str(Path(__file__).parent))
from config import HF_CACHE, BASE_DIR

WAN_MODEL   = "Wan-AI/Wan2.1-T2V-1.3B-Diffusers"
WAN_DIR     = BASE_DIR / "wan_videos"
WAN_DIR.mkdir(exist_ok=True)

# ── Per-section prompts (defaults — overridable per song) ─────────────────────
DEFAULT_PROMPTS = {
    "VERSE 1": (
        "slow motion rain falling on a dark window at night, neon reflections, "
        "cinematic, moody, 4k, emotional atmosphere, no text, no people"
    ),
    "VERSE 2": (
        "cherry blossoms falling in slow motion, night city lights bokeh, "
        "cinematic, soft purple tones, emotional, 4k, no text"
    ),
    "PRE-CHORUS": (
        "two hands almost touching across a dark table, candlelight flickering, "
        "intimate close up, cinematic, soft focus, no text"
    ),
    "CHORUS": (
        "ocean waves crashing on rocks at golden hour, dramatic sky, "
        "slow motion water spray, epic cinematic, wide shot, 4k, no text"
    ),
    "VERSE 3": (
        "empty hallway with a single light at the end, shadows moving slowly, "
        "cinematic, desaturated, emotional tension, 4k, no text"
    ),
    "BRIDGE": (
        "time lapse of storm clouds spiraling over a city, lightning in distance, "
        "hypnotic motion, deep blues and purples, cinematic, 4k, no text"
    ),
    "FINAL CHORUS": (
        "slow motion glass shattering and falling, golden backlight, "
        "fragments catching light, dramatic, cinematic, 4k, no text"
    ),
    "OUTRO": (
        "empty room, curtains drifting in slow motion, dust particles in sunlight, "
        "someone just left, devastating silence, cinematic, 4k, no text"
    ),
}

NEGATIVE_PROMPT = (
    "text, watermark, logo, blurry, low quality, cartoon, anime, "
    "ugly, deformed, still image, no motion"
)

# ── Load pipeline ─────────────────────────────────────────────────────────────
def load_pipeline():
    print(f"Loading Wan2.1 model (first run downloads ~6GB to E:/hf-cache)...")
    os.environ["HF_HOME"] = HF_CACHE

    pipe = WanPipeline.from_pretrained(
        WAN_MODEL,
        torch_dtype=torch.bfloat16,
        cache_dir=HF_CACHE,
    )
    pipe.enable_model_cpu_offload()
    print(f"Wan2.1 loaded on {torch.cuda.get_device_name(0)}")
    return pipe

# ── Generate one clip ─────────────────────────────────────────────────────────
def generate_clip(pipe, section, prompt, out_path):
    print(f"\n  [{section}]")
    print(f"  Prompt: {prompt[:80]}...")

    output = pipe(
        prompt=prompt,
        negative_prompt=NEGATIVE_PROMPT,
        height=480,
        width=832,        # 16:9 at 480p
        num_frames=49,    # ~4s at 16fps — good loop length
        guidance_scale=5.0,
        num_inference_steps=30,
        generator=torch.Generator("cpu").manual_seed(42),
    )

    export_to_video(output.frames[0], str(out_path), fps=16)
    print(f"  Saved → {out_path}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--song", required=True, help="Song name")
    parser.add_argument("--section", default=None, help="Generate only this section (optional)")
    parser.add_argument("--prompt", default=None, help="Custom prompt for --section")
    args = parser.parse_args()

    if not torch.cuda.is_available():
        print("ERROR: CUDA GPU required for Wan2.1.")
        sys.exit(1)

    print(f"GPU  : {torch.cuda.get_device_name(0)}")
    print(f"VRAM : {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB")
    print(f"Song : {args.song}\n")

    # Build section list
    if args.section:
        sections = {args.section: args.prompt or DEFAULT_PROMPTS.get(args.section, "")}
    else:
        sections = DEFAULT_PROMPTS

    # Check which are missing
    to_generate = {}
    for section, prompt in sections.items():
        key = section.lower().replace(" ", "_").replace("-", "_")
        out_path = WAN_DIR / f"{key}.mp4"
        if out_path.exists():
            print(f"  Skipping {section} (already exists)")
        else:
            to_generate[section] = (prompt, out_path)

    if not to_generate:
        print("All clips already exist. Delete wan_videos/*.mp4 to regenerate.")
        return

    pipe = load_pipeline()

    for section, (prompt, out_path) in to_generate.items():
        generate_clip(pipe, section, prompt, out_path)

    print(f"\nDone! {len(to_generate)} clips saved to {WAN_DIR}")
    print("Run lyric_video.py to render the final video.")

if __name__ == "__main__":
    main()
