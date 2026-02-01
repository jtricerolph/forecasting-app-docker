"""
Weekly Summary Page
Weekly aggregated historical data with trends
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

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

st.set_page_config(page_title="Weekly Summary", page_icon="📊", layout="wide")

# Require authentication
require_auth()

st.title("📊 Weekly Summary")

# Help expander
with st.expander("ℹ️ Understanding This Page", expanded=False):
    st.markdown("""
    ### What This Page Shows
    This page aggregates daily data into **weekly summaries** to help identify trends and patterns.

    ### Key Concepts

    **Occupancy Calculations:**
    - **Occ % (Total)**: Occupied rooms ÷ Total physical rooms (25) × 100
    - **Occ % (Avail)**: Occupied rooms ÷ Available rooms × 100 (accounts for maintenance)

    **Data Coverage:**
    - The "Days" column shows how many days in each week have actual data
    - Format: "actual/total" (e.g., "5/7" means 5 days of data in a 7-day week)
    - Days without data are counted as 0 occupancy

    **Week-over-Week Change:**
    - Shows the change from the previous week
    - Positive = improvement, Negative = decline
    - Useful for spotting trends

    ### Data Sources
    - **Hotel Data**: Newbook PMS (bookings, occupancy, revenue)
    - **Restaurant Data**: Resos booking system (covers)
    """)

    st.markdown("### Metric Definitions")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Room Nights Sold**: Total rooms occupied across the week

        **Room Revenue (Net)**: Sum of room tariffs excluding VAT

        **ADR (Net)**: Average Daily Rate = Revenue ÷ Rooms Sold
        """)
    with col2:
        st.markdown("""
        **Total Guests**: Sum of all guests staying

        **Dinner/Lunch Covers**: Restaurant bookings from Resos

        **4-Week Avg**: Rolling average showing trend direction
        """)

# Controls
col1, col2 = st.columns([1, 3])
with col1:
    weeks = st.slider(
        "Weeks to show",
        4, 26, 12,
        help="Number of weeks of historical data to display"
    )
with col2:
    metrics = st.multiselect(
        "Metrics to chart",
        ["Occupancy", "Room Revenue", "ADR", "Dinner Covers", "Lunch Covers", "Guests"],
        default=["Occupancy", "Room Revenue"],
        help="Select which metrics to show in the trend charts"
    )

st.markdown("---")

# Fetch real data
@st.cache_data(ttl=60)
def fetch_weekly_data(weeks_back):
    try:
        end_date = date.today()
        start_date = end_date - timedelta(weeks=weeks_back)

        response = httpx.get(
            f"{BACKEND_URL}/historical/summary",
            params={"from_date": str(start_date), "to_date": str(end_date)},
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to fetch data: {response.status_code}")
            return []
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return []

data = fetch_weekly_data(weeks)

if not data:
    st.warning("No data available for the selected period")
    st.stop()

# Convert to DataFrame
df = pd.DataFrame(data)
df['date'] = pd.to_datetime(df['date'])

# Determine hotel room capacity from data (use mode of total_rooms)
room_capacity = int(df['total_rooms'].mode().iloc[0]) if len(df) > 0 else 25

# Generate complete date range and fill missing dates
end_date = pd.Timestamp(date.today())
start_date = end_date - pd.Timedelta(weeks=weeks)
all_dates = pd.date_range(start=start_date, end=end_date, freq='D')

# Create complete dataframe with all dates
complete_df = pd.DataFrame({'date': all_dates})
complete_df = complete_df.merge(df, on='date', how='left')

# Fill missing dates with room capacity and 0 for other values
complete_df['total_rooms'] = complete_df['total_rooms'].fillna(room_capacity)
complete_df['available_rooms'] = complete_df['available_rooms'].fillna(complete_df['total_rooms'])
complete_df['occupied_rooms'] = complete_df['occupied_rooms'].fillna(0)
complete_df['room_revenue'] = complete_df['room_revenue'].fillna(0)
complete_df['adr'] = complete_df['adr'].fillna(0)
complete_df['agr'] = complete_df['agr'].fillna(0)
complete_df['revpar'] = complete_df['revpar'].fillna(0)
complete_df['total_guests'] = complete_df['total_guests'].fillna(0)
complete_df['arrival_count'] = complete_df['arrival_count'].fillna(0)
complete_df['lunch_covers'] = complete_df['lunch_covers'].fillna(0)
complete_df['dinner_covers'] = complete_df['dinner_covers'].fillna(0)

# Track which days have actual data vs filled
complete_df['has_data'] = complete_df['day_of_week'].notna()

# Add week grouping columns
complete_df['week_start'] = complete_df['date'].dt.to_period('W-MON').dt.start_time
complete_df['week_label'] = complete_df['week_start'].dt.strftime('%d %b')

# Aggregate by week
weekly_df = complete_df.groupby(['week_start', 'week_label']).agg({
    'total_rooms': 'sum',
    'available_rooms': 'sum',
    'occupied_rooms': 'sum',
    'has_data': 'sum',
    'room_revenue': 'sum',
    'adr': lambda x: x[x > 0].mean() if (x > 0).any() else 0,
    'agr': lambda x: x[x > 0].mean() if (x > 0).any() else 0,
    'revpar': lambda x: x[x > 0].mean() if (x > 0).any() else 0,
    'total_guests': 'sum',
    'arrival_count': 'sum',
    'lunch_covers': 'sum',
    'dinner_covers': 'sum'
}).reset_index()

weekly_df = weekly_df.rename(columns={'has_data': 'days_with_data'})

# Calculate days in each week
weekly_df['days'] = weekly_df.apply(
    lambda row: len(pd.date_range(start=row['week_start'],
                                   end=min(row['week_start'] + pd.Timedelta(days=6), end_date),
                                   freq='D')), axis=1)

# Calculate occupancy percentages
weekly_df['occ_total_pct'] = (weekly_df['occupied_rooms'] / weekly_df['total_rooms'] * 100).fillna(0)
weekly_df['occ_avail_pct'] = (weekly_df['occupied_rooms'] / weekly_df['available_rooms'] * 100).fillna(0)
weekly_df['occupancy_pct'] = weekly_df['occ_avail_pct']

weekly_df = weekly_df.sort_values('week_start')

# Metric mapping
metric_config = {
    "Occupancy": {
        "col": "occupancy_pct",
        "unit": "%",
        "format": ".1f",
        "agg": "mean",
        "description": "Average occupancy rate for the week (rooms sold ÷ available rooms)"
    },
    "Room Revenue": {
        "col": "room_revenue",
        "unit": "£",
        "format": ",.0f",
        "agg": "sum",
        "description": "Total accommodation revenue for the week (net of VAT)"
    },
    "ADR": {
        "col": "adr",
        "unit": "£",
        "format": ",.2f",
        "agg": "mean",
        "description": "Average Daily Rate - average revenue per occupied room"
    },
    "Dinner Covers": {
        "col": "dinner_covers",
        "unit": "",
        "format": ",.0f",
        "agg": "sum",
        "description": "Total dinner covers from Resos bookings"
    },
    "Lunch Covers": {
        "col": "lunch_covers",
        "unit": "",
        "format": ",.0f",
        "agg": "sum",
        "description": "Total lunch covers from Resos bookings"
    },
    "Guests": {
        "col": "total_guests",
        "unit": "",
        "format": ",.0f",
        "agg": "sum",
        "description": "Total guests staying during the week"
    }
}

# Weekly charts for selected metrics
st.subheader("📈 Weekly Trends")

for metric in metrics:
    if metric not in metric_config:
        continue

    config = metric_config[metric]

    # Metric description tooltip
    st.caption(f"_{config['description']}_")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=weekly_df['week_label'],
        y=weekly_df[config['col']],
        name=metric,
        marker_color='#1f77b4',
        text=weekly_df[config['col']].apply(lambda x: f"{x:{config['format']}}"),
        textposition='outside',
        hovertemplate=f"<b>%{{x}}</b><br>{metric}: %{{y:{config['format']}}}<extra></extra>"
    ))

    # Add trend line (4-week moving average if enough data)
    if len(weekly_df) >= 4:
        weekly_df[f'{config["col"]}_ma4'] = weekly_df[config['col']].rolling(window=4).mean()
        fig.add_trace(go.Scatter(
            x=weekly_df['week_label'],
            y=weekly_df[f'{config["col"]}_ma4'],
            name='4-Week Avg',
            mode='lines',
            line=dict(color='#ff7f0e', width=3),
            hovertemplate=f"4-Week Avg: %{{y:{config['format']}}}<extra></extra>"
        ))

    unit_label = f" ({config['unit']})" if config['unit'] else ""
    fig.update_layout(
        title=f'{metric} - Weekly{unit_label}',
        xaxis_title='Week Starting',
        yaxis_title=metric,
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=350,
        margin=dict(l=0, r=0, t=60, b=0)
    )

    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Summary table
st.subheader("📋 Weekly Data Table")

with st.expander("ℹ️ Table Column Explanations", expanded=False):
    st.markdown("""
    | Column | Description |
    |--------|-------------|
    | **Week** | Week starting date (Monday) |
    | **Days** | Days with data / Total days in week |
    | **Sold** | Room nights sold during the week |
    | **Avail** | Available room nights (after maintenance) |
    | **Occ % (Total)** | Occupancy vs total physical rooms |
    | **Occ % (Avail)** | Occupancy vs available rooms |
    | **Revenue (Net)** | Total room revenue excluding VAT |
    | **ADR (Net)** | Average daily rate excluding VAT |
    | **Guests** | Total guests staying |
    | **Dinner/Lunch** | Restaurant covers from Resos |
    """)

# Create data coverage indicator
weekly_df['data_coverage'] = weekly_df.apply(
    lambda row: f"{int(row['days_with_data'])}/{int(row['days'])}", axis=1)

display_cols = ['week_label', 'data_coverage', 'occupied_rooms', 'available_rooms',
                'occ_total_pct', 'occ_avail_pct', 'room_revenue',
                'adr', 'total_guests', 'dinner_covers', 'lunch_covers']
display_df = weekly_df[display_cols].copy()
display_df.columns = ['Week', 'Days', 'Sold', 'Avail',
                      'Occ % (Total)', 'Occ % (Avail)', 'Revenue (Net)',
                      'ADR (Net)', 'Guests', 'Dinner', 'Lunch']

st.dataframe(
    display_df.style.format({
        'Occ % (Total)': '{:.1f}%',
        'Occ % (Avail)': '{:.1f}%',
        'Revenue (Net)': '£{:,.0f}',
        'ADR (Net)': '£{:,.2f}',
        'Sold': '{:,.0f}',
        'Avail': '{:,.0f}',
        'Guests': '{:,.0f}',
        'Dinner': '{:,.0f}',
        'Lunch': '{:,.0f}'
    }),
    use_container_width=True,
    hide_index=True
)

# Period totals
st.subheader("📊 Period Summary")
st.caption(f"_Aggregated totals for the past {weeks} weeks_")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    avg_occ = weekly_df['occupancy_pct'].mean()
    st.metric(
        "Avg Occupancy",
        f"{avg_occ:.1f}%",
        help="Average weekly occupancy rate across the period"
    )

with col2:
    total_revenue = weekly_df['room_revenue'].sum()
    st.metric(
        "Total Revenue (Net)",
        f"£{total_revenue:,.0f}",
        help="Sum of all room revenue excluding VAT"
    )

with col3:
    avg_adr = weekly_df['adr'].mean()
    st.metric(
        "Avg ADR (Net)",
        f"£{avg_adr:,.2f}",
        help="Average daily rate excluding VAT"
    )

with col4:
    total_dinner = weekly_df['dinner_covers'].sum()
    st.metric(
        "Total Dinner Covers",
        f"{total_dinner:,.0f}",
        help="Total dinner covers from Resos"
    )

with col5:
    total_guests = weekly_df['total_guests'].sum()
    st.metric(
        "Total Guests",
        f"{total_guests:,.0f}",
        help="Total guests who stayed during the period"
    )

# Week-over-week comparison
st.markdown("---")
st.subheader("📈 Week-over-Week Change")
st.caption("_Percentage change compared to the previous week_")

if len(weekly_df) >= 2:
    wow_data = []
    for i in range(1, len(weekly_df)):
        prev_week = weekly_df.iloc[i-1]
        curr_week = weekly_df.iloc[i]

        wow_data.append({
            'Week': curr_week['week_label'],
            'Occ % Change': curr_week['occupancy_pct'] - prev_week['occupancy_pct'],
            'Revenue Change': ((curr_week['room_revenue'] - prev_week['room_revenue']) / prev_week['room_revenue'] * 100) if prev_week['room_revenue'] > 0 else 0,
            'Dinner Change': ((curr_week['dinner_covers'] - prev_week['dinner_covers']) / prev_week['dinner_covers'] * 100) if prev_week['dinner_covers'] > 0 else 0
        })

    wow_df = pd.DataFrame(wow_data)

    fig = go.Figure()

    colors = {'Occ % Change': '#1f77b4', 'Revenue Change': '#2ca02c', 'Dinner Change': '#ff7f0e'}

    for col, color in colors.items():
        fig.add_trace(go.Bar(
            x=wow_df['Week'],
            y=wow_df[col],
            name=col.replace(' Change', ''),
            marker_color=color,
            hovertemplate=f"<b>%{{x}}</b><br>{col.replace(' Change', '')}: %{{y:+.1f}}%<extra></extra>"
        ))

    fig.update_layout(
        title='Week-over-Week % Change',
        xaxis_title='Week',
        yaxis_title='Change (%)',
        barmode='group',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=350
    )

    # Add zero line
    fig.add_hline(y=0, line_dash="dot", line_color="gray")

    st.plotly_chart(fig, use_container_width=True)

    with st.expander("ℹ️ Interpreting Week-over-Week Changes", expanded=False):
        st.markdown("""
        - **Positive values**: Improvement compared to previous week
        - **Negative values**: Decline compared to previous week
        - **Occupancy % Change**: Absolute percentage point change (e.g., 70% → 75% = +5%)
        - **Revenue/Dinner Change**: Relative percentage change (e.g., £10k → £12k = +20%)

        **Typical patterns to look for:**
        - Seasonal trends (summer peak, winter low)
        - Day-of-week effects (weekends vs weekdays)
        - Event-driven spikes
        """)

# Export
st.markdown("---")
col1, col2 = st.columns([1, 4])
with col1:
    csv = weekly_df.to_csv(index=False)
    st.download_button(
        label="📥 Export Weekly Data",
        data=csv,
        file_name=f"weekly_summary_{weeks}_weeks.csv",
        mime="text/csv"
    )
