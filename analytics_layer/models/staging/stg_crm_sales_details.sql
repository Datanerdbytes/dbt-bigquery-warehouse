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
    SELECT * FROM {{ source('bronze_source', 'crm_sales_details') }}
),

-- Step 1: Standardize Dates and Clean Base Price Values
base_cleaned AS (
    SELECT 
        sls_ord_num,
        sls_prd_key,
        sls_cust_id,

        -- Parse Order Date (Fallback to '1900-01-01')
        COALESCE(
            CASE 
                WHEN sls_order_dt <= 0 OR LENGTH(CAST(sls_order_dt AS STRING)) != 8 THEN NULL
                ELSE PARSE_DATE('%Y%m%d', CAST(sls_order_dt AS STRING))
            END,
            DATE('1900-01-01')
        ) AS sls_order_dt,

        -- Parse Raw Ship Date
        CASE 
            WHEN sls_ship_dt <= 0 OR LENGTH(CAST(sls_ship_dt AS STRING)) != 8 THEN NULL
            ELSE PARSE_DATE('%Y%m%d', CAST(sls_ship_dt AS STRING))
        END AS raw_ship_dt, 

        -- Parse Raw Due Date
        CASE 
            WHEN sls_due_dt <= 0 OR LENGTH(CAST(sls_due_dt AS STRING)) != 8 THEN NULL
            ELSE PARSE_DATE('%Y%m%d', CAST(sls_due_dt AS STRING))
        END AS raw_due_dt,

        sls_quantity,
        sls_sales AS raw_sales,
        
        -- Fix Price (Absolute value for negatives, derive from raw sales if zero/null)
        CASE 
            WHEN sls_price IS NULL OR sls_price = 0 
                THEN sls_sales / NULLIF(sls_quantity, 0)
            ELSE ABS(sls_price)
        END AS sls_price
    FROM source
),

-- Step 2: Enforce Logical Date Sequence & Derive Clean Sales
final_calculations AS (
    SELECT
        sls_ord_num,
        sls_prd_key,
        sls_cust_id,
        
        sls_order_dt,
       
        -- Enforce sls_ship_dt >= sls_order_dt
        GREATEST(
            COALESCE(raw_ship_dt, sls_order_dt),
            sls_order_dt
        ) AS sls_ship_dt,
        
        -- Enforce sls_due_dt >= sls_order_dt
        GREATEST(
            COALESCE(raw_due_dt, sls_order_dt),
            sls_order_dt
        ) AS sls_due_dt,

        sls_quantity,
        sls_price,

        -- Derive sales if negative, zero, or null
        CASE 
            WHEN raw_sales IS NULL OR raw_sales <= 0 
                THEN sls_quantity * sls_price
            ELSE raw_sales
        END AS sls_sales,

        CURRENT_TIMESTAMP() AS ingested_at
    FROM base_cleaned
)

SELECT * FROM final_calculations
