"""
Model Comparison Page
Compare Prophet, XGBoost, Pickup, and TFT model performance
"""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.auth import require_auth, get_auth_header
from components.date_picker import get_quick_date_ranges

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

st.set_page_config(page_title="Model Comparison", page_icon="🔄", layout="wide")

# Require authentication
require_auth()

st.title("🔄 Model Comparison")

# Help expander
with st.expander("ℹ️ Understanding Forecasting Models", expanded=False):
    st.markdown("""
    ### The Four Forecasting Models

    This page compares predictions from four different forecasting approaches:

    ---

    **🔵 XGBoost (Gradient Boosting)**
    - **What it does**: Machine learning model that learns patterns from historical data
    - **Strengths**: Excellent at capturing complex patterns, day-of-week effects, seasonal trends
    - **Features used**: Day of week, month, lag values (7/14/21/28 days), rolling averages
    - **Best for**: Medium to long-term forecasts where historical patterns are consistent
    - **Limitations**: Cannot react to real-time booking changes

    ---

    **🟢 Pickup Model**
    - **What it does**: Compares current bookings to historical pace at the same lead time
    - **Strengths**: Uses real-time on-the-books data, compares to prior year
    - **Best for**: Short-term forecasts (0-28 days) where current bookings matter
    - **Key concept**: "Pickup" = how bookings accumulate as date approaches
    - **Limitations**: Requires OTB snapshots; less useful for far-future dates

    ---

    **🟣 TFT (Temporal Fusion Transformer)**
    - **What it does**: State-of-the-art deep learning model for time series forecasting
    - **Strengths**: Handles complex patterns, known future inputs (holidays), provides uncertainty estimates
    - **Features used**: Attention mechanism to identify influential historical patterns and future events
    - **Best for**: Multi-horizon forecasts with strong holiday/event effects
    - **Limitations**: Runs weekly (computationally expensive); requires more training data

    ---

    **🟡 Prophet (Time Series)**
    - **What it does**: Facebook's model designed for business forecasting
    - **Strengths**: Handles seasonality, holidays, missing data; provides confidence intervals
    - **Best for**: Data with strong seasonal patterns and holiday effects
    - **Limitations**: Currently experiencing technical issues (being fixed)

    ---

    ### Accuracy Metrics Explained

    | Metric | Description | Interpretation |
    |--------|-------------|----------------|
    | **MAE** | Mean Absolute Error | Average error in original units (e.g., 5 MAE = off by 5 rooms on average) |
    | **RMSE** | Root Mean Squared Error | Penalizes large errors more heavily than MAE |
    | **MAPE** | Mean Absolute Percentage Error | Error as percentage (e.g., 10% MAPE = 10% off on average) |
    | **Win Count** | Number of times this model was most accurate | Higher = more reliable |

    ### Model Divergence

    When models disagree significantly, it often indicates:
    - **Unusual patterns**: Something different from historical norms
    - **Missing data**: One model may lack information another has
    - **Uncertainty**: Consider using a range rather than single forecast
    """)


@st.cache_data(ttl=60)
def fetch_forecasts(from_date, to_date, metric):
    """Fetch forecast data from API"""
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
    except Exception as e:
        st.error(f"Error fetching forecasts: {e}")
        return []


@st.cache_data(ttl=60)
def fetch_metrics():
    """Fetch available forecast metrics"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/forecast/metrics",
            headers=get_auth_header(),
            timeout=10.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []


@st.cache_data(ttl=60)
def fetch_accuracy(from_date, to_date, model=None):
    """Fetch model accuracy data"""
    try:
        params = {"from_date": str(from_date), "to_date": str(to_date)}
        if model:
            params["model"] = model
        response = httpx.get(
            f"{BACKEND_URL}/accuracy/summary",
            params=params,
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception:
        return {}


# Quick-fill date buttons
quick_ranges = get_quick_date_ranges()
st.markdown("**Quick Select:**")

# Initialize session state
if "mc_start" not in st.session_state:
    st.session_state.mc_start = date.today()
if "mc_end" not in st.session_state:
    st.session_state.mc_end = date.today() + timedelta(days=28)

# Button row
cols_q = st.columns(6)
quick_buttons = ["This Week", "This Month", "Next Month", "Next 3 Months", "Last Month", "Last Week"]
for i, name in enumerate(quick_buttons):
    with cols_q[i]:
        if st.button(name, key=f"mc_quick_{name}", use_container_width=True):
            start, end = quick_ranges[name]
            st.session_state.mc_start = start
            st.session_state.mc_end = end
            st.rerun()

st.markdown("")

# Controls
col1, col2, col3 = st.columns([1, 1, 1])

# Fetch available metrics
metrics = fetch_metrics()
metric_options = {m["metric_code"]: m["metric_name"] for m in metrics} if metrics else {
    "hotel_occupancy_pct": "Occupancy %",
    "hotel_guests": "Total Guests",
    "resos_dinner_covers": "Dinner Covers",
    "resos_lunch_covers": "Lunch Covers",
    "hotel_adr": "Average Daily Rate"
}

with col1:
    selected_metric = st.selectbox(
        "Select Metric",
        options=list(metric_options.keys()),
        format_func=lambda x: metric_options.get(x, x),
        help="Choose which metric to compare across models"
    )

with col2:
    start_date = st.date_input(
        "From",
        value=st.session_state.mc_start,
        help="Start date for forecast comparison"
    )
    st.session_state.mc_start = start_date

with col3:
    end_date = st.date_input(
        "To",
        value=st.session_state.mc_end,
        help="End date for forecast comparison"
    )
    st.session_state.mc_end = end_date

st.markdown("---")

# Fetch forecast data
forecast_data = fetch_forecasts(start_date, end_date, selected_metric)

if not forecast_data:
    st.warning("""
    **No forecast data available for this metric and date range.**

    To generate forecasts:
    1. Ensure you have sufficient historical data (90+ days)
    2. Go to Settings and trigger a manual forecast run, or wait for the scheduled run
    3. Forecasts are generated daily at 6:00 AM by default
    """)

    # Show button to trigger forecast generation
    if st.button("Generate Forecasts Now"):
        try:
            response = httpx.post(
                f"{BACKEND_URL}/forecast/regenerate",
                params={
                    "from_date": str(start_date),
                    "to_date": str(end_date),
                    "models": ["prophet", "xgboost", "pickup"]
                },
                headers=get_auth_header(),
                timeout=10.0
            )
            if response.status_code == 200:
                st.success("Forecast generation started in background. Refresh in a few minutes.")
            else:
                st.error(f"Failed to trigger forecast: {response.status_code}")
        except Exception as e:
            st.error(f"Error triggering forecast: {e}")

    st.stop()

# Convert to DataFrame
df = pd.DataFrame(forecast_data)
df['date'] = pd.to_datetime([item['date'] for item in forecast_data])

# Extract model values
df['Prophet'] = df.apply(lambda row: row.get('models', {}).get('prophet', {}).get('value'), axis=1)
df['XGBoost'] = df.apply(lambda row: row.get('models', {}).get('xgboost', {}).get('value'), axis=1)
df['Pickup'] = df.apply(lambda row: row.get('models', {}).get('pickup', {}).get('value'), axis=1)
df['TFT'] = df.apply(lambda row: row.get('models', {}).get('tft', {}).get('value'), axis=1)
df['TFT_Lower'] = df.apply(lambda row: row.get('models', {}).get('tft', {}).get('lower'), axis=1)
df['TFT_Upper'] = df.apply(lambda row: row.get('models', {}).get('tft', {}).get('upper'), axis=1)
df['Actual'] = df.apply(lambda row: row.get('actual'), axis=1)
df['Current_OTB'] = df.apply(lambda row: row.get('current_otb'), axis=1)
df['Budget'] = df.apply(lambda row: row.get('budget'), axis=1)
df['Prior_Year'] = df.apply(lambda row: row.get('prior_year_actual'), axis=1)

# Sort by date
df = df.sort_values('date')

# Model comparison chart
st.subheader("📈 Model Predictions Over Time")
st.caption("_Compare how each model forecasts the selected metric_")

fig = go.Figure()

colors = {
    'Prophet': '#1f77b4',
    'XGBoost': '#ff7f0e',
    'Pickup': '#2ca02c',
    'TFT': '#9467bd',       # Purple for TFT
    'Actual': '#d62728',
    'Current_OTB': '#17becf',  # Cyan for OTB
    'Budget': '#8c564b',
    'Prior_Year': '#7f7f7f'  # Gray for reference
}

# Add model traces
for model in ['XGBoost', 'Pickup', 'TFT', 'Prophet']:
    model_data = df[df[model].notna()]
    if len(model_data) > 0:
        fig.add_trace(go.Scatter(
            x=model_data['date'],
            y=model_data[model],
            name=model,
            line=dict(color=colors[model], width=2 if model not in ['Prophet'] else 1),
            hovertemplate=f"<b>{model}</b><br>Date: %{{x|%a %d %b}}<br>Value: %{{y:.1f}}<extra></extra>"
        ))

# Add TFT confidence band if available
tft_data = df[df['TFT'].notna() & df['TFT_Lower'].notna() & df['TFT_Upper'].notna()]
if len(tft_data) > 0:
    fig.add_trace(go.Scatter(
        x=pd.concat([tft_data['date'], tft_data['date'][::-1]]),
        y=pd.concat([tft_data['TFT_Upper'], tft_data['TFT_Lower'][::-1]]),
        fill='toself',
        fillcolor='rgba(148, 103, 189, 0.2)',
        line=dict(color='rgba(255,255,255,0)'),
        name='TFT 80% CI',
        showlegend=True,
        hoverinfo='skip'
    ))

# Add actuals as scatter
actual_df = df[df['Actual'].notna()]
if len(actual_df) > 0:
    fig.add_trace(go.Scatter(
        x=actual_df['date'],
        y=actual_df['Actual'],
        name='Actual',
        mode='markers',
        marker=dict(color=colors['Actual'], size=10, symbol='star'),
        hovertemplate="<b>Actual</b><br>Date: %{x|%a %d %b}<br>Value: %{y:.1f}<extra></extra>"
    ))

# Add current OTB
otb_df = df[df['Current_OTB'].notna()]
if len(otb_df) > 0:
    fig.add_trace(go.Scatter(
        x=otb_df['date'],
        y=otb_df['Current_OTB'],
        name='On-the-Books',
        mode='markers',
        marker=dict(color=colors['Current_OTB'], size=8, symbol='diamond'),
        hovertemplate="<b>Current OTB</b><br>Date: %{x|%a %d %b}<br>Value: %{y:.1f}<extra></extra>"
    ))

# Add budget line
budget_df = df[df['Budget'].notna()]
if len(budget_df) > 0:
    fig.add_trace(go.Scatter(
        x=budget_df['date'],
        y=budget_df['Budget'],
        name='Budget',
        line=dict(color=colors['Budget'], width=1, dash='dash'),
        hovertemplate="<b>Budget</b><br>Date: %{x|%a %d %b}<br>Value: %{y:.1f}<extra></extra>"
    ))

# Add prior year actual as reference line
py_df = df[df['Prior_Year'].notna()]
if len(py_df) > 0:
    fig.add_trace(go.Scatter(
        x=py_df['date'],
        y=py_df['Prior_Year'],
        name='Prior Year',
        line=dict(color=colors['Prior_Year'], width=2, dash='dot'),
        hovertemplate="<b>Prior Year Actual</b><br>Date: %{x|%a %d %b}<br>Value: %{y:.1f}<extra></extra>"
    ))

# Add today line (without annotation to avoid type issues)
fig.add_vline(x=str(date.today()), line_dash="dot", line_color="gray")

fig.update_layout(
    xaxis_title='Date',
    yaxis_title=metric_options.get(selected_metric, selected_metric),
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    height=450,
    hovermode='x unified',
    xaxis=dict(tickformat='%a %d %b')  # Shows "Mon 01 Feb"
)

st.plotly_chart(fig, use_container_width=True)

# Model accuracy comparison
st.subheader("🎯 Model Accuracy (Historical)")
st.caption("_How accurate each model has been for past forecasts_")

accuracy_data = fetch_accuracy(start_date - timedelta(days=30), date.today())

if accuracy_data:
    col1, col2 = st.columns(2)

    with col1:
        if 'by_model' in accuracy_data:
            st.markdown("**Accuracy Metrics by Model**")
            accuracy_df = pd.DataFrame(accuracy_data['by_model'])
            st.dataframe(
                accuracy_df.style.highlight_min(subset=['mae', 'rmse', 'mape'], color='lightgreen')
                    .highlight_max(subset=['win_count'], color='lightgreen'),
                use_container_width=True,
                hide_index=True
            )

            with st.expander("What do these metrics mean?"):
                st.markdown("""
                - **MAE (Mean Absolute Error)**: Average absolute difference between forecast and actual. Lower = better.
                - **RMSE (Root Mean Squared Error)**: Similar to MAE but penalizes large errors more. Lower = better.
                - **MAPE (%)**: Error as a percentage. 10% MAPE means forecasts are typically 10% off.
                - **Win Count**: Number of days where this model was closest to actual. Higher = more reliable.
                """)

    with col2:
        if 'by_model' in accuracy_data and len(accuracy_data['by_model']) > 0:
            fig_pie = px.pie(
                values=[m.get('win_count', 0) for m in accuracy_data['by_model']],
                names=[m.get('model', '') for m in accuracy_data['by_model']],
                title='Model Win Rate',
                color_discrete_sequence=['#ff7f0e', '#2ca02c', '#9467bd', '#1f77b4']  # XGBoost, Pickup, TFT, Prophet
            )
            fig_pie.update_traces(hovertemplate="<b>%{label}</b><br>Wins: %{value}<br>%{percent}<extra></extra>")
            st.plotly_chart(fig_pie, use_container_width=True)
else:
    st.info("""
    **Accuracy data not yet available.**

    Accuracy is calculated after forecasted dates pass and actual results are known.
    Check back once you have historical forecasts to compare against actuals.
    """)

# Model divergence analysis
st.subheader("🔍 Model Divergence Analysis")
st.caption("_When models disagree, it may indicate unusual patterns or uncertainty_")

# Calculate model divergence where we have all values
valid_df = df[df['XGBoost'].notna()].copy()

if len(valid_df) > 0:
    # Calculate differences
    has_pickup = valid_df['Pickup'].notna().any()

    col1, col2 = st.columns(2)

    with col1:
        if has_pickup:
            valid_df['XGBoost_Pickup_Diff'] = abs(valid_df['XGBoost'] - valid_df['Pickup'])
            avg_diff = valid_df['XGBoost_Pickup_Diff'].mean()
            st.metric(
                "Avg XGBoost-Pickup Gap",
                f"{avg_diff:.1f}",
                help="Average absolute difference between XGBoost and Pickup predictions"
            )

            # Identify high divergence days
            high_div = valid_df[valid_df['XGBoost_Pickup_Diff'] > avg_diff * 1.5]
            if len(high_div) > 0:
                st.warning(f"⚠️ {len(high_div)} days with high model disagreement (>50% above average)")

    with col2:
        if has_pickup:
            # Divergence over time chart
            fig_div = go.Figure()
            fig_div.add_trace(go.Scatter(
                x=valid_df['date'],
                y=valid_df['XGBoost_Pickup_Diff'],
                name='XGBoost vs Pickup',
                fill='tozeroy',
                line=dict(color='#1f77b4'),
                hovertemplate="Date: %{x|%a %d %b}<br>Difference: %{y:.1f}<extra></extra>"
            ))
            fig_div.update_layout(
                title='Model Divergence Over Time',
                xaxis_title='Date',
                yaxis_title='Absolute Difference',
                height=250,
                legend=dict(orientation='h', yanchor='bottom', y=1.02)
            )
            st.plotly_chart(fig_div, use_container_width=True)
        else:
            st.info("Pickup model data not available for divergence analysis.")

    with st.expander("ℹ️ How to Interpret Model Divergence"):
        st.markdown("""
        **Why models might disagree:**

        1. **Short vs Long-term horizon**: Pickup uses current bookings; XGBoost uses historical patterns
        2. **Unusual events**: Special events, weather, or external factors one model captures better
        3. **Data availability**: Pickup requires OTB data; XGBoost needs sufficient training history

        **What to do when models disagree:**

        - **High divergence near-term**: Trust Pickup model (has real booking data)
        - **High divergence far-term**: XGBoost is often more reliable
        - **Consistently high divergence**: Investigate if there's a data quality issue
        """)
else:
    st.info("Not enough data to calculate model divergence. Wait for forecasts to be generated.")

# Data table
st.markdown("---")
st.subheader("📊 Forecast Data Table")

# Prepare display dataframe
display_cols = ['date']
col_labels = {'date': 'Date'}

if 'XGBoost' in df.columns and df['XGBoost'].notna().any():
    display_cols.append('XGBoost')
    col_labels['XGBoost'] = 'XGBoost'
if 'Pickup' in df.columns and df['Pickup'].notna().any():
    display_cols.append('Pickup')
    col_labels['Pickup'] = 'Pickup'
if 'TFT' in df.columns and df['TFT'].notna().any():
    display_cols.append('TFT')
    col_labels['TFT'] = 'TFT'
if 'Prophet' in df.columns and df['Prophet'].notna().any():
    display_cols.append('Prophet')
    col_labels['Prophet'] = 'Prophet'
if 'Current_OTB' in df.columns and df['Current_OTB'].notna().any():
    display_cols.append('Current_OTB')
    col_labels['Current_OTB'] = 'OTB'
if 'Actual' in df.columns and df['Actual'].notna().any():
    display_cols.append('Actual')
    col_labels['Actual'] = 'Actual'
if 'Budget' in df.columns and df['Budget'].notna().any():
    display_cols.append('Budget')
    col_labels['Budget'] = 'Budget'

display_df = df[display_cols].copy()
display_df['date'] = display_df['date'].dt.strftime('%a %d %b %Y')
display_df = display_df.rename(columns=col_labels)

st.dataframe(display_df, use_container_width=True, hide_index=True, height=300)

# Export
col1, col2 = st.columns([1, 4])
with col1:
    csv = display_df.to_csv(index=False)
    st.download_button(
        label="📥 Export CSV",
        data=csv,
        file_name=f"forecast_comparison_{selected_metric}_{start_date}_{end_date}.csv",
        mime="text/csv"
    )
