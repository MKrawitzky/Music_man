"""
Beat & Energy Analyzer using Librosa
Detects beats, tempo, and high-energy moments in the song.
Saves beats.json used by lyric_video.py to sync background cuts to the beat.

Usage:
    python analyze_beats.py --song "Love is a battlefield ( the death of me)"
"""

import argparse
import json
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import BASE_DIR, all_songs, TS_DIR

def analyze(audio_path, out_path):
    import librosa

    print(f"Loading audio: {audio_path.name}")
    y, sr = librosa.load(str(audio_path), sr=None, mono=True)
    duration = len(y) / sr
    print(f"  Duration: {duration:.1f}s | Sample rate: {sr}Hz")

    # ── Tempo & beats ─────────────────────────────────────────────────────────
    print("  Detecting tempo and beats...")
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    print(f"  Tempo: {float(tempo):.1f} BPM | Beats found: {len(beat_times)}")

    # ── Energy / RMS (intensity over time) ────────────────────────────────────
    print("  Analyzing energy...")
    hop_length  = 512
    rms         = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    rms_times   = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    rms_norm    = (rms / rms.max()).tolist()

    # ── Spectral contrast (brightness) ────────────────────────────────────────
    contrast    = librosa.feature.spectral_contrast(y=y, sr=sr)
    contrast_mean = contrast.mean(axis=0).tolist()

    # ── Onset strength (sudden loud moments) ──────────────────────────────────
    onset_env   = librosa.onset.onset_strength(y=y, sr=sr)
    onset_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr).tolist()
    onset_norm  = (onset_env / onset_env.max()).tolist()

    # ── Chorus detection (high-energy repeated sections) ──────────────────────
    print("  Detecting high-energy sections (chorus candidates)...")
    # Simple: find time windows where RMS > 75th percentile
    threshold   = np.percentile(rms, 75)
    high_energy = [float(t) for t, r in zip(rms_times, rms) if r > threshold]

    result = {
        "tempo_bpm":    round(float(tempo), 2),
        "duration":     round(duration, 3),
        "beat_times":   [round(t, 3) for t in beat_times],
        "energy": {
            "times":  [round(float(t), 3) for t in rms_times],
            "values": [round(float(v), 4) for v in rms_norm],
        },
        "onsets": {
            "times":  [round(float(t), 3) for t in onset_times],
            "values": [round(float(v), 4) for v in onset_norm],
        },
        "high_energy_times": [round(t, 3) for t in high_energy],
    }

    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nBeat data saved → {out_path}")
    print(f"  Tempo: {float(tempo):.1f} BPM")
    print(f"  {len(beat_times)} beats detected")
    print(f"  Beat interval: ~{60/float(tempo):.2f}s")
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--song", required=True)
    args = parser.parse_args()

    songs = {s["name"]: s for s in all_songs()}
    if args.song not in songs:
        print(f"ERROR: Song '{args.song}' not found.")
        sys.exit(1)

    s = songs[args.song]
    if not s["has_audio"]:
        print(f"ERROR: No audio for '{args.song}'.")
        sys.exit(1)

    out_path = TS_DIR / f"{args.song}.beats.json"
    analyze(s["audio_path"], out_path)
