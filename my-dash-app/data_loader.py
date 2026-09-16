import os
from dotenv import load_dotenv
from google.cloud import bigquery
import pandas as pd
from utils.cache import cache

def get_bigquery_client():
    """Helper function to initialize the BigQuery client from environment variables."""
    load_dotenv()
    key_file_path = os.environ.get("GCP_KEY_PATH")
    project_id = os.environ.get("GCP_PROJECT_ID", "quantum-echo-data-eng-prod")

    if key_file_path and os.path.exists(key_file_path):
        return bigquery.Client.from_service_account_json(key_file_path, project=project_id)
    return bigquery.Client(project=project_id)


@cache.memoize()
def load_and_prep_data():
    client = get_bigquery_client()

    query_sales = """
        SELECT 
            product_key, 
            customer_key,
            order_date, 
            order_number,
            quantity,
            gross_sales_amount, 
            unit_price 
        FROM `quantum-echo-data-eng-prod.gold.fct_sales`
    """

    query_products = """
        SELECT 
            product_key,
            product_name, 
            category 
        FROM `quantum-echo-data-eng-prod.gold.dim_products`
    """

    query_customers = """
        SELECT 
            customer_key,
            first_name, 
            last_name,
            country
        FROM `quantum-echo-data-eng-prod.gold.dim_customers`
    """

    # Query BigQuery
    df_sales = client.query(query_sales).to_dataframe()
    df_products = client.query(query_products).to_dataframe()
    df_customers = client.query(query_customers).to_dataframe()

    # Data transformation and merge
    df_sales['order_date'] = pd.to_datetime(df_sales['order_date'], errors='coerce')

    df_merged = (
        df_sales
        .merge(df_products, on="product_key", how="left")
        .merge(df_customers, on="customer_key", how="left")  
    )

    df_merged['order_date'] = pd.to_datetime(df_merged['order_date'], errors='coerce')
    df_merged = df_merged[df_merged["order_date"].dt.year >= 2010].copy()

    # Compute Datepicker bounds
    min_data_date = df_merged["order_date"].min().strftime("%Y-%m-%d")
    max_data_date = df_merged["order_date"].max().strftime("%Y-%m-%d")

    # Compute Category dropdown options
    unique_categories = sorted(df_merged["category"].dropna().unique())
    category_options = [{"label": "All Categories", "value": "ALL"}] + [
        {"label": str(cat).title(), "value": cat} for cat in unique_categories
    ]

    # Compute Region/Country dropdown options
    unique_countries = sorted(df_merged["country"].dropna().unique())
    country_options = [{"label": "All Countries", "value": "ALL"}] + [
        {"label": str(cntry).title(), "value": cntry} for cntry in unique_countries
    ]

    return df_merged, min_data_date, max_data_date, category_options, country_options


@cache.memoize()
def load_pipeline_health_summary():
    """Fetches high-level pipeline health summary KPIs from audit_metadata."""
    client = get_bigquery_client()
    query = """
        SELECT *
        FROM `quantum-echo-data-eng-prod.audit_metadata.v_latest_pipeline_health`
    """
    df = client.query(query).to_dataframe()
    return df


@cache.memoize()
def load_model_coverage_details():
    """Fetches per-model test coverage details for drill-down."""
    client = get_bigquery_client()
    query = """
        SELECT
            model_name,
            schema,
            model_total_columns as total_columns,
            model_columns_with_tests as columns_with_tests,
            model_column_coverage_pct as column_coverage_pct,
            model_total_tests as total_tests
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
        WHERE DATE(calculated_at) = (
            SELECT MAX(DATE(calculated_at))
            FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
        )
        GROUP BY model_name, schema, model_total_columns, model_columns_with_tests, model_column_coverage_pct, model_total_tests
        ORDER BY model_column_coverage_pct ASC, model_name
    """
    df = client.query(query).to_dataframe()
    return df


@cache.memoize()
def load_column_coverage_details():
    """Fetches column-level test coverage details."""
    client = get_bigquery_client()
    query = """
        SELECT
            model_name,
            schema,
            column_name,
            column_description,
            data_type,
            test_count,
            test_names,
            has_tests
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
        WHERE DATE(calculated_at) = (
            SELECT MAX(DATE(calculated_at))
            FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_test_coverage`
        )
        ORDER BY model_name, has_tests ASC, column_name
    """
    df = client.query(query).to_dataframe()
    return df


@cache.memoize()
def load_source_freshness():
    """Fetches source (bronze) table freshness from ingestion logs."""
    client = get_bigquery_client()
    query = """
        SELECT
            node_name as source_table,
            target_table,
            run_timestamp as last_loaded,
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), run_timestamp, HOUR) as hours_since_load,
            TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), run_timestamp, MINUTE) as minutes_since_load
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs`
        WHERE resource_type = 'sql_to_bigquery'
        ORDER BY run_timestamp DESC
    """
    df = client.query(query).to_dataframe()
    return df


@cache.memoize()
def load_dbt_execution_logs(limit=200):
    """Fetches detailed dbt test and model execution logs."""
    client = get_bigquery_client()
    query = f"""
        SELECT
            execution_id,
            run_timestamp,
            resource_type,
            node_name,
            target_table,
            column_name,
            status,
            execution_time_seconds,
            rows_affected,
            error_message
        FROM `quantum-echo-data-eng-prod.audit_metadata.dbt_execution_logs`
        ORDER BY run_timestamp DESC
        LIMIT {limit}
    """
    df = client.query(query).to_dataframe()
    return df