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
    SELECT * FROM {{ source('bronze_source', 'erp_cust_az12') }}
),

parsed_erp AS (
    SELECT 
        CASE 
            WHEN cid LIKE 'NAS%' THEN SUBSTRING(cid, 4)  
            ELSE cid
        END AS cid,

        COALESCE(
            SAFE.PARSE_DATE('%Y-%m-%d', bdate),
            SAFE.PARSE_DATE('%Y%m%d', bdate)
        ) AS bdate,

        CASE
            WHEN UPPER(TRIM(gen)) IN ('F', 'FEMALE') THEN 'Female'
            WHEN UPPER(TRIM(gen)) IN ('M', 'MALE') THEN 'Male'
        END AS gen
    FROM source
)

SELECT 
    cid,
    -- Replaces future birth dates with NULL
    CASE 
        WHEN bdate > CURRENT_DATE() THEN null 
        ELSE bdate 
    END AS bdate,
    gen,
    CURRENT_TIMESTAMP() AS ingested_at
FROM parsed_erp
