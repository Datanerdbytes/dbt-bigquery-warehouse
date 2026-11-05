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
            {{ qe_safe_parse_date('%Y-%m-%d', 'bdate') }},
            {{ qe_safe_parse_date('%Y%m%d', 'bdate') }}
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
        WHEN bdate > {{ qe_current_date() }} THEN null
        ELSE bdate
    END AS bdate,
    gen,
    {{ qe_current_timestamp() }} AS ingested_at
FROM parsed_erp
