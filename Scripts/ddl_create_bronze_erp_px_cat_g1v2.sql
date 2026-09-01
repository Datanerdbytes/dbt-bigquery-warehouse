/*
    Script      : ddl_create_bronze_erp_px_cat_g1v2.sql
    Purpose     : Create the bronze-layer ERP product category table that mirrors the
                  Pandas DataFrame produced in Notebooks/load_customer_info.ipynb.
    Schema      : bronze (matches create_init_database.sql convention)
    Source Data : DataFrame columns + dtypes
                  ID           str  (37/37 non-null)
                  CAT          str  (37/37 non-null)
                  SUBCAT       str  (37/37 non-null)
                  MAINTENANCE  str  (37/37 non-null)
*/

USE Demo_Database;
GO

-- Drop table if it already exists so the script is re-runnable.
IF OBJECT_ID('bronze.erp_px_cat_g1v2', 'U') IS NOT NULL
BEGIN
    DROP TABLE bronze.erp_px_cat_g1v2;
END;
GO

CREATE TABLE bronze.erp_px_cat_g1v2 (
    [ID]           NVARCHAR(50)  NULL,  -- source: str
    [CAT]          NVARCHAR(50)  NULL,  -- source: str
    [SUBCAT]       NVARCHAR(50)  NULL,  -- source: str
    [MAINTENANCE]  NVARCHAR(20)  NULL   -- source: str (likely Y/N flag)
);
GO
