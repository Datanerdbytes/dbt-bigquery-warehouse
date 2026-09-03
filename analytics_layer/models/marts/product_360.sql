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
        max(order_date) OVER () AS max_dataset_date
    FROM {{ ref('fct_sales') }}
),

product_sales_aggregated AS (
    SELECT 
        product_key,
        max(max_dataset_date) AS anchor_date, 
        count(DISTINCT order_number) AS total_orders,
        CAST(sum(gross_sales_amount) AS int64) AS total_sales,
        sum(quantity) AS total_quantity,
        count(DISTINCT customer_key) AS total_unique_customers,
        max(order_date) AS last_order_date,
        min(order_date) AS first_order_date,
        
        -- Exact days active
        DATE_DIFF(max(order_date), min(order_date), DAY) AS lifespan_days,
        
        -- Normalized months (enforces minimum 1.0 to prevent zero-division)
        greatest(round(DATE_DIFF(max(order_date), min(order_date), DAY) / 30.4375, 1), 1.0) AS lifespan_months
    FROM dataset_anchor
    GROUP BY product_key
),

joined AS (
    SELECT 
        p.product_key,
        p.product_name,
        p.category,
        p.subcategory,
        p.cost,
        s.anchor_date,
        s.total_orders,
        s.total_sales,
        s.total_quantity,
        s.total_unique_customers,
        s.last_order_date,
        s.lifespan_days,
        s.lifespan_months
    FROM product_sales_aggregated s
    INNER JOIN {{ ref('dim_products') }} p
        ON s.product_key = p.product_key
)

SELECT 
    product_key,
    product_name,
    category,
    subcategory,
    cost,
    last_order_date AS last_sale_date,
    DATE_DIFF(anchor_date, last_order_date, MONTH) AS recency_months,
    
    -- Performance Tiering
    CASE 
        WHEN total_sales > 50000 THEN 'High-Performer'
        WHEN total_sales >= 10000 THEN 'Mid-Range'
        ELSE 'Low-Performer'
    END AS product_segment,
    
    lifespan_days,
    lifespan_months,
    total_orders,
    total_sales,
    total_quantity,
    total_unique_customers,

    -- Key Financial Ratios
    round(safe_divide(total_sales, total_quantity), 2) AS avg_selling_price,
    round(safe_divide(total_sales, total_orders), 2) AS avg_order_revenue,
    
    -- Consistent Monthly Revenue Divisor
    round(safe_divide(total_sales, COALESCE(nullif(lifespan_months, 0), 1)), 2) AS avg_monthly_revenue

FROM joined