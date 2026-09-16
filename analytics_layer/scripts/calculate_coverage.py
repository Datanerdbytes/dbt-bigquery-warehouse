#!/usr/bin/env python3
"""
Parse dbt manifest.json to calculate test coverage per model and column.
Outputs coverage data for BigQuery ingestion.
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any


def load_manifest(manifest_path: str) -> Dict[str, Any]:
    """Load and parse dbt manifest.json"""
    with open(manifest_path, 'r') as f:
        return json.load(f)


def calculate_coverage(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Calculate test coverage metrics from manifest.

    Returns list of dicts with coverage data per model.
    """
    nodes = manifest.get('nodes', {})

    # 1. Get all models with their columns
    models = {}
    for node_id, node in nodes.items():
        if node.get('resource_type') == 'model':
            model_name = node.get('name')
            columns = node.get('columns', {})
            models[node_id] = {
                'model_name': model_name,
                'schema': node.get('schema'),
                'database': node.get('database'),
                'columns': {col_name: col_info for col_name, col_info in columns.items()},
                'total_columns': len(columns),
            }

    # 2. Get all tests and map to their attached model/column
    test_by_model_column = defaultdict(lambda: defaultdict(set))

    for node_id, node in nodes.items():
        if node.get('resource_type') == 'test':
            attached_node = node.get('attached_node')
            column_name = node.get('column_name')
            test_name = node.get('name')

            if attached_node and column_name and attached_node in models:
                test_by_model_column[attached_node][column_name].add(test_name)

    # 3. Calculate coverage per model
    coverage_results = []
    run_timestamp = datetime.utcnow().isoformat()

    for model_id, model_info in models.items():
        model_name = model_info['model_name']
        columns = model_info['columns']
        total_columns = model_info['total_columns']

        if total_columns == 0:
            continue

        # Columns with at least one test
        tested_columns = test_by_model_column.get(model_id, {})
        columns_with_tests = len(tested_columns)

        # Total tests across all columns
        total_tests = sum(len(tests) for tests in tested_columns.values())

        # Column-level detail
        column_details = []
        for col_name, col_info in columns.items():
            col_tests = tested_columns.get(col_name, set())
            column_details.append({
                'model_name': model_name,
                'column_name': col_name,
                'column_description': col_info.get('description', ''),
                'data_type': col_info.get('data_type', ''),
                'test_count': len(col_tests),
                'test_names': sorted(list(col_tests)),
                'has_tests': len(col_tests) > 0,
            })

        coverage_results.append({
            'model_name': model_name,
            'schema': model_info['schema'],
            'database': model_info['database'],
            'total_columns': total_columns,
            'columns_with_tests': columns_with_tests,
            'columns_without_tests': total_columns - columns_with_tests,
            'column_coverage_pct': round((columns_with_tests / total_columns) * 100, 2) if total_columns > 0 else 0,
            'total_tests': total_tests,
            'avg_tests_per_column': round(total_tests / total_columns, 2) if total_columns > 0 else 0,
            'column_details': column_details,
            'calculated_at': run_timestamp,
        })

    return coverage_results


def flatten_for_bigquery(coverage_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Flatten coverage results for BigQuery row-per-model-per-column"""
    rows = []
    for model in coverage_results:
        for col in model['column_details']:
            rows.append({
                'model_name': model['model_name'],
                'schema': model['schema'],
                'database': model['database'],
                'column_name': col['column_name'],
                'column_description': col['column_description'],
                'data_type': col['data_type'],
                'test_count': col['test_count'],
                'test_names': ','.join(col['test_names']),
                'has_tests': col['has_tests'],
                'model_total_columns': model['total_columns'],
                'model_columns_with_tests': model['columns_with_tests'],
                'model_column_coverage_pct': model['column_coverage_pct'],
                'model_total_tests': model['total_tests'],
                'calculated_at': model['calculated_at'],
            })
    return rows


def main():
    manifest_path = Path(__file__).parent.parent / 'target' / 'manifest.json'

    if not manifest_path.exists():
        print(f"Manifest not found at {manifest_path}")
        print("Run 'dbt parse' or 'dbt compile' first")
        return 1

    print(f"Loading manifest from {manifest_path}...")
    manifest = load_manifest(str(manifest_path))

    print("Calculating coverage...")
    coverage = calculate_coverage(manifest)

    # Print summary
    print("\n" + "="*80)
    print("TEST COVERAGE SUMMARY")
    print("="*80)

    total_models = len(coverage)
    total_columns = sum(m['total_columns'] for m in coverage)
    total_tested = sum(m['columns_with_tests'] for m in coverage)
    overall_pct = round((total_tested / total_columns) * 100, 2) if total_columns > 0 else 0

    print(f"Models analyzed: {total_models}")
    print(f"Total columns: {total_columns}")
    print(f"Columns with tests: {total_tested}")
    print(f"Overall column coverage: {overall_pct}%")
    print()

    for model in sorted(coverage, key=lambda x: x['model_name']):
        status = "✅" if model['column_coverage_pct'] == 100 else ("⚠️" if model['column_coverage_pct'] >= 50 else "❌")
        print(f"{status} {model['model_name']:30s} | {model['columns_with_tests']:2d}/{model['total_columns']:2d} cols ({model['column_coverage_pct']:5.1f}%) | {model['total_tests']} tests")

    # Output flattened for BigQuery
    flat_rows = flatten_for_bigquery(coverage)

    # Save to JSON for BigQuery load
    output_path = Path(__file__).parent.parent / 'target' / 'test_coverage.json'
    with open(output_path, 'w') as f:
        json.dump(flat_rows, f, indent=2)

    print(f"\nSaved {len(flat_rows)} column-level rows to {output_path}")

    return 0


if __name__ == '__main__':
    exit(main())