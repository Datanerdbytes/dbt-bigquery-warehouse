WITH source AS (
    SELECT * FROM {{ source('bronze_source', 'erp_loc_a101') }}
),

transformed AS (
    SELECT
        -- Standardize Customer ID by removing hyphens
        replace(cid, '-', '') AS cid,

        -- Standardize Country Names
        CASE 
            WHEN trim(cntry) = 'DE' THEN 'Germany'
            WHEN trim(cntry) IN ('US', 'USA') THEN 'United States'
            WHEN trim(cntry) = '' THEN null
            ELSE trim(cntry)
        END AS cntry,
        current_timestamp() AS ingested_at
    FROM source
)

SELECT * FROM transformed
