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
),
-- Get latest test coverage snapshot
latest_coverage AS (
  SELECT *
  FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
  WHERE DATE(calculated_at) = (
    SELECT MAX(DATE(calculated_at))
    FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
  )
),
-- Aggregate coverage per model
model_coverage AS (
  SELECT
    model_name,
    schema,
    MAX(model_total_columns) AS total_columns,
    MAX(model_columns_with_tests) AS columns_with_tests,
    MAX(model_column_coverage_pct) AS column_coverage_pct,
    MAX(model_total_tests) AS total_tests
  FROM latest_coverage
  GROUP BY model_name, schema
),
-- Overall coverage stats
overall_coverage AS (
  SELECT
    COUNT(*) AS total_models,
    SUM(total_columns) AS total_columns,
    SUM(columns_with_tests) AS total_columns_with_tests,
    ROUND(SAFE_DIVIDE(SUM(columns_with_tests), SUM(total_columns)) * 100, 2) AS overall_column_coverage_pct,
    SUM(total_tests) AS total_tests,
    COUNTIF(column_coverage_pct = 100) AS models_fully_covered,
    COUNTIF(column_coverage_pct >= 80) AS models_well_covered,
    COUNTIF(column_coverage_pct < 50) AS models_poorly_covered
  FROM model_coverage
)
SELECT
  le.last_run_at AS last_dbt_run,
  -- Test execution metrics
  COUNTIF(status IN ('pass', 'success')) AS passed_tests,
  COUNTIF(status IN ('fail', 'error')) AS failed_tests,
  COUNTIF(status = 'warn') AS warning_tests,
  ROUND(AVG(execution_time_seconds), 2) AS avg_model_duration_sec,
  -- Test coverage metrics
  oc.total_models,
  oc.total_columns,
  oc.total_columns_with_tests,
  oc.overall_column_coverage_pct,
  oc.total_tests,
  oc.models_fully_covered,
  oc.models_well_covered,
  oc.models_poorly_covered,
  -- System status
  CASE
    WHEN COUNTIF(status IN ('fail', 'error')) > 0 THEN 'CRITICAL'
    WHEN COUNTIF(status = 'warn') > 0 THEN 'WARNING'
    WHEN oc.overall_column_coverage_pct < 80 THEN 'WARNING'
    ELSE 'HEALTHY'
  END AS overall_system_status
FROM current_run_logs, latest_execution le, overall_coverage oc
GROUP BY le.last_run_at, oc.total_models, oc.total_columns, oc.total_columns_with_tests,
         oc.overall_column_coverage_pct, oc.total_tests, oc.models_fully_covered,
         oc.models_well_covered, oc.models_poorly_covered;