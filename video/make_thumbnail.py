#!/usr/bin/env python3
"""Vignette YouTube 1280x720 avec les durées mesurées dans la vidéo (out/marks.json)."""
import json, os
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__))
d = json.load(open(os.path.join(HERE, "out", "marks.json")))
en = lambda t: t.replace(" min ", " min ").replace(" s", " s")
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1280, "height": 720})
    pg.goto("file://" + os.path.join(HERE, "cards", "thumb.html"), wait_until="load")
    pg.evaluate("([a, b]) => { document.getElementById('t1').textContent = a; document.getElementById('t4').textContent = b; }", [en(d["t1"]), en(d["t4"])])
    pg.wait_for_timeout(300); pg.screenshot(path=os.path.join(HERE, "thumbnail" + ("-en" if d.get("lang") == "en" else "") + ".png")); b.close()
print("thumbnail.png :", d["t1"], "/", d["t4"])
