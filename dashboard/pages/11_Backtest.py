"""
Backtest Page
Evaluate model accuracy by simulating historical forecasts
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

st.set_page_config(page_title="Backtest", page_icon="🔬", layout="wide")
require_auth()

st.title("🔬 Model Backtesting")


# ============================================
# HELPER FUNCTIONS
# ============================================

def run_backtest(metric_code: str, from_date: date, to_date: date, lead_times: str):
    """Run pickup backtest via API"""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/backtest/run",
            params={
                "metric_code": metric_code,
                "from_date": str(from_date),
                "to_date": str(to_date),
                "lead_times": lead_times
            },
            headers=get_auth_header(),
            timeout=120.0
        )
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Backtest failed: {response.text}")
            return None
    except Exception as e:
        st.error(f"Error running backtest: {e}")
        return None


def run_historical_forecasts(simulated_dates: str, metrics: str, models: str, forecast_days: int):
    """Run all models as historical dates"""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/backtest/historical-forecast",
            params={
                "simulated_dates": simulated_dates,
                "metrics": metrics,
                "models": models,
                "forecast_days": forecast_days
            },
            headers=get_auth_header(),
            timeout=600.0  # Can take a long time
        )
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Historical forecast failed: {response.text}")
            return None
    except Exception as e:
        st.error(f"Error running historical forecasts: {e}")
        return None


def get_backtest_summary(metric_code: str, from_date: date = None, to_date: date = None):
    """Get stored backtest summary"""
    try:
        params = {"metric_code": metric_code}
        if from_date:
            params["from_date"] = str(from_date)
        if to_date:
            params["to_date"] = str(to_date)

        response = httpx.get(
            f"{BACKEND_URL}/backtest/summary",
            params=params,
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        st.error(f"Error fetching summary: {e}")
        return None


def get_backtest_results(metric_code: str, from_date: date = None, to_date: date = None, lead_time: int = None):
    """Get detailed backtest results"""
    try:
        params = {"metric_code": metric_code}
        if from_date:
            params["from_date"] = str(from_date)
        if to_date:
            params["to_date"] = str(to_date)
        if lead_time:
            params["lead_time"] = lead_time

        response = httpx.get(
            f"{BACKEND_URL}/backtest/results",
            params=params,
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception as e:
        st.error(f"Error fetching results: {e}")
        return []


# ============================================
# TAB LAYOUT
# ============================================

tab1, tab2 = st.tabs(["🚀 All Models Historical Forecast", "📊 Pickup Model Detailed Backtest"])


# ============================================
# TAB 1: ALL MODELS HISTORICAL FORECAST
# ============================================

with tab1:
    st.subheader("Run All Models on Historical Dates")

    with st.expander("ℹ️ How This Works", expanded=True):
        st.markdown("""
        This runs **Prophet, XGBoost, and Pickup** models as if it were a specific historical date.

        **Example:** If you select April 1, 2025:
        - All models will only see data from **before** April 1, 2025
        - They will generate 60-day forecasts (April 2 - May 31)
        - These forecasts are stored and can be compared to actual outcomes

        **Use this to populate the Accuracy page** with historical forecast data for model evaluation.
        """)

    st.markdown("---")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.markdown("**Select Historical Dates to Simulate**")

        # Quick presets
        preset = st.radio(
            "Presets",
            ["Custom", "Monthly (Apr-Sep 2025)", "Quarterly 2025"],
            horizontal=True
        )

        if preset == "Monthly (Apr-Sep 2025)":
            default_dates = "2025-04-01,2025-05-01,2025-06-01,2025-07-01,2025-08-01,2025-09-01"
        elif preset == "Quarterly 2025":
            default_dates = "2025-01-01,2025-04-01,2025-07-01,2025-10-01"
        else:
            default_dates = "2025-04-01,2025-07-01"

        simulated_dates = st.text_input(
            "Dates (comma-separated, YYYY-MM-DD)",
            value=default_dates,
            help="Enter dates as YYYY-MM-DD, comma-separated"
        )

    with col2:
        st.markdown("**Options**")

        metrics_options = st.multiselect(
            "Metrics",
            ["hotel_room_nights", "hotel_occupancy_pct", "resos_dinner_covers", "resos_lunch_covers"],
            default=["hotel_room_nights", "hotel_occupancy_pct"],
            format_func=lambda x: {
                "hotel_room_nights": "Room Nights",
                "hotel_occupancy_pct": "Occupancy %",
                "resos_dinner_covers": "Dinner Covers",
                "resos_lunch_covers": "Lunch Covers"
            }.get(x, x)
        )

        models_options = st.multiselect(
            "Models",
            ["prophet", "xgboost", "pickup"],
            default=["prophet", "xgboost", "pickup"],
            format_func=lambda x: x.title()
        )

        forecast_days = st.slider("Forecast Days", 30, 90, 60)

    st.markdown("---")

    if st.button("🚀 Run Historical Forecasts", type="primary", key="run_all_models"):
        metrics_str = ",".join(metrics_options)
        models_str = ",".join(models_options)

        # Count total operations
        num_dates = len([d for d in simulated_dates.split(",") if d.strip()])
        total_ops = num_dates * len(metrics_options) * len(models_options)

        st.info(f"Running {total_ops} forecast operations ({num_dates} dates × {len(metrics_options)} metrics × {len(models_options)} models)")

        with st.spinner(f"Running forecasts... This may take several minutes."):
            result = run_historical_forecasts(simulated_dates, metrics_str, models_str, forecast_days)

            if result:
                st.success(f"✅ Complete! Generated {result.get('total_forecasts', 0)} total forecasts across {result.get('dates_processed', 0)} dates.")

                # Show results summary
                for r in result.get('results', []):
                    if 'error' in r:
                        st.error(f"❌ {r['simulated_today']}: {r['error']}")
                    else:
                        st.markdown(f"**{r['simulated_today']}:** {r.get('total_forecasts', 0)} forecasts")
                        with st.expander(f"Details for {r['simulated_today']}"):
                            for metric, models in r.get('metrics', {}).items():
                                st.write(f"  {metric}:")
                                for model, count in models.items():
                                    if isinstance(count, int):
                                        st.write(f"    - {model}: {count} forecasts")
                                    else:
                                        st.write(f"    - {model}: {count}")

                st.markdown("---")
                st.info("📊 Go to the **Accuracy** page to see how these historical forecasts compare to actual outcomes!")


# ============================================
# TAB 2: PICKUP MODEL DETAILED BACKTEST
# ============================================

with tab2:
    st.subheader("Pickup Model Detailed Backtest")

    # Quick-fill date buttons for backtest periods
    quick_ranges = get_quick_date_ranges()
    st.markdown("**Quick Select Historical Period:**")

    # Initialize session state
    if "bt_from" not in st.session_state:
        st.session_state.bt_from = date.today() - timedelta(days=90)
    if "bt_to" not in st.session_state:
        st.session_state.bt_to = date.today() - timedelta(days=7)

    cols_bt = st.columns(5)
    bt_buttons = ["Last Week", "Last Month", "Last 3 Months", "Last 6 Months", "This Year"]
    for i, name in enumerate(bt_buttons):
        with cols_bt[i]:
            if st.button(name, key=f"bt_quick_{name}", use_container_width=True):
                start, end = quick_ranges[name]
                # Ensure end date is in the past for backtesting
                if end >= date.today():
                    end = date.today() - timedelta(days=7)
                st.session_state.bt_from = start
                st.session_state.bt_to = end
                st.rerun()

    st.markdown("")

    with st.expander("ℹ️ Understanding Pickup Backtesting", expanded=False):
        st.markdown("""
        ### What This Does

        Tests the **Pickup model specifically** by reconstructing historical OTB values
        and comparing predicted vs actual outcomes at various lead times.

        ### Key Metrics

        | Metric | Description |
        |--------|-------------|
        | **MAE** | Mean Absolute Error - average magnitude of errors |
        | **MAPE** | Mean Absolute Percentage Error - average % error |

        ### Use This For
        - Detailed analysis of pickup model accuracy
        - Understanding how accuracy varies by lead time
        - Comparing projection methods (additive vs implied)
        """)

    st.markdown("---")

    # Controls
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])

    with col1:
        metric_code = st.selectbox(
            "Metric",
            ["hotel_room_nights", "hotel_occupancy_pct", "resos_dinner_covers", "resos_lunch_covers"],
            format_func=lambda x: {
                "hotel_room_nights": "Room Nights",
                "hotel_occupancy_pct": "Occupancy %",
                "resos_dinner_covers": "Dinner Covers",
                "resos_lunch_covers": "Lunch Covers"
            }.get(x, x),
            key="pickup_metric"
        )

    with col2:
        from_date = st.date_input("From Date", value=st.session_state.bt_from, key="pickup_from")
        st.session_state.bt_from = from_date

    with col3:
        to_date = st.date_input("To Date", value=st.session_state.bt_to, key="pickup_to")
        st.session_state.bt_to = to_date

    with col4:
        lead_times_input = st.text_input("Lead Times (days)", value="7,14,21,28", key="pickup_leads")

    if st.button("Run Pickup Backtest", type="primary", key="run_pickup"):
        with st.spinner("Running backtest... This may take a moment."):
            result = run_backtest(metric_code, from_date, to_date, lead_times_input)

            if result:
                st.success(f"Backtest complete! Evaluated {result['total_forecasts']} forecasts.")

                summary = result.get('summary', {})
                overall = summary.get('overall', {})

                if overall:
                    st.markdown("### Overall Results")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("MAE", f"{overall.get('mae', 'N/A')}")
                    with col2:
                        st.metric("MAPE", f"{overall.get('mape', 'N/A')}%" if overall.get('mape') else "N/A")
                    with col3:
                        st.metric("Forecasts", overall.get('count', 0))

    st.markdown("---")

    # View existing results
    st.subheader("📊 Pickup Backtest Results")

    summary = get_backtest_summary(metric_code)

    if summary and summary.get('overall', {}).get('count', 0) > 0:
        overall = summary['overall']

        st.markdown(f"**Date Range:** {overall.get('date_range', {}).get('from')} to {overall.get('date_range', {}).get('to')}")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Overall MAE", f"{overall.get('mae', 'N/A')}")
        with col2:
            st.metric("Overall MAPE", f"{overall.get('mape', 'N/A')}%" if overall.get('mape') else "N/A")
        with col3:
            st.metric("Total Forecasts", overall.get('count', 0))

        # By lead time
        st.markdown("### Accuracy by Lead Time")
        lead_data = summary.get('by_lead_time', [])

        if lead_data:
            lead_df = pd.DataFrame(lead_data)

            col1, col2 = st.columns([2, 1])

            with col1:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[f"{row['lead_time']}d" for row in lead_data],
                    y=[row['mae'] for row in lead_data],
                    name='MAE',
                    marker_color='#1f77b4'
                ))
                fig.update_layout(
                    title='MAE by Lead Time',
                    xaxis_title='Lead Time',
                    yaxis_title='Mean Absolute Error',
                    height=300
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.dataframe(
                    lead_df.rename(columns={
                        'lead_time': 'Lead Time',
                        'mae': 'MAE',
                        'mape': 'MAPE %',
                        'count': 'Count'
                    }),
                    hide_index=True,
                    use_container_width=True
                )

        # By method
        st.markdown("### Accuracy by Projection Method")
        method_data = summary.get('by_method', [])

        if method_data:
            method_df = pd.DataFrame(method_data)

            col1, col2 = st.columns([2, 1])

            with col1:
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[row['method'] for row in method_data],
                    y=[row['mae'] for row in method_data],
                    marker_color='#2ca02c'
                ))
                fig.update_layout(
                    title='MAE by Projection Method',
                    xaxis_title='Method',
                    yaxis_title='Mean Absolute Error',
                    height=300
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                st.dataframe(
                    method_df.rename(columns={
                        'method': 'Method',
                        'mae': 'MAE',
                        'mape': 'MAPE %',
                        'count': 'Count'
                    }),
                    hide_index=True,
                    use_container_width=True
                )

        # Detailed results
        st.markdown("---")
        st.markdown("### Detailed Results")

        selected_lead = st.selectbox(
            "Filter by Lead Time",
            [None] + [lt['lead_time'] for lt in lead_data],
            format_func=lambda x: "All" if x is None else f"{x} days",
            key="pickup_lead_filter"
        )

        results = get_backtest_results(metric_code, lead_time=selected_lead)

        if results:
            results_df = pd.DataFrame(results)
            results_df['target_date'] = pd.to_datetime(results_df['target_date'])

            # Scatter plot
            fig_scatter = px.scatter(
                results_df,
                x='actual_value',
                y='projected_value',
                color='projection_method',
                hover_data=['target_date', 'lead_time', 'error'],
                title='Predicted vs Actual Values'
            )
            max_val = max(results_df['actual_value'].max(), results_df['projected_value'].max())
            fig_scatter.add_trace(go.Scatter(
                x=[0, max_val],
                y=[0, max_val],
                mode='lines',
                name='Perfect Prediction',
                line=dict(dash='dash', color='gray')
            ))
            fig_scatter.update_layout(height=400)
            st.plotly_chart(fig_scatter, use_container_width=True)

            # Export
            csv = results_df.to_csv(index=False)
            st.download_button(
                label="📥 Export Results",
                data=csv,
                file_name=f"backtest_{metric_code}.csv",
                mime="text/csv"
            )

    else:
        st.info("No backtest results found. Run a backtest above to generate results.")
