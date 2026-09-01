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

WITH crm_prd AS (
    SELECT * FROM {{ ref('stg_crm_prd_info') }}
),

erp_cat AS (
    SELECT * FROM {{ ref('stg_erp_px_cat_g1v2') }}
),

joined AS (
    SELECT 
        -- Primary Surrogate Key for Dim & Fact joins
        {{ dbt_utils.generate_surrogate_key(['pi.prd_id']) }} AS product_key,
        
        -- Business/Natural Keys
        pi.prd_id AS product_id,
        pi.prd_key AS product_number,
        
        -- Attributes
        pi.prd_nm AS product_name,
        pi.cat_id AS category_id,
        pc.cat AS category,
        pc.subcat AS subcategory,
        pc.maintenance,
        pi.prd_cost AS cost,
        pi.prd_line AS product_line,
        pi.prd_start_dt AS start_date
    FROM crm_prd pi
    LEFT JOIN erp_cat pc   
        ON pi.cat_id = pc.id
    WHERE pi.prd_end_dt IS null -- Filter active products
)

SELECT *    
FROM joined
