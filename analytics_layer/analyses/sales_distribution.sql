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

WITH category_sales AS (
    SELECT
        p.category,
        CAST(sum(s.gross_sales_amount) AS int64) AS total_sales
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_products') }} p
    ON s.product_key = p.product_key
    GROUP BY p.category
)

SELECT 
    category,
    total_sales,
    sum(total_sales) OVER() AS overall_sales,
    concat(round((CAST(total_sales AS decimal) / sum(total_sales) OVER()) * 100, 2), '%') AS percentage_of_total
FROM category_sales
ORDER BY total_sales DESC