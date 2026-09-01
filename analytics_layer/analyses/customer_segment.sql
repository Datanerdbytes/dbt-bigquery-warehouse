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

WITH customer_spending AS (
    SELECT 
        customer_key,
        sum(gross_sales_amount) AS total_spending,
        min(order_date) AS first_order,
        max(order_date) AS last_order,
        DATE_DIFF(max(order_date), min(order_date), MONTH) AS lifespan_months
    FROM {{ ref('fct_sales') }}
    GROUP BY customer_key
),

customer_segments AS (
    SELECT
        customer_key,
        CASE 
            WHEN lifespan_months >= 12 AND total_spending > 5000 THEN 'VIP'
            WHEN lifespan_months >= 12 AND total_spending <= 5000 THEN 'Regular'
            ELSE 'New'
        END AS customer_segment
    FROM customer_spending
)

SELECT 
    customer_segment,
    count(customer_key) AS total_customers
FROM customer_segments
GROUP BY customer_segment
ORDER BY total_customers DESC






