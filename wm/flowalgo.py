""""Pseudo-algorithm" view of an IS package, to tell the scenario to a customer: every step in plain words (the flow
comment when there is one, otherwise a sentence derived from the step), numbered, with keywords (TRIGGER, FOR EACH, IF, ELSE,
ON ERROR, PUBLISH), and on the right the services and document types involved. Package services that are called
are expanded below (collapsible). HTML generated from the deployed definitions, through the extraction of wm/flowexec.py.
"""
import html, re
import flowexec
from flowexec import short, build_rows

T = {
    "fr": {"title": "Le scénario en clair : pseudo-algorithme, avec les services et documents de chaque étape",
           "hint": "À lire comme une histoire, de haut en bas. Les phrases viennent des commentaires des flows déployés (ou sont déduites de l'étape) ; "
                   "à droite, ce que webMethods exécute réellement : services du package, services adaptateur (table SQL), documents, triggers, API. "
                   "Cliquer une ligne « ▸ » pour déplier le détail d'un service.",
           "trigger": "DÉCLENCHEUR", "foreach": "POUR CHAQUE", "if": "SI", "else": "SINON", "none": "SI AUCUN", "catch": "EN CAS D'ERREUR", "publish": "PUBLIER",
           "receive": "RECEVOIR", "exit": "ARRÊTER", "tx": "TRANSACTION", "commit": "valider la transaction (commit)", "rollback": "annuler la transaction (rollback)",
           "tx_open": "ouvrir une transaction", "parallel": "en parallèle", "on_insert": "dès qu'une ligne est insérée", "notif": "webMethods la détecte (notification JDBC, scrutation toutes les secondes) et publie le document",
           "starts": "le trigger déclenche le flux", "ui": "Depuis l'interface (navigateur), l'utilisateur lance", "subs": "les abonnés reçoivent le document, indépendamment l'un de l'autre",
           "sub_line": "abonné", "schedule": "planifier l'exécution asynchrone de", "in3s": "dans 3 s", "receive_doc": "recevoir le document", "log": "journal",
           "call": "appeler", "api": "appeler l'API", "read": "lire", "insert": "insérer dans", "update": "mettre à jour", "delete": "supprimer dans", "run": "exécuter",
           "write_file": "écrire dans le fichier", "ctl": "suspendre ou reprendre", "then": "puis", "the_file": "le fichier", "utils": "Services utilitaires",
           "expand": "tout déplier", "collapse": "tout replier", "of": "de", "publish_to": "sur Universal Messaging (file durable par abonné)", "doc_out": "produit",
           "stamp": "horodatage", "sched_head": "Scheduler IS : tâche unique planifiée par", "see": "voir le bloc", "sched_then": "qui exécute",
           "verbs": {"getCurrentDateString": "horodater", "currentNanoTime": "horodater", "getCurrentDate": "horodater", "elapsedNanoTime": "mesurer la durée",
                     "generateUUID": "générer un identifiant unique", "multiplyFloats": "calculer les montants", "addInts": "calculer", "divideInts": "calculer", "divideFloats": "convertir",
                     "roundNumber": "arrondir", "documentToJSONString": "sérialiser en JSON", "jsonStringToDocument": "lire le JSON", "setResponse": "renvoyer la réponse JSON",
                     "checkFileExistence": "vérifier si le fichier existe", "deleteFile": "supprimer le fichier", "sizeOfList": "compter les lignes", "dateTimeFormat": "formater la date",
                     "getLastError": "récupérer l'erreur", "getLastFailureCaught": "récupérer l'erreur", "getTriggerReport": "lire l'état des triggers",
                     "retrievePollingNotificationData": "lire l'état de la notification", "getConnectionAliasReport": "lire l'état de la connexion UM", "incrementDate": "calculer la date",
                     "objectToString": "mettre en forme", "substring": "mettre en forme", "concat": "mettre en forme", "replace": "mettre en forme", "bytesToString": "décoder la réponse",
                     "appendToDocumentList": "ajouter à la liste", "listProfiles": "lire les profils d'API", "MAP": "préparer les données"}},
    "en": {"title": "The scenario in plain words: pseudo-algorithm with the services and documents of each step",
           "hint": "Read it top to bottom like a story. Sentences come from the comments of the deployed flows (or are derived from the step); on the right, what "
                   "webMethods really runs: package services, adapter services (SQL table), documents, triggers, API. Click a « ▸ » line to expand a service.",
           "trigger": "TRIGGER", "foreach": "FOR EACH", "if": "IF", "else": "ELSE", "none": "IF NONE", "catch": "ON ERROR", "publish": "PUBLISH",
           "receive": "RECEIVE", "exit": "STOP", "tx": "TRANSACTION", "commit": "commit the transaction", "rollback": "roll back the transaction",
           "tx_open": "open a transaction", "parallel": "in parallel", "on_insert": "as soon as a row is inserted", "notif": "webMethods detects it (JDBC notification, polled every second) and publishes the document",
           "starts": "the trigger starts the flow", "ui": "From the browser UI, the user runs", "subs": "the subscribers receive the document, independently of each other",
           "sub_line": "subscriber", "schedule": "schedule the asynchronous execution of", "in3s": "in 3 s", "receive_doc": "receive the document", "log": "log",
           "call": "call", "api": "call the API", "read": "read", "insert": "insert into", "update": "update", "delete": "delete from", "run": "run",
           "write_file": "write to the file", "ctl": "suspend or resume", "then": "then", "the_file": "the file", "utils": "Utility services",
           "expand": "expand all", "collapse": "collapse all", "of": "of", "publish_to": "on Universal Messaging (durable queue per subscriber)", "doc_out": "produces",
           "stamp": "timestamp", "sched_head": "IS scheduler: one-time task scheduled by", "see": "see block", "sched_then": "which runs",
           "verbs": {"getCurrentDateString": "timestamp", "currentNanoTime": "timestamp", "getCurrentDate": "timestamp", "elapsedNanoTime": "measure the duration",
                     "generateUUID": "generate a unique id", "multiplyFloats": "compute the amounts", "addInts": "compute", "divideInts": "compute", "divideFloats": "convert",
                     "roundNumber": "round", "documentToJSONString": "serialise to JSON", "jsonStringToDocument": "parse the JSON", "setResponse": "return the JSON response",
                     "checkFileExistence": "check whether the file exists", "deleteFile": "delete the file", "sizeOfList": "count the rows", "dateTimeFormat": "format the date",
                     "getLastError": "get the error", "getLastFailureCaught": "get the error", "getTriggerReport": "read the trigger states",
                     "retrievePollingNotificationData": "read the notification state", "getConnectionAliasReport": "read the UM connection state", "incrementDate": "compute the date",
                     "objectToString": "format", "substring": "format", "concat": "format", "replace": "format", "bytesToString": "decode the response",
                     "appendToDocumentList": "append to the list", "listProfiles": "read the API profiles", "MAP": "prepare the data"}},
}
CHIP = {"flow": "c-flow", "api": "c-api", "adapter": "c-adp", "doc": "c-doc", "external": "c-ext", "entry": "c-ent", "builtin": "c-bi", "util": "c-bi"}


def esc(s):
    return html.escape(str(s))


def chip(kind, label, title=""):
    return f'<span class="ch {CHIP.get(kind, "c-bi")}" title="{esc(title or label)}">{esc(label)}</span>'


def first_clause(s, n=220):
    s = (s or "").strip()
    s = re.split(r"(?<=[.;])\s", s)[0]
    return s if len(s) <= n else s[: n - 1] + "…"


def lower_first(s):
    return s[:1].lower() + s[1:] if s and not s[:2].isupper() else s


class Algo:
    def __init__(self, lang, adapters, tr):
        self.t, self.adapters, self.tr = T[lang], adapters, tr or (lambda x: x)
        self.lines = []

    def cm(self, s):
        return esc(lower_first(self.tr(s))) if s else ""

    # ---- one line = (html text, html annotations)
    def phrase(self, it, first=False):
        t, k = self.t, it["kind"]
        c = self.cm(it.get("comment", ""))
        sets = it.get("sets") or {}
        if k in ("flow", "api"):
            desc = first_clause(self.cm(it.get("title", ""))) if it.get("title") and it.get("title") != it["name"] else ""
            return (c or desc or f"{t['run']} {short(it['name'])}"), [chip(k, it["name"], it.get("title", ""))]
        if k == "entry":
            return f"{t['sub_line']} {esc(it['label'])} :", [chip("entry", it["label"], it["title"])]
        if k == "adapter":
            sub = self.adapters.get(it["name"], "")
            kind, _, table = sub.partition(" · ")
            verb = {"SELECT": t["read"], "INSERT": t["insert"], "BATCHINSERT": t["insert"], "UPDATE": t["update"], "DELETE": t["delete"], "WITH": t["read"]}.get(kind.upper(), t["run"])
            if table.endswith("()"):
                verb = t["call"]
            return (c or f"{verb} {table or short(it['name'])}"), [chip("adapter", short(it["name"]) + (" → " + table if table else ""), it["name"] + "\n" + sub)]
        if k == "publish":
            return (f'<b class="kw">{t["publish"]}</b> ⟨{esc(short(it["doc"]))}⟩ {t["publish_to"]}' + (f" · {c}" if c else "")), [chip("doc", "⟨" + short(it["doc"]) + "⟩", it["doc"]), chip("builtin", "pub.publish:publish")]
        if k == "scheduler":
            see = f' → <b class="kw">{t["see"]} {it["see"]}</b>' if it.get("see") else ""
            return (f"{t['schedule']} {esc(it['sub'].lstrip('→ '))} {t['in3s']}" + (f" · {c}" if c else "") + see), [chip("entry", "pub.scheduler:addOneTimeTask", it["title"])]
        if k == "file":
            return (c or f"{t['write_file']} {esc(it['label'].split(' ', 1)[-1])}"), [chip("entry", it["label"], it["title"])]
        if k == "tx":
            lab = it["label"]
            return (t["tx_open"] if "▶" in lab else (t["commit"] if "✓" in lab else t["rollback"])), [chip("builtin", it["name"])]
        if k == "external":
            path = re.sub(r"%([^%]+)%", lambda m: "{" + m.group(1).split("/")[-1] + "}", sets.get("path", ""))
            auto = f"{t['api']} {sets.get('method', '').upper()} {path}".strip() + (f" ({sets.get('alias')})" if sets.get("alias") else "")
            return (c or auto), [chip("external", it["name"], it["title"])]
        if k == "ctl":
            return (c or f"{t['ctl']} ({it['sub']})"), [chip("builtin", it["name"])]
        if k == "ops":
            cms = [self.cm(x) for x in it.get("comments", [])]
            verbs = list(dict.fromkeys(t["verbs"][short(n)] for n in it.get("names", []) if short(n) in t["verbs"]))
            txt = " ; ".join(cms) if cms else ", ".join(verbs[:3])
            if not txt and it.get("sets"):
                txt = esc(", ".join(f"{k_} = {v}" for k_, v in it["sets"][:2]))
            if not txt:
                return None, []
            return txt, [chip("builtin", short(n), n) for n in it.get("names", [])[:4]] + ([chip("builtin", f"+{len(it['names']) - 4}")] if len(it.get("names", [])) > 4 else [])
        if k == "util":
            return f"{t['log']} : {esc(it['label'].split(' ', 1)[-1] if ' ' in it['label'] else it['label'])}", [chip("util", it["name"])]
        if k == "doc":
            lab = it["label"]
            return (f'<b class="kw">{t["receive"]}</b> {esc(lab.split(" ", 1)[-1])}' if lab.startswith(("reçoit", "receives")) else f"{t['doc_out']} {esc(lab)}"), [chip("doc", lab.split(" ", 1)[-1] if " " in lab else lab, it["title"])]
        if k == "exit":
            return f'<b class="kw">{t["exit"]}</b> ({esc(it.get("signal", ""))}{(" : " + esc(it["message"])) if it.get("message") else ""})', []
        return esc(it["label"]), []

    def suffix(self, it):
        """attached utility services (log, timestamp): at the end of the line, discreet."""
        utils = it.get("pre", []) + it.get("post", [])
        if not utils:
            return ""
        def lab(u):
            tag = u["label"].split(" ", 1)[1] if " " in u["label"] else ""
            if short(u["name"] or "").lower().startswith(flowexec.PREFIX_HINT):
                return self.t["stamp"]
            return (self.t["log"] + " : " + tag) if tag else short(u["name"] or u["label"])
        return ' <span class="ut">+ ' + " · ".join(esc(lab(u)) for u in utils) + "</span>"

    def render_items(self, items, num, children_by_item, depth, force_open=False):
        out, i = [], 0
        for it in items:
            if it["kind"] == "group":
                i += 1
                n = f"{num}.{i}" if num else str(i)
                out.append(self.render_group(it, n, children_by_item, depth, force_open))
                continue
            txt, ann = self.phrase(it)
            if txt is None and it["kind"] == "ops":
                continue
            i += 1
            n = f"{num}.{i}" if num else str(i)
            kids = children_by_item.get(id(it), [])
            line = self.line(n, txt + self.suffix(it), ann, depth, expandable=bool(kids))
            if kids:
                pub = it["kind"] == "publish"
                intro = self.line("", f'<i>{self.t["subs"]} :</i>', [], depth + 1) if pub else ""
                inner = "".join(self.render_row(r, n, children_by_item, depth + 1, force_open=pub) for r in kids)
                opened = pub or force_open or depth <= 1
                out.append(f'<details{" open" if opened else ""}><summary>{line}</summary><div class="sub">{intro}{inner}</div></details>')
            else:
                out.append(line)
        return "".join(out)

    def render_group(self, it, n, children_by_item, depth, force_open=False):
        t, g = self.t, it["gkind"]
        c = self.cm(it.get("comment", ""))
        if g == "loop":
            par = f" · ×{it['threads']} {t['parallel']}" if it.get("threads", "1") not in ("1", "") else ""
            head = f'<b class="kw">{t["foreach"]}</b> {esc(it.get("array", ""))}{par}' + (f" : {c}" if c else "")
            return self.line(n, head, [], depth) + f'<div class="sub">{self.render_items(it["items"], n, children_by_item, depth + 1, force_open)}</div>'
        if g == "catch":
            head = f'<b class="kw">{t["catch"]}</b>' + (f" : {c}" if c else "")
            return self.line(n, head, [], depth) + f'<div class="sub">{self.render_items(it["items"], n, children_by_item, depth + 1, force_open)}</div>'
        # branch
        head = f'<b class="kw">{t["if"]}</b> {esc(it.get("switch") or "")}' + (f" ({c})" if c else "")
        parts = [self.line(n, head, [], depth)]
        for j, (lab, items) in enumerate(it["cases"]):
            kw = t["else"] if lab == "$default" else (t["none"] if lab == "$null" else f"{t['if']} = {esc(lab)}")
            sub = self.render_items(items, f"{n}.{j + 1}", children_by_item, depth + 2, force_open)
            parts.append(f'<div class="sub">{self.line(f"{n}.{j + 1}", f"<b class=\"kw\">{kw}</b> :", [], depth + 1)}<div class="sub">{sub}</div></div>')
        return "".join(parts)

    def line(self, n, txt, ann, depth, expandable=False):
        n = n if n.count(".") < 3 else ""
        return (f'<div class="ln d{min(depth, 5)}"><span class="num">{esc(n)}</span><span class="txt">{"<span class=\"tri\">▸</span> " if expandable else ""}{txt}</span>'
                f'<span class="an">{"".join(ann)}</span></div>')

    def render_row(self, row, num, children_by_item, depth, force_open=False):
        """An expanded line = the content of the service (without repeating its header, already carried by the parent line)."""
        return self.render_items(row["items"], num, children_by_item, depth, force_open)


def render(services, adapters, doctypes, lang="fr", triggers=(), notifications=(), sections=None, aliases=None, tr=None):
    t = T[lang]
    sections = set(sections) if sections is not None else {s["node_nsName"] for s in services}
    rows = build_rows(services, adapters, doctypes, lang, triggers, notifications, sections, aliases or {})
    children_by_item = {}
    for r in rows:
        if r["parent"]:
            children_by_item.setdefault(id(r["parent"][1]), []).append(r)
    a = Algo(lang, adapters, tr)
    blocks, k = [], 0
    tops = [r for r in rows if not r["parent"] and r["kind"] != "util"]
    # executions scheduled by the scheduler: triggers in their own right (block after the UI block)
    sched = [r for r in rows if r["parent"] and r["parent"][1]["kind"] == "scheduler"]
    for r in sched:
        children_by_item[id(r["parent"][1])] = [x for x in children_by_item.get(id(r["parent"][1]), []) if x is not r]
    order = []
    for r in tops:
        order.append(r)
        if r["label"] == flowexec.T[lang]["ui"]:
            order.extend(sched)
    for idx, r in enumerate(order):
        if r["parent"]:
            r["parent"][1]["see"] = idx + 1
    for r in order:
        k += 1
        items = r["items"]
        if r["parent"]:      # "scheduler" block
            caller = r["parent"][0]
            head = f'<b class="kw">{t["trigger"]}</b> : {t["sched_head"]} {esc(caller["label"])} (+3 s), {t["sched_then"]} :'
            blocks.append(a.line(str(k), head, [], 0))
            it = {"kind": "flow", "name": r["name"], "title": r["comment"] or r["name"], "comment": "", "pre": [], "post": []}
            txt, ann = a.phrase(it)
            line = a.line(f"{k}.1", txt, ann, 1, expandable=True)
            blocks.append(f'<div class="sub"><details open><summary>{line}</summary><div class="sub">{a.render_items(items, f"{k}.1", children_by_item, 2)}</div></details></div>')
            continue
        if r["kind"] == "entry":
            ui = flowexec.T[lang]["ui"]
            is_ui = r["label"] == ui
            n_open = (1 if r is order[0] else 0) if is_ui else 99      # UI: only the first service opened, and only when the UI is the first trigger
            opened = 0
            src = next((x for x in items if x["kind"] == "entry" and x["label"].startswith("INSERT")), None)
            if r["label"] == ui:
                head = f'<b class="kw">{t["trigger"]}</b> : {t["ui"]} :'
            elif src:
                head = f'<b class="kw">{t["trigger"]}</b> : {t["on_insert"]} ({esc(src["label"])} · {esc(src["sub"])})'
            else:
                head = f'<b class="kw">{t["trigger"]}</b> : {esc(r["label"])}'
            blocks.append(a.line(str(k), head, [], 0))
            inner, i = [], 0
            for it in items:
                if it is src:
                    continue
                if it["kind"] == "entry":
                    is_notif = it["sub"].startswith(flowexec.T[lang]["notif"])
                    txt = t["notif"] if is_notif else f"{t['starts']} ↓"
                    i += 1; inner.append(a.line(f"{k}.{i}", txt, [chip("entry", it["label"], it["title"])], 1))
                elif it["kind"] == "doc":
                    if inner:
                        inner[-1] = inner[-1].replace('<span class="an">', '<span class="an">' + chip("doc", it["label"], it["title"]), 1)
                    else:
                        i += 1; inner.append(a.line(f"{k}.{i}", f"{t['receive_doc']} {esc(it['label'])}", [chip("doc", it["label"], it["title"])], 1))
                elif it["kind"] in ("flow", "api"):
                    i += 1
                    n = f"{k}.{i}"
                    txt, ann = a.phrase(it)
                    kids = children_by_item.get(id(it), [])
                    line = a.line(n, txt, ann, 1, expandable=bool(kids))
                    if kids:
                        body = "".join(a.render_row(rr, n, children_by_item, 2) for rr in kids)
                        opened += 1
                        inner.append(f'<details{" open" if opened <= n_open else ""}><summary>{line}</summary><div class="sub">{body}</div></details>')
                    else:
                        inner.append(line)
            blocks.append(f'<div class="sub">{"".join(inner)}</div>')
    utils = [r for r in rows if r["kind"] == "util"]
    if utils:
        k += 1
        blocks.append(a.line(str(k), f'<b class="kw">{t["utils"]}</b>', [], 0))
        inner = []
        for j, r in enumerate(utils):
            n = f"{k}.{j + 1}"
            body = a.render_items(r["items"], n, children_by_item, 2)
            inner.append(f'<details><summary>{a.line(n, first_clause(a.cm(r["comment"])) or esc(short(r["name"])), [chip("flow", r["name"], r["comment"])], 1, expandable=True)}</summary><div class="sub">{body}</div></details>')
        blocks.append(f'<div class="sub">{"".join(inner)}</div>')
    return '<div class="algo">' + "".join(blocks) + "</div>"


STYLE = """
.algo{font-size:13.5px;line-height:1.45} .algo .ln{display:grid;grid-template-columns:58px minmax(0,1fr) minmax(220px,36%);gap:10px;align-items:start;padding:3px 0;border-bottom:1px solid rgba(42,53,66,.45)}
.algo .num{color:#8b98a8;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:11.5px;padding-top:2px} .algo .txt{color:#e6edf3} .algo .kw{color:#f1c21b;font-weight:700;letter-spacing:.3px}
.algo .an{display:flex;flex-wrap:wrap;gap:4px;justify-content:flex-end} .algo .ch{font-size:10.5px;padding:1px 7px;border-radius:999px;border:1px solid #2a3542;color:#8b98a8;white-space:nowrap;font-family:"IBM Plex Mono",ui-monospace,monospace}
.algo .c-flow{color:#4589ff;border-color:#4589ff} .algo .c-api{color:#f1c21b;border-color:#f1c21b} .algo .c-adp{color:#42be65;border-color:#42be65} .algo .c-doc{color:#a56eff;border-color:#a56eff}
.algo .c-ext{color:#ff7eb6;border-color:#ff7eb6} .algo .c-ent{color:#33b1ff;border-color:#33b1ff} .algo .sub{margin-left:26px;border-left:1px solid #2a3542;padding-left:10px}
.algo .ut{color:#8b98a8;font-size:12px} .algo summary{list-style:none;cursor:pointer} .algo summary::-webkit-details-marker{display:none} .algo .tri{color:#33b1ff;display:inline-block;transition:transform .15s}
.algo details[open]>summary .tri{transform:rotate(90deg)} .algo details>summary:hover .txt{color:#33b1ff}
"""
SCRIPT = """<script>
document.querySelectorAll('[data-algo]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.algo details').forEach(d=>d.open=b.dataset.algo==='1');}));
</script>"""
