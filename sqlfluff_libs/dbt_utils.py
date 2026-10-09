"""Lint-time SQL expansion for the sole dbt-utils macro used by our models.

Matches BigQuery's default dbt_utils.generate_surrogate_key expression. This
module is loaded only by SQLFluff's Jinja library, never by dbt execution.
Unknown dbt-utils macros remain errors rather than being silently ignored.
"""


def generate_surrogate_key(fields):
    """Keep field references, separators, nulls and hashing visible to SQL lint."""
    if not fields:
        raise ValueError("generate_surrogate_key requires at least one field")
    values = [
        f"coalesce(cast({field} as string), '_dbt_utils_surrogate_key_null_')"
        for field in fields
    ]
    expression = " || '-' || ".join(values)
    return f"to_hex(md5(cast({expression} as string)))"
