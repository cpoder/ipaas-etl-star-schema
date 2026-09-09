#!/usr/bin/env python3
"""StarSchemaETL package: creation, folders and JDBC adapter connections (idempotent)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpcli import Mcp

PKG = "StarSchemaETL"
FOLDERS = ["star", "star.connections", "star.adapters", "star.docs", "star.etl", "star.etl.steps", "star.api"]
DB_NAME = os.environ.get("DB_NAME", "stardemo")
DB = {"serverName": "localhost", "portNumber": os.environ.get("PG_PORT", "5435"), "databaseName": DB_NAME, "user": DB_NAME, "password": DB_NAME}
CONNECTIONS = [
    # alias, transaction type, extra properties, pool min/max
    ("star.connections:dwh", "LOCAL_TRANSACTION", "BatchPerformanceWorkaround=true", 2, 10),   # loads (explicit transactions)
    ("star.connections:dwhLog", "NO_TRANSACTION", "", 1, 5),                                    # log, control, UI
]


def ignore_exists(fn):
    try:
        return fn()
    except Exception as e:
        if "exist" in str(e).lower() or "already" in str(e).lower():
            return None
        raise


def main():
    m = Mcp()
    try:
        ignore_exists(lambda: m.call("package_create", {"package_name": PKG}))
        for f in FOLDERS:
            ignore_exists(lambda: m.call("folder_create", {"package": PKG, "folder_path": f}))
        existing = m.call("adapter_connection_list", {})
        for alias, tx, other, pmin, pmax in CONNECTIONS:
            if alias in existing:
                print(f"OK  connection {alias} (already exists)")
            else:
                settings = dict(DB, transactionType=tx, driverType="Default", networkProtocol="", otherProperties=other,
                                datasourceClass="com.wm.dd.jdbcx.postgresql.PostgreSQLDataSource")
                m.call("adapter_connection_create", {"connection_alias": alias, "package_name": PKG, "adapter_type": "JDBCAdapter",
                                                     "connection_factory_type": "com.wm.adapter.wmjdbc.connection.JDBCConnectionFactory",
                                                     "connection_settings": json.dumps(settings), "pool_min": pmin, "pool_max": pmax})
                print(f"OK  connection {alias} created")
            ignore_exists(lambda: m.call("adapter_connection_enable", {"connection_alias": alias}))
            st = json.loads(m.call("adapter_connection_state", {"connection_alias": alias}))
            if st.get("connectionState") != "enabled" or str(st.get("hasError")) != "false":
                raise SystemExit(f"connection {alias} not enabled: {st}")
            print(f"OK  connection {alias} enabled")
    finally:
        m.close()


if __name__ == "__main__":
    main()
