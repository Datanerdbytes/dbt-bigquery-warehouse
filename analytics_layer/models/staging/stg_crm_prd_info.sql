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
    SELECT * FROM {{ source('bronze_source', 'crm_prd_info') }}
),

cleaned_and_renamed AS (
    SELECT
        SAFE_CAST(prd_id AS int64) AS prd_id,
        REPLACE(SUBSTRING(prd_key,1, 5),'-','_') AS cat_id,
        SUBSTRING(prd_key, 7, LENGTH(prd_key)) AS prd_key,

        TRIM(prd_nm) AS prd_nm,
        COALESCE(prd_cost,0) AS prd_cost,
        CASE UPPER(TRIM(prd_line))
            WHEN 'M' THEN 'Mountain'
            WHEN 'R' THEN 'Road'
            WHEN 'S' THEN 'Standard'
            WHEN 'T' THEN 'Touring' 
        END AS prd_line,

        SAFE_CAST(prd_start_dt AS date) AS prd_start_dt,
        
        DATE_SUB(
            SAFE_CAST(LEAD(prd_start_dt) OVER (PARTITION BY prd_key ORDER BY prd_start_dt) AS date), 
            INTERVAL 1 DAY
        ) AS prd_end_dt,
        CURRENT_TIMESTAMP() AS ingested_at
    FROM source
)

SELECT * FROM cleaned_and_renamed
