import os
from dotenv import load_dotenv
from google.cloud import bigquery
import pandas as pd
import numpy as np
import plotly.express as px
from  plotly.subplots import make_subplots
import plotly.graph_objects as go
from dash import Dash, html, dcc, callback, Input, Output

load_dotenv()

key_file_path = os.environ.get("GCP_KEY_PATH")

client = bigquery.Client.from_service_account_json(
    key_file_path,
    project="quantum-echo-data-eng-prod"
)

query_sales = """
    SELECT 
        product_key, 
        order_date, 
        gross_sales_amount, 
        unit_price 
    FROM `quantum-echo-data-eng-prod.gold.fct_sales`
"""

df_sales = client.query(query_sales).to_dataframe()

query_products = """
    SELECT 
        product_key,
        product_name, 
        category 
    FROM `quantum-echo-data-eng-prod.gold.dim_products`
"""

df_products = client.query(query_products).to_dataframe()


df_sales["order_date"] = pd.to_datetime(df_sales["order_date"])

df_sales["gross_sales_amount"] = pd.to_numeric(df_sales["gross_sales_amount"], errors='coerce')
df_sales["unit_price"] = pd.to_numeric(df_sales["unit_price"], errors='coerce')

# =====================================================================
# 1. THE JOIN: Combine sales with products
# =====================================================================

df_sales_enriched = pd.merge(
    df_sales,
    df_products,
    on="product_key",
    how="left"

)

sales_by_category = (
    df_sales_enriched
    .assign(order_year=lambda x: pd.to_datetime(x["order_date"]).dt.year.astype(int))
    .query("order_year >= 2010") 
    .groupby(["order_year", "category"], as_index=False)
    .agg(
        category_sales=("gross_sales_amount", lambda s: pd.to_numeric(s).sum()),
        avg_price=("unit_price", lambda s: pd.to_numeric(s).mean())
    )
    .assign(
        category_sales=lambda x: x["category_sales"].round().astype("Int64"),
        avg_price=lambda x: x["avg_price"].round().astype("Int64"),
        order_year=lambda x: x["order_year"].astype(str)
    )
)


# Initialize the app
app = Dash()

#App layout

app.layout = [
    html.Div(children='Sales by Category'),
    html.Hr(),
    dcc.RadioItems(options=['2010', '2011', '2012', '2013', '2014'], value='2014', id='controls-and-radio-item'),
    dcc.Graph(figure={}, id='controls-and-graph')

]

@callback (
    Output(component_id='controls-and-graph', component_property='figure'),
    Input(component_id='controls-and-radio-item', component_property='value')
)

def update_pie_chart(selected_year):
    # 1. Filter your dataset cleanly for the selected snapshot year
    filtered_df = sales_by_category.query("order_year == @selected_year")

    # 🌟 2. CALCULATE THE TOTAL FOR THE SELECTED YEAR RIGHT HERE
    total_sales_selected_year = filtered_df['category_sales'].sum()
    formatted_total = f"${total_sales_selected_year:,.0f}" # Formats to '$29,000,000'

    # 3. Create the standalone pie chart figure
    fig = px.pie(
        filtered_df,
        names='category',
        values='category_sales',
        hole=0.4,
        color_discrete_sequence=px.colors.sequential.Sunset,
        title=f"Category Share Breakdowns ({selected_year})"
    )

     # 4. Apply your professional text orientation cleanups
    fig.update_traces(
        textinfo="percent", 
        textposition="inside", 
        insidetextorientation="radial",
        hovertemplate="<b>Category:</b> %{label}<br><b>Revenue:</b> $%{value:,}<extra></extra>"
    )

     # 🌟 5. INJECT THE DYNAMIC TOTAL TEXT LABEL INSIDE THE HOLE
    fig.add_annotation(
        text=f"<b>Total Revenue</b><br>{formatted_total}",
        x=0.5, y=0.5,        # 👈 Sets it exactly dead-center of a standalone chart canvas
        showarrow=False,
        font=dict(size=12, color="#2c3e50", family="Arial"),
        align="center"
    )

    # 6. Apply clean white template background styles
    fig.update_layout(
        template="plotly_white",
        title_x=0.5,
        showlegend=True,
        # Positions your chart legends nicely below the donut space
        legend=dict(orientation="h", x=0.5, y=-0.1, xanchor="center", yanchor="top")
    )

    return fig

if __name__ == '__main__':
    app.run(debug=True)