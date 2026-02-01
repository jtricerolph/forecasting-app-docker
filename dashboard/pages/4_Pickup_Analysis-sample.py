"""
Pickup Analysis Page
Track booking pace and lead time patterns
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

st.set_page_config(page_title="Pickup Analysis", page_icon="📈", layout="wide")

# Require authentication
require_auth()

st.title("📈 Pickup Analysis")
st.markdown("Track booking pace vs prior year and historical pickup patterns")

# Controls
col1, col2 = st.columns(2)
with col1:
    metric = st.selectbox("Metric", [
        "hotel_occupancy_pct",
        "resos_dinner_covers",
        "resos_lunch_covers"
    ])
with col2:
    target_date = st.date_input("Target Date", date.today() + timedelta(days=14))

st.markdown("---")

# Pace comparison section
st.subheader("🏃 Pace vs Prior Year")

# Generate sample pace data
np.random.seed(42)
lead_times = [28, 21, 14, 7, 3, 1, 0]

base_value = 85 if 'occupancy' in metric else 140
final_actual = base_value + 8

pace_data = []
for lt in lead_times:
    current_otb = final_actual * (0.5 + (28 - lt) / 28 * 0.5) + np.random.randn() * 2
    prior_otb = final_actual * (0.45 + (28 - lt) / 28 * 0.5) + np.random.randn() * 2
    pace_pct = ((current_otb - prior_otb) / prior_otb) * 100 if prior_otb > 0 else 0

    pace_data.append({
        'Lead Time': f"{lt}d" if lt > 0 else "Final",
        'Lead_Days': lt,
        'Current Year OTB': current_otb,
        'Prior Year OTB': prior_otb,
        'Prior Year Final': final_actual - 5,
        'Pace (%)': pace_pct
    })

pace_df = pd.DataFrame(pace_data)

# Pace chart
col1, col2 = st.columns([2, 1])

with col1:
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=pace_df['Lead Time'],
        y=pace_df['Current Year OTB'],
        name='Current Year OTB',
        mode='lines+markers',
        line=dict(color='#1f77b4', width=3),
        marker=dict(size=10)
    ))

    fig.add_trace(go.Scatter(
        x=pace_df['Lead Time'],
        y=pace_df['Prior Year OTB'],
        name='Prior Year OTB',
        mode='lines+markers',
        line=dict(color='#ff7f0e', width=2, dash='dash'),
        marker=dict(size=8)
    ))

    fig.add_trace(go.Scatter(
        x=pace_df['Lead Time'],
        y=pace_df['Prior Year Final'],
        name='Prior Year Final',
        mode='lines',
        line=dict(color='#2ca02c', width=2, dash='dot')
    ))

    fig.update_layout(
        title=f'Booking Pace for {target_date.strftime("%d %b %Y")}',
        xaxis_title='Days Before Stay',
        yaxis_title=metric.replace('_', ' ').title(),
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)

with col2:
    # Pace indicators
    current_pace = pace_df[pace_df['Lead_Days'] == 14]['Pace (%)'].values[0]

    if current_pace > 5:
        st.success(f"**+{current_pace:.1f}%** ahead of last year's pace")
    elif current_pace < -5:
        st.error(f"**{current_pace:.1f}%** behind last year's pace")
    else:
        st.info(f"**{current_pace:+.1f}%** tracking with last year")

    st.markdown("---")

    st.metric("Current OTB", f"{pace_df[pace_df['Lead_Days'] == 14]['Current Year OTB'].values[0]:.0f}")
    st.metric("Prior Year (same point)", f"{pace_df[pace_df['Lead_Days'] == 14]['Prior Year OTB'].values[0]:.0f}")
    st.metric("Prior Year Final", f"{pace_df['Prior Year Final'].values[0]:.0f}")

# Pickup curve section
st.markdown("---")
st.subheader("📊 Historical Pickup Curves")

col1, col2 = st.columns(2)

with col1:
    dow = st.selectbox("Day of Week", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"])

with col2:
    season = st.selectbox("Season", ["Peak", "Shoulder", "Low"])

# Generate pickup curve data
curve_data = []
for lt in [60, 45, 30, 21, 14, 7, 3, 1]:
    pct = 40 + (60 - lt) / 60 * 60 + np.random.randn() * 3
    curve_data.append({
        'Days Out': lt,
        'Avg % of Final': min(100, pct),
        'Std Dev': 5 + np.random.rand() * 5
    })

curve_df = pd.DataFrame(curve_data)

fig_curve = go.Figure()

# Add confidence band
fig_curve.add_trace(go.Scatter(
    x=curve_df['Days Out'],
    y=curve_df['Avg % of Final'] + curve_df['Std Dev'],
    mode='lines', line=dict(width=0),
    showlegend=False
))
fig_curve.add_trace(go.Scatter(
    x=curve_df['Days Out'],
    y=curve_df['Avg % of Final'] - curve_df['Std Dev'],
    mode='lines', line=dict(width=0),
    fill='tonexty', fillcolor='rgba(31, 119, 180, 0.2)',
    showlegend=False
))

# Add main curve
fig_curve.add_trace(go.Scatter(
    x=curve_df['Days Out'],
    y=curve_df['Avg % of Final'],
    mode='lines+markers',
    name='Avg % of Final',
    line=dict(color='#1f77b4', width=3)
))

fig_curve.update_layout(
    title=f'Pickup Curve: {dow} in {season} Season',
    xaxis_title='Days Before Stay',
    yaxis_title='% of Final Value',
    xaxis=dict(autorange='reversed'),  # Show furthest out on left
    height=350
)

st.plotly_chart(fig_curve, use_container_width=True)

# Lead time analysis
st.markdown("---")
st.subheader("⏱️ Booking Lead Time Distribution")

# Generate lead time data
lead_time_data = np.abs(np.random.exponential(scale=14, size=500))

fig_hist = px.histogram(
    lead_time_data,
    nbins=30,
    title='Distribution of Booking Lead Times',
    labels={'value': 'Days Before Stay', 'count': 'Number of Bookings'}
)
fig_hist.update_layout(
    xaxis_title='Days Before Stay',
    yaxis_title='Number of Bookings',
    showlegend=False,
    height=300
)

st.plotly_chart(fig_hist, use_container_width=True)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Avg Lead Time", f"{np.mean(lead_time_data):.1f} days")
with col2:
    st.metric("Median Lead Time", f"{np.median(lead_time_data):.1f} days")
with col3:
    st.metric("Same Day %", f"{(lead_time_data < 1).sum() / len(lead_time_data) * 100:.1f}%")
with col4:
    st.metric("7+ Days Out %", f"{(lead_time_data >= 7).sum() / len(lead_time_data) * 100:.1f}%")
