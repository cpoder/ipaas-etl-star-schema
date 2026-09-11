"""Overview graph of an IS package ("workflow" view): services and how they chain (INVOKE, scheduler, publication,
triggers, JDBC notification, HTTP calls from the UI), document types used or published, adapter services
(with their SQL table) and resources (file, external API). Rendered as a self-contained SVG (layered layout computed here,
no dependency), embedded in flows.html by wm/flowdoc.py. Flow service nodes link to their
step tree; hovering highlights the neighbours.
"""
import html, re
from xml.sax.saxutils import unescape

W, H, HS, GAP_X, GAP_Y, PAD = 204, 46, 34, 72, 10, 24        # width, height (services / adapters), column / row spacing, margin
GROUP_MIN = 4                                                # number of exclusive adapters from which they are grouped

T = {
    "fr": {"ui": "Interface (navigateur)", "ui_sub": "HTTP /invoke, Basic auth", "sched": "Scheduler IS", "sched_sub": "tâche unique, +3 s", "uses": "utilise",
           "publish": "publie", "sub": "abonné", "notif": "notification JDBC", "trigger": "trigger", "file": "fichier", "http": "HTTP", "schedules": "planifie",
           "fields": "champs", "publishable": "publiable · Universal Messaging", "adapters": "services adaptateur", "builtin": "services intégrés",
           "ctl": "suspend / resume", "legend": "Légende", "k_flow": "flow service (cliquer : arbre des étapes)", "k_adapter": "service adaptateur JDBC (table SQL)",
           "k_doc": "type de document", "k_ext": "service d'un autre package", "k_entry": "déclencheur / ressource", "invoke": "appel (INVOKE)",
           "polls": "scrute", "title": "Vue d'ensemble : enchaînement des services et types de documents"},
    "en": {"ui": "Browser UI", "ui_sub": "HTTP /invoke, Basic auth", "sched": "IS scheduler", "sched_sub": "one-time task, +3 s", "uses": "uses",
           "publish": "publishes", "sub": "subscriber", "notif": "JDBC notification", "trigger": "trigger", "file": "file", "http": "HTTP", "schedules": "schedules",
           "fields": "fields", "publishable": "publishable · Universal Messaging", "adapters": "adapter services", "builtin": "built-in services",
           "ctl": "suspend / resume", "legend": "Legend", "k_flow": "flow service (click: step tree)", "k_adapter": "JDBC adapter service (SQL table)",
           "k_doc": "document type", "k_ext": "service from another package", "k_entry": "trigger / resource", "invoke": "call (INVOKE)",
           "polls": "polls", "title": "Overview: service chaining and document types"},
}
COLORS = {"flow": ("#1c2a3d", "#4589ff"), "api": ("#2a2416", "#f1c21b"), "adapter": ("#16291f", "#42be65"), "adapters": ("#16291f", "#42be65"),
          "doc": ("#241d33", "#a56eff"), "external": ("#2d1a26", "#ff7eb6"), "entry": ("#142630", "#33b1ff")}
EDGE_COLORS = {"invoke": "#5b6f8a", "uses": "#a56eff", "publish": "#a56eff", "subscribe": "#a56eff", "schedules": "#f1c21b", "http": "#33b1ff", "ctl": "#f1c21b",
               "notif": "#33b1ff", "file": "#08bdba"}


# ------------------------------------------------------------------ extraction from the putNode JSON
def walk(node):
    yield node
    for c in node.get("nodes", []):
        yield from walk(c)


def mapset_value(node):
    m = re.search(r'<value name="xml">(.*?)</value>', node.get("data", ""), re.S)
    return unescape(m.group(1)) if m else ""


def collect(svc):
    """What a flow service references: invoked services, documents (;4;dim;doc paths and signature), MAPSET values."""
    info = {"invokes": [], "docs": set(), "sets": [], "builtin": set()}
    for n in walk(svc["flow"]):
        t = n.get("type")
        if t == "INVOKE":
            info["invokes"].append(n["service"])
        elif t == "MAPCOPY":
            for p in (n.get("from", ""), n.get("to", "")):
                for seg in p.split("/"):
                    parts = seg.split(";")
                    if len(parts) >= 4 and parts[1] == "4":
                        info["docs"].add(parts[3])
        elif t == "MAPSET":
            info["sets"].append((n.get("field", ""), mapset_value(n)))
    for k in ("sig_in", "sig_out"):
        for f in svc["svc_sig"].get(k, {}).get("rec_fields", []):
            if f.get("rec_ref"):
                info["docs"].add(f["rec_ref"])
    return info


def sql_target(sql):
    m = re.search(r"\b(?:INTO|UPDATE|FROM|JOIN)\s+([a-z_]+\.[a-z_]+)", sql, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\b([a-z_]+\.[a-z_]+)\s*\(", sql, re.I)      # fonction SQL, ex. dwh.reset_demo()
    return m.group(1) + "()" if m else ""


def adapter_infos(folder, custom_sql=(), batch_insert=()):
    """(full name, subtitle) list of the adapter services of a builder module."""
    out = {}
    for row in custom_sql:
        name, conn, sql = row[0], row[1], row[2]
        kind = "SELECT" if sql.lstrip().upper().startswith(("SELECT", "WITH")) else sql.split()[0].upper()
        out[f"{folder}:{name}"] = f"{kind} · {sql_target(sql)}"
    for row in batch_insert:
        name, conn, schema, table = row[0], row[1], row[2], row[3]
        out[f"{folder}:{name}"] = f"BatchInsert · {schema}.{table}"
    return out


# ------------------------------------------------------------------ graph construction
class Graph:
    def __init__(self, lang):
        self.t = T[lang]
        self.nodes = {}        # id -> {kind, label, sub, title, href}
        self.edges = []        # {src, dst, kind, label}
        self.edge_keys = set()

    def node(self, nid, kind, label, sub="", title="", href=None):
        if nid not in self.nodes:
            self.nodes[nid] = {"id": nid, "kind": kind, "label": label, "sub": sub, "title": title or nid, "href": href}
        return self.nodes[nid]

    def edge(self, src, dst, kind="invoke", label=""):
        key = (src, dst, kind)
        if src == dst or key in self.edge_keys or src not in self.nodes or dst not in self.nodes:
            return
        self.edge_keys.add(key)
        self.edges.append({"src": src, "dst": dst, "kind": kind, "label": label})


def build(services, adapters, doctypes, lang="fr", triggers=(), notifications=(), sections=None, aliases=None):
    g, t = Graph(lang), T[lang]
    flows = {s["node_nsName"]: s for s in services}
    sections = set(sections) if sections is not None else set(flows)
    aliases = aliases or {}
    docs = {d["node_nsName"]: d for d in doctypes}
    for name, s in flows.items():
        folder, short = name.split(":")
        target = aliases.get(name, name)
        g.node(name, "api" if folder.endswith(".api") else "flow", short, folder, s.get("node_comment", "") or name, href=("#" + target) if target in sections else None)
    for name, d in docs.items():
        n = len(d.get("rec_fields", []))
        pub = "eventDescription" in d
        g.node(name, "doc", name.split(":")[1], (t["publishable"] if pub else name.split(":")[0]) + f" · {n} {t['fields']}", name)
    infos = {name: collect(s) for name, s in flows.items()}
    # HTTP entries from the UI to the *.api services
    api = [n for n in flows if n.split(":")[0].endswith(".api")]
    if api:
        g.node("ui", "entry", t["ui"], t["ui_sub"])
        for n in api:
            g.edge("ui", n, "http", "")
    # JDBC notifications and triggers (outside the flows: declared by the builder module)
    for notif, doc, source, *detail in notifications:
        g.node(doc, "doc", doc.split(":")[1], t["publishable"], doc)
        g.node(notif, "entry", notif.split(":")[1], t["notif"] + " · " + source, notif + "\n" + " ".join(detail))
        g.edge(notif, doc, "publish", t["publish"])
    for trig, doc, svc, *_ in triggers:
        if doc not in g.nodes:
            g.node(doc, "doc", doc.split(":")[1], t["publishable"], doc)
        g.node(trig, "entry", trig.split(":")[1], t["trigger"] + " · " + t["sub"], trig)
        g.edge(doc, trig, "subscribe", t["sub"])
        g.edge(trig, svc, "subscribe", "")
    subscribed = {(doc, svc) for _, doc, svc, *_ in triggers}
    # appels
    adapter_callers = {}
    for name, info in infos.items():
        builtin = 0
        for inv in info["invokes"]:
            if inv in flows:
                g.edge(name, inv)
            elif inv in adapters:
                adapter_callers.setdefault(inv, set()).add(name)
            elif inv.startswith("pub.publish:publish"):
                for field, value in info["sets"]:
                    if field.startswith("/documentTypeName"):
                        if value not in g.nodes:
                            g.node(value, "doc", value.split(":")[1], t["publishable"], value)
                        g.edge(name, value, "publish", t["publish"])
            elif inv.startswith("pub.scheduler:"):
                g.node("scheduler", "entry", t["sched"], t["sched_sub"])
                g.edge(name, "scheduler", "schedules", t["schedules"])
                for field, value in info["sets"]:
                    if value in flows:
                        g.edge("scheduler", value, "schedules", "")
            elif inv.startswith("pub.file:") and inv.split(":")[1] in ("stringToFile", "bytesToFile", "streamToFile"):
                path = next((v for f, v in info["sets"] if "/out/" in v or v.endswith((".csv", ".txt", ".json"))), "")
                g.node("file", "entry", path.rsplit("/", 1)[-1].replace("%day%", "<jour>") or t["file"], t["file"] + " · " + path.rsplit("/", 2)[0].rsplit("/", 1)[-1] + "/", path)
                g.edge(name, "file", "file", "")
            elif inv.startswith("pub.trigger:"):
                for trig, _, _, *_ in triggers:
                    g.edge(name, trig, "ctl", "")
            elif inv == "wm.art.admin:setNotificationStatus":
                for notif, *_ in notifications:
                    g.edge(name, notif, "ctl", "")
            elif not inv.startswith(("pub.", "wm.")):
                g.node(inv, "external", inv.split(":")[1], inv.split(":")[0] + " · " + t["k_ext"].split(" ")[0], inv)
                g.edge(name, inv)
            else:
                builtin += 1
        if builtin:
            g.nodes[name]["sub"] += f" · {builtin} {t['builtin']}"
        for d in info["docs"]:
            if d in g.nodes and (d, name) not in subscribed and not any(e["src"] == name and e["dst"] == d for e in g.edges):
                g.edge(name, d, "uses", t["uses"])
    # adapter services: grouped when a single caller uses several of them exclusively
    exclusive = {}
    for adp, callers in adapter_callers.items():
        if len(callers) == 1:
            exclusive.setdefault(next(iter(callers)), []).append(adp)
    grouped = set()
    for caller, adps in exclusive.items():
        if len(adps) >= GROUP_MIN:
            gid = "group:" + caller
            names = [a.split(":")[1] for a in adps]
            g.node(gid, "adapters", f"{len(adps)} {t['adapters']}", ", ".join(names[:3]) + (" …" if len(names) > 3 else ""),
                   "\n".join(f"{a.split(':')[1]} : {adapters[a]}" for a in adps))
            g.edge(caller, gid)
            grouped.update(adps)
    for adp, callers in adapter_callers.items():
        if adp in grouped:
            continue
        g.node(adp, "adapter", adp.split(":")[1], adapters[adp], adp + "\n" + adapters[adp])
        for c in callers:
            g.edge(c, adp)
    return g


# ------------------------------------------------------------------ disposition en couches (gauche → droite)
def layout(g):
    succ, pred = {n: [] for n in g.nodes}, {n: [] for n in g.nodes}
    for e in g.edges:
        succ[e["src"]].append(e["dst"]); pred[e["dst"]].append(e["src"])
    layer, state = {}, {}

    def depth(n):          # longest path from a root (cycles, if any, are cut)
        if n in layer: return layer[n]
        if state.get(n) == 1: return 0
        state[n] = 1
        layer[n] = max([depth(p) + 1 for p in pred[n]] or [0])
        state[n] = 2
        return layer[n]
    for n in g.nodes: depth(n)
    for n in g.nodes:      # leaves (documents, adapters) move next to their callers
        if not succ[n] and pred[n]:
            layer[n] = max(layer[p] for p in pred[n]) + 1
    cols = {}
    for n, l in layer.items(): cols.setdefault(l, []).append(n)
    order = {l: list(ns) for l, ns in cols.items()}
    pos = {}
    for l in order:
        for i, n in enumerate(order[l]): pos[n] = i
    for sweep in range(6):     # barycenters: down then up
        seq = sorted(order) if sweep % 2 == 0 else sorted(order, reverse=True)
        for l in seq:
            def key(n):
                nb = [pos[p] for p in (pred[n] if sweep % 2 == 0 else succ[n]) if p in pos and layer[p] != l]
                return (sum(nb) / len(nb)) if nb else pos[n]
            order[l].sort(key=key)
            for i, n in enumerate(order[l]): pos[n] = i
    heights = {n: (HS if g.nodes[n]["kind"] in ("adapter", "adapters") else H) for n in g.nodes}
    col_h = {l: sum(heights[n] for n in ns) + GAP_Y * (len(ns) - 1) for l, ns in order.items()}
    total_h = max(col_h.values()) if col_h else 0
    xy = {}
    for l, ns in order.items():
        y = PAD + (total_h - col_h[l]) / 2
        for n in ns:
            xy[n] = (PAD + l * (W + GAP_X), y, heights[n]); y += heights[n] + GAP_Y
    width = PAD * 2 + (max(order) + 1) * W + max(order) * GAP_X if order else 0
    return xy, width, total_h + 2 * PAD


def ellipsis(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def render(services, adapters, doctypes, lang="fr", triggers=(), notifications=(), pkg="", sections=None, aliases=None):
    g = build(services, adapters, doctypes, lang, triggers, notifications, sections, aliases)
    t = T[lang]
    xy, width, height = layout(g)
    legend_h = 58
    out = [f'<svg class="wf" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height + legend_h:.0f}" width="{width:.0f}" height="{height + legend_h:.0f}" data-w="{width:.0f}" role="img" aria-label="{html.escape(t["title"])}">',
           '<defs>' + "".join(f'<marker id="m-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="{c}"/></marker>' for k, c in EDGE_COLORS.items()) + '</defs>',
           '<style>.wf .e{fill:none;stroke-width:1.6;opacity:.55}.wf .e.dashed{stroke-dasharray:6 4}.wf .e.dotted{stroke-dasharray:2 4}.wf .n rect{stroke-width:1.4}.wf .n text{font-family:"IBM Plex Sans","Segoe UI",system-ui,sans-serif}'
           '.wf .lb{font-size:12.5px;font-weight:600;fill:#e6edf3}.wf .sb{font-size:10.5px;fill:#8b98a8}.wf .el{font-size:10px;fill:#8b98a8}.wf .elbg{fill:#161c24}'
           '.wf .n.dim{opacity:.25}.wf .e.dim{opacity:.08}.wf .e.hi{opacity:1;stroke-width:2.4}.wf .n.hi rect{stroke-width:2.6;filter:drop-shadow(0 0 6px rgba(51,177,255,.6))}.wf .n{cursor:default}.wf a .n{cursor:pointer}.wf .lg{font-size:11px;fill:#8b98a8}</style>']
    # edges
    for i, e in enumerate(g.edges):
        (x1, y1, h1), (x2, y2, h2) = xy[e["src"]], xy[e["dst"]]
        sx, sy, tx, ty = x1 + W, y1 + h1 / 2, x2, y2 + h2 / 2
        if x2 <= x1:      # backward edge (rare): goes around below
            sx, sy, tx, ty = x1 + W / 2, y1 + h1, x2 + W / 2, y2 + h2
            d = f"M {sx:.1f} {sy:.1f} C {sx:.1f} {sy + 40:.1f}, {tx:.1f} {ty + 40:.1f}, {tx:.1f} {ty:.1f}"
        else:
            mx = (sx + tx) / 2
            d = f"M {sx:.1f} {sy:.1f} C {mx:.1f} {sy:.1f}, {mx:.1f} {ty:.1f}, {tx:.1f} {ty:.1f}"
        dash = "dashed" if e["kind"] in ("schedules", "http", "ctl") else ("dotted" if e["kind"] == "uses" else "")
        out.append(f'<path class="e {dash}" data-s="{html.escape(e["src"])}" data-d="{html.escape(e["dst"])}" d="{d}" stroke="{EDGE_COLORS[e["kind"]]}" marker-end="url(#m-{e["kind"]})"/>')
        if e["label"]:
            lx, ly = (sx + tx) / 2, (sy + ty) / 2 - 4
            wl = len(e["label"]) * 5.6 + 8
            out.append(f'<rect class="elbg" x="{lx - wl / 2:.1f}" y="{ly - 9:.1f}" width="{wl:.1f}" height="13" rx="3"/><text class="el" x="{lx:.1f}" y="{ly + 1:.1f}" text-anchor="middle">{html.escape(e["label"])}</text>')
    # nœuds
    for nid, n in g.nodes.items():
        x, y, h = xy[nid]
        fill, stroke = COLORS[n["kind"]]
        dash = ' stroke-dasharray="5 3"' if n["kind"] == "entry" else ""
        rx = 12 if n["kind"] in ("flow", "api") else (3 if n["kind"] == "doc" else 7)
        body = (f'<g class="n" data-id="{html.escape(nid)}"><title>{html.escape(n["title"])}</title>'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{W}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}"{dash}/>')
        if n["kind"] == "doc":       # folded corner = document
            body += f'<path d="M {x + W - 14:.1f} {y:.1f} L {x + W:.1f} {y + 14:.1f} L {x + W - 14:.1f} {y + 14:.1f} z" fill="{stroke}" opacity=".7"/>'
        if h >= H:
            body += (f'<text class="lb" x="{x + 12:.1f}" y="{y + 19:.1f}">{html.escape(ellipsis(n["label"], 28))}</text>'
                     f'<text class="sb" x="{x + 12:.1f}" y="{y + 35:.1f}">{html.escape(ellipsis(n["sub"], 36))}</text>')
        else:
            body += (f'<text class="lb" x="{x + 10:.1f}" y="{y + 14:.1f}" style="font-size:11.5px">{html.escape(ellipsis(n["label"], 30))}</text>'
                     f'<text class="sb" x="{x + 10:.1f}" y="{y + 27:.1f}" style="font-size:9.8px">{html.escape(ellipsis(n["sub"], 40))}</text>')
        body += "</g>"
        out.append(f'<a href="{html.escape(n["href"])}">{body}</a>' if n.get("href") else body)
    # legend
    ly = height + 8
    items = [("flow", t["k_flow"]), ("adapter", t["k_adapter"]), ("doc", t["k_doc"]), ("external", t["k_ext"]), ("entry", t["k_entry"])]
    lx = PAD
    out.append(f'<text class="lg" x="{lx}" y="{ly + 14}" style="font-weight:600">{html.escape(t["legend"])}</text>')
    lx += 60
    for kind, label in items:
        fill, stroke = COLORS[kind]
        out.append(f'<rect x="{lx}" y="{ly + 4}" width="16" height="12" rx="3" fill="{fill}" stroke="{stroke}"{" stroke-dasharray=\"3 2\"" if kind == "entry" else ""}/><text class="lg" x="{lx + 22}" y="{ly + 14}">{html.escape(label)}</text>')
        lx += 22 + len(label) * 6.2 + 26
    out.append(f'<text class="lg" x="{PAD}" y="{ly + 38}">─── {html.escape(t["invoke"])}     ╌╌╌ {html.escape(t["schedules"])} / {html.escape(t["http"])} / {html.escape(t["ctl"])}     ··· {html.escape(t["uses"])}     ──▶ {html.escape(t["publish"])} / {html.escape(t["sub"])}</text>')
    out.append("</svg>")
    return "".join(out), g


SCRIPT = """<script>
(function(){const svg=document.querySelector('svg.wf');if(!svg)return;const nodes=[...svg.querySelectorAll('.n')],edges=[...svg.querySelectorAll('.e')];
const wrap=svg.parentElement;function fit(on){svg.classList.toggle('fit',on);document.querySelectorAll('.gbtn').forEach(b=>b.classList.toggle('on',(b.dataset.fit==='1')===on));}
fit(+svg.dataset.w<=Math.min(wrap.clientWidth,document.documentElement.clientWidth-96)*1.25);document.querySelectorAll('.gbtn').forEach(b=>b.addEventListener('click',()=>fit(b.dataset.fit==='1')));
function hi(id){if(!id){nodes.forEach(n=>n.classList.remove('dim','hi'));edges.forEach(e=>e.classList.remove('dim','hi'));return;}
const near=new Set([id]);edges.forEach(e=>{const on=e.dataset.s===id||e.dataset.d===id;e.classList.toggle('hi',on);e.classList.toggle('dim',!on);if(on){near.add(e.dataset.s);near.add(e.dataset.d);}});
nodes.forEach(n=>{const k=near.has(n.dataset.id);n.classList.toggle('hi',n.dataset.id===id);n.classList.toggle('dim',!k);});}
nodes.forEach(n=>{n.addEventListener('mouseenter',()=>hi(n.dataset.id));n.addEventListener('mouseleave',()=>hi(null));});})();
</script>"""
