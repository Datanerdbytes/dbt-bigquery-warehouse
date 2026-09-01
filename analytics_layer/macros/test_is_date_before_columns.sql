{% test is_date_before_columns(model, column_name, compare_columns) %}

select *
from {{ model }}
where 
{% for comp_col in compare_columns %}
  (
    {{ column_name }} >= {{ comp_col }}
    and {{ column_name }} is not null
    and {{ comp_col }} is not null
  )
  {% if not loop.last %} or {% endif %}
{% endfor %}

{% endtest %}

