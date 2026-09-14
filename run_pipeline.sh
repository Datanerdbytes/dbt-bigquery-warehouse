#!/usr/bin/env bash
set -e

# Export project root to Python module path
export PYTHONPATH=.

echo "=================================================="
echo "🚀 STARTING END-TO-END DATA PIPELINE EXECUTION"
echo "=================================================="

# Step 1: Ingest local CSV files into SQL Server (Bronze schema)
echo "📥 Step 1/4: Ingesting CSVs into SQL Server..."
uv run Scripts/ingest_bronze.py /Users/roelsomido/Source

# Step 2: Extract Bronze tables from SQL Server to BigQuery
echo "☁️ Step 2/4: Extracting SQL Server tables to BigQuery..."
uv run Scripts/ingest_bigquery.py

# Step 3: Run dbt transformations and data assertion tests
echo "⚙️ Step 3/4: Executing dbt models and quality checks..."
cd analytics_layer
dbt run
dbt test
cd ..

# Step 4: Stream dbt run artifacts into BigQuery audit logs
echo "📊 Step 4/4: Ingesting dbt run results into BigQuery audit schema..."
uv run Scripts/ingest_dbt_artifacts.py

echo "=================================================="
echo "✅ PIPELINE COMPLETE: All stages executed successfully!"
echo "=================================================="