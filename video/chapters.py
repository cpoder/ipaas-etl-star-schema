#!/usr/bin/env python3
"""YouTube chapters from out/marks.json (real-time version and condensed version)."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "out", "marks.json")))
marks = {m["name"]: m["t"] for m in d["marks"]}
CH = [("intro", "Intro: the use case"), ("mapping", "ETL concepts mapped to webMethods"), ("ui_start", "Starting point: source table, empty star schema"),
      ("flows_page", "The flow services (orchestrator, batch sub-flow, time dimension)"), ("run1_click", "Run 1: sequential load, dimensions then facts"),
      ("explore_start", "Querying the star schema while it loads"), ("run1_done", "Run 1 done: reconciliation"), ("reset_done", "Reset and run 2: 4 parallel batches"),
      ("run2_done", "Run 2 done: 4x faster"), ("outro", "Wrap-up")]
def mmss(t): t = int(round(t)); return f"{t//60:02d}:{t%60:02d}"
def condensed(t):  # same cut plan as make_video.py: run1 x4, run2 x2
    cuts = [(0, marks["run1_wait_start"], 1), (marks["run1_wait_start"], marks["run1_done"], 4),
            (marks["run1_done"], marks["run2_wait_start"], 1), (marks["run2_wait_start"], marks["run2_done"], 2), (marks["run2_done"], 1e9, 1)]
    out = 0.0
    for a, b, f in cuts:
        if t <= a: break
        out += (min(t, b) - a) / f
    return out
print("Chapters (real time):")
for k, label in CH: print(f"{mmss(marks[k])} {label}")
print("\nChapters (condensed):")
for k, label in CH: print(f"{mmss(condensed(marks[k]))} {label}")
print(f"\nrun1 = {d['t1']} · run2 = {d['t4']}")
