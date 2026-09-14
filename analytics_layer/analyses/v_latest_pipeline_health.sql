CREATE OR REPLACE VIEW `quantum-echo-data-eng-prod.audit_metadata.v_latest_pipeline_health` AS
WITH latest_execution AS (
  -- Grab the most recent single execution run based on timestamp
  SELECT execution_id, MAX(run_timestamp) AS last_run_at
  FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs`
  GROUP BY execution_id
  ORDER BY last_run_at DESC
  LIMIT 1
),
current_run_logs AS (
  -- Filter logs strictly for that latest execution run
  SELECT logs.*
  FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs` logs
  INNER JOIN latest_execution le ON logs.execution_id = le.execution_id
)
SELECT
  le.last_run_at AS last_dbt_run,
  COUNTIF(status IN ('pass', 'success')) AS passed_tests,
  COUNTIF(status IN ('fail', 'error')) AS failed_tests,
  COUNTIF(status = 'warn') AS warning_tests,
  ROUND(AVG(execution_time_seconds), 2) AS avg_model_duration_sec,
  CASE 
    WHEN COUNTIF(status IN ('fail', 'error')) > 0 THEN 'CRITICAL'
    WHEN COUNTIF(status = 'warn') > 0 THEN 'WARNING'
    ELSE 'HEALTHY'
  END AS overall_system_status
FROM current_run_logs, latest_execution le
GROUP BY le.last_run_at;