WITH source AS (
    SELECT * FROM {{ source('bronze_source', 'crm_prd_info') }}
),

cleaned_and_renamed AS (
    SELECT
        {{ qe_safe_cast('prd_id', 'BIGINT') }} AS prd_id,
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

        {{ qe_safe_cast('prd_start_dt', 'DATE') }} AS prd_start_dt,

        {{ qe_date_sub_day(
            qe_safe_cast(
                'LEAD(prd_start_dt) OVER (PARTITION BY prd_key ORDER BY prd_start_dt)',
                'DATE'
            )
        ) }} AS prd_end_dt,
        {{ qe_current_timestamp() }} AS ingested_at
    FROM source
)

SELECT * FROM cleaned_and_renamed
