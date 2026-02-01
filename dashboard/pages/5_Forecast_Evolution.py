"""
Forecast Evolution Page
Track how forecasts change as dates approach
"""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.auth import require_auth, get_auth_header
from components.date_picker import get_quick_date_ranges

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

st.set_page_config(page_title="Forecast Evolution", page_icon="📉", layout="wide")
require_auth()

st.title("📉 Forecast Evolution")

# Help expander
with st.expander("ℹ️ Understanding Forecast Evolution", expanded=False):
    st.markdown("""
    ### What This Page Shows

    Track how forecasts for a specific date change as that date approaches. This helps you understand:

    - **Forecast Stability**: Do predictions change significantly or stay consistent?
    - **Convergence**: Do forecasts become more accurate closer to the date?
    - **Model Behavior**: Which models adjust more frequently?

    ### Why Forecasts Change

    Forecasts may change over time because:

    1. **New Bookings**: Pickup model incorporates real-time booking data
    2. **Updated Patterns**: XGBoost retrains with latest historical data
    3. **Seasonality Adjustments**: Models refine seasonal estimates

    ### Interpreting Evolution

    | Pattern | Interpretation |
    |---------|----------------|
    | **Stable** | High confidence; patterns match historical norms |
    | **Gradually increasing** | Building demand; positive momentum |
    | **Gradually decreasing** | Softening demand; potential concern |
    | **Volatile** | Unusual situation; models uncertain |

    ### Ideal Scenario

    - Forecasts should **converge toward the actual** as the date approaches
    - **Large last-minute changes** suggest forecasting model improvements needed
    - **Consistent accuracy** indicates well-tuned models
    """)

st.markdown("---")

# Quick target date buttons
st.markdown("**Quick Select Target Date:**")

# Initialize session state
if "fe_target" not in st.session_state:
    st.session_state.fe_target = date.today() + timedelta(days=14)

# Create quick target dates
cols_q = st.columns(6)
quick_targets = [
    ("Tomorrow", date.today() + timedelta(days=1)),
    ("Next Week", date.today() + timedelta(days=7)),
    ("2 Weeks", date.today() + timedelta(days=14)),
    ("3 Weeks", date.today() + timedelta(days=21)),
    ("1 Month", date.today() + timedelta(days=30)),
    ("2 Months", date.today() + timedelta(days=60)),
]
for i, (name, target) in enumerate(quick_targets):
    with cols_q[i]:
        if st.button(name, key=f"fe_quick_{name}", use_container_width=True):
            st.session_state.fe_target = target
            st.rerun()

st.markdown("")

@st.cache_data(ttl=60)
def fetch_evolution_data(target_date, metric_code):
    """Fetch forecast evolution data for a specific date"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/evolution/date",
            params={
                "target_date": str(target_date),
                "metric": metric_code
            },
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"Error fetching evolution data: {e}")
        return []

@st.cache_data(ttl=60)
def fetch_forecasts(from_date, to_date, metric):
    """Fetch current forecasts"""
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
col1, col2 = st.columns([1, 1])

with col1:
    target_date = st.date_input(
        "Target Date",
        value=st.session_state.fe_target,
        help="The date to track forecast evolution for"
    )
    st.session_state.fe_target = target_date

with col2:
    metric = st.selectbox(
        "Metric",
        ["hotel_occupancy_pct", "hotel_room_nights", "resos_dinner_covers", "resos_lunch_covers"],
        format_func=lambda x: {
            "hotel_occupancy_pct": "Occupancy %",
            "hotel_room_nights": "Room Nights",
            "resos_dinner_covers": "Dinner Covers",
            "resos_lunch_covers": "Lunch Covers"
        }.get(x, x),
        help="Select metric to track"
    )

st.markdown("---")

# Fetch evolution data
evolution_data = fetch_evolution_data(target_date, metric)

if evolution_data and len(evolution_data) > 0:
    df = pd.DataFrame(evolution_data)
    df['forecast_date'] = pd.to_datetime(df['forecast_date'])
    df = df.sort_values('forecast_date')

    # Main evolution chart
    st.subheader(f"📈 Forecast Evolution for {target_date.strftime('%a %d %b %Y')}")
    st.caption("_How forecasts changed as the date approached_")

    fig = go.Figure()

    # Add traces for each model
    colors = {'prophet': '#1f77b4', 'xgboost': '#ff7f0e', 'pickup': '#2ca02c'}

    for model in ['xgboost', 'pickup', 'prophet']:
        model_df = df[df['model_type'] == model]
        if len(model_df) > 0:
            fig.add_trace(go.Scatter(
                x=model_df['forecast_date'],
                y=model_df['predicted_value'],
                name=model.title(),
                line=dict(color=colors.get(model, '#333'), width=2),
                mode='lines+markers',
                hovertemplate=f"<b>{model.title()}</b><br>" +
                              "Generated: %{x|%d %b}<br>" +
                              "Prediction: %{y:.1f}<extra></extra>"
            ))

    # Add actual if past date
    if target_date <= date.today():
        # Try to get actual value
        current = fetch_forecasts(target_date, target_date, metric)
        if current and len(current) > 0:
            actual = current[0].get('actual')
            if actual is not None:
                fig.add_hline(
                    y=actual,
                    line_dash="solid",
                    line_color="red",
                    annotation_text=f"Actual: {actual:.1f}"
                )

    # Add vertical line for target date
    fig.add_vline(x=target_date, line_dash="dot", line_color="gray")

    fig.update_layout(
        xaxis_title='Forecast Generated Date',
        yaxis_title='Predicted Value',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=400,
        hovermode='x unified'
    )

    st.plotly_chart(fig, use_container_width=True)

    # Evolution statistics
    st.subheader("📊 Evolution Statistics")

    col1, col2, col3 = st.columns(3)

    for i, model in enumerate(['xgboost', 'pickup', 'prophet']):
        model_df = df[df['model_type'] == model]
        if len(model_df) > 0:
            with [col1, col2, col3][i]:
                st.markdown(f"**{model.title()}**")

                first_val = model_df.iloc[0]['predicted_value']
                last_val = model_df.iloc[-1]['predicted_value']
                change = last_val - first_val
                volatility = model_df['predicted_value'].std()

                st.metric("First Forecast", f"{first_val:.1f}")
                st.metric("Latest Forecast", f"{last_val:.1f}", delta=f"{change:+.1f}")
                st.metric("Volatility (Std Dev)", f"{volatility:.2f}")

    # Data table
    st.subheader("📋 Forecast History")

    display_df = df[['forecast_date', 'model_type', 'predicted_value']].copy()
    display_df['forecast_date'] = display_df['forecast_date'].dt.strftime('%d %b %Y')

    # Pivot for easier reading
    pivot_df = display_df.pivot(index='forecast_date', columns='model_type', values='predicted_value')
    pivot_df = pivot_df.round(1)

    st.dataframe(pivot_df, use_container_width=True)

else:
    st.info("""
    **No evolution data available for this date.**

    Forecast evolution tracking requires:
    1. Multiple forecast runs over time (daily regeneration)
    2. The forecast history to be stored

    As forecasts are generated each day, the evolution for future dates will accumulate.
    Check back after a few days of forecast runs.
    """)

    # Show current forecast instead
    st.markdown("---")
    st.subheader("📊 Current Forecast")

    current_fc = fetch_forecasts(target_date, target_date, metric)
    if current_fc and len(current_fc) > 0:
        fc = current_fc[0]
        models = fc.get('models', {})

        col1, col2, col3 = st.columns(3)

        with col1:
            xgb = models.get('xgboost', {}).get('value')
            if xgb:
                st.metric("XGBoost", f"{xgb:.1f}")

        with col2:
            pickup = models.get('pickup', {}).get('value')
            if pickup:
                st.metric("Pickup", f"{pickup:.1f}")

        with col3:
            prophet = models.get('prophet', {}).get('value')
            if prophet:
                st.metric("Prophet", f"{prophet:.1f}")
    else:
        st.warning("No forecast available for this date yet.")

# Additional insights
st.markdown("---")
st.subheader("💡 Tips for Using Forecast Evolution")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **When to be confident:**
    - All models converging to similar values
    - Low volatility over time
    - Patterns match historical norms
    """)

with col2:
    st.markdown("""
    **When to investigate further:**
    - Large swings in predictions
    - Models strongly disagreeing
    - Last-minute major revisions
    """)
