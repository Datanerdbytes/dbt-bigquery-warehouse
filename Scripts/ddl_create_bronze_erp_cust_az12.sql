/*
    Script      : ddl_create_erp_cust_az12.sql
    Purpose     : Create the flat-staging ERP customer info table that mirrors the
                  Pandas DataFrame produced in Notebooks/load_customer_info.ipynb.
    Target      : Default PostgreSQL schema (Flat Staging)
    Source Data : DataFrame columns + dtypes
                  CID    str  (18484/18484 non-null)
                  BDATE  str  (18484/18484 non-null) -> DATE
                  GEN    str  (17012/18484 non-null)
*/

-- Drop table if it already exists so the script is re-runnable.
DROP TABLE IF EXISTS erp_cust_az12;

CREATE TABLE erp_cust_az12 (
    CID    VARCHAR(50)  NULL,  -- source: str
    BDATE  VARCHAR(30)  NULL,  -- source: str (treated as DATE in dbt)
    GEN    VARCHAR(10)  NULL   -- source: str (17012/18484 non-null)
);
