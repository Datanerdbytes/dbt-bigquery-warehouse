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

WITH crm_cust AS (
    SELECT * FROM {{ ref('stg_crm_cust_info') }}
),

erp_cust AS (
    SELECT * FROM {{ ref('stg_erp_cust_az12') }}
),

erp_loc AS (
    SELECT * FROM {{ ref('stg_erp_loc_a101') }}
),

joined AS  (
    SELECT 
        {{ dbt_utils.generate_surrogate_key(['c.cst_id']) }} AS customer_key,
        c.cst_id AS customer_id,
        c.cst_key AS customer_number,
        c.cst_firstname AS first_name,
        c.cst_lastname AS last_name,
        l.cntry AS country,
        c.cst_marital_status AS marital_status,
        COALESCE(c.cst_gndr, e.gen) AS gender,
        e.bdate AS birthdate,
        c.cst_create_date AS create_date
    FROM crm_cust c
    LEFT JOIN erp_cust e
        ON c.cst_key = e.cid
    LEFT JOIN erp_loc l
        ON c.cst_key = l.cid
)

SELECT * FROM joined
