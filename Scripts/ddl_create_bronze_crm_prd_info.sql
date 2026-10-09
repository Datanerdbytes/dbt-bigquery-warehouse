/*
    Script      : ddl_create_crm_prd_info.sql
    Purpose     : Create the flat-staging CRM product info table that mirrors the
                  Pandas DataFrame produced for product data.
    Target      : Default PostgreSQL schema (Flat Staging)
    Notes       : All string columns (including prd_start_dt / prd_end_dt) are
                  intentionally stored as VARCHAR — downstream types will be
                  cast/handled in dbt, per user direction.
    Source Data : DataFrame columns + dtypes
                  prd_id        int64     (397/397 non-null)
                  prd_key       str       (397/397 non-null)
                  prd_nm        str       (397/397 non-null)
                  prd_cost      float64   (395/397 non-null)
                  prd_line      str       (380/397 non-null)
                  prd_start_dt  str       (397/397 non-null)
                  prd_end_dt    str       (200/397 non-null)
*/

-- Drop table if it already exists so the script is re-runnable.
DROP TABLE IF EXISTS crm_prd_info;

CREATE TABLE crm_prd_info (
    prd_id        BIGINT          NOT NULL,  -- source: int64
    prd_key       VARCHAR(50)     NOT NULL,  -- source: str
    prd_nm        VARCHAR(100)    NOT NULL,  -- source: str
    prd_cost      DECIMAL(18, 4)  NULL,      -- source: float64
    prd_line      VARCHAR(50)     NULL,      -- source: str
    prd_start_dt  VARCHAR(50)     NOT NULL,  -- source: str (cast to date in dbt)
    prd_end_dt    VARCHAR(50)     NULL       -- source: str (cast to date in dbt)
);
