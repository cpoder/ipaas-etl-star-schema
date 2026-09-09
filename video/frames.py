#!/usr/bin/env python3
"""Extracts one frame per chapter (+ offset) from the real-time mp4 for visual checks: out/frame_<chapter>.png"""
import json, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "out", "marks.json")))
marks = {m["name"]: m["t"] for m in d["marks"]}
src = os.path.join(HERE, "ipaas-etl-star-schema-demo" + ("-fr" if d.get("lang") == "fr" else "") + ".mp4")
for name, off in [("intro", 3), ("mapping", 3), ("ui_start", 4), ("flows_page", 9), ("run1_running", 4), ("explore_start", 8), ("run1_done", 4), ("run2_running", 12), ("run2_done", 4), ("outro", 3)]:
    t = marks[name] + off
    out = os.path.join(HERE, "out", f"frame_{name}.png")
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", out])
    print(f"{name:14s} t={t:6.1f}s -> {os.path.basename(out)}")
