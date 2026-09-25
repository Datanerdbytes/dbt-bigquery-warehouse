/* @datacloud.settings
{
  "version": 1,
  "service": "BIG_QUERY",
  "connectionInfo": {
    "billingProjectId": "INHERIT"
  },
  "dialect": "GOOGLE_SQL"
}
*/

CREATE SCHEMA IF NOT EXISTS audit_metadata;

CREATE TABLE IF NOT EXISTS audit_metadata.table_ingestion_logs (
    log_id STRING,
    run_timestamp TIMESTAMP,
    resource_type STRING,
    table_name STRING,
    target_table STRING,
    source_rows INT64,
    destination_rows INT64,
    duration_seconds FLOAT64,
    status STRING,
    error_message STRING
);