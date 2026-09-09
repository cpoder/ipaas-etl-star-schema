#!/usr/bin/env python3
"""Generation and deployment of the StarSchemaETL flow services through the putNode API (MCP tool put_node).

Each flow is described in Python with a small builder (copy/setv/delete/invoke/loop/branch/repeat/try_catch)
that produces the JSON tree expected by wm.server.ns:putNode (explicit WmPath paths /field;type;dim).

Usage: flows.py [service_name ...]   (no argument: deploy everything)
"""
import json, os, sys
from xml.sax.saxutils import escape
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpcli import Mcp

PKG = "StarSchemaETL"
DOC_FACTROW = "star.docs:FactRow"
DOC_FACT = "star.docs:Fact"
DOC_DATEROW = "star.docs:DateRow"
DOC_DIMDATE = "star.docs:DimDate"
DOC_CHUNK = "star.docs:Chunk"

# ------------------------------------------------------------------ builder
def copy(frm, to):
    return {"type": "MAPCOPY", "from": frm, "to": to}

def setv(field, value, variables=False, overwrite=True):
    d = {"type": "MAPSET", "field": field, "overwrite": "true" if overwrite else "false",
         "d_enc": "XMLValues", "mapseti18n": "true",
         "data": f'<Values version="2.0"><value name="xml">{escape(value)}</value></Values>'}
    if variables:
        d["variables"] = "true"
    return d

def delete(*fields):
    return [{"type": "MAPDELETE", "field": f} for f in fields]

def flat(items):
    out = []
    for i in items:
        out.extend(i) if isinstance(i, list) else out.append(i)
    return out

def mapstep(*nodes, comment=None):
    d = {"type": "MAP", "mode": "STANDALONE", "nodes": flat(nodes)}
    if comment: d["comment"] = comment
    return d

def invoke(service, inp=(), out=(), comment=None):
    d = {"type": "INVOKE", "service": service, "validate-in": "$none", "validate-out": "$none",
         "nodes": [{"type": "MAP", "mode": "INPUT", "nodes": flat(inp)},
                   {"type": "MAP", "mode": "OUTPUT", "nodes": flat(out)}]}
    if comment: d["comment"] = comment
    return d

def sequence(*nodes, label=None, exit_on="FAILURE", form=None, comment=None):
    d = {"type": "SEQUENCE", "exit-on": exit_on, "nodes": flat(nodes)}
    if label is not None: d["label"] = label
    if form: d["form"] = form
    if comment: d["comment"] = comment
    return d

def try_catch(try_nodes, catch_nodes):
    return [sequence(*try_nodes, form="TRY"), sequence(*catch_nodes, form="CATCH")]

def loop(in_array, out_array, *nodes, comment=None):
    d = {"type": "LOOP", "in-array": in_array, "nodes": flat(nodes)}
    if out_array: d["out-array"] = out_array
    if comment: d["comment"] = comment
    return d

def branch(switch, *cases, comment=None):
    """cases: (label, [nodes])"""
    d = {"type": "BRANCH", "switch": switch, "nodes": [sequence(*n, label=l) for l, n in cases]}
    if comment: d["comment"] = comment
    return d

def branch_expr(*cases, comment=None):
    """cases: (expression, [nodes]) -> SEQUENCE label=expression"""
    d = {"type": "BRANCH", "label-expressions": "true", "nodes": [sequence(*n, label=e) for e, n in cases]}
    if comment: d["comment"] = comment
    return d

def repeat(*nodes, count="-1", repeat_on="SUCCESS", interval="0", comment=None):
    d = {"type": "REPEAT", "count": count, "repeat-on": repeat_on, "repeat-interval": interval, "nodes": flat(nodes)}
    if comment: d["comment"] = comment
    return d

def exit_(from_="$flow", signal="FAILURE", message=None):
    d = {"type": "EXIT", "from": from_, "signal": signal}
    if message: d["failure-message"] = message
    return d

def field(name, ftype="string", dim=0, doc=None):
    if ftype == "recref":
        return {"node_type": "record", "field_name": name, "field_type": "recref", "field_dim": str(dim), "nillable": "true", "rec_ref": doc, "rec_closed": "true"}
    if ftype == "record":
        return {"node_type": "record", "field_name": name, "field_type": "record", "field_dim": str(dim), "nillable": "true", "rec_fields": []}
    d = {"node_type": "field", "field_name": name, "field_type": ftype, "field_dim": str(dim), "nillable": "true"}
    if ftype == "object":
        d["wrapper_type"] = "java.lang.Object"
    return d

def sig(*fields):
    return {"node_type": "record", "field_type": "record", "field_dim": "0", "nillable": "true",
            "javaclass": "com.wm.util.Values", "rec_fields": list(fields)}

def service(ns, sig_in, sig_out, nodes, comment=""):
    return {"node_nsName": ns, "node_pkg": PKG, "node_type": "service", "svc_type": "flow", "svc_subtype": "default",
            "svc_sigtype": "java 3.5", "stateless": "yes", "pipeline_option": 1, "node_comment": comment,
            "svc_sig": {"sig_in": sig_in, "sig_out": sig_out},
            "flow": {"type": "ROOT", "version": "3.0", "cleanup": "true", "nodes": flat(nodes)}}

def doctype(ns, names):
    return {"node_nsName": ns, "node_pkg": PKG, "node_type": "record", "field_type": "record", "field_dim": "0",
            "nillable": "true", "rec_fields": [field(n) for n in names]}

# ------------------------------------------------------------------ shared building blocks
def tx_start(name):
    return invoke("pub.art.transaction:startTransaction",
                  inp=[setv("/startTransactionInput;2;0/transactionName;1;0", name)],
                  out=[copy("/startTransactionOutput;2;0/transactionName;1;0", "/txName;1;0"),
                       delete("/startTransactionOutput;2;0", "/startTransactionInput;2;0")],
                  comment="start local transaction (star.connections:dwh)")

TX_COMMIT = invoke("pub.art.transaction:commitTransaction",
                   inp=[copy("/txName;1;0", "/commitTransactionInput;2;0/transactionName;1;0")],
                   out=[delete("/commitTransactionInput;2;0", "/txName;1;0")], comment="commit")

def catch_block(label):
    return [
        invoke("pub.flow:getLastFailureCaught", out=[copy("/failureMessage;1;0", "/errorMsg;1;0"), delete("/failureMessage;1;0", "/failureName;1;0", "/failure;3;0")]),
        branch("/txName",
               ("$null", []),
               ("$default", [invoke("pub.art.transaction:rollbackTransaction",
                                    inp=[copy("/txName;1;0", "/rollbackTransactionInput;2;0/transactionName;1;0")],
                                    out=[delete("/rollbackTransactionInput;2;0", "/txName;1;0")], comment="rollback")]),
               comment="rollback if a transaction is open"),
        exit_("$flow", "FAILURE", f"{label}: %errorMsg%"),
    ]

def size_of(listpath, target="/rowCount;1;0"):
    return invoke("pub.list:sizeOfList", inp=[copy(listpath, "/fromList;3;1")],
                  out=[copy("/size;1;0", target), delete("/size;1;0", "/fromList;3;1")], comment="row count")

def batch_insert(svc, listpath):
    return invoke(f"star.adapters:{svc}", inp=[copy(listpath, f"/{svc}Input;2;0/inputs;2;1")],
                  out=[delete(f"/{svc}Input;2;0", f"/{svc}Output;2;0")], comment="JDBC BatchInsert (a single executeBatch)")

def now_string(pattern, target):
    return invoke("pub.date:getCurrentDateString", inp=[setv("/pattern;1;0", pattern)],
                  out=[copy("/value;1;0", target), delete("/value;1;0", "/pattern;1;0")])

def add_ints(a, b_path_or_const, target, const=False):
    inp = [copy(a, "/num1;1;0"), setv("/num2;1;0", b_path_or_const) if const else copy(b_path_or_const, "/num2;1;0")]
    return invoke("pub.math:addInts", inp=inp, out=[copy("/value;1;0", target), delete("/value;1;0", "/num1;1;0", "/num2;1;0")])

# ------------------------------------------------------------------ simple dimensions
def dim_loader(name, select_svc, insert_svc, listvar, comment):
    lp = f"/{listvar};2;1"
    return service(f"star.etl.steps:{name}", sig(), sig(field("rowCount")), try_catch([
        tx_start("tx" + name[0].upper() + name[1:]),
        invoke(f"star.adapters:{select_svc}",
               out=[copy(f"/{select_svc}Output;2;0/results;2;1", lp), delete(f"/{select_svc}Output;2;0")],
               comment="SELECT DISTINCT extraction from staging.orders"),
        size_of(lp),
        batch_insert(insert_svc, lp),
        mapstep(delete(lp)),
        TX_COMMIT,
    ], catch_block(name)), comment)

# ------------------------------------------------------------------ time dimension
D = f"/dates;4;0;{DOC_DIMDATE}"

def fmt(pattern, target, locale=None, comment="", variables=False):
    inp = [copy("/d;1;0", "/inString;1;0"), setv("/currentPattern;1;0", "yyyy-MM-dd"), setv("/newPattern;1;0", pattern, variables=variables)]
    out = [copy("/value;1;0", f"{D}/{target};1;0"), delete("/value;1;0", "/inString;1;0", "/currentPattern;1;0", "/newPattern;1;0")]
    if locale:  # locale taken from the pipeline (dimLocale: fr_FR or en_GB depending on the demo language)
        inp.append(copy("/dimLocale;1;0", "/locale;1;0")); out.append(delete("/locale;1;0"))
    return invoke("pub.date:dateTimeFormat", inp=inp, out=out, comment=comment)

def set_weekend(v):
    return [mapstep(setv(f"{D}/is_weekend;1;0", v))]

LOAD_DATES = service("star.etl.steps:loadDates", sig(field("dimLocale"), field("quarterLetter"), field("weekLetter")), sig(field("rowCount")), try_catch([
    mapstep(setv("/dimLocale;1;0", "fr_FR", overwrite=False), setv("/quarterLetter;1;0", "T", overwrite=False), setv("/weekLetter;1;0", "S", overwrite=False),
            comment="dimension locale: fr_FR / T / S by default, en_GB / Q / W for an English demo (ISO weeks)"),
    tx_start("txLoadDates"),
    invoke("star.adapters:selectDates",
           out=[copy("/selectDatesOutput;2;0/results;2;1", f"/rawDates;4;1;{DOC_DATEROW}"), delete("/selectDatesOutput;2;0")],
           comment="distinct dates of the source"),
    loop("/rawDates", "/dates",
         mapstep(copy(f"/rawDates;4;0;{DOC_DATEROW}/order_date;1;0", "/d;1;0"),
                 copy(f"/rawDates;4;0;{DOC_DATEROW}/order_date;1;0", f"{D}/full_date;1;0")),
         fmt("yyyyMMdd", "date_key", None, "yyyymmdd key"),
         fmt("yyyy", "year_num", None, "year"),
         fmt("M", "month_num", None, "month"),
         fmt("MMMM", "month_name", "fr_FR", "month name (locale)"),
         fmt("yyyy-MM", "year_month", None, "year-month"),
         fmt("w", "week_of_year", "fr_FR", "ISO week (Monday first, 4-day rule)"),
         fmt("YYYY-'%weekLetter%'ww", "year_week", "fr_FR", "ISO year + week, e.g. 2025-W01 (en) / 2025-S01 (fr)", variables=True),
         fmt("d", "day_of_month", None, "day of month"),
         fmt("u", "day_of_week", None, "1 = Monday ... 7 = Sunday"),
         fmt("EEEE", "day_name", "fr_FR", "day name (locale)"),
         invoke("pub.math:addInts", inp=[copy(f"{D}/month_num;1;0", "/num1;1;0"), setv("/num2;1;0", "2")],
                out=[copy("/value;1;0", "/tmp;1;0"), delete("/value;1;0", "/num1;1;0", "/num2;1;0")], comment="quarter = (month + 2) / 3"),
         invoke("pub.math:divideInts", inp=[copy("/tmp;1;0", "/num1;1;0"), setv("/num2;1;0", "3")],
                out=[copy("/value;1;0", f"{D}/quarter_num;1;0"), delete("/value;1;0", "/num1;1;0", "/num2;1;0", "/tmp;1;0")]),
         mapstep(setv(f"{D}/quarter_label;1;0", "%dates/year_num%-%quarterLetter%%dates/quarter_num%", variables=True), comment="label 2024-Q3 (en) / 2024-T3 (fr)"),
         branch("/dates/day_of_week", ("6", set_weekend("true")), ("7", set_weekend("true")), ("$default", set_weekend("false")),
                comment="weekend if Saturday or Sunday"),
         mapstep(delete("/d;1;0")),
         comment="one iteration per date: calendar attributes computed here"),
    size_of(f"/dates;4;1;{DOC_DIMDATE}"),
    batch_insert("insertDates", f"/dates;4;1;{DOC_DIMDATE}"),
    mapstep(delete(f"/dates;4;1;{DOC_DIMDATE}", f"/rawDates;4;1;{DOC_DATEROW}")),
    TX_COMMIT,
], catch_block("loadDates")),
    "Time dimension: for each distinct date of staging.orders, the flow computes the calendar attributes, then BatchInsert into dwh.dim_date. One transaction.")

# ------------------------------------------------------------------ fact batch
R = f"/rows;4;0;{DOC_FACTROW}"
F = f"/facts;4;0;{DOC_FACT}"
FACT_COLS = ["order_line_id", "order_id", "date_key", "customer_key", "salesrep_key", "product_key", "quantity", "unit_price"]

LOAD_FACT_CHUNK = service("star.etl.steps:loadFactChunk", sig(field("fromId"), field("toId")), sig(field("rowCount")), try_catch([
    tx_start("txFactChunk"),
    invoke("star.adapters:selectFactChunk",
           inp=[copy("/fromId;1;0", "/selectFactChunkInput;2;0/from_id;1;0"), copy("/toId;1;0", "/selectFactChunkInput;2;0/to_id;1;0")],
           out=[copy("/selectFactChunkOutput;2;0/results;2;1", f"/rows;4;1;{DOC_FACTROW}"),
                delete("/selectFactChunkOutput;2;0", "/selectFactChunkInput;2;0")],
           comment="batch extraction + dimension key lookup (SQL join)"),
    loop("/rows", "/facts",
         mapstep(*[copy(f"{R}/{c};1;0", f"{F}/{c};1;0") for c in FACT_COLS], comment="projection to the fact table"),
         invoke("pub.math:multiplyFloats",
                inp=[copy(f"{R}/quantity;1;0", "/num1;1;0"), copy(f"{R}/unit_price;1;0", "/num2;1;0"), setv("/precision;1;0", "2")],
                out=[copy("/value;1;0", f"{F}/amount;1;0"), delete("/value;1;0", "/num1;1;0", "/num2;1;0", "/precision;1;0")],
                comment="amount = quantity x unit price"),
         comment="row-by-row transformation"),
    size_of(f"/facts;4;1;{DOC_FACT}"),
    batch_insert("insertFacts", f"/facts;4;1;{DOC_FACT}"),
    mapstep(delete(f"/facts;4;1;{DOC_FACT}", f"/rows;4;1;{DOC_FACTROW}")),
    TX_COMMIT,
], catch_block("loadFactChunk")),
    "Transactional sub-flow: loads the order_line_id rows in ]fromId, toId] into dwh.fact_sales (extraction + SQL lookup, amount computed in the flow, BatchInsert). Rollback on error.")

TRUNCATE_STAR = service("star.etl.steps:truncateStar", sig(), sig(field("rowCount")), try_catch([
    tx_start("txTruncate"),
    invoke("star.adapters:truncateStar", out=[delete("/truncateStarOutput;2;0")], comment="dwh.truncate_star()"),
    mapstep(setv("/rowCount;1;0", "0")),
    TX_COMMIT,
], catch_block("truncateStar")), "Empties the star schema (facts + dimensions, sequences restarted).")

# ------------------------------------------------------------------ logging
BEGIN_STEP = service("star.etl.steps:beginStep", sig(), sig(field("stepStart"), field("stepNano", "object")), [
    now_string("yyyy-MM-dd HH:mm:ss.SSS", "/stepStart;1;0"),
    invoke("pub.date:currentNanoTime", out=[copy("/nanoTime;3;0", "/stepNano;3;0"), delete("/nanoTime;3;0")]),
], "Step start timestamp (readable date + nanosecond counter).")

def log_step(objtostring_out):
    return service("star.etl.steps:logStep",
        sig(field("runId"), field("stepName"), field("startedAt"), field("startNano", "object"), field("rowCount"), field("status"), field("message")),
        sig(field("durationMs"), field("endedAt")), [
        now_string("yyyy-MM-dd HH:mm:ss.SSS", "/endedAt;1;0"),
        invoke("pub.date:elapsedNanoTime", inp=[copy("/startNano;3;0", "/nanoTime;3;0")],
               out=[copy("/elapsedNanoTime;3;0", "/elapsedNs;3;0"), delete("/elapsedNanoTime;3;0", "/elapsedNanoTimeStr;1;0", "/nanoTime;3;0")]),
        invoke("pub.string:objectToString", inp=[copy("/elapsedNs;3;0", "/object;3;0")],
               out=[copy(f"/{objtostring_out};1;0", "/elapsedNsStr;1;0"), delete(f"/{objtostring_out};1;0", "/object;3;0", "/elapsedNs;3;0")]),
        invoke("pub.math:divideFloats", inp=[copy("/elapsedNsStr;1;0", "/num1;1;0"), setv("/num2;1;0", "1000000"), setv("/precision;1;0", "0")],
               out=[copy("/value;1;0", "/msFloat;1;0"), delete("/value;1;0", "/num1;1;0", "/num2;1;0", "/precision;1;0", "/elapsedNsStr;1;0")], comment="ns -> ms"),
        invoke("pub.math:roundNumber", inp=[copy("/msFloat;1;0", "/num;1;0"), setv("/numberOfDigits;1;0", "0")],
               out=[copy("/roundedNumber;1;0", "/durationMs;1;0"), delete("/roundedNumber;1;0", "/num;1;0", "/numberOfDigits;1;0", "/msFloat;1;0")]),
        invoke("star.adapters:insertLog",
               inp=[copy("/runId;1;0", "/insertLogInput;2;0/run_id;1;0"), copy("/stepName;1;0", "/insertLogInput;2;0/step_name;1;0"),
                    copy("/startedAt;1;0", "/insertLogInput;2;0/started_at;1;0"), copy("/endedAt;1;0", "/insertLogInput;2;0/ended_at;1;0"),
                    copy("/rowCount;1;0", "/insertLogInput;2;0/row_count;1;0"), copy("/durationMs;1;0", "/insertLogInput;2;0/duration_ms;1;0"),
                    copy("/status;1;0", "/insertLogInput;2;0/status;1;0"), copy("/message;1;0", "/insertLogInput;2;0/message;1;0")],
               out=[delete("/insertLogInput;2;0", "/insertLogOutput;2;0")], comment="dwh.etl_run_log (non-transactional connection: visible immediately)"),
    ], "Logs a step into dwh.etl_run_log with its duration (ms) computed by the flow.")

# ------------------------------------------------------------------ orchestrator
def step_block(svc, step_name, comment):
    return [
        invoke("star.etl.steps:beginStep"),
        invoke(f"star.etl.steps:{svc}", comment=comment),
        invoke("star.etl.steps:logStep",
               inp=[copy("/stepStart;1;0", "/startedAt;1;0"), copy("/stepNano;3;0", "/startNano;3;0"),
                    setv("/stepName;1;0", step_name), setv("/status;1;0", "DONE")],
               out=[delete("/durationMs;1;0", "/endedAt;1;0", "/stepStart;1;0", "/stepNano;3;0", "/rowCount;1;0",
                           "/stepName;1;0", "/startedAt;1;0", "/startNano;3;0", "/status;1;0")]),
    ]

def run_pipeline(name, threads):
    """Orchestrator; threads = number of batches loaded at the same time (static MAX-THREADS of the LOOP)."""
    l = loop("/chunks", None,
             invoke("star.adapters:selectStopFlag",
                    out=[copy("/selectStopFlagOutput;2;0/results[0];2;1/ctl_value;1;0", "/stopFlag;1;0"), delete("/selectStopFlagOutput;2;0")],
                    comment="stop flag (dwh.etl_control)"),
             branch("/stopFlag",
                    ("true", [mapstep(delete("/stopFlag;1;0"), comment="stop requested: batch skipped (parallel-LOOP safe)")]),
                    ("$default", [
                        mapstep(copy(f"/chunks;4;0;{DOC_CHUNK}/chunk_no;1;0", "/chunkNo;1;0"), copy(f"/chunks;4;0;{DOC_CHUNK}/from_id;1;0", "/fromId;1;0"),
                                copy(f"/chunks;4;0;{DOC_CHUNK}/to_id;1;0", "/toId;1;0"), comment="bounds of the current batch"),
                        invoke("star.etl.steps:beginStep"),
                        invoke("star.etl.steps:loadFactChunk", comment="transactional sub-flow: one batch"),
                        invoke("star.etl.steps:logStep",
                               inp=[copy("/stepStart;1;0", "/startedAt;1;0"), copy("/stepNano;3;0", "/startNano;3;0"),
                                    setv("/stepName;1;0", "FACT_CHUNK_%chunkNo%", variables=True), setv("/status;1;0", "DONE"),
                                    setv("/message;1;0", "order_line_id %fromId%-%toId%", variables=True)],
                               out=[delete("/durationMs;1;0", "/endedAt;1;0", "/stepStart;1;0", "/stepNano;3;0", "/rowCount;1;0",
                                           "/stepName;1;0", "/startedAt;1;0", "/startNano;3;0", "/status;1;0", "/message;1;0")]),
                        mapstep(delete("/fromId;1;0", "/toId;1;0", "/chunkNo;1;0", "/stopFlag;1;0")),
                    ]), comment="stop requested?"),
             comment=f"one batch per iteration, {threads} in parallel (sub-flow < 5 min)")
    l["max-threads"] = str(threads)
    l["parallel-error-handling"] = "reportError"
    return service(f"star.etl:{name}", sig(field("chunkSize"), field("lang")),
        sig(field("runId"), field("status"), field("totalRows"), field("durationMs")), [
        mapstep(setv("/chunkSize;1;0", "20000", overwrite=False), setv("/lang;1;0", "fr", overwrite=False), setv("/totalRows;1;0", "0"),
                setv("/pipeStatus;1;0", "RUNNING"), setv("/threads;1;0", str(threads)), comment="default values"),
        branch("/lang",
               ("en", [mapstep(setv("/dimLocale;1;0", "en_GB"), setv("/quarterLetter;1;0", "Q"), setv("/weekLetter;1;0", "W"))]),
               ("$default", [mapstep(setv("/dimLocale;1;0", "fr_FR"), setv("/quarterLetter;1;0", "T"), setv("/weekLetter;1;0", "S"))]),
               comment="time dimension language"),
        now_string("'RUN-'yyyyMMdd-HHmmss", "/runId;1;0"),
        invoke("star.etl.steps:beginStep", out=[copy("/stepStart;1;0", "/pipeStart;1;0"), copy("/stepNano;3;0", "/pipeNano;3;0"),
                                                  delete("/stepStart;1;0", "/stepNano;3;0")]),
        invoke("star.adapters:insertLog",
               inp=[copy("/runId;1;0", "/insertLogInput;2;0/run_id;1;0"), copy("/pipeStart;1;0", "/insertLogInput;2;0/started_at;1;0"),
                    setv("/insertLogInput;2;0/step_name;1;0", "PIPELINE"), setv("/insertLogInput;2;0/status;1;0", "RUNNING"),
                    setv("/insertLogInput;2;0/message;1;0", "chunk=%chunkSize% threads=%threads% lang=%lang%", variables=True)],
               out=[delete("/insertLogInput;2;0", "/insertLogOutput;2;0")], comment="PIPELINE row set to RUNNING (visible to the UI)"),
        *try_catch([
            *step_block("truncateStar", "TRUNCATE_STAR", "truncate the star schema"),
            *step_block("loadDates", "DIM_DATE", "time dimension"),
            *step_block("loadCustomers", "DIM_CUSTOMER", "customer dimension"),
            *step_block("loadSalesreps", "DIM_SALESREP", "sales rep dimension"),
            *step_block("loadProducts", "DIM_PRODUCT", "product dimension"),
            invoke("star.adapters:selectChunks",
                   inp=[copy("/chunkSize;1;0", "/selectChunksInput;2;0/chunk_size;1;0"), copy("/chunkSize;1;0", "/selectChunksInput;2;0/chunk_size2;1;0")],
                   out=[copy("/selectChunksOutput;2;0/results;2;1", f"/chunks;4;1;{DOC_CHUNK}"),
                        delete("/selectChunksOutput;2;0", "/selectChunksInput;2;0")],
                   comment="batch plan (generate_series on order_line_id)"),
            l,
            invoke("star.adapters:selectCounts",
                   out=[copy("/selectCountsOutput;2;0/results[0];2;1/fact_rows;1;0", "/totalRows;1;0"), delete("/selectCountsOutput;2;0")],
                   comment="total rows loaded, re-read from the database (safe with any parallelism)"),
            mapstep(delete(f"/chunks;4;1;{DOC_CHUNK}")),
            invoke("star.adapters:selectStopFlag",
                   out=[copy("/selectStopFlagOutput;2;0/results[0];2;1/ctl_value;1;0", "/stopFlag;1;0"), delete("/selectStopFlagOutput;2;0")]),
            branch("/stopFlag", ("true", [mapstep(setv("/pipeStatus;1;0", "STOPPED"))]), comment="stopped by the user?"),
            branch("/pipeStatus", ("RUNNING", [mapstep(setv("/pipeStatus;1;0", "DONE"))])),
        ], [
            invoke("pub.flow:getLastFailureCaught", out=[copy("/failureMessage;1;0", "/errorMsg;1;0"), delete("/failureMessage;1;0", "/failureName;1;0", "/failure;3;0")]),
            mapstep(setv("/pipeStatus;1;0", "FAILED")),
        ]),
        invoke("star.etl.steps:logStep",
               inp=[copy("/pipeStart;1;0", "/startedAt;1;0"), copy("/pipeNano;3;0", "/startNano;3;0"), copy("/totalRows;1;0", "/rowCount;1;0"),
                    copy("/pipeStatus;1;0", "/status;1;0"), copy("/errorMsg;1;0", "/message;1;0"), setv("/stepName;1;0", "PIPELINE_END")],
               out=[delete("/stepName;1;0", "/startedAt;1;0", "/startNano;3;0", "/rowCount;1;0", "/message;1;0", "/status;1;0")],
               comment="total duration (PIPELINE_END row)"),
        invoke("star.adapters:updatePipelineLog",
               inp=[copy("/runId;1;0", "/updatePipelineLogInput;2;0/run_id;1;0"), copy("/endedAt;1;0", "/updatePipelineLogInput;2;0/ended_at;1;0"),
                    copy("/durationMs;1;0", "/updatePipelineLogInput;2;0/duration_ms;1;0"), copy("/totalRows;1;0", "/updatePipelineLogInput;2;0/row_count;1;0"),
                    copy("/pipeStatus;1;0", "/updatePipelineLogInput;2;0/status;1;0"), copy("/errorMsg;1;0", "/updatePipelineLogInput;2;0/message;1;0")],
               out=[delete("/updatePipelineLogInput;2;0", "/updatePipelineLogOutput;2;0")], comment="close the PIPELINE row"),
        mapstep(copy("/pipeStatus;1;0", "/status;1;0"),
                delete("/pipeStatus;1;0", "/errorMsg;1;0", "/pipeStart;1;0", "/pipeNano;3;0", "/endedAt;1;0", "/fromId;1;0", "/chunkNo;1;0",
                       "/chunkSize;1;0", "/threads;1;0", "/lang;1;0", "/dimLocale;1;0", "/quarterLetter;1;0", "/weekLetter;1;0",
                       "/stepStart;1;0", "/stepNano;3;0", "/toId;1;0", "/stopFlag;1;0", f"/chunks;4;1;{DOC_CHUNK}")),
    ], f"ETL orchestrator ({threads} fact batch(es) in parallel): truncates the star schema, loads the 4 dimensions (including the computed time dimension), then the fact table by logged transactional batches; a stop flag is checked between batches.")

START_PIPELINE = service("star.etl:startPipeline", sig(field("chunkSize"), field("threads"), field("lang")), sig(field("taskID"), field("scheduledAt"), field("service")), [
    mapstep(setv("/chunkSize;1;0", "20000", overwrite=False), setv("/threads;1;0", "1", overwrite=False), setv("/lang;1;0", "fr", overwrite=False)),
    branch("/threads",
           ("2", [mapstep(setv("/service;1;0", "star.etl:runPipelineX2"))]),
           ("4", [mapstep(setv("/service;1;0", "star.etl:runPipelineX4"))]),
           ("$default", [mapstep(setv("/service;1;0", "star.etl:runPipeline"))]), comment="orchestrator for the requested parallelism"),
    now_string("yyyy/MM/dd HH:mm:ss", "/nowStr;1;0"),
    invoke("pub.date:incrementDate",
           inp=[copy("/nowStr;1;0", "/startDate;1;0"), setv("/startDatePattern;1;0", "yyyy/MM/dd HH:mm:ss"),
                setv("/endDatePattern;1;0", "yyyy/MM/dd HH:mm:ss"), setv("/addSeconds;1;0", "3")],
           out=[copy("/endDate;1;0", "/scheduledAt;1;0"),
                delete("/endDate;1;0", "/startDate;1;0", "/startDatePattern;1;0", "/endDatePattern;1;0", "/addSeconds;1;0", "/nowStr;1;0")],
           comment="+3 s (the scheduler refuses a past time)"),
    invoke("pub.string:substring", inp=[copy("/scheduledAt;1;0", "/inString;1;0"), setv("/beginIndex;1;0", "0"), setv("/endIndex;1;0", "10")],
           out=[copy("/value;1;0", "/runDate;1;0"), delete("/value;1;0", "/inString;1;0", "/beginIndex;1;0", "/endIndex;1;0")]),
    invoke("pub.string:substring", inp=[copy("/scheduledAt;1;0", "/inString;1;0"), setv("/beginIndex;1;0", "11"), setv("/endIndex;1;0", "19")],
           out=[copy("/value;1;0", "/runTime;1;0"), delete("/value;1;0", "/inString;1;0", "/beginIndex;1;0", "/endIndex;1;0")]),
    invoke("pub.scheduler:addOneTimeTask",
           inp=[copy("/runDate;1;0", "/date;1;0"), copy("/runTime;1;0", "/time;1;0"), copy("/chunkSize;1;0", "/inputs;2;0/chunkSize;1;0"),
                copy("/lang;1;0", "/inputs;2;0/lang;1;0"),
                setv("/description;1;0", "Star schema ETL - star schema load"), setv("/runAsUser;1;0", "Administrator")],
           out=[delete("/description;1;0", "/runAsUser;1;0", "/date;1;0", "/time;1;0", "/inputs;2;0", "/type;1;0",
                       "/taskAdded;1;0", "/runDate;1;0", "/runTime;1;0", "/chunkSize;1;0", "/threads;1;0", "/lang;1;0")],
           comment="one-time IS scheduler task"),
], "Asynchronous start: schedules the orchestrator (1, 2 or 4 parallel batches) in 3 seconds through the IS scheduler.")

# ------------------------------------------------------------------ API UI
def api_select(svc, target, first=False):
    frm = f"/{svc}Output;2;0/results[0];2;1" if first else f"/{svc}Output;2;0/results;2;1"
    to = f"/{target};2;0" if first else f"/{target};2;1"
    return invoke(f"star.adapters:{svc}", out=[copy(frm, to), delete(f"/{svc}Output;2;0")])

API_STATUS = service("star.api:status", sig(),
    sig(field("serverTime"), field("counts", "record"), field("runLog", "record", 1), field("preview", "record", 1), field("sourceNext", "record", 1)), [
    now_string("HH:mm:ss.SSS", "/serverTime;1;0"),
    api_select("selectCounts", "counts", True),
    api_select("selectRunLog", "runLog"),
    api_select("selectFactPreview", "preview"),
    api_select("selectSourceNext", "sourceNext"),
], "Demo state for the UI (JSON): volumes, log of the last run, last transformed rows, next source rows.")

API_CHART = service("star.api:chart", sig(), sig(field("salesByMonth", "record", 1)), [
    api_select("selectSalesByMonth", "salesByMonth"),
], "Revenue by month (fact_sales ⋈ dim_date) for the UI chart, refreshed less often than the status.")

def set_stop_flag(v):
    return invoke("star.adapters:setStopFlag", inp=[setv("/setStopFlagInput;2;0/value;1;0", v)],
                  out=[delete("/setStopFlagInput;2;0", "/setStopFlagOutput;2;0")])

API_START = service("star.api:start", sig(field("chunkSize"), field("threads"), field("lang")), sig(field("started"), field("message"), field("taskID"), field("scheduledAt"), field("service")), [
    invoke("star.adapters:selectRunLog", out=[copy("/selectRunLogOutput;2;0/results[0];2;1/status;1;0", "/lastStatus;1;0"), delete("/selectRunLogOutput;2;0")],
           comment="status of the last run"),
    branch("/lastStatus",
           ("RUNNING", [mapstep(setv("/started;1;0", "false"), setv("/message;1;0", "A pipeline is already running"))]),
           ("$default", [set_stop_flag("false"),
                         invoke("star.etl:startPipeline", out=[delete("/chunkSize;1;0", "/threads;1;0", "/lang;1;0")]),
                         mapstep(setv("/started;1;0", "true"), setv("/message;1;0", "Pipeline scheduled (%service%)", variables=True))]),
           comment="refused if a pipeline is already running"),
    mapstep(delete("/lastStatus;1;0")),
], "Starts the demo (double-start guard): re-arms the stop flag, then schedules the pipeline.")

API_STOP = service("star.api:stop", sig(), sig(field("stopped")), [
    set_stop_flag("true"), mapstep(setv("/stopped;1;0", "true")),
], "Requests the running pipeline to stop (honoured between two batches).")

API_RESET = service("star.api:reset", sig(), sig(field("reset")), [
    invoke("star.adapters:resetDemo", out=[delete("/resetDemoOutput;2;0")]), mapstep(setv("/reset;1;0", "true")),
], "Resets the demo: empties the star schema and the log, re-arms the stop flag (dwh.reset_demo()).")

API_SOURCE = service("star.api:source", sig(), sig(field("source", "record")), [
    api_select("selectSourceTotals", "source", True),
], "Totals of the source table (rows, amount, orders, period) for the reconciliation shown by the UI.")

AXES = ["anYear", "anQuarter", "anMonth", "anWeek", "anWeekday", "anSegment", "anDept", "anCustomer", "anRegion", "anSalesrep", "anCategory", "anBrand", "anProduct"]
API_ANALYZE = service("star.api:analyze", sig(field("axis")), sig(field("axis"), field("rows", "record", 1), field("error")), [
    branch("/axis", *[(ax, [api_select(ax, "rows")]) for ax in AXES],
           ("$default", [mapstep(setv("/error;1;0", "unknown axis"))]), comment="whitelisted queries on fact_sales ⋈ dimension"),
], "Dimension analysis for the UI: axis (year, quarter, month, week, weekday, segment, department, customer, region, sales rep, category, brand, product) -> revenue, quantities, lines, average line amount.")

DIMS = [("date", "dimDateRows"), ("customer", "dimCustomerRows"), ("salesrep", "dimSalesrepRows"), ("product", "dimProductRows")]
API_DIMENSION = service("star.api:dimension", sig(field("name")), sig(field("name"), field("rows", "record", 1), field("error")), [
    branch("/name", *[(n, [api_select(svc, "rows")]) for n, svc in DIMS],
           ("$default", [mapstep(setv("/error;1;0", "unknown dimension"))]), comment="preview of a dimension's content"),
], "Preview of the first 12 rows of a dimension table (date, customer, salesrep, product).")

DOCTYPES = [
    doctype(DOC_FACTROW, FACT_COLS),
    doctype(DOC_FACT, FACT_COLS + ["amount"]),
    doctype(DOC_DATEROW, ["order_date"]),
    doctype(DOC_CHUNK, ["chunk_no", "from_id", "to_id"]),
    doctype(DOC_DIMDATE, ["date_key", "full_date", "year_num", "quarter_num", "quarter_label", "month_num", "month_name", "year_month",
                          "week_of_year", "year_week", "day_of_month", "day_of_week", "day_name", "is_weekend"]),
]


def node_exists(m, name):
    try:
        return bool((json.loads(m.call("node_get", {"name": name})) or {}).get("node"))
    except Exception:
        return False


def checked(out):
    """The MCP server returns some IS failures as plain text: detect them."""
    if out.lstrip().lower().startswith(("putnode failed", "failed", "error")) or "HTTP 5" in out[:200]:
        raise RuntimeError(out[:600])
    return out


def objtostring_output(m):
    d = json.loads(m.call("node_get", {"name": "pub.string:objectToString"}))
    return d["node"]["svc_sig"]["sig_out"]["rec_fields"][0]["field_name"]


def main():
    only = sys.argv[1:]
    m = Mcp()
    rc = 0
    try:
        for dt in DOCTYPES:
            try:
                m.call("document_type_create", {"doc_path": dt["node_nsName"], "package": PKG})
            except Exception as e:
                if "exist" not in str(e).lower() and "already in use" not in str(e).lower():
                    print("!! document_type_create", dt["node_nsName"], str(e)[:200])
            checked(m.call("put_node", {"node_data": json.dumps(dt)}))
            print(f"OK  doctype {dt['node_nsName']} ({len(dt['rec_fields'])} fields)")
        services = [BEGIN_STEP, log_step(objtostring_output(m)), TRUNCATE_STAR,
                    dim_loader("loadCustomers", "selectCustomers", "insertCustomers", "customers", "Customer dimension: SELECT DISTINCT then BatchInsert into dwh.dim_customer. One transaction."),
                    dim_loader("loadSalesreps", "selectSalesreps", "insertSalesreps", "salesreps", "Sales rep dimension: SELECT DISTINCT then BatchInsert into dwh.dim_salesrep. One transaction."),
                    dim_loader("loadProducts", "selectProducts", "insertProducts", "products", "Product dimension: SELECT DISTINCT then BatchInsert into dwh.dim_product. One transaction."),
                    LOAD_DATES, LOAD_FACT_CHUNK, run_pipeline("runPipeline", 1), run_pipeline("runPipelineX2", 2), run_pipeline("runPipelineX4", 4),
                    START_PIPELINE, API_STATUS, API_CHART, API_START, API_STOP, API_RESET, API_ANALYZE, API_DIMENSION, API_SOURCE]
        for s in services:
            name = s["node_nsName"].split(":")[1]
            if only and name not in only:
                continue
            folder = s["node_nsName"].split(":")[0]
            parts = folder.split(".")
            for i in range(1, len(parts) + 1):
                try:
                    m.call("folder_create", {"package": PKG, "folder_path": ".".join(parts[:i])})
                except Exception as e:
                    if "exist" not in str(e).lower():
                        raise
            try:
                # putNode locks the node before writing: the shell must exist
                if not node_exists(m, s["node_nsName"]):
                    m.call("flow_service_create", {"package": PKG, "service_path": s["node_nsName"]})
                checked(m.call("put_node", {"node_data": json.dumps(s, ensure_ascii=False)}))
                g = json.loads(m.call("node_get", {"name": s["node_nsName"]}))
                if (g.get("node") or {}).get("svc_type") != "flow":
                    raise RuntimeError("node missing or not a flow after put_node")
                print(f"OK  {s['node_nsName']}")
            except Exception as e:
                rc = 1
                print(f"KO  {s['node_nsName']}: {str(e)[:500]}")
    finally:
        m.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
