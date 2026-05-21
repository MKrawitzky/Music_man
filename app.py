"""
Lyric Video Generator — Web Dashboard
Opens in Chrome at http://localhost:5000
Run: python app.py  (or double-click start.bat)
"""

import threading
import subprocess
from pathlib import Path
from flask import Flask, render_template, jsonify, send_from_directory, request
from config import (
    BASE_DIR, LYRICS_DIR, AUDIO_DIR, OUTPUTS_DIR,
    BG_DIR, VIDEO_BG_DIR, WAN_DIR, CLIPS_DIR, TS_DIR, all_songs
)

app = Flask(__name__)
VENV_PYTHON = str(BASE_DIR / ".venv" / "Scripts" / "python.exe")

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

# ── API ───────────────────────────────────────────────────────────────────────
@app.route("/api/songs")
def api_songs():
    songs = all_songs()
    return jsonify([{
        "name":           s["name"],
        "has_audio":      s["has_audio"],
        "has_timestamps": s["has_timestamps"],
        "has_output":     s["has_output"],
        "audio_path":     str(s["audio_path"]) if s["audio_path"] else None,
    } for s in songs])

@app.route("/api/run/<job>", methods=["POST"])
def run_job(job):
    song = request.json.get("song") if request.is_json else None

    jobs = {
        "sync":        "sync_lyrics.py",
        "backgrounds": "generate_backgrounds.py",
        "animate":     "generate_video_backgrounds.py",
        "wan":         "generate_wan_videos.py",
        "render":      "lyric_video.py",
    }
    if job not in jobs:
        return jsonify({"error": "Unknown job"}), 400

    job_id = f"{job}_{song}" if song else job
    if job_id in running_jobs and not running_jobs[job_id]["done"]:
        return jsonify({"error": "Job already running"}), 409

    args = ["--song", song] if song else []
    run_script(job_id, jobs[job], args)
    return jsonify({"started": job_id})

@app.route("/api/log/<path:job_id>")
def get_log(job_id):
    if job_id not in running_jobs:
        return jsonify({"lines": [], "done": True, "error": False})
    j = running_jobs[job_id]
    return jsonify({"lines": j["log"], "done": j["done"], "error": j["error"]})

@app.route("/api/outputs")
def api_outputs():
    files = [f.name for f in OUTPUTS_DIR.glob("*.mp4")] if OUTPUTS_DIR.exists() else []
    return jsonify(files)

@app.route("/api/backgrounds")
def api_backgrounds():
    images  = [f.name for f in BG_DIR.glob("*.png")]       if BG_DIR.exists()       else []
    videos  = [f.name for f in VIDEO_BG_DIR.glob("*.mp4")] if VIDEO_BG_DIR.exists() else []
    wan     = [f.name for f in WAN_DIR.glob("*.mp4")]       if WAN_DIR.exists()      else []
    clips   = [f.name for f in CLIPS_DIR.glob("*.mp4")]     if CLIPS_DIR.exists()    else []
    return jsonify({"images": images, "videos": videos, "wan": wan, "clips": clips})

@app.route("/wan_videos/<filename>")
def serve_wan(filename):
    return send_from_directory(str(WAN_DIR), filename)

@app.route("/clips/<filename>")
def serve_clip(filename):
    return send_from_directory(str(CLIPS_DIR), filename)

# ── Static file serving ───────────────────────────────────────────────────────
@app.route("/outputs/<filename>")
def serve_output(filename):
    return send_from_directory(str(OUTPUTS_DIR), filename)

@app.route("/backgrounds/<filename>")
def serve_bg(filename):
    return send_from_directory(str(BG_DIR), filename)

@app.route("/video_backgrounds/<filename>")
def serve_vid_bg(filename):
    return send_from_directory(str(VIDEO_BG_DIR), filename)

@app.route("/")
def index():
    return render_template("index.html")

# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import webbrowser
    print(f"Lyrics folder : {LYRICS_DIR}")
    print(f"Audio folder  : {AUDIO_DIR}")
    print(f"Found {len(all_songs())} songs")
    print("\nStarting dashboard at http://localhost:5000")
    threading.Timer(1.2, lambda: webbrowser.open("http://localhost:5001")).start()
    app.run(debug=False, port=5001)
