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

SELECT
    row_number() OVER (ORDER BY sum(f.gross_sales_amount) DESC) AS rank,
    c.country,
    p.category,
    sum(f.gross_sales_amount) AS total_revenue
FROM {{ ref('fct_sales') }} f
INNER JOIN {{ ref('dim_customers') }} c
    ON f.customer_key = c.customer_key
INNER JOIN {{ ref('dim_products') }} p
    ON f.product_key = p.product_key
GROUP BY 
    c.country, 
    p.category
ORDER BY total_revenue DESC
LIMIT 10