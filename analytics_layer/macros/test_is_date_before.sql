{% test is_date_before(model, column_name, end_date_column) %}

select *
from {{ model }}
where {{ column_name }} >= {{ end_date_column }}
  and {{ end_date_column }} is not null

{% endtest %}

