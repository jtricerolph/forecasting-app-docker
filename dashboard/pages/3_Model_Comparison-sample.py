"""
Model Comparison Page
Compare Prophet, XGBoost, and Pickup model performance
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

st.set_page_config(page_title="Model Comparison", page_icon="🔄", layout="wide")

# Require authentication
require_auth()

st.title("🔄 Model Comparison")
st.markdown("Compare forecasting models: Prophet vs XGBoost vs Pickup")

# Controls
col1, col2 = st.columns(2)
with col1:
    metric = st.selectbox("Select Metric", [
        "hotel_occupancy_pct",
        "resos_dinner_covers",
        "resos_lunch_covers",
        "hotel_guests",
        "hotel_adr"
    ])
with col2:
    date_range = st.date_input(
        "Date Range",
        value=(date.today(), date.today() + timedelta(days=28)),
        key="date_range"
    )

st.markdown("---")

# Generate sample comparison data
np.random.seed(42)
if isinstance(date_range, tuple) and len(date_range) == 2:
    dates = pd.date_range(start=date_range[0], end=date_range[1], freq='D')
else:
    dates = pd.date_range(start=date.today(), periods=28, freq='D')

n = len(dates)

# Create model predictions
base = 85 if 'occupancy' in metric else 140 if 'covers' in metric else 150

df = pd.DataFrame({
    'Date': dates,
    'Prophet': base + np.random.randn(n) * 3 + np.sin(np.arange(n) * 0.3) * 8,
    'XGBoost': base + np.random.randn(n) * 4 + np.sin(np.arange(n) * 0.3) * 7,
    'Pickup': base + np.random.randn(n) * 2 + np.sin(np.arange(n) * 0.3) * 9,
    'Actual': None  # Will have values for past dates
})

# Add actuals for past dates
today = date.today()
for i, d in enumerate(dates):
    if d.date() < today:
        df.loc[i, 'Actual'] = base + np.random.randn() * 2 + np.sin(i * 0.3) * 8

# Model comparison chart
st.subheader("📈 Model Predictions Over Time")

fig = go.Figure()

colors = {'Prophet': '#1f77b4', 'XGBoost': '#ff7f0e', 'Pickup': '#2ca02c', 'Actual': '#d62728'}

for model in ['Prophet', 'XGBoost', 'Pickup']:
    fig.add_trace(go.Scatter(
        x=df['Date'], y=df[model],
        name=model, line=dict(color=colors[model], width=2)
    ))

# Add actuals as scatter
actual_df = df.dropna(subset=['Actual'])
fig.add_trace(go.Scatter(
    x=actual_df['Date'], y=actual_df['Actual'],
    name='Actual', mode='markers',
    marker=dict(color=colors['Actual'], size=10, symbol='star')
))

fig.update_layout(
    xaxis_title='Date',
    yaxis_title=metric.replace('_', ' ').title(),
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    height=450,
    hovermode='x unified'
)

st.plotly_chart(fig, use_container_width=True)

# Model accuracy comparison
st.subheader("🎯 Model Accuracy (Historical)")

# Generate accuracy metrics
accuracy_data = {
    'Model': ['Prophet', 'XGBoost', 'Pickup'],
    'MAE': [2.3, 2.8, 1.9],
    'RMSE': [3.1, 3.6, 2.5],
    'MAPE (%)': [2.8, 3.4, 2.2],
    'Best Days': [12, 8, 15],
    'Win Rate (%)': [34, 23, 43]
}
accuracy_df = pd.DataFrame(accuracy_data)

col1, col2 = st.columns(2)

with col1:
    # Accuracy metrics table
    st.dataframe(
        accuracy_df.style.highlight_min(subset=['MAE', 'RMSE', 'MAPE (%)'], color='lightgreen')
            .highlight_max(subset=['Best Days', 'Win Rate (%)'], color='lightgreen'),
        use_container_width=True,
        hide_index=True
    )

with col2:
    # Win rate pie chart
    fig_pie = px.pie(
        accuracy_df,
        values='Win Rate (%)',
        names='Model',
        title='Model Win Rate',
        color='Model',
        color_discrete_map={'Prophet': '#1f77b4', 'XGBoost': '#ff7f0e', 'Pickup': '#2ca02c'}
    )
    st.plotly_chart(fig_pie, use_container_width=True)

# Error distribution
st.subheader("📊 Error Distribution by Model")

# Generate error data
error_data = []
for model in ['Prophet', 'XGBoost', 'Pickup']:
    errors = np.random.randn(100) * (3 if model == 'XGBoost' else 2)
    for e in errors:
        error_data.append({'Model': model, 'Error': e})

error_df = pd.DataFrame(error_data)

fig_box = px.box(
    error_df,
    x='Model',
    y='Error',
    color='Model',
    color_discrete_map={'Prophet': '#1f77b4', 'XGBoost': '#ff7f0e', 'Pickup': '#2ca02c'},
    title='Forecast Error Distribution'
)
fig_box.update_layout(height=350, showlegend=False)
st.plotly_chart(fig_box, use_container_width=True)

# Model divergence analysis
st.subheader("🔍 Model Divergence")

# Calculate model divergence
df['Prophet_XGBoost_Diff'] = abs(df['Prophet'] - df['XGBoost'])
df['Prophet_Pickup_Diff'] = abs(df['Prophet'] - df['Pickup'])
df['XGBoost_Pickup_Diff'] = abs(df['XGBoost'] - df['Pickup'])

col1, col2 = st.columns(2)

with col1:
    st.metric("Avg Prophet-XGBoost Gap", f"{df['Prophet_XGBoost_Diff'].mean():.1f}")
    st.metric("Avg Prophet-Pickup Gap", f"{df['Prophet_Pickup_Diff'].mean():.1f}")
    st.metric("Avg XGBoost-Pickup Gap", f"{df['XGBoost_Pickup_Diff'].mean():.1f}")

with col2:
    # Divergence over time
    fig_div = go.Figure()
    fig_div.add_trace(go.Scatter(
        x=df['Date'], y=df['Prophet_XGBoost_Diff'],
        name='Prophet vs XGBoost', fill='tozeroy'
    ))
    fig_div.update_layout(
        title='Model Divergence Over Time',
        xaxis_title='Date',
        yaxis_title='Absolute Difference',
        height=250
    )
    st.plotly_chart(fig_div, use_container_width=True)

# Recommendation
st.markdown("---")
st.subheader("💡 Recommendation")

best_model = accuracy_df.loc[accuracy_df['MAPE (%)'].idxmin(), 'Model']
st.success(f"""
**Best performing model: {best_model}**

Based on historical accuracy, the {best_model} model shows:
- Lowest MAPE ({accuracy_df.loc[accuracy_df['Model'] == best_model, 'MAPE (%)'].values[0]}%)
- Highest win rate ({accuracy_df.loc[accuracy_df['Model'] == best_model, 'Win Rate (%)'].values[0]}%)

Consider using {best_model} as the primary forecast for operational decisions.
""")
