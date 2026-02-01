"""
TFT Live Forecast Page
Live Temporal Fusion Transformer forecasting with uncertainty quantiles
"""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import httpx

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.auth import require_auth, get_auth_header
from components.date_picker import get_quick_date_ranges

# TFT uses the new backend with forecast_data database (newbook_bookings_stats)
BACKEND_URL = os.getenv("BACKEND_NEW_URL", "http://backend-new:8000")

st.set_page_config(page_title="TFT Live Forecast", page_icon="🟣", layout="wide")

# Require authentication
require_auth()

st.title("🟣 TFT Live Forecast")
st.caption("_Temporal Fusion Transformer - deep learning with attention-based explainability_")

# Help expander
with st.expander("ℹ️ About TFT (Temporal Fusion Transformer)", expanded=False):
    st.markdown("""
    ### What is TFT?

    TFT (Temporal Fusion Transformer) is a state-of-the-art deep learning model designed for
    multi-horizon time series forecasting. It was developed by Google and is particularly
    effective for hotel occupancy forecasting.

    ---

    **Key Features:**

    - **Attention Mechanism**: Identifies which historical patterns and future events matter most
    - **Multi-Horizon**: Forecasts multiple days ahead in a single pass
    - **Uncertainty Quantification**: Provides 80% confidence intervals (10th to 90th percentile)
    - **Known Future Inputs**: Uses holidays, day of week, and special events as known future features

    ---

    **How to Interpret the Forecast:**

    | Element | Description |
    |---------|-------------|
    | **Purple Line** | The median (50th percentile) forecast - most likely value |
    | **Shaded Band** | 80% confidence interval (10th to 90th percentile) |
    | **Prior Year** | Same day of week from 52 weeks ago for comparison |
    | **Current OTB** | On-the-books - actual bookings we already have |

    ---

    **When TFT is Most Useful:**

    - Medium to long-term forecasts (7-28 days out)
    - Periods with strong holiday/event effects
    - When you need uncertainty estimates for planning
    - Complex patterns that simpler models might miss

    **Limitations:**

    - Runs weekly (computationally expensive to train)
    - Requires more historical data than simpler models
    - Less responsive to real-time booking changes than Pickup model
    """)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def fetch_tft_forecast(start_date, end_date, metric, perception_date=None):
    """Fetch TFT live forecast from API"""
    try:
        params = {
            "start_date": str(start_date),
            "end_date": str(end_date),
            "metric": metric
        }
        if perception_date:
            params["perception_date"] = str(perception_date)

        response = httpx.get(
            f"{BACKEND_URL}/forecast/tft-preview",
            params=params,
            headers=get_auth_header(),
            timeout=120.0  # TFT can take time to train
        )
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 503:
            return {"error": "TFT dependencies not installed on server"}
        else:
            return {"error": f"API error: {response.status_code}"}
    except httpx.TimeoutException:
        return {"error": "Request timed out - TFT training may take longer than expected"}
    except Exception as e:
        return {"error": str(e)}


# Quick-fill date buttons
quick_ranges = get_quick_date_ranges()
st.markdown("**Quick Select:**")

# Initialize session state
if "tft_start" not in st.session_state:
    st.session_state.tft_start = date.today()
if "tft_end" not in st.session_state:
    st.session_state.tft_end = date.today() + timedelta(days=28)

# Button row
cols_q = st.columns(6)
quick_buttons = ["This Week", "This Month", "Next Month", "Next 3 Months", "Next 7 Days", "Next 14 Days"]
for i, name in enumerate(quick_buttons):
    with cols_q[i]:
        if name in quick_ranges:
            if st.button(name, key=f"tft_quick_{name}", use_container_width=True):
                start, end = quick_ranges[name]
                st.session_state.tft_start = start
                st.session_state.tft_end = end
                st.rerun()
        elif name == "Next 7 Days":
            if st.button(name, key=f"tft_quick_{name}", use_container_width=True):
                st.session_state.tft_start = date.today()
                st.session_state.tft_end = date.today() + timedelta(days=7)
                st.rerun()
        elif name == "Next 14 Days":
            if st.button(name, key=f"tft_quick_{name}", use_container_width=True):
                st.session_state.tft_start = date.today()
                st.session_state.tft_end = date.today() + timedelta(days=14)
                st.rerun()

st.markdown("")

# Controls
col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

with col1:
    metric = st.selectbox(
        "Metric",
        options=["occupancy", "rooms"],
        format_func=lambda x: "Occupancy %" if x == "occupancy" else "Room Nights",
        help="Choose between occupancy percentage or room night count"
    )

with col2:
    start_date = st.date_input(
        "From",
        value=st.session_state.tft_start,
        help="Start date for forecast"
    )
    st.session_state.tft_start = start_date

with col3:
    end_date = st.date_input(
        "To",
        value=st.session_state.tft_end,
        help="End date for forecast"
    )
    st.session_state.tft_end = end_date

with col4:
    backtest_mode = st.checkbox(
        "Backtest Mode",
        value=False,
        help="Generate forecast as if it was a past date"
    )
    if backtest_mode:
        perception_date = st.date_input(
            "As of Date",
            value=date.today() - timedelta(days=30),
            help="Pretend today is this date"
        )
    else:
        perception_date = None

st.markdown("---")

# Fetch forecast
with st.spinner("Training TFT model and generating forecast... This may take 1-2 minutes."):
    forecast_data = fetch_tft_forecast(start_date, end_date, metric, perception_date)

if "error" in forecast_data:
    st.error(f"**Error:** {forecast_data['error']}")
    st.info("""
    **Troubleshooting:**
    - Ensure PyTorch and pytorch-forecasting are installed on the backend
    - Check that you have at least 90 days of historical data
    - Try a shorter date range (TFT requires significant computation)
    """)
    st.stop()

if not forecast_data.get("data"):
    st.warning("No forecast data generated. Check your date range.")
    st.stop()

# Convert to DataFrame
df = pd.DataFrame(forecast_data["data"])
df['date'] = pd.to_datetime(df['date'])
summary = forecast_data.get("summary", {})

# Summary metrics
st.subheader("📊 Forecast Summary")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        "TFT Forecast Total",
        f"{summary.get('forecast_total', 0):.1f}{'%' if metric == 'occupancy' else ''}",
        help="Sum of TFT median forecasts"
    )

with col2:
    st.metric(
        "Current OTB Total",
        f"{summary.get('otb_total', 0):.1f}{'%' if metric == 'occupancy' else ''}",
        help="Sum of current on-the-books"
    )

with col3:
    st.metric(
        "Prior Year Total",
        f"{summary.get('prior_final_total', 0):.1f}{'%' if metric == 'occupancy' else ''}",
        help="Sum of prior year actuals (52 weeks ago)"
    )

with col4:
    delta = summary.get('days_forecasting_more', 0) - summary.get('days_forecasting_less', 0)
    st.metric(
        "Days Above Prior Year",
        f"{summary.get('days_forecasting_more', 0)} / {summary.get('days_count', 0)}",
        delta=f"{delta:+d} net",
        help="Days where TFT forecasts higher than prior year"
    )

st.markdown("---")

# Forecast chart
st.subheader("📈 TFT Forecast with Confidence Interval")

fig = go.Figure()

# Add confidence band
fig.add_trace(go.Scatter(
    x=pd.concat([df['date'], df['date'][::-1]]),
    y=pd.concat([df['forecast_upper'], df['forecast_lower'][::-1]]),
    fill='toself',
    fillcolor='rgba(148, 103, 189, 0.2)',  # Purple with transparency
    line=dict(color='rgba(255,255,255,0)'),
    name='80% Confidence Interval',
    hoverinfo='skip'
))

# Add TFT median forecast line (purple)
fig.add_trace(go.Scatter(
    x=df['date'],
    y=df['forecast'],
    name='TFT Forecast',
    line=dict(color='#9467bd', width=3),  # Purple
    hovertemplate="<b>TFT</b><br>Date: %{x|%a %d %b}<br>Forecast: %{y:.1f}<extra></extra>"
))

# Add current OTB
otb_df = df[df['current_otb'].notna()]
if len(otb_df) > 0:
    fig.add_trace(go.Scatter(
        x=otb_df['date'],
        y=otb_df['current_otb'],
        name='Current OTB',
        mode='markers',
        marker=dict(color='#17becf', size=10, symbol='diamond'),
        hovertemplate="<b>On-the-Books</b><br>Date: %{x|%a %d %b}<br>Value: %{y:.1f}<extra></extra>"
    ))

# Add prior year
py_df = df[df['prior_year_final'].notna()]
if len(py_df) > 0:
    fig.add_trace(go.Scatter(
        x=py_df['date'],
        y=py_df['prior_year_final'],
        name='Prior Year',
        line=dict(color='#7f7f7f', width=2, dash='dot'),
        hovertemplate="<b>Prior Year</b><br>Date: %{x|%a %d %b}<br>Value: %{y:.1f}<extra></extra>"
    ))

# Add today line
fig.add_vline(x=str(date.today()), line_dash="dot", line_color="gray")

y_axis_title = "Occupancy %" if metric == "occupancy" else "Room Nights"
fig.update_layout(
    xaxis_title='Date',
    yaxis_title=y_axis_title,
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    height=450,
    hovermode='x unified',
    xaxis=dict(tickformat='%a %d %b')
)

st.plotly_chart(fig, use_container_width=True)

# Data table
st.markdown("---")
st.subheader("📋 Forecast Data Table")

# Prepare display dataframe
display_df = df[['date', 'day_of_week', 'forecast', 'forecast_lower', 'forecast_upper',
                 'current_otb', 'prior_year_final']].copy()
display_df['date'] = display_df['date'].dt.strftime('%a %d %b %Y')
display_df = display_df.rename(columns={
    'date': 'Date',
    'day_of_week': 'DOW',
    'forecast': 'TFT Forecast',
    'forecast_lower': 'Lower (10%)',
    'forecast_upper': 'Upper (90%)',
    'current_otb': 'OTB',
    'prior_year_final': 'Prior Year'
})

# Style the dataframe
st.dataframe(
    display_df,
    use_container_width=True,
    hide_index=True,
    height=400
)

# Export
col1, col2 = st.columns([1, 4])
with col1:
    csv = display_df.to_csv(index=False)
    st.download_button(
        label="📥 Export CSV",
        data=csv,
        file_name=f"tft_forecast_{metric}_{start_date}_{end_date}.csv",
        mime="text/csv"
    )

# Comparison with other models
st.markdown("---")
st.subheader("🔄 Compare with Other Models")
st.info("To compare TFT with Prophet, XGBoost, and Pickup models, use the **Model Comparison** page.")
