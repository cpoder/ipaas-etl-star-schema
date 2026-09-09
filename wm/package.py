#!/usr/bin/env python3
"""Package StarSchemaETL : création, dossiers et connexions adaptateur JDBC (idempotent)."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcpcli import Mcp

PKG = "StarSchemaETL"
FOLDERS = ["star", "star.connections", "star.adapters", "star.docs", "star.etl", "star.etl.steps", "star.api"]
DB = {"serverName": "localhost", "portNumber": "5435", "databaseName": "winfarm", "user": "winfarm", "password": "winfarm"}
CONNECTIONS = [
    # alias, type de transaction, propriétés supplémentaires, pool
    ("star.connections:dwh", "LOCAL_TRANSACTION", "BatchPerformanceWorkaround=true", 2, 10),   # chargements (transactions explicites)
    ("star.connections:dwhLog", "NO_TRANSACTION", "", 1, 5),                                    # journal, pilotage, UI
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
                print(f"OK  connexion {alias} (existante)")
            else:
                settings = dict(DB, transactionType=tx, driverType="Default", networkProtocol="", otherProperties=other,
                                datasourceClass="com.wm.dd.jdbcx.postgresql.PostgreSQLDataSource")
                m.call("adapter_connection_create", {"connection_alias": alias, "package_name": PKG, "adapter_type": "JDBCAdapter",
                                                     "connection_factory_type": "com.wm.adapter.wmjdbc.connection.JDBCConnectionFactory",
                                                     "connection_settings": json.dumps(settings), "pool_min": pmin, "pool_max": pmax})
                print(f"OK  connexion {alias} créée")
            ignore_exists(lambda: m.call("adapter_connection_enable", {"connection_alias": alias}))
            st = json.loads(m.call("adapter_connection_state", {"connection_alias": alias}))
            if st.get("connectionState") != "enabled" or str(st.get("hasError")) != "false":
                raise SystemExit(f"connexion {alias} non active : {st}")
            print(f"OK  connexion {alias} active")
    finally:
        m.close()


if __name__ == "__main__":
    main()
