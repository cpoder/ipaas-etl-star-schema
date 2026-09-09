#!/usr/bin/env python3
"""Génère ui/flows.html : vue arborescente (façon Designer) des flow services générés par flows.py."""
import html, os, sys, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as F

LANG = "en" if "--lang" in sys.argv and sys.argv[sys.argv.index("--lang") + 1] == "en" else "fr"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ui", "flows-en.html" if LANG == "en" else "flows.html")
TR = {  # commentaires des flows (flows.py) -> anglais, pour la page publique
    "début de transaction locale (star.connections:dwh)": "start local transaction (star.connections:dwh)", "commit": "commit", "rollback": "rollback",
    "rollback si une transaction est ouverte": "rollback if a transaction is open", "nombre de lignes": "row count", "BatchInsert JDBC (un seul executeBatch)": "JDBC BatchInsert (a single executeBatch)",
    "extraction SELECT DISTINCT depuis staging.orders": "SELECT DISTINCT extraction from staging.orders", "dates distinctes de la source": "distinct dates of the source",
    "une itération par date : calcul des attributs calendaires": "one iteration per date: calendar attributes computed here", "clé yyyymmdd": "yyyymmdd key", "année": "year", "mois": "month",
    "nom du mois (fr)": "month name (locale)", "année-mois": "year-month", "semaine ISO (lundi premier jour, 4 jours minimum)": "ISO week (Monday first, 4-day rule)",
    "année ISO + semaine, ex : 2025-S01 (fr) / 2025-W01 (en)": "ISO year + week, e.g. 2025-W01", "jour du mois": "day of month", "1=lundi ... 7=dimanche": "1 = Monday ... 7 = Sunday", "nom du jour (fr)": "day name (locale)",
    "trimestre = (mois + 2) / 3": "quarter = (month + 2) / 3", "libellé 2024-T3 (fr) / 2024-Q3 (en)": "label 2024-Q3", "week-end si samedi ou dimanche": "weekend if Saturday or Sunday",
    "langue de la dimension : fr_FR / T / S par défaut, en_GB / Q / W pour une démo en anglais": "dimension locale: fr_FR / T / S by default, en_GB / Q / W for an English demo (ISO weeks)",
    "extraction du lot + lookup des clés de dimension (jointure)": "batch extraction + dimension key lookup (SQL join)", "transformation ligne à ligne": "row-by-row transformation",
    "projection vers la table de faits": "projection to the fact table", "montant = quantité x prix unitaire": "amount = quantity x unit price", "dwh.truncate_star()": "dwh.truncate_star()",
    "dwh.etl_run_log (connexion sans transaction : visible immédiatement)": "dwh.etl_run_log (non-transactional connection: visible immediately)", "ns -> ms": "ns -> ms",
    "valeurs par défaut": "default values", "langue de la dimension temporelle": "time dimension language", "ligne PIPELINE en RUNNING (visible par l UI)": "PIPELINE row set to RUNNING (visible to the UI)",
    "vidage du schéma en étoile": "truncate the star schema", "dimension temporelle": "time dimension", "dimension client": "customer dimension", "dimension commercial": "sales rep dimension", "dimension produit": "product dimension",
    "plan de lots (generate_series sur order_line_id)": "batch plan (generate_series on order_line_id)", "drapeau d arrêt (dwh.etl_control)": "stop flag (dwh.etl_control)", "arrêt demandé ?": "stop requested?",
    "arrêt demandé : lot ignoré (compatible LOOP parallèle)": "stop requested: batch skipped (parallel-LOOP safe)", "bornes du lot courant": "bounds of the current batch", "sous-flux transactionnel : un lot": "transactional sub-flow: one batch",
    "total des lignes chargées, relu en base (sûr quel que soit le parallélisme)": "total rows loaded, re-read from the database (safe with any parallelism)", "arrêté par l utilisateur ?": "stopped by the user?",
    "durée totale (ligne PIPELINE_END)": "total duration (PIPELINE_END row)", "clôture de la ligne PIPELINE": "close the PIPELINE row", "orchestrateur selon le parallélisme demandé": "orchestrator for the requested parallelism",
    "+3 s (le scheduler refuse une heure passée)": "+3 s (the scheduler refuses a past time)", "tâche unique du scheduler IS": "one-time IS scheduler task", "statut de la dernière exécution": "status of the last run",
    "refus si un pipeline tourne déjà": "refused if a pipeline is already running", "requêtes en liste blanche sur fact_sales ⋈ dimension": "whitelisted queries on fact_sales ⋈ dimension", "aperçu du contenu d une dimension": "preview of a dimension's content",
}
def tr(txt):
    if LANG != "en" or not txt: return txt
    if txt in TR: return TR[txt]
    m = re.match(r"un lot par itération, (\d+) en parallèle \(sous-flux < 5 min\)", txt)
    if m: return f"one batch per iteration, {m.group(1)} in parallel (sub-flow < 5 min)"
    for k, v in TR.items():  # préfixes (ex. "un lot par itération, 4 en parallèle ...")
        if txt.startswith(k): return v + txt[len(k):]
    return txt
ICON = {"INVOKE": ("⚙", "#4589ff"), "MAP": ("⇄", "#42be65"), "LOOP": ("↻", "#ff832b"), "BRANCH": ("⑂", "#a56eff"),
        "SEQUENCE": ("▤", "#8b98a8"), "EXIT": ("⏏", "#fa4d56"), "REPEAT": ("↺", "#ff832b"), "MAPINVOKE": ("ƒ", "#42be65")}

def short_path(p):
    return html.escape(p.split(";")[0].lstrip("/") if not p.startswith("/") or ";" not in p else "/".join(seg.split(";")[0] for seg in p.strip("/").split("/")))

def map_summary(nodes):
    c = sum(1 for n in nodes if n["type"] == "MAPCOPY"); s = sum(1 for n in nodes if n["type"] == "MAPSET"); d = sum(1 for n in nodes if n["type"] == "MAPDELETE")
    parts = []
    if LANG == "en":
        if c: parts.append(f"{c} cop{'ies' if c > 1 else 'y'}")
        if s: parts.append(f"{s} set{'s' if s > 1 else ''}")
        if d: parts.append(f"{d} drop{'s' if d > 1 else ''}")
        return ", ".join(parts)
    if c: parts.append(f"{c} copie{'s' if c > 1 else ''}")
    if s: parts.append(f"{s} affectation{'s' if s > 1 else ''}")
    if d: parts.append(f"{d} suppression{'s' if d > 1 else ''}")
    return ", ".join(parts)

def render(node, depth=0):
    t = node["type"]
    ic, col = ICON.get(t, ("•", "#8b98a8"))
    label, detail = t, ""
    if t == "INVOKE":
        label = f'<b>{html.escape(node["service"])}</b>'
        inp = [x for m in node.get("nodes", []) if m.get("mode") == "INPUT" for x in m.get("nodes", [])]
        out = [x for m in node.get("nodes", []) if m.get("mode") == "OUTPUT" for x in m.get("nodes", [])]
        li, lo = ("input: ", "output: ") if LANG == "en" else ("entrée : ", "sortie : ")
        detail = " · ".join(x for x in [(li + map_summary(inp)) if inp else "", (lo + map_summary(out)) if out else ""] if x)
    elif t == "MAP":
        label = "MAP"; detail = map_summary(node.get("nodes", []))
    elif t == "LOOP":
        label = ("LOOP over " if LANG == "en" else "LOOP sur ") + f'<code>{html.escape(node["in-array"])}</code>' + (f' → <code>{html.escape(node["out-array"])}</code>' if node.get("out-array") else "")
        if node.get("max-threads", "1") != "1": detail = f'{node["max-threads"]} ' + ("parallel iterations" if LANG == "en" else "itérations en parallèle")
    elif t == "BRANCH":
        label = ("BRANCH on <code>" if LANG == "en" else "BRANCH sur <code>") + html.escape(node.get("switch", "expressions")) + "</code>"
    elif t == "SEQUENCE":
        label = {"TRY": "TRY", "CATCH": "CATCH"}.get(node.get("form"), "SEQUENCE") + (f' <span class="lbl">{html.escape(str(node["label"]))}</span>' if "label" in node else "")
    elif t == "EXIT":
        label = f'EXIT {html.escape(node["from"])} / {html.escape(node["signal"])}'; detail = html.escape(node.get("failure-message", ""))
    comment = html.escape(tr(node.get("comment", "")))
    children = [n for n in node.get("nodes", []) if n["type"] not in ("MAPCOPY", "MAPSET", "MAPDELETE") and not (t == "INVOKE" and n["type"] == "MAP")]
    h = f'<div class="step d{min(depth, 6)}"><span class="ic" style="color:{col}">{ic}</span><span class="lb">{label}</span>'
    if detail: h += f'<span class="dt">{detail}</span>'
    if comment: h += f'<span class="cm">— {comment}</span>'
    h += "</div>"
    for c in children:
        h += render(c, depth + 1)
    return h

def sig_fields(sig):
    return ", ".join(f'{f["field_name"]}{"[]" if f.get("field_dim") == "1" else ""}' for f in sig.get("rec_fields", [])) or "—"

m = None
class _M:  # objectToString : nom réel de la sortie sur cet IS (voir flows.objtostring_output)
    def call(self, *a, **k): return '{"node":{"svc_sig":{"sig_out":{"rec_fields":[{"field_name":"string"}]}}}}'
services = [F.BEGIN_STEP, F.log_step("string"), F.TRUNCATE_STAR,
            F.dim_loader("loadCustomers", "selectCustomers", "insertCustomers", "customers", "Dimension client"),
            F.dim_loader("loadSalesreps", "selectSalesreps", "insertSalesreps", "salesreps", "Dimension commercial"),
            F.dim_loader("loadProducts", "selectProducts", "insertProducts", "products", "Dimension produit"),
            F.LOAD_DATES, F.LOAD_FACT_CHUNK, F.run_pipeline("runPipeline", 1), F.run_pipeline("runPipelineX4", 4), F.START_PIPELINE,
            F.API_STATUS, F.API_START, F.API_ANALYZE, F.API_DIMENSION]
ORDER = ["star.etl:runPipeline", "star.etl.steps:loadFactChunk", "star.etl.steps:loadDates", "star.etl.steps:loadCustomers",
         "star.etl.steps:logStep", "star.etl:startPipeline", "star.etl:runPipelineX4", "star.api:start", "star.api:analyze"]
by = {s["node_nsName"]: s for s in services}
SVC_EN = {
    "star.etl:runPipeline": "ETL orchestrator (1 fact batch at a time): truncates the star schema, loads the 4 dimensions (including the computed time dimension), then the fact table by logged transactional batches; a stop flag is checked before each batch.",
    "star.etl:runPipelineX4": "ETL orchestrator (4 fact batches in parallel): same flow with MAX-THREADS = 4 on the LOOP.",
    "star.etl.steps:loadFactChunk": "Transactional sub-flow: loads order lines in ]fromId, toId] into dwh.fact_sales (extraction + SQL lookup, amount computed in the flow, BatchInsert). Rollback on error.",
    "star.etl.steps:loadDates": "Time dimension: for each distinct date of staging.orders, the flow computes the calendar attributes, then BatchInsert into dwh.dim_date. One transaction.",
    "star.etl.steps:loadCustomers": "Customer dimension: SELECT DISTINCT then BatchInsert into dwh.dim_customer. One transaction.",
    "star.etl.steps:loadSalesreps": "Sales rep dimension: SELECT DISTINCT then BatchInsert into dwh.dim_salesrep. One transaction.",
    "star.etl.steps:loadProducts": "Product dimension: SELECT DISTINCT then BatchInsert into dwh.dim_product. One transaction.",
    "star.etl.steps:logStep": "Logs a step into dwh.etl_run_log with its duration (ms) computed by the flow.",
    "star.etl.steps:beginStep": "Step start timestamp (readable date + nanosecond counter).",
    "star.etl.steps:truncateStar": "Empties the star schema (facts + dimensions, sequences restarted).",
    "star.etl:startPipeline": "Asynchronous start: schedules the orchestrator (1, 2 or 4 parallel batches) in 3 seconds through the IS scheduler.",
    "star.api:start": "Starts the demo (double-start guard): re-arms the stop flag, then schedules the pipeline.",
    "star.api:status": "Demo state for the UI (JSON): volumes, log of the last run, last transformed rows, next source rows.",
    "star.api:analyze": "Dimension analysis for the UI: axis (year, quarter, month, week, weekday, segment, department, customer, region, sales rep, category, brand, product) -> revenue, quantities, lines, average line amount.",
    "star.api:dimension": "Preview of the first 12 rows of a dimension table (date, customer, salesrep, product).",
}
parts = []
for name in ORDER + [n for n in by if n not in ORDER]:
    s = by[name]
    parts.append(f'''<section class="svc" id="{html.escape(name)}"><h2>{html.escape(name)}</h2><p class="cm">{html.escape(SVC_EN.get(name, s.get("node_comment", "")) if LANG == "en" else s.get("node_comment", ""))}</p>
<p class="sig">{"input" if LANG == "en" else "entrée"} : <code>{sig_fields(s["svc_sig"]["sig_in"])}</code> · {"output" if LANG == "en" else "sortie"} : <code>{sig_fields(s["svc_sig"]["sig_out"])}</code></p>
{"".join(render(n) for n in s["flow"]["nodes"])}</section>''')
page = f'''<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>StarSchemaETL · flow services</title>
<style>
body{{margin:0;background:#0f1419;color:#e6edf3;font:14px/1.5 "IBM Plex Sans","Segoe UI",system-ui,sans-serif}}
header{{padding:14px 24px;border-bottom:1px solid #2a3542;background:#161c24;position:sticky;top:0}} header h1{{margin:0;font-size:18px}} header small{{color:#8b98a8;margin-left:10px}}
main{{padding:16px 24px;display:grid;gap:14px}} .svc{{background:#161c24;border:1px solid #2a3542;border-radius:8px;padding:12px 16px}}
.svc h2{{margin:0 0 4px;font-size:15px;color:#33b1ff}} .sig{{color:#8b98a8;font-size:12px;margin:0 0 8px}} code{{color:#f1c21b;font-size:12px}}
.step{{padding:2px 0 2px 0;border-left:1px solid #2a3542;margin-left:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.d0{{padding-left:8px;border-left:none;margin-left:0}} .d1{{padding-left:26px}} .d2{{padding-left:52px}} .d3{{padding-left:78px}} .d4{{padding-left:104px}} .d5{{padding-left:130px}} .d6{{padding-left:156px}}
.ic{{display:inline-block;width:18px;font-weight:700}} .lb{{margin-right:8px}} .dt{{color:#8b98a8;font-size:12px;margin-right:8px}} .cm{{color:#8b98a8;font-style:italic;font-size:12px}} .lbl{{color:#f1c21b}}
nav{{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;margin-top:6px}} nav a{{color:#8b98a8;text-decoration:none}} nav a:hover{{color:#33b1ff}}
</style></head><body><header><h1>{"StarSchemaETL package · flow services" if LANG == "en" else "Package StarSchemaETL · flow services"} <small>{"step tree exactly as deployed on the Integration Server (generated by wm/flowdoc.py)" if LANG == "en" else "arbre des étapes tel que déployé sur l'Integration Server (généré par wm/flowdoc.py)"}</small></h1>
<nav>{" ".join(f'<a href="#{html.escape(n)}">{html.escape(n.split(":")[1])}</a>' for n in ORDER + [n for n in by if n not in ORDER])}</nav></header>
<main>{"".join(parts)}</main></body></html>'''
open(OUT, "w", encoding="utf-8").write(page)
print("écrit", OUT, len(page), "octets,", len(parts), "services")

# ---- version markdown (docs/flows-trees.md) : mêmes arbres, en texte
import re as _re
def md_node(node, depth=0):
    t = node["type"]; ind = "  " * depth
    if t == "INVOKE":
        inp = [x for m in node.get("nodes", []) if m.get("mode") == "INPUT" for x in m.get("nodes", [])]
        out = [x for m in node.get("nodes", []) if m.get("mode") == "OUTPUT" for x in m.get("nodes", [])]
        det = " · ".join(x for x in [("entrée : " + map_summary(inp)) if inp else "", ("sortie : " + map_summary(out)) if out else ""] if x)
        line = f"INVOKE `{node['service']}`" + (f" ({det})" if det else "")
    elif t == "MAP": line = "MAP " + map_summary(node.get("nodes", []))
    elif t == "LOOP": line = f"LOOP sur `{node['in-array']}`" + (f" → `{node['out-array']}`" if node.get("out-array") else "") + (f" · {node['max-threads']} itérations en parallèle" if node.get("max-threads", "1") != "1" else "")
    elif t == "BRANCH": line = "BRANCH sur `" + node.get("switch", "expressions") + "`"
    elif t == "SEQUENCE": line = {"TRY": "TRY", "CATCH": "CATCH"}.get(node.get("form"), "SEQUENCE") + (f" [{node['label']}]" if "label" in node else "")
    elif t == "EXIT": line = f"EXIT {node['from']} / {node['signal']}" + (f" « {node['failure-message']} »" if node.get("failure-message") else "")
    else: line = t
    if node.get("comment"): line += f" — *{node['comment']}*"
    md = f"{ind}- {line}\n"
    for c in [n for n in node.get("nodes", []) if n["type"] not in ("MAPCOPY", "MAPSET", "MAPDELETE") and not (t == "INVOKE" and n["type"] == "MAP")]:
        md += md_node(c, depth + 1)
    return md
MD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "flows-trees-en.md" if LANG == "en" else "flows-trees.md")
lines = ["# Arbres des flow services (générés par wm/flowdoc.py)\n", "Chaque étape telle que déployée sur l'Integration Server (package StarSchemaETL).\n"]
for name in ORDER + [n for n in by if n not in ORDER]:
    s_ = by[name]
    lines.append(f"\n## {name}\n\n{s_.get('node_comment', '')}\n\n*Entrée* : `{sig_fields(s_['svc_sig']['sig_in'])}` · *Sortie* : `{sig_fields(s_['svc_sig']['sig_out'])}`\n\n")
    lines.append("".join(md_node(n) for n in s_["flow"]["nodes"]))
open(MD, "w", encoding="utf-8").write("".join(lines))
print("écrit", MD)
