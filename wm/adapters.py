#!/usr/bin/env python3
"""Création des services adaptateur JDBC du package StarSchemaETL via le serveur MCP.

Reproduit ce que fait Designer : lookups de domaines de ressources (colInfo,
types JDBC) puis createAdapterServiceNode avec les propriétés complètes.
Idempotent : un service existant est supprimé puis recréé.
"""
import json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpcli import Mcp

PKG = "StarSchemaETL"
FOLDER = "star.adapters"
CONN_DWH = "star.connections:dwh"        # LOCAL_TRANSACTION : chargements
CONN_LOG = "star.connections:dwhLog"     # NO_TRANSACTION    : journal, pilotage, UI
CATALOG = "winfarm"
TPL_CUSTOM = "com.wm.adapter.wmjdbc.services.CustomSQL"
TPL_BATCH = "com.wm.adapter.wmjdbc.services.BatchInsert"

COMMON = {
    "designTimeLocale": "en",
    "userid": "overrideCredentials.$dbUser", "useridType": "java.lang.String",
    "inputUseridSign": "overrideCredentials.$dbUser",
    "password": "overrideCredentials.$dbPassword", "passwordType": "java.lang.String",
    "inputPasswordSign": "overrideCredentials.$dbPassword",
}

# --------------------------------------------------------------------------
# Définitions
# --------------------------------------------------------------------------
# CustomSQL : (nom, connexion, sql, [noms des paramètres d'entrée], resultRowField, colInfo forcé)
CUSTOM_SQL = [
    # --- chargement (connexion transactionnelle) ---
    ("truncateStar", CONN_DWH, "SELECT dwh.truncate_star() AS result", [], None, None),
    ("selectMaxLineId", CONN_DWH,
     "SELECT max(order_line_id) AS max_id, count(*) AS row_count FROM staging.orders", [], None, None),
    ("selectCustomers", CONN_DWH,
     "SELECT DISTINCT customer_code, customer_name, customer_city AS city, customer_dept AS dept, customer_segment AS segment "
     "FROM staging.orders ORDER BY customer_code", [], None, None),
    ("selectSalesreps", CONN_DWH,
     "SELECT DISTINCT salesrep_code, salesrep_name, salesrep_region AS region FROM staging.orders ORDER BY salesrep_code",
     [], None, None),
    ("selectProducts", CONN_DWH,
     "SELECT DISTINCT product_code, product_name, product_category AS category, product_brand AS brand "
     "FROM staging.orders ORDER BY product_code", [], None, None),
    ("selectDates", CONN_DWH,
     "SELECT DISTINCT order_date FROM staging.orders ORDER BY order_date", [], None, None),
    ("selectFactChunk", CONN_DWH,
     "SELECT o.order_line_id, o.order_id, to_char(o.order_date, 'YYYYMMDD') AS date_key, "
     "c.customer_key, s.salesrep_key, p.product_key, o.quantity, o.unit_price "
     "FROM staging.orders o "
     "JOIN dwh.dim_customer c ON c.customer_code = o.customer_code "
     "JOIN dwh.dim_salesrep s ON s.salesrep_code = o.salesrep_code "
     "JOIN dwh.dim_product  p ON p.product_code  = o.product_code "
     "WHERE o.order_line_id > ? AND o.order_line_id <= ? ORDER BY o.order_line_id",
     ["from_id", "to_id"], None,
     [("from_id", "BIGINT", "IN"), ("to_id", "BIGINT", "IN"),
      ("order_line_id", "BIGINT"), ("order_id", "VARCHAR"), ("date_key", "VARCHAR"), ("customer_key", "INTEGER"),
      ("salesrep_key", "INTEGER"), ("product_key", "INTEGER"), ("quantity", "INTEGER"), ("unit_price", "NUMERIC")]),
    # --- journal & pilotage (connexion sans transaction) ---
    ("insertLog", CONN_LOG,
     "INSERT INTO dwh.etl_run_log (run_id, step_name, started_at, ended_at, row_count, duration_ms, status, message) "
     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
     ["run_id", "step_name", "started_at", "ended_at", "row_count", "duration_ms", "status", "message"], "rowCount",
     [("run_id", "VARCHAR", "IN"), ("step_name", "VARCHAR", "IN"), ("started_at", "TIMESTAMP", "IN"), ("ended_at", "TIMESTAMP", "IN"),
      ("row_count", "BIGINT", "IN"), ("duration_ms", "BIGINT", "IN"), ("status", "VARCHAR", "IN"), ("message", "VARCHAR", "IN")]),
    ("updatePipelineLog", CONN_LOG,
     "UPDATE dwh.etl_run_log SET ended_at = ?, duration_ms = ?, row_count = ?, status = ?, message = ? "
     "WHERE run_id = ? AND step_name = 'PIPELINE'",
     ["ended_at", "duration_ms", "row_count", "status", "message", "run_id"], "rowCount",
     [("ended_at", "TIMESTAMP", "IN"), ("duration_ms", "BIGINT", "IN"), ("row_count", "BIGINT", "IN"), ("status", "VARCHAR", "IN"),
      ("message", "VARCHAR", "IN"), ("run_id", "VARCHAR", "IN")]),
    ("selectChunks", CONN_LOG,
     "SELECT row_number() OVER (ORDER BY s) AS chunk_no, s AS from_id, s + ? AS to_id "
     "FROM generate_series(0, (SELECT max(order_line_id) FROM staging.orders) - 1, ?) AS s",
     ["chunk_size", "chunk_size2"], None,
     [("chunk_size", "BIGINT", "IN"), ("chunk_size2", "BIGINT", "IN"), ("chunk_no", "BIGINT"), ("from_id", "BIGINT"), ("to_id", "BIGINT")]),
    ("resetDemo", CONN_LOG, "SELECT dwh.reset_demo() AS result", [], None, None),
    ("selectStopFlag", CONN_LOG,
     "SELECT ctl_value FROM dwh.etl_control WHERE ctl_key = 'stop_requested'", [], None, None),
    ("setStopFlag", CONN_LOG,
     "UPDATE dwh.etl_control SET ctl_value = ? WHERE ctl_key = 'stop_requested'", ["value"], "rowCount",
     [("value", "VARCHAR", "IN")]),
    ("selectCounts", CONN_LOG,
     "SELECT (SELECT count(*) FROM staging.orders) AS src_rows, "
     "(SELECT pg_size_pretty(pg_total_relation_size('staging.orders'))) AS src_size, "
     "(SELECT count(*) FROM dwh.dim_date) AS dim_date, "
     "(SELECT count(*) FROM dwh.dim_customer) AS dim_customer, "
     "(SELECT count(*) FROM dwh.dim_salesrep) AS dim_salesrep, "
     "(SELECT count(*) FROM dwh.dim_product) AS dim_product, "
     "(SELECT count(*) FROM dwh.fact_sales) AS fact_rows, "
     "(SELECT coalesce(sum(amount), 0) FROM dwh.fact_sales) AS fact_amount, "
     "(SELECT pg_size_pretty(pg_total_relation_size('dwh.fact_sales'))) AS fact_size, "
     "(SELECT ctl_value FROM dwh.etl_control WHERE ctl_key = 'stop_requested') AS stop_requested",
     [], None,
     [("src_rows", "BIGINT"), ("src_size", "VARCHAR"), ("dim_date", "BIGINT"), ("dim_customer", "BIGINT"),
      ("dim_salesrep", "BIGINT"), ("dim_product", "BIGINT"), ("fact_rows", "BIGINT"), ("fact_amount", "NUMERIC"),
      ("fact_size", "VARCHAR"), ("stop_requested", "VARCHAR")]),
    ("selectRunLog", CONN_LOG,
     "SELECT run_id, step_name, to_char(started_at, 'HH24:MI:SS.MS') AS started_at, "
     "to_char(ended_at, 'HH24:MI:SS.MS') AS ended_at, row_count, duration_ms, status, message "
     "FROM dwh.v_etl_last_run", [], None, None),
    ("selectFactPreview", CONN_LOG,
     "SELECT f.order_line_id, f.order_id, f.date_key, f.customer_key, f.salesrep_key, f.product_key, "
     "d.full_date, c.customer_name, s.salesrep_name, p.product_name, f.quantity, f.unit_price, f.amount "
     "FROM dwh.fact_sales f JOIN dwh.dim_date d ON d.date_key = f.date_key "
     "JOIN dwh.dim_customer c ON c.customer_key = f.customer_key "
     "JOIN dwh.dim_salesrep s ON s.salesrep_key = f.salesrep_key "
     "JOIN dwh.dim_product p ON p.product_key = f.product_key "
     "ORDER BY f.order_line_id DESC LIMIT 6", [], None,
     [("order_line_id", "BIGINT"), ("order_id", "VARCHAR"), ("date_key", "INTEGER"), ("customer_key", "INTEGER"),
      ("salesrep_key", "INTEGER"), ("product_key", "INTEGER"), ("full_date", "DATE"), ("customer_name", "VARCHAR"),
      ("salesrep_name", "VARCHAR"), ("product_name", "VARCHAR"), ("quantity", "INTEGER"), ("unit_price", "NUMERIC"),
      ("amount", "NUMERIC")]),
    ("selectSourceNext", CONN_LOG,
     "SELECT order_line_id, order_id, order_date, customer_code, customer_name, customer_city, customer_segment, "
     "salesrep_code, salesrep_name, product_code, product_name, product_category, quantity, unit_price "
     "FROM staging.orders WHERE order_line_id > coalesce((SELECT max(order_line_id) FROM dwh.fact_sales), 0) "
     "ORDER BY order_line_id LIMIT 6", [], None, None),
    ("selectSalesByMonth", CONN_LOG,
     "SELECT d.year_month, sum(f.amount) AS amount, count(*) AS lines "
     "FROM dwh.fact_sales f JOIN dwh.dim_date d ON d.date_key = f.date_key GROUP BY d.year_month ORDER BY d.year_month",
     [], None, [("year_month", "VARCHAR"), ("amount", "NUMERIC"), ("lines", "BIGINT")]),
    # --- analyses par dimension et aperçu des dimensions (UI « Explorer ») ---
    ("anYear", CONN_LOG,
     "SELECT CAST(d.year_num AS varchar) AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_date d ON d.date_key = f.date_key GROUP BY d.year_num ORDER BY d.year_num",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anQuarter", CONN_LOG,
     "SELECT d.quarter_label AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_date d ON d.date_key = f.date_key GROUP BY d.quarter_label ORDER BY d.quarter_label",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anMonth", CONN_LOG,
     "SELECT d.year_month AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_date d ON d.date_key = f.date_key GROUP BY d.year_month ORDER BY d.year_month",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anWeek", CONN_LOG,
     "SELECT d.year_week AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_date d ON d.date_key = f.date_key GROUP BY d.year_week ORDER BY d.year_week",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anWeekday", CONN_LOG,
     "SELECT d.day_name AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_date d ON d.date_key = f.date_key GROUP BY d.day_of_week, d.day_name ORDER BY d.day_of_week",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anSegment", CONN_LOG,
     "SELECT d.segment AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_customer d ON d.customer_key = f.customer_key GROUP BY d.segment ORDER BY amount DESC",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anDept", CONN_LOG,
     "SELECT d.dept AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_customer d ON d.customer_key = f.customer_key GROUP BY d.dept ORDER BY amount DESC LIMIT 15",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anCustomer", CONN_LOG,
     "SELECT d.customer_name AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_customer d ON d.customer_key = f.customer_key GROUP BY d.customer_name ORDER BY amount DESC LIMIT 10",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anRegion", CONN_LOG,
     "SELECT d.region AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_salesrep d ON d.salesrep_key = f.salesrep_key GROUP BY d.region ORDER BY amount DESC",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anSalesrep", CONN_LOG,
     "SELECT d.salesrep_name AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_salesrep d ON d.salesrep_key = f.salesrep_key GROUP BY d.salesrep_name ORDER BY amount DESC LIMIT 10",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anCategory", CONN_LOG,
     "SELECT d.category AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_product d ON d.product_key = f.product_key GROUP BY d.category ORDER BY amount DESC",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anBrand", CONN_LOG,
     "SELECT d.brand AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_product d ON d.product_key = f.product_key GROUP BY d.brand ORDER BY amount DESC",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("anProduct", CONN_LOG,
     "SELECT d.product_name AS label, sum(f.amount) AS amount, sum(f.quantity) AS quantity, count(*) AS lines, round(avg(f.amount), 2) AS avg_amount FROM dwh.fact_sales f JOIN dwh.dim_product d ON d.product_key = f.product_key GROUP BY d.product_name ORDER BY amount DESC LIMIT 10",
     [], None, [('label', 'VARCHAR'), ('amount', 'NUMERIC'), ('quantity', 'BIGINT'), ('lines', 'BIGINT'), ('avg_amount', 'NUMERIC')]),
    ("dimDateRows", CONN_LOG,
     "SELECT date_key, full_date, year_num, quarter_label, year_month, year_week, day_name, is_weekend FROM dwh.dim_date ORDER BY date_key LIMIT 12",
     [], None, [("date_key", "INTEGER"), ("full_date", "DATE"), ("year_num", "SMALLINT"), ("quarter_label", "VARCHAR"), ("year_month", "VARCHAR"), ("year_week", "VARCHAR"), ("day_name", "VARCHAR"), ("is_weekend", "BOOLEAN")]),
    ("dimCustomerRows", CONN_LOG,
     "SELECT customer_key, customer_code, customer_name, city, dept, segment FROM dwh.dim_customer ORDER BY customer_key LIMIT 12",
     [], None, [("customer_key", "INTEGER"), ("customer_code", "VARCHAR"), ("customer_name", "VARCHAR"), ("city", "VARCHAR"), ("dept", "VARCHAR"), ("segment", "VARCHAR")]),
    ("dimSalesrepRows", CONN_LOG,
     "SELECT salesrep_key, salesrep_code, salesrep_name, region FROM dwh.dim_salesrep ORDER BY salesrep_key LIMIT 12",
     [], None, [("salesrep_key", "INTEGER"), ("salesrep_code", "VARCHAR"), ("salesrep_name", "VARCHAR"), ("region", "VARCHAR")]),
    ("dimProductRows", CONN_LOG,
     "SELECT product_key, product_code, product_name, category, brand FROM dwh.dim_product ORDER BY product_key LIMIT 12",
     [], None, [("product_key", "INTEGER"), ("product_code", "VARCHAR"), ("product_name", "VARCHAR"), ("category", "VARCHAR"), ("brand", "VARCHAR")]),
    ("selectSourceTotals", CONN_LOG,
     "SELECT count(*) AS src_rows, sum(quantity * unit_price) AS src_amount, count(DISTINCT order_id) AS src_orders, "
     "min(order_date) AS date_min, max(order_date) AS date_max FROM staging.orders",
     [], None, [("src_rows", "BIGINT"), ("src_amount", "NUMERIC"), ("src_orders", "BIGINT"), ("date_min", "DATE"), ("date_max", "DATE")]),
    ("selectDimSample", CONN_LOG,
     "SELECT 'dim_date' AS dim, CAST(date_key AS varchar) AS key, quarter_label || ' ' || day_name || ' ' || CAST(full_date AS varchar) AS label FROM dwh.dim_date ORDER BY date_key DESC LIMIT 3", [], None,
     [("dim", "VARCHAR"), ("key", "VARCHAR"), ("label", "VARCHAR")]),
]

# BatchInsert : (nom, connexion, schéma, table, colonnes exclues (clés techniques auto))
BATCH_INSERT = [
    ("insertCustomers", CONN_DWH, "dwh", "dim_customer", ["customer_key"]),
    ("insertSalesreps", CONN_DWH, "dwh", "dim_salesrep", ["salesrep_key"]),
    ("insertProducts", CONN_DWH, "dwh", "dim_product", ["product_key"]),
    ("insertDates", CONN_DWH, "dwh", "dim_date", []),
    ("insertFacts", CONN_DWH, "dwh", "fact_sales", ["loaded_at"]),
]


def lookup(m, conn, tpl, domain, values=None):
    args = {"connection_alias": conn, "service_template": tpl, "resource_domain_name": domain}
    if values is not None:
        args["values"] = json.dumps(values)
    d = json.loads(m.call("adapter_resource_domain_lookup", args))
    return [v["name"] for v in d["resourceDomainValues"][0]["values"]]


def parse_colinfo(colinfo):
    """'0;name;TYPE;IN;\\n1;...' -> (inputs, outputs) listes de (idx, name, jdbcType)."""
    ins, outs = [], []
    for line in colinfo.replace("\\n", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        idx, name, jtype, io = line.split(";")[:4]
        (ins if io == "IN" else outs).append((idx, name, jtype))
    return ins, outs


def build_colinfo(cols):
    """[(name, TYPE), (name, TYPE, 'IN')] -> chaîne colInfo (index séparés IN / OUT)."""
    out, ni, no = [], 0, 0
    for c in cols:
        name, jt = c[0], c[1]
        io = c[2] if len(c) > 2 else "OUT"
        if io == "IN":
            out.append(f"{ni};{name};{jt};IN;"); ni += 1
        else:
            out.append(f"{no};{name};{jt};OUT;"); no += 1
    return "\n".join(out) + "\n"


def custom_sql_settings(m, conn, sql, in_names, result_row_field, forced_colinfo):
    if isinstance(forced_colinfo, list):
        forced_colinfo = build_colinfo(forced_colinfo)
    colinfo = forced_colinfo or lookup(m, conn, TPL_CUSTOM, "customSQLcolInfo", [sql])[0]
    if colinfo.strip() == "-1":
        raise RuntimeError("SQL non analysable par l'adaptateur : fournir la liste des colonnes explicitement")
    ins, outs = parse_colinfo(colinfo)
    if len(ins) != len(in_names):
        raise RuntimeError(f"{len(ins)} paramètres détectés dans le SQL, {len(in_names)} noms fournis: {colinfo!r}")
    s = dict(COMMON)
    s.update({
        "sql": sql, "sqlFieldType": "java.lang.String", "colInfo": colinfo,
        "inputColIndexes": [i for i, _, _ in ins],
        "inputExpression": [n for _, n, _ in ins],
        "inputJDBCType": [t for _, _, t in ins],
        "inputFieldType": ["java.lang.String"] * len(ins),
        "inputField": list(in_names),
        "realInputFields": list(in_names),
        "outputColIndexes": [i for i, _, _ in outs],
        "outputExpression": [n for _, n, _ in outs],
        "outputJDBCType": [t for _, _, t in outs],
        "outputFieldType": ["java.lang.String"] * len(outs),
        "outputField": [n for _, n, _ in outs],
        "resultField": [f"results[].{n}" for _, n, _ in outs],
        "resultFieldType": ["java.lang.String[]"] * len(outs),
        "realOutputField": [f"results[].{n}" for _, n, _ in outs],
        "maxRow": "0", "queryTimeOut": "-1",
        "resultRowField": result_row_field or "",
        "resultRowFieldType": "java.lang.String" if result_row_field else "",
    })
    return s


JDBC_TYPE_NAMES = {-7: "BIT", -6: "TINYINT", 5: "SMALLINT", 4: "INTEGER", -5: "BIGINT", 6: "FLOAT", 7: "REAL",
                   8: "DOUBLE", 2: "NUMERIC", 3: "DECIMAL", 1: "CHAR", 12: "VARCHAR", -1: "LONGVARCHAR",
                   91: "DATE", 92: "TIME", 93: "TIMESTAMP", 16: "BOOLEAN", 2005: "CLOB", 2004: "BLOB",
                   -2: "BINARY", -3: "VARBINARY", -9: "NVARCHAR", 1111: "OTHER"}


def parse_columninfo(columninfo):
    """Format Designer : 'name\\nTYPE(len) NOT NULL\\n<code>\\n<pos>\\n"\\n' par colonne, colonnes séparées par \\n."""
    cols = []
    for entry in columninfo.split("\n"):
        if not entry.strip():
            continue
        parts = entry.split("\\n")
        name, ctype, code = parts[0], parts[1], int(parts[2])
        cols.append((name, ctype, JDBC_TYPE_NAMES.get(code, "VARCHAR")))
    return cols


def batch_insert_settings(m, conn, schema, table, exclude):
    colinfo = lookup(m, conn, TPL_BATCH, "columnInfo", [CATALOG, schema, table])[0]
    cols = [c for c in parse_columninfo(colinfo) if c[0] not in exclude]
    s = dict(COMMON)
    s.update({
        "tables.tableIndexes": ["T1"], "tables.catalogName": [CATALOG], "tables.schemaName": [schema],
        "tables.tableName": [table], "tables.tableType": ["TABLE"], "tables.columnInfo": [colinfo],
        "tables.realSchemaName": [schema],
        "update.column": [n for n, _, _ in cols],
        "update.columnType": [ct for _, ct, _ in cols],
        "update.JDBCType": [jt for _, _, jt in cols],
        "update.expression": ["?"] * len(cols),
        "update.inputColumn": [n for n, _, _ in cols],
        "update.inputColumnType": [ct for _, ct, _ in cols],
        "update.inputJDBCType": [jt for _, _, jt in cols],
        "update.inputField": [n for n, _, _ in cols],
        "update.inputFieldType": ["java.lang.String"] * len(cols),
        "update.batchInputField": [f"inputs[].{n}" for n, _, _ in cols],
        "update.batchInputFieldType": ["java.lang.String[]"] * len(cols),
        "update.realInputField": [f"inputs[].{n}" for n, _, _ in cols],
        "update.queryTimeOut": "-1",
        "updatecount.fieldName": "updateCount",
        "updatecount.updateCountOutputName": ["updateCount[]"],
        "updatecount.updateCountOutputType": ["java.lang.String[]"],
        "updatecount.realOutput": ["updateCount[]"],
    })
    return s, cols


def node_exists(m, full):
    try:
        d = json.loads(m.call("node_get", {"name": full}))
        return bool(d.get("node"))
    except Exception:
        return False


def create(m, name, conn, tpl, settings):
    full = f"{FOLDER}:{name}"
    # un tableau JSON vide devient Object[] côté IS -> "could not set property ... argument type mismatch"
    settings = {k: v for k, v in settings.items() if not (isinstance(v, list) and len(v) == 0)}
    args = {"service_name": full, "package_name": PKG, "connection_alias": conn,
            "service_template": tpl, "adapter_service_settings": json.dumps(settings)}
    if node_exists(m, full):
        m.call("node_delete", {"name": full})
    out = m.call("adapter_service_create", args)
    # createAdapterServiceNode répond 200 même quand l'ART a refusé le nœud : vérifier
    if not node_exists(m, full):
        raise RuntimeError("le nœud n'existe pas après création (voir logs/server.log : ART.117.4030)")
    return out


def main():
    only = sys.argv[1:]  # noms optionnels
    m = Mcp()
    ok, ko = [], []
    try:
        for name, conn, sql, ins, rrf, forced in CUSTOM_SQL:
            if only and name not in only:
                continue
            try:
                s = custom_sql_settings(m, conn, sql, ins, rrf, forced)
                create(m, name, conn, TPL_CUSTOM, s)
                ok.append(name)
                print(f"OK  CustomSQL   {name:22s} in={s['inputField']} out={s['outputField']}")
            except Exception as e:
                ko.append(name); print(f"KO  CustomSQL   {name}: {str(e)[:400]}")
        for name, conn, schema, table, excl in BATCH_INSERT:
            if only and name not in only:
                continue
            try:
                s, cols = batch_insert_settings(m, conn, schema, table, excl)
                create(m, name, conn, TPL_BATCH, s)
                ok.append(name)
                print(f"OK  BatchInsert {name:22s} {schema}.{table} cols={[c[0] for c in cols]} jdbc={[c[2] for c in cols]}")
            except Exception as e:
                ko.append(name); print(f"KO  BatchInsert {name}: {str(e)[:400]}")
    finally:
        m.close()
    print(f"\n{len(ok)} créés, {len(ko)} en erreur {ko}")
    return 1 if ko else 0


if __name__ == "__main__":
    sys.exit(main())
