---
name: loading-spinner
description: Standardized dcc.Loading spinner pattern for async data visualization components in Dash apps
---

# Loading Spinner Skill

## Overview
This skill defines the standardized pattern for adding loading spinners to Dash components that fetch or compute data asynchronously. Based on the implementation in `my-dash-app/pages/overview.py`.

## Pattern

### Basic Usage
Wrap any component that may have delayed rendering with `dcc.Loading`:

```python
dcc.Loading(
    id="unique-loading-id",           # Required: unique across the app
    type="circle",                    # Spinner type: "circle" | "default" | "dot" | "cube"
    color="#10b981",                  # Brand green (matches KPI badge color)
    children=<target_component>,      # Component to show while loading
    fullscreen=False,                 # False = inline; True = full-page overlay
    className="mb-3"                  # Optional spacing utility
)
```

### Component-Specific Patterns

#### KPI Cards Bar
```python
dcc.Loading(
    id="kpi-loading",
    type="circle",
    color="#10b981",
    children=create_kpi_bar([
        ("TOTAL SALES", "kpi-sales"),
        ("TOTAL ORDERS", "kpi-orders"),
        ("TOTAL QUANTITY", "kpi-quantity"),
        ("TOTAL CUSTOMERS", "kpi-customers"),
    ]),
    fullscreen=False,
    className="mb-3"
)
```

#### Graph/Chart Components
```python
dcc.Loading(
    id="sales-trend-loading",         # Format: {chart-name}-loading
    type="circle",
    color="#10b981",
    children=dcc.Graph(
        id="sales-trend-graph",
        config={"displayModeBar": False}
    ),
    fullscreen=False
)
```

#### Modal Content (Tables, Detail Views)
```python
dcc.Loading(
    id="modal-table-loading",
    type="circle",
    color="#10b981",
    children=html.Div(id="modal-product-table-container"),
    fullscreen=False
)
```

## Design Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `spinner-color` | `#10b981` | Primary brand green (emerald-500) |
| `spinner-type` | `circle` | Consistent across all dashboards |
| `fullscreen` | `false` | Inline loading, not page-blocking |

## Rules

1. **Unique IDs**: Every `dcc.Loading` must have a unique `id` across the entire app (including all pages)
2. **Consistent Color**: Always use `#10b981` (emerald-500) to match KPI badges and brand
3. **Inline Only**: Use `fullscreen=False` for component-level loading; reserve `fullscreen=True` only for initial page load or major navigation
4. **Wrap the Slowest Child**: Place `dcc.Loading` around the component that triggers the callback (Graph, AgGrid, custom component), not the container
5. **Naming Convention**: `{component-purpose}-loading` (e.g., `kpi-loading`, `sales-trend-loading`, `modal-table-loading`)

## Anti-Patterns to Avoid

| ❌ Don't | ✅ Do |
|----------|-------|
| `type="default"` (browser default) | `type="circle"` (consistent) |
| Random colors per chart | Single brand color `#10b981` |
| `fullscreen=True` on every spinner | `fullscreen=False` for inline |
| Missing `id` prop | Always provide unique `id` |
| Wrapping entire `dbc.Card` | Wrap only the `dcc.Graph`/`AgGrid` inside |

## Applying to Other Pages

When adding spinners to `customer_360.py` or `pipeline_health.py`:

1. Identify all `dcc.Graph`, `dag.AgGrid`, or custom components driven by callbacks
2. Wrap each with `dcc.Loading` using the pattern above
3. Ensure unique IDs (prefix with page name if needed: `customer360-orders-loading`)
4. Keep `fullscreen=False` and `color="#10b981"`

## Example: Adding to a New Chart

```python
# Before
dcc.Graph(id="new-chart-graph", config={"displayModeBar": False})

# After
dcc.Loading(
    id="new-chart-loading",
    type="circle",
    color="#10b981",
    children=dcc.Graph(id="new-chart-graph", config={"displayModeBar": False}),
    fullscreen=False
)
```