-- 1. Create schema if it doesn't exist (SQL Server pattern)
IF NOT EXISTS (SELECT * FROM sys.schemas WHERE name = 'audit_metadata')
BEGIN
    EXEC('CREATE SCHEMA audit_metadata')
END
GO

-- 2. Create the table with SQL Server identity syntax
CREATE TABLE audit_metadata.table_ingestion_logs (
    log_id INT IDENTITY(1,1) PRIMARY KEY,
    run_timestamp DATETIME2 NOT NULL DEFAULT GETDATE(),
    resource_type VARCHAR(50) NOT NULL,    
    table_name VARCHAR(150) NOT NULL,      
    target_table VARCHAR(150) NOT NULL,    
    source_rows INT NOT NULL DEFAULT 0,    
    destination_rows INT NOT NULL DEFAULT 0, 
    duration_seconds FLOAT,                
    status VARCHAR(20) NOT NULL,           
    error_message VARCHAR(MAX)             
);