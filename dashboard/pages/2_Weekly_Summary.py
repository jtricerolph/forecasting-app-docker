"""
Weekly Summary Page
8-week rolling forecast with budget comparison
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import date, timedelta
import numpy as np

st.set_page_config(page_title="Weekly Summary", page_icon="📊", layout="wide")

st.title("📊 Weekly Summary")
st.markdown("8-week rolling forecast with budget comparison")

# Controls
col1, col2 = st.columns([1, 3])
with col1:
    weeks = st.slider("Weeks to show", 4, 12, 8)
with col2:
    metrics = st.multiselect(
        "Metrics",
        ["Occupancy", "Dinner Covers", "Lunch Covers", "Room Revenue", "F&B Revenue"],
        default=["Occupancy", "Dinner Covers"]
    )

st.markdown("---")

# Generate sample weekly data
np.random.seed(42)
week_starts = pd.date_range(start=date.today(), periods=weeks, freq='W-MON')

weekly_data = []
for i, week in enumerate(week_starts):
    for metric in ["Occupancy", "Dinner Covers", "Lunch Covers", "Room Revenue", "F&B Revenue"]:
        if metric == "Occupancy":
            base, budget = 82, 78
            unit = "%"
        elif "Covers" in metric:
            base, budget = 850, 800
            unit = "covers"
        else:
            base, budget = 45000, 42000
            unit = "£"

        forecast = base + np.random.randn() * (base * 0.05) + np.sin(i * 0.3) * (base * 0.1)
        budget_val = budget + np.sin(i * 0.2) * (budget * 0.05)

        weekly_data.append({
            "Week": week.strftime("%d %b"),
            "Week_Date": week,
            "Metric": metric,
            "Forecast": forecast,
            "Budget": budget_val,
            "Variance": forecast - budget_val,
            "Variance_Pct": ((forecast - budget_val) / budget_val) * 100,
            "Unit": unit
        })

df = pd.DataFrame(weekly_data)

# Filter by selected metrics
df_filtered = df[df['Metric'].isin(metrics)]

# Weekly forecast vs budget chart
st.subheader("📈 Forecast vs Budget Comparison")

for metric in metrics:
    metric_df = df_filtered[df_filtered['Metric'] == metric]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=metric_df['Week'],
        y=metric_df['Forecast'],
        name='Forecast',
        marker_color='#1f77b4',
        text=metric_df['Forecast'].round(0),
        textposition='outside'
    ))

    fig.add_trace(go.Scatter(
        x=metric_df['Week'],
        y=metric_df['Budget'],
        name='Budget',
        mode='lines+markers',
        line=dict(color='#d62728', width=3, dash='dash'),
        marker=dict(size=8)
    ))

    unit = metric_df['Unit'].iloc[0]
    fig.update_layout(
        title=f'{metric} - Weekly Forecast vs Budget',
        xaxis_title='Week Starting',
        yaxis_title=f'{metric} ({unit})',
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=350,
        margin=dict(l=0, r=0, t=60, b=0)
    )

    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# Variance heatmap
st.subheader("📊 Variance Heatmap")

pivot_df = df.pivot_table(
    index='Metric',
    columns='Week',
    values='Variance_Pct',
    aggfunc='mean'
)

fig = px.imshow(
    pivot_df,
    labels=dict(x="Week", y="Metric", color="Variance %"),
    color_continuous_scale=['red', 'white', 'green'],
    color_continuous_midpoint=0,
    aspect='auto',
    text_auto='.1f'
)

fig.update_layout(
    title='Forecast vs Budget Variance (%)',
    height=300
)

st.plotly_chart(fig, use_container_width=True)

# Summary table
st.subheader("📋 Weekly Data Table")

summary_df = df_filtered.pivot_table(
    index='Week',
    columns='Metric',
    values=['Forecast', 'Budget', 'Variance_Pct']
).round(1)

# Flatten column names
summary_df.columns = [f'{col[1]} {col[0]}' for col in summary_df.columns]

st.dataframe(summary_df, use_container_width=True, height=300)

# Totals
st.subheader("📊 Period Totals")

col1, col2, col3, col4 = st.columns(4)

total_occ = df[df['Metric'] == 'Occupancy']['Forecast'].mean()
total_occ_budget = df[df['Metric'] == 'Occupancy']['Budget'].mean()

total_dinner = df[df['Metric'] == 'Dinner Covers']['Forecast'].sum()
total_dinner_budget = df[df['Metric'] == 'Dinner Covers']['Budget'].sum()

total_revenue = df[df['Metric'] == 'Room Revenue']['Forecast'].sum()
total_revenue_budget = df[df['Metric'] == 'Room Revenue']['Budget'].sum()

total_fb = df[df['Metric'] == 'F&B Revenue']['Forecast'].sum()
total_fb_budget = df[df['Metric'] == 'F&B Revenue']['Budget'].sum()

with col1:
    variance = ((total_occ - total_occ_budget) / total_occ_budget) * 100
    st.metric("Avg Occupancy", f"{total_occ:.1f}%", f"{variance:+.1f}% vs budget")

with col2:
    variance = ((total_dinner - total_dinner_budget) / total_dinner_budget) * 100
    st.metric("Total Dinner Covers", f"{total_dinner:,.0f}", f"{variance:+.1f}% vs budget")

with col3:
    variance = ((total_revenue - total_revenue_budget) / total_revenue_budget) * 100
    st.metric("Room Revenue", f"£{total_revenue:,.0f}", f"{variance:+.1f}% vs budget")

with col4:
    variance = ((total_fb - total_fb_budget) / total_fb_budget) * 100
    st.metric("F&B Revenue", f"£{total_fb:,.0f}", f"{variance:+.1f}% vs budget")
