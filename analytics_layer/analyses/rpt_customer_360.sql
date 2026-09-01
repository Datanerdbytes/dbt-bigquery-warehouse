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

WITH dataset_anchor AS (
    SELECT 
        customer_key,
        order_number,
        product_key,
        gross_sales_amount,
        quantity,
        order_date,
        -- Find the latest transaction date across the entire dataset
        max(order_date) OVER () AS max_dataset_date
    FROM {{ ref('fct_sales') }}
),

customer_sales_aggregated AS (
    SELECT 
        customer_key,
        max(max_dataset_date) AS anchor_date, -- Carry the global max date forward
        count(DISTINCT order_number) AS total_orders,
        CAST(sum(gross_sales_amount) AS int64) AS total_sales,
        sum(quantity) AS total_quantity,
        count(product_key) AS total_products,
        max(order_date) AS last_order_date,
        min(order_date) AS first_order_date,
        DATE_DIFF(max(order_date), min(order_date), MONTH) AS lifespan_months
    FROM dataset_anchor
    GROUP BY customer_key
),

joined AS (
    SELECT 
        c.customer_key,
        c.customer_number,
        concat(c.first_name, ' ', c.last_name) AS customer_name,
        
        -- Age relative to when the dataset ended (Anchor Date)
        DATE_DIFF(s.anchor_date, c.birthdate, YEAR) AS age,
        
        s.anchor_date,
        s.total_orders,
        s.total_sales,
        s.total_quantity,
        s.total_products,
        s.last_order_date,
        s.lifespan_months
    FROM customer_sales_aggregated s
    INNER JOIN {{ ref('dim_customers') }} c
        ON s.customer_key = c.customer_key
)

SELECT 
    customer_key,
    customer_number,
    customer_name,
    age,
    
    CASE 
        WHEN age < 20 THEN 'Under 20'
        WHEN age BETWEEN 20 AND 29 THEN '20-29'
        WHEN age BETWEEN 30 AND 39 THEN '30-39'
        WHEN age BETWEEN 40 AND 49 THEN '40-49'
        ELSE '50 and above'
    END AS age_group,

    CASE 
        WHEN lifespan_months >= 12 AND total_sales > 5000 THEN 'VIP'
        WHEN lifespan_months >= 12 AND total_sales <= 5000 THEN 'Regular'
        ELSE 'New'
    END AS customer_segment,

    last_order_date,
    
    -- Recency relative to the latest dataset activity (Anchor Date)
    DATE_DIFF(anchor_date, last_order_date, DAY) AS recency_days,
    DATE_DIFF(anchor_date, last_order_date, MONTH) AS recency_months,
    
    total_orders,
    total_sales,
    total_quantity,
    total_products,
    lifespan_months,

    round(safe_divide(total_sales, total_orders), 2) AS avg_order_value,
    round(safe_divide(total_sales, COALESCE(nullif(lifespan_months, 0), 1)), 2) AS avg_monthly_spend

FROM joined