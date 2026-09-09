#!/usr/bin/env python3
"""Tests unitaires des étapes ETL (invocation directe via MCP service_invoke)."""
import json, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpcli import Mcp

m = Mcp()
failed = 0

def inv(svc, inputs=None, maxlen=400, expect=None):
    global failed
    args = {"service_path": svc}
    if inputs is not None:
        args["inputs"] = json.dumps(inputs)
    t = time.time()
    try:
        raw = m.call("service_invoke", args)
        try:
            d = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError(raw[:900])
        txt = json.dumps(d, ensure_ascii=False)
        ok = True
        if expect:
            for k, v in expect.items():
                if str(d.get(k)) != str(v):
                    ok = False
        if not ok:
            failed += 1
        print(f"{'OK ' if ok else 'KO '} {svc} ({time.time()-t:.1f}s): {txt[:maxlen]}")
        return d
    except Exception as e:
        failed += 1
        print(f"KO  {svc} ({time.time()-t:.1f}s): {str(e)[:700]}".replace("\n", " "))
        return None

inv("star.api:reset", expect={"reset": "true"})
inv("star.etl.steps:beginStep")
inv("star.etl.steps:logStep", {"runId": "RUN-TEST", "stepName": "UNIT_TEST", "startedAt": "2026-09-08 14:00:00.000", "startNano": 1, "rowCount": "12", "status": "DONE", "message": "test"})
inv("star.etl.steps:truncateStar", expect={"rowCount": "0"})
inv("star.etl.steps:loadDates", expect={"rowCount": "1096"})
inv("star.adapters:selectDimSample", maxlen=300)
inv("star.etl.steps:loadCustomers", expect={"rowCount": "5000"})
inv("star.etl.steps:loadSalesreps", expect={"rowCount": "143"})
inv("star.etl.steps:loadProducts", expect={"rowCount": "2000"})
inv("star.etl.steps:loadFactChunk", {"fromId": "0", "toId": "5000"}, expect={"rowCount": "5000"})
inv("star.adapters:selectCounts", maxlen=500)
inv("star.adapters:selectFactPreview", maxlen=500)
inv("star.api:status", maxlen=300)
inv("star.api:source", maxlen=300)
inv("star.api:analyze", {"axis": "anRegion"}, maxlen=300)
inv("star.api:analyze", {"axis": "bogus"}, maxlen=200, expect={"error": "axe inconnu"})
inv("star.api:dimension", {"name": "product"}, maxlen=300)
inv("star.api:reset", expect={"reset": "true"})
m.close()
print("\nFAILED" if failed else "\nALL OK")
sys.exit(1 if failed else 0)
