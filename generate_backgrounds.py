"""
Background Image Generator using Stable Diffusion (free, local, GPU-accelerated)
Generates one atmospheric background image per song section.
"""

import torch
from pathlib import Path
from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

OUTPUT_DIR = Path("backgrounds")
OUTPUT_DIR.mkdir(exist_ok=True)

# ── Section prompts ────────────────────────────────────────────────────────────
# Each section of the song gets a tailored visual prompt.
SECTION_PROMPTS = {
    "VERSE 1": (
        "dark cinematic night scene, person standing at the edge, slow motion, "
        "velvet shadows, dramatic moonlight, emotional atmosphere, 4k, no text"
    ),
    "VERSE 2": (
        "neon lights reflecting on wet pavement, silhouette of a woman, "
        "cherry blossom petals falling, cinematic, moody, 4k, no text"
    ),
    "PRE-CHORUS": (
        "two silhouettes barely touching in a dark room, soft golden light, "
        "intimate, whispered moment, cinematic still, no text"
    ),
    "CHORUS": (
        "battlefield at dusk, burning embers floating upward, dramatic sky, "
        "emotional and epic, wide shot, cinematic, 4k, no text"
    ),
    "VERSE 3": (
        "person alone in dark hallway, soft light at the end, longing, "
        "cinematic, desaturated colors, emotional, 4k, no text"
    ),
    "BRIDGE": (
        "time lapse swirling galaxy, hypnotic spiral, deep purples and blues, "
        "emotional spiral, cinematic, 4k, no text"
    ),
    "FINAL CHORUS": (
        "broken mirror reflecting shattered light, hands reaching toward glass, "
        "golden hour, emotional, cinematic, dramatic, 4k, no text"
    ),
    "OUTRO": (
        "empty room, curtains moving in wind, single spotlight, "
        "someone just left, intimate, devastating silence, cinematic, 4k, no text"
    ),
}

NEGATIVE_PROMPT = (
    "text, watermark, logo, blurry, low quality, cartoon, anime, "
    "oversaturated, ugly, deformed, noisy"
)

def load_pipeline():
    print("Loading Stable Diffusion model (first run downloads ~4GB)...")
    model_id = "runwayml/stable-diffusion-v1-5"

    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=torch.float16,
        safety_checker=None,
    )
    pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe = pipe.to("cuda")
    pipe.enable_attention_slicing()  # saves VRAM
    print("Model loaded.")
    return pipe

def generate_backgrounds(pipe):
    for section, prompt in SECTION_PROMPTS.items():
        out_path = OUTPUT_DIR / f"{section.lower().replace(' ', '_')}.png"
        if out_path.exists():
            print(f"  Skipping {section} (already exists)")
            continue

        print(f"  Generating: {section}...")
        result = pipe(
            prompt=prompt,
            negative_prompt=NEGATIVE_PROMPT,
            width=1024,
            height=576,   # 16:9 at this scale, upscale in video
            num_inference_steps=30,
            guidance_scale=7.5,
        )
        img = result.images[0]
        img.save(out_path)
        print(f"    Saved → {out_path}")

if __name__ == "__main__":
    if not torch.cuda.is_available():
        print("WARNING: No CUDA GPU detected — generation will be very slow on CPU.")
        print("Install PyTorch with CUDA: https://pytorch.org/get-started/locally/")
    else:
        print(f"GPU: {torch.cuda.get_device_name(0)}")

    pipe = load_pipeline()
    generate_backgrounds(pipe)
    print("\nAll backgrounds generated in ./backgrounds/")
