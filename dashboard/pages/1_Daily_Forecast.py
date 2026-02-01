"""
Daily Forecast Page
Shows daily actual data and forecasts with all models side-by-side
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
from components.date_picker import render_date_picker_with_quickfill

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

st.set_page_config(page_title="Daily Forecast", page_icon="📅", layout="wide")

# Require authentication
require_auth()

# ============================================
# METRIC DEFINITIONS WITH EXPLANATIONS
# ============================================
METRIC_INFO = {
    "hotel_occupancy_pct": {
        "name": "Occupancy %",
        "description": "Percentage of available rooms that are occupied on a given night.",
        "calculation": "Occupied Rooms ÷ Available Rooms × 100",
        "source": "Newbook PMS - calculated from booking data and room inventory",
        "interpretation": "Higher occupancy indicates stronger demand. Industry benchmark is 65-75%.",
        "unit": "%",
        "format": ".1f"
    },
    "hotel_room_nights": {
        "name": "Room Nights",
        "description": "Total number of rooms occupied on a given night.",
        "calculation": "Count of all room bookings for the night",
        "source": "Newbook PMS - booking records",
        "interpretation": "Core volume metric. Compare to available inventory to assess capacity.",
        "unit": "rooms",
        "format": ".0f"
    },
    "hotel_guests": {
        "name": "Total Guests",
        "description": "Total number of guests staying at the hotel.",
        "calculation": "Sum of adults + children across all bookings",
        "source": "Newbook PMS - guest count from booking records",
        "interpretation": "Useful for F&B planning and staffing. Average 1.5-2 guests per room.",
        "unit": "guests",
        "format": ".0f"
    },
    "hotel_arrivals": {
        "name": "Arrivals",
        "description": "Number of new guest check-ins on a given day.",
        "calculation": "Count of bookings with check-in date matching the day",
        "source": "Newbook PMS - booking arrival dates",
        "interpretation": "High arrivals = busy reception. Plan staffing accordingly.",
        "unit": "arrivals",
        "format": ".0f"
    },
    "hotel_adr": {
        "name": "ADR (Net)",
        "description": "Average Daily Rate - average revenue per occupied room (excluding VAT).",
        "calculation": "Net Room Revenue ÷ Occupied Rooms",
        "source": "Newbook PMS - tariff data excluding VAT",
        "interpretation": "Key pricing metric. Higher ADR with stable occupancy = optimal revenue management.",
        "unit": "£",
        "format": ".2f"
    },
    "hotel_revpar": {
        "name": "RevPAR",
        "description": "Revenue Per Available Room - revenue performance across all inventory.",
        "calculation": "Net Room Revenue ÷ Available Rooms (or ADR × Occupancy %)",
        "source": "Calculated from Newbook data",
        "interpretation": "Best single metric for revenue performance. Combines rate and occupancy.",
        "unit": "£",
        "format": ".2f"
    },
    "hotel_breakfast_qty": {
        "name": "Breakfast Allocation",
        "description": "Number of breakfast covers allocated from hotel bookings.",
        "calculation": "Sum of breakfast allocations across all bookings",
        "source": "Newbook PMS - breakfast add-ons and packages",
        "interpretation": "Helps F&B team plan breakfast service capacity.",
        "unit": "covers",
        "format": ".0f"
    },
    "hotel_dinner_qty": {
        "name": "Dinner Allocation",
        "description": "Number of dinner covers allocated from hotel bookings.",
        "calculation": "Sum of dinner allocations across all bookings",
        "source": "Newbook PMS - dinner add-ons and packages",
        "interpretation": "Pre-booked hotel guest dinners. Add to Resos for total expected covers.",
        "unit": "covers",
        "format": ".0f"
    },
    "resos_lunch_covers": {
        "name": "Lunch Covers",
        "description": "Total restaurant covers for lunch service from Resos bookings.",
        "calculation": "Sum of party sizes for lunch bookings",
        "source": "Resos booking system - lunch service bookings",
        "interpretation": "External restaurant demand. Combine with hotel breakfast for lunch planning.",
        "unit": "covers",
        "format": ".0f"
    },
    "resos_dinner_covers": {
        "name": "Dinner Covers",
        "description": "Total restaurant covers for dinner service from Resos bookings.",
        "calculation": "Sum of party sizes for dinner bookings",
        "source": "Resos booking system - dinner service bookings",
        "interpretation": "External restaurant demand. Add hotel dinner allocation for total covers.",
        "unit": "covers",
        "format": ".0f"
    },
    "resos_lunch_bookings": {
        "name": "Lunch Bookings",
        "description": "Number of lunch booking reservations.",
        "calculation": "Count of lunch bookings",
        "source": "Resos booking system",
        "interpretation": "Booking count vs covers shows average party size.",
        "unit": "bookings",
        "format": ".0f"
    },
    "resos_dinner_bookings": {
        "name": "Dinner Bookings",
        "description": "Number of dinner booking reservations.",
        "calculation": "Count of dinner bookings",
        "source": "Resos booking system",
        "interpretation": "Booking count vs covers shows average party size.",
        "unit": "bookings",
        "format": ".0f"
    },
    "revenue_rooms": {
        "name": "Room Revenue",
        "description": "Total accommodation revenue (net of VAT).",
        "calculation": "Sum of room tariffs excluding VAT",
        "source": "Newbook PMS - earned revenue report",
        "interpretation": "Primary revenue stream. Track against budget and prior year.",
        "unit": "£",
        "format": ",.0f"
    }
}

MODEL_INFO = {
    "xgboost": {
        "name": "XGBoost",
        "description": "Gradient boosting machine learning model that learns patterns from historical data.",
        "strengths": "Excellent at capturing complex patterns, day-of-week effects, and trends.",
        "best_for": "Medium to long-term forecasts where historical patterns are strong.",
        "color": "#ff7f0e"
    },
    "prophet": {
        "name": "Prophet",
        "description": "Facebook's time series model designed for business forecasting with seasonality.",
        "strengths": "Handles holidays, missing data, and provides uncertainty intervals.",
        "best_for": "Data with strong seasonal patterns and holiday effects.",
        "color": "#1f77b4"
    },
    "pickup": {
        "name": "Pickup",
        "description": "Hotel industry standard model comparing current bookings to historical pace.",
        "strengths": "Uses real-time booking data and prior year comparisons.",
        "best_for": "Short-term forecasts (0-28 days) where current OTB is available.",
        "color": "#2ca02c"
    }
}

# ============================================
# PAGE CONTENT
# ============================================
st.title("📅 Daily Forecast")

# Help expander with metric explanations
with st.expander("ℹ️ Understanding This Page", expanded=False):
    st.markdown("""
    ### What This Page Shows
    This page displays **daily forecasts** from multiple forecasting models alongside **historical actual data**.

    ### Data Sources
    - **Hotel Data**: Newbook Property Management System (PMS)
    - **Restaurant Data**: Resos booking system
    - **Forecasts**: Generated daily using XGBoost, Prophet, and Pickup models

    ### How to Use
    1. Select a date range to view historical data and forecasts
    2. Choose a metric from the dropdown
    3. Compare model forecasts to see consensus or divergence
    4. Use the data table for detailed day-by-day values
    """)

    st.markdown("### Forecasting Models")
    cols = st.columns(3)
    for i, (model_key, model) in enumerate(MODEL_INFO.items()):
        with cols[i]:
            st.markdown(f"**{model['name']}**")
            st.markdown(f"_{model['description']}_")
            st.markdown(f"**Best for:** {model['best_for']}")

# Date range selector with quick-fill buttons
available_metrics = list(METRIC_INFO.keys())
start_date, end_date, metric = render_date_picker_with_quickfill(
    key_prefix="daily_forecast",
    default_start=date.today() - timedelta(days=7),
    default_end=date.today() + timedelta(days=28),
    show_metric_selector=True,
    metric_options=available_metrics,
    metric_format_func=lambda x: METRIC_INFO.get(x, {}).get("name", x)
)

# Show metric info
metric_info = METRIC_INFO.get(metric, {})
if metric_info:
    with st.expander(f"ℹ️ About {metric_info.get('name', metric)}", expanded=False):
        st.markdown(f"**Description:** {metric_info.get('description', 'N/A')}")
        st.markdown(f"**Calculation:** {metric_info.get('calculation', 'N/A')}")
        st.markdown(f"**Data Source:** {metric_info.get('source', 'N/A')}")
        st.markdown(f"**Interpretation:** {metric_info.get('interpretation', 'N/A')}")

st.markdown("---")

# ============================================
# DATA FETCHING
# ============================================
@st.cache_data(ttl=60)
def fetch_historical_data(from_date, to_date):
    """Fetch historical actual data"""
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
    except Exception as e:
        st.error(f"Error fetching historical data: {e}")
        return []

@st.cache_data(ttl=60)
def fetch_forecasts(from_date, to_date, metric_code):
    """Fetch forecast data for a specific metric"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/forecast/comparison",
            params={
                "from_date": str(from_date),
                "to_date": str(to_date),
                "metric": metric_code
            },
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"Error fetching forecasts: {e}")
        return []

# Fetch data
historical_data = fetch_historical_data(start_date, min(end_date, date.today()))
forecast_data = fetch_forecasts(max(start_date, date.today()), end_date, metric)

# ============================================
# MAIN CHART
# ============================================
st.subheader("📈 Forecast vs Actuals")

fig = go.Figure()

# Map metric codes to historical data columns
metric_to_column = {
    "hotel_occupancy_pct": "occupancy_pct",
    "hotel_room_nights": "occupied_rooms",
    "hotel_guests": "total_guests",
    "hotel_arrivals": "arrival_count",
    "hotel_adr": "adr",
    "hotel_revpar": "revpar",
    "resos_lunch_covers": "lunch_covers",
    "resos_dinner_covers": "dinner_covers",
    "revenue_rooms": "room_revenue"
}

# Add historical actuals if available
if historical_data:
    hist_df = pd.DataFrame(historical_data)
    hist_df['date'] = pd.to_datetime(hist_df['date'])
    hist_df = hist_df.sort_values('date')

    col_name = metric_to_column.get(metric)
    if col_name and col_name in hist_df.columns:
        fig.add_trace(go.Scatter(
            x=hist_df['date'],
            y=hist_df[col_name],
            name='Actual',
            line=dict(color='#333333', width=3),
            mode='lines+markers',
            marker=dict(size=6)
        ))

# Add forecasts if available
if forecast_data:
    fc_df = pd.DataFrame(forecast_data)
    fc_df['date'] = pd.to_datetime(fc_df['date'])
    fc_df = fc_df.sort_values('date')

    # XGBoost forecast
    if 'models' in fc_df.columns:
        xgb_values = []
        prophet_values = []
        pickup_values = []

        for _, row in fc_df.iterrows():
            models = row.get('models', {})
            xgb_values.append(models.get('xgboost', {}).get('value'))
            prophet_values.append(models.get('prophet', {}).get('value'))
            pickup_values.append(models.get('pickup', {}).get('value'))

        # Add XGBoost
        if any(v is not None for v in xgb_values):
            fig.add_trace(go.Scatter(
                x=fc_df['date'],
                y=xgb_values,
                name='XGBoost Forecast',
                line=dict(color='#ff7f0e', width=2),
                mode='lines'
            ))

        # Add Prophet
        if any(v is not None for v in prophet_values):
            fig.add_trace(go.Scatter(
                x=fc_df['date'],
                y=prophet_values,
                name='Prophet Forecast',
                line=dict(color='#1f77b4', width=2),
                mode='lines'
            ))

        # Add Pickup
        if any(v is not None for v in pickup_values):
            fig.add_trace(go.Scatter(
                x=fc_df['date'],
                y=pickup_values,
                name='Pickup Forecast',
                line=dict(color='#2ca02c', width=2),
                mode='lines+markers',
                marker=dict(size=8, symbol='diamond')
            ))

    # Add budget line if available
    if 'budget' in fc_df.columns and fc_df['budget'].notna().any():
        fig.add_trace(go.Scatter(
            x=fc_df['date'],
            y=fc_df['budget'],
            name='Budget',
            line=dict(color='#d62728', width=2, dash='dash')
        ))

    # Add current OTB if available
    if 'current_otb' in fc_df.columns and fc_df['current_otb'].notna().any():
        fig.add_trace(go.Scatter(
            x=fc_df['date'],
            y=fc_df['current_otb'],
            name='Current OTB',
            mode='markers',
            marker=dict(color='#9467bd', size=10, symbol='diamond')
        ))

    # Add prior year OTB (what was booked at this lead time last year)
    if 'prior_year_otb' in fc_df.columns and fc_df['prior_year_otb'].notna().any():
        fig.add_trace(go.Scatter(
            x=fc_df['date'],
            y=fc_df['prior_year_otb'],
            name='Prior Year OTB',
            mode='markers',
            marker=dict(color='#17becf', size=8, symbol='square')
        ))

    # Add prior year actual as reference
    if 'prior_year_actual' in fc_df.columns and fc_df['prior_year_actual'].notna().any():
        fig.add_trace(go.Scatter(
            x=fc_df['date'],
            y=fc_df['prior_year_actual'],
            name='Prior Year',
            line=dict(color='#7f7f7f', width=2, dash='dot'),
            mode='lines'
        ))

# Add vertical line for today
fig.add_vline(x=str(date.today()), line_dash="dot", line_color="gray")

unit = metric_info.get('unit', '')
fig.update_layout(
    title=f"{metric_info.get('name', metric)} - Daily View",
    xaxis_title='Date',
    yaxis_title=f"{metric_info.get('name', metric)} ({unit})",
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    height=500,
    hovermode='x unified',
    xaxis=dict(tickformat='%a %d %b')  # Shows "Mon 01 Feb"
)

st.plotly_chart(fig, use_container_width=True)

# ============================================
# DATA TABLE
# ============================================
st.subheader("📊 Data Table")

# Build combined dataframe
all_dates = pd.date_range(start=start_date, end=end_date, freq='D')
table_data = []

for d in all_dates:
    row = {'Date': d, 'Day': d.strftime('%a')}

    # Add actual if available
    if historical_data:
        hist_match = [h for h in historical_data if h.get('date') == str(d.date())]
        if hist_match:
            col_name = metric_to_column.get(metric)
            if col_name:
                row['Actual'] = hist_match[0].get(col_name)

    # Add forecasts if available
    if forecast_data:
        fc_match = [f for f in forecast_data if f.get('date') == str(d.date())]
        if fc_match:
            models = fc_match[0].get('models', {})
            row['XGBoost'] = models.get('xgboost', {}).get('value')
            row['Prophet'] = models.get('prophet', {}).get('value')
            row['Pickup'] = models.get('pickup', {}).get('value')
            row['Budget'] = fc_match[0].get('budget')
            row['OTB'] = fc_match[0].get('current_otb')
            row['PY OTB'] = fc_match[0].get('prior_year_otb')
            row['PY Actual'] = fc_match[0].get('prior_year_actual')

    table_data.append(row)

table_df = pd.DataFrame(table_data)
table_df['Date'] = table_df['Date'].dt.strftime('%d %b %Y')

# Format based on metric
fmt = metric_info.get('format', '.1f')
style_dict = {}
for col in ['Actual', 'XGBoost', 'Prophet', 'Pickup', 'Budget', 'OTB', 'PY OTB', 'PY Actual']:
    if col in table_df.columns:
        if metric_info.get('unit') == '£':
            style_dict[col] = '£{:' + fmt + '}'
        elif metric_info.get('unit') == '%':
            style_dict[col] = '{:' + fmt + '}%'
        else:
            style_dict[col] = '{:' + fmt + '}'

st.dataframe(
    table_df.style.format(style_dict, na_rep='-'),
    use_container_width=True,
    hide_index=True,
    height=400
)

# ============================================
# SUMMARY STATISTICS
# ============================================
st.subheader("📋 Summary Statistics")

col1, col2, col3, col4, col5 = st.columns(5)

# Calculate averages
with col1:
    if 'Actual' in table_df.columns:
        avg_actual = pd.to_numeric(table_df['Actual'], errors='coerce').mean()
        if pd.notna(avg_actual):
            if metric_info.get('unit') == '£':
                st.metric("Avg Actual", f"£{avg_actual:,.1f}")
            elif metric_info.get('unit') == '%':
                st.metric("Avg Actual", f"{avg_actual:.1f}%")
            else:
                st.metric("Avg Actual", f"{avg_actual:.1f}")
        else:
            st.metric("Avg Actual", "-")
    else:
        st.metric("Avg Actual", "-")

with col2:
    if 'XGBoost' in table_df.columns:
        avg_xgb = pd.to_numeric(table_df['XGBoost'], errors='coerce').mean()
        if pd.notna(avg_xgb):
            if metric_info.get('unit') == '£':
                st.metric("Avg XGBoost", f"£{avg_xgb:,.1f}")
            elif metric_info.get('unit') == '%':
                st.metric("Avg XGBoost", f"{avg_xgb:.1f}%")
            else:
                st.metric("Avg XGBoost", f"{avg_xgb:.1f}")
        else:
            st.metric("Avg XGBoost", "-")
    else:
        st.metric("Avg XGBoost", "-")

with col3:
    if 'Pickup' in table_df.columns:
        avg_pickup = pd.to_numeric(table_df['Pickup'], errors='coerce').mean()
        if pd.notna(avg_pickup):
            if metric_info.get('unit') == '£':
                st.metric("Avg Pickup", f"£{avg_pickup:,.1f}")
            elif metric_info.get('unit') == '%':
                st.metric("Avg Pickup", f"{avg_pickup:.1f}%")
            else:
                st.metric("Avg Pickup", f"{avg_pickup:.1f}")
        else:
            st.metric("Avg Pickup", "-")
    else:
        st.metric("Avg Pickup", "-")

with col4:
    if 'Budget' in table_df.columns:
        avg_budget = pd.to_numeric(table_df['Budget'], errors='coerce').mean()
        if pd.notna(avg_budget):
            if metric_info.get('unit') == '£':
                st.metric("Avg Budget", f"£{avg_budget:,.1f}")
            elif metric_info.get('unit') == '%':
                st.metric("Avg Budget", f"{avg_budget:.1f}%")
            else:
                st.metric("Avg Budget", f"{avg_budget:.1f}")
        else:
            st.metric("Avg Budget", "-")
    else:
        st.metric("Avg Budget", "-")

with col5:
    days = len(table_df)
    st.metric("Days in Range", f"{days}")

# ============================================
# EXPORT
# ============================================
st.markdown("---")
col1, col2 = st.columns([1, 4])
with col1:
    csv = table_df.to_csv(index=False)
    st.download_button(
        label="📥 Export CSV",
        data=csv,
        file_name=f"forecast_{metric}_{start_date}_{end_date}.csv",
        mime="text/csv"
    )
