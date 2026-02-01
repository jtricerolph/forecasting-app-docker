"""
Cross Reference Page
Analyze correlations between different metrics
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

st.set_page_config(page_title="Cross Reference", page_icon="🔗", layout="wide")
require_auth()

st.title("🔗 Cross Reference Analysis")

# Help expander
with st.expander("ℹ️ Understanding Cross-Reference Analysis", expanded=False):
    st.markdown("""
    ### What This Page Shows

    Explore relationships between different metrics to understand:
    - **Correlations**: How metrics move together
    - **Dependencies**: What drives what
    - **Planning Insights**: Use one metric to predict another

    ### Key Relationships to Explore

    | Relationship | What it tells you |
    |--------------|-------------------|
    | **Occupancy ↔ Restaurant Covers** | Hotel guests dining in the restaurant |
    | **Room Revenue ↔ ADR** | Price vs volume trade-offs |
    | **Arrivals ↔ Dinner Covers** | Check-in day dining patterns |
    | **Guests ↔ Breakfast Allocation** | Breakfast planning needs |

    ### Correlation Interpretation

    | Value | Meaning |
    |-------|---------|
    | **0.8 to 1.0** | Strong positive correlation - metrics move together |
    | **0.5 to 0.8** | Moderate correlation - some relationship |
    | **0 to 0.5** | Weak correlation - limited relationship |
    | **Negative** | Inverse relationship - one goes up, other goes down |

    ### Using This for Planning

    **Example**: If occupancy correlates strongly with dinner covers (0.85):
    - When occupancy forecast is high → expect more dinner covers
    - Use occupancy forecast to estimate F&B demand
    - Adjust staffing based on expected hotel guests
    """)

st.markdown("---")

@st.cache_data(ttl=60)
def fetch_historical_data(from_date, to_date):
    """Fetch historical data for correlation analysis"""
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
    lookback = st.slider(
        "Analysis Period (Days)",
        30, 365, 90,
        help="Number of days of historical data to analyze"
    )

with col2:
    analysis_type = st.selectbox(
        "Analysis Type",
        ["Occupancy vs Restaurant", "Revenue Breakdown", "Custom Comparison"],
        help="Choose predefined analysis or custom metric selection"
    )

st.markdown("---")

# Fetch data
end_date = date.today()
start_date = end_date - timedelta(days=lookback)
data = fetch_historical_data(start_date, end_date)

if not data:
    st.warning("No historical data available for the selected period.")
    st.stop()

df = pd.DataFrame(data)
df['date'] = pd.to_datetime(df['date'])
df = df.sort_values('date')

# Define metric groups
metric_columns = {
    'occupancy_pct': 'Occupancy %',
    'occupied_rooms': 'Rooms Sold',
    'total_guests': 'Guests',
    'arrival_count': 'Arrivals',
    'room_revenue': 'Room Revenue',
    'adr': 'ADR',
    'revpar': 'RevPAR',
    'dinner_covers': 'Dinner Covers',
    'lunch_covers': 'Lunch Covers'
}

if analysis_type == "Occupancy vs Restaurant":
    metric_x = 'occupancy_pct'
    metric_y = 'dinner_covers'
    x_label = 'Occupancy %'
    y_label = 'Dinner Covers'

elif analysis_type == "Revenue Breakdown":
    metric_x = 'occupied_rooms'
    metric_y = 'room_revenue'
    x_label = 'Rooms Sold'
    y_label = 'Room Revenue (£)'

else:  # Custom
    col1, col2 = st.columns(2)
    with col1:
        metric_x = st.selectbox(
            "X-Axis Metric",
            options=list(metric_columns.keys()),
            format_func=lambda x: metric_columns.get(x, x)
        )
    with col2:
        metric_y = st.selectbox(
            "Y-Axis Metric",
            options=list(metric_columns.keys()),
            index=7,  # Default to dinner_covers
            format_func=lambda x: metric_columns.get(x, x)
        )
    x_label = metric_columns.get(metric_x, metric_x)
    y_label = metric_columns.get(metric_y, metric_y)

# Scatter plot
st.subheader(f"📊 {x_label} vs {y_label}")

# Calculate correlation
if metric_x in df.columns and metric_y in df.columns:
    valid_df = df[[metric_x, metric_y, 'date', 'day_of_week']].dropna()

    if len(valid_df) > 5:
        correlation = valid_df[metric_x].corr(valid_df[metric_y])

        col1, col2 = st.columns([3, 1])

        with col1:
            # Scatter plot with trendline
            fig = px.scatter(
                valid_df,
                x=metric_x,
                y=metric_y,
                color='day_of_week',
                trendline='ols',
                labels={metric_x: x_label, metric_y: y_label, 'day_of_week': 'Day'},
                title=f'Correlation: {correlation:.3f}'
            )
            fig.update_layout(height=450)
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            # Correlation interpretation
            st.metric("Correlation", f"{correlation:.3f}")

            if abs(correlation) >= 0.8:
                st.success("Strong relationship")
            elif abs(correlation) >= 0.5:
                st.info("Moderate relationship")
            else:
                st.warning("Weak relationship")

            # Simple stats
            st.markdown("---")
            st.markdown("**Quick Stats**")
            st.markdown(f"**{x_label}**")
            st.markdown(f"Mean: {valid_df[metric_x].mean():.1f}")
            st.markdown(f"**{y_label}**")
            st.markdown(f"Mean: {valid_df[metric_y].mean():.1f}")

        # Day of week breakdown
        st.subheader("📅 Relationship by Day of Week")

        dow_stats = valid_df.groupby('day_of_week').agg({
            metric_x: 'mean',
            metric_y: 'mean'
        }).round(2)

        col1, col2 = st.columns(2)

        with col1:
            st.dataframe(dow_stats.rename(columns={
                metric_x: f'Avg {x_label}',
                metric_y: f'Avg {y_label}'
            }), use_container_width=True)

        with col2:
            # Bar chart comparison by day
            fig_dow = go.Figure()
            fig_dow.add_trace(go.Bar(
                x=dow_stats.index,
                y=dow_stats[metric_x],
                name=x_label,
                yaxis='y'
            ))
            fig_dow.add_trace(go.Scatter(
                x=dow_stats.index,
                y=dow_stats[metric_y],
                name=y_label,
                yaxis='y2',
                mode='lines+markers',
                line=dict(color='red', width=2)
            ))
            fig_dow.update_layout(
                title='By Day of Week',
                yaxis=dict(title=x_label),
                yaxis2=dict(title=y_label, overlaying='y', side='right'),
                height=300
            )
            st.plotly_chart(fig_dow, use_container_width=True)

    else:
        st.warning("Not enough data points for correlation analysis.")

# Correlation matrix
st.markdown("---")
st.subheader("📈 Full Correlation Matrix")
st.caption("_Explore relationships between all metrics_")

# Select numeric columns
numeric_cols = ['occupancy_pct', 'occupied_rooms', 'total_guests', 'arrival_count',
                'room_revenue', 'adr', 'revpar', 'dinner_covers', 'lunch_covers']
available_cols = [c for c in numeric_cols if c in df.columns]

if len(available_cols) >= 2:
    corr_matrix = df[available_cols].corr()

    # Rename for display
    display_names = [metric_columns.get(c, c) for c in available_cols]
    corr_matrix.index = display_names
    corr_matrix.columns = display_names

    fig_heatmap = px.imshow(
        corr_matrix,
        labels=dict(color="Correlation"),
        color_continuous_scale='RdBu_r',
        zmin=-1, zmax=1,
        aspect='auto'
    )
    fig_heatmap.update_layout(height=500)
    st.plotly_chart(fig_heatmap, use_container_width=True)

    with st.expander("ℹ️ Reading the Correlation Matrix"):
        st.markdown("""
        - **Red/Orange**: Positive correlation (metrics increase together)
        - **Blue**: Negative correlation (one increases, other decreases)
        - **White/Light**: No significant correlation

        **Strong positive correlations to look for:**
        - Occupancy ↔ Room Revenue (more rooms = more revenue)
        - Guests ↔ Breakfast (more guests = more breakfasts)

        **Interesting negative correlations:**
        - ADR ↔ Occupancy might show pricing strategy effects
        """)

# Time series comparison
st.markdown("---")
st.subheader("📈 Time Series Comparison")

if metric_x in df.columns and metric_y in df.columns:
    fig_ts = go.Figure()

    fig_ts.add_trace(go.Scatter(
        x=df['date'], y=df[metric_x],
        name=x_label, yaxis='y'
    ))

    fig_ts.add_trace(go.Scatter(
        x=df['date'], y=df[metric_y],
        name=y_label, yaxis='y2',
        line=dict(color='red')
    ))

    fig_ts.update_layout(
        title=f'{x_label} and {y_label} Over Time',
        yaxis=dict(title=x_label, side='left'),
        yaxis2=dict(title=y_label, side='right', overlaying='y'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02),
        height=350,
        hovermode='x unified'
    )

    st.plotly_chart(fig_ts, use_container_width=True)

# Export
st.markdown("---")
csv = df.to_csv(index=False)
st.download_button(
    label="📥 Export Cross-Reference Data",
    data=csv,
    file_name=f"cross_reference_{lookback}days.csv",
    mime="text/csv"
)
