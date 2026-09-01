/*
    Script      : ddl_create_bronze_erp_loc_a101.sql
    Purpose     : Create the bronze-layer ERP location table that mirrors the
                  Pandas DataFrame produced in Notebooks/load_customer_info.ipynb.
    Schema      : bronze (matches create_init_database.sql convention)
    Source Data : DataFrame columns + dtypes
                  CID    str  (18484/18484 non-null)
                  CNTRY  str  (18152/18484 non-null)
*/

USE Demo_Database;
GO

-- Drop table if it already exists so the script is re-runnable.
IF OBJECT_ID('bronze.erp_loc_a101', 'U') IS NOT NULL
BEGIN
    DROP TABLE bronze.erp_loc_a101;
END;
GO

CREATE TABLE bronze.erp_loc_a101 (
    [CID]    NVARCHAR(50)  NULL,  -- source: str
    [CNTRY]  NVARCHAR(50)  NULL   -- source: str (18152/18484 non-null)
);
GO
