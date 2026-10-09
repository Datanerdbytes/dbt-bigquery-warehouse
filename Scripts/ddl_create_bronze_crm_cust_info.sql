/*
    Script      : ddl_create_crm_cust_info.sql
    Purpose     : Create the flat-staging CRM customer info table that mirrors the
                  Pandas DataFrame produced in Notebooks/load_customer_info.ipynb[cite: 3].
    Target      : Default PostgreSQL schema (Flat Staging)
*/

-- Drop table if it already exists so the script is re-runnable[cite: 3].
DROP TABLE IF EXISTS crm_cust_info;

CREATE TABLE crm_cust_info (
    cst_id              BIGINT,       -- source: float64 -> BIGINT[cite: 3]
    cst_key             VARCHAR(50),  -- source: str[cite: 3]
    cst_firstname       VARCHAR(50),  -- source: str[cite: 3]
    cst_lastname        VARCHAR(50),  -- source: str[cite: 3]
    cst_marital_status  VARCHAR(20),  -- source: str[cite: 3]
    cst_gndr            VARCHAR(10),  -- source: str[cite: 3]
    cst_create_date     VARCHAR(10)   -- source: str treated as DATE[cite: 3]
);
