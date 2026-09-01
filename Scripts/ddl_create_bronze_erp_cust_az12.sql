/*
    Script      : ddl_create_bronze_erp_cust_az12.sql
    Purpose     : Create the bronze-layer ERP customer info table that mirrors the
                  Pandas DataFrame produced in Notebooks/load_customer_info.ipynb.
    Schema      : bronze (matches create_init_database.sql convention)
    Source Data : DataFrame columns + dtypes
                  CID    str  (18484/18484 non-null)
                  BDATE  str  (18484/18484 non-null) -> DATE
                  GEN    str  (17012/18484 non-null)
*/

USE Demo_Database;
GO

-- Drop table if it already exists so the script is re-runnable.
IF OBJECT_ID('bronze.erp_cust_az12', 'U') IS NOT NULL
BEGIN
    DROP TABLE bronze.erp_cust_az12;
END;
GO

CREATE TABLE bronze.erp_cust_az12 (
    [CID]    NVARCHAR(50)  NULL,  -- source: str
    [BDATE]  NVARCHAR(30)  NULL,  -- source: str (treated as DATE in dbt)
    [GEN]    NVARCHAR(10)  NULL   -- source: str (17012/18484 non-null)
);
GO
