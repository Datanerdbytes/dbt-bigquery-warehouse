/*
    Script      : ddl_create_erp_loc_a101.sql
    Purpose     : Create the flat-staging ERP location table that mirrors the
                  Pandas DataFrame produced in Notebooks/load_customer_info.ipynb.
    Target      : Default PostgreSQL schema (Flat Staging)
    Source Data : DataFrame columns + dtypes
                  CID    str  (18484/18484 non-null)
                  CNTRY  str  (18152/18484 non-null)
*/

-- Drop table if it already exists so the script is re-runnable.
DROP TABLE IF EXISTS erp_loc_a101;

CREATE TABLE erp_loc_a101 (
    CID    VARCHAR(50)  NULL,  -- source: str
    CNTRY  VARCHAR(50)  NULL   -- source: str (18152/18484 non-null)
);
