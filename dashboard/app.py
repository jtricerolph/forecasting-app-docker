"""
Forecasting Dashboard - Main Streamlit Application
"""
import os
import sys
import streamlit as st
import httpx
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

# Add components to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from components.auth import (
    init_session_state, save_token_to_cookie, clear_token_cookie,
    get_auth_header
)

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

# Page config
st.set_page_config(
    page_title="Forecasting Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1rem;
        margin: 0.5rem 0;
    }
    .stMetric {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


def login_page():
    """Display login form"""
    st.markdown('<p class="main-header">📊 Forecasting Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Hotel & Restaurant Forecasting System</p>', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])

    with col2:
        st.markdown("### Login")

        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)

            if submitted:
                if username and password:
                    try:
                        response = httpx.post(
                            f"{BACKEND_URL}/auth/login",
                            json={"username": username, "password": password},
                            timeout=10.0
                        )
                        if response.status_code == 200:
                            data = response.json()
                            st.session_state.token = data["access_token"]

                            # Save token to cookie for persistence
                            save_token_to_cookie(data["access_token"])

                            # Get user info
                            user_response = httpx.get(
                                f"{BACKEND_URL}/auth/me",
                                headers={"Authorization": f"Bearer {st.session_state.token}"},
                                timeout=10.0
                            )
                            if user_response.status_code == 200:
                                st.session_state.user = user_response.json()
                                st.rerun()
                        else:
                            st.error("Invalid username or password")
                    except Exception as e:
                        st.error(f"Connection error: {e}")
                else:
                    st.warning("Please enter username and password")


@st.cache_data(ttl=60)
def fetch_historical_summary(from_date, to_date, _headers):
    """Fetch historical summary data"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/historical/summary",
            params={"from_date": str(from_date), "to_date": str(to_date)},
            headers=_headers,
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []


@st.cache_data(ttl=60)
def fetch_forecasts(from_date, to_date, metric, _headers):
    """Fetch forecast data"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/forecast/comparison",
            params={"from_date": str(from_date), "to_date": str(to_date), "metric": metric},
            headers=_headers,
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return []
    except Exception:
        return []


@st.cache_data(ttl=60)
def fetch_accuracy(from_date, to_date, _headers):
    """Fetch accuracy data"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/accuracy/summary",
            params={"from_date": str(from_date), "to_date": str(to_date)},
            headers=_headers,
            timeout=30.0
        )
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception:
        return {}


@st.cache_data(ttl=60)
def fetch_sync_status(_headers):
    """Fetch sync status"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/sync/status",
            headers=_headers,
            timeout=10.0
        )
        if response.status_code == 200:
            return response.json()
        return {}
    except Exception:
        return {}


def main_dashboard():
    """Main dashboard view after login"""
    headers = get_auth_header()

    # Sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user.get('display_name', 'User')}")
        st.markdown("---")

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.token = None
            st.session_state.user = None
            clear_token_cookie()
            st.rerun()

        st.markdown("---")

        with st.expander("ℹ️ Dashboard Help"):
            st.markdown("""
            **Welcome to the Forecasting Dashboard!**

            This system forecasts hotel occupancy and restaurant demand using multiple models:

            - **XGBoost**: Machine learning model
            - **Pickup**: Real-time booking pace
            - **Prophet**: Time series forecasting

            **Pages:**
            - 📅 Daily Forecast
            - 📊 Weekly Summary
            - 🔄 Model Comparison
            - 📈 Pickup Analysis
            - 📉 Forecast Evolution
            - 🔗 Cross Reference
            - 💰 Budget Variance
            - 📊 Trends
            - 🎯 Accuracy
            - ⚙️ Settings
            """)

    # Main content
    st.markdown('<p class="main-header">📊 Forecasting Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Hotel & Restaurant Forecasting Overview</p>', unsafe_allow_html=True)

    # Fetch today's data
    today = date.today()
    yesterday = today - timedelta(days=1)

    historical = fetch_historical_summary(yesterday, today, headers)
    occ_forecasts = fetch_forecasts(today, today + timedelta(days=14), "hotel_occupancy_pct", headers)
    dinner_forecasts = fetch_forecasts(today, today + timedelta(days=14), "resos_dinner_covers", headers)
    accuracy = fetch_accuracy(today - timedelta(days=30), today, headers)
    sync_status = fetch_sync_status(headers)

    # Quick stats
    st.subheader("📊 Today's Overview")

    col1, col2, col3, col4 = st.columns(4)

    # Today's occupancy from forecast
    today_occ = None
    if occ_forecasts:
        for fc in occ_forecasts:
            if fc.get('date') == str(today):
                models = fc.get('models', {})
                today_occ = models.get('xgboost', {}).get('value') or models.get('pickup', {}).get('value')
                break

    with col1:
        st.metric(
            label="Today's Occupancy Forecast",
            value=f"{today_occ:.0f}%" if today_occ else "N/A",
            help="XGBoost or Pickup model forecast for today's occupancy"
        )

    # Today's dinner covers from forecast
    today_dinner = None
    if dinner_forecasts:
        for fc in dinner_forecasts:
            if fc.get('date') == str(today):
                models = fc.get('models', {})
                today_dinner = models.get('xgboost', {}).get('value') or models.get('pickup', {}).get('value')
                break

    with col2:
        st.metric(
            label="Dinner Covers Forecast",
            value=f"{today_dinner:.0f}" if today_dinner else "N/A",
            help="Forecasted restaurant covers for tonight's dinner service"
        )

    # Yesterday's actual (for comparison)
    yesterday_occ = None
    if historical:
        for h in historical:
            if h.get('date') == str(yesterday):
                yesterday_occ = h.get('occupancy_pct')
                break

    with col3:
        st.metric(
            label="Yesterday's Actual",
            value=f"{yesterday_occ:.0f}%" if yesterday_occ else "N/A",
            help="Actual occupancy from yesterday (latest available)"
        )

    # Accuracy metric
    avg_accuracy = None
    if accuracy and 'by_model' in accuracy:
        mapes = [m.get('mape', 100) for m in accuracy['by_model'] if m.get('mape')]
        if mapes:
            avg_accuracy = 100 - min(mapes)  # Convert MAPE to accuracy

    with col4:
        st.metric(
            label="Best Model Accuracy",
            value=f"{avg_accuracy:.0f}%" if avg_accuracy else "N/A",
            help="Accuracy of best performing model over past 30 days (100% - MAPE)"
        )

    st.markdown("---")

    # Quick forecast table
    st.subheader("📅 Next 7 Days Forecast")
    st.caption("_XGBoost model predictions for the coming week_")

    col1, col2 = st.columns([2, 1])

    with col1:
        # Build forecast table
        forecast_table = []
        dates = pd.date_range(start=today, periods=7, freq='D')

        for d in dates:
            row = {'Date': d.strftime('%a %d %b')}

            # Get occupancy
            for fc in occ_forecasts or []:
                if fc.get('date') == str(d.date()):
                    models = fc.get('models', {})
                    row['Occupancy %'] = models.get('xgboost', {}).get('value')
                    break

            # Get dinner covers
            for fc in dinner_forecasts or []:
                if fc.get('date') == str(d.date()):
                    models = fc.get('models', {})
                    row['Dinner Covers'] = models.get('xgboost', {}).get('value')
                    break

            forecast_table.append(row)

        forecast_df = pd.DataFrame(forecast_table)

        st.dataframe(
            forecast_df.style.format({
                'Occupancy %': '{:.0f}%' if 'Occupancy %' in forecast_df.columns else '{}',
                'Dinner Covers': '{:.0f}' if 'Dinner Covers' in forecast_df.columns else '{}'
            }, na_rep='-'),
            use_container_width=True,
            hide_index=True
        )

    with col2:
        st.markdown("### Quick Actions")
        if st.button("🔄 Refresh Forecasts", use_container_width=True):
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/forecast/regenerate",
                    params={"from_date": str(today), "to_date": str(today + timedelta(days=30))},
                    headers=headers,
                    timeout=10.0
                )
                if response.status_code == 200:
                    st.success("Forecast refresh started!")
                    st.cache_data.clear()
                else:
                    st.error("Failed to trigger refresh")
            except Exception as e:
                st.error(f"Error: {e}")

        if st.button("📊 View Full Report", use_container_width=True):
            st.info("Navigate to pages in sidebar for detailed reports")

        with st.expander("ℹ️ Table Help"):
            st.markdown("""
            - **Occupancy %**: Predicted room occupancy
            - **Dinner Covers**: Expected restaurant covers

            Values are XGBoost model forecasts.
            For model comparison, see the Model Comparison page.
            """)

    st.markdown("---")

    # Charts row
    st.subheader("📈 14-Day Forecast Trends")

    col1, col2 = st.columns(2)

    with col1:
        # Occupancy chart
        if occ_forecasts:
            fc_df = pd.DataFrame(occ_forecasts)
            fc_df['date'] = pd.to_datetime(fc_df['date'])
            fc_df = fc_df.sort_values('date')

            fig = go.Figure()

            # Extract model values
            xgb_vals = [fc.get('models', {}).get('xgboost', {}).get('value') for fc in occ_forecasts]
            pickup_vals = [fc.get('models', {}).get('pickup', {}).get('value') for fc in occ_forecasts]

            if any(v is not None for v in xgb_vals):
                fig.add_trace(go.Scatter(
                    x=fc_df['date'],
                    y=xgb_vals,
                    name='XGBoost',
                    line=dict(color='#ff7f0e', width=2)
                ))

            if any(v is not None for v in pickup_vals):
                fig.add_trace(go.Scatter(
                    x=fc_df['date'],
                    y=pickup_vals,
                    name='Pickup',
                    line=dict(color='#2ca02c', width=2)
                ))

            fig.add_vline(x=today, line_dash="dot", line_color="gray")

            fig.update_layout(
                title='Occupancy Forecast',
                xaxis_title='Date',
                yaxis_title='Occupancy %',
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                margin=dict(l=0, r=0, t=40, b=0),
                height=350
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No occupancy forecasts available. Generate forecasts in Settings.")

    with col2:
        # Covers chart
        if dinner_forecasts:
            fig2 = go.Figure()

            # Extract values
            xgb_dinner = [fc.get('models', {}).get('xgboost', {}).get('value') for fc in dinner_forecasts]
            dates = [fc.get('date') for fc in dinner_forecasts]

            if any(v is not None for v in xgb_dinner):
                fig2.add_trace(go.Bar(
                    x=dates,
                    y=xgb_dinner,
                    name='Dinner',
                    marker_color='#1f77b4'
                ))

            fig2.update_layout(
                title='Dinner Covers Forecast',
                xaxis_title='Date',
                yaxis_title='Covers',
                margin=dict(l=0, r=0, t=40, b=0),
                height=350
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No dinner cover forecasts available. Generate forecasts in Settings.")

    # Sync status
    st.markdown("---")
    st.subheader("🔄 System Status")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        newbook_sync = sync_status.get('newbook_bookings', {})
        last_sync = newbook_sync.get('last_sync', 'Never')
        status = newbook_sync.get('status', 'unknown')
        color = "success" if status == 'completed' else "warning" if status == 'running' else "error"
        getattr(st, color)(f"**Newbook Sync**\n\n{last_sync[:16] if last_sync != 'Never' else 'Never'}")

    with col2:
        resos_sync = sync_status.get('resos_bookings', {})
        last_sync = resos_sync.get('last_sync', 'Never')
        status = resos_sync.get('status', 'unknown')
        color = "success" if status == 'completed' else "warning" if status == 'running' else "error"
        getattr(st, color)(f"**Resos Sync**\n\n{last_sync[:16] if last_sync != 'Never' else 'Never'}")

    with col3:
        occ_sync = sync_status.get('newbook_occupancy_report', {})
        last_sync = occ_sync.get('last_sync', 'Never')
        status = occ_sync.get('status', 'unknown')
        color = "success" if status == 'completed' else "warning" if status == 'running' else "error"
        getattr(st, color)(f"**Occupancy Report**\n\n{last_sync[:16] if last_sync != 'Never' else 'Never'}")

    with col4:
        st.info(f"**Backend Status**\n\nHealthy")

    # Footer help
    st.markdown("---")
    with st.expander("📖 Dashboard Guide"):
        st.markdown("""
        ### Understanding the Dashboard

        **Quick Stats** show today's key metrics:
        - Forecasted occupancy and covers
        - Yesterday's actual results for comparison
        - Model accuracy over the past 30 days

        **7-Day Forecast Table** shows XGBoost predictions for the next week.

        **Trend Charts** display 14-day forecasts from multiple models.

        **System Status** shows when data was last synced from source systems.

        ### Navigation

        Use the sidebar to access detailed pages:
        - **Daily Forecast**: Detailed day-by-day forecasts
        - **Weekly Summary**: Aggregated weekly trends
        - **Model Comparison**: Compare XGBoost vs Pickup
        - **Pickup Analysis**: Booking pace analysis
        - **Accuracy**: Model performance tracking
        - **Settings**: Configuration and data sync

        ### Data Sources

        - **Newbook**: Hotel bookings, occupancy, revenue
        - **Resos**: Restaurant reservations
        - **Forecasts**: Generated daily at 6 AM
        """)


def main():
    """Main application entry point"""
    init_session_state()

    if st.session_state.token is None:
        login_page()
    else:
        main_dashboard()


if __name__ == "__main__":
    main()
