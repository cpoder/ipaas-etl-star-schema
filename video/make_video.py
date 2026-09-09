#!/usr/bin/env python3
"""Memory-frugal ffmpeg editing: out/<base>.webm -> <base>.mp4 (real time) and <base>-condensed.mp4
(waiting phases sped up: run1 x4, run2 x2, with an on-screen label), from the time marks of record_demo.py.
Each segment is encoded separately (a single decode at a time, no buffering of the input), then the
segments are concatenated without re-encoding."""
import json, os, subprocess, glob, tempfile, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
MJ = json.load(open(os.path.join(OUT, "marks.json")))
FR = MJ.get("lang") == "fr"
BASE = "ipaas-etl-star-schema-demo" + ("-fr" if FR else "")
SRC = os.path.join(OUT, BASE + ".webm")
marks = {m["name"]: m["t"] for m in MJ["marks"]}
FONT = next(iter(glob.glob("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")), None)
ENC = ["-c:v", "libx264", "-preset", "medium", "-crf", "22", "-pix_fmt", "yuv420p", "-r", "30", "-threads", "4"]
LABEL = "accéléré x{f}" if FR else "sped up x{f}"

def duration(path):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).decode().strip())

def run(cmd):
    print(" ".join(cmd)[:220], flush=True); subprocess.check_call(cmd)

# 1. real-time version (a single pass, no filter)
real = os.path.join(HERE, BASE + ".mp4")
run(["ffmpeg", "-y", "-loglevel", "error", "-i", SRC] + ENC + ["-movflags", "+faststart", real])
total = duration(real)
print(f"real time: {total:.1f} s")
# 2. condensed version: segments encoded one by one (-ss/-to before -i: cut while reading, constant memory)
cuts = [(0, marks["run1_wait_start"], 1), (marks["run1_wait_start"], marks["run1_done"], 4),
        (marks["run1_done"], marks["run2_wait_start"], 1), (marks["run2_wait_start"], marks["run2_done"], 2), (marks["run2_done"], total, 1)]
tmp = tempfile.mkdtemp(prefix="montage-", dir=OUT)
parts = []
try:
    for i, (a, b, f) in enumerate(cuts):
        if b - a < 0.2:
            continue
        seg = os.path.join(tmp, f"seg{i}.mp4")
        vf = f"setpts=PTS/{f}"
        if f > 1 and FONT:
            vf += f",drawtext=fontfile={FONT}:text='{LABEL.format(f=f)}':fontsize=40:fontcolor=white:x=w-tw-40:y=40:box=1:boxcolor=0x0b0f14@0.75:boxborderw=16"
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.2f}", "-to", f"{b:.2f}", "-i", real, "-vf", vf] + ENC + [seg])
        parts.append(seg)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    cond = os.path.join(HERE, BASE + "-condensed.mp4")
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-movflags", "+faststart", cond])
finally:
    shutil.rmtree(tmp, ignore_errors=True)
for f in (BASE + ".mp4", BASE + "-condensed.mp4"):
    p = os.path.join(HERE, f); print(f"{f}: {duration(p):.0f} s, {os.path.getsize(p)/1e6:.1f} MB")
