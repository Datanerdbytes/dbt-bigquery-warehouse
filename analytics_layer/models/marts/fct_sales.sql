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

WITH sales_details AS (
    SELECT * FROM {{ ref('stg_crm_sales_details') }}
),

customers AS (
    SELECT
        customer_key,
        customer_id
    FROM {{ ref('dim_customers') }}
),

products AS (
    SELECT
        product_key,
        product_number
    FROM {{ ref('dim_products') }}
), 

final AS (
    SELECT
        -- Generate Fact Primary Key
        {{ dbt_utils.generate_surrogate_key(['s.sls_ord_num', 's.sls_prd_key']) }} AS sales_item_key,
        
        -- Foreign Keys linking to Dimensions
        c.customer_key,
        p.product_key,
        
        -- Degenerate Dimensions / Business Keys
        s.sls_ord_num AS order_number,
        s.sls_order_dt AS order_date,
        s.sls_ship_dt AS ship_date,
        s.sls_due_dt AS due_date,
        
        -- Measures (Metrics)
        s.sls_quantity AS quantity,
        CAST(s.sls_price AS decimal) AS unit_price,  
        CAST(s.sls_sales AS decimal) AS gross_sales_amount
    FROM sales_details s
    LEFT JOIN customers c 
        ON s.sls_cust_id = c.customer_id
    LEFT JOIN products p 
        ON s.sls_prd_key = p.product_number
)

SELECT * FROM final
