"""
Accuracy Page
Model performance tracking over time
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
import numpy as np

st.set_page_config(page_title="Accuracy", page_icon="🎯", layout="wide")

st.title("🎯 Model Accuracy")
st.markdown("Track how well each model predicts actual outcomes")

# Controls
col1, col2 = st.columns(2)
with col1:
    date_range = st.date_input(
        "Date Range",
        value=(date.today() - timedelta(days=30), date.today() - timedelta(days=1))
    )
with col2:
    metric = st.selectbox("Metric", [
        "hotel_occupancy_pct",
        "resos_dinner_covers",
        "resos_lunch_covers"
    ])

st.markdown("---")

# Generate accuracy data
np.random.seed(42)

if isinstance(date_range, tuple) and len(date_range) == 2:
    dates = pd.date_range(start=date_range[0], end=date_range[1], freq='D')
else:
    dates = pd.date_range(end=date.today() - timedelta(days=1), periods=30, freq='D')

n = len(dates)

base = 85 if 'occupancy' in metric else 140

data = []
for i, d in enumerate(dates):
    actual = base + np.random.randn() * 5 + np.sin(i * 0.3) * 8

    # Prophet error (generally good)
    prophet = actual + np.random.randn() * 2
    # XGBoost error (slightly higher variance)
    xgboost = actual + np.random.randn() * 3
    # Pickup error (lowest for short-term)
    pickup = actual + np.random.randn() * 1.5

    data.append({
        'Date': d,
        'Actual': actual,
        'Prophet': prophet,
        'XGBoost': xgboost,
        'Pickup': pickup,
        'Prophet_Error': prophet - actual,
        'XGBoost_Error': xgboost - actual,
        'Pickup_Error': pickup - actual,
        'Prophet_Pct': abs((prophet - actual) / actual) * 100,
        'XGBoost_Pct': abs((xgboost - actual) / actual) * 100,
        'Pickup_Pct': abs((pickup - actual) / actual) * 100
    })

df = pd.DataFrame(data)

# Determine best model for each day
df['Best_Model'] = df[['Prophet_Pct', 'XGBoost_Pct', 'Pickup_Pct']].idxmin(axis=1).str.replace('_Pct', '')

# Summary metrics
st.subheader("📊 Model Performance Summary")

col1, col2, col3 = st.columns(3)

models = ['Prophet', 'XGBoost', 'Pickup']
colors = {'Prophet': '#1f77b4', 'XGBoost': '#ff7f0e', 'Pickup': '#2ca02c'}

for i, (col, model) in enumerate(zip([col1, col2, col3], models)):
    with col:
        mae = df[f'{model}_Error'].abs().mean()
        rmse = np.sqrt((df[f'{model}_Error'] ** 2).mean())
        mape = df[f'{model}_Pct'].mean()
        wins = (df['Best_Model'] == model).sum()

        st.markdown(f"### {model}")
        st.metric("MAE", f"{mae:.2f}")
        st.metric("RMSE", f"{rmse:.2f}")
        st.metric("MAPE", f"{mape:.1f}%")
        st.metric("Best Days", f"{wins}/{n}")

# Accuracy over time chart
st.markdown("---")
st.subheader("📈 Forecast Error Over Time")

fig = go.Figure()

for model in models:
    fig.add_trace(go.Scatter(
        x=df['Date'],
        y=df[f'{model}_Pct'],
        name=model,
        mode='lines+markers',
        line=dict(color=colors[model], width=2),
        marker=dict(size=6)
    ))

fig.add_hline(y=5, line_dash="dash", line_color="gray", annotation_text="5% Target")

fig.update_layout(
    title='Absolute Percentage Error by Model',
    xaxis_title='Date',
    yaxis_title='Absolute % Error',
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    height=400
)

st.plotly_chart(fig, use_container_width=True)

# Win rate pie chart and error distribution
col1, col2 = st.columns(2)

with col1:
    st.subheader("🏆 Model Win Rate")

    win_counts = df['Best_Model'].value_counts()

    fig_pie = px.pie(
        values=win_counts.values,
        names=win_counts.index,
        color=win_counts.index,
        color_discrete_map=colors
    )
    fig_pie.update_layout(height=350)
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader("📊 Error Distribution")

    error_data = []
    for model in models:
        for e in df[f'{model}_Error']:
            error_data.append({'Model': model, 'Error': e})

    error_df = pd.DataFrame(error_data)

    fig_box = px.box(
        error_df,
        x='Model',
        y='Error',
        color='Model',
        color_discrete_map=colors
    )
    fig_box.update_layout(
        showlegend=False,
        height=350,
        yaxis_title='Forecast Error'
    )
    st.plotly_chart(fig_box, use_container_width=True)

# Accuracy by day of week
st.subheader("📅 Accuracy by Day of Week")

df['DayOfWeek'] = df['Date'].dt.day_name()

dow_accuracy = df.groupby('DayOfWeek').agg({
    'Prophet_Pct': 'mean',
    'XGBoost_Pct': 'mean',
    'Pickup_Pct': 'mean'
}).reindex(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'])

fig_dow = go.Figure()
for model in models:
    fig_dow.add_trace(go.Bar(
        name=model,
        x=dow_accuracy.index,
        y=dow_accuracy[f'{model}_Pct'],
        marker_color=colors[model]
    ))

fig_dow.update_layout(
    barmode='group',
    title='MAPE by Day of Week',
    xaxis_title='Day',
    yaxis_title='Avg Absolute % Error',
    height=350,
    legend=dict(orientation='h', yanchor='bottom', y=1.02)
)

st.plotly_chart(fig_dow, use_container_width=True)

# Data table
st.subheader("📋 Detailed Accuracy Data")

display_df = df[['Date', 'Actual', 'Prophet', 'XGBoost', 'Pickup',
                  'Prophet_Pct', 'XGBoost_Pct', 'Pickup_Pct', 'Best_Model']].copy()
display_df['Date'] = display_df['Date'].dt.strftime('%a %d %b')

st.dataframe(
    display_df.style.format({
        'Actual': '{:.1f}',
        'Prophet': '{:.1f}',
        'XGBoost': '{:.1f}',
        'Pickup': '{:.1f}',
        'Prophet_Pct': '{:.1f}%',
        'XGBoost_Pct': '{:.1f}%',
        'Pickup_Pct': '{:.1f}%'
    }).highlight_min(subset=['Prophet_Pct', 'XGBoost_Pct', 'Pickup_Pct'], color='lightgreen', axis=1),
    use_container_width=True,
    hide_index=True,
    height=400
)
