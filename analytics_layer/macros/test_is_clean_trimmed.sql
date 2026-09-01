{% test is_clean_trimmed(model, column_name) %}

select
    {{ column_name }}
from {{ model }}
-- The test fails if the original column doesn't match its perfectly trimmed version
where {{ column_name }} != trim({{ column_name }})
   or {{ column_name }} like '%  %'  -- Optional: also catches double spaces in the middle

{% endtest %}


