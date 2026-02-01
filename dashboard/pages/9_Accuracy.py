"""
Accuracy Page
Track forecast accuracy and model performance over time
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
from components.date_picker import get_quick_date_ranges

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

st.set_page_config(page_title="Accuracy", page_icon="🎯", layout="wide")
require_auth()

st.title("🎯 Forecast Accuracy")

# Help expander
with st.expander("ℹ️ Understanding Forecast Accuracy", expanded=False):
    st.markdown("""
    ### What This Page Shows

    Track how accurate forecasts have been compared to actual results.

    ### Accuracy Metrics Explained

    | Metric | Formula | Interpretation |
    |--------|---------|----------------|
    | **MAE** | Mean Absolute Error | Average error in original units (e.g., "off by 5 rooms") |
    | **RMSE** | Root Mean Squared Error | Penalizes large errors more; always ≥ MAE |
    | **MAPE** | Mean Absolute % Error | Error as percentage (10% = typically 10% off) |

    ### What is "Good" Accuracy?

    | MAPE | Interpretation |
    |------|----------------|
    | **< 10%** | Excellent - high confidence in forecasts |
    | **10-20%** | Good - useful for planning |
    | **20-30%** | Fair - directionally helpful |
    | **> 30%** | Poor - forecasts need improvement |
    """)

st.markdown("---")


@st.cache_data(ttl=60)
def fetch_accuracy_summary(from_date, to_date):
    """Fetch accuracy summary from API"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/accuracy/summary",
            params={"from_date": str(from_date), "to_date": str(to_date)},
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"Error fetching accuracy data: {e}")
        return []


@st.cache_data(ttl=60)
def fetch_historical_accuracy(from_date, to_date):
    """Fetch accuracy by comparing historical forecasts to actuals"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/forecast/comparison",
            params={
                "from_date": str(from_date),
                "to_date": str(to_date),
                "metric": "hotel_room_nights"
            },
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []


# Quick-fill date buttons
quick_ranges = get_quick_date_ranges()
st.markdown("**Quick Select:**")

# Initialize session state for dates
if "accuracy_start" not in st.session_state:
    st.session_state.accuracy_start = date(2025, 4, 1)
if "accuracy_end" not in st.session_state:
    st.session_state.accuracy_end = date.today()

# Button row 1
cols1 = st.columns(5)
button_names = list(quick_ranges.keys())
for i, name in enumerate(button_names[:5]):
    with cols1[i]:
        if st.button(name, key=f"accuracy_quick_{name}", use_container_width=True):
            start, end = quick_ranges[name]
            st.session_state.accuracy_start = start
            st.session_state.accuracy_end = end
            st.rerun()

# Button row 2
cols2 = st.columns(4)
for i, name in enumerate(button_names[5:]):
    with cols2[i]:
        if st.button(name, key=f"accuracy_quick_{name}", use_container_width=True):
            start, end = quick_ranges[name]
            st.session_state.accuracy_start = start
            st.session_state.accuracy_end = end
            st.rerun()

st.markdown("")

# Controls row
col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    start_date = st.date_input("From Date", value=st.session_state.accuracy_start)
    st.session_state.accuracy_start = start_date

with col2:
    end_date = st.date_input("To Date", value=st.session_state.accuracy_end)
    st.session_state.accuracy_end = end_date

with col3:
    metric_filter = st.selectbox(
        "Filter by Metric",
        ["All Metrics", "hotel_room_nights", "hotel_occupancy_pct", "resos_dinner_covers", "resos_lunch_covers"],
        format_func=lambda x: {
            "All Metrics": "All Metrics",
            "hotel_room_nights": "Room Nights",
            "hotel_occupancy_pct": "Occupancy %",
            "resos_dinner_covers": "Dinner Covers",
            "resos_lunch_covers": "Lunch Covers"
        }.get(x, x)
    )

st.markdown("---")
st.caption(f"Analyzing: {start_date} to {end_date}")

# Fetch data from actual_vs_forecast table
accuracy_data = fetch_accuracy_summary(start_date, end_date)

# ============================================
# SUMMARY METRICS - from actual_vs_forecast
# ============================================
st.subheader("📊 Accuracy Summary (from actual_vs_forecast)")

if accuracy_data and isinstance(accuracy_data, list) and len(accuracy_data) > 0:
    # Transform the data for display
    # API returns list of metrics with nested model data
    all_models = []

    for metric_row in accuracy_data:
        metric_type = metric_row.get('metric_type', 'unknown')
        sample_count = metric_row.get('sample_count', 0)

        if metric_filter != "All Metrics" and metric_type != metric_filter:
            continue

        for model_name in ['prophet', 'xgboost', 'pickup']:
            model_data = metric_row.get(model_name, {})
            if model_data and model_data.get('mae') is not None:
                all_models.append({
                    'metric': metric_type,
                    'model': model_name,
                    'mae': model_data.get('mae'),
                    'rmse': model_data.get('rmse'),
                    'mape': model_data.get('mape'),
                    'wins': model_data.get('wins', 0),
                    'samples': sample_count
                })

    if all_models:
        model_df = pd.DataFrame(all_models)

        # Summary stats
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            avg_mae = model_df['mae'].mean()
            st.metric("Avg MAE", f"{avg_mae:.2f}")

        with col2:
            avg_mape = model_df['mape'].mean()
            st.metric("Avg MAPE", f"{avg_mape:.1f}%")

        with col3:
            best_model = model_df.loc[model_df['mape'].idxmin()]
            st.metric("Best Model", best_model['model'].title(), f"{best_model['mape']:.1f}% MAPE")

        with col4:
            total_wins = model_df['wins'].sum()
            st.metric("Total Comparisons", f"{total_wins:,}")

        # Model comparison table
        st.subheader("📈 Model Performance by Metric")

        st.dataframe(
            model_df.style.format({
                'mae': '{:.2f}',
                'rmse': '{:.2f}',
                'mape': '{:.1f}%'
            }),
            use_container_width=True,
            hide_index=True
        )

        # Chart: MAPE by Model
        fig = px.bar(
            model_df,
            x='metric',
            y='mape',
            color='model',
            barmode='group',
            title='MAPE by Metric and Model',
            labels={'mape': 'MAPE %', 'metric': 'Metric', 'model': 'Model'}
        )
        fig.add_hline(y=10, line_dash="dot", line_color="green", annotation_text="10% Target")
        fig.add_hline(y=20, line_dash="dot", line_color="orange", annotation_text="20% Threshold")
        st.plotly_chart(fig, use_container_width=True)

    else:
        st.info("No accuracy data for selected filters.")

else:
    st.warning("""
    **No accuracy data in actual_vs_forecast table.**

    This table is populated by the daily accuracy calculation job.
    For historical backtest data, see the section below.
    """)

# ============================================
# HISTORICAL FORECAST ACCURACY (direct comparison)
# ============================================
st.markdown("---")
st.subheader("📊 Historical Forecast Accuracy (Direct Comparison)")
st.caption("_Compare forecasts to actuals directly from forecasts + daily_metrics tables_")

# Query forecasts vs actuals directly
@st.cache_data(ttl=60)
def calculate_historical_accuracy(from_date, to_date, metric_code):
    """Calculate accuracy by directly comparing forecasts to actuals"""
    try:
        # Get forecasts that were generated before the dates they forecast
        response = httpx.get(
            f"{BACKEND_URL}/forecast/comparison",
            params={
                "from_date": str(from_date),
                "to_date": str(to_date),
                "metric": metric_code
            },
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict):
                return list(data.values())
            return data
        return []
    except Exception as e:
        return []


metric_for_analysis = metric_filter if metric_filter != "All Metrics" else "hotel_room_nights"
comparison_data = calculate_historical_accuracy(start_date, end_date, metric_for_analysis)

if comparison_data and len(comparison_data) > 0:
    comp_df = pd.DataFrame(comparison_data)

    if 'date' in comp_df.columns:
        comp_df['date'] = pd.to_datetime(comp_df['date'])

    # Calculate errors for each model where we have both forecast and actual
    results = []

    for _, row in comp_df.iterrows():
        actual = row.get('actual')
        if actual is None or actual == 0:
            continue

        row_date = row.get('date')

        # Extract models from nested structure (API returns models dict with value/lower/upper)
        models_dict = row.get('models', {})
        if isinstance(models_dict, str):
            import json
            try:
                models_dict = json.loads(models_dict)
            except:
                models_dict = {}

        for model in ['xgboost', 'pickup', 'prophet']:
            model_data = models_dict.get(model, {}) if models_dict else {}
            forecast = model_data.get('value') if isinstance(model_data, dict) else None
            if forecast is not None:
                error = forecast - actual
                pct_error = (error / actual) * 100
                results.append({
                    'date': row_date,
                    'model': model,
                    'actual': actual,
                    'forecast': forecast,
                    'error': error,
                    'abs_error': abs(error),
                    'pct_error': pct_error,
                    'abs_pct_error': abs(pct_error)
                })

    if results:
        results_df = pd.DataFrame(results)

        # Summary by model
        model_summary = results_df.groupby('model').agg({
            'abs_error': 'mean',
            'abs_pct_error': 'mean',
            'date': 'count'
        }).reset_index()
        model_summary.columns = ['Model', 'MAE', 'MAPE', 'Count']

        col1, col2 = st.columns([1, 2])

        with col1:
            st.markdown("**Model Accuracy Summary**")
            st.dataframe(
                model_summary.style.format({
                    'MAE': '{:.2f}',
                    'MAPE': '{:.1f}%'
                }),
                use_container_width=True,
                hide_index=True
            )

        with col2:
            fig = px.bar(
                model_summary,
                x='Model',
                y='MAPE',
                color='Model',
                title=f'MAPE by Model ({metric_for_analysis})'
            )
            fig.add_hline(y=10, line_dash="dot", line_color="green")
            fig.add_hline(y=20, line_dash="dot", line_color="orange")
            st.plotly_chart(fig, use_container_width=True)

        # Scatter: Forecast vs Actual
        st.subheader("📈 Forecast vs Actual")

        fig_scatter = px.scatter(
            results_df,
            x='actual',
            y='forecast',
            color='model',
            hover_data=['date', 'error', 'pct_error'],
            title='Forecast vs Actual Values'
        )

        # Add perfect prediction line
        max_val = max(results_df['actual'].max(), results_df['forecast'].max())
        fig_scatter.add_trace(go.Scatter(
            x=[0, max_val],
            y=[0, max_val],
            mode='lines',
            name='Perfect',
            line=dict(dash='dash', color='gray')
        ))
        fig_scatter.update_layout(height=450)
        st.plotly_chart(fig_scatter, use_container_width=True)

        # Error over time
        st.subheader("📅 Error Over Time")

        fig_time = go.Figure()
        for model in results_df['model'].unique():
            model_data = results_df[results_df['model'] == model]
            fig_time.add_trace(go.Scatter(
                x=model_data['date'],
                y=model_data['pct_error'],
                mode='markers',
                name=model.title(),
                opacity=0.7
            ))

        fig_time.add_hline(y=0, line_dash="solid", line_color="gray")
        fig_time.add_hline(y=10, line_dash="dot", line_color="green")
        fig_time.add_hline(y=-10, line_dash="dot", line_color="green")
        fig_time.update_layout(
            xaxis_title='Date',
            yaxis_title='Error %',
            height=400
        )
        st.plotly_chart(fig_time, use_container_width=True)

        # Export
        csv = results_df.to_csv(index=False)
        st.download_button(
            label="📥 Export Accuracy Data",
            data=csv,
            file_name=f"accuracy_{metric_for_analysis}_{start_date}_{end_date}.csv",
            mime="text/csv"
        )

    else:
        st.info("No forecast-actual pairs found for the selected period.")

else:
    st.info(f"No comparison data available for {metric_for_analysis} in the selected date range.")

# ============================================
# RECOMMENDATIONS
# ============================================
st.markdown("---")
st.subheader("💡 Recommendations")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **To Improve Accuracy:**
    - Ensure complete historical data sync
    - Review large error days for anomalies
    - Consider seasonal model tuning
    - Validate data quality regularly
    """)

with col2:
    st.markdown("""
    **Model Selection Guide:**
    - **Short-term (0-14 days)**: Pickup often best (has OTB data)
    - **Medium-term (15-60 days)**: XGBoost typically reliable
    - **Long-term (60+ days)**: Consider averaging models
    """)
