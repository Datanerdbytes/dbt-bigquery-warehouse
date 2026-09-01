/*
    Script      : ddl_create_bronze_crm_sales_details.sql
    Purpose     : Create the bronze-layer CRM sales details table that mirrors the
                  Pandas DataFrame produced for sales data.
    Schema      : bronze (matches create_init_database.sql convention)
    Notes       : Per user direction, dtypes are kept 1:1 with the source
                  dataframe — types will be cast/refined in dbt.
                  The three date-named int64 columns (sls_order_dt,
                  sls_ship_dt, sls_due_dt) are intentionally BIGINT here.
    Source Data : DataFrame columns + dtypes
                  sls_ord_num   str       (60398/60398 non-null)
                  sls_prd_key   str       (60398/60398 non-null)
                  sls_cust_id   int64     (60398/60398 non-null)
                  sls_order_dt  int64     (60398/60398 non-null)  -> BIGINT, cast in dbt
                  sls_ship_dt   int64     (60398/60398 non-null)  -> BIGINT, cast in dbt
                  sls_due_dt    int64     (60398/60398 non-null)  -> BIGINT, cast in dbt
                  sls_sales     float64   (60390/60398 non-null)
                  sls_quantity  int64     (60398/60398 non-null)
                  sls_price     float64   (60391/60398 non-null)
*/

USE Demo_Database;
GO

-- Drop table if it already exists so the script is re-runnable.
IF OBJECT_ID('bronze.crm_sales_details', 'U') IS NOT NULL
BEGIN
    DROP TABLE bronze.crm_sales_details;
END;
GO

CREATE TABLE bronze.crm_sales_details (
    [sls_ord_num]  NVARCHAR(50)    NOT NULL,  -- source: str
    [sls_prd_key]  NVARCHAR(50)    NOT NULL,  -- source: str
    [sls_cust_id]  BIGINT          NOT NULL,  -- source: int64
    [sls_order_dt] BIGINT          NOT NULL,  -- source: int64 (cast to date in dbt)
    [sls_ship_dt]  BIGINT          NOT NULL,  -- source: int64 (cast to date in dbt)
    [sls_due_dt]   BIGINT          NOT NULL,  -- source: int64 (cast to date in dbt)
    [sls_sales]    DECIMAL(18, 4)  NULL,      -- source: float64
    [sls_quantity] BIGINT          NOT NULL,  -- source: int64
    [sls_price]    DECIMAL(18, 4)  NULL       -- source: float64
);
GO
