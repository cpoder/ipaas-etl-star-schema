-- =====================================================================
--  webMethods ETL demo (an iPaaS instead of a classic ETL) -- database "stardemo"
--  Source : staging.orders  (flat "classic" order line table,
--           data-lake style replication of an ERP)
--  Target : star schema dwh.* (1 fact table + 4 dimensions,
--           including a time dimension)
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dwh;

-- ---------------------------------------------------------------------
-- 1. Denormalized source table: one row per order line
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS staging.orders CASCADE;
CREATE TABLE staging.orders (
    order_line_id     bigint        PRIMARY KEY,
    order_id          varchar(12)   NOT NULL,
    order_date        date          NOT NULL,
    -- customer
    customer_code     varchar(10)   NOT NULL,
    customer_name     varchar(80)   NOT NULL,
    customer_city     varchar(60),
    customer_dept     varchar(3),
    customer_segment  varchar(30),
    -- sales rep
    salesrep_code     varchar(10)   NOT NULL,
    salesrep_name     varchar(80)   NOT NULL,
    salesrep_region   varchar(40),
    -- product
    product_code      varchar(12)   NOT NULL,
    product_name      varchar(100)  NOT NULL,
    product_category  varchar(40),
    product_brand     varchar(40),
    -- measures
    quantity          integer       NOT NULL,
    unit_price        numeric(12,2) NOT NULL
);

-- ---------------------------------------------------------------------
-- 2. Star schema
-- ---------------------------------------------------------------------
DROP TABLE IF EXISTS dwh.fact_sales   CASCADE;
DROP TABLE IF EXISTS dwh.dim_date     CASCADE;
DROP TABLE IF EXISTS dwh.dim_customer CASCADE;
DROP TABLE IF EXISTS dwh.dim_salesrep CASCADE;
DROP TABLE IF EXISTS dwh.dim_product  CASCADE;
DROP TABLE IF EXISTS dwh.etl_run_log  CASCADE;

-- Time dimension (key = yyyymmdd)
CREATE TABLE dwh.dim_date (
    date_key        integer      PRIMARY KEY,
    full_date       date         NOT NULL UNIQUE,
    year_num        smallint     NOT NULL,
    quarter_num     smallint     NOT NULL,
    quarter_label   varchar(7)   NOT NULL,   -- e.g. 2024-Q3 (2024-T3 with the French locale)
    month_num       smallint     NOT NULL,
    month_name      varchar(12)  NOT NULL,
    year_month      varchar(7)   NOT NULL,   -- e.g. 2024-09
    week_of_year    smallint     NOT NULL,   -- ISO week (Monday first)
    year_week       varchar(8),               -- e.g. 2025-W01 (ISO year + week; 2025-S01 with the French locale)
    day_of_month    smallint     NOT NULL,
    day_of_week     smallint     NOT NULL,   -- 1 = Monday ... 7 = Sunday
    day_name        varchar(10)  NOT NULL,
    is_weekend      boolean      NOT NULL
);

CREATE TABLE dwh.dim_customer (
    customer_key      serial       PRIMARY KEY,
    customer_code     varchar(10)  NOT NULL UNIQUE,
    customer_name     varchar(80)  NOT NULL,
    city              varchar(60),
    dept              varchar(3),
    segment           varchar(30)
);

CREATE TABLE dwh.dim_salesrep (
    salesrep_key      serial       PRIMARY KEY,
    salesrep_code     varchar(10)  NOT NULL UNIQUE,
    salesrep_name     varchar(80)  NOT NULL,
    region            varchar(40)
);

CREATE TABLE dwh.dim_product (
    product_key       serial       PRIMARY KEY,
    product_code      varchar(12)  NOT NULL UNIQUE,
    product_name      varchar(100) NOT NULL,
    category          varchar(40),
    brand             varchar(40)
);

-- Central fact table
CREATE TABLE dwh.fact_sales (
    order_line_id     bigint        PRIMARY KEY,
    order_id          varchar(12)   NOT NULL,
    date_key          integer       NOT NULL REFERENCES dwh.dim_date(date_key),
    customer_key      integer       NOT NULL REFERENCES dwh.dim_customer(customer_key),
    salesrep_key      integer       NOT NULL REFERENCES dwh.dim_salesrep(salesrep_key),
    product_key       integer       NOT NULL REFERENCES dwh.dim_product(product_key),
    quantity          integer       NOT NULL,
    unit_price        numeric(12,2) NOT NULL,
    amount            numeric(14,2) NOT NULL,     -- quantity * unit_price (computed by the flow)
    loaded_at         timestamp     NOT NULL DEFAULT now()
);
CREATE INDEX ix_fact_sales_date     ON dwh.fact_sales(date_key);
CREATE INDEX ix_fact_sales_customer ON dwh.fact_sales(customer_key);
CREATE INDEX ix_fact_sales_product  ON dwh.fact_sales(product_key);
CREATE INDEX ix_fact_sales_salesrep ON dwh.fact_sales(salesrep_key);

-- ETL run log (written by the webMethods flows)
CREATE TABLE dwh.etl_run_log (
    log_id        serial        PRIMARY KEY,
    run_id        varchar(40)   NOT NULL,
    step_name     varchar(60)   NOT NULL,
    started_at    timestamp     NOT NULL,
    ended_at      timestamp,
    row_count     bigint,
    duration_ms   bigint,
    status        varchar(20)   NOT NULL DEFAULT 'RUNNING',
    message       varchar(500)
);
CREATE INDEX ix_etl_run_log_run ON dwh.etl_run_log(run_id);

-- Control view, handy during the demo
CREATE OR REPLACE VIEW dwh.v_etl_last_run AS
SELECT run_id, step_name, started_at, ended_at, row_count, duration_ms, status, message
FROM dwh.etl_run_log
WHERE run_id = (SELECT run_id FROM dwh.etl_run_log ORDER BY log_id DESC LIMIT 1)
ORDER BY log_id;

-- Control view: source / target reconciliation
CREATE OR REPLACE VIEW dwh.v_reconciliation AS
SELECT 'staging.orders'   AS table_name, count(*) AS row_count, sum(quantity*unit_price) AS total_amount FROM staging.orders
UNION ALL
SELECT 'dwh.fact_sales',  count(*), sum(amount) FROM dwh.fact_sales;

-- Empties the target (called by the orchestration flow)
CREATE OR REPLACE FUNCTION dwh.truncate_star() RETURNS integer LANGUAGE plpgsql AS $$
BEGIN
    TRUNCATE dwh.fact_sales, dwh.dim_date, dwh.dim_customer, dwh.dim_salesrep, dwh.dim_product RESTART IDENTITY;
    RETURN 1;
END $$;

-- ---------------------------------------------------------------------
-- 3. Demo control (stop flag + full reset)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dwh.etl_control (
    ctl_key     varchar(40)  PRIMARY KEY,
    ctl_value   varchar(200) NOT NULL
);
INSERT INTO dwh.etl_control VALUES ('stop_requested', 'false') ON CONFLICT (ctl_key) DO NOTHING;

-- Reset: empties the star schema + the log, re-arms the flag
CREATE OR REPLACE FUNCTION dwh.reset_demo() RETURNS integer LANGUAGE plpgsql AS $$
BEGIN
    TRUNCATE dwh.fact_sales, dwh.dim_date, dwh.dim_customer, dwh.dim_salesrep, dwh.dim_product RESTART IDENTITY;
    TRUNCATE dwh.etl_run_log RESTART IDENTITY;
    UPDATE dwh.etl_control SET ctl_value = 'false' WHERE ctl_key = 'stop_requested';
    RETURN 1;
END $$;
