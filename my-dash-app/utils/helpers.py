import pandas as pd
from dash import html


# KPI Badge Customer 360
def create_trend_badge(current_val, prev_val):
    """Generates a dynamic HTML badge using custom CSS soft badge classes."""
    if prev_val == 0 or pd.isna(prev_val) or pd.isna(current_val):
        return html.Span("N/A", className="badge-soft-secondary")
    
    pct_change = ((current_val - prev_val) / abs(prev_val)) * 100
    
    if pct_change >= 0:
        return html.Span(f"+{pct_change:.1f}% ↑", className="badge-soft-success")
    else:
        return html.Span(f"{pct_change:.1f}% ↓", className="badge-soft-danger")

# KPI Badge Overview
def calculate_pop_badge(full_df, date_col, metric_col, start_date, end_date, agg_type="sum", category=None, country=None):
    if not start_date or not end_date or full_df.empty:
        return html.Span("N/A", className="badge-soft-secondary")

    # 1. Parse current date window
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    
    # Calculate window length in days
    period_days = (end - start).days + 1
    
    # 2. Derive prior period date range
    prior_start = (start - pd.Timedelta(days=period_days)).strftime("%Y-%m-%d")
    prior_end = (start - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

    # 3. Filter current and prior dataframes using your existing filter_dataframe function
    curr_df = filter_dataframe(full_df, start_date, end_date, category, country)
    prior_df = filter_dataframe(full_df, prior_start, prior_end, category, country)

    # 4. Aggregations
    if agg_type == "nunique":
        curr_val = curr_df[metric_col].nunique() if not curr_df.empty else 0
        prior_val = prior_df[metric_col].nunique() if not prior_df.empty else 0
    else:
        curr_val = curr_df[metric_col].sum() if not curr_df.empty else 0
        prior_val = prior_df[metric_col].sum() if not prior_df.empty else 0

    # Prevent division by zero
    if prior_val == 0 or pd.isna(prior_val):
        return html.Span("N/A", className="badge-soft-secondary")

    # 5. Compute percentage change
    pct_change = ((curr_val - prior_val) / prior_val) * 100

    if pct_change >= 0:
        return html.Span(f"+{pct_change:.1f}% ↑", className="badge-soft-success")
    else:
        return html.Span(f"{pct_change:.1f}% ↓", className="badge-soft-danger")
    

def filter_dataframe(df, start_date, end_date, selected_category="ALL", selected_country="ALL"):
    """
    Reusable DataFrame filtering logic for Date Range, Product Category, and Region.
    """
    if df.empty or not start_date or not end_date:
        return df.head(0)

    # Convert date range to datetime
    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)

    filtered_df = df[(df["order_date"] >= start_dt) & (df["order_date"] <= end_dt)]

    if selected_category and selected_category != "ALL":
        filtered_df = filtered_df[filtered_df["category"] == selected_category]

    if selected_country and selected_country != "ALL":
        filtered_df = filtered_df[filtered_df["country"] == selected_country]

    return filtered_df