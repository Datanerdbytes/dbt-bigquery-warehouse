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

WITH 

sales_performance AS (
    SELECT 
        EXTRACT(YEAR FROM order_date) AS order_year,
        sum(gross_sales_amount) AS total_sales,
        count(DISTINCT customer_key) AS total_customers,
        sum(quantity) AS total_quantity
    FROM {{ ref('fct_sales') }}
    WHERE EXTRACT(YEAR FROM order_date) >= 2010
    GROUP BY EXTRACT(YEAR FROM order_date)
    ORDER BY EXTRACT(YEAR FROM order_date)
)

SELECT * FROM sales_performance