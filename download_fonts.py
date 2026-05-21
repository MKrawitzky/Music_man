"""
Google Fonts Downloader
Downloads free cinematic fonts for use in the lyric video.
Run once — fonts saved to ./fonts/

Usage:
    python download_fonts.py
"""

import urllib.request
import zipfile
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import BASE_DIR

FONTS_DIR = BASE_DIR / "fonts"
FONTS_DIR.mkdir(exist_ok=True)

# Google Fonts direct download URLs (zip files)
FONT_PACKS = {
    "Playfair Display": "https://fonts.google.com/download?family=Playfair+Display",
    "Cormorant":        "https://fonts.google.com/download?family=Cormorant",
    "Bebas Neue":       "https://fonts.google.com/download?family=Bebas+Neue",
    "Montserrat":       "https://fonts.google.com/download?family=Montserrat",
    "Raleway":          "https://fonts.google.com/download?family=Raleway",
}

def download_font(name, url):
    font_dir = FONTS_DIR / name.replace(" ", "_")
    if font_dir.exists() and any(font_dir.glob("*.ttf")):
        print(f"  Already downloaded: {name}")
        return

    print(f"  Downloading: {name}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            font_dir.mkdir(exist_ok=True)
            for member in z.namelist():
                if member.endswith(".ttf") or member.endswith(".otf"):
                    fname = Path(member).name
                    (font_dir / fname).write_bytes(z.read(member))
                    print(f"    → {fname}")
    except Exception as e:
        print(f"    FAILED: {e}")

def list_available():
    """Print all downloaded fonts with their paths."""
    print("\nAvailable fonts:")
    for ttf in sorted(FONTS_DIR.rglob("*.ttf")):
        print(f"  {ttf.relative_to(FONTS_DIR)} → {ttf}")

def get_font_path(name_contains):
    """Find a font file by partial name match."""
    for ttf in FONTS_DIR.rglob("*.ttf"):
        if name_contains.lower() in ttf.stem.lower():
            return ttf
    return None

if __name__ == "__main__":
    print("Downloading Google Fonts for lyric videos...\n")
    for name, url in FONT_PACKS.items():
        download_font(name, url)
    list_available()
    print("\nTo use a font, set FONT_NAME in lyric_video.py")
    print('Example: FONT_NAME = "Playfair_Display/PlayfairDisplay-Regular.ttf"')
