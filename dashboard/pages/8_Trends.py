"""
Trends Page
Multi-week trending and seasonality patterns
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

st.set_page_config(page_title="Trends", page_icon="📊", layout="wide")
require_auth()

st.title("📊 Trends & Patterns")

# Help expander
with st.expander("ℹ️ Understanding Trend Analysis", expanded=False):
    st.markdown("""
    ### What This Page Shows

    Analyze long-term trends and patterns in your data to understand:

    - **Seasonality**: How metrics change by month/quarter
    - **Day-of-week patterns**: Weekday vs weekend differences
    - **Year-over-year**: Comparison to the same period last year
    - **Trend direction**: Is performance improving or declining?

    ### Key Pattern Types

    | Pattern | Description |
    |---------|-------------|
    | **Seasonal** | Predictable changes by time of year (summer peak, winter low) |
    | **Weekly** | Recurring patterns within each week (Sat/Sun higher than Tue/Wed) |
    | **Trend** | Underlying direction independent of seasonality |
    | **Cyclical** | Longer-term patterns (economic cycles, multi-year trends) |

    ### Using Trends for Planning

    - **Staffing**: Match labor to expected demand patterns
    - **Pricing**: Adjust rates based on demand seasonality
    - **Marketing**: Time promotions for shoulder seasons
    - **Forecasting**: Validate model predictions against known patterns
    """)

st.markdown("---")

@st.cache_data(ttl=60)
def fetch_historical_data(from_date, to_date):
    """Fetch historical data for trend analysis"""
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
        st.error(f"Error fetching data: {e}")
        return []

# Controls
col1, col2 = st.columns([1, 1])

with col1:
    lookback_months = st.slider(
        "Analysis Period (Months)",
        3, 24, 12,
        help="Number of months of historical data to analyze"
    )

with col2:
    primary_metric = st.selectbox(
        "Primary Metric",
        ["occupancy_pct", "room_revenue", "adr", "total_guests", "dinner_covers", "lunch_covers"],
        format_func=lambda x: {
            "occupancy_pct": "Occupancy %",
            "room_revenue": "Room Revenue",
            "adr": "Average Daily Rate",
            "total_guests": "Total Guests",
            "dinner_covers": "Dinner Covers",
            "lunch_covers": "Lunch Covers"
        }.get(x, x),
        help="Select the primary metric to analyze"
    )

st.markdown("---")

# Fetch data
end_date = date.today()
start_date = end_date - timedelta(days=lookback_months * 30)
data = fetch_historical_data(start_date, end_date)

if not data:
    st.warning("No historical data available for trend analysis.")
    st.stop()

df = pd.DataFrame(data)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date')

# Add time components
df['month'] = df['date'].dt.month
df['month_name'] = df['date'].dt.strftime('%b')
df['day_of_week'] = df['date'].dt.dayofweek
df['day_name'] = df['date'].dt.strftime('%a')
df['week'] = df['date'].dt.isocalendar().week
df['year'] = df['date'].dt.year
df['quarter'] = df['date'].dt.quarter

metric_name = {
    "occupancy_pct": "Occupancy %",
    "room_revenue": "Room Revenue",
    "adr": "ADR",
    "total_guests": "Guests",
    "dinner_covers": "Dinner Covers",
    "lunch_covers": "Lunch Covers"
}.get(primary_metric, primary_metric)

# ============================================
# OVERALL TREND
# ============================================
st.subheader(f"📈 {metric_name} - Overall Trend")

fig_trend = go.Figure()

# Daily values
fig_trend.add_trace(go.Scatter(
    x=df['date'],
    y=df[primary_metric],
    name='Daily',
    mode='lines',
    line=dict(color='lightblue', width=1),
    opacity=0.5
))

# 7-day moving average
if len(df) >= 7:
    df['ma7'] = df[primary_metric].rolling(7).mean()
    fig_trend.add_trace(go.Scatter(
        x=df['date'],
        y=df['ma7'],
        name='7-Day Avg',
        line=dict(color='#1f77b4', width=2)
    ))

# 30-day moving average
if len(df) >= 30:
    df['ma30'] = df[primary_metric].rolling(30).mean()
    fig_trend.add_trace(go.Scatter(
        x=df['date'],
        y=df['ma30'],
        name='30-Day Avg',
        line=dict(color='#ff7f0e', width=2)
    ))

fig_trend.update_layout(
    xaxis_title='Date',
    yaxis_title=metric_name,
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    height=400,
    hovermode='x unified'
)

st.plotly_chart(fig_trend, use_container_width=True)

# Trend direction indicator
if len(df) >= 30:
    recent_avg = df['ma30'].iloc[-1]
    earlier_avg = df['ma30'].iloc[-30] if len(df) >= 60 else df['ma30'].iloc[0]
    trend_change = ((recent_avg - earlier_avg) / earlier_avg * 100) if earlier_avg != 0 else 0

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "30-Day Trend",
            f"{trend_change:+.1f}%",
            delta="Improving" if trend_change > 0 else "Declining" if trend_change < 0 else "Stable"
        )
    with col2:
        st.metric("Current 30-Day Avg", f"{recent_avg:.1f}")
    with col3:
        overall_avg = df[primary_metric].mean()
        st.metric("Period Average", f"{overall_avg:.1f}")

# ============================================
# DAY OF WEEK PATTERN
# ============================================
st.markdown("---")
st.subheader("📅 Day of Week Pattern")
st.caption("_Average performance by day of the week_")

dow_order = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
dow_stats = df.groupby('day_name')[primary_metric].agg(['mean', 'std', 'count']).round(2)
dow_stats = dow_stats.reindex(dow_order)

col1, col2 = st.columns([2, 1])

with col1:
    fig_dow = go.Figure()
    fig_dow.add_trace(go.Bar(
        x=dow_stats.index,
        y=dow_stats['mean'],
        name='Average',
        marker_color='#1f77b4',
        error_y=dict(type='data', array=dow_stats['std'], visible=True),
        hovertemplate="<b>%{x}</b><br>Avg: %{y:.1f}<extra></extra>"
    ))

    # Add overall average line
    overall_mean = df[primary_metric].mean()
    fig_dow.add_hline(y=overall_mean, line_dash="dash", line_color="red",
                      annotation_text=f"Overall Avg: {overall_mean:.1f}")

    fig_dow.update_layout(
        xaxis_title='Day of Week',
        yaxis_title=f'Avg {metric_name}',
        height=350
    )
    st.plotly_chart(fig_dow, use_container_width=True)

with col2:
    st.markdown("**Day of Week Stats**")
    display_dow = dow_stats.copy()
    display_dow.columns = ['Average', 'Std Dev', 'Count']
    st.dataframe(display_dow.style.format({
        'Average': '{:.1f}',
        'Std Dev': '{:.1f}'
    }), use_container_width=True)

    # Best/worst days
    best_day = dow_stats['mean'].idxmax()
    worst_day = dow_stats['mean'].idxmin()
    st.success(f"📈 Best: **{best_day}** ({dow_stats.loc[best_day, 'mean']:.1f})")
    st.warning(f"📉 Lowest: **{worst_day}** ({dow_stats.loc[worst_day, 'mean']:.1f})")

# ============================================
# MONTHLY SEASONALITY
# ============================================
st.markdown("---")
st.subheader("📆 Monthly Seasonality")
st.caption("_Average performance by month_")

month_order = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
monthly_stats = df.groupby('month_name')[primary_metric].agg(['mean', 'count']).round(2)
monthly_stats = monthly_stats.reindex(month_order)
monthly_stats = monthly_stats.dropna()

if len(monthly_stats) > 0:
    fig_month = go.Figure()
    fig_month.add_trace(go.Bar(
        x=monthly_stats.index,
        y=monthly_stats['mean'],
        marker_color=px.colors.sequential.Blues_r[:len(monthly_stats)],
        hovertemplate="<b>%{x}</b><br>Avg: %{y:.1f}<br>Days: %{customdata}<extra></extra>",
        customdata=monthly_stats['count']
    ))

    fig_month.add_hline(y=overall_mean, line_dash="dash", line_color="red",
                        annotation_text=f"Overall: {overall_mean:.1f}")

    fig_month.update_layout(
        xaxis_title='Month',
        yaxis_title=f'Avg {metric_name}',
        height=350
    )
    st.plotly_chart(fig_month, use_container_width=True)

    # Season analysis
    with st.expander("ℹ️ Seasonal Insights"):
        peak_months = monthly_stats.nlargest(3, 'mean')
        low_months = monthly_stats.nsmallest(3, 'mean')

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Peak Season**")
            for month, row in peak_months.iterrows():
                st.markdown(f"- {month}: {row['mean']:.1f}")

        with col2:
            st.markdown("**Low Season**")
            for month, row in low_months.iterrows():
                st.markdown(f"- {month}: {row['mean']:.1f}")

# ============================================
# YEAR OVER YEAR (if enough data)
# ============================================
years = df['year'].unique()
if len(years) >= 2:
    st.markdown("---")
    st.subheader("📅 Year-over-Year Comparison")

    # Monthly comparison by year
    yoy_data = df.groupby(['year', 'month_name'])[primary_metric].mean().reset_index()
    yoy_pivot = yoy_data.pivot(index='month_name', columns='year', values=primary_metric)
    yoy_pivot = yoy_pivot.reindex(month_order).dropna(how='all')

    fig_yoy = go.Figure()
    for year in sorted(years):
        if year in yoy_pivot.columns:
            fig_yoy.add_trace(go.Scatter(
                x=yoy_pivot.index,
                y=yoy_pivot[year],
                name=str(year),
                mode='lines+markers'
            ))

    fig_yoy.update_layout(
        xaxis_title='Month',
        yaxis_title=f'Avg {metric_name}',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=350
    )
    st.plotly_chart(fig_yoy, use_container_width=True)

# ============================================
# HEATMAP
# ============================================
st.markdown("---")
st.subheader("🗓️ Day-of-Week by Month Heatmap")
st.caption("_Spot patterns in demand by day and month_")

# Create pivot for heatmap
heatmap_data = df.groupby(['month_name', 'day_name'])[primary_metric].mean().reset_index()
heatmap_pivot = heatmap_data.pivot(index='month_name', columns='day_name', values=primary_metric)
heatmap_pivot = heatmap_pivot.reindex(index=month_order, columns=dow_order).dropna(how='all')

if len(heatmap_pivot) > 0:
    fig_heat = px.imshow(
        heatmap_pivot,
        labels=dict(x="Day", y="Month", color=metric_name),
        color_continuous_scale='RdYlGn',
        aspect='auto'
    )
    fig_heat.update_layout(height=400)
    st.plotly_chart(fig_heat, use_container_width=True)

# Export
st.markdown("---")
csv = df.to_csv(index=False)
st.download_button(
    label="📥 Export Trend Data",
    data=csv,
    file_name=f"trends_{primary_metric}_{lookback_months}months.csv",
    mime="text/csv"
)
