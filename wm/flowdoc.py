#!/usr/bin/env python3
"""Generates ui/flows.html (Designer-like tree view of the flow services built by flows.py) and docs/flows-trees.md
(same trees as Markdown). The comments shown are the ones deployed on the Integration Server."""
import html, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flows as F

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "ui", "flows.html")
MD = os.path.join(HERE, "..", "docs", "flows-trees.md")
ICON = {"INVOKE": ("⚙", "#4589ff"), "MAP": ("⇄", "#42be65"), "LOOP": ("↻", "#ff832b"), "BRANCH": ("⑂", "#a56eff"),
        "SEQUENCE": ("▤", "#8b98a8"), "EXIT": ("⏏", "#fa4d56"), "REPEAT": ("↺", "#ff832b"), "MAPINVOKE": ("ƒ", "#42be65")}

def short_path(p):
    return html.escape(p.split(";")[0].lstrip("/") if not p.startswith("/") or ";" not in p else "/".join(seg.split(";")[0] for seg in p.strip("/").split("/")))

def map_summary(nodes):
    c = sum(1 for n in nodes if n["type"] == "MAPCOPY"); s = sum(1 for n in nodes if n["type"] == "MAPSET"); d = sum(1 for n in nodes if n["type"] == "MAPDELETE")
    parts = []
    if c: parts.append(f"{c} cop{'ies' if c > 1 else 'y'}")
    if s: parts.append(f"{s} set{'s' if s > 1 else ''}")
    if d: parts.append(f"{d} drop{'s' if d > 1 else ''}")
    return ", ".join(parts)

def invoke_detail(node, sep=" · "):
    inp = [x for m in node.get("nodes", []) if m.get("mode") == "INPUT" for x in m.get("nodes", [])]
    out = [x for m in node.get("nodes", []) if m.get("mode") == "OUTPUT" for x in m.get("nodes", [])]
    return sep.join(x for x in [("input: " + map_summary(inp)) if inp else "", ("output: " + map_summary(out)) if out else ""] if x)

def children_of(node):
    t = node["type"]
    return [n for n in node.get("nodes", []) if n["type"] not in ("MAPCOPY", "MAPSET", "MAPDELETE") and not (t == "INVOKE" and n["type"] == "MAP")]

def render(node, depth=0):
    t = node["type"]
    ic, col = ICON.get(t, ("•", "#8b98a8"))
    label, detail = t, ""
    if t == "INVOKE":
        label = f'<b>{html.escape(node["service"])}</b>'; detail = invoke_detail(node)
    elif t == "MAP":
        label = "MAP"; detail = map_summary(node.get("nodes", []))
    elif t == "LOOP":
        label = "LOOP over " + f'<code>{html.escape(node["in-array"])}</code>' + (f' → <code>{html.escape(node["out-array"])}</code>' if node.get("out-array") else "")
        if node.get("max-threads", "1") != "1": detail = f'{node["max-threads"]} parallel iterations'
    elif t == "BRANCH":
        label = "BRANCH on <code>" + html.escape(node.get("switch", "expressions")) + "</code>"
    elif t == "SEQUENCE":
        label = {"TRY": "TRY", "CATCH": "CATCH"}.get(node.get("form"), "SEQUENCE") + (f' <span class="lbl">{html.escape(str(node["label"]))}</span>' if "label" in node else "")
    elif t == "EXIT":
        label = f'EXIT {html.escape(node["from"])} / {html.escape(node["signal"])}'; detail = html.escape(node.get("failure-message", ""))
    comment = html.escape(node.get("comment", ""))
    h = f'<div class="step d{min(depth, 6)}"><span class="ic" style="color:{col}">{ic}</span><span class="lb">{label}</span>'
    if detail: h += f'<span class="dt">{detail}</span>'
    if comment: h += f'<span class="cm">— {comment}</span>'
    h += "</div>"
    for c in children_of(node):
        h += render(c, depth + 1)
    return h

def sig_fields(sig):
    return ", ".join(f'{f["field_name"]}{"[]" if f.get("field_dim") == "1" else ""}' for f in sig.get("rec_fields", [])) or "—"

# objectToString: the real output field name on the IS is resolved at deploy time (flows.objtostring_output); "string" here
services = [F.BEGIN_STEP, F.log_step("string"), F.TRUNCATE_STAR,
            F.dim_loader("loadCustomers", "selectCustomers", "insertCustomers", "customers", "Customer dimension: SELECT DISTINCT then BatchInsert into dwh.dim_customer. One transaction."),
            F.dim_loader("loadSalesreps", "selectSalesreps", "insertSalesreps", "salesreps", "Sales rep dimension: SELECT DISTINCT then BatchInsert into dwh.dim_salesrep. One transaction."),
            F.dim_loader("loadProducts", "selectProducts", "insertProducts", "products", "Product dimension: SELECT DISTINCT then BatchInsert into dwh.dim_product. One transaction."),
            F.LOAD_DATES, F.LOAD_FACT_CHUNK, F.run_pipeline("runPipeline", 1), F.run_pipeline("runPipelineX4", 4), F.START_PIPELINE,
            F.API_STATUS, F.API_START, F.API_ANALYZE, F.API_DIMENSION]
ORDER = ["star.etl:runPipeline", "star.etl.steps:loadFactChunk", "star.etl.steps:loadDates", "star.etl.steps:loadCustomers",
         "star.etl.steps:logStep", "star.etl:startPipeline", "star.etl:runPipelineX4", "star.api:start", "star.api:analyze"]
by = {s["node_nsName"]: s for s in services}
names = ORDER + [n for n in by if n not in ORDER]

parts = []
for name in names:
    s = by[name]
    parts.append(f'''<section class="svc" id="{html.escape(name)}"><h2>{html.escape(name)}</h2><p class="cm">{html.escape(s.get("node_comment", ""))}</p>
<p class="sig">input: <code>{sig_fields(s["svc_sig"]["sig_in"])}</code> · output: <code>{sig_fields(s["svc_sig"]["sig_out"])}</code></p>
{"".join(render(n) for n in s["flow"]["nodes"])}</section>''')
page = f'''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>StarSchemaETL · flow services</title>
<style>
body{{margin:0;background:#0f1419;color:#e6edf3;font:14px/1.5 "IBM Plex Sans","Segoe UI",system-ui,sans-serif}}
header{{padding:14px 24px;border-bottom:1px solid #2a3542;background:#161c24;position:sticky;top:0}} header h1{{margin:0;font-size:18px}} header small{{color:#8b98a8;margin-left:10px}}
main{{padding:16px 24px;display:grid;gap:14px}} .svc{{background:#161c24;border:1px solid #2a3542;border-radius:8px;padding:12px 16px}}
.svc h2{{margin:0 0 4px;font-size:15px;color:#33b1ff}} .sig{{color:#8b98a8;font-size:12px;margin:0 0 8px}} code{{color:#f1c21b;font-size:12px}}
.step{{padding:2px 0 2px 0;border-left:1px solid #2a3542;margin-left:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.d0{{padding-left:8px;border-left:none;margin-left:0}} .d1{{padding-left:26px}} .d2{{padding-left:52px}} .d3{{padding-left:78px}} .d4{{padding-left:104px}} .d5{{padding-left:130px}} .d6{{padding-left:156px}}
.ic{{display:inline-block;width:18px;font-weight:700}} .lb{{margin-right:8px}} .dt{{color:#8b98a8;font-size:12px;margin-right:8px}} .cm{{color:#8b98a8;font-style:italic;font-size:12px}} .lbl{{color:#f1c21b}}
nav{{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;margin-top:6px}} nav a{{color:#8b98a8;text-decoration:none}} nav a:hover{{color:#33b1ff}}
</style></head><body><header><h1>StarSchemaETL package · flow services <small>step tree exactly as deployed on the Integration Server (generated by wm/flowdoc.py)</small></h1>
<nav>{" ".join(f'<a href="#{html.escape(n)}">{html.escape(n.split(":")[1])}</a>' for n in names)}</nav></header>
<main>{"".join(parts)}</main></body></html>'''
open(OUT, "w", encoding="utf-8").write(page)
print("written", OUT, len(page), "bytes,", len(parts), "services")

# ---- Markdown version (docs/flows-trees.md): the same trees as text
def md_node(node, depth=0):
    t = node["type"]; ind = "  " * depth
    if t == "INVOKE":
        det = invoke_detail(node)
        line = f"INVOKE `{node['service']}`" + (f" ({det})" if det else "")
    elif t == "MAP": line = "MAP " + map_summary(node.get("nodes", []))
    elif t == "LOOP": line = f"LOOP over `{node['in-array']}`" + (f" → `{node['out-array']}`" if node.get("out-array") else "") + (f" · {node['max-threads']} parallel iterations" if node.get("max-threads", "1") != "1" else "")
    elif t == "BRANCH": line = "BRANCH on `" + node.get("switch", "expressions") + "`"
    elif t == "SEQUENCE": line = {"TRY": "TRY", "CATCH": "CATCH"}.get(node.get("form"), "SEQUENCE") + (f" [{node['label']}]" if "label" in node else "")
    elif t == "EXIT": line = f"EXIT {node['from']} / {node['signal']}" + (f" \"{node['failure-message']}\"" if node.get("failure-message") else "")
    else: line = t
    if node.get("comment"): line += f" — *{node['comment']}*"
    md = f"{ind}- {line}\n"
    for c in children_of(node):
        md += md_node(c, depth + 1)
    return md
lines = ["# Flow service trees (generated by wm/flowdoc.py)\n", "Every step exactly as deployed on the Integration Server (StarSchemaETL package).\n"]
for name in names:
    s_ = by[name]
    lines.append(f"\n## {name}\n\n{s_.get('node_comment', '')}\n\n*Input*: `{sig_fields(s_['svc_sig']['sig_in'])}` · *Output*: `{sig_fields(s_['svc_sig']['sig_out'])}`\n\n")
    lines.append("".join(md_node(n) for n in s_["flow"]["nodes"]))
open(MD, "w", encoding="utf-8").write("".join(lines))
print("written", MD)
