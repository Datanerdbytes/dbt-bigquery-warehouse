/*
    Script      : ddl_create_bronze_crm_cust_info.sql
    Purpose     : Create the bronze-layer CRM customer info table that mirrors the
                  Pandas DataFrame produced in Notebooks/load_customer_info.ipynb.
    Schema      : bronze (matches create_init_database.sql convention)
    Source Data : DataFrame columns + dtypes
                  cst_id              float64  (18490/18494 non-null)
                  cst_key             str      (18494/18494 non-null)
                  cst_firstname       str      (18486/18494 non-null)
                  cst_lastname        str      (18487/18494 non-null)
                  cst_marital_status  str      (18487/18494 non-null)
                  cst_gndr            str      (13916/18494 non-null)
                  cst_create_date     str (date) -> DATE
*/

USE Demo_Database;
GO

-- Drop table if it already exists so the script is re-runnable.
IF OBJECT_ID('bronze.crm_cust_info', 'U') IS NOT NULL
BEGIN
    DROP TABLE bronze.crm_cust_info;
END;
GO

CREATE TABLE bronze.crm_cust_info (
    [cst_id]              BIGINT           NULL,  -- source: float64 -> BIGINT
    [cst_key]             NVARCHAR(50)     NULL,  -- source: str
    [cst_firstname]       NVARCHAR(50)     NULL,  -- source: str
    [cst_lastname]        NVARCHAR(50)     NULL,  -- source: str
    [cst_marital_status]  NVARCHAR(20)     NULL,  -- source: str
    [cst_gndr]            NVARCHAR(10)     NULL,  -- source: str
    [cst_create_date]     NVARCHAR(10)             NULL   -- source: str treated as DATE
);
GO
