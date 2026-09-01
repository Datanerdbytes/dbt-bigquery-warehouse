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

WITH source AS (
    SELECT * FROM {{ source('bronze_source', 'crm_cust_info') }}
),

ranked_records AS (
    SELECT
        *,
        -- drop duplicates
        row_number() OVER (
            PARTITION BY cast(cst_id AS int64) 
            ORDER BY cast(cst_create_date AS timestamp) DESC
        ) AS row_num
    FROM source
    WHERE cst_id IS NOT null
)

SELECT
    safe_cast(cst_id AS int64) AS cst_id,
    trim(cst_key) AS cst_key,
    trim(cst_firstname) AS cst_firstname,
    trim(cst_lastname) AS cst_lastname,
   
    CASE
        WHEN upper(trim(cst_marital_status)) = 'S' THEN 'Single'
        WHEN upper(trim(cst_marital_status)) = 'M' THEN 'Married' 
    END AS cst_marital_status,

    CASE
        WHEN upper(trim(cst_gndr)) = 'F' THEN 'Female'
        WHEN upper(trim(cst_gndr)) = 'M' THEN 'Male' 
    END AS cst_gndr,

    cast(cst_create_date AS date) AS cst_create_date,
    current_timestamp() AS ingested_at
FROM ranked_records
WHERE row_num = 1
