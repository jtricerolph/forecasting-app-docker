"""
Daily Forecast Page
Shows daily forecasts with all models side-by-side
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
from components.auth import require_auth

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Daily Forecast", page_icon="📅", layout="wide")

# Require authentication
require_auth()

st.title("📅 Daily Forecast")
st.markdown("View daily forecasts from all models with confidence intervals")

# Date range selector
col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    start_date = st.date_input("From", date.today())
with col2:
    end_date = st.date_input("To", date.today() + timedelta(days=14))
with col3:
    metric = st.selectbox("Metric", [
        "hotel_occupancy_pct",
        "hotel_guests",
        "resos_dinner_covers",
        "resos_lunch_covers",
        "hotel_adr",
        "hotel_arrivals"
    ])

st.markdown("---")

# Sample data for visualization
dates = pd.date_range(start=start_date, end=end_date, freq='D')
n = len(dates)

# Generate sample forecast data
import numpy as np
np.random.seed(42)

base = 80 if 'occupancy' in metric else 120 if 'covers' in metric else 150

df = pd.DataFrame({
    'Date': dates,
    'Prophet': base + np.random.randn(n) * 5 + np.sin(np.arange(n) * 0.5) * 10,
    'Prophet_Lower': None,
    'Prophet_Upper': None,
    'XGBoost': base + np.random.randn(n) * 5 + np.sin(np.arange(n) * 0.5) * 8,
    'Pickup': base + np.random.randn(n) * 4 + np.sin(np.arange(n) * 0.5) * 12,
    'Current_OTB': None,
    'Budget': [base - 5] * n
})

# Add confidence intervals for Prophet
df['Prophet_Lower'] = df['Prophet'] - 8
df['Prophet_Upper'] = df['Prophet'] + 8

# Add current OTB for first week
for i in range(min(7, n)):
    df.loc[i, 'Current_OTB'] = df.loc[i, 'Prophet'] * (0.6 + i * 0.05)

# Main forecast chart with confidence intervals
st.subheader("📈 Forecast Comparison")

fig = go.Figure()

# Prophet with confidence interval
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Prophet_Upper'],
    mode='lines', line=dict(width=0),
    showlegend=False, name='Prophet Upper'
))
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Prophet_Lower'],
    mode='lines', line=dict(width=0),
    fill='tonexty', fillcolor='rgba(31, 119, 180, 0.2)',
    showlegend=False, name='Prophet Lower'
))
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Prophet'],
    name='Prophet', line=dict(color='#1f77b4', width=3)
))

# Other models
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['XGBoost'],
    name='XGBoost', line=dict(color='#ff7f0e', width=2)
))
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Pickup'],
    name='Pickup', line=dict(color='#2ca02c', width=2)
))

# Current OTB
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Current_OTB'],
    name='Current OTB', mode='markers',
    marker=dict(color='#9467bd', size=10, symbol='diamond')
))

# Budget line
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Budget'],
    name='Budget', line=dict(color='#d62728', width=2, dash='dash')
))

fig.update_layout(
    title=f'{metric.replace("_", " ").title()} - Daily Forecast',
    xaxis_title='Date',
    yaxis_title='Value',
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
    height=500,
    hovermode='x unified'
)

st.plotly_chart(fig, use_container_width=True)

# Data table
st.subheader("📊 Forecast Data")

display_df = df[['Date', 'Prophet', 'XGBoost', 'Pickup', 'Current_OTB', 'Budget']].copy()
display_df['Date'] = display_df['Date'].dt.strftime('%a %d %b')
display_df = display_df.round(1)

# Add day of week coloring
st.dataframe(
    display_df.style.format({
        'Prophet': '{:.1f}',
        'XGBoost': '{:.1f}',
        'Pickup': '{:.1f}',
        'Current_OTB': '{:.1f}',
        'Budget': '{:.1f}'
    }),
    use_container_width=True,
    hide_index=True,
    height=400
)

# Summary stats
st.subheader("📋 Summary")

col1, col2, col3, col4 = st.columns(4)

with col1:
    avg_prophet = df['Prophet'].mean()
    st.metric("Avg Prophet Forecast", f"{avg_prophet:.1f}")

with col2:
    avg_xgb = df['XGBoost'].mean()
    st.metric("Avg XGBoost Forecast", f"{avg_xgb:.1f}")

with col3:
    avg_pickup = df['Pickup'].mean()
    st.metric("Avg Pickup Forecast", f"{avg_pickup:.1f}")

with col4:
    avg_budget = df['Budget'].mean()
    variance = ((avg_prophet - avg_budget) / avg_budget) * 100
    st.metric("Avg vs Budget", f"{variance:+.1f}%")

# Export
st.markdown("---")
col1, col2 = st.columns([1, 4])
with col1:
    if st.button("📥 Export Data"):
        csv = df.to_csv(index=False)
        st.download_button(
            label="Download CSV",
            data=csv,
            file_name=f"forecast_{metric}_{start_date}_{end_date}.csv",
            mime="text/csv"
        )
