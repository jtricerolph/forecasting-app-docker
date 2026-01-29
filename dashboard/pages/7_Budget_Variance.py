"""
Budget Variance Page
Compare forecast vs budget vs actual
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
import numpy as np

st.set_page_config(page_title="Budget Variance", page_icon="💰", layout="wide")

st.title("💰 Budget Variance")
st.markdown("Compare forecasts against budget targets and actuals")

# Controls
col1, col2, col3 = st.columns(3)
with col1:
    start_date = st.date_input("From", date.today() - timedelta(days=7))
with col2:
    end_date = st.date_input("To", date.today() + timedelta(days=21))
with col3:
    metric = st.selectbox("Metric", [
        "hotel_occupancy_pct",
        "resos_dinner_covers",
        "resos_lunch_covers",
        "revenue_rooms",
        "revenue_fb_total"
    ])

st.markdown("---")

# Generate sample data
np.random.seed(42)
dates = pd.date_range(start=start_date, end=end_date, freq='D')
n = len(dates)

# Base values depending on metric
if 'occupancy' in metric:
    base, unit = 80, '%'
elif 'covers' in metric:
    base, unit = 120, 'covers'
else:
    base, unit = 8000, '£'

data = []
today = date.today()

for i, d in enumerate(dates):
    budget = base + np.sin(i * 0.2) * (base * 0.1)
    forecast = budget + np.random.randn() * (base * 0.08) + np.sin(i * 0.3) * (base * 0.05)

    # Only have actuals for past dates
    actual = None
    if d.date() <= today:
        actual = forecast + np.random.randn() * (base * 0.03)

    data.append({
        'Date': d,
        'Budget': budget,
        'Forecast': forecast,
        'Actual': actual,
        'Forecast_vs_Budget': forecast - budget,
        'Forecast_vs_Budget_Pct': ((forecast - budget) / budget) * 100
    })

df = pd.DataFrame(data)

# Main variance chart
st.subheader("📊 Forecast vs Budget vs Actual")

fig = go.Figure()

# Budget
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Budget'],
    name='Budget',
    line=dict(color='#d62728', width=2, dash='dash')
))

# Forecast
fig.add_trace(go.Scatter(
    x=df['Date'], y=df['Forecast'],
    name='Forecast',
    line=dict(color='#1f77b4', width=2)
))

# Actual
actual_df = df.dropna(subset=['Actual'])
fig.add_trace(go.Scatter(
    x=actual_df['Date'], y=actual_df['Actual'],
    name='Actual',
    mode='markers',
    marker=dict(color='#2ca02c', size=10, symbol='circle')
))

fig.update_layout(
    title=f'{metric.replace("_", " ").title()} - Budget vs Forecast vs Actual',
    xaxis_title='Date',
    yaxis_title=f'Value ({unit})',
    legend=dict(orientation='h', yanchor='bottom', y=1.02),
    height=450,
    hovermode='x unified'
)

# Add today marker
fig.add_vline(x=today, line_dash="dot", line_color="gray", annotation_text="Today")

st.plotly_chart(fig, use_container_width=True)

# Variance breakdown
st.subheader("📈 Variance Analysis")

col1, col2 = st.columns(2)

with col1:
    # Variance bar chart
    fig_var = go.Figure()

    colors = ['#2ca02c' if v >= 0 else '#d62728' for v in df['Forecast_vs_Budget_Pct']]

    fig_var.add_trace(go.Bar(
        x=df['Date'],
        y=df['Forecast_vs_Budget_Pct'],
        marker_color=colors,
        text=df['Forecast_vs_Budget_Pct'].round(1),
        textposition='outside'
    ))

    fig_var.update_layout(
        title='Daily Variance (Forecast vs Budget %)',
        xaxis_title='Date',
        yaxis_title='Variance %',
        height=350
    )

    st.plotly_chart(fig_var, use_container_width=True)

with col2:
    # Summary metrics
    total_budget = df['Budget'].sum()
    total_forecast = df['Forecast'].sum()
    total_actual = actual_df['Actual'].sum() if len(actual_df) > 0 else 0

    forecast_variance = ((total_forecast - total_budget) / total_budget) * 100
    actual_variance = ((total_actual - df[df['Actual'].notna()]['Budget'].sum()) / df[df['Actual'].notna()]['Budget'].sum()) * 100 if len(actual_df) > 0 else 0

    st.metric(
        "Total Budget",
        f"{unit}{total_budget:,.0f}" if unit == '£' else f"{total_budget:,.0f} {unit}"
    )
    st.metric(
        "Total Forecast",
        f"{unit}{total_forecast:,.0f}" if unit == '£' else f"{total_forecast:,.0f} {unit}",
        f"{forecast_variance:+.1f}% vs budget"
    )
    if len(actual_df) > 0:
        st.metric(
            "Actual to Date",
            f"{unit}{total_actual:,.0f}" if unit == '£' else f"{total_actual:,.0f} {unit}",
            f"{actual_variance:+.1f}% vs budget"
        )

# Data table
st.subheader("📋 Daily Breakdown")

display_df = df[['Date', 'Budget', 'Forecast', 'Actual', 'Forecast_vs_Budget', 'Forecast_vs_Budget_Pct']].copy()
display_df['Date'] = display_df['Date'].dt.strftime('%a %d %b')
display_df.columns = ['Date', 'Budget', 'Forecast', 'Actual', 'Variance', 'Variance %']

def highlight_variance(val):
    if pd.isna(val):
        return ''
    if isinstance(val, (int, float)):
        if val > 5:
            return 'background-color: #d4edda'
        elif val < -5:
            return 'background-color: #f8d7da'
    return ''

st.dataframe(
    display_df.style.format({
        'Budget': '{:.0f}',
        'Forecast': '{:.0f}',
        'Actual': '{:.0f}',
        'Variance': '{:+.0f}',
        'Variance %': '{:+.1f}%'
    }).applymap(highlight_variance, subset=['Variance %']),
    use_container_width=True,
    hide_index=True,
    height=400
)

# MTD/YTD Summary
st.markdown("---")
st.subheader("📊 Period Summary")

col1, col2, col3, col4 = st.columns(4)

with col1:
    positive_days = (df['Forecast_vs_Budget_Pct'] > 0).sum()
    st.metric("Days Above Budget", f"{positive_days}/{n}")

with col2:
    avg_variance = df['Forecast_vs_Budget_Pct'].mean()
    st.metric("Avg Daily Variance", f"{avg_variance:+.1f}%")

with col3:
    max_variance = df['Forecast_vs_Budget_Pct'].max()
    st.metric("Best Day Variance", f"{max_variance:+.1f}%")

with col4:
    min_variance = df['Forecast_vs_Budget_Pct'].min()
    st.metric("Worst Day Variance", f"{min_variance:+.1f}%")
