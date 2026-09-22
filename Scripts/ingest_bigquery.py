import os
import pandas as pd
import time
import uuid
from urllib.parse import quote_plus
from utils.audit_logger import log_execution_to_bigquery
from dotenv import load_dotenv
from sqlalchemy import create_engine
from google.cloud import bigquery
from google.oauth2 import service_account

# 1. Load environment variables from .env file
load_dotenv()

# 2. Retrieve variables from environment
SERVER = os.getenv('DB_SERVER', '127.0.0.1')
DATABASE = os.getenv('DB_DATABASE', 'Demo_Database')
USERNAME = os.getenv('DB_USERNAME', 'sa')
PASSWORD = os.getenv('DB_PASSWORD')
DRIVER = os.getenv('DB_DRIVER', 'ODBC Driver 18 for SQL Server')

encoded_password = quote_plus(PASSWORD) if PASSWORD else ""

GCP_PROJECT_ID = os.getenv('GCP_PROJECT_ID')
KEY_PATH = os.getenv('GCP_KEY_PATH')
TARGET_DATASET = os.getenv('TARGET_DATASET', 'bronze')

# Safety check to ensure credentials loaded properly
if not USERNAME or not PASSWORD:
    raise ValueError("Missing database credentials in .env file!")

# 3. Authenticate and Initialize Clients
credentials = service_account.Credentials.from_service_account_file(KEY_PATH)

bq_client = bigquery.Client(
    project=GCP_PROJECT_ID, 
    credentials=credentials
)

sql_conn_str = (
    f"mssql+pyodbc://{USERNAME}:{encoded_password}@{SERVER}/{DATABASE}?"
    f"driver={DRIVER}&TrustServerCertificate=yes"
)
db_engine = create_engine(sql_conn_str, pool_pre_ping=True)

# 4. Tables to Ingest
TABLES_TO_INGEST = [
    'crm_cust_info', 
    'crm_prd_info', 
    'crm_sales_details', 
    'erp_cust_az12', 
    'erp_loc_a101', 
    'erp_px_cat_g1v2'
]

def extract_and_load():
    execution_id = str(uuid.uuid4())  # Generate a unique execution ID for this run

    for table_name in TABLES_TO_INGEST:
        print(f"\n--- Processing table: {table_name} ---")
        start_time = time.time()
        destination_table = f"{GCP_PROJECT_ID}.{TARGET_DATASET}.{table_name}"

        try:
            query = f"SELECT * FROM bronze.{table_name}"
            print("Reading data from SQL Server...")
            with db_engine.connect() as conn:
                df = pd.read_sql(query, con=conn)
            print(f"Extracted {len(df)} rows.")

            job_config = bigquery.LoadJobConfig(
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                autodetect=True
            )

            print(f"Loading into BigQuery: '{destination_table}'...")
            load_job = bq_client.load_table_from_dataframe(
                df, destination_table, job_config=job_config
            )
            
            load_job.result()
            duration = time.time() - start_time
            print(f"Successfully loaded {table_name} into BigQuery!")

            # Log success to BigQuery audit
            log_execution_to_bigquery(
                execution_id=execution_id,
                resource_type="sql_to_bigquery",
                node_name=table_name,
                target_table=destination_table,
                status="pass",
                duration_sec=duration,
                rows_affected=len(df)
            )

        except Exception as exc:
            duration = time.time() - start_time
            print(f"❌ Failed to process {table_name}: {exc}")

            # Log failure to BigQuery audit
            log_execution_to_bigquery(
                execution_id=execution_id,
                resource_type="sql_to_bigquery",
                node_name=table_name,
                target_table=destination_table,
                status="fail",
                duration_sec=duration,
                rows_affected=0,
                error_msg=str(exc)
            )

if __name__ == '__main__':
    extract_and_load()