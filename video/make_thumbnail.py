#!/usr/bin/env python3
"""YouTube thumbnail 1280x720 with the durations measured in the video (out/marks.json)."""
import json, os
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "out", "marks.json")))
name = "thumbnail" + ("-fr" if d.get("lang") == "fr" else "") + ".png"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.goto("file://" + os.path.join(HERE, "cards", "thumb.html"), wait_until="load")
    pg.evaluate("([a, b]) => { document.getElementById('t1').textContent = a; document.getElementById('t4').textContent = b; }", [d["t1"], d["t4"]])
    pg.wait_for_timeout(300); pg.screenshot(path=os.path.join(HERE, name)); b.close()
print(f"{name}:", d["t1"], "/", d["t4"])
