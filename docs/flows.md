# Les flows de la démo : comment les transformations sont réalisées

Package Integration Server **StarSchemaETL** (namespace racine `star`). Tout est construit avec des briques
standard de webMethods : flow services, services adaptateur JDBC, transactions ART, scheduler. L'arbre exact de
chaque flow (tel que déployé) est dans `docs/flows-trees.md` et à l'écran sur
`http://localhost:5555/StarSchemaETL/flows.html`.

## 1. Vue d'ensemble

```
                          star.etl:startPipeline  (scheduler IS, +3 s)
                                     │
                          star.etl:runPipeline / runPipelineX2 / runPipelineX4   (orchestrateur)
   TRUNCATE_STAR ─► DIM_DATE ─► DIM_CUSTOMER ─► DIM_SALESREP ─► DIM_PRODUCT ─► plan de lots ─► LOOP (1, 2 ou 4 lots en parallèle)
        │             │              │               │               │                              │
  truncateStar     loadDates     loadCustomers   loadSalesreps   loadProducts                 loadFactChunk (fromId, toId)
        └─────────────┴──────────────┴───────────────┴───────────────┴──────────────────────────────┘
                                   chaque étape : beginStep → travail → logStep (dwh.etl_run_log)
```

| Couche | Rôle | Services |
|---|---|---|
| Orchestration | ordre des étapes, journal, arrêt, statut | `star.etl:runPipeline*`, `star.etl:startPipeline` |
| Étapes (sous-flux) | une unité de travail transactionnelle par étape | `star.etl.steps:truncateStar`, `loadDates`, `loadCustomers`, `loadSalesreps`, `loadProducts`, `loadFactChunk` |
| Journalisation | horodatage et durée par étape | `star.etl.steps:beginStep`, `star.etl.steps:logStep` |
| Accès aux données | SQL d'extraction et de chargement | `star.adapters:*` (CustomSQL, BatchInsert) sur `star.connections:dwh` (transactionnelle) et `star.connections:dwhLog` (sans transaction) |
| API de pilotage | JSON pour l'UI | `star.api:status`, `chart`, `start`, `stop`, `reset`, `analyze`, `dimension`, `source` |

Deux connexions JDBC vers la même base, volontairement :

- `dwh` en **LOCAL_TRANSACTION** : les chargements, avec des transactions explicites (`pub.art.transaction:startTransaction` / `commitTransaction` / `rollbackTransaction`) ;
- `dwhLog` en **NO_TRANSACTION** : le journal, le drapeau d'arrêt et les requêtes de l'UI, pour que chaque ligne de journal soit visible dès qu'elle est écrite, même pendant une transaction de chargement.

## 2. Le patron d'une étape (sous-flux)

Toutes les étapes suivent le même squelette, en TRY / CATCH :

```
TRY
  pub.art.transaction:startTransaction        → txName
  ... extraction (adaptateur CustomSQL) ...
  ... transformation (MAP / LOOP / pub.*) ...
  ... chargement (adaptateur BatchInsert) ...
  pub.list:sizeOfList                          → rowCount (sortie de l'étape)
  pub.art.transaction:commitTransaction
CATCH
  pub.flow:getLastError                        → errorMsg
  BRANCH txName : $null → rien ; sinon rollbackTransaction
  EXIT $flow FAILURE « <étape> : %errorMsg% »
```

Ce qui est ainsi garanti : une étape est **atomique** (tout ou rien), **rejouable** (elle ne laisse pas de demi-lot),
et **courte** (un lot de 20 000 lignes dure 2 à 3 s, très en dessous des 5 minutes exigées pour un sous-flux).
L'orchestrateur ne touche jamais aux données lui-même : il enchaîne les étapes et journalise.

## 3. Les transformations, étape par étape

### 3.1 Dimensions simples — `loadCustomers`, `loadSalesreps`, `loadProducts`

| Source (`staging.orders`) | Cible | Règle |
|---|---|---|
| `customer_code, customer_name, customer_city, customer_dept, customer_segment` | `dwh.dim_customer` (`customer_key` serial, `customer_code` unique, `customer_name, city, dept, segment`) | `SELECT DISTINCT` sur la source (adaptateur `selectCustomers`), renommage des colonnes dans le SQL, clé de substitution générée par la séquence de la base |
| `salesrep_code, salesrep_name, salesrep_region` | `dwh.dim_salesrep` | idem (`selectSalesreps` → `insertSalesreps`) |
| `product_code, product_name, product_category, product_brand` | `dwh.dim_product` | idem (`selectProducts` → `insertProducts`) |

Le flow copie la liste de documents renvoyée par le CustomSQL (`<svc>Output/results[]`) directement dans l'entrée
du BatchInsert (`<svc>Input/inputs[]`) : les noms de champs sont alignés par construction (alias SQL = colonnes
cible), donc **une seule copie de référence**, sans boucle. Le BatchInsert émet un seul `executeBatch` JDBC.

### 3.2 Dimension temporelle — `loadDates`

Entrée : les 1 096 dates distinctes de la source (`selectDates`). Le flow itère (LOOP `rawDates` → `dates`) et
calcule chaque attribut avec `pub.date:dateTimeFormat` (locale `fr_FR`, règle ISO), `pub.math` et un BRANCH :

| Colonne `dwh.dim_date` | Exemple (2025-09-08) | Étape du flow |
|---|---|---|
| `date_key` | 20250908 | `dateTimeFormat yyyyMMdd` — clé référencée par la table de faits |
| `full_date` | 2025-09-08 | copie |
| `year_num` | 2025 | `yyyy` |
| `quarter_num` | 3 | `pub.math:addInts (mois + 2)` puis `pub.math:divideInts (/ 3)` |
| `quarter_label` | 2025-T3 | MAPSET avec substitution `%dates/year_num%-T%dates/quarter_num%` |
| `month_num`, `month_name`, `year_month` | 9, septembre, 2025-09 | `M`, `MMMM`, `yyyy-MM` |
| `week_of_year`, `year_week` | 37, 2025-S37 | `w`, `YYYY-'S'ww` : semaines ISO (lundi, 4 jours minimum) → 2023-01-01 = `2022-S52`, 2024-12-30 = `2025-S01` |
| `day_of_month`, `day_of_week`, `day_name` | 8, 1, lundi | `d`, `u` (1 = lundi … 7 = dimanche), `EEEE` |
| `is_weekend` | false | BRANCH sur `day_of_week` : 6 ou 7 → true, sinon false |

Le tableau de sortie de la LOOP (`dates`) est ensuite chargé d'un bloc par `insertDates`. Point à retenir pour
la discussion ETL : **la logique calendaire vit dans le flow**, pas dans la base, et elle est visible pas à pas
dans Designer (ou dans `flows.html`).

### 3.3 Table de faits — `loadFactChunk (fromId, toId)`

1. **Extraction + lookup** (`selectFactChunk`) : une requête paramétrée sur l'intervalle `]fromId, toId]` de
   `order_line_id`, qui joint la source aux trois dimensions sur leurs codes métier pour rapporter les clés de
   substitution (`customer_key`, `salesrep_key`, `product_key`) et calcule `date_key = to_char(order_date, 'YYYYMMDD')`.
   C'est l'équivalent des « lookups » d'un ETL, réalisé par jointure dans la base (le meilleur endroit pour le faire).
2. **Transformation ligne à ligne** : LOOP sur `rows` (type `star.docs:FactRow`) vers `facts` (type `star.docs:Fact`) :
   - MAP : projection des 8 champs (`order_line_id, order_id, date_key, customer_key, salesrep_key, product_key, quantity, unit_price`) ;
   - `pub.math:multiplyFloats (quantity × unit_price, précision 2)` → `amount`.
   Une règle métier supplémentaire (remise, devise, TVA, filtrage) s'ajouterait ici, sous forme de MAP, BRANCH ou
   INVOKE, sans toucher au SQL.
3. **Chargement** : `insertFacts` (BatchInsert, 9 colonnes) ; `loaded_at` est renseigné par défaut par la base.
4. `commit`, ou `rollback` + échec en cas d'erreur (le lot est alors rejouable à l'identique).

### 3.4 Vidage — `truncateStar`

`SELECT dwh.truncate_star()` (fonction PL/pgSQL : TRUNCATE des cinq tables cibles, séquences remises à zéro),
dans une transaction comme les autres étapes.

## 4. L'orchestrateur — `runPipeline` (et `runPipelineX2`, `runPipelineX4`)

1. Valeurs par défaut (`chunkSize` = 20 000), identifiant `RUN-yyyyMMdd-HHmmss`, ligne `PIPELINE` en `RUNNING`
   dans `dwh.etl_run_log` (visible immédiatement par l'UI grâce à la connexion sans transaction).
2. TRY : les cinq étapes de préparation, chacune encadrée par `beginStep` (date lisible + compteur nanosecondes)
   et `logStep` (durée en ms calculée par le flow, nombre de lignes, statut).
3. **Plan de lots** : `selectChunks` renvoie la liste `(chunk_no, from_id, to_id)` par `generate_series` sur
   `order_line_id` ; la taille de lot vient de l'UI.
4. **LOOP sur le plan** (1, 2 ou 4 itérations simultanées selon la variante, attribut `MAX-THREADS` de la LOOP) :
   lecture du drapeau d'arrêt (`dwh.etl_control`) → si levé, le lot est ignoré ; sinon `loadFactChunk` puis
   `logStep FACT_CHUNK_n`. Aucune variable partagée entre itérations (compatible multithread) ; le total chargé est
   relu en base après la boucle.
5. Statut final : `STOPPED` si le drapeau a été levé, `DONE` sinon ; CATCH → `FAILED` avec le message d'erreur.
6. `PIPELINE_END` puis mise à jour de la ligne `PIPELINE` (durée totale, lignes, statut, message).

Le parallélisme ne change **rien** à la logique métier : `runPipelineX4` est le même flow avec `MAX-THREADS = 4`
sur la LOOP ; chaque itération porte sa propre transaction sur sa propre connexion du pool.

## 5. Lancement, arrêt, réinitialisation

- `star.etl:startPipeline (chunkSize, threads)` : choisit l'orchestrateur, calcule « maintenant + 3 s »
  (`pub.date:incrementDate`) et le planifie avec `pub.scheduler:addOneTimeTask` (tâche unique, utilisateur
  `Administrator`). L'appel HTTP rend la main tout de suite.
- `star.api:start` refuse le lancement si la dernière exécution est encore `RUNNING`, réarme le drapeau d'arrêt
  puis appelle `startPipeline`.
- `star.api:stop` positionne `stop_requested = true` ; l'orchestrateur saute les lots restants et se termine
  proprement en `STOPPED` (les lots en cours sont commités).
- `star.api:reset` appelle `dwh.reset_demo()` : cinq tables vidées, journal purgé, drapeau réarmé.

## 6. Ce que l'UI interroge

| API | Requêtes (connexion `dwhLog`) | Usage |
|---|---|---|
| `status` (toutes les 2 s) | volumes par table, journal de la dernière exécution, 6 dernières lignes de faits jointes aux dimensions, 6 prochaines lignes source | compteurs, schéma en étoile, journal, « avant / après » |
| `chart` (toutes les 6 s) | CA par mois (`fact_sales ⋈ dim_date`) | graphique |
| `analyze (axis)` | 13 requêtes en liste blanche (`anYear`, `anQuarter`, `anMonth`, `anWeek`, `anWeekday`, `anSegment`, `anDept`, `anCustomer`, `anRegion`, `anSalesrep`, `anCategory`, `anBrand`, `anProduct`) : CA, quantités, lignes, panier moyen | panneau « Explorer » |
| `dimension (name)` | 12 premières lignes de `dim_date`, `dim_customer`, `dim_salesrep`, `dim_product` | contenu des dimensions |
| `source` | lignes, montant, commandes, période de `staging.orders` | réconciliation affichée |

## 7. Traçabilité (lineage) résumée

| `staging.orders` | → | cible | par |
|---|---|---|---|
| `order_line_id`, `order_id`, `quantity`, `unit_price` | → | `fact_sales` (+ `amount`) | `loadFactChunk` |
| `order_date` | → | `dim_date` (13 attributs) et `fact_sales.date_key` | `loadDates`, `selectFactChunk` |
| `customer_*` | → | `dim_customer` et `fact_sales.customer_key` | `loadCustomers`, jointure dans `selectFactChunk` |
| `salesrep_*` | → | `dim_salesrep` et `fact_sales.salesrep_key` | `loadSalesreps`, jointure |
| `product_*` | → | `dim_product` et `fact_sales.product_key` | `loadProducts`, jointure |

Contrôles de bout en bout : `dwh.v_reconciliation` (lignes et montant source = faits) et la comparaison ligne à
ligne `amount = round(quantity × unit_price, 2)` (0 écart sur 999 343 lignes).

## 8. Comment modifier ou étendre

- **Nouvelle règle de transformation** : dans `wm/flows.py`, ajouter une étape dans la LOOP de `LOAD_FACT_CHUNK`
  (MAP / BRANCH / INVOKE `pub.*`), puis `python3 wm/flows.py loadFactChunk` et `python3 wm/test_steps.py`.
- **Nouvelle dimension ou nouvelle table de faits** : un CustomSQL d'extraction + un BatchInsert (`wm/adapters.py`),
  un type de document si une LOOP doit typer ses éléments, un sous-flux sur le patron du §2, une ligne
  `step_block(...)` dans l'orchestrateur.
- **Nouvelle source** (autre table de staging) : mêmes briques ; la spécification du client prévoit ~80 tables de
  staging, ~50 normalisées et ~90 tables de faits, chacune devenant un sous-flux journalisé de moins de 5 minutes.
