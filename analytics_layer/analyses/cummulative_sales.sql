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

WITH monthly_sales AS (
    SELECT 
        date_trunc(order_date, year) AS order_date,
        CAST(sum(gross_sales_amount) AS int64) AS total_sales,
        CAST(avg(unit_price) AS int64) AS avg_price
    FROM {{ ref('fct_sales') }}
    WHERE order_date >= '2010-01-01'
    GROUP BY 1
),

running_sales AS (
    SELECT 
        order_date,
        total_sales,
        CAST(sum(total_sales) OVER (ORDER BY order_date ASC) AS int64) AS running_total_sales,
        avg_price,
        CAST(avg(avg_price) OVER (ORDER BY order_date ASC) AS int64) AS moving_avg_price
    FROM monthly_sales
)

SELECT * 
FROM running_sales
ORDER BY order_date ASC
