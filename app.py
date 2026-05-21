"""
Lyric Video Generator — Web Dashboard
Opens in Chrome at http://localhost:5000
Run: python app.py
"""

import subprocess
import sys
import json
import threading
from pathlib import Path
from flask import Flask, render_template, jsonify, send_from_directory, request

app = Flask(__name__)

BASE_DIR     = Path(__file__).parent
OUTPUTS_DIR  = BASE_DIR / "outputs"
VIDEO_BG_DIR = BASE_DIR / "video_backgrounds"
BG_DIR       = BASE_DIR / "backgrounds"
SONGS_DIR    = BASE_DIR / "songs"
VENV_PYTHON  = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")

# Track running processes
running_jobs = {}

def run_script(job_id, script, args=None):
    cmd = [VENV_PYTHON, str(BASE_DIR / script)] + (args or [])
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(BASE_DIR),
    )
    running_jobs[job_id] = {"proc": proc, "log": [], "done": False, "error": False}

    def stream():
        for line in proc.stdout:
            running_jobs[job_id]["log"].append(line.rstrip())
        proc.wait()
        running_jobs[job_id]["done"] = True
        running_jobs[job_id]["error"] = proc.returncode != 0

    threading.Thread(target=stream, daemon=True).start()

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    songs = []
    for song_dir in SONGS_DIR.iterdir():
        if song_dir.is_dir():
            wav  = list(song_dir.glob("*.wav")) + list(song_dir.glob("*.mp3"))
            txt  = list(song_dir.glob("*.txt"))
            ts   = song_dir / "timestamps.json"
            songs.append({
                "name": song_dir.name,
                "has_audio": bool(wav),
                "has_lyrics": bool(txt),
                "has_timestamps": ts.exists(),
            })

    outputs = [f.name for f in OUTPUTS_DIR.glob("*.mp4")] if OUTPUTS_DIR.exists() else []
    bg_images = [f.name for f in BG_DIR.glob("*.png")] if BG_DIR.exists() else []
    bg_videos = [f.name for f in VIDEO_BG_DIR.glob("*.mp4")] if VIDEO_BG_DIR.exists() else []

    return jsonify({
        "songs": songs,
        "outputs": outputs,
        "bg_images": bg_images,
        "bg_videos": bg_videos,
    })

@app.route("/api/run/<job>", methods=["POST"])
def run_job(job):
    jobs = {
        "sync":       "sync_lyrics.py",
        "backgrounds": "generate_backgrounds.py",
        "animate":    "generate_video_backgrounds.py",
        "render":     "lyric_video.py",
    }
    if job not in jobs:
        return jsonify({"error": "Unknown job"}), 400
    if job in running_jobs and not running_jobs[job]["done"]:
        return jsonify({"error": "Job already running"}), 409

    run_script(job, jobs[job])
    return jsonify({"started": job})

@app.route("/api/log/<job_id>")
def get_log(job_id):
    if job_id not in running_jobs:
        return jsonify({"lines": [], "done": True, "error": False})
    j = running_jobs[job_id]
    return jsonify({"lines": j["log"], "done": j["done"], "error": j["error"]})

@app.route("/outputs/<filename>")
def serve_output(filename):
    return send_from_directory(str(OUTPUTS_DIR), filename)

@app.route("/backgrounds/<filename>")
def serve_background(filename):
    return send_from_directory(str(BG_DIR), filename)

@app.route("/video_backgrounds/<filename>")
def serve_video_bg(filename):
    return send_from_directory(str(VIDEO_BG_DIR), filename)

if __name__ == "__main__":
    import webbrowser
    print("Starting Lyric Video Generator dashboard...")
    print("Open http://localhost:5000 in Chrome")
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5000")).start()
    app.run(debug=False, port=5000)
