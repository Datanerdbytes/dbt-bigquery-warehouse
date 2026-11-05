{#
    Dialect-portable helpers for the analytics models.

    Each macro dispatches on the dbt adapter, so one set of model SQL renders
    either BigQuery SQL (the original warehouse) or DuckDB SQL (the local and
    Vercel build). The bigquery branch reproduces the original SQL verbatim;
    the duckdb branch is the closest DuckDB equivalent of the same operation.
#}

{% macro qe_unsupported_adapter(macro_name) -%}
    {% do exceptions.raise_compiler_error(
        "analytics_layer: macro '" ~ macro_name ~ "' has no implementation for adapter '"
        ~ target.type ~ "'. Supported adapters: bigquery, duckdb."
    ) %}
{%- endmacro %}


{# Non-throwing cast: NULL on malformed input. #}
{% macro qe_safe_cast(expression, type) -%}
    {{ return(adapter.dispatch('qe_safe_cast')(expression, type)) }}
{%- endmacro %}
{% macro bigquery__qe_safe_cast(expression, type) -%}
    SAFE_CAST({{ expression }} AS {{ type }})
{%- endmacro %}

{% macro duckdb__qe_safe_cast(expression, type) -%}
    TRY_CAST({{ expression }} AS {{ type }})
{%- endmacro %}

{% macro default__qe_safe_cast(expression, type) -%}
    {{ qe_unsupported_adapter('qe_safe_cast') }}
{%- endmacro %}


{# Text type name: BigQuery spells it string, DuckDB spells it VARCHAR. #}
{% macro qe_string_type() -%}
    {{ return(adapter.dispatch('qe_string_type')()) }}
{%- endmacro %}

{% macro bigquery__qe_string_type() -%}
    string
{%- endmacro %}

{% macro duckdb__qe_string_type() -%}
    VARCHAR
{%- endmacro %}

{% macro default__qe_string_type() -%}
    {{ qe_unsupported_adapter('qe_string_type') }}
{%- endmacro %}


{# Strict date parse: raises on malformed input, like BigQuery PARSE_DATE. #}
{% macro qe_parse_date(format, expression) -%}
    {{ return(adapter.dispatch('qe_parse_date')(format, expression)) }}
{%- endmacro %}

{% macro bigquery__qe_parse_date(format, expression) -%}
    PARSE_DATE('{{ format }}', CAST({{ expression }} AS {{ dbt.type_string() }}))
{%- endmacro %}

{% macro duckdb__qe_parse_date(format, expression) -%}
    CAST(strptime(CAST({{ expression }} AS {{ dbt.type_string() }}), '{{ format }}') AS DATE)
{%- endmacro %}

{% macro default__qe_parse_date(format, expression) -%}
    {{ qe_unsupported_adapter('qe_parse_date') }}
{%- endmacro %}


{# Lenient date parse: NULL on malformed input, like BigQuery SAFE.PARSE_DATE. #}
{% macro qe_safe_parse_date(format, expression) -%}
    {{ return(adapter.dispatch('qe_safe_parse_date')(format, expression)) }}
{%- endmacro %}

{% macro bigquery__qe_safe_parse_date(format, expression) -%}
    SAFE.PARSE_DATE('{{ format }}', CAST({{ expression }} AS {{ dbt.type_string() }}))
{%- endmacro %}

{% macro duckdb__qe_safe_parse_date(format, expression) -%}
    CAST(TRY_STRPTIME(CAST({{ expression }} AS {{ dbt.type_string() }}), '{{ format }}') AS DATE)
{%- endmacro %}

{% macro default__qe_safe_parse_date(format, expression) -%}
    {{ qe_unsupported_adapter('qe_safe_parse_date') }}
{%- endmacro %}


{# DuckDB rejects the call form of the current-time functions. #}
{% macro qe_current_timestamp() -%}
    {{ return(adapter.dispatch('qe_current_timestamp')()) }}
{%- endmacro %}

{% macro bigquery__qe_current_timestamp() -%}
    CURRENT_TIMESTAMP()
{%- endmacro %}

{% macro duckdb__qe_current_timestamp() -%}
    current_timestamp
{%- endmacro %}

{% macro default__qe_current_timestamp() -%}
    {{ qe_unsupported_adapter('qe_current_timestamp') }}
{%- endmacro %}


{% macro qe_current_date() -%}
    {{ return(adapter.dispatch('qe_current_date')()) }}
{%- endmacro %}

{% macro bigquery__qe_current_date() -%}
    CURRENT_DATE()
{%- endmacro %}

{% macro duckdb__qe_current_date() -%}
    current_date
{%- endmacro %}

{% macro default__qe_current_date() -%}
    {{ qe_unsupported_adapter('qe_current_date') }}
{%- endmacro %}


{# BigQuery orders DATE_DIFF as (end, start, unit); DuckDB as (unit, start, end).
    Both engines count unit boundaries crossed, so the results agree. #}
{% macro qe_date_diff(end_expression, start_expression, unit) -%}
    {{ return(adapter.dispatch('qe_date_diff')(end_expression, start_expression, unit)) }}
{%- endmacro %}

{% macro bigquery__qe_date_diff(end_expression, start_expression, unit) -%}
    DATE_DIFF({{ end_expression }}, {{ start_expression }}, {{ unit }})
{%- endmacro %}

{% macro duckdb__qe_date_diff(end_expression, start_expression, unit) -%}
    date_diff('{{ unit | lower }}', {{ start_expression }}, {{ end_expression }})
{%- endmacro %}

{% macro default__qe_date_diff(end_expression, start_expression, unit) -%}
    {{ qe_unsupported_adapter('qe_date_diff') }}
{%- endmacro %}


{% macro qe_date_sub_day(expression) -%}
    {{ return(adapter.dispatch('qe_date_sub_day')(expression)) }}
{%- endmacro %}

{% macro bigquery__qe_date_sub_day(expression) -%}
    DATE_SUB({{ expression }}, INTERVAL 1 DAY)
{%- endmacro %}

{% macro duckdb__qe_date_sub_day(expression) -%}
    ({{ expression }} - INTERVAL 1 DAY)
{%- endmacro %}

{% macro default__qe_date_sub_day(expression) -%}
    {{ qe_unsupported_adapter('qe_date_sub_day') }}
{%- endmacro %}


{# BigQuery SAFE_DIVIDE returns NULL for a zero divisor; DuckDB fdiv returns inf. #}
{% macro qe_safe_divide(numerator, denominator) -%}
    {{ return(adapter.dispatch('qe_safe_divide')(numerator, denominator)) }}
{%- endmacro %}

{% macro bigquery__qe_safe_divide(numerator, denominator) -%}
    SAFE_DIVIDE({{ numerator }}, {{ denominator }})
{%- endmacro %}

{% macro duckdb__qe_safe_divide(numerator, denominator) -%}
    CASE
        WHEN {{ denominator }} = 0 THEN NULL
        ELSE {{ numerator }} / {{ denominator }}
    END
{%- endmacro %}

{% macro default__qe_safe_divide(numerator, denominator) -%}
    {{ qe_unsupported_adapter('qe_safe_divide') }}
{%- endmacro %}
