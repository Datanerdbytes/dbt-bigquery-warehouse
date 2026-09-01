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

-- Find the date of the first and last order
-- How many years  of sales are available
SELECT 
  min(order_date) AS first_order_date,
  max(order_date) AS last_order_date,
  DATE_DIFF(max(order_date), min(order_date), YEAR) AS order_range_year
FROM {{ ref('fct_sales') }};

-- Find the youngest and oldest customer

SELECT 
  max(birthdate) AS oldest_birthdate,
  min(birthdate) AS youngest_birthdate,
  DATE_DIFF(current_date(), min(birthdate),  YEAR) AS oldest_age

FROM {{ ref('dim_customers') }}