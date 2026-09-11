""""Execution flow" view of an IS package: for every trigger (UI, JDBC notification, IS trigger, scheduler),
the sequence of steps in actual execution order, as defined by the deployed flow: package services
(expanded below, once), adapter services with their SQL table, produced documents, loops, branches,
CATCH, transactions, publication on UM then subscribers, file, external API. Utility services called everywhere
(log, timestamp) are attached to the steps they surround. Self-contained SVG embedded in flows.html by wm/flowdoc.py.
"""
import html, re
from flowgraph import mapset_value, walk as _walk

MAXW, HEADER_W, INDENT, GAP, ROW_GAP, LINE_GAP, PAD = 1560, 236, 26, 22, 18, 14, 24
BOX_H, BOX_H2, CHIP_H, GROUP_PAD, GROUP_TOP = 44, 58, 26, 8, 20
UTIL_MIN = 2

T = {
    "fr": {"title": "Flux d'exécution : dans l'ordre, déclencheur par déclencheur", "ui": "Interface (navigateur)", "ui_sub": "appels HTTP /invoke",
           "sched": "Scheduler IS", "sched_sub": "tâche unique, +3 s →", "notif": "notification JDBC", "trigger": "trigger", "ops": "opérations",
           "op": "opération", "publish": "publie sur UM", "file": "fichier", "loop": "LOOP", "branch": "BRANCH", "catch": "CATCH", "exit": "EXIT",
           "tx": "transaction", "commit": "commit", "rollback": "rollback", "parallel": "en parallèle", "start": "Déclenchement",
           "subs": "abonnés UM", "utils": "Services utilitaires (appelés par les étapes ci-dessus)", "seeabove": "développé plus haut",
           "legend": "Légende", "k_flow": "service du package (développé en dessous)", "k_adapter": "service adaptateur JDBC · table",
           "k_doc": "document produit", "k_util": "service utilitaire rattaché", "k_ext": "autre package / ressource", "k_group": "LOOP · BRANCH · CATCH",
           "ctl": "suspend / resume", "wrap": "suite", "receives": "reçoit", "day": "<jour>"},
    "en": {"title": "Execution flow: in order, trigger by trigger", "ui": "Browser UI", "ui_sub": "HTTP /invoke calls",
           "sched": "IS scheduler", "sched_sub": "one-time task, +3 s →", "notif": "JDBC notification", "trigger": "trigger", "ops": "operations",
           "op": "operation", "publish": "publishes to UM", "file": "file", "loop": "LOOP", "branch": "BRANCH", "catch": "CATCH", "exit": "EXIT",
           "tx": "transaction", "commit": "commit", "rollback": "rollback", "parallel": "in parallel", "start": "Trigger",
           "subs": "UM subscribers", "utils": "Utility services (called by the steps above)", "seeabove": "expanded above",
           "legend": "Legend", "k_flow": "package service (expanded below)", "k_adapter": "JDBC adapter service · table",
           "k_doc": "document produced", "k_util": "attached utility service", "k_ext": "other package / resource", "k_group": "LOOP · BRANCH · CATCH",
           "ctl": "suspend / resume", "wrap": "continued", "receives": "receives", "day": "<day>"},
}
STYLE = {"flow": ("#1c2a3d", "#4589ff"), "api": ("#2a2416", "#f1c21b"), "adapter": ("#16291f", "#42be65"), "external": ("#2d1a26", "#ff7eb6"),
         "entry": ("#142630", "#33b1ff"), "publish": ("#241d33", "#a56eff"), "doc": ("#241d33", "#a56eff"), "ops": ("#1a2028", "#5b6f8a"),
         "util": ("#1a2028", "#8b98a8"), "tx": ("#1a2028", "#8b98a8"), "exit": ("#2a1a1c", "#fa4d56"), "file": ("#142630", "#08bdba"),
         "scheduler": ("#142630", "#33b1ff"), "ctl": ("#2a2416", "#f1c21b")}
GROUP_STYLE = {"loop": "#ff832b", "branch": "#a56eff", "catch": "#fa4d56", "case": "#5b6f8a"}


# ------------------------------------------------------------------ step extraction of a service
def short(name):
    return name.split(":")[-1]


def path_name(p):
    return p.strip("/").split("/")[-1].split(";")[0]


def doc_refs(nodes):
    out = []
    for n in nodes:
        if n.get("type") == "MAPCOPY":
            for p in (n.get("from", ""), n.get("to", "")):
                for seg in p.split("/"):
                    parts = seg.split(";")
                    if len(parts) >= 4 and parts[1] == "4" and parts[3] not in out:
                        out.append(parts[3])
    return out


class Ctx:
    def __init__(self, flows, adapters, doctypes, utilities, sets_by_svc, lang):
        self.flows, self.adapters, self.doctypes, self.utilities, self.sets_by_svc, self.t = flows, adapters, doctypes, utilities, sets_by_svc, T[lang]
        self.seen_docs = set()


def item(kind, label, sub="", title="", name=None, **kw):
    d = {"kind": kind, "label": label, "sub": sub, "title": title or label, "name": name, "pre": [], "post": []}
    d.update(kw)
    return d


class Ops:
    """Run of built-in operations (pub.*, wm.*, MAP) between two significant steps: a single chip."""
    def __init__(self):
        self.names, self.maps, self.sets, self.comments = [], 0, [], []

    def flush(self, out, ctx, force=False):
        if self.names or (force and self.maps):
            names = list(dict.fromkeys(self.names))
            n = len(self.names)
            if not names:
                label = "⚙ MAP" + (" " + ", ".join(f"{k} = {v}" for k, v in self.sets[:2]) if self.sets else "")
            elif n == 1:
                label = "⚙ " + short(names[0])
            elif n <= 3:
                label = "⚙ " + ", ".join(short(x) for x in names)
            else:
                label = f"⚙ {n} {ctx.t['ops']}"
            out.append(item("ops", label[:34], "", "\n".join(names) or ("MAP\n" + "\n".join(f"{k} = {v}" for k, v in self.sets)), names=names, sets=list(self.sets), comments=list(self.comments)))
        self.names, self.maps, self.sets, self.comments = [], 0, [], []


def seq(nodes, ctx, svc_name, out=None):
    out = [] if out is None else out
    ops = Ops()
    for n in nodes:
        t = n.get("type")
        if t == "INVOKE":
            name = n["service"]
            maps = [x for m in n.get("nodes", []) for x in m.get("nodes", [])]
            sets = {path_name(x.get("field", "")): mapset_value(x) for x in maps if x.get("type") == "MAPSET"}
            docs = [d for d in doc_refs(maps) if d not in ctx.seen_docs]
            it = None
            if name in ctx.flows:
                if name in ctx.utilities:
                    tag = " ".join(v for k, v in sets.items() if (k.lower() in ("stepname", "step", "event") or (k.lower() == "status" and v not in ("OK", "DONE"))) and v and len(v) <= 24)
                    it = item("util", short(name) + (" " + tag if tag else ""), "", name + ("\n" + tag if tag else ""), name)
                else:
                    it = item("api" if name.split(":")[0].endswith(".api") else "flow", short(name), name.split(":")[0], ctx.flows[name].get("node_comment", "") or name, name, expand=True)
            elif name in ctx.adapters:
                it = item("adapter", short(name), ctx.adapters[name], name + "\n" + ctx.adapters[name], name)
            elif name.startswith("pub.publish:"):
                doc = sets.get("documentTypeName", "?")
                it = item("publish", ctx.t["publish"], short(doc), name + " → " + doc, name, doc=doc)
            elif name.startswith("pub.scheduler:"):
                targets = list(dict.fromkeys(v for _, v in ctx.sets_by_svc.get(svc_name, []) if v in ctx.flows))
                names = sorted((short(x) for x in targets), key=len)
                shown = (names[0] + " (" + ", ".join(n[len(names[0]):] for n in names[1:] if n.startswith(names[0])) + ")") if len(names) > 1 and all(n.startswith(names[0]) for n in names) else ", ".join(names)
                it = item("scheduler", ctx.t["sched"] + " · +3 s", "→ " + shown, name + "\n" + "\n".join(targets), name, targets=targets)
            elif name.startswith("pub.file:") and short(name) in ("stringToFile", "bytesToFile", "streamToFile"):
                path = next((v for _, v in ctx.sets_by_svc.get(svc_name, []) if "/out/" in v or v.endswith((".csv", ".txt", ".json"))), "")
                shown = "/".join(path.rsplit("/", 2)[-2:])          # directory/file only (no absolute path in the pages)
                it = item("file", ctx.t["file"] + " " + (path.rsplit("/", 1)[-1].replace("%day%", ctx.t["day"]) or ""), short(name), name + "\n" + shown, name)
            elif name.startswith("pub.art.transaction:"):
                k = short(name)
                it = item("tx", "▶ " + ctx.t["tx"] if k.startswith("start") else ("✓ " + ctx.t["commit"] if k.startswith("commit") else "↩ " + ctx.t["rollback"]), "", name, name)
            elif name.startswith("pub.trigger:") or name == "wm.art.admin:setNotificationStatus":
                it = item("ctl", ctx.t["ctl"], short(name), name, name)
            elif not name.startswith(("pub.", "wm.")):
                it = item("external", short(name), name.split(":")[0], name, name)
            if it is None:
                ops.names.append(name)
                if n.get("comment"): ops.comments.append(n["comment"])
            else:
                ops.flush(out, ctx)
                it["comment"], it["sets"] = n.get("comment", ""), sets
                out.append(it)
            for d in docs:
                ctx.seen_docs.add(d)
                out.append(item("doc", "⟨" + short(d) + "⟩", "", d, d))
        elif t == "MAP":
            docs = [d for d in doc_refs(n.get("nodes", [])) if d not in ctx.seen_docs]
            if docs:
                ops.flush(out, ctx)
                for d in docs:
                    ctx.seen_docs.add(d)
                    out.append(item("doc", "⟨" + short(d) + "⟩", "", d, d))
            else:
                ops.maps += 1
                if n.get("comment"): ops.comments.append(n["comment"])
                ops.sets += [(path_name(x.get("field", "")), (short(v) if ":" in v and " " not in v else v)) for x in n.get("nodes", []) if x.get("type") == "MAPSET" for v in [mapset_value(x)] if len(v) <= 40]
        elif t == "SEQUENCE":
            if n.get("form") == "CATCH":
                ops.flush(out, ctx)
                out.append(item("group", ctx.t["catch"], gkind="catch", items=seq(n.get("nodes", []), ctx, svc_name), comment=n.get("comment", "")))
            else:
                seq(n.get("nodes", []), ctx, svc_name, out)
        elif t in ("LOOP", "REPEAT"):
            ops.flush(out, ctx)
            label = ctx.t["loop"] + " " + path_name(n.get("in-array", "")) if t == "LOOP" else "REPEAT"
            if n.get("max-threads", "1") not in ("1", ""):
                label += f" · ×{n['max-threads']} {ctx.t['parallel']}"
            out.append(item("group", label, gkind="loop", items=seq(n.get("nodes", []), ctx, svc_name), comment=n.get("comment", ""), array=path_name(n.get("in-array", "")), threads=n.get("max-threads", "1")))
        elif t == "BRANCH":
            ops.flush(out, ctx)
            cases = []
            for c in n.get("nodes", []):
                lab = str(c.get("label", "")) if c.get("type") == "SEQUENCE" else ""
                cases.append((lab, seq(c.get("nodes", []) if c.get("type") == "SEQUENCE" else [c], ctx, svc_name)))
            out.append(item("group", ctx.t["branch"] + " " + (n.get("switch") or "expr"), gkind="branch", cases=cases, comment=n.get("comment", ""), switch=n.get("switch") or ""))
        elif t == "EXIT":
            ops.flush(out, ctx)
            out.append(item("exit", ctx.t["exit"] + " " + n.get("signal", ""), "", n.get("failure-message", "") or n.get("from", ""), signal=n.get("signal", ""), message=n.get("failure-message", "")))
    ops.flush(out, ctx, force=not out)
    return out


def finalize(items):
    """Attaches the utility services, once per list, then descends into the groups."""
    items = attach_utils(items)
    for it in items:
        if it["kind"] == "group":
            if it["gkind"] == "branch":
                it["cases"] = [(lab, finalize(c)) for lab, c in it["cases"]]
            else:
                it["items"] = finalize(it["items"])
    return items


PREFIX_HINT = ("begin", "start", "init", "open", "prepare")


def attach_utils(items):
    """A utility service becomes the suffix of the step before it (log) or the prefix of the step after it
    (start timestamp: name starting with begin/start/init, or utility coming right after another utility)."""
    res, pending = [], []
    boxes = ("flow", "api", "adapter", "external", "publish", "scheduler", "file", "ops", "ctl")
    just_attached = False
    for i, it in enumerate(items):
        if it["kind"] == "util":
            nxt = next((x for x in items[i + 1:] if x["kind"] != "util"), None)
            prefers_next = short(it["name"] or "").lower().startswith(PREFIX_HINT) and nxt is not None and nxt["kind"] in boxes
            if res and res[-1]["kind"] in boxes and not pending and not just_attached and not prefers_next:
                res[-1]["post"].append(it); just_attached = True
            else:
                pending.append(it)
        else:
            just_attached = False
            if it["kind"] in boxes and pending:
                it["pre"].extend(pending); pending = []
            elif pending:
                res.extend(pending); pending = []
            res.append(it)
    res.extend(pending)
    return res


# ------------------------------------------------------------------ row construction (triggers then expansions)
def text_w(s, size=12):
    return len(s) * size * 0.58


def ellipsis(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def measure(it):
    k = it["kind"]
    if k == "group":
        if it["gkind"] == "branch":
            rows = []
            for lab, items in it["cases"]:
                w = text_w(lab or "$default", 10.5) + 12
                h = CHIP_H
                for x in items:
                    measure(x); w += x["w"] + GAP; h = max(h, x["h"])
                rows.append((w, h))
            it["w"] = max([r[0] for r in rows] + [text_w(it["label"], 10.5) + 10]) + 2 * GROUP_PAD
            it["h"] = GROUP_TOP + sum(r[1] for r in rows) + 8 * (len(rows) - 1) + GROUP_PAD
        else:
            w, h = 0, CHIP_H
            for x in it["items"]:
                measure(x); w += x["w"] + GAP; h = max(h, x["h"])
            it["w"] = max(w - GAP, text_w(it["label"], 10.5) + 10) + 2 * GROUP_PAD
            it["h"] = GROUP_TOP + h + GROUP_PAD
        return
    if k in ("util", "doc", "tx", "exit"):
        it["w"], it["h"] = max(text_w(ellipsis(it["label"], 44), 11) + 20, 60), CHIP_H
        return
    badges = " · ".join(x["label"] for x in it["pre"] + it["post"])
    it["w"] = min(max(text_w(it["label"], 12) + 22, text_w(it["sub"], 10.5) + 22, text_w(badges, 10) + 22, 112), 260)
    it["h"] = BOX_H2 if badges else BOX_H


def build_rows(services, adapters, doctypes, lang, triggers, notifications, sections, aliases):
    t = T[lang]
    flows = {s["node_nsName"]: s for s in services}
    infos = {}
    calls = {}
    for name, s in flows.items():
        invs = [n["service"] for n in _walk(s["flow"]) if n.get("type") == "INVOKE"]
        infos[name] = invs
        for x in invs:
            calls[x] = calls.get(x, 0) + 1
    max_in_one = {}
    for name, invs in infos.items():
        for x in set(invs):
            max_in_one[x] = max(max_in_one.get(x, 0), invs.count(x))
    utilities = {n for n in flows if max_in_one.get(n, 0) >= UTIL_MIN and not any(x in flows for x in infos[n])}
    sets_by_svc = {name: [(n.get("field", ""), mapset_value(n)) for n in _walk(s["flow"]) if n.get("type") == "MAPSET"] for name, s in flows.items()}
    ctx = Ctx(flows, adapters, {d["node_nsName"]: d for d in doctypes}, utilities, sets_by_svc, lang)
    rows, expanded = [], set()
    trig_by_doc = {}
    for trig, doc, svc, *_ in triggers:
        trig_by_doc.setdefault(doc, []).append((trig, svc))

    def href(name):
        target = aliases.get(name, name)
        return "#" + target if target in sections else None

    def add_row(kind, label, sub, items, depth, parent=None, name=None, comment=""):
        for x in items:
            measure(x)
        row = {"kind": kind, "label": label, "sub": sub, "items": items, "depth": depth, "parent": parent, "name": name, "href": href(name) if name else None, "comment": comment}
        rows.append(row)
        return row

    def expand(name, depth, parent):
        if name not in flows:
            return
        if name in expanded:
            return
        expanded.add(name)
        ctx.seen_docs = set()
        items = finalize(seq(flows[name]["flow"]["nodes"], ctx, name))
        sig_docs = [f["rec_ref"] for f in flows[name]["svc_sig"].get("sig_in", {}).get("rec_fields", []) if f.get("rec_ref")]
        for d in sig_docs:
            items.insert(0, item("doc", t["receives"] + " ⟨" + short(d) + "⟩", "", d, d))
        folder = name.split(":")[0]
        row = add_row("api" if folder.endswith(".api") else "flow", short(name), folder, items, depth, parent, name, flows[name].get("node_comment", ""))
        expand_children(items, depth + 1, row)

    def expand_children(items, depth, row):
        for it in items:
            if it["kind"] == "group":
                subs = [x for _, c in it["cases"] for x in c] if it["gkind"] == "branch" else it["items"]
                expand_children(subs, depth, row)
            elif it["kind"] == "flow":
                if it["name"] in expanded:
                    it["sub"] = t["seeabove"]
                it["parent_row"] = row
                expand(it["name"], depth, (row, it))
            elif it["kind"] == "scheduler":
                it["parent_row"] = row
                for tg in it["targets"]:
                    if aliases.get(tg, tg) == tg:
                        expand(tg, depth, (row, it))
            elif it["kind"] == "publish":
                it["parent_row"] = row
                for trig, svc in trig_by_doc.get(it["doc"], []):
                    chain = [item("entry", short(trig), t["trigger"] + " · " + t["subs"], trig), item("flow", short(svc), svc.split(":")[0], flows.get(svc, {}).get("node_comment", "") or svc, svc, expand=True)]
                    r = add_row("entry", "⟨" + short(it["doc"]) + "⟩", t["subs"], chain, depth, (row, it), None)
                    expand(svc, depth + 1, (r, chain[1]))

    # 1. notifications JDBC → document → trigger → service
    for notif, doc, source, *detail in notifications:
        chain = [item("entry", "INSERT " + source, detail[0] if detail else "", source + ("\n" + detail[0] if detail else "")), item("entry", short(notif), t["notif"] + " · 1 s", notif),
                 item("doc", "⟨" + short(doc) + "⟩", "", doc, doc)]
        for trig, svc in trig_by_doc.get(doc, []):
            chain += [item("entry", short(trig), t["trigger"], trig), item("flow", short(svc), svc.split(":")[0], flows.get(svc, {}).get("node_comment", "") or svc, svc, expand=True)]
        r = add_row("entry", t["start"], t["notif"], chain, 0)
        for trig, svc in trig_by_doc.get(doc, []):
            expand(svc, 1, (r, chain[-1]))
    # 2. UI → *.api services (deepest first)
    api = [n for n in flows if n.split(":")[0].endswith(".api")]
    if api:
        def depth_of(n, seen=()):
            if n in seen: return 0
            return 1 + max([depth_of(x, seen + (n,)) for x in infos[n] if x in flows and x not in utilities] + [0])
        api.sort(key=lambda n: -depth_of(n))
        chain = [item("flow", short(n), n.split(":")[0], flows[n].get("node_comment", "") or n, n, expand=True) for n in api]
        r = add_row("entry", t["ui"], t["ui_sub"], chain, 0)
        for it in chain:
            expand(it["name"], 1, (r, it))
    # 3. remaining triggers (document published by nobody here)
    for trig, doc, svc, *_ in triggers:
        if svc not in expanded:
            chain = [item("doc", "⟨" + short(doc) + "⟩", "", doc, doc), item("entry", short(trig), t["trigger"], trig), item("flow", short(svc), svc.split(":")[0], "", svc, expand=True)]
            r = add_row("entry", t["start"], t["trigger"], chain, 0)
            expand(svc, 1, (r, chain[-1]))
    # 4. utility services, once
    for u in sorted(utilities):
        if u not in expanded:
            expanded.add(u)
            ctx.seen_docs = set()
            add_row("util", short(u), u.split(":")[0] + " · " + t["utils"].split(" (")[0].lower(), finalize(seq(flows[u]["flow"]["nodes"], ctx, u)), 0, None, u, flows[u].get("node_comment", ""))
    return rows


# ------------------------------------------------------------------ SVG rendering
def esc(s):
    return html.escape(str(s))


def ellipsis(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


class Svg:
    def __init__(self):
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def box(self, it, x, y):
        k = it["kind"]
        it["x"], it["y"] = x, y
        w, h = it["w"], it["h"]
        if k == "group":
            col = GROUP_STYLE[it["gkind"]]
            self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="8" fill="rgba(255,255,255,.02)" stroke="{col}" stroke-dasharray="5 3" stroke-width="1.2"/>'
                     f'<text x="{x + 9:.1f}" y="{y + 13:.1f}" font-size="10.5" font-weight="600" fill="{col}">{esc(it["label"])}</text>')
            if it["gkind"] == "branch":
                cy = y + GROUP_TOP
                for lab, items in it["cases"]:
                    rh = max([CHIP_H] + [x_["h"] for x_ in items])
                    cx = x + GROUP_PAD
                    self.add(f'<text x="{cx:.1f}" y="{cy + rh / 2 + 4:.1f}" font-size="10.5" fill="#8b98a8" font-style="italic">{esc(lab or "$default")}</text>')
                    cx += text_w(lab or "$default", 10.5) + 12
                    self.chain(items, cx, cy, rh)
                    cy += rh + 8
            else:
                self.chain(it["items"], x + GROUP_PAD, y + GROUP_TOP, h - GROUP_TOP - GROUP_PAD)
            return
        fill, stroke = STYLE.get(k, STYLE["ops"])
        dash = ' stroke-dasharray="5 3"' if k in ("entry", "scheduler", "file", "ctl") else ""
        rx = 13 if k in ("util", "doc", "tx", "exit") else (10 if k in ("flow", "api") else 6)
        self.add(f'<g class="s" data-name="{esc(it.get("name") or "")}"><title>{esc(it["title"])}</title>')
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1.3"{dash}/>')
        if k == "doc":
            self.add(f'<path d="M {x + w - 10:.1f} {y:.1f} L {x + w:.1f} {y + 10:.1f} L {x + w - 10:.1f} {y + 10:.1f} z" fill="{stroke}" opacity=".7"/>')
        if h == CHIP_H:
            self.add(f'<text x="{x + w / 2:.1f}" y="{y + 17:.1f}" text-anchor="middle" font-size="11" fill="#e6edf3">{esc(ellipsis(it["label"], 44))}</text>')
        else:
            ty = y + 18 if h == BOX_H else y + 17
            self.add(f'<text x="{x + 11:.1f}" y="{ty:.1f}" font-size="12" font-weight="600" fill="#e6edf3">{esc(ellipsis(it["label"], 32))}</text>')
            if it["sub"]:
                self.add(f'<text x="{x + 11:.1f}" y="{ty + 15:.1f}" font-size="10.5" fill="#8b98a8">{esc(ellipsis(it["sub"], 38))}</text>')
            badges = " · ".join(("◷ " if short(b["name"] or "").lower().startswith(PREFIX_HINT) else "✎ ") + b["label"] for b in it["pre"] + it["post"])
            if badges:
                self.add(f'<text x="{x + 11:.1f}" y="{y + h - 8:.1f}" font-size="10" fill="#33b1ff">{esc(ellipsis(badges, 40))}</text>')
        self.add("</g>")

    def arrow(self, x1, y, x2):
        self.add(f'<path d="M {x1:.1f} {y:.1f} L {x2 - 1:.1f} {y:.1f}" stroke="#5b6f8a" stroke-width="1.5" fill="none" marker-end="url(#ar)"/>')

    def chain(self, items, x, y, rh):
        for i, it in enumerate(items):
            cy = y + (rh - it["h"]) / 2
            if i:
                self.arrow(x - GAP, y + rh / 2, x)
            self.box(it, x, cy)
            x += it["w"] + GAP
        return x


def render(services, adapters, doctypes, lang="fr", triggers=(), notifications=(), sections=None, aliases=None):
    t = T[lang]
    sections = set(sections) if sections is not None else {s["node_nsName"] for s in services}
    rows = build_rows(services, adapters, doctypes, lang, triggers, notifications, sections, aliases or {})
    svg = Svg()
    y = PAD
    for row in rows:
        x0 = PAD + row["depth"] * INDENT
        # line wrapping (new line when the sequence exceeds the width)
        lines, cur, cw = [], [], 0
        for it in row["items"]:
            if cur and x0 + HEADER_W + GAP + cw + it["w"] > MAXW:
                lines.append(cur); cur, cw = [], 0
            cur.append(it); cw += it["w"] + GAP
        if cur: lines.append(cur)
        line_h = [max([BOX_H] + [it["h"] for it in ln]) for ln in lines]
        row_h = sum(line_h) + LINE_GAP * (len(lines) - 1)
        row["y"], row["h"], row["x0"] = y, row_h, x0
        fill, stroke = STYLE["api" if row["kind"] == "api" else ("entry" if row["kind"] == "entry" else ("util" if row["kind"] == "util" else "flow"))]
        hh = min(row_h, 64)
        hy = y + (row_h - hh) / 2 if len(lines) == 1 else y
        row["hy"], row["hh"] = hy, hh
        svg.add(f'<g class="hd"><title>{esc((row["name"] or row["label"]) + chr(10) + (row["comment"] or ""))}</title>')
        body = (f'<rect x="{x0:.1f}" y="{hy:.1f}" width="{HEADER_W}" height="{hh:.1f}" rx="10" fill="{fill}" stroke="{stroke}" stroke-width="1.6"{" stroke-dasharray=\"5 3\"" if row["kind"] == "entry" else ""}/>'
                f'<text x="{x0 + 12:.1f}" y="{hy + 21:.1f}" font-size="13" font-weight="700" fill="#e6edf3">{esc(ellipsis(row["label"], 26))}</text>'
                f'<text x="{x0 + 12:.1f}" y="{hy + 37:.1f}" font-size="10.5" fill="#8b98a8">{esc(ellipsis(row["sub"], 34))}</text>')
        if row["comment"] and hh >= 60:
            body += f'<text x="{x0 + 12:.1f}" y="{hy + 53:.1f}" font-size="10" fill="#8b98a8" font-style="italic">{esc(ellipsis(row["comment"], 36))}</text>'
        svg.add(f'<a href="{esc(row["href"])}">{body}</a>' if row["href"] else body)
        svg.add("</g>")
        ly = y
        for i, ln in enumerate(lines):
            x = x0 + HEADER_W + GAP
            if i == 0:
                svg.arrow(x0 + HEADER_W, hy + hh / 2 if len(lines) == 1 else ly + line_h[0] / 2, x)
            else:
                svg.add(f'<text x="{x - 6:.1f}" y="{ly + line_h[i] / 2 + 4:.1f}" font-size="10" fill="#5b6f8a" text-anchor="end">↳ {esc(t["wrap"])}</text>')
            svg.chain(ln, x, ly, line_h[i])
            ly += line_h[i] + LINE_GAP
        # tree guide from the parent header (expansion)
        if row["parent"]:
            prow, pit = row["parent"]
            if "hy" in prow:
                px, py = prow["x0"] + 12, prow["hy"] + prow["hh"]
                svg.add(f'<path d="M {px:.1f} {py:.1f} L {px:.1f} {hy + hh / 2:.1f} L {x0 - 2:.1f} {hy + hh / 2:.1f}" stroke="#3b4d63" stroke-width="1.4" fill="none" marker-end="url(#ar2)"/>')
        y += row_h + ROW_GAP
    height = y + 52
    width = MAXW + PAD
    legend = [("flow", t["k_flow"]), ("adapter", t["k_adapter"]), ("doc", t["k_doc"]), ("util", t["k_util"]), ("external", t["k_ext"])]
    lx, ly = PAD, y + 4
    parts = [f'<text x="{lx}" y="{ly + 12}" font-size="11" font-weight="600" fill="#8b98a8">{esc(t["legend"])}</text>']
    lx += 62
    for k, lab in legend:
        f, s = STYLE[k]
        parts.append(f'<rect x="{lx}" y="{ly + 2}" width="16" height="12" rx="3" fill="{f}" stroke="{s}"/><text x="{lx + 22}" y="{ly + 12}" font-size="11" fill="#8b98a8">{esc(lab)}</text>')
        lx += 22 + text_w(lab, 11) + 26
    parts.append(f'<rect x="{lx}" y="{ly + 2}" width="16" height="12" rx="3" fill="none" stroke="#ff832b" stroke-dasharray="3 2"/><text x="{lx + 22}" y="{ly + 12}" font-size="11" fill="#8b98a8">{esc(t["k_group"])}</text>')
    out = [f'<svg class="ex" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}" data-w="{width:.0f}" role="img" aria-label="{esc(t["title"])}">',
           '<defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#5b6f8a"/></marker>'
           '<marker id="ar2" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 z" fill="#3b4d63"/></marker></defs>'
           '<style>.ex text{font-family:"IBM Plex Sans","Segoe UI",system-ui,sans-serif}.ex a .hd rect{cursor:pointer}.ex .s:hover rect{stroke-width:2.4}.ex.fit{width:100%;height:auto}</style>']
    out += svg.parts + parts + ["</svg>"]
    return "".join(out), rows


SCRIPT = """<script>
(function(){document.querySelectorAll('.graph').forEach(sec=>{const svg=sec.querySelector('svg');if(!svg)return;const wrap=svg.parentElement;
function fit(on){svg.classList.toggle('fit',on);sec.querySelectorAll('.gbtn').forEach(b=>b.classList.toggle('on',(b.dataset.fit==='1')===on));}
fit(+svg.dataset.w<=(document.documentElement.clientWidth-120)*1.25);sec.querySelectorAll('.gbtn').forEach(b=>b.addEventListener('click',()=>fit(b.dataset.fit==='1')));
if(svg.classList.contains('wf')){const nodes=[...svg.querySelectorAll('.n')],edges=[...svg.querySelectorAll('.e')];
function hi(id){if(!id){nodes.forEach(n=>n.classList.remove('dim','hi'));edges.forEach(e=>e.classList.remove('dim','hi'));return;}
const near=new Set([id]);edges.forEach(e=>{const on=e.dataset.s===id||e.dataset.d===id;e.classList.toggle('hi',on);e.classList.toggle('dim',!on);if(on){near.add(e.dataset.s);near.add(e.dataset.d);}});
nodes.forEach(n=>{const k=near.has(n.dataset.id);n.classList.toggle('hi',n.dataset.id===id);n.classList.toggle('dim',!k);});}
nodes.forEach(n=>{n.addEventListener('mouseenter',()=>hi(n.dataset.id));n.addEventListener('mouseleave',()=>hi(null));});}});})();
</script>"""
