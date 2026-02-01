"""
Forecast Evolution Page
Track how forecasts change over time as dates approach
"""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, datetime, timedelta
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.auth import require_auth

st.set_page_config(page_title="Forecast Evolution", page_icon="📉", layout="wide")

# Require authentication
require_auth()

st.title("📉 Forecast Evolution")
st.markdown("Track how forecasts for a specific date changed over time")

# Controls
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("Select Date to Analyze", date.today() - timedelta(days=7))
with col2:
    metric = st.selectbox("Metric", [
        "hotel_occupancy_pct",
        "resos_dinner_covers",
        "resos_lunch_covers"
    ])

st.markdown("---")

# Generate evolution data
np.random.seed(int(target_date.toordinal()))

base_value = 88 if 'occupancy' in metric else 145
actual_value = base_value + np.random.randn() * 3

# Generate forecasts at different horizons
evolution_data = []
for days_before in [60, 45, 30, 21, 14, 7, 3, 1]:
    forecast_date = target_date - timedelta(days=days_before)

    # Forecasts converge toward actual as date approaches
    noise = (days_before / 60) * np.random.randn() * 8
    prophet_val = actual_value + noise + np.random.randn() * 2
    xgboost_val = actual_value + noise + np.random.randn() * 3
    pickup_val = actual_value + noise * 0.8 + np.random.randn() * 1.5 if days_before <= 30 else None

    evolution_data.append({
        'Forecast Made': forecast_date,
        'Days Before': days_before,
        'Prophet': prophet_val,
        'XGBoost': xgboost_val,
        'Pickup': pickup_val
    })

# Add actual
evolution_data.append({
    'Forecast Made': target_date,
    'Days Before': 0,
    'Prophet': None,
    'XGBoost': None,
    'Pickup': None,
    'Actual': actual_value
})

evolution_df = pd.DataFrame(evolution_data)

# Evolution chart
st.subheader(f"📈 Forecast Evolution for {target_date.strftime('%d %b %Y')}")

fig = go.Figure()

# Prophet evolution
prophet_df = evolution_df.dropna(subset=['Prophet'])
fig.add_trace(go.Scatter(
    x=prophet_df['Days Before'],
    y=prophet_df['Prophet'],
    name='Prophet',
    mode='lines+markers',
    line=dict(color='#1f77b4', width=2),
    marker=dict(size=8)
))

# XGBoost evolution
xgboost_df = evolution_df.dropna(subset=['XGBoost'])
fig.add_trace(go.Scatter(
    x=xgboost_df['Days Before'],
    y=xgboost_df['XGBoost'],
    name='XGBoost',
    mode='lines+markers',
    line=dict(color='#ff7f0e', width=2),
    marker=dict(size=8)
))

# Pickup evolution
pickup_df = evolution_df.dropna(subset=['Pickup'])
if len(pickup_df) > 0:
    fig.add_trace(go.Scatter(
        x=pickup_df['Days Before'],
        y=pickup_df['Pickup'],
        name='Pickup',
        mode='lines+markers',
        line=dict(color='#2ca02c', width=2),
        marker=dict(size=8)
    ))

# Actual line
fig.add_hline(
    y=actual_value,
    line_dash="dash",
    line_color="#d62728",
    annotation_text=f"Actual: {actual_value:.1f}",
    annotation_position="right"
)

fig.update_layout(
    xaxis_title='Days Before Date',
    yaxis_title=metric.replace('_', ' ').title(),
    xaxis=dict(autorange='reversed'),
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    height=450
)

st.plotly_chart(fig, use_container_width=True)

# Change log
st.subheader("📝 Forecast Change Log")

# Generate change log
changes = []
for i in range(1, len(evolution_data) - 1):
    prev_prophet = evolution_data[i-1].get('Prophet', 0)
    curr_prophet = evolution_data[i].get('Prophet', 0)

    if prev_prophet and curr_prophet:
        change = curr_prophet - prev_prophet
        change_pct = (change / prev_prophet) * 100 if prev_prophet else 0

        reason = np.random.choice([
            "New bookings received",
            "Cancellations processed",
            "Model retrained",
            "Scheduled update",
            "Data correction"
        ])

        changes.append({
            'Date': evolution_data[i]['Forecast Made'],
            'Days Out': evolution_data[i]['Days Before'],
            'Previous': prev_prophet,
            'New': curr_prophet,
            'Change': change,
            'Change %': change_pct,
            'Reason': reason
        })

changes_df = pd.DataFrame(changes)

if not changes_df.empty:
    st.dataframe(
        changes_df.style.format({
            'Previous': '{:.1f}',
            'New': '{:.1f}',
            'Change': '{:+.1f}',
            'Change %': '{:+.1f}%'
        }).applymap(
            lambda x: 'color: green' if isinstance(x, (int, float)) and x > 0 else 'color: red' if isinstance(x, (int, float)) and x < 0 else '',
            subset=['Change', 'Change %']
        ),
        use_container_width=True,
        hide_index=True
    )

# Accuracy by horizon
st.markdown("---")
st.subheader("🎯 Accuracy by Forecast Horizon")

# Calculate errors at each horizon
horizon_accuracy = []
for row in evolution_data[:-1]:
    if row.get('Prophet'):
        error = abs(row['Prophet'] - actual_value)
        pct_error = (error / actual_value) * 100
        horizon_accuracy.append({
            'Days Before': row['Days Before'],
            'Abs Error': error,
            'Pct Error': pct_error
        })

accuracy_df = pd.DataFrame(horizon_accuracy)

fig_acc = go.Figure()
fig_acc.add_trace(go.Bar(
    x=accuracy_df['Days Before'],
    y=accuracy_df['Pct Error'],
    marker_color=['#2ca02c' if e < 5 else '#ff7f0e' if e < 10 else '#d62728' for e in accuracy_df['Pct Error']],
    text=accuracy_df['Pct Error'].round(1),
    textposition='outside'
))

fig_acc.update_layout(
    title='Forecast Error by Horizon',
    xaxis_title='Days Before Date',
    yaxis_title='Absolute % Error',
    xaxis=dict(autorange='reversed'),
    height=300
)

st.plotly_chart(fig_acc, use_container_width=True)

# Summary
col1, col2, col3 = st.columns(3)
with col1:
    first_forecast = evolution_data[0]['Prophet']
    st.metric(
        "Initial Forecast (60d)",
        f"{first_forecast:.1f}",
        f"{first_forecast - actual_value:+.1f} error"
    )
with col2:
    final_forecast = evolution_data[-2]['Prophet']
    st.metric(
        "Final Forecast (1d)",
        f"{final_forecast:.1f}",
        f"{final_forecast - actual_value:+.1f} error"
    )
with col3:
    st.metric(
        "Actual",
        f"{actual_value:.1f}"
    )
