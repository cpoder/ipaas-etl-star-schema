#!/usr/bin/env bash
# Full deployment of the ETL demo (idempotent). IS_HOME and WM_MCP_BIN can be overridden from the environment.
#   ./deploy.sh            -> everything (database, data set, IS package, UI)
#   ./deploy.sh db         -> container + schema
#   ./deploy.sh data       -> regenerate the ~1M source rows (English labels; data-fr: French labels)
#   ./deploy.sh is         -> connections + adapter services + flows + UI
#   ./deploy.sh ui         -> copy the UI only
set -euo pipefail
cd "$(dirname "$0")"
IS_HOME=${IS_HOME:-/home/cpo/wm12/IntegrationServer/instances/default}
DB_NAME=${DB_NAME:-stardemo}        # PostgreSQL database, user and password (also read by wm/package.py)
PG_PORT=${PG_PORT:-5435}
PKG_DIR=$IS_HOME/packages/StarSchemaETL
DB=${DB_CONTAINER:-$DB_NAME-db}

db() {
  if ! docker ps -a --format '{{.Names}}' | grep -qx $DB; then
    docker run -d --name $DB -p $PG_PORT:5432 -e POSTGRES_USER=$DB_NAME -e POSTGRES_PASSWORD=$DB_NAME -e POSTGRES_DB=$DB_NAME \
      -v $DB-pgdata:/var/lib/postgresql/data --shm-size=1g --restart unless-stopped postgres:16-alpine \
      -c shared_buffers=512MB -c work_mem=64MB -c maintenance_work_mem=256MB -c max_wal_size=2GB
  else
    docker start $DB >/dev/null
  fi
  for i in $(seq 1 30); do docker exec $DB pg_isready -U $DB_NAME -d $DB_NAME >/dev/null 2>&1 && break; sleep 1; done
  docker exec -i $DB psql -U $DB_NAME -d $DB_NAME -v ON_ERROR_STOP=1 -q < db/01_schema.sql
  docker exec $DB psql -U $DB_NAME -d $DB_NAME -qc "ALTER DATABASE $DB_NAME SET timezone = 'Europe/Paris'"
  echo "[db] schema applied"
}
data() {   # data set (English labels by default; `data-fr` for the French variant)
  docker exec -i $DB psql -U $DB_NAME -d $DB_NAME -v ON_ERROR_STOP=1 < db/02_generate_data${1:-}.sql | tail -4
}
is() {
  curl -sf -m 5 -u Administrator:manage http://localhost:5555/invoke/wm.server/ping >/dev/null || { echo "IS unreachable on :5555 (start $IS_HOME/bin/startup.sh)"; exit 1; }
  DB_NAME=$DB_NAME PG_PORT=$PG_PORT python3 wm/package.py     # package, folders, JDBC connections
  python3 wm/adapters.py    # JDBC adapter services (CustomSQL / BatchInsert)
  python3 wm/flows.py       # document types + flow services (putNode)
  ui
}
ui() {
  mkdir -p "$PKG_DIR/pub"
  cp ui/index.html "$PKG_DIR/pub/index.html"
  [ -f ui/flows.html ] && cp ui/flows.html "$PKG_DIR/pub/flows.html"
  echo "[ui] http://localhost:5555/StarSchemaETL/index.html (Administrator / manage)"
}
case "${1:-all}" in
  db) db ;; data) data ;; data-fr) data _fr ;; is) is ;; ui) ui ;;
  all) db; data; is ;;
  *) echo "usage: $0 [all|db|data|data-fr|is|ui]"; exit 2 ;;
esac
