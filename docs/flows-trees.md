# Arbres des flow services (générés par wm/flowdoc.py)
Chaque étape telle que déployée sur l'Integration Server (package StarSchemaETL).

## star.etl:runPipeline

ETL orchestrator (1 fact batch(es) in parallel): truncates the star schema, loads the 4 dimensions (including the computed time dimension), then the fact table by logged transactional batches; a stop flag is checked between batches.

*Entrée* : `chunkSize, lang` · *Sortie* : `runId, status, totalRows, durationMs`

- MAP 5 sets — *default values*
- BRANCH sur `/lang` — *time dimension language*
  - SEQUENCE [en]
    - MAP 3 sets
  - SEQUENCE [$default]
    - MAP 3 sets
- INVOKE `pub.date:getCurrentDateString` (entrée : 1 set · sortie : 1 copy, 2 drops)
- INVOKE `star.etl.steps:beginStep` (sortie : 2 copies, 2 drops)
- INVOKE `star.adapters:insertLog` (entrée : 2 copies, 3 sets · sortie : 2 drops) — *PIPELINE row set to RUNNING (visible to the UI)*
- TRY
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:truncateStar` — *truncate the star schema*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadDates` — *time dimension*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadCustomers` — *customer dimension*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadSalesreps` — *sales rep dimension*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadProducts` — *product dimension*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.adapters:selectChunks` (entrée : 2 copies · sortie : 1 copy, 2 drops) — *batch plan (generate_series on order_line_id)*
  - LOOP sur `/chunks` — *one batch per iteration, 1 in parallel (sub-flow < 5 min)*
    - INVOKE `star.adapters:selectStopFlag` (sortie : 1 copy, 1 drop) — *stop flag (dwh.etl_control)*
    - BRANCH sur `/stopFlag` — *stop requested?*
      - SEQUENCE [true]
        - MAP 1 drop — *stop requested: batch skipped (parallel-LOOP safe)*
      - SEQUENCE [$default]
        - MAP 3 copies — *bounds of the current batch*
        - INVOKE `star.etl.steps:beginStep`
        - INVOKE `star.etl.steps:loadFactChunk` — *transactional sub-flow: one batch*
        - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 3 sets · sortie : 10 drops)
        - MAP 4 drops
  - INVOKE `star.adapters:selectCounts` (sortie : 1 copy, 1 drop) — *total rows loaded, re-read from the database (safe with any parallelism)*
  - MAP 1 drop
  - INVOKE `star.adapters:selectStopFlag` (sortie : 1 copy, 1 drop)
  - BRANCH sur `/stopFlag` — *stopped by the user?*
    - SEQUENCE [true]
      - MAP 1 set
  - BRANCH sur `/pipeStatus`
    - SEQUENCE [RUNNING]
      - MAP 1 set
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copy, 3 drops)
  - MAP 1 set
- INVOKE `star.etl.steps:logStep` (entrée : 5 copies, 1 set · sortie : 6 drops) — *total duration (PIPELINE_END row)*
- INVOKE `star.adapters:updatePipelineLog` (entrée : 6 copies · sortie : 2 drops) — *close the PIPELINE row*
- MAP 1 copy, 18 drops

## star.etl.steps:loadFactChunk

Transactional sub-flow: loads the order_line_id rows in ]fromId, toId] into dwh.fact_sales (extraction + SQL lookup, amount computed in the flow, BatchInsert). Rollback on error.

*Entrée* : `fromId, toId` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 set · sortie : 1 copy, 2 drops) — *start local transaction (star.connections:dwh)*
  - INVOKE `star.adapters:selectFactChunk` (entrée : 2 copies · sortie : 1 copy, 2 drops) — *batch extraction + dimension key lookup (SQL join)*
  - LOOP sur `/rows` → `/facts` — *row-by-row transformation*
    - MAP 8 copies — *projection to the fact table*
    - INVOKE `pub.math:multiplyFloats` (entrée : 2 copies, 1 set · sortie : 1 copy, 4 drops) — *amount = quantity x unit price*
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copy · sortie : 1 copy, 2 drops) — *row count*
  - INVOKE `star.adapters:insertFacts` (entrée : 1 copy · sortie : 2 drops) — *JDBC BatchInsert (a single executeBatch)*
  - MAP 2 drops
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copy · sortie : 2 drops) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copy, 3 drops)
  - BRANCH sur `/txName` — *rollback if a transaction is open*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copy · sortie : 2 drops) — *rollback*
  - EXIT $flow / FAILURE « loadFactChunk: %errorMsg% »

## star.etl.steps:loadDates

Time dimension: for each distinct date of staging.orders, the flow computes the calendar attributes, then BatchInsert into dwh.dim_date. One transaction.

*Entrée* : `dimLocale, quarterLetter, weekLetter` · *Sortie* : `rowCount`

- TRY
  - MAP 3 sets — *dimension locale: fr_FR / T / S by default, en_GB / Q / W for an English demo (ISO weeks)*
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 set · sortie : 1 copy, 2 drops) — *start local transaction (star.connections:dwh)*
  - INVOKE `star.adapters:selectDates` (sortie : 1 copy, 1 drop) — *distinct dates of the source*
  - LOOP sur `/rawDates` → `/dates` — *one iteration per date: calendar attributes computed here*
    - MAP 2 copies
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copy, 2 sets · sortie : 1 copy, 4 drops) — *yyyymmdd key*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copy, 2 sets · sortie : 1 copy, 4 drops) — *year*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copy, 2 sets · sortie : 1 copy, 4 drops) — *month*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 2 copies, 2 sets · sortie : 1 copy, 5 drops) — *month name (locale)*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copy, 2 sets · sortie : 1 copy, 4 drops) — *year-month*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 2 copies, 2 sets · sortie : 1 copy, 5 drops) — *ISO week (Monday first, 4-day rule)*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 2 copies, 2 sets · sortie : 1 copy, 5 drops) — *ISO year + week, e.g. 2025-W01 (en) / 2025-S01 (fr)*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copy, 2 sets · sortie : 1 copy, 4 drops) — *day of month*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 1 copy, 2 sets · sortie : 1 copy, 4 drops) — *1 = Monday ... 7 = Sunday*
    - INVOKE `pub.date:dateTimeFormat` (entrée : 2 copies, 2 sets · sortie : 1 copy, 5 drops) — *day name (locale)*
    - INVOKE `pub.math:addInts` (entrée : 1 copy, 1 set · sortie : 1 copy, 3 drops) — *quarter = (month + 2) / 3*
    - INVOKE `pub.math:divideInts` (entrée : 1 copy, 1 set · sortie : 1 copy, 4 drops)
    - MAP 1 set — *label 2024-Q3 (en) / 2024-T3 (fr)*
    - BRANCH sur `/dates/day_of_week` — *weekend if Saturday or Sunday*
      - SEQUENCE [6]
        - MAP 1 set
      - SEQUENCE [7]
        - MAP 1 set
      - SEQUENCE [$default]
        - MAP 1 set
    - MAP 1 drop
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copy · sortie : 1 copy, 2 drops) — *row count*
  - INVOKE `star.adapters:insertDates` (entrée : 1 copy · sortie : 2 drops) — *JDBC BatchInsert (a single executeBatch)*
  - MAP 2 drops
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copy · sortie : 2 drops) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copy, 3 drops)
  - BRANCH sur `/txName` — *rollback if a transaction is open*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copy · sortie : 2 drops) — *rollback*
  - EXIT $flow / FAILURE « loadDates: %errorMsg% »

## star.etl.steps:loadCustomers

Dimension client

*Entrée* : `—` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 set · sortie : 1 copy, 2 drops) — *start local transaction (star.connections:dwh)*
  - INVOKE `star.adapters:selectCustomers` (sortie : 1 copy, 1 drop) — *SELECT DISTINCT extraction from staging.orders*
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copy · sortie : 1 copy, 2 drops) — *row count*
  - INVOKE `star.adapters:insertCustomers` (entrée : 1 copy · sortie : 2 drops) — *JDBC BatchInsert (a single executeBatch)*
  - MAP 1 drop
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copy · sortie : 2 drops) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copy, 3 drops)
  - BRANCH sur `/txName` — *rollback if a transaction is open*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copy · sortie : 2 drops) — *rollback*
  - EXIT $flow / FAILURE « loadCustomers: %errorMsg% »

## star.etl.steps:logStep

Logs a step into dwh.etl_run_log with its duration (ms) computed by the flow.

*Entrée* : `runId, stepName, startedAt, startNano, rowCount, status, message` · *Sortie* : `durationMs, endedAt`

- INVOKE `pub.date:getCurrentDateString` (entrée : 1 set · sortie : 1 copy, 2 drops)
- INVOKE `pub.date:elapsedNanoTime` (entrée : 1 copy · sortie : 1 copy, 3 drops)
- INVOKE `pub.string:objectToString` (entrée : 1 copy · sortie : 1 copy, 3 drops)
- INVOKE `pub.math:divideFloats` (entrée : 1 copy, 2 sets · sortie : 1 copy, 5 drops) — *ns -> ms*
- INVOKE `pub.math:roundNumber` (entrée : 1 copy, 1 set · sortie : 1 copy, 4 drops)
- INVOKE `star.adapters:insertLog` (entrée : 8 copies · sortie : 2 drops) — *dwh.etl_run_log (non-transactional connection: visible immediately)*

## star.etl:startPipeline

Asynchronous start: schedules the orchestrator (1, 2 or 4 parallel batches) in 3 seconds through the IS scheduler.

*Entrée* : `chunkSize, threads, lang` · *Sortie* : `taskID, scheduledAt, service`

- MAP 3 sets
- BRANCH sur `/threads` — *orchestrator for the requested parallelism*
  - SEQUENCE [2]
    - MAP 1 set
  - SEQUENCE [4]
    - MAP 1 set
  - SEQUENCE [$default]
    - MAP 1 set
- INVOKE `pub.date:getCurrentDateString` (entrée : 1 set · sortie : 1 copy, 2 drops)
- INVOKE `pub.date:incrementDate` (entrée : 1 copy, 3 sets · sortie : 1 copy, 6 drops) — *+3 s (the scheduler refuses a past time)*
- INVOKE `pub.string:substring` (entrée : 1 copy, 2 sets · sortie : 1 copy, 4 drops)
- INVOKE `pub.string:substring` (entrée : 1 copy, 2 sets · sortie : 1 copy, 4 drops)
- INVOKE `pub.scheduler:addOneTimeTask` (entrée : 4 copies, 2 sets · sortie : 12 drops) — *one-time IS scheduler task*

## star.etl:runPipelineX4

ETL orchestrator (4 fact batch(es) in parallel): truncates the star schema, loads the 4 dimensions (including the computed time dimension), then the fact table by logged transactional batches; a stop flag is checked between batches.

*Entrée* : `chunkSize, lang` · *Sortie* : `runId, status, totalRows, durationMs`

- MAP 5 sets — *default values*
- BRANCH sur `/lang` — *time dimension language*
  - SEQUENCE [en]
    - MAP 3 sets
  - SEQUENCE [$default]
    - MAP 3 sets
- INVOKE `pub.date:getCurrentDateString` (entrée : 1 set · sortie : 1 copy, 2 drops)
- INVOKE `star.etl.steps:beginStep` (sortie : 2 copies, 2 drops)
- INVOKE `star.adapters:insertLog` (entrée : 2 copies, 3 sets · sortie : 2 drops) — *PIPELINE row set to RUNNING (visible to the UI)*
- TRY
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:truncateStar` — *truncate the star schema*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadDates` — *time dimension*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadCustomers` — *customer dimension*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadSalesreps` — *sales rep dimension*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.etl.steps:beginStep`
  - INVOKE `star.etl.steps:loadProducts` — *product dimension*
  - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 2 sets · sortie : 9 drops)
  - INVOKE `star.adapters:selectChunks` (entrée : 2 copies · sortie : 1 copy, 2 drops) — *batch plan (generate_series on order_line_id)*
  - LOOP sur `/chunks` · 4 itérations en parallèle — *one batch per iteration, 4 in parallel (sub-flow < 5 min)*
    - INVOKE `star.adapters:selectStopFlag` (sortie : 1 copy, 1 drop) — *stop flag (dwh.etl_control)*
    - BRANCH sur `/stopFlag` — *stop requested?*
      - SEQUENCE [true]
        - MAP 1 drop — *stop requested: batch skipped (parallel-LOOP safe)*
      - SEQUENCE [$default]
        - MAP 3 copies — *bounds of the current batch*
        - INVOKE `star.etl.steps:beginStep`
        - INVOKE `star.etl.steps:loadFactChunk` — *transactional sub-flow: one batch*
        - INVOKE `star.etl.steps:logStep` (entrée : 2 copies, 3 sets · sortie : 10 drops)
        - MAP 4 drops
  - INVOKE `star.adapters:selectCounts` (sortie : 1 copy, 1 drop) — *total rows loaded, re-read from the database (safe with any parallelism)*
  - MAP 1 drop
  - INVOKE `star.adapters:selectStopFlag` (sortie : 1 copy, 1 drop)
  - BRANCH sur `/stopFlag` — *stopped by the user?*
    - SEQUENCE [true]
      - MAP 1 set
  - BRANCH sur `/pipeStatus`
    - SEQUENCE [RUNNING]
      - MAP 1 set
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copy, 3 drops)
  - MAP 1 set
- INVOKE `star.etl.steps:logStep` (entrée : 5 copies, 1 set · sortie : 6 drops) — *total duration (PIPELINE_END row)*
- INVOKE `star.adapters:updatePipelineLog` (entrée : 6 copies · sortie : 2 drops) — *close the PIPELINE row*
- MAP 1 copy, 18 drops

## star.api:start

Starts the demo (double-start guard): re-arms the stop flag, then schedules the pipeline.

*Entrée* : `chunkSize, threads, lang` · *Sortie* : `started, message, taskID, scheduledAt, service`

- INVOKE `star.adapters:selectRunLog` (sortie : 1 copy, 1 drop) — *status of the last run*
- BRANCH sur `/lastStatus` — *refused if a pipeline is already running*
  - SEQUENCE [RUNNING]
    - MAP 2 sets
  - SEQUENCE [$default]
    - INVOKE `star.adapters:setStopFlag` (entrée : 1 set · sortie : 2 drops)
    - INVOKE `star.etl:startPipeline` (sortie : 3 drops)
    - MAP 2 sets
- MAP 1 drop

## star.api:analyze

Dimension analysis for the UI: axis (year, quarter, month, week, weekday, segment, department, customer, region, sales rep, category, brand, product) -> revenue, quantities, lines, average line amount.

*Entrée* : `axis` · *Sortie* : `axis, rows[], error`

- BRANCH sur `/axis` — *whitelisted queries on fact_sales ⋈ dimension*
  - SEQUENCE [anYear]
    - INVOKE `star.adapters:anYear` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anQuarter]
    - INVOKE `star.adapters:anQuarter` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anMonth]
    - INVOKE `star.adapters:anMonth` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anWeek]
    - INVOKE `star.adapters:anWeek` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anWeekday]
    - INVOKE `star.adapters:anWeekday` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anSegment]
    - INVOKE `star.adapters:anSegment` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anDept]
    - INVOKE `star.adapters:anDept` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anCustomer]
    - INVOKE `star.adapters:anCustomer` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anRegion]
    - INVOKE `star.adapters:anRegion` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anSalesrep]
    - INVOKE `star.adapters:anSalesrep` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anCategory]
    - INVOKE `star.adapters:anCategory` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anBrand]
    - INVOKE `star.adapters:anBrand` (sortie : 1 copy, 1 drop)
  - SEQUENCE [anProduct]
    - INVOKE `star.adapters:anProduct` (sortie : 1 copy, 1 drop)
  - SEQUENCE [$default]
    - MAP 1 set

## star.etl.steps:beginStep

Step start timestamp (readable date + nanosecond counter).

*Entrée* : `—` · *Sortie* : `stepStart, stepNano`

- INVOKE `pub.date:getCurrentDateString` (entrée : 1 set · sortie : 1 copy, 2 drops)
- INVOKE `pub.date:currentNanoTime` (sortie : 1 copy, 1 drop)

## star.etl.steps:truncateStar

Empties the star schema (facts + dimensions, sequences restarted).

*Entrée* : `—` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 set · sortie : 1 copy, 2 drops) — *start local transaction (star.connections:dwh)*
  - INVOKE `star.adapters:truncateStar` (sortie : 1 drop) — *dwh.truncate_star()*
  - MAP 1 set
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copy · sortie : 2 drops) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copy, 3 drops)
  - BRANCH sur `/txName` — *rollback if a transaction is open*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copy · sortie : 2 drops) — *rollback*
  - EXIT $flow / FAILURE « truncateStar: %errorMsg% »

## star.etl.steps:loadSalesreps

Dimension commercial

*Entrée* : `—` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 set · sortie : 1 copy, 2 drops) — *start local transaction (star.connections:dwh)*
  - INVOKE `star.adapters:selectSalesreps` (sortie : 1 copy, 1 drop) — *SELECT DISTINCT extraction from staging.orders*
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copy · sortie : 1 copy, 2 drops) — *row count*
  - INVOKE `star.adapters:insertSalesreps` (entrée : 1 copy · sortie : 2 drops) — *JDBC BatchInsert (a single executeBatch)*
  - MAP 1 drop
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copy · sortie : 2 drops) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copy, 3 drops)
  - BRANCH sur `/txName` — *rollback if a transaction is open*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copy · sortie : 2 drops) — *rollback*
  - EXIT $flow / FAILURE « loadSalesreps: %errorMsg% »

## star.etl.steps:loadProducts

Dimension produit

*Entrée* : `—` · *Sortie* : `rowCount`

- TRY
  - INVOKE `pub.art.transaction:startTransaction` (entrée : 1 set · sortie : 1 copy, 2 drops) — *start local transaction (star.connections:dwh)*
  - INVOKE `star.adapters:selectProducts` (sortie : 1 copy, 1 drop) — *SELECT DISTINCT extraction from staging.orders*
  - INVOKE `pub.list:sizeOfList` (entrée : 1 copy · sortie : 1 copy, 2 drops) — *row count*
  - INVOKE `star.adapters:insertProducts` (entrée : 1 copy · sortie : 2 drops) — *JDBC BatchInsert (a single executeBatch)*
  - MAP 1 drop
  - INVOKE `pub.art.transaction:commitTransaction` (entrée : 1 copy · sortie : 2 drops) — *commit*
- CATCH
  - INVOKE `pub.flow:getLastFailureCaught` (sortie : 1 copy, 3 drops)
  - BRANCH sur `/txName` — *rollback if a transaction is open*
    - SEQUENCE [$null]
    - SEQUENCE [$default]
      - INVOKE `pub.art.transaction:rollbackTransaction` (entrée : 1 copy · sortie : 2 drops) — *rollback*
  - EXIT $flow / FAILURE « loadProducts: %errorMsg% »

## star.api:status

Demo state for the UI (JSON): volumes, log of the last run, last transformed rows, next source rows.

*Entrée* : `—` · *Sortie* : `serverTime, counts, runLog[], preview[], sourceNext[]`

- INVOKE `pub.date:getCurrentDateString` (entrée : 1 set · sortie : 1 copy, 2 drops)
- INVOKE `star.adapters:selectCounts` (sortie : 1 copy, 1 drop)
- INVOKE `star.adapters:selectRunLog` (sortie : 1 copy, 1 drop)
- INVOKE `star.adapters:selectFactPreview` (sortie : 1 copy, 1 drop)
- INVOKE `star.adapters:selectSourceNext` (sortie : 1 copy, 1 drop)

## star.api:dimension

Preview of the first 12 rows of a dimension table (date, customer, salesrep, product).

*Entrée* : `name` · *Sortie* : `name, rows[], error`

- BRANCH sur `/name` — *preview of a dimension's content*
  - SEQUENCE [date]
    - INVOKE `star.adapters:dimDateRows` (sortie : 1 copy, 1 drop)
  - SEQUENCE [customer]
    - INVOKE `star.adapters:dimCustomerRows` (sortie : 1 copy, 1 drop)
  - SEQUENCE [salesrep]
    - INVOKE `star.adapters:dimSalesrepRows` (sortie : 1 copy, 1 drop)
  - SEQUENCE [product]
    - INVOKE `star.adapters:dimProductRows` (sortie : 1 copy, 1 drop)
  - SEQUENCE [$default]
    - MAP 1 set
