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

WITH yearly_product_sales AS (
    SELECT 
        date_trunc(s.order_date, year) AS order_year,
        p.product_name,
        CAST(sum(s.gross_sales_amount) AS int64) AS current_sales
    FROM {{ ref('fct_sales') }} s
    LEFT JOIN {{ ref('dim_products') }} p
        ON s.product_key = p.product_key
    WHERE s.order_date >= '2010-01-01'
    GROUP BY 1, 2
),

average_product_sales AS (
    SELECT 
        order_year,
        product_name,
        current_sales,
        CAST(avg(current_sales) OVER (PARTITION BY product_name) AS int64) AS avg_sales,
        lag(current_sales) OVER (PARTITION BY product_name ORDER BY order_year) AS py_sales
    FROM yearly_product_sales
),

sales_metrics_calculated AS (
    SELECT
        order_year,
        product_name,
        current_sales,
        avg_sales,
        current_sales - avg_sales AS diff_avg,
        py_sales,
        current_sales - py_sales AS diff_py
    FROM average_product_sales
)

SELECT 
    order_year,
    product_name,
    current_sales,
    avg_sales,
    diff_avg,
    CASE 
        WHEN diff_avg > 0 THEN 'Above Avg'
        WHEN diff_avg < 0 THEN 'Below Avg'
        ELSE 'Avg'
    END AS avg_change,
    py_sales,
    diff_py,
    CASE 
        WHEN diff_py > 0 THEN 'Increase'
        WHEN diff_py < 0 THEN 'Decrease'
        ELSE 'No Change'
    END AS py_change
FROM sales_metrics_calculated
ORDER BY product_name ASC, order_year ASC

