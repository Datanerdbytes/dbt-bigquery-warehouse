{#
    Lint-time expansions for the analytics_layer macros.

    SQLFluff runs the Jinja templater with the BigQuery dialect and never
    connects to a warehouse, so these macros render the BigQuery branch of
    analytics_layer/macros/portable.sql. They exist so the model SQL can be
    parsed and linted offline; dbt uses the real macros at build time.
#}

{% macro qe_safe_cast(expression, type) -%}
    SAFE_CAST({{ expression }} AS {{ type }})
{%- endmacro %}

{% macro qe_string_type() -%}
    string
{%- endmacro %}

{% macro qe_parse_date(format, expression) -%}
    PARSE_DATE('{{ format }}', CAST({{ expression }} AS string))
{%- endmacro %}

{% macro qe_safe_parse_date(format, expression) -%}
    SAFE.PARSE_DATE('{{ format }}', CAST({{ expression }} AS string))
{%- endmacro %}

{% macro qe_current_timestamp() -%}
    CURRENT_TIMESTAMP()
{%- endmacro %}

{% macro qe_current_date() -%}
    CURRENT_DATE()
{%- endmacro %}

{% macro qe_date_diff(end_expression, start_expression, unit) -%}
    DATE_DIFF({{ end_expression }}, {{ start_expression }}, {{ unit }})
{%- endmacro %}

{% macro qe_date_sub_day(expression) -%}
    DATE_SUB({{ expression }}, INTERVAL 1 DAY)
{%- endmacro %}

{% macro qe_safe_divide(numerator, denominator) -%}
    SAFE_DIVIDE({{ numerator }}, {{ denominator }})
{%- endmacro %}
