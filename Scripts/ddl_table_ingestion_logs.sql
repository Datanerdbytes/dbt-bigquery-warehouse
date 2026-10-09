/*
    Script      : ddl_create_table_ingestion_logs.sql
    Purpose     : Create the local ingestion audit log table in PostgreSQL.
*/

-- 1. Create schema if it doesn't exist
CREATE SCHEMA IF NOT EXISTS audit_metadata;

-- 2. Drop table if it already exists so the script is re-runnable
DROP TABLE IF EXISTS audit_metadata.table_ingestion_logs;

-- 3. Create the table with PostgreSQL auto-increment (SERIAL) syntax
CREATE TABLE audit_metadata.table_ingestion_logs (
    log_id            SERIAL PRIMARY KEY,
    run_timestamp     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resource_type     VARCHAR(50) NOT NULL,
    table_name        VARCHAR(150) NOT NULL,
    target_table      VARCHAR(150) NOT NULL,
    source_rows       INT NOT NULL DEFAULT 0,
    destination_rows  INT NOT NULL DEFAULT 0,
    duration_seconds  DOUBLE PRECISION,
    status            VARCHAR(20) NOT NULL,
    error_message     TEXT
);
