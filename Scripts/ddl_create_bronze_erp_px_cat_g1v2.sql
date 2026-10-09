/*
    Script      : ddl_create_erp_px_cat_g1v2.sql
    Purpose     : Create the flat-staging ERP product category table that mirrors the
                  Pandas DataFrame produced in Notebooks/load_customer_info.ipynb.
    Target      : Default PostgreSQL schema (Flat Staging)
    Source Data : DataFrame columns + dtypes
                  ID           str  (37/37 non-null)
                  CAT          str  (37/37 non-null)
                  SUBCAT       str  (37/37 non-null)
                  MAINTENANCE  str  (37/37 non-null)
*/

-- Drop table if it already exists so the script is re-runnable.
DROP TABLE IF EXISTS erp_px_cat_g1v2;

CREATE TABLE erp_px_cat_g1v2 (
    ID           VARCHAR(50)  NULL,  -- source: str
    CAT          VARCHAR(50)  NULL,  -- source: str
    SUBCAT       VARCHAR(50)  NULL,  -- source: str
    MAINTENANCE  VARCHAR(20)  NULL   -- source: str (likely Y/N flag)
);
