#!/usr/bin/env python3
"""Records the demo video (Playwright + Chromium): title cards, the real UI, captions.

Output: video/out/ipaas-etl-star-schema-demo.webm + time marks (marks.json) for the ffmpeg editing (make_video.py).
Usage: python3 record_demo.py [--fast] [--lang fr]
  --fast     batches of 50,000 rows and 4 parallel batches from the first run (for testing)
  --lang fr  French captions, French title cards (*-fr.html) and French UI (?lang=fr); English by default
"""
import json, os, sys, time
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
CARDS = os.path.join(HERE, "cards")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
URL = "http://localhost:5555/StarSchemaETL/"
W, H = 1920, 1200          # video frame
ZOOM = 0.8                 # page zoomed out: the whole screen visible without scrolling
FAST = "--fast" in sys.argv
LANG = "fr" if "--lang" in sys.argv and sys.argv[sys.argv.index("--lang") + 1] == "fr" else "en"
SUF = "-fr" if LANG == "fr" else ""
Q = "?lang=fr" if LANG == "fr" else ""
C = {  # captions: (French, English)
 "start": ("Situation de départ : 999 343 lignes de commandes dans staging.orders, schéma en étoile vide", "Starting point: 999,343 order lines in staging.orders, an empty star schema"),
 "flat": ("Une seule table « classique » : commande, client, commercial, produit, quantité, prix unitaire", "A single flat table: order, customer, sales rep, product, quantity, unit price"),
 "flows": ("Les flow services du package StarSchemaETL, tels que déployés sur l'Integration Server", "The flow services of the StarSchemaETL package, exactly as deployed on the Integration Server"),
 "orch": ("runPipeline : vidage, 4 dimensions, puis la table de faits par lots transactionnels journalisés", "runPipeline: truncate, 4 dimensions, then the fact table by logged transactional batches"),
 "chunk": ("loadFactChunk : extraction + lookup des clés par jointure, LOOP ligne à ligne (montant = quantité × prix), BatchInsert, commit", "loadFactChunk: extraction + key lookup by join, row-by-row LOOP (amount = quantity × price), BatchInsert, commit"),
 "dates": ("loadDates : la dimension temporelle est calculée par le flow (clé, trimestre, semaine, libellés français, week-end)", "loadDates: the time dimension is computed by the flow (key, quarter, ISO week, names, weekend)"),
 "launch": ("Lancement : lots de 20 000 lignes, un lot à la fois — le scheduler de l'IS démarre le pipeline", "Start: batches of 20,000 rows, one batch at a time — the IS scheduler kicks off the pipeline"),
 "dims": ("Les 4 dimensions sont chargées en moins de deux secondes, avec leurs clés de substitution", "The 4 dimensions are loaded in under two seconds, with their surrogate keys"),
 "facts": ("Puis les faits : chaque lot est un sous-flux avec sa transaction (start / commit / rollback) et sa ligne de journal", "Then the facts: each batch is a sub-flow with its own transaction (start / commit / rollback) and its log row"),
 "kpi": ("Débit, temps écoulé et temps restant sont calculés à partir du journal écrit par les flows", "Throughput, elapsed and remaining time come from the log written by the flows"),
 "tables": ("En bas : les prochaines lignes source et les dernières lignes chargées, clés de substitution et montant calculé", "Below: the next source rows and the last rows loaded, with surrogate keys and the computed amount"),
 "region": ("Le schéma en étoile est déjà interrogeable pendant le chargement : chiffre d'affaires par région commerciale", "The star schema can be queried while it loads: revenue by sales region"),
 "category": ("Par catégorie de produit…", "By product category…"),
 "segment": ("… en quantités, par segment de clientèle", "… in quantities, by customer segment"),
 "dimcontent": ("Le contenu de chaque dimension : dim_customer, dim_date…", "The content of each dimension: dim_customer, dim_date…"),
 "week": ("La dimension temporelle calculée par le flow : par année, trimestre, mois, semaine ISO, jour…", "The time dimension computed by the flow: by year, quarter, month, ISO week, day…"),
 "month": ("Chiffre d'affaires par mois : les agrégats se complètent au fil des lots", "Revenue by month: the aggregates build up batch after batch"),
 "done1": ("Terminé : 999 343 faits chargés en {t} — réconciliation exacte avec la source (mêmes lignes, même montant)", "Done: 999,343 facts loaded in {t} — exact reconciliation with the source (same rows, same amount)"),
 "reset": ("Réinitialisation en un clic : schéma en étoile vidé, journal purgé", "One-click reset: star schema emptied, log purged"),
 "par": ("Même chargement avec 4 lots en parallèle : la LOOP native de l'IS exécute 4 sous-flux transactionnels simultanés", "Same load with 4 batches in parallel: the native IS LOOP runs 4 transactional sub-flows at once"),
 "par2": ("Quatre lots à la fois, chacun sur sa connexion et sa transaction — sans modifier la logique du flow", "Four batches at a time, each on its own connection and transaction — without touching the flow logic"),
 "done2": ("Terminé en {t4} avec 4 lots en parallèle, contre {t1} en séquentiel — même réconciliation exacte", "Done in {t4} with 4 parallel batches, versus {t1} sequentially — same exact reconciliation"),
 "analysis": ("Et l'analyse par dimension sur le million de faits reste instantanée", "And dimension-level analysis on the million facts stays instantaneous"),
}
def cap(k, **kw): return C[k][1 if LANG == "en" else 0].format(**kw)

CAPTION_JS = """
(text) => {
  let c = document.getElementById('demoCaption');
  if (!c) {
    c = document.createElement('div'); c.id = 'demoCaption';
    c.style.cssText = 'position:fixed;left:50%;bottom:26px;transform:translateX(-50%);max-width:1500px;padding:16px 30px;zoom:1.25;'
      + 'background:rgba(8,12,18,.92);color:#fff;font:600 24px/1.35 "IBM Plex Sans","Segoe UI",system-ui,sans-serif;'
      + 'border:1px solid #4589ff;border-left:8px solid #4589ff;border-radius:10px;z-index:99999;box-shadow:0 8px 30px rgba(0,0,0,.5);'
      + 'transition:opacity .35s;text-align:center;';
    document.body.appendChild(c);
  }
  if (!text) { c.style.opacity = '0'; return; }
  c.style.opacity = '0'; setTimeout(() => { c.textContent = text; c.style.opacity = '1'; }, 200);
}
"""
HILITE_JS = """
(sel) => { document.querySelectorAll(sel).forEach(el => {
  el.style.transition = 'box-shadow .4s'; el.style.boxShadow = '0 0 0 3px #f1c21b, 0 0 28px rgba(241,194,27,.6)';
  setTimeout(() => { el.style.boxShadow = ''; }, 3200); }); }
"""

class Recorder:
    def __init__(self, page):
        self.page = page; self.t0 = time.monotonic(); self.marks = []
    def mark(self, name):
        self.marks.append({"name": name, "t": round(time.monotonic() - self.t0, 2)}); print(f"  [{self.marks[-1]['t']:7.1f}s] {name}", flush=True)
    def wait(self, s): self.page.wait_for_timeout(int(s * 1000))
    def caption(self, text, s=None):
        self.page.evaluate(CAPTION_JS, text)
        if s: self.wait(s)
    def hilite(self, sel): self.page.evaluate(HILITE_JS, sel)
    def scroll(self, y): self.page.evaluate("y => window.scrollTo({top: y, behavior: 'smooth'})", y); self.wait(1.2)
    def goto(self, url):
        self.page.goto(url, wait_until="load"); self.page.evaluate(f"document.documentElement.style.zoom = '{ZOOM}'")
    def card(self, name, s, fill=None):
        self.page.goto(f"file://{CARDS}/{name}{SUF}.html", wait_until="load")
        self.page.evaluate("document.body.style.zoom = '1.2'")
        if fill:
            for k, v in fill.items(): self.page.evaluate("([k, v]) => { const e = document.getElementById(k); if (e) e.textContent = v; }", [k, v])
        self.wait(s)
    def pill(self): return self.page.locator("#pill").inner_text()
    def wait_pill(self, wanted, timeout):
        for _ in range(int(timeout)):
            if self.pill() in wanted: return self.pill()
            self.wait(1)
        return self.pill()
    def elapsed_text(self): return self.page.locator("#kElapsed").inner_text()

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--force-color-profile=srgb", "--hide-scrollbars"])
        ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=OUT, record_video_size={"width": W, "height": H},
                                  http_credentials={"username": "Administrator", "password": "manage"}, device_scale_factor=1)
        page = ctx.new_page(); page.on("dialog", lambda d: d.accept())
        r = Recorder(page)
        # ---- 1. title cards
        r.mark("intro"); r.card("intro", 9)
        r.mark("mapping"); r.card("flows", 10)
        # ---- 2. starting point
        r.goto(URL + "index.html" + Q); r.wait(3)
        assert "INJOIGNABLE" not in r.pill() and "UNREACHABLE" not in r.pill(), "the UI cannot reach the IS: " + r.pill()
        r.mark("ui_start")
        r.caption(cap("start"), 1); r.hilite(".kpi:first-child, #star"); r.wait(6)
        r.caption(cap("flat"), 1); r.hilite("#src"); r.wait(6)
        # ---- 3. the flows
        r.mark("flows_page")
        r.goto(URL + "flows.html"); r.wait(1)
        r.caption(cap("flows"), 5)
        r.caption(cap("orch"), 1); r.scroll(120); r.wait(6)
        r.caption(cap("chunk"), 1)
        page.locator("#star\\.etl\\.steps\\:loadFactChunk").scroll_into_view_if_needed(); r.wait(7)
        r.caption(cap("dates"), 1)
        page.locator("#star\\.etl\\.steps\\:loadDates").scroll_into_view_if_needed(); r.wait(6)
        # ---- 4. sequential run
        r.goto(URL + "index.html" + Q); r.wait(2.5)
        page.select_option("#chunk", "50000" if FAST else "20000"); page.select_option("#threads", "4" if FAST else "1")
        r.caption(cap("launch"), 1); r.hilite("#btnStart"); r.wait(2)
        page.click("#btnStart"); r.mark("run1_click")
        r.wait_pill(("RUNNING",), 30); r.mark("run1_running")
        r.caption(cap("dims"), 1); r.hilite("#bDate, #bCust, #bRep, #bProd"); r.wait(6)
        r.caption(cap("facts"), 1); r.hilite("#log"); r.wait(7)
        r.caption(cap("kpi"), 1); r.hilite(".kpi:nth-child(3), .kpi:nth-child(4)"); r.wait(6)
        r.caption(cap("tables"), 1); r.hilite("#src, #fact"); r.wait(7)
        r.scroll(700); r.mark("explore_start")
        r.caption(cap("region"), 1); r.hilite("#an")
        page.select_option("#axis", "anRegion"); r.wait(6)
        r.caption(cap("category"), 1); page.select_option("#axis", "anCategory"); r.wait(5)
        r.caption(cap("segment"), 1); page.select_option("#measure", "quantity"); page.select_option("#axis", "anSegment"); r.wait(5)
        r.caption(cap("dimcontent"), 1); r.hilite("#dim"); page.click(".tabs button[data-dim=customer]"); r.wait(4)
        page.click(".tabs button[data-dim=date]"); r.wait(4)
        page.select_option("#measure", "amount"); page.select_option("#axis", "anWeek"); r.caption(cap("week"), 1); r.wait(5)
        page.select_option("#axis", "anMonth"); r.caption(cap("month"), 1); r.hilite("#chart"); r.wait(6)
        r.scroll(0); r.caption("", 0); r.mark("run1_wait_start")
        st = r.wait_pill(("DONE", "FAILED", "STOPPED"), 240); r.mark("run1_done"); r.wait(1.5)
        t1 = r.elapsed_text()
        r.caption(cap("done1", t=t1), 1); r.hilite(".kpi:nth-child(2), .kpi:nth-child(5)"); r.wait(8)
        # ---- 5. reset, then parallelism
        r.caption(cap("reset"), 1); page.click("#btnReset"); r.wait(4)
        r.mark("reset_done")
        page.select_option("#threads", "4"); page.select_option("#chunk", "20000")
        r.caption(cap("par"), 1); r.hilite("#threads"); r.wait(3)
        page.click("#btnStart"); r.mark("run2_click"); r.wait_pill(("RUNNING",), 30); r.mark("run2_running")
        r.caption(cap("par2"), 8)
        r.caption("", 0); r.mark("run2_wait_start")
        r.wait_pill(("DONE", "FAILED", "STOPPED"), 240); r.mark("run2_done"); r.wait(1.5)
        t4 = r.elapsed_text()
        r.caption(cap("done2", t1=t1, t4=t4), 1); r.hilite(".kpi:nth-child(4)"); r.wait(8)
        r.scroll(700); r.caption(cap("analysis"), 1); page.select_option("#axis", "anSalesrep"); r.hilite("#an"); r.wait(5)
        r.caption("", 0); r.wait(0.5)
        # ---- 6. wrap-up
        r.mark("outro"); r.card("outro", 12, fill=({"t1": f"1 batch at a time: {t1}", "t4": f"4 parallel batches: {t4}"} if LANG == "en" else {"t1": f"1 lot à la fois : {t1}", "t4": f"4 lots en parallèle : {t4}"}))
        r.mark("end")
        video = page.video; ctx.close()
        src = video.path(); dst = os.path.join(OUT, f"ipaas-etl-star-schema-demo{SUF}.webm"); os.replace(src, dst)
        json.dump({"marks": r.marks, "t1": t1, "t4": t4, "lang": LANG, "size": [W, H]}, open(os.path.join(OUT, "marks.json"), "w"), indent=1)
        print("VIDEO:", dst, os.path.getsize(dst), "bytes"); browser.close()

if __name__ == "__main__":
    main()
