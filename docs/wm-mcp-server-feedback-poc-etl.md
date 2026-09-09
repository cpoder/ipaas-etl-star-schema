# Retour d'expérience wm-mcp-server — PoC ETL schéma en étoile (2026-09-08)

Contexte : IS 12.1 (`/home/cpo/wm12`, port 5555), WmJDBCAdapter 10.3.0.0.34, driver DataDirect PostgreSQL
6.0.0.1902, PostgreSQL 16 (Docker `stardemo-db`, port 5435), wm-mcp-server **2.11.1** (commit b1c265e) piloté en
stdio par `wm/mcpcli.py` (initialize → tools/list → tools/call, protocole 2024-11-05 ; 343 outils).
Objectif : créer par MCP un package complet (2 connexions JDBC, 24 services adaptateur CustomSQL/BatchInsert,
5 types de documents, 13 flows avec LOOP / BRANCH / TRY-CATCH / transactions explicites, scheduler) — tout a
fini par marcher, mais chaque point ci-dessous a coûté une itération de débogage (flow.xml sur disque,
`logs/server.log`, décompilation cfr de `WmJDBCAdapter/code/classes`) alors que l'outil répondait « OK ».

Artefacts vérifiables : `wm/adapters.py` (settings CustomSQL/BatchInsert complets),
`wm/flows.py` (constructeur putNode + 13 flows), `wm/test_steps.py`,
sources décompilées (cfr)
(CustomSQL, BatchUpdateOperation, BatchUpdateColumns, BatchResult, TableList, JDBCAdapterService, FieldMap),
mémoire notes internes.

## A. Bugs / comportements des outils (avec repro et correctif proposé)

### A1. `put_node` : échec IS renvoyé comme un texte normal, et nœud requis avant écriture
- Repro : `put_node` avec le JSON de l'exemple « greet » de `wm://docs/putnode-examples` sur un service
  inexistant → la réponse est le TEXTE `putNode failed: HTTP 500 Internal Server Error: {"$error":"[ISS.0081.9001]
  Node demo.api:greet does not exist" ... at wm.server.nsimpl.lockNode(nsimpl.java:418) at
  wm.server.nsimpl.putNode(nsimpl.java:5768)` **sans `isError`** ; un client qui teste le succès de l'appel croit
  que le service est créé (13 flows « OK », aucun sur disque).
- Cause : sur IS 12.1, `wm.server.ns:putNode` fait `lockNode` avant d'écrire → le nœud doit exister.
  `flow_service_create` (coquille) puis `put_node` fonctionne ; idem `document_type_create` puis `put_node`.
- Correctifs : (1) `isError: true` (ou erreur JSON-RPC) sur toute réponse « failed » ; (2) `put_node` crée la
  coquille automatiquement quand `[ISS.0081.9001]` survient (flow service ou doc type selon `node_type`), ou au
  minimum le documente ; (3) corriger `wm://docs/flow-language-reference` et le CLAUDE.md (« tu peux créer
  directement le service final en un seul put_node ») : faux sur 12.1.

### A2. `adapter_service_create` répond « created » alors que l'ART a refusé le nœud
- Repro : settings CustomSQL avec un tableau vide (`"inputField": []`, service sans paramètre) → réponse
  `{"status":"created"}`, mais `server.log` : `[ART.117.4030] Unable to create adapter service ... [ART.114.72]
  Unable to set JavaBean properties. [ART.114.542] could not set property "realInputFields" in class
  "com.wm.adapter.wmjdbc.services.CustomSQL". argument type mismatch`. Le nœud n'existe pas
  (`service_invoke` → `UnknownServiceException`).
- Cause : un `[]` JSON devient `Object[]` côté IS, le setter attend `String[]`.
- Correctifs : omettre les propriétés vides (ou les encoder en tableau typé vide
  `<array name="x" type="value" depth="1"/>` dans l'IData) ; après `createAdapterServiceNode`, vérifier
  l'existence par `getNode` et remonter l'erreur ART (elle est dans `server.log` / le journal d'erreurs, pas
  dans la réponse HTTP).

### A3. `service_invoke` : erreur HTTP 500 renvoyée comme texte
- `Service invocation failed: HTTP 500 Internal Server Error: {...}` sans `isError` → un appelant qui parse
  du JSON casse. Proposition : `isError: true` + champ structuré (`$error`, `$errorType`, `$errorDump` tronqué).

### A4. `adapter_resource_domain_lookup` : dépendances `*prop` inexprimables
- `updateColumnNames` / `updateColumnTypes` / `updateJDBCTypes` (dépendance `*tables.columnInfo`) avec
  `values: [columnInfo]` → `[ART.114.243] Failed to run resourceDomainLookupValues service. Cannot read field
  "value" because "original" is null`. Le paramètre `values` (tableau de chaînes) ne permet pas de passer une
  dépendance de type tableau. Proposition : accepter `values` en tableau de tableaux (`[[...]]`) pour les
  dépendances étoilées, et documenter le format de `columnInfo`.

### A5. `customSQLcolInfo` renvoie `-1` dès que le SQL dépasse le parseur fdb-sql-parser
- Jointures avec alias, sous-requêtes, `to_char(...)`, `generate_series(...)`, `||` → `-1`. La doc ne le dit
  pas ; il faut alors décrire les colonnes soi-même : format `idx;nom;JDBCTYPE;IN|OUT;\n` (index séparés pour
  IN et OUT, ex. `0;from_id;BIGINT;IN;\n1;to_id;BIGINT;IN;\n0;order_line_id;BIGINT;OUT;\n...`).

### A6. Nœud `REPEAT` ignoré par putNode
- JSON exactement comme la doc (`{"type":"REPEAT","count":"-1","repeat-on":"SUCCESS","repeat-interval":"0",
  "nodes":[...]}`) dans un SEQUENCE FORM=TRY → aucun `<REPEAT` dans le flow.xml, tout le sous-arbre
  disparaît, sans erreur (le pipeline a « réussi » avec 0 lot chargé). Aucun flow avec REPEAT n'existe sur
  cet IS pour comparer ; il faudrait décompiler `com.wm.lang.flow.FlowRetry` (wm-isserver.jar) pour les
  clés IData réelles, corriger la doc et, idéalement, faire un contrôle après écriture (voir A8).
  Contournement utilisé : plan de lots calculé en SQL (`generate_series`) + `LOOP` ; `EXIT from=$loop
  signal=SUCCESS` dans un BRANCH fonctionne dans la LOOP.

### A7. FSL (`fsl_deploy` → `wm.server.flowGen:generateFromFSLString`, compilateur côté IS)
Le compilateur IBM, pas le serveur MCP, mais la doc `wm://docs/fsl-language-reference` (« Prefer FSL for
anything beyond a trivial one-step service ») envoie droit dans le mur :
- `copy` de `recordList` **supprimés en silence** quand la variable n'est pas dans la signature du service :
  `copy selectSalesrepsOutput/results -> reps;` puis `copy reps -> insertSalesrepsInput/inputs;` → MAP INPUT
  vide, `reps` typé `;2;0`. Marche seulement quand la liste est déclarée dans `input {}` du service (tests
  v1/v2/v3/v6 vs v7/v8). Vérifiable : `dsl_validate` SUCCESS, `fsl_deploy` SUCCESS, MAPCOPY absent du flow.xml.
- `WHILE (%fromId% < %maxId%) { ... }` : validé, déployé, **aucun REPEAT/LOOP émis** (corps perdu).
- `date` est un mot réservé : `INVOKE pub.date:getCurrentDateString` → `mismatched input 'date'` ;
  `pub.`date`:x` est accepté par le parseur mais compilé tel quel → `[ISC.0049.9010] ... unknown service
  'pub.`date`:getCurrentDateString'`. Même chose pour un champ `date` (`pub.scheduler:addOneTimeTask`).
  `fsl_extract` émet `pub.date:...` sans échappement : la sortie n'est pas re-validable (pas de round-trip).
- Propositions : (1) dans la doc FSL, réserver FSL aux services sans listes de documents ni boucles, et
  renvoyer vers `put_node` sinon ; (2) `fsl_deploy` pourrait post-vérifier le flow produit (nombre de
  `copy`/`set` du source vs MAPCOPY/MAPSET du flow.xml via `getNode`, présence des LOOP/REPEAT) et
  signaler les pertes ; (3) lister les mots réservés problématiques dans les noms de services (`date`, et
  probablement `time`, `type`, `value`, `pattern`...).

### A8. Contrôle après écriture (proposition transversale)
Tous les cas ci-dessus ont le même symptôme : succès rapporté, nœud absent ou incomplet. Un `flow_verify`
(ou une option `verify: true` sur `put_node`/`fsl_deploy`/`adapter_service_create`) qui relit le nœud et
compare le nombre d'étapes par type (INVOKE/MAP/MAPCOPY/LOOP/REPEAT/BRANCH/SEQUENCE) avec le JSON envoyé
éviterait 100 % de ces pertes silencieuses.

### A9. Divers
- `document_type_create` sur un type existant → `[ISS.0085.9080] node name "X" already in use` (message
  différent de `folder_create` / `package_create` « exists ») : uniformiser ou rendre idempotent.
- `node_get` d'un service adaptateur : `svc_sig` présent mais les champs de `<svc>Input/<svc>Output` ne sont
  pas détaillés (rec_fields vides) ; `adapter_service_get` donne les settings mais pas la signature.
- `wm://docs/builtin-services` dit `pub.string:objectToString → value` ; la signature réelle sur 12.1 est
  `string` (confirmé par `node_get` ; `flow-language-reference` a raison).

## B. Settings vérifiés à ajouter à `wm://docs/adapter-service-reference`

### B1. CustomSQL (template `com.wm.adapter.wmjdbc.services.CustomSQL`)
Runtime (décompilé) : `sql`, `inputField/inputFieldType/inputJDBCType` (si `inputField` absent → pas de
paramètres), `outputField/outputFieldType/outputJDBCType` (FieldMap construit avec ces tableaux), `maxRow`,
`queryTimeOut`, `resultRowField/resultRowFieldType`. Signature générée par les domaines `inputFieldNames` /
`outputFieldNames` : `realInputFields = inputField`, `resultField = results[].<col>`,
`resultFieldType = java.lang.String[]`, `realOutputField = results[].<col>`. Exemple qui marche (2 paramètres) :
```json
{"sql":"SELECT o.order_line_id, ... WHERE o.order_line_id > ? AND o.order_line_id <= ?",
 "sqlFieldType":"java.lang.String",
 "colInfo":"0;from_id;BIGINT;IN;\n1;to_id;BIGINT;IN;\n0;order_line_id;BIGINT;OUT;\n1;order_id;VARCHAR;OUT;\n",
 "inputColIndexes":["0","1"], "inputExpression":["from_id","to_id"], "inputJDBCType":["BIGINT","BIGINT"],
 "inputFieldType":["java.lang.String","java.lang.String"], "inputField":["from_id","to_id"], "realInputFields":["from_id","to_id"],
 "outputColIndexes":["0","1"], "outputExpression":["order_line_id","order_id"], "outputJDBCType":["BIGINT","VARCHAR"],
 "outputFieldType":["java.lang.String","java.lang.String"], "outputField":["order_line_id","order_id"],
 "resultField":["results[].order_line_id","results[].order_id"], "resultFieldType":["java.lang.String[]","java.lang.String[]"],
 "realOutputField":["results[].order_line_id","results[].order_id"],
 "maxRow":"0", "queryTimeOut":"-1", "resultRowField":"", "resultRowFieldType":"", "designTimeLocale":"en",
 "userid":"overrideCredentials.$dbUser","useridType":"java.lang.String","inputUseridSign":"overrideCredentials.$dbUser",
 "password":"overrideCredentials.$dbPassword","passwordType":"java.lang.String","inputPasswordSign":"overrideCredentials.$dbPassword"}
```
Règles : entiers en chaînes ; **omettre** tout tableau vide ; `resultRowField` = nom d'un champ de sortie
supplémentaire contenant le nombre de lignes (utile pour INSERT/UPDATE) ; `java.lang.String` convient pour
DATE, TIMESTAMP (`yyyy-MM-dd HH:mm:ss.SSS`), NUMERIC, BOOLEAN (`true`/`false`) en entrée comme en sortie ;
sortie `<svc>Output/results[]` (liste vide si aucune ligne).

### B2. BatchInsert (template `com.wm.adapter.wmjdbc.services.BatchInsert`)
Signature : `<svc>Input/inputs[]` (liste de documents) → `<svc>Output/updateCount[]`. Colonnes depuis le
lookup `columnInfo(catalog, schema, table)` (format par colonne `name\nTYPE(len) NOT NULL\n<code
java.sql.Types>\n<position>\n"\n`, colonnes séparées par `\n` ; code 16 = BOOLEAN, 91 = DATE, 93 = TIMESTAMP,
-5 = BIGINT, 2 = NUMERIC, 4 = INTEGER, 5 = SMALLINT, 12 = VARCHAR) ; exclure les colonnes serial/identity.
```json
{"tables.tableIndexes":["T1"],"tables.catalogName":["stardemo"],"tables.schemaName":["dwh"],"tables.tableName":["dim_customer"],
 "tables.tableType":["TABLE"],"tables.columnInfo":["<chaîne columnInfo>"],"tables.realSchemaName":["dwh"],
 "update.column":["customer_code","customer_name"],"update.columnType":["CHARACTER(10) VARYING NOT NULL","..."],
 "update.JDBCType":["VARCHAR","VARCHAR"],"update.expression":["?","?"],
 "update.inputColumn":["customer_code","customer_name"],"update.inputColumnType":["...","..."],"update.inputJDBCType":["VARCHAR","VARCHAR"],
 "update.inputField":["customer_code","customer_name"],"update.inputFieldType":["java.lang.String","java.lang.String"],
 "update.batchInputField":["inputs[].customer_code","inputs[].customer_name"],"update.batchInputFieldType":["java.lang.String[]","java.lang.String[]"],
 "update.realInputField":["inputs[].customer_code","inputs[].customer_name"],"update.queryTimeOut":"-1",
 "updatecount.fieldName":"updateCount","updatecount.updateCountOutputName":["updateCount[]"],
 "updatecount.updateCountOutputType":["java.lang.String[]"],"updatecount.realOutput":["updateCount[]"], ...userid/password comme ci-dessus}
```
Le SQL généré est `INSERT INTO <catalog>.<schema>.<table>(cols) VALUES (?, ...)` (3 segments : OK pour
PostgreSQL si catalog = base courante). Si `inputs` est absent du pipeline, le service fait un `executeUpdate`
sans paramètres → `(07009/0) [IBM][PostgreSQL JDBC Driver]Invalid parameter binding(s)` : message trompeur
à documenter (cause = liste non fournie). Perf : 20 000 lignes/lot, ~8 700 lignes/s de bout en bout avec la
connexion `otherProperties: "BatchPerformanceWorkaround=true"` (accepté par DataDirect PostgreSQL).

### B3. Connexions / transactions
`LOCAL_TRANSACTION` + `pub.art.transaction:startTransaction`/`commitTransaction`/`rollbackTransaction`
explicites dans chaque sous-flux (nom de transaction libre) : OK, y compris TRUNCATE dans la transaction.
Journal sur une 2e connexion `NO_TRANSACTION` pour rendre les écritures visibles pendant le run.

## C. Propositions de nouveaux outils
1. `jdbc_custom_sql_create(service, connection, sql, inputs=[{name,jdbcType}], outputs=[{name,jdbcType}],
   result_row_field?)` : construit tous les settings B1 (colInfo, index, realInputFields, resultField…), tente
   `customSQLcolInfo`, sinon exige la liste explicite ; vérifie l'existence après création.
2. `jdbc_batch_insert_create(service, connection, catalog, schema, table, exclude_columns=[])` : columnInfo →
   settings B2 automatiques (idem pour Insert/BatchUpdate).
3. `flow_verify(service, expected_json?)` ou option `verify` (A8).
4. Un « constructeur de flow » documenté comme approche recommandée : `wm/flows.py` du PoC montre le pattern
   (copy/setv/delete/invoke/loop/branch/try_catch → JSON putNode) en ~120 lignes ; une ressource
   `wm://docs/putnode-builder` avec ce pattern éviterait la voie FSL.
5. `service_invoke` : option `timeout` par appel (un pipeline de 2 min dépasse `WM_IS_TIMEOUT` par défaut) et
   erreurs structurées (A3).

## D. Patterns vérifiés (bons à documenter)
- LOOP `in-array`/`out-array` avec chemins `;4;0;<docType>` pour l'élément courant ; MAPSET `variables:"true"`
  avec `%dates/year_num%-T%dates/quarter_num%` sur l'élément courant ; BRANCH `switch` sur `/dates/day_of_week`
  dans la LOOP ; `EXIT from=$loop` dans un BRANCH dans la LOOP.
- TRY/CATCH FORM + `pub.flow:getLastError` (`/lastError;4;0;pub.event:exceptionInfo/error;1;0`) + BRANCH
  `$null`/`$default` sur `txName` pour ne rollbacker que si une transaction est ouverte + `EXIT $flow FAILURE`
  avec `failure-message: "loadFactChunk : %errorMsg%"` (substitution OK).
- `pub.scheduler:addOneTimeTask` : `date` `yyyy/MM/dd`, `time` `HH:mm:ss`, refuse le passé
  (`[ISS.0085.9114]`) → `pub.date:incrementDate(addSeconds=3)` avant.
- Durées : `pub.date:currentNanoTime` → Long, `elapsedNanoTime` → Long, `pub.string:objectToString` (sortie
  `string`), `pub.math:divideFloats(precision 0)` + `roundNumber`.
- Invocation JSON pour une UI : `POST /invoke/<folder>/<svc>` avec `Content-Type`/`Accept: application/json`
  + Basic auth ; fichiers `pub/` du package servis avec auth (401 anonyme sur cet IS).
- `adapter_connection_create/enable/state` et lookups `catalogNames`, `columnInfo`, `resultField`,
  `batchResultFieldType`, `supportedJavaTypes` : conformes à la doc.

## E. Chiffres du PoC (pour situer)
999 343 lignes source → 4 dimensions (< 0,5 s chacune) + 999 343 faits en 1 min 57 s (50 lots de 20 000,
≈ 2,3 s/lot, ≈ 8 700 lignes/s), réconciliation exacte. Détails : `README.md`.
