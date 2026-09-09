# Arbres des flow services (générés par wm/flowdoc.py)
Chaque étape telle que déployée sur l'Integration Server (package StarSchemaETL).

## star.etl:runPipeline

Orchestrateur ETL (1 lot(s) de faits en parallèle) : vide le schéma en étoile, charge les 4 dimensions (dont la dimension temporelle calculée) puis la table de faits par lots transactionnels journalisés ; drapeau d arrêt testé entre deux lots.

*Entrée* : `chunkSize, lang` · *Sortie* : `runId, status, totalRows, durationMs`

- MAP 5 affectations — *valeurs par défaut*
- BRANCH sur `/lang` — *langue de la dimension temporelle*
  - SEQUENCE [en]
    - MAP 3 affectations
  - SEQUENCE [$default]
    - MAP 3 affectations
- INVOKE `pub.date:getCurrentDateString` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions)
- INVOKE `star.etl.steps:beginStep` (sortie : 2 copies, 2 suppressions)
- INVOKE `star.adapters:insertLog` (entrée : 2 copies, 3 affectations · sortie : 2 suppressions) — *ligne PIPELINE en RUNNING (visible par l UI)*
- TRY
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:truncateStar` — *vidage du schéma en étoile*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadDates` — *dimension temporelle*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadCustomers` — *dimension client*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadSalesreps` — *dimension commercial*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadProducts` — *dimension produit*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.adapters:selectChunks` (entrée : 2 copies · sortie : 1 copie, 2 suppressions) — *plan de lots (generate_series sur order_line_id)*
  - LOOP sur `/chunks` — *un lot par itération, 1 en parallèle (sous-flux < 5 min)*
    - INVOKE `star.adapters:selectStopFlag` (sortie : 1 copie, 1 suppression) — *drapeau d arrêt (dwh.etl_control)*
    - BRANCH sur `/stopFlag` — *arrêt demandé ?*
      - SEQUENCE [true]
        - MAP 1 suppression — *arrêt demandé : lot ignoré (compatible LOOP parallèle)*
      - SEQUENCE [$default]
        - MAP 3 copies — *bornes du lot courant*
        - INVOKE `star.etl.steps:beginStep`
        - INVOKE `star.etl.steps:loadFactChunk` — *sous-flux transactionnel : un lot*
        - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 3 affectations · sortie : 10 suppressions)
        - MAP 4 suppressions
  - INVOKE `star.adapters:selectCounts` (sortie : 1 copie, 1 suppression) — *total des lignes chargées, relu en base (sûr quel que soit le parallélisme)*
  - MAP 1 suppression
  - INVOKE `star.adapters:selectStopFlag` (sortie : 1 copie, 1 suppression)
  - BRANCH sur `/stopFlag` — *arrêté par l utilisateur ?*
    - SEQUENCE [true]
      - MAP 1 affectation
  - BRANCH sur `/pipeStatus`
    - SEQUENCE [RUNNING]
      - MAP 1 affectation
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copie, 3 suppressions)
  - MAP 1 affectation
- INVOKE `star.etl.steps:logStep` (entrée : 5 copies, 1 affectation · sortie : 6 suppressions) — *durée totale (ligne PIPELINE_END)*
- INVOKE `star.adapters:updatePipelineLog` (entrée : 6 copies · sortie : 2 suppressions) — *clôture de la ligne PIPELINE*
- MAP 1 copie, 18 suppressions

## star.etl.steps:loadFactChunk

Sous-flux transactionnel : charge les lignes order_line_id dans ]fromId, toId] dans dwh.fact_sales (extraction + lookup SQL, montant calculé en flow, BatchInsert). Rollback en cas d erreur.

*Entrée* : `fromId, toId` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions) — *début de transaction locale (star.connections:dwh)*
  - INVOKE `star.adapters:selectFactChunk` (entrée : 2 copies · sortie : 1 copie, 2 suppressions) — *extraction du lot + lookup des clés de dimension (jointure)*
  - LOOP sur `/rows` → `/facts` — *transformation ligne à ligne*
    - MAP 8 copies — *projection vers la table de faits*
    - INVOKE `pub.math:multiplyFloats` (entrée : 2 copies, 1 affectation · sortie : 1 copie, 4 suppressions) — *montant = quantité x prix unitaire*
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copie · sortie : 1 copie, 2 suppressions) — *nombre de lignes*
  - INVOKE `star.adapters:insertFacts` (entrée : 1 copie · sortie : 2 suppressions) — *BatchInsert JDBC (un seul executeBatch)*
  - MAP 2 suppressions
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copie, 3 suppressions)
  - BRANCH sur `/txName` — *rollback si une transaction est ouverte*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *rollback*
  - EXIT $flow / FAILURE « loadFactChunk : %errorMsg% »

## star.etl.steps:loadDates

Dimension temporelle : pour chaque date distincte de staging.orders, le flow calcule les attributs calendaires puis BatchInsert dans dwh.dim_date. Une transaction.

*Entrée* : `dimLocale, quarterLetter, weekLetter` · *Sortie* : `rowCount`

- TRY
  - MAP 3 affectations — *langue de la dimension : fr_FR / T / S par défaut, en_GB / Q / W pour une démo en anglais*
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions) — *début de transaction locale (star.connections:dwh)*
  - INVOKE `star.adapters:selectDates` (sortie : 1 copie, 1 suppression) — *dates distinctes de la source*
  - LOOP sur `/rawDates` → `/dates` — *une itération par date : calcul des attributs calendaires*
    - MAP 2 copies
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 4 suppressions) — *clé yyyymmdd*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 4 suppressions) — *année*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 4 suppressions) — *mois*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 2 copies, 2 affectations · sortie : 1 copie, 5 suppressions) — *nom du mois (fr)*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 4 suppressions) — *année-mois*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 2 copies, 2 affectations · sortie : 1 copie, 5 suppressions) — *semaine ISO (lundi premier jour, 4 jours minimum)*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 2 copies, 2 affectations · sortie : 1 copie, 5 suppressions) — *année ISO + semaine, ex : 2025-S01 (fr) / 2025-W01 (en)*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 4 suppressions) — *jour du mois*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 4 suppressions) — *1=lundi ... 7=dimanche*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 2 copies, 2 affectations · sortie : 1 copie, 5 suppressions) — *nom du jour (fr)*
    - INVOKE `pub.math:addInts` (entrée : 1 copie, 1 affectation · sortie : 1 copie, 3 suppressions) — *trimestre = (mois + 2) / 3*
    - INVOKE `pub.math:divideInts` (entrée : 1 copie, 1 affectation · sortie : 1 copie, 4 suppressions)
    - MAP 1 affectation — *libellé 2024-T3 (fr) / 2024-Q3 (en)*
    - BRANCH sur `/dates/day_of_week` — *week-end si samedi ou dimanche*
      - SEQUENCE [6]
        - MAP 1 affectation
      - SEQUENCE [7]
        - MAP 1 affectation
      - SEQUENCE [$default]
        - MAP 1 affectation
    - MAP 1 suppression
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copie · sortie : 1 copie, 2 suppressions) — *nombre de lignes*
  - INVOKE `star.adapters:insertDates` (entrée : 1 copie · sortie : 2 suppressions) — *BatchInsert JDBC (un seul executeBatch)*
  - MAP 2 suppressions
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copie, 3 suppressions)
  - BRANCH sur `/txName` — *rollback si une transaction est ouverte*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *rollback*
  - EXIT $flow / FAILURE « loadDates : %errorMsg% »

## star.etl.steps:loadCustomers

Dimension client

*Entrée* : `—` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions) — *début de transaction locale (star.connections:dwh)*
  - INVOKE `star.adapters:selectCustomers` (sortie : 1 copie, 1 suppression) — *extraction SELECT DISTINCT depuis staging.orders*
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copie · sortie : 1 copie, 2 suppressions) — *nombre de lignes*
  - INVOKE `star.adapters:insertCustomers` (entrée : 1 copie · sortie : 2 suppressions) — *BatchInsert JDBC (un seul executeBatch)*
  - MAP 1 suppression
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copie, 3 suppressions)
  - BRANCH sur `/txName` — *rollback si une transaction est ouverte*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *rollback*
  - EXIT $flow / FAILURE « loadCustomers : %errorMsg% »

## star.etl.steps:logStep

Journalise une étape dans dwh.etl_run_log avec sa durée (ms) calculée par le flow.

*Entrée* : `runId, stepName, startedAt, startNano, rowCount, status, message` · *Sortie* : `durationMs, endedAt`

- INVOKE `pub.date:getCurrentDateString` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions)
- INVOKE `pub.date:elapsedNanoTime` (entrée : 1 copie · sortie : 1 copie, 3 suppressions)
- INVOKE `pub.string:objectToString` (entrée : 1 copie · sortie : 1 copie, 3 suppressions)
- INVOKE `pub.math:divideFloats` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 5 suppressions) — *ns -> ms*
- INVOKE `pub.math:roundNumber` (entrée : 1 copie, 1 affectation · sortie : 1 copie, 4 suppressions)
- INVOKE `star.adapters:insertLog` (entrée : 8 copies · sortie : 2 suppressions) — *dwh.etl_run_log (connexion sans transaction : visible immédiatement)*

## star.etl:startPipeline

Lancement asynchrone : planifie l orchestrateur (1, 2 ou 4 lots en parallèle) dans 3 secondes via le scheduler de l IS.

*Entrée* : `chunkSize, threads, lang` · *Sortie* : `taskID, scheduledAt, service`

- MAP 3 affectations
- BRANCH sur `/threads` — *orchestrateur selon le parallélisme demandé*
  - SEQUENCE [2]
    - MAP 1 affectation
  - SEQUENCE [4]
    - MAP 1 affectation
  - SEQUENCE [$default]
    - MAP 1 affectation
- INVOKE `pub.date:getCurrentDateString` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions)
- INVOKE `pub.date:incrementDate` (entrée : 1 copie, 3 affectations · sortie : 1 copie, 6 suppressions) — *+3 s (le scheduler refuse une heure passée)*
- INVOKE `pub.string:substring` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 4 suppressions)
- INVOKE `pub.string:substring` (entrée : 1 copie, 2 affectations · sortie : 1 copie, 4 suppressions)
- INVOKE `pub.scheduler:addOneTimeTask` (entrée : 4 copies, 2 affectations · sortie : 12 suppressions) — *tâche unique du scheduler IS*

## star.etl:runPipelineX4

Orchestrateur ETL (4 lot(s) de faits en parallèle) : vide le schéma en étoile, charge les 4 dimensions (dont la dimension temporelle calculée) puis la table de faits par lots transactionnels journalisés ; drapeau d arrêt testé entre deux lots.

*Entrée* : `chunkSize, lang` · *Sortie* : `runId, status, totalRows, durationMs`

- MAP 5 affectations — *valeurs par défaut*
- BRANCH sur `/lang` — *langue de la dimension temporelle*
  - SEQUENCE [en]
    - MAP 3 affectations
  - SEQUENCE [$default]
    - MAP 3 affectations
- INVOKE `pub.date:getCurrentDateString` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions)
- INVOKE `star.etl.steps:beginStep` (sortie : 2 copies, 2 suppressions)
- INVOKE `star.adapters:insertLog` (entrée : 2 copies, 3 affectations · sortie : 2 suppressions) — *ligne PIPELINE en RUNNING (visible par l UI)*
- TRY
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:truncateStar` — *vidage du schéma en étoile*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadDates` — *dimension temporelle*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadCustomers` — *dimension client*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadSalesreps` — *dimension commercial*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadProducts` — *dimension produit*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 affectations · sortie : 9 suppressions)
  - INVOKE `star.adapters:selectChunks` (entrée : 2 copies · sortie : 1 copie, 2 suppressions) — *plan de lots (generate_series sur order_line_id)*
  - LOOP sur `/chunks` · 4 itérations en parallèle — *un lot par itération, 4 en parallèle (sous-flux < 5 min)*
    - INVOKE `star.adapters:selectStopFlag` (sortie : 1 copie, 1 suppression) — *drapeau d arrêt (dwh.etl_control)*
    - BRANCH sur `/stopFlag` — *arrêt demandé ?*
      - SEQUENCE [true]
        - MAP 1 suppression — *arrêt demandé : lot ignoré (compatible LOOP parallèle)*
      - SEQUENCE [$default]
        - MAP 3 copies — *bornes du lot courant*
        - INVOKE `star.etl.steps:beginStep`
        - INVOKE `star.etl.steps:loadFactChunk` — *sous-flux transactionnel : un lot*
        - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 3 affectations · sortie : 10 suppressions)
        - MAP 4 suppressions
  - INVOKE `star.adapters:selectCounts` (sortie : 1 copie, 1 suppression) — *total des lignes chargées, relu en base (sûr quel que soit le parallélisme)*
  - MAP 1 suppression
  - INVOKE `star.adapters:selectStopFlag` (sortie : 1 copie, 1 suppression)
  - BRANCH sur `/stopFlag` — *arrêté par l utilisateur ?*
    - SEQUENCE [true]
      - MAP 1 affectation
  - BRANCH sur `/pipeStatus`
    - SEQUENCE [RUNNING]
      - MAP 1 affectation
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copie, 3 suppressions)
  - MAP 1 affectation
- INVOKE `star.etl.steps:logStep` (entrée : 5 copies, 1 affectation · sortie : 6 suppressions) — *durée totale (ligne PIPELINE_END)*
- INVOKE `star.adapters:updatePipelineLog` (entrée : 6 copies · sortie : 2 suppressions) — *clôture de la ligne PIPELINE*
- MAP 1 copie, 18 suppressions

## star.api:start

Lance la démo (garde anti-double lancement) : réarme le drapeau d arrêt puis planifie le pipeline.

*Entrée* : `chunkSize, threads, lang` · *Sortie* : `started, message, taskID, scheduledAt, service`

- INVOKE `star.adapters:selectRunLog` (sortie : 1 copie, 1 suppression) — *statut de la dernière exécution*
- BRANCH sur `/lastStatus` — *refus si un pipeline tourne déjà*
  - SEQUENCE [RUNNING]
    - MAP 2 affectations
  - SEQUENCE [$default]
    - INVOKE `star.adapters:setStopFlag` (entrée : 1 affectation · sortie : 2 suppressions)
    - INVOKE `star.etl:startPipeline` (sortie : 3 suppressions)
    - MAP 2 affectations
- MAP 1 suppression

## star.api:analyze

Analyse par dimension pour l UI : axe (année, trimestre, mois, jour, segment, département, client, région, commercial, catégorie, marque, produit) → CA, quantités, lignes, panier moyen.

*Entrée* : `axis` · *Sortie* : `axis, rows[], error`

- BRANCH sur `/axis` — *requêtes en liste blanche sur fact_sales ⋈ dimension*
  - SEQUENCE [anYear]
    - INVOKE `star.adapters:anYear` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anQuarter]
    - INVOKE `star.adapters:anQuarter` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anMonth]
    - INVOKE `star.adapters:anMonth` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anWeek]
    - INVOKE `star.adapters:anWeek` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anWeekday]
    - INVOKE `star.adapters:anWeekday` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anSegment]
    - INVOKE `star.adapters:anSegment` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anDept]
    - INVOKE `star.adapters:anDept` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anCustomer]
    - INVOKE `star.adapters:anCustomer` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anRegion]
    - INVOKE `star.adapters:anRegion` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anSalesrep]
    - INVOKE `star.adapters:anSalesrep` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anCategory]
    - INVOKE `star.adapters:anCategory` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anBrand]
    - INVOKE `star.adapters:anBrand` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [anProduct]
    - INVOKE `star.adapters:anProduct` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [$default]
    - MAP 1 affectation

## star.etl.steps:beginStep

Horodatage de début d étape (date lisible + compteur nanosecondes).

*Entrée* : `—` · *Sortie* : `stepStart, stepNano`

- INVOKE `pub.date:getCurrentDateString` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions)
- INVOKE `pub.date:currentNanoTime` (sortie : 1 copie, 1 suppression)

## star.etl.steps:truncateStar

Vide le schéma en étoile (faits + dimensions, séquences remises à zéro).

*Entrée* : `—` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions) — *début de transaction locale (star.connections:dwh)*
  - INVOKE `star.adapters:truncateStar` (sortie : 1 suppression) — *dwh.truncate_star()*
  - MAP 1 affectation
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copie, 3 suppressions)
  - BRANCH sur `/txName` — *rollback si une transaction est ouverte*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *rollback*
  - EXIT $flow / FAILURE « truncateStar : %errorMsg% »

## star.etl.steps:loadSalesreps

Dimension commercial

*Entrée* : `—` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions) — *début de transaction locale (star.connections:dwh)*
  - INVOKE `star.adapters:selectSalesreps` (sortie : 1 copie, 1 suppression) — *extraction SELECT DISTINCT depuis staging.orders*
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copie · sortie : 1 copie, 2 suppressions) — *nombre de lignes*
  - INVOKE `star.adapters:insertSalesreps` (entrée : 1 copie · sortie : 2 suppressions) — *BatchInsert JDBC (un seul executeBatch)*
  - MAP 1 suppression
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copie, 3 suppressions)
  - BRANCH sur `/txName` — *rollback si une transaction est ouverte*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *rollback*
  - EXIT $flow / FAILURE « loadSalesreps : %errorMsg% »

## star.etl.steps:loadProducts

Dimension produit

*Entrée* : `—` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions) — *début de transaction locale (star.connections:dwh)*
  - INVOKE `star.adapters:selectProducts` (sortie : 1 copie, 1 suppression) — *extraction SELECT DISTINCT depuis staging.orders*
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copie · sortie : 1 copie, 2 suppressions) — *nombre de lignes*
  - INVOKE `star.adapters:insertProducts` (entrée : 1 copie · sortie : 2 suppressions) — *BatchInsert JDBC (un seul executeBatch)*
  - MAP 1 suppression
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copie, 3 suppressions)
  - BRANCH sur `/txName` — *rollback si une transaction est ouverte*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copie · sortie : 2 suppressions) — *rollback*
  - EXIT $flow / FAILURE « loadProducts : %errorMsg% »

## star.api:status

État de la démo pour l UI (JSON) : volumes, journal de la dernière exécution, dernières lignes transformées, prochaines lignes source.

*Entrée* : `—` · *Sortie* : `serverTime, counts, runLog[], preview[], sourceNext[]`

- INVOKE `pub.date:getCurrentDateString` (entrée : 1 affectation · sortie : 1 copie, 2 suppressions)
- INVOKE `star.adapters:selectCounts` (sortie : 1 copie, 1 suppression)
- INVOKE `star.adapters:selectRunLog` (sortie : 1 copie, 1 suppression)
- INVOKE `star.adapters:selectFactPreview` (sortie : 1 copie, 1 suppression)
- INVOKE `star.adapters:selectSourceNext` (sortie : 1 copie, 1 suppression)

## star.api:dimension

Aperçu des 12 premières lignes d une table de dimension (date, customer, salesrep, product).

*Entrée* : `name` · *Sortie* : `name, rows[], error`

- BRANCH sur `/name` — *aperçu du contenu d une dimension*
  - SEQUENCE [date]
    - INVOKE `star.adapters:dimDateRows` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [customer]
    - INVOKE `star.adapters:dimCustomerRows` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [salesrep]
    - INVOKE `star.adapters:dimSalesrepRows` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [product]
    - INVOKE `star.adapters:dimProductRows` (sortie : 1 copie, 1 suppression)
  - SEQUENCE [$default]
    - MAP 1 affectation
