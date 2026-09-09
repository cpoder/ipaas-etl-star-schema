#!/usr/bin/env bash
# Déploiement complet de la démo ETL (idempotent). IS_HOME et WM_MCP_BIN surchargeables par l'environnement.
#   ./deploy.sh            -> tout (base, données, package IS, UI)
#   ./deploy.sh db         -> conteneur + schéma
#   ./deploy.sh data       -> régénération des ~1M lignes source (data-en : libellés en anglais)
#   ./deploy.sh is         -> connexions + services adaptateur + flows + UI
#   ./deploy.sh ui         -> copie de l'UI seulement
set -euo pipefail
cd "$(dirname "$0")"
IS_HOME=${IS_HOME:-/home/cpo/wm12/IntegrationServer/instances/default}
PKG_DIR=$IS_HOME/packages/StarSchemaETL
DB=winfarm-db

db() {
  if ! docker ps -a --format '{{.Names}}' | grep -qx $DB; then
    docker run -d --name $DB -p 5435:5432 -e POSTGRES_USER=winfarm -e POSTGRES_PASSWORD=winfarm -e POSTGRES_DB=winfarm \
      -v winfarm-pgdata:/var/lib/postgresql/data --shm-size=1g --restart unless-stopped postgres:16-alpine \
      -c shared_buffers=512MB -c work_mem=64MB -c maintenance_work_mem=256MB -c max_wal_size=2GB
  else
    docker start $DB >/dev/null
  fi
  for i in $(seq 1 30); do docker exec $DB pg_isready -U winfarm -d winfarm >/dev/null 2>&1 && break; sleep 1; done
  docker exec -i $DB psql -U winfarm -d winfarm -v ON_ERROR_STOP=1 -q < db/01_schema.sql
  docker exec $DB psql -U winfarm -d winfarm -qc "ALTER DATABASE winfarm SET timezone = 'Europe/Paris'"
  echo "[db] schéma appliqué"
}
data() {   # jeu de données (français par défaut ; `data-en` pour la variante anglaise)
  docker exec -i $DB psql -U winfarm -d winfarm -v ON_ERROR_STOP=1 < db/02_generate_data${1:-}.sql | tail -4
}
is() {
  curl -sf -m 5 -u Administrator:manage http://localhost:5555/invoke/wm.server/ping >/dev/null || { echo "IS injoignable sur :5555 (démarrer $IS_HOME/bin/startup.sh)"; exit 1; }
  python3 wm/package.py     # package, dossiers, connexions JDBC
  python3 wm/adapters.py    # services adaptateur JDBC (CustomSQL / BatchInsert)
  python3 wm/flows.py       # types de documents + flow services (putNode)
  ui
}
ui() {
  mkdir -p "$PKG_DIR/pub"
  cp ui/index.html "$PKG_DIR/pub/index.html"
  echo "[ui] http://localhost:5555/StarSchemaETL/index.html (Administrator / manage)"
}
case "${1:-all}" in
  db) db ;; data) data ;; data-en) data _en ;; is) is ;; ui) ui ;;
  all) db; data; is ;;
  *) echo "usage: $0 [all|db|data|data-en|is|ui]"; exit 2 ;;
esac
