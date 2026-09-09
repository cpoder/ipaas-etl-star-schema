# LinkedIn post + YouTube sheet (English)

## LinkedIn post

Need to replace your old ETL with a modern iPaaS? Here you go 👇

We took a classic, flat order table: 1,000,000 lines with customer, sales rep, product, quantity and unit price. We turned it into a proper star schema (fact table + 4 dimensions, including a computed time dimension) with webMethods Integration Server alone. No ETL engine.

What the video shows, live:
▸ Flow services doing the transformation row by row (amount = quantity × unit price, calendar attributes computed in the flow)
▸ JDBC adapter services for extraction (with surrogate-key lookups) and batch loading
▸ One transaction per batch (start / commit / rollback), every step logged, stop and restart in one click
▸ The star schema queryable while it loads: revenue by region, category, segment, ISO week, month…
▸ Same flow, 1 batch at a time: 3 min 02 s. With 4 batches in parallel, thanks to the native parallel LOOP: 1 min 14 s. Measured without the screen recorder running on the same laptop, that is 1 min 57 s and 49 s.
▸ Exact reconciliation with the source: same rows, same total, every amount identical

Bonus: the whole package (connections, 40+ adapter services, 15 flows, UI) was generated and deployed through an MCP server driving the Integration Server API. Reproducible in one command.

If your integration platform already runs your APIs and B2B flows, it can run your data pipelines too.

🎥 Video: <YouTube link>

#webMethods #iPaaS #ETL #DataIntegration #StarSchema #DataWarehouse #IBM #PostgreSQL #Integration #DataEngineering

## YouTube sheet

**Title**: webMethods as an ETL: 1,000,000 rows into a star schema, live (replace your ETL with an iPaaS)

**Description**:
webMethods Integration Server replacing an ETL on a real star-schema use case: a 1,000,000-line order table is transformed into a fact table and four dimensions (customer, sales rep, product, computed time dimension) with flow services and the JDBC adapter only.

You will see: the flow services (orchestrator, transactional batch sub-flow, computed time dimension), the live monitoring UI served by the Integration Server, dimension-level queries while the data loads (year, quarter, month, ISO week, region, category…), the exact reconciliation with the source, and the native parallel LOOP bringing the load from 3 min 02 s down to 1 min 14 s (1 min 57 s → 49 s without the screen recorder running).

Stack: IBM webMethods Integration Server 12.1, JDBC Adapter 10.3, PostgreSQL 16 (Docker). The package was built through an MCP server driving the Integration Server API.

Chapters:
00:00 Intro: the use case
00:09 ETL concepts mapped to webMethods
00:22 Starting point: flat source table, empty star schema
00:36 The flow services: orchestrator, transactional batch sub-flow, computed time dimension
01:11 Run 1: sequential load, dimensions then facts
01:48 Querying the star schema while it loads (region, category, segment, ISO week, month)
02:57 Run 1 done: exact reconciliation with the source
03:13 Reset and run 2: 4 parallel batches
04:02 Run 2 done: 2.4x faster, same reconciliation
04:20 Wrap-up

**Tags**: webMethods, iPaaS, ETL, data integration, star schema, data warehouse, IBM, PostgreSQL, JDBC, integration server, flow services, ETL modernization

**Files**: `video/ipaas-etl-star-schema-demo-en-condensee.mp4` (condensed, waits sped up, chapters above) or `video/ipaas-etl-star-schema-demo-en.mp4` (real time, chapters: 00:00, 00:09, 00:22, 00:36, 01:11, 01:48, 04:18, 04:34, 05:57, 06:15); thumbnail `video/thumbnail-en.png` (1280×720).

## Publishing

1. YouTube Studio → Create → Upload the condensed MP4, thumbnail `thumbnail-en.png`, visibility Unlisted or Public, chapters in the description.
2. LinkedIn: paste the post, replace `<YouTube link>`. A natively attached MP4 (under 10 min) usually gets more reach than a link, so consider both: native video in the post, YouTube link in a comment.
