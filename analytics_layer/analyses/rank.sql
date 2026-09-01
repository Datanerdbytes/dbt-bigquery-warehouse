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

WITH top_performing_products AS (
    SELECT 
        p.product_name,
        sum(gross_sales_amount) AS total_revenue,
        row_number() OVER (ORDER BY sum(gross_sales_amount) DESC ) AS product_rank
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_products') }} p 
    ON s.product_key = p.product_key
    GROUP BY p.product_name

),

worst_performing_products AS (
    SELECT 
        p.product_name,
        sum(gross_sales_amount) AS total_revenue,
        row_number() OVER (ORDER BY sum(gross_sales_amount) ) AS product_rank
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_products') }} p 
    ON s.product_key = p.product_key
    GROUP BY p.product_name

),

top_performing_customers AS (
    SELECT 
        c.customer_key,
        c.first_name, 
        c.last_name,
        sum(gross_sales_amount)  AS total_revenue,
        row_number() OVER ( ORDER BY sum(gross_sales_amount)  DESC) AS customer_rank
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_customers') }} c
    ON s.customer_key = c.customer_key
    GROUP BY  c.customer_key,
              c.first_name, 
              c.last_name
    LIMIT 10
),

lowest_performing_customers AS (
    SELECT 
        c.customer_key,
        c.first_name, 
        c.last_name,
        count(DISTINCT order_number)  AS total_orders,
        row_number() OVER ( ORDER BY count(DISTINCT order_number)) AS customer_rank
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_customers') }} c
    ON s.customer_key = c.customer_key
    GROUP BY  c.customer_key,
              c.first_name, 
              c.last_name
)

SELECT * FROM lowest_performing_customers