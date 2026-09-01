WITH source AS (
    SELECT * FROM {{ source('bronze_source', 'erp_px_cat_g1v2') }}
),

transformed_erp AS (
    SELECT 
        CASE 
            WHEN id = 'CO_PD' THEN 'CO_PE'
            ELSE id
        END AS id,
        cat,
        subcat,
        maintenance,
        CURRENT_TIMESTAMP() AS ingested_at
    FROM source
)

SELECT * FROM transformed_erp
