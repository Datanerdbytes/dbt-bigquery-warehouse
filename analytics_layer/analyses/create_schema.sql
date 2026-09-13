/* @datacloud.settings
{
  "version": 1,
  "service": "BIG_QUERY",
  "connectionInfo": {
    "billingProjectId": "INHERIT",
    "location": "us-central1"
  },
  "dialect": "GOOGLE_SQL"
}
*/

-- CREATE SCHEMA IF NOT EXISTS `quantum-echo-data-eng-prod.audit_metadata`
-- OPTIONS(
--   location="US-CENTRAL1", -- Match the location of your existing BigQuery datasets
--   description="Audit dataset for dbt test runs, model execution logs, and pipeline health metrics."
-- );

-- DROP SCHEMA IF EXISTS `quantum-echo-data-eng-prod.quantum_echo_data_eng_prod` CASCADE;

-- CREATE TABLE IF NOT EXISTS `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs` (
--     execution_id STRING OPTIONS(description="Unique ID for the dbt run batch"),
--     run_timestamp TIMESTAMP OPTIONS(description="Timestamp when dbt run/test started"),
--     resource_type STRING OPTIONS(description="Type of dbt object: 'test' or 'model'"),
--     node_name STRING OPTIONS(description="Name of the dbt model or test (e.g., unique_customers_customer_id)"),
--     target_table STRING OPTIONS(description="Associated model or table being tested/built"),
--     column_name STRING OPTIONS(description="Target column name if applicable"),
--     status STRING OPTIONS(description="Execution status: 'pass', 'fail', 'warn', 'error', 'success'"),
--     execution_time_seconds FLOAT64 OPTIONS(description="Runtime duration in seconds"),
--     rows_affected INT64 OPTIONS(description="Number of failed records or affected rows"),
--     error_message STRING OPTIONS(description="Detailed error or assertion message from dbt log")
-- )
-- PARTITION BY DATE(run_timestamp)
-- CLUSTER BY resource_type, status;

-- CREATE TABLE IF NOT EXISTS `quantum-echo-data-eng-prod.audit_metadata.ingestion_freshness_logs` (
--     check_timestamp TIMESTAMP OPTIONS(description="Timestamp when the freshness check ran"),
--     dataset_name STRING OPTIONS(description="Target dataset (e.g., gold, staging)"),
--     table_name STRING OPTIONS(description="Target table name (e.g., fct_orders, dim_customers)"),
--     last_modified_time TIMESTAMP OPTIONS(description="Last updated timestamp from BigQuery metadata"),
--     row_count INT64 OPTIONS(description="Total row count in table"),
--     size_bytes INT64 OPTIONS(description="Table size in bytes"),
--     freshness_lag_minutes INT64 OPTIONS(description="Lag in minutes between check time and last modified time"),
--     status STRING OPTIONS(description="Freshness status: 'HEALTHY', 'DELAYED', 'STALE'")
-- )
-- PARTITION BY DATE(check_timestamp)
-- CLUSTER BY dataset_name, status;

-- CREATE OR REPLACE VIEW `quantum-echo-data-eng-prod.audit_metadata.v_latest_pipeline_health` AS
-- WITH latest_dbt AS (
--     SELECT 
--         COUNTIF(status = 'pass') AS passed_tests,
--         COUNTIF(status IN ('fail', 'error')) AS failed_tests,
--         COUNTIF(status = 'warn') AS warning_tests,
--         ROUND(AVG(execution_time_seconds), 2) AS avg_model_duration_sec,
--         MAX(run_timestamp) AS last_dbt_run
--     FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs`
--     WHERE run_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
-- ),
-- latest_ingestion AS (
--     SELECT 
--         COUNTIF(status = 'STALE') AS stale_tables_count,
--         MAX(freshness_lag_minutes) AS max_lag_minutes,
--         MAX(check_timestamp) AS last_ingestion_check
--     FROM `quantum-echo-data-eng-prod.audit_metadata.ingestion_freshness_logs`
--     WHERE check_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
-- )
-- SELECT 
--     dbt.last_dbt_run,
--     dbt.passed_tests,
--     dbt.failed_tests,
--     dbt.warning_tests,
--     dbt.avg_model_duration_sec,
--     ing.stale_tables_count,
--     ing.max_lag_minutes,
--     ing.last_ingestion_check,
--     CASE 
--         WHEN dbt.failed_tests > 0 OR ing.stale_tables_count > 0 THEN 'CRITICAL'
--         WHEN dbt.warning_tests > 0 OR ing.max_lag_minutes > 120 THEN 'WARNING'
--         ELSE 'HEALTHY'
--     END AS overall_system_status
-- FROM latest_dbt dbt
-- CROSS JOIN latest_ingestion ing;

-- INSERT INTO `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs` (
--     execution_id, run_timestamp, resource_type, node_name, target_table, column_name, status, execution_time_seconds, rows_affected, error_message
-- ) VALUES (
--     'exec_001', CURRENT_TIMESTAMP(), 'test', 'not_null_dim_customers_customer_id', 'dim_customers', 'customer_id', 'pass', 0.45, 0, NULL
-- );

