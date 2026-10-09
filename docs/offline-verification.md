# Local verification without warehouse access

Run from the repository root after `uv sync --locked` and `npm ci`:

```bash
uv run --locked python Scripts/prepare_dbt_checks.py
uv run --locked python -m pre_commit run --all-files
.venv/bin/python -B -m unittest discover -s tests -v
npm run build:auth
npm run test:auth
```

The preparation hook downloads only the package versions pinned by
`analytics_layer/package-lock.yml` when its cache is missing or outdated, then
runs a fresh `dbt parse` of the actual project. It uses a temporary isolated
profile with a dummy BigQuery project and no usable credentials. Environment
credentials and the normal `~/.dbt` profile are excluded. Parse never executes
warehouse SQL. Failure removes stale manifest output and fails the hook.

`dbt-checkpoint` checks the freshly generated manifest with external usage
telemetry disabled by the tracked `.dbt-checkpoint.yaml` configuration.

SQLFluff uses Jinja's dbt builtins for commit-time linting. The only package
macro currently used by models, `dbt_utils.generate_surrogate_key`, has an
explicit lint-only BigQuery expansion in `sqlfluff_libs/dbt_utils.py`; its
expressions match the existing compiled models. Unknown macros and malformed
SQL remain errors. Tests verify all current models parse without a BigQuery
client. Update the lint library and its tests when adding package macros or
changing surrogate-key options.

This validates model SQL syntax/style, references and manifest quality without
production access. Warehouse-backed compilation and data tests continue in
the existing CI workflow. No dbt run, dbt test, ingestion, or uploads are part
of local commit checks.

Sources: [SQLFluff Jinja library templating](https://docs.sqlfluff.com/en/stable/configuration/templating/jinja.html),
[SQLFluff templater guidance](https://docs.sqlfluff.com/en/stable/configuration/templating/dbt.html),
[dbt parse](https://docs.getdbt.com/reference/commands/parse).
