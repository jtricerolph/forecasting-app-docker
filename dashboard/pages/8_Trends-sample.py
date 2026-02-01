"""
Trends Page
Historical patterns and seasonality visualization
"""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.auth import require_auth

st.set_page_config(page_title="Trends", page_icon="📈", layout="wide")

# Require authentication
require_auth()

st.title("📈 Historical Trends")
st.markdown("Analyze historical patterns and seasonality")

# Metric selector
metric = st.selectbox("Select Metric", [
    "hotel_occupancy_pct",
    "resos_dinner_covers",
    "resos_lunch_covers",
    "hotel_adr",
    "hotel_guests"
])

st.markdown("---")

# Generate historical data
np.random.seed(42)
dates = pd.date_range(end=date.today(), periods=365, freq='D')

base = 80 if 'occupancy' in metric else 120 if 'covers' in metric else 150

# Create seasonal pattern
values = []
for i, d in enumerate(dates):
    # Yearly seasonality (peak in summer)
    yearly = np.sin((d.dayofyear - 100) / 365 * 2 * np.pi) * 15

    # Weekly seasonality (higher on weekends)
    weekly = 5 if d.weekday() >= 4 else -3

    # Random noise
    noise = np.random.randn() * 5

    value = base + yearly + weekly + noise
    values.append(value)

df = pd.DataFrame({'Date': dates, 'Value': values})
df['DayOfWeek'] = df['Date'].dt.day_name()
df['Month'] = df['Date'].dt.month_name()
df['MonthNum'] = df['Date'].dt.month
df['Week'] = df['Date'].dt.isocalendar().week

# Trend chart
st.subheader("📊 Historical Trend (Last 12 Months)")

fig = go.Figure()

# Raw data
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Value'],
    name='Daily Values',
    line=dict(color='#1f77b4', width=1),
    opacity=0.5
))

# 7-day moving average
df['MA7'] = df['Value'].rolling(7).mean()
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['MA7'],
    name='7-day MA',
    line=dict(color='#ff7f0e', width=2)
))

# 30-day moving average
df['MA30'] = df['Value'].rolling(30).mean()
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['MA30'],
    name='30-day MA',
    line=dict(color='#d62728', width=2)
))

fig.update_layout(
    title=f'{metric.replace("_", " ").title()} - Historical Trend',
    xaxis_title='Date',
    yaxis_title='Value',
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    height=400
)

st.plotly_chart(fig, use_container_width=True)

# Seasonality analysis
st.subheader("📅 Seasonality Patterns")

col1, col2 = st.columns(2)

with col1:
    # Day of week pattern
    dow_avg = df.groupby('DayOfWeek')['Value'].mean().reindex([
        'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'
    ])

    fig_dow = go.Figure()
    fig_dow.add_trace(go.Bar(
        x=dow_avg.index,
        y=dow_avg.values,
        marker_color=['#1f77b4' if d in ['Friday', 'Saturday', 'Sunday'] else '#aec7e8'
                      for d in dow_avg.index],
        text=dow_avg.values.round(1),
        textposition='outside'
    ))
    fig_dow.update_layout(
        title='Average by Day of Week',
        xaxis_title='Day',
        yaxis_title='Average Value',
        height=300
    )
    st.plotly_chart(fig_dow, use_container_width=True)

with col2:
    # Monthly pattern
    month_avg = df.groupby('MonthNum')['Value'].mean()
    month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                   'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    fig_month = go.Figure()
    fig_month.add_trace(go.Bar(
        x=month_names,
        y=month_avg.values,
        marker_color=['#2ca02c' if v > month_avg.mean() else '#d62728' for v in month_avg.values],
        text=month_avg.values.round(1),
        textposition='outside'
    ))
    fig_month.update_layout(
        title='Average by Month',
        xaxis_title='Month',
        yaxis_title='Average Value',
        height=300
    )
    st.plotly_chart(fig_month, use_container_width=True)

# Heatmap
st.subheader("🗓️ Weekly Heatmap")

# Create pivot table for heatmap
df['WeekDay'] = df['Date'].dt.weekday
last_12_weeks = df.tail(84)  # ~12 weeks

pivot = last_12_weeks.pivot_table(
    values='Value',
    index='WeekDay',
    columns='Week',
    aggfunc='mean'
)

day_labels = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

fig_heat = px.imshow(
    pivot,
    labels=dict(x="Week", y="Day", color="Value"),
    y=day_labels,
    color_continuous_scale='RdYlGn',
    aspect='auto'
)
fig_heat.update_layout(
    title='Value Heatmap by Day and Week',
    height=300
)

st.plotly_chart(fig_heat, use_container_width=True)

# Year over year comparison
st.subheader("📊 Year-over-Year Comparison")

# Generate YoY data
this_year = df.tail(90)  # Last 3 months
last_year = df.head(90).copy()  # Simulated last year
last_year['Date'] = last_year['Date'] + timedelta(days=365)
last_year['Value'] = last_year['Value'] * 0.95  # Slight growth

fig_yoy = go.Figure()
fig_yoy.add_trace(go.Scatter(
    x=this_year['Date'], y=this_year['Value'],
    name='This Year',
    line=dict(color='#1f77b4', width=2)
))
fig_yoy.add_trace(go.Scatter(
    x=last_year['Date'], y=last_year['Value'],
    name='Last Year',
    line=dict(color='#ff7f0e', width=2, dash='dash')
))
fig_yoy.update_layout(
    title='Year-over-Year Comparison (Last 90 Days)',
    xaxis_title='Date',
    yaxis_title='Value',
    height=350,
    legend=dict(orientation='h', yanchor='bottom', y=1.02)
)

st.plotly_chart(fig_yoy, use_container_width=True)

# Summary stats
st.subheader("📋 Summary Statistics")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Average", f"{df['Value'].mean():.1f}")
with col2:
    st.metric("Std Dev", f"{df['Value'].std():.1f}")
with col3:
    st.metric("Maximum", f"{df['Value'].max():.1f}")
with col4:
    st.metric("Minimum", f"{df['Value'].min():.1f}")
