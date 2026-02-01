"""
Cross-Reference Validation Page
Validate that related forecasts align with each other
"""
import os
import sys
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta
import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.auth import require_auth

st.set_page_config(page_title="Cross-Reference", page_icon="✅", layout="wide")

# Require authentication
require_auth()

st.title("✅ Cross-Reference Validation")
st.markdown("Ensure forecast consistency - verify related metrics align")

# Date selector
check_date = st.date_input("Check Date", date.today() + timedelta(days=7))

st.markdown("---")

# Generate cross-reference check data
np.random.seed(int(check_date.toordinal()))

# Hotel checks
room_nights = 65 + np.random.randint(-5, 10)
adr = 175 + np.random.randint(-20, 30)
revenue_calculated = room_nights * adr
revenue_forecast = revenue_calculated * (1 + np.random.randn() * 0.03)

occupancy_calculated = (room_nights / 80) * 100  # Assuming 80 rooms
occupancy_forecast = occupancy_calculated * (1 + np.random.randn() * 0.02)

guests_per_room = 1.8
guests_calculated = room_nights * guests_per_room
guests_forecast = guests_calculated * (1 + np.random.randn() * 0.05)

# Restaurant checks
dinner_bookings = 45 + np.random.randint(-5, 10)
party_size = 3.2 + np.random.randn() * 0.3
covers_calculated = dinner_bookings * party_size
covers_forecast = covers_calculated * (1 + np.random.randn() * 0.05)

checks = [
    {
        'Category': 'Hotel',
        'Check': 'Revenue (nights × ADR)',
        'Calculated': revenue_calculated,
        'Forecasted': revenue_forecast,
        'Tolerance': 5.0,
        'Formula': f'{room_nights} × £{adr}'
    },
    {
        'Category': 'Hotel',
        'Check': 'Occupancy (nights / rooms)',
        'Calculated': occupancy_calculated,
        'Forecasted': occupancy_forecast,
        'Tolerance': 2.0,
        'Formula': f'{room_nights} / 80 × 100'
    },
    {
        'Category': 'Hotel',
        'Check': 'Guests (nights × avg)',
        'Calculated': guests_calculated,
        'Forecasted': guests_forecast,
        'Tolerance': 10.0,
        'Formula': f'{room_nights} × {guests_per_room}'
    },
    {
        'Category': 'Restaurant',
        'Check': 'Dinner Covers (bookings × party)',
        'Calculated': covers_calculated,
        'Forecasted': covers_forecast,
        'Tolerance': 10.0,
        'Formula': f'{dinner_bookings} × {party_size:.1f}'
    }
]

# Calculate differences and status
for check in checks:
    diff = check['Forecasted'] - check['Calculated']
    diff_pct = abs(diff / check['Calculated']) * 100 if check['Calculated'] != 0 else 0
    check['Difference'] = diff
    check['Diff %'] = diff_pct
    check['Status'] = '✅ OK' if diff_pct <= check['Tolerance'] else '⚠️ Warning' if diff_pct <= check['Tolerance'] * 2 else '❌ Discrepancy'

checks_df = pd.DataFrame(checks)

# Alignment score
passed = sum(1 for c in checks if '✅' in c['Status'])
warnings = sum(1 for c in checks if '⚠️' in c['Status'])
total = len(checks)
alignment_score = ((passed + warnings * 0.5) / total) * 100

# Summary metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Alignment Score", f"{alignment_score:.0f}%")
with col2:
    st.metric("Checks Passed", f"{passed}/{total}")
with col3:
    st.metric("Warnings", f"{warnings}")
with col4:
    st.metric("Discrepancies", f"{total - passed - warnings}")

st.markdown("---")

# Results table
st.subheader("📋 Cross-Reference Results")

# Style the dataframe
def style_status(val):
    if '✅' in str(val):
        return 'background-color: #d4edda'
    elif '⚠️' in str(val):
        return 'background-color: #fff3cd'
    elif '❌' in str(val):
        return 'background-color: #f8d7da'
    return ''

display_df = checks_df[['Category', 'Check', 'Calculated', 'Forecasted', 'Diff %', 'Tolerance', 'Status', 'Formula']]

st.dataframe(
    display_df.style.applymap(style_status, subset=['Status']).format({
        'Calculated': '{:.1f}',
        'Forecasted': '{:.1f}',
        'Diff %': '{:.1f}%',
        'Tolerance': '{:.1f}%'
    }),
    use_container_width=True,
    hide_index=True,
    height=250
)

# Visualization
st.subheader("📊 Calculated vs Forecasted Values")

fig = go.Figure()

for i, check in enumerate(checks):
    fig.add_trace(go.Bar(
        name=check['Check'][:20] + '...' if len(check['Check']) > 20 else check['Check'],
        x=['Calculated', 'Forecasted'],
        y=[check['Calculated'], check['Forecasted']],
        text=[f"{check['Calculated']:.0f}", f"{check['Forecasted']:.0f}"],
        textposition='outside',
        offsetgroup=i
    ))

fig.update_layout(
    barmode='group',
    title='Calculated vs Forecasted Comparison',
    height=400,
    legend=dict(orientation='h', yanchor='bottom', y=1.02)
)

st.plotly_chart(fig, use_container_width=True)

# Discrepancy details
discrepancies = [c for c in checks if '❌' in c['Status']]
if discrepancies:
    st.markdown("---")
    st.subheader("⚠️ Discrepancy Details")

    for disc in discrepancies:
        st.error(f"""
        **{disc['Check']}**

        - Calculated: {disc['Calculated']:.1f} (Formula: {disc['Formula']})
        - Forecasted: {disc['Forecasted']:.1f}
        - Difference: {disc['Diff %']:.1f}% (Tolerance: {disc['Tolerance']}%)

        **Possible causes:**
        - Input metric forecasts may be inconsistent
        - Check individual model predictions for this date
        - Review if any manual overrides were applied
        """)

# Historical alignment
st.markdown("---")
st.subheader("📈 Alignment Score Trend")

# Generate historical alignment scores
dates = pd.date_range(end=check_date, periods=14, freq='D')
scores = 85 + np.random.randn(14) * 5 + np.sin(np.arange(14) * 0.3) * 3

fig_trend = go.Figure()
fig_trend.add_trace(go.Scatter(
    x=dates, y=scores,
    mode='lines+markers',
    fill='tozeroy',
    line=dict(color='#1f77b4', width=2)
))
fig_trend.add_hline(y=90, line_dash="dash", line_color="green", annotation_text="Target: 90%")
fig_trend.update_layout(
    title='Alignment Score Over Time',
    xaxis_title='Date',
    yaxis_title='Alignment Score (%)',
    height=300,
    yaxis=dict(range=[70, 100])
)

st.plotly_chart(fig_trend, use_container_width=True)
