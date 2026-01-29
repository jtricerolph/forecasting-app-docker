"""
Forecasting Dashboard - Main Streamlit Application
"""
import os
import streamlit as st
import httpx
from datetime import date, timedelta

# Configuration
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

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


def init_session_state():
    """Initialize session state variables"""
    if "token" not in st.session_state:
        st.session_state.token = None
    if "user" not in st.session_state:
        st.session_state.user = None


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


def main_dashboard():
    """Main dashboard view after login"""
    # Sidebar
    with st.sidebar:
        st.markdown(f"### 👤 {st.session_state.user.get('display_name', 'User')}")
        st.markdown("---")

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.token = None
            st.session_state.user = None
            st.rerun()

        st.markdown("---")
        st.markdown("### Navigation")
        st.markdown("""
        - 📅 Daily Forecast
        - 📊 Weekly Summary
        - 🔄 Model Comparison
        - 📈 Pickup Analysis
        - 📉 Forecast Evolution
        - ✅ Cross-Reference
        - 💰 Budget Variance
        - 📈 Trends
        - 🎯 Accuracy
        - ⚙️ Settings
        """)

    # Main content
    st.markdown('<p class="main-header">📊 Forecasting Dashboard</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Hotel & Restaurant Forecasting Overview</p>', unsafe_allow_html=True)

    # Quick stats
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            label="Today's Occupancy",
            value="85%",
            delta="+5% vs forecast"
        )

    with col2:
        st.metric(
            label="Dinner Covers Tonight",
            value="142",
            delta="+12 vs last week"
        )

    with col3:
        st.metric(
            label="Week Revenue Forecast",
            value="£45,230",
            delta="+8% vs budget"
        )

    with col4:
        st.metric(
            label="Model Accuracy (7d)",
            value="94%",
            delta="+2%"
        )

    st.markdown("---")

    # Quick forecast table
    st.subheader("📅 Next 7 Days Forecast")

    col1, col2 = st.columns([2, 1])

    with col1:
        # Sample forecast data
        import pandas as pd
        import plotly.graph_objects as go

        dates = pd.date_range(start=date.today(), periods=7, freq='D')
        forecast_data = pd.DataFrame({
            'Date': dates,
            'Occupancy %': [85, 88, 92, 90, 75, 82, 87],
            'Dinner Covers': [142, 156, 168, 152, 98, 125, 145],
            'Lunch Covers': [45, 52, 58, 55, 35, 42, 48]
        })

        st.dataframe(
            forecast_data.style.format({
                'Occupancy %': '{:.0f}%',
                'Dinner Covers': '{:.0f}',
                'Lunch Covers': '{:.0f}'
            }),
            use_container_width=True,
            hide_index=True
        )

    with col2:
        st.markdown("### Quick Actions")
        if st.button("🔄 Refresh Forecasts", use_container_width=True):
            st.info("Triggering forecast refresh...")

        if st.button("📥 Export to Excel", use_container_width=True):
            st.info("Preparing export...")

        if st.button("📊 Full Report", use_container_width=True):
            st.info("Generating report...")

    st.markdown("---")

    # Charts row
    st.subheader("📈 Forecast Trends")

    col1, col2 = st.columns(2)

    with col1:
        # Occupancy chart
        import plotly.express as px

        dates = pd.date_range(start=date.today(), periods=14, freq='D')
        occ_data = pd.DataFrame({
            'Date': dates,
            'Prophet': [85, 88, 92, 90, 75, 82, 87, 89, 91, 88, 72, 78, 85, 88],
            'XGBoost': [83, 86, 90, 88, 73, 80, 85, 87, 89, 86, 70, 76, 83, 86],
            'Pickup': [86, 89, 93, 91, 76, 83, 88, 90, 92, 89, 73, 79, 86, 89],
            'Budget': [80, 80, 85, 85, 70, 75, 80, 80, 85, 85, 70, 75, 80, 80]
        })

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=occ_data['Date'], y=occ_data['Prophet'],
                                  name='Prophet', line=dict(color='#1f77b4', width=2)))
        fig.add_trace(go.Scatter(x=occ_data['Date'], y=occ_data['XGBoost'],
                                  name='XGBoost', line=dict(color='#ff7f0e', width=2)))
        fig.add_trace(go.Scatter(x=occ_data['Date'], y=occ_data['Pickup'],
                                  name='Pickup', line=dict(color='#2ca02c', width=2)))
        fig.add_trace(go.Scatter(x=occ_data['Date'], y=occ_data['Budget'],
                                  name='Budget', line=dict(color='#d62728', width=2, dash='dash')))

        fig.update_layout(
            title='Occupancy Forecast by Model',
            xaxis_title='Date',
            yaxis_title='Occupancy %',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            margin=dict(l=0, r=0, t=40, b=0),
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # Covers chart
        covers_data = pd.DataFrame({
            'Date': dates,
            'Dinner': [142, 156, 168, 152, 98, 125, 145, 150, 160, 155, 95, 120, 140, 148],
            'Lunch': [45, 52, 58, 55, 35, 42, 48, 50, 54, 52, 32, 40, 45, 50]
        })

        fig2 = go.Figure()
        fig2.add_trace(go.Bar(x=covers_data['Date'], y=covers_data['Dinner'],
                              name='Dinner', marker_color='#1f77b4'))
        fig2.add_trace(go.Bar(x=covers_data['Date'], y=covers_data['Lunch'],
                              name='Lunch', marker_color='#ff7f0e'))

        fig2.update_layout(
            title='Covers Forecast',
            xaxis_title='Date',
            yaxis_title='Covers',
            barmode='group',
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            margin=dict(l=0, r=0, t=40, b=0),
            height=350
        )
        st.plotly_chart(fig2, use_container_width=True)

    # Sync status
    st.markdown("---")
    st.subheader("🔄 System Status")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.info("**Last Newbook Sync:** 6:00 AM Today")

    with col2:
        st.info("**Last Resos Sync:** 6:00 AM Today")

    with col3:
        st.success("**Last Forecast Run:** 6:15 AM Today")


def main():
    """Main application entry point"""
    init_session_state()

    if st.session_state.token is None:
        login_page()
    else:
        main_dashboard()


if __name__ == "__main__":
    main()
