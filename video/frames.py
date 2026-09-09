#!/usr/bin/env python3
"""Extrait une image par chapitre (+2 s) du mp4 temps réel pour contrôle visuel : out/frame_<chapitre>.png"""
import json, os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "out", "marks.json")))
marks = {m["name"]: m["t"] for m in d["marks"]}
src = os.path.join(HERE, "ipaas-etl-star-schema-demo" + ("-en" if d.get("lang") == "en" else "") + ".mp4")
for name, off in [("intro", 3), ("mapping", 3), ("ui_start", 4), ("flows_page", 9), ("run1_running", 4), ("explore_start", 8), ("run1_done", 4), ("run2_running", 12), ("run2_done", 4), ("outro", 3)]:
    t = marks[name] + off
    out = os.path.join(HERE, "out", f"frame_{name}.png")
    subprocess.check_call(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", src, "-frames:v", "1", out])
    print(f"{name:14s} t={t:6.1f}s -> {os.path.basename(out)}")
