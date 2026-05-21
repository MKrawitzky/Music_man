"""
SVD Video Background Generator
Uses Stable Video Diffusion (image-to-video) to animate each still background
into a short looping video clip per song section.

Requires: diffusers, torch (CUDA), transformers, accelerate
First run downloads ~7GB model to E:/hf-cache/
"""

import torch
import numpy as np
from pathlib import Path
from PIL import Image
from diffusers import StableVideoDiffusionPipeline
from diffusers.utils import export_to_video

# ── Config ────────────────────────────────────────────────────────────────────
BACKGROUNDS_DIR  = Path("backgrounds")
VIDEO_BG_DIR     = Path("video_backgrounds")
HF_CACHE_DIR     = "E:/hf-cache"          # keeps models off C: drive

VIDEO_BG_DIR.mkdir(exist_ok=True)

# SVD settings
SVD_MODEL    = "stabilityai/stable-video-diffusion-img2vid-xt"  # 25 frames
NUM_FRAMES   = 25       # 25 frames at 6fps = ~4s clip, loops seamlessly
FPS_OUT      = 6        # cinematic slow motion feel
MOTION_SCALE = 100      # 0–255: lower = subtle drift, higher = lots of motion
DECODE_CHUNK = 8        # lower if you hit VRAM limits

# Section → background image mapping
SECTIONS = [
    "verse_1",
    "verse_2",
    "pre-chorus",
    "chorus",
    "verse_3",
    "bridge",
    "final_chorus",
    "outro",
]

# ── Load pipeline ─────────────────────────────────────────────────────────────
def load_pipeline():
    print("Loading SVD model (first run ~7GB download to E:/hf-cache)...")
    import os
    os.environ["HF_HOME"] = HF_CACHE_DIR

    pipe = StableVideoDiffusionPipeline.from_pretrained(
        SVD_MODEL,
        torch_dtype=torch.float16,
        variant="fp16",
        cache_dir=HF_CACHE_DIR,
    )
    pipe.to("cuda")
    pipe.enable_model_cpu_offload()   # offloads to RAM when not in use — saves VRAM
    pipe.unet.enable_forward_chunking()
    print(f"SVD loaded on {torch.cuda.get_device_name(0)}")
    return pipe

# ── Animate one image ─────────────────────────────────────────────────────────
def animate_image(pipe, img_path: Path, out_path: Path):
    print(f"  Animating: {img_path.name} ...")

    # SVD XT expects 1024x576 (16:9)
    img = Image.open(img_path).convert("RGB").resize((1024, 576), Image.LANCZOS)

    generator = torch.manual_seed(42)  # fixed seed = reproducible results

    frames = pipe(
        img,
        num_frames=NUM_FRAMES,
        motion_bucket_id=MOTION_SCALE,
        noise_aug_strength=0.02,       # low = stays close to source image
        decode_chunk_size=DECODE_CHUNK,
        generator=generator,
    ).frames[0]

    # Export as MP4
    export_to_video(frames, str(out_path), fps=FPS_OUT)
    print(f"    Saved → {out_path}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not torch.cuda.is_available():
        print("ERROR: No CUDA GPU found. SVD requires a GPU.")
        return

    print(f"GPU: {torch.cuda.get_device_name(0)}")
    print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB\n")

    missing = [s for s in SECTIONS if not (BACKGROUNDS_DIR / f"{s}.png").exists()]
    if missing:
        print(f"WARNING: Missing background images: {missing}")
        print("Run generate_backgrounds.py first to create still images.\n")

    pipe = load_pipeline()

    for section in SECTIONS:
        img_path = BACKGROUNDS_DIR / f"{section}.png"
        out_path = VIDEO_BG_DIR / f"{section}.mp4"

        if not img_path.exists():
            print(f"  Skipping {section} (no source image)")
            continue
        if out_path.exists():
            print(f"  Skipping {section} (video already exists)")
            continue

        animate_image(pipe, img_path, out_path)

    print("\nAll video backgrounds generated in ./video_backgrounds/")
    print("Now run lyric_video.py to build the final video.")

if __name__ == "__main__":
    main()
