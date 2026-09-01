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
WITH product_segments AS (
    SELECT 
        product_key,
        product_name,
        cost,
        CASE 
            WHEN cost < 100 THEN 'Below 100'
            WHEN cost >= 100 AND cost < 500 THEN '100 - 500'
            WHEN cost >= 500 AND cost <= 1000 THEN '500 - 1000'
            ELSE 'Above 1000'
        END AS cost_range,
        
        
        CASE 
            WHEN cost < 100 THEN 1
            WHEN cost >= 100 AND cost < 500 THEN 2
            WHEN cost >= 500 AND cost <= 1000 THEN 3
            ELSE 4
        END AS cost_range_order
    FROM {{ ref('dim_products') }}
)

SELECT 
    cost_range,
    count(product_key) AS total_products
FROM product_segments
GROUP BY cost_range, cost_range_order
ORDER BY cost_range_order ASC 



