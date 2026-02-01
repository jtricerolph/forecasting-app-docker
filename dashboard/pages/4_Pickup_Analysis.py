"""
Pickup Analysis Page
Booking pace and lead time analysis with pickup model insights
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

st.set_page_config(page_title="Pickup Analysis", page_icon="📈", layout="wide")
require_auth()

st.title("📈 Pickup Analysis")

# Help expander
with st.expander("ℹ️ Understanding Pickup Analysis", expanded=False):
    st.markdown("""
    ### What is Pickup?

    **Pickup** is a hotel industry term describing how bookings accumulate (or "pick up") as a date approaches.

    ### Key Concepts

    **On-the-Books (OTB)**
    - Current bookings for a future date
    - Changes daily as new bookings come in and cancellations occur

    **Pickup Pace**
    - Rate at which new bookings are coming in
    - Compared to the same time period last year

    **Lead Time**
    - Days between booking and stay date
    - Different guests book at different lead times

    ### Pickup Curve Example

    | Days Out | OTB Today | Prior Year OTB | Prior Year Final | Pace vs PY |
    |----------|-----------|----------------|------------------|------------|
    | 28 days  | 45 rooms  | 40 rooms       | 72 rooms         | +12% ahead |
    | 21 days  | 52 rooms  | 48 rooms       | 72 rooms         | +8% ahead  |
    | 14 days  | 61 rooms  | 55 rooms       | 72 rooms         | +11% ahead |
    | 7 days   | 68 rooms  | 62 rooms       | 72 rooms         | +10% ahead |
    | Stay day | ?         | -              | 72 rooms         | **Projected: 79** |

    ### Projection Methods

    1. **Ratio Method**: Uses prior year's pickup ratio
       - Formula: Current OTB × (Prior Year Final ÷ Prior Year OTB at same lead time)

    2. **Curve Method**: Uses historical pickup curves by day-of-week and season
       - Formula: Current OTB ÷ (Historical % of final at this lead time)
    """)

st.markdown("---")

@st.cache_data(ttl=60)
def fetch_pickup_data(metric_code, from_date, to_date):
    """Fetch pickup/OTB data from API"""
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
        st.error(f"Error fetching pickup data: {e}")
        return []

# Quick-fill date buttons
quick_ranges = get_quick_date_ranges()
st.markdown("**Quick Select:**")

# Initialize session state
if "pickup_start" not in st.session_state:
    st.session_state.pickup_start = date.today()
if "pickup_end" not in st.session_state:
    st.session_state.pickup_end = date.today() + timedelta(days=60)

# Button row - focus on future dates for pickup analysis
cols1 = st.columns(5)
future_buttons = ["This Week", "This Month", "Next Month", "Next 3 Months", "Next 6 Months"]
for i, name in enumerate(future_buttons):
    with cols1[i]:
        if st.button(name, key=f"pickup_quick_{name}", use_container_width=True):
            start, end = quick_ranges[name]
            st.session_state.pickup_start = start
            st.session_state.pickup_end = end
            st.rerun()

st.markdown("")

# Controls
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    metric = st.selectbox(
        "Metric",
        ["hotel_occupancy_pct", "hotel_room_nights", "resos_dinner_covers", "resos_lunch_covers"],
        format_func=lambda x: {
            "hotel_occupancy_pct": "Occupancy %",
            "hotel_room_nights": "Room Nights",
            "resos_dinner_covers": "Dinner Covers",
            "resos_lunch_covers": "Lunch Covers"
        }.get(x, x),
        help="Select metric to analyze pickup patterns"
    )

with col2:
    start_date = st.date_input(
        "From",
        value=st.session_state.pickup_start,
        help="Start of forecast period"
    )
    st.session_state.pickup_start = start_date

with col3:
    end_date = st.date_input(
        "To",
        value=st.session_state.pickup_end,
        help="End of forecast period"
    )
    st.session_state.pickup_end = end_date

st.markdown("---")

# Fetch data
data = fetch_pickup_data(metric, start_date, end_date)

if data:
    df = pd.DataFrame(data)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')

    # Extract values
    df['pickup_value'] = df.apply(lambda row: row.get('models', {}).get('pickup', {}).get('value'), axis=1)
    df['xgboost_value'] = df.apply(lambda row: row.get('models', {}).get('xgboost', {}).get('value'), axis=1)
    df['current_otb'] = df.apply(lambda row: row.get('current_otb'), axis=1)
    df['prior_year_otb'] = df.apply(lambda row: row.get('prior_year_otb'), axis=1)
    df['prior_year_actual'] = df.apply(lambda row: row.get('prior_year_actual'), axis=1)
    df['budget'] = df.apply(lambda row: row.get('budget'), axis=1)

    # Calculate days out from today
    df['days_out'] = (df['date'] - pd.Timestamp(date.today())).dt.days

    # Main chart - OTB vs Pickup Projection
    st.subheader("📊 On-the-Books vs Projections")
    st.caption("_Current bookings compared to model projections_")

    fig = go.Figure()

    # Pickup projection
    if df['pickup_value'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['pickup_value'],
            name='Pickup Projection',
            line=dict(color='#2ca02c', width=3),
            hovertemplate="<b>Pickup</b><br>Date: %{x|%a %d %b}<br>Projected: %{y:.1f}<extra></extra>"
        ))

    # XGBoost for comparison
    if df['xgboost_value'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['xgboost_value'],
            name='XGBoost Projection',
            line=dict(color='#ff7f0e', width=2, dash='dot'),
            hovertemplate="<b>XGBoost</b><br>Date: %{x|%a %d %b}<br>Projected: %{y:.1f}<extra></extra>"
        ))

    # Current OTB
    if df['current_otb'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['current_otb'],
            name='Current OTB',
            mode='markers+lines',
            line=dict(color='#9467bd', width=2),
            marker=dict(size=8, symbol='diamond'),
            hovertemplate="<b>OTB</b><br>Date: %{x|%a %d %b}<br>Booked: %{y:.1f}<extra></extra>"
        ))

    # Prior Year OTB (same lead time last year)
    if df['prior_year_otb'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['prior_year_otb'],
            name='Prior Year OTB',
            line=dict(color='#17becf', width=2, dash='dot'),
            hovertemplate="<b>PY OTB</b><br>Date: %{x|%a %d %b}<br>Last Year OTB: %{y:.1f}<extra></extra>"
        ))

    # Prior Year Actual (final outcome last year)
    if df['prior_year_actual'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['prior_year_actual'],
            name='Prior Year Actual',
            line=dict(color='#7f7f7f', width=1, dash='dashdot'),
            hovertemplate="<b>PY Actual</b><br>Date: %{x|%a %d %b}<br>Last Year Final: %{y:.1f}<extra></extra>"
        ))

    # Budget line
    if df['budget'].notna().any():
        fig.add_trace(go.Scatter(
            x=df['date'],
            y=df['budget'],
            name='Budget',
            line=dict(color='#d62728', width=1, dash='dash'),
            hovertemplate="<b>Budget</b><br>Date: %{x|%a %d %b}<br>Target: %{y:.1f}<extra></extra>"
        ))

    fig.add_vline(x=str(date.today()), line_dash="dot", line_color="gray")

    fig.update_layout(
        xaxis_title='Date',
        yaxis_title=metric.replace('_', ' ').title(),
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=450,
        hovermode='x unified',
        xaxis=dict(tickformat='%a %d %b')  # Shows "Mon 01 Feb"
    )

    st.plotly_chart(fig, use_container_width=True)

    # Pickup Details Section
    st.subheader("📋 Pickup Details by Date")

    # Filter to dates with pickup data
    pickup_df = df[df['pickup_value'].notna()][['date', 'days_out', 'current_otb', 'prior_year_otb', 'pickup_value', 'prior_year_actual', 'budget']].copy()

    if len(pickup_df) > 0:
        # Calculate pace vs prior year
        pickup_df['pace_pct'] = pickup_df.apply(
            lambda row: ((row['current_otb'] - row['prior_year_otb']) / row['prior_year_otb'] * 100)
            if row['prior_year_otb'] and row['prior_year_otb'] > 0 else None,
            axis=1
        )
        pickup_df['date'] = pickup_df['date'].dt.strftime('%a %d %b')
        pickup_df = pickup_df.rename(columns={
            'date': 'Date',
            'days_out': 'Days Out',
            'current_otb': 'Current OTB',
            'prior_year_otb': 'PY OTB',
            'pace_pct': 'Pace vs PY',
            'pickup_value': 'Pickup Proj',
            'prior_year_actual': 'PY Final',
            'budget': 'Budget'
        })

        st.dataframe(
            pickup_df.style.format({
                'Current OTB': '{:.0f}',
                'PY OTB': '{:.0f}',
                'Pace vs PY': '{:+.1f}%',
                'Pickup Proj': '{:.1f}',
                'PY Final': '{:.1f}',
                'Budget': '{:.1f}'
            }, na_rep='-'),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No pickup projections available for this date range.")

    # Lead Time Analysis
    st.subheader("📈 Pickup by Lead Time")

    with st.expander("ℹ️ Understanding Lead Time Patterns"):
        st.markdown("""
        **Lead Time** = Days between today and stay date

        - **Short lead (0-7 days)**: Walk-ins, last-minute bookers
        - **Medium lead (8-28 days)**: Planned leisure stays
        - **Long lead (29+ days)**: Business travel, events, groups

        Higher OTB at longer lead times suggests:
        - Strong advance demand
        - Groups or events booked
        - Confident pricing opportunity
        """)

    # Group by lead time buckets
    df['lead_bucket'] = pd.cut(
        df['days_out'],
        bins=[-1, 7, 14, 28, 60, 365],
        labels=['0-7d', '8-14d', '15-28d', '29-60d', '60d+']
    )

    if df['pickup_value'].notna().any():
        lead_summary = df.groupby('lead_bucket', observed=True).agg({
            'current_otb': 'mean',
            'prior_year_otb': 'mean',
            'pickup_value': 'mean',
            'prior_year_actual': 'mean'
        }).round(1)

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Average by Lead Time**")
            st.dataframe(lead_summary.rename(columns={
                'current_otb': 'Avg OTB',
                'prior_year_otb': 'Avg PY OTB',
                'pickup_value': 'Avg Pickup',
                'prior_year_actual': 'Avg PY Final'
            }), use_container_width=True)

        with col2:
            # Bar chart
            fig_lead = go.Figure()
            fig_lead.add_trace(go.Bar(
                x=lead_summary.index.astype(str),
                y=lead_summary['pickup_value'],
                name='Pickup Projection',
                marker_color='#2ca02c'
            ))
            if lead_summary['current_otb'].notna().any():
                fig_lead.add_trace(go.Bar(
                    x=lead_summary.index.astype(str),
                    y=lead_summary['current_otb'],
                    name='Current OTB',
                    marker_color='#9467bd'
                ))
            if lead_summary['prior_year_otb'].notna().any():
                fig_lead.add_trace(go.Bar(
                    x=lead_summary.index.astype(str),
                    y=lead_summary['prior_year_otb'],
                    name='Prior Year OTB',
                    marker_color='#17becf'
                ))
            fig_lead.update_layout(
                title='Avg Values by Lead Time',
                barmode='group',
                height=300
            )
            st.plotly_chart(fig_lead, use_container_width=True)

else:
    st.warning("""
    **No pickup data available.**

    The Pickup model requires:
    1. **OTB Snapshots**: Daily snapshots of current bookings for future dates
    2. **Historical Data**: At least 60 days of booking history
    3. **Pickup Curves**: Historical patterns of how bookings accumulate

    The pickup snapshot job runs daily at 5:30 AM. Once you have a few weeks of snapshots,
    the pickup model will start producing projections.
    """)

    st.markdown("---")
    st.subheader("📅 How the Pickup Model Works")

    st.markdown("""
    The Pickup model uses this process:

    1. **Daily Snapshot**: Each morning, we capture current OTB for the next 60 days
    2. **Compare to Prior Year**: Look at OTB at the same lead time last year
    3. **Calculate Pace**: Are we ahead or behind last year's booking pace?
    4. **Project Final**: Use prior year's pickup ratio to project the final outcome

    **Example Calculation:**

    ```
    Today: January 30
    Stay Date: February 15 (16 days out)

    Current OTB: 18 rooms
    Prior Year OTB (at 16 days out): 15 rooms
    Prior Year Final: 22 rooms

    Pace: +20% ahead of prior year
    Pickup Ratio: 22 / 15 = 1.47

    Projected Final: 18 × 1.47 = 26 rooms
    ```
    """)

# Export
st.markdown("---")
if data:
    csv = df.to_csv(index=False)
    st.download_button(
        label="📥 Export Pickup Data",
        data=csv,
        file_name=f"pickup_analysis_{metric}_{start_date}_{end_date}.csv",
        mime="text/csv"
    )
