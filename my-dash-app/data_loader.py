import os
from dotenv import load_dotenv
from google.cloud import bigquery
import pandas as pd


def load_and_prep_data():
    load_dotenv()

    key_file_path = os.environ.get("GCP_KEY_PATH")

    client = bigquery.Client.from_service_account_json(
        key_file_path,
        project="quantum-echo-data-eng-prod"
    )

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