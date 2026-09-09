# Démo ETL : webMethods Integration Server à la place d'un ETL classique (schéma en étoile)

Scénario de référence : les données de l'ERP arrivent en tables de *staging* (réplication d'un data lake),
sont normalisées puis transformées en tables de faits, avec des sous-flux de moins de 5 minutes.
La démo reproduit ce schéma sur un cas concret : une **table de commandes « classique »** (client, commercial,
produit, quantité, prix unitaire, ~1 million de lignes) transformée par webMethods Integration Server en un
**schéma en étoile** (table de faits centrale + 4 dimensions dont une dimension temporelle), avec une UI de
pilotage et de visualisation en quasi temps réel.

```
 staging.orders (999 343 lignes, 245 Mo)                     dwh (schéma en étoile)
 ┌─────────────────────────────────────┐                     ┌──────────────┐
 │ order_id, order_date                │   webMethods IS     │  dim_date    │ 1 096 (calculée en flow)
 │ customer_code, name, city, dept, …  │ ─── package ──────▶ │  dim_customer│ 5 000
 │ salesrep_code, name, region         │   StarSchemaETL        │  dim_salesrep│   143
 │ product_code, name, category, brand │  (flows + JDBC)     │  dim_product │ 2 000
 │ quantity, unit_price                │                     │  fact_sales  │ 999 343 (amount = qté × PU)
 └─────────────────────────────────────┘                     └──────────────┘
```

## Composants

| Élément | Où | Détail |
|---|---|---|
| Base PostgreSQL 16 | conteneur Docker `stardemo-db`, port **5435** (`stardemo`/`stardemo`, surchargeables par `DB_NAME`, `PG_PORT`, `DB_CONTAINER`) | `db/01_schema.sql` (schémas `staging`, `dwh`, journal `etl_run_log`, pilotage `etl_control`), `db/02_generate_data.sql` (jeu de données reproductible) |
| Integration Server 12.1 | `$IS_HOME` (défaut `/home/cpo/wm12/IntegrationServer/instances/default`), port **5555** (`Administrator`/`manage`) | package **StarSchemaETL** (namespace `star.*`) |
| Connexions JDBC | `star.connections:dwh` (LOCAL_TRANSACTION), `star.connections:dwhLog` (NO_TRANSACTION) | adaptateur JDBC 10.3, driver DataDirect PostgreSQL |
| Services adaptateur | `star.adapters:*` | 24 services CustomSQL / BatchInsert (`wm/adapters.py`) |
| Flows | `star.etl.steps:*`, `star.etl:*` | générés en JSON putNode (`wm/flows.py`) |
| API UI | `star.api:status / start / stop / reset` | JSON via `/invoke/star.api/<service>` |
| UI | `ui/index.html` → `packages/StarSchemaETL/pub/index.html` | **http://localhost:5555/StarSchemaETL/index.html** |

### Flows

- `star.etl:runPipeline` (orchestrateur, variantes `runPipelineX2` / `runPipelineX4` avec `MAX-THREADS` sur
  la LOOP) : TRUNCATE_STAR → DIM_DATE → DIM_CUSTOMER → DIM_SALESREP → DIM_PRODUCT → plan de lots
  (`selectChunks`, `generate_series` sur `order_line_id`) → LOOP : un sous-flux `loadFactChunk` par lot,
  journalisé, avec test du drapeau d'arrêt à chaque lot ; total relu en base après la boucle.
- `star.etl.steps:loadDates` (dimension temporelle) : pour chaque date distincte de la source (1 096 jours), le
  flow calcule avec `pub.date:dateTimeFormat` (locale `fr_FR`, règle ISO), `pub.math` et un BRANCH :

  | Colonne | Exemple | Calcul dans le flow |
  |---|---|---|
  | `date_key` | 20250908 | pattern `yyyyMMdd` (clé de la table de faits) |
  | `year_num`, `quarter_num`, `quarter_label` | 2025, 3, `2025-T3` | `yyyy` ; trimestre = (mois + 2) / 3 (`pub.math:addInts`, `divideInts`) ; libellé par substitution `%dates/year_num%-T%dates/quarter_num%` |
  | `month_num`, `month_name`, `year_month` | 9, septembre, `2025-09` | `M`, `MMMM`, `yyyy-MM` |
  | `week_of_year`, `year_week` | 37, `2025-S37` | `w` et `YYYY-'S'ww` en locale `fr_FR` : semaines ISO (lundi, 4 jours minimum), donc 2023-01-01 → `2022-S52`, 2024-12-30 → `2025-S01` |
  | `day_of_month`, `day_of_week`, `day_name` | 8, 1, lundi | `d`, `u` (1 = lundi … 7 = dimanche), `EEEE` |
  | `is_weekend` | false | BRANCH sur `day_of_week` (6, 7 → true) |

  Les axes Année / Trimestre / Mois / Semaine (ISO) / Jour de semaine de l'explorateur s'appuient sur ces colonnes.
- `star.etl.steps:loadFactChunk` : `startTransaction` → extraction du lot avec résolution des clés de
  substitution par jointure → LOOP ligne à ligne (projection + `amount = quantity × unit_price` via
  `pub.math:multiplyFloats`) → `BatchInsert` (un seul `executeBatch`) → `commitTransaction` ; `rollback` en CATCH.
- `star.etl:startPipeline` : lancement asynchrone par le scheduler IS (`pub.scheduler:addOneTimeTask`, +3 s).
- `star.etl.steps:logStep` : journalise chaque étape (durée calculée par le flow) dans `dwh.etl_run_log`,
  sur la connexion sans transaction, donc visible immédiatement par l'UI.

### Vues complémentaires

- **http://localhost:5555/StarSchemaETL/flows.html** : arbre des étapes de chaque flow service (généré par `wm/flowdoc.py`),
  pratique pour expliquer la logique sans ouvrir Designer.
- Panneau **Explorer le schéma en étoile** dans l'UI : requêtes par dimension (année, trimestre, mois, jour, segment,
  département, client, région, commercial, catégorie, marque, produit × CA, quantités, lignes, panier moyen) et
  contenu des tables de dimension, rafraîchis pendant le chargement.
- **Parallélisme** : sélecteur 1 / 2 / 4 lots simultanés (orchestrateurs `runPipeline`, `runPipelineX2`,
  `runPipelineX4`, LOOP parallèle native `MAX-THREADS`).

## Lancer la démo

```bash
# 1. base (si le conteneur est arrêté)
docker start stardemo-db
# 2. Integration Server (≈ 40 s)
/home/cpo/wm12/IntegrationServer/instances/default/bin/startup.sh
# 3. UI
xdg-open http://localhost:5555/StarSchemaETL/index.html      # login Administrator / manage
```

Dans l'UI :

- **▶ Lancer la démo** : planifie le pipeline (taille de lot 10 000 / 20 000 / 50 000 lignes, 1 / 2 / 4 lots en
  parallèle) ; refusé si un pipeline tourne déjà.
  Les compteurs, le schéma en étoile, le journal, le débit, les « prochaines lignes source » et les
  « dernières lignes chargées » se rafraîchissent toutes les 1,5 s ; le CA par mois se construit en direct.
- **■ Arrêter** : le pipeline s'arrête proprement (statut STOPPED) : les lots restants sont sautés, les lots en
  cours se terminent et sont commités (fonctionne aussi avec 2 ou 4 lots en parallèle).
- **↺ Réinitialiser** : vide le schéma en étoile et le journal (`dwh.reset_demo()`) pour repartir de zéro ;
  si un pipeline tourne, il est d'abord arrêté.

Contrôles utiles côté base (`docker exec -it stardemo-db psql -U stardemo`) :

```sql
SELECT * FROM dwh.v_etl_last_run;      -- journal de la dernière exécution
SELECT * FROM dwh.v_reconciliation;    -- lignes et montants source vs faits
```

## Redéployer / reconstruire

```bash
./deploy.sh        # tout : conteneur + schéma, données (~10 s), package IS, UI
./deploy.sh data   # régénérer le jeu de données
./deploy.sh is     # package : connexions, services adaptateur, flows, UI
python3 wm/test_steps.py   # tests unitaires des étapes (vide puis charge un lot de 5 000 lignes)
```

Les scripts pilotent l'IS via le serveur MCP `webmethods-is` (wm-mcp-server, binaire indiqué par `WM_MCP_BIN`),
soit par Claude Code (`.mcp.json`, modèle dans `.mcp.json.example`), soit en ligne de commande avec `wm/mcpcli.py`
(JSON-RPC stdio). Prérequis : Docker, Python 3 (Playwright et ffmpeg pour la vidéo), un Integration Server 12.1 avec
l'adaptateur JDBC et le driver PostgreSQL.

## Chiffres de référence (mesurés le 2026-09-08, WSL2, 16 vCPU, IS Xmx 1 Go)

| Étape | Lignes | Durée |
|---|---|---|
| Dimension temporelle (calculée en flow) | 1 096 | 0,4 s |
| Dimensions client / commercial / produit | 5 000 / 143 / 2 000 | 0,4 s / 0,2 s / 0,3 s |
| Table de faits, 50 lots de 20 000 lignes, 1 lot à la fois | 999 343 | 1 min 57 s (≈ 2,3 s par lot, ≈ 8 700 lignes/s) |
| Table de faits, 50 lots de 20 000 lignes, 4 lots en parallèle | 999 343 | 48 s (≈ 3,2 s par lot, ≈ 21 000 lignes/s) |
| Réconciliation `dwh.v_reconciliation` | 999 343 = 999 343 | montant 2 993 009 298,57 € identique |

Chaque lot est un sous-flux indépendant (transaction commitée), très en deçà de l'objectif de 5 minutes par sous-flux.

## Version anglaise (vidéo publique)

- UI : `http://localhost:5555/StarSchemaETL/index.html?lang=en` (textes, formats de nombres, statuts) ; page des flows
  `flows-en.html` (commentaires traduits par `wm/flowdoc.py --lang en`).
- Dimension temporelle : `star.api:start` transmet `lang` ; en anglais le flow `loadDates` utilise la locale `en_GB` (semaines ISO)
  (`Monday`, `September`) et les libellés `2025-Q3` / `2025-W37` (français : `fr_FR`, `2025-T3` / `2025-S37`).
- Jeu de données : `./deploy.sh data-en` (catégories, produits et segments en anglais, mêmes volumes) ;
  `./deploy.sh data` pour revenir au jeu français.
- Vidéo : `python3 video/record_demo.py --lang en` (cadre 1920×1200, page dézoomée à 80 %, cartes `*-en.html`),
  puis `make_video.py`, `chapters.py`, `make_thumbnail.py` (fichiers `ipaas-etl-star-schema-demo-en*.mp4`, `thumbnail-en.png`).

## Neutralité des noms

Le package IS s'appelle `StarSchemaETL` (namespace `star.*`), la base `stardemo` ; écrans, cartes de titre, vignette,
post et ce dépôt ne citent aucun nom d'entreprise (ni client, ni éditeur d'ETL, ni ERP).

## Vidéo et communication

- `video/record_demo.py` enregistre la démo avec Playwright (cartes de titre `video/cards/`, sous-titres, deux
  exécutions : séquentielle puis 4 lots en parallèle) ; `video/make_video.py` produit `video/ipaas-etl-star-schema-demo.mp4` (les vidéos ne sont pas versionnées)
  (temps réel, 5 min 54 s) et `video/ipaas-etl-star-schema-demo-condensee.mp4` (attentes accélérées, 4 min 23 s) ;
  `video/chapters.py`, `video/make_thumbnail.py` et `video/frames.py` produisent chapitres, vignette et images de contrôle.
  Prise du 2026-09-08 : 2 min 33 s (1 lot) et 1 min 10 s (4 lots) — l'encodage vidéo sur la même machine ralentit
  les chargements d'environ 30 % par rapport aux mesures sans capture (1 min 57 s / 49 s). Enregistrer sur une
  machine au repos (aucune compilation ni autre charge en parallèle).
- `docs/linkedin-post.md` : texte du post LinkedIn (EN/FR), fiche YouTube, vignette `video/thumbnail.png`.
- `docs/wm-mcp-server-feedback-poc-etl.md` : retour d'expérience transmis à l'équipe wm-mcp-server.

## Ordre de grandeur

La table source (999 343 lignes, 245 Mo) vaut deux fois une table de staging moyenne d'un ERP de taille
intermédiaire. Avec les débits mesurés sans capture d'écran (8 700 lignes/s ≈ 1,9 Mo/s en séquentiel, 20 000 lignes/s
≈ 4,6 Mo/s à 4 lots), une table de 1 Go se charge en 9 min / 3,7 min, avant tout parallélisme entre tables
(scheduler) et en rechargement complet, alors qu'un ETL de ce type travaille en delta. Pour une démo à cette échelle :
1 000 000 de commandes dans `db/02_generate_data.sql` (≈ 4 M de lignes, ≈ 1 Go).

## Points d'attention

- Montage vidéo : `video/make_video.py` encode segment par segment (pic RAM ≈ 3,7 Go). Ne pas revenir à un
  `filter_complex` multi-`trim` sur la même entrée : il met la vidéo entière en mémoire et a saturé la machine.
- Après un redémarrage de WSL, le conteneur `stardemo-db` repart seul mais l'IS doit être relancé (`startup.sh`).
- Le service `star.api:status` agrège 5 requêtes (dont le CA par mois sur toute la table de faits) : coût
  faible sur 1 M de lignes, à surveiller si le volume est multiplié.
- La taille de lot borne la mémoire de l'IS (20 000 lignes ≈ quelques dizaines de Mo dans le pipeline) ; le
  Xmx de l'instance est de 1 Go (`configuration/custom_wrapper.conf`).
- Les timestamps du journal sont ceux de l'IS (base en Europe/Paris) ; les durées sont mesurées par le flow.
