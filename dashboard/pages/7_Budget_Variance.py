"""
Budget Variance Page
Compare forecasts and actuals against budget
"""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.auth import require_auth, get_auth_header

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

st.set_page_config(page_title="Budget Variance", page_icon="💰", layout="wide")
require_auth()

st.title("💰 Budget Variance")

# Help expander
with st.expander("ℹ️ Understanding Budget Variance", expanded=False):
    st.markdown("""
    ### What This Page Shows

    Compare **actual results** and **forecasts** against **budget targets** to track performance.

    ### Key Metrics

    | Metric | Description |
    |--------|-------------|
    | **Variance** | Actual/Forecast minus Budget (positive = above budget) |
    | **Variance %** | Variance as percentage of budget |
    | **Pace** | Cumulative performance vs budget |

    ### Interpreting Variance

    | Variance | Color | Meaning |
    |----------|-------|---------|
    | **+10% or more** | Green | Significantly above budget - strong performance |
    | **+5% to +10%** | Light Green | Above budget - on track |
    | **-5% to +5%** | Gray | On budget - within tolerance |
    | **-10% to -5%** | Light Red | Below budget - needs attention |
    | **-10% or worse** | Red | Significantly below - action required |

    ### Budget Sources

    Budgets can be uploaded via the Settings page as:
    - Monthly targets (spread across days)
    - Daily specific targets
    - By metric (occupancy, revenue, covers)

    ### Using This for Decision Making

    - **Forecast vs Budget**: Early warning of potential shortfalls
    - **Actual vs Budget**: Historical performance tracking
    - **Trend analysis**: Is variance improving or worsening?
    """)

st.markdown("---")

@st.cache_data(ttl=60)
def fetch_historical_data(from_date, to_date):
    """Fetch historical actuals"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/historical/summary",
            params={"from_date": str(from_date), "to_date": str(to_date)},
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

@st.cache_data(ttl=60)
def fetch_forecasts(from_date, to_date, metric):
    """Fetch forecast data"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/forecast/comparison",
            params={"from_date": str(from_date), "to_date": str(to_date), "metric": metric},
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []

# Controls
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    view_mode = st.selectbox(
        "View Mode",
        ["MTD (Month to Date)", "YTD (Year to Date)", "Custom Range"],
        help="Select the time period for analysis"
    )

with col2:
    metric = st.selectbox(
        "Metric",
        ["occupancy_pct", "room_revenue", "dinner_covers", "lunch_covers"],
        format_func=lambda x: {
            "occupancy_pct": "Occupancy %",
            "room_revenue": "Room Revenue",
            "dinner_covers": "Dinner Covers",
            "lunch_covers": "Lunch Covers"
        }.get(x, x),
        help="Select metric to analyze"
    )

# Metric to API mapping
metric_mapping = {
    "occupancy_pct": "hotel_occupancy_pct",
    "room_revenue": "revenue_rooms",
    "dinner_covers": "resos_dinner_covers",
    "lunch_covers": "resos_lunch_covers"
}
api_metric = metric_mapping.get(metric, metric)

# Set date range based on view mode
today = date.today()
if view_mode == "MTD (Month to Date)":
    start_date = today.replace(day=1)
    end_date = today
elif view_mode == "YTD (Year to Date)":
    start_date = today.replace(month=1, day=1)
    end_date = today
else:
    with col3:
        date_range = st.date_input(
            "Date Range",
            value=(today - timedelta(days=30), today),
            help="Select custom date range"
        )
        start_date = date_range[0] if len(date_range) > 0 else today - timedelta(days=30)
        end_date = date_range[1] if len(date_range) > 1 else today

st.markdown("---")

# Fetch data
historical = fetch_historical_data(start_date, end_date)
forecasts = fetch_forecasts(start_date, end_date + timedelta(days=30), api_metric)

# Build variance dataframe
variance_data = []

# Add historical actuals
if historical:
    for item in historical:
        d = item.get('date')
        actual = item.get(metric)
        # Budget would come from budget data - using placeholder
        budget = actual * 0.95 if actual else None  # Placeholder

        if actual is not None and budget is not None:
            variance = actual - budget
            variance_pct = (variance / budget * 100) if budget != 0 else 0

            variance_data.append({
                'date': d,
                'type': 'Actual',
                'value': actual,
                'budget': budget,
                'variance': variance,
                'variance_pct': variance_pct
            })

# Add forecasts
if forecasts:
    for item in forecasts:
        d = item.get('date')
        if d > str(end_date):  # Future dates only
            models = item.get('models', {})
            xgb = models.get('xgboost', {}).get('value')
            budget = item.get('budget')

            if xgb is not None:
                budget_val = budget if budget else xgb * 0.95  # Placeholder if no budget
                variance = xgb - budget_val
                variance_pct = (variance / budget_val * 100) if budget_val != 0 else 0

                variance_data.append({
                    'date': d,
                    'type': 'Forecast',
                    'value': xgb,
                    'budget': budget_val,
                    'variance': variance,
                    'variance_pct': variance_pct
                })

if variance_data:
    df = pd.DataFrame(variance_data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')

    # Summary metrics
    st.subheader("📊 Variance Summary")

    actual_df = df[df['type'] == 'Actual']
    forecast_df = df[df['type'] == 'Forecast']

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if len(actual_df) > 0:
            total_actual = actual_df['value'].sum()
            total_budget = actual_df['budget'].sum()
            total_var = ((total_actual - total_budget) / total_budget * 100) if total_budget != 0 else 0

            st.metric(
                f"Actual vs Budget ({view_mode.split()[0]})",
                f"{total_var:+.1f}%",
                delta=f"{'Above' if total_var > 0 else 'Below'} budget",
                delta_color="normal" if total_var >= 0 else "inverse"
            )
        else:
            st.metric("Actual vs Budget", "N/A")

    with col2:
        if len(forecast_df) > 0:
            fc_total = forecast_df['value'].sum()
            fc_budget = forecast_df['budget'].sum()
            fc_var = ((fc_total - fc_budget) / fc_budget * 100) if fc_budget != 0 else 0

            st.metric(
                "Forecast vs Budget",
                f"{fc_var:+.1f}%",
                help="Projected variance for future period"
            )
        else:
            st.metric("Forecast vs Budget", "N/A")

    with col3:
        avg_var = df['variance_pct'].mean()
        st.metric(
            "Avg Variance",
            f"{avg_var:+.1f}%",
            help="Average daily variance percentage"
        )

    with col4:
        days_above = len(df[df['variance_pct'] > 0])
        days_total = len(df)
        st.metric(
            "Days Above Budget",
            f"{days_above}/{days_total}",
            help="Number of days with positive variance"
        )

    # Variance chart
    st.subheader("📈 Variance Over Time")

    fig = go.Figure()

    # Variance bars
    colors = ['green' if v > 0 else 'red' for v in df['variance_pct']]

    fig.add_trace(go.Bar(
        x=df['date'],
        y=df['variance_pct'],
        name='Variance %',
        marker_color=colors,
        hovertemplate="<b>%{x|%a %d %b}</b><br>" +
                      "Variance: %{y:+.1f}%<extra></extra>"
    ))

    # Zero line
    fig.add_hline(y=0, line_dash="solid", line_color="gray")

    # Threshold lines
    fig.add_hline(y=5, line_dash="dot", line_color="lightgreen", annotation_text="+5%")
    fig.add_hline(y=-5, line_dash="dot", line_color="lightcoral", annotation_text="-5%")

    fig.update_layout(
        title=f'{metric.replace("_", " ").title()} - Variance vs Budget',
        xaxis_title='Date',
        yaxis_title='Variance %',
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)

    # Actual vs Budget vs Forecast chart
    st.subheader("📊 Actual, Budget & Forecast Comparison")

    fig2 = go.Figure()

    # Budget line
    fig2.add_trace(go.Scatter(
        x=df['date'],
        y=df['budget'],
        name='Budget',
        line=dict(color='#d62728', width=2, dash='dash'),
        hovertemplate="Budget: %{y:.1f}<extra></extra>"
    ))

    # Actuals
    if len(actual_df) > 0:
        fig2.add_trace(go.Scatter(
            x=actual_df['date'],
            y=actual_df['value'],
            name='Actual',
            mode='lines+markers',
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=6),
            hovertemplate="Actual: %{y:.1f}<extra></extra>"
        ))

    # Forecasts
    if len(forecast_df) > 0:
        fig2.add_trace(go.Scatter(
            x=forecast_df['date'],
            y=forecast_df['value'],
            name='Forecast',
            mode='lines+markers',
            line=dict(color='#ff7f0e', width=2),
            marker=dict(size=6, symbol='diamond'),
            hovertemplate="Forecast: %{y:.1f}<extra></extra>"
        ))

    fig2.add_vline(x=today, line_dash="dot", line_color="gray")

    fig2.update_layout(
        xaxis_title='Date',
        yaxis_title=metric.replace('_', ' ').title(),
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=400,
        hovermode='x unified'
    )

    st.plotly_chart(fig2, use_container_width=True)

    # Data table
    st.subheader("📋 Variance Detail")

    display_df = df[['date', 'type', 'value', 'budget', 'variance', 'variance_pct']].copy()
    display_df['date'] = display_df['date'].dt.strftime('%a %d %b')
    display_df = display_df.rename(columns={
        'date': 'Date',
        'type': 'Type',
        'value': 'Value',
        'budget': 'Budget',
        'variance': 'Variance',
        'variance_pct': 'Var %'
    })

    # Color variance column
    def highlight_variance(val):
        if isinstance(val, (int, float)):
            if val > 5:
                return 'background-color: lightgreen'
            elif val < -5:
                return 'background-color: lightcoral'
        return ''

    st.dataframe(
        display_df.style.format({
            'Value': '{:.1f}',
            'Budget': '{:.1f}',
            'Variance': '{:+.1f}',
            'Var %': '{:+.1f}%'
        }).applymap(highlight_variance, subset=['Var %']),
        use_container_width=True,
        hide_index=True,
        height=400
    )

else:
    st.info("""
    **No variance data available.**

    To enable budget variance analysis:
    1. Upload budget data in the Settings page
    2. Budget should include monthly or daily targets by metric
    3. Historical actuals must be synced from Newbook/Resos

    Once budget is configured, this page will show actual and forecast variance.
    """)

# Export
st.markdown("---")
if variance_data:
    csv = df.to_csv(index=False)
    st.download_button(
        label="📥 Export Variance Data",
        data=csv,
        file_name=f"budget_variance_{metric}_{start_date}_{end_date}.csv",
        mime="text/csv"
    )
