/*
    Script      : ddl_create_bronze_crm_prd_info.sql
    Purpose     : Create the bronze-layer CRM product info table that mirrors the
                  Pandas DataFrame produced for product data.
    Schema      : bronze (matches create_init_database.sql convention)
    Notes       : All string columns (including prd_start_dt / prd_end_dt) are
                  intentionally stored as NVARCHAR — downstream types will be
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

USE Demo_Database;
GO

-- Drop table if it already exists so the script is re-runnable.
IF OBJECT_ID('bronze.crm_prd_info', 'U') IS NOT NULL
BEGIN
    DROP TABLE bronze.crm_prd_info;
END;
GO

CREATE TABLE bronze.crm_prd_info (
    [prd_id]        BIGINT          NOT NULL,  -- source: int64
    [prd_key]       NVARCHAR(50)    NOT NULL,  -- source: str
    [prd_nm]        NVARCHAR(100)   NOT NULL,  -- source: str
    [prd_cost]      DECIMAL(18, 4)  NULL,      -- source: float64
    [prd_line]      NVARCHAR(50)    NULL,      -- source: str
    [prd_start_dt]  NVARCHAR(50)    NOT NULL,  -- source: str (cast to date in dbt)
    [prd_end_dt]    NVARCHAR(50)    NULL       -- source: str (cast to date in dbt)
);
GO
