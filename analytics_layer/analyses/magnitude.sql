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

WITH total_customer_by_country AS (
    SELECT
        country,
        count(customer_key) AS total_customers
    FROM {{ ref('dim_customers') }}
    WHERE country IS NOT null
    GROUP BY country
),

total_customer_by_gender AS (
    SELECT
        gender,
        count(customer_key) AS total_customers
    FROM {{ ref('dim_customers') }}
    WHERE gender IS NOT null
    GROUP BY gender
),

product_metrics_by_category AS (
    SELECT 
        category, 
        count(product_key) AS total_products,
        round(avg(cost), 2) AS avg_cost
    FROM {{ ref('dim_products') }}
    GROUP BY category
),

total_revenue_by_category AS (
    SELECT 
        p.category,
        sum(s.gross_sales_amount) AS total_revenue
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_products') }} p
        ON s.product_key = p.product_key
    GROUP BY p.category
),

-- Renamed duplicate CTE to avoid name collision
top_customers_by_revenue AS (
    SELECT 
        c.customer_id,
        c.first_name,
        c.last_name,
        sum(s.gross_sales_amount) AS total_revenue,
        row_number() OVER(ORDER BY sum(s.gross_sales_amount) DESC) AS rank
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_customers') }} c
        ON s.customer_key = c.customer_key
    GROUP BY 
        c.customer_id,
        c.first_name,
        c.last_name
),

total_sold_items_by_country AS (
    SELECT 
        c.country,
        sum(s.quantity) AS total_sold_items
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_customers') }} c
        ON s.customer_key = c.customer_key
    WHERE c.country IS NOT null
    GROUP BY c.country
)

-- Select from whichever CTE you want to inspect
SELECT * 
FROM product_metrics_by_category