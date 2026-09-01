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

WITH sales_metrics AS (
    SELECT
        sum(gross_sales_amount) AS total_sales,
        sum(quantity) AS total_quantity,
        round(avg(unit_price), 2) AS avg_unit_price,
        count(DISTINCT order_number) AS total_distinct_orders,
        count(DISTINCT customer_key) AS active_customers
    FROM {{ ref('fct_sales') }}
),

product_metrics AS (
    SELECT count(*) AS total_products
    FROM {{ ref('dim_products') }}
),

customer_metrics AS (
    SELECT count(*) AS total_customers
    FROM {{ ref('dim_customers') }}
)

SELECT 'Total Sales' AS measure_name, total_sales AS measure_value FROM sales_metrics
UNION ALL
SELECT 'Total Quantity', total_quantity FROM sales_metrics
UNION ALL
SELECT 'Average Unit Price', avg_unit_price FROM sales_metrics
UNION ALL
SELECT 'Distinct Total Orders', total_distinct_orders FROM sales_metrics
UNION ALL
SELECT 'Active Purchasing Customers', active_customers FROM sales_metrics
UNION ALL
SELECT 'Total Products (Catalog)', total_products FROM product_metrics
UNION ALL
SELECT 'Total Customers (Registered)', total_customers FROM customer_metrics







