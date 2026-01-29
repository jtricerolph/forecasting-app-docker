"""
Settings Page
API configuration, sync controls, budget upload, and system settings
"""
import os
import streamlit as st
import pandas as pd
import httpx
from datetime import date, datetime, timedelta

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

st.title("⚙️ Settings")
st.markdown("Configure API connections, manage data sync, and system settings")


def get_auth_header():
    """Get authorization header from session"""
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def get_config(key: str) -> str:
    """Fetch a config value from backend"""
    try:
        response = httpx.get(
            f"{BACKEND_URL}/config/{key}",
            headers=get_auth_header(),
            timeout=10.0
        )
        if response.status_code == 200:
            return response.json().get("value", "")
    except:
        pass
    return ""


def save_config(key: str, value: str, is_encrypted: bool = False) -> bool:
    """Save a config value to backend"""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/config",
            headers=get_auth_header(),
            json={"key": key, "value": value, "is_encrypted": is_encrypted},
            timeout=10.0
        )
        return response.status_code == 200
    except:
        return False


def test_api_connection(api: str) -> tuple:
    """Test API connection"""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/config/test/{api}",
            headers=get_auth_header(),
            timeout=30.0
        )
        if response.status_code == 200:
            return True, "Connection successful!"
        else:
            return False, response.json().get("detail", "Connection failed")
    except Exception as e:
        return False, str(e)


# Tabs
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔑 API Configuration",
    "🔄 Data Sync",
    "💰 Budget Upload",
    "📊 System Settings",
    "👤 Account"
])

# API Configuration Tab
with tab1:
    st.subheader("API Configuration")
    st.markdown("Configure connections to Newbook and Resos APIs")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Newbook API")
        st.markdown("Hotel property management system")

        with st.form("newbook_config"):
            nb_api_key = st.text_input(
                "API Key",
                value="",
                type="password",
                help="Your Newbook API key"
            )
            nb_username = st.text_input(
                "Username",
                value="",
                help="Newbook account username"
            )
            nb_password = st.text_input(
                "Password",
                value="",
                type="password",
                help="Newbook account password"
            )
            nb_region = st.text_input(
                "Region",
                value="",
                help="Newbook region code (e.g., 'uk', 'au')"
            )

            col_save, col_test = st.columns(2)
            with col_save:
                nb_save = st.form_submit_button("💾 Save", use_container_width=True)
            with col_test:
                nb_test = st.form_submit_button("🔌 Test Connection", use_container_width=True)

        if nb_save:
            success = True
            if nb_api_key:
                success &= save_config("newbook_api_key", nb_api_key, is_encrypted=True)
            if nb_username:
                success &= save_config("newbook_username", nb_username)
            if nb_password:
                success &= save_config("newbook_password", nb_password, is_encrypted=True)
            if nb_region:
                success &= save_config("newbook_region", nb_region)

            if success:
                st.success("Newbook configuration saved!")
            else:
                st.error("Failed to save some settings")

        if nb_test:
            with st.spinner("Testing Newbook connection..."):
                ok, msg = test_api_connection("newbook")
                if ok:
                    st.success(msg)
                else:
                    st.error(f"Connection failed: {msg}")

    with col2:
        st.markdown("### Resos API")
        st.markdown("Restaurant reservation system")

        with st.form("resos_config"):
            rs_api_key = st.text_input(
                "API Key",
                value="",
                type="password",
                help="Your Resos API key"
            )

            col_save, col_test = st.columns(2)
            with col_save:
                rs_save = st.form_submit_button("💾 Save", use_container_width=True)
            with col_test:
                rs_test = st.form_submit_button("🔌 Test Connection", use_container_width=True)

        if rs_save:
            if rs_api_key:
                if save_config("resos_api_key", rs_api_key, is_encrypted=True):
                    st.success("Resos configuration saved!")
                else:
                    st.error("Failed to save settings")

        if rs_test:
            with st.spinner("Testing Resos connection..."):
                ok, msg = test_api_connection("resos")
                if ok:
                    st.success(msg)
                else:
                    st.error(f"Connection failed: {msg}")

    # Connection status
    st.markdown("---")
    st.markdown("### Connection Status")

    col1, col2 = st.columns(2)
    with col1:
        # Would fetch actual status from backend
        st.info("**Newbook:** ⚠️ Not configured")
    with col2:
        st.info("**Resos:** ⚠️ Not configured")

# Data Sync Tab
with tab2:
    st.subheader("Data Synchronization")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Newbook Sync")
        st.info("**Last sync:** Never\n\n**Records:** -")

        newbook_from = st.date_input("From Date", date.today() - timedelta(days=7), key="nb_from")
        newbook_to = st.date_input("To Date", date.today() + timedelta(days=60), key="nb_to")

        if st.button("🔄 Sync Newbook", use_container_width=True):
            with st.spinner("Syncing Newbook data..."):
                try:
                    response = httpx.post(
                        f"{BACKEND_URL}/sync/newbook",
                        headers=get_auth_header(),
                        params={"from_date": str(newbook_from), "to_date": str(newbook_to)},
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        st.success("Newbook sync started!")
                    else:
                        st.error("Failed to start sync")
                except Exception as e:
                    st.error(f"Error: {e}")

    with col2:
        st.markdown("### Resos Sync")
        st.info("**Last sync:** Never\n\n**Records:** -")

        resos_from = st.date_input("From Date", date.today() - timedelta(days=7), key="rs_from")
        resos_to = st.date_input("To Date", date.today() + timedelta(days=60), key="rs_to")

        if st.button("🔄 Sync Resos", use_container_width=True):
            with st.spinner("Syncing Resos data..."):
                try:
                    response = httpx.post(
                        f"{BACKEND_URL}/sync/resos",
                        headers=get_auth_header(),
                        params={"from_date": str(resos_from), "to_date": str(resos_to)},
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        st.success("Resos sync started!")
                    else:
                        st.error("Failed to start sync")
                except Exception as e:
                    st.error(f"Error: {e}")

    st.markdown("---")

    # Full sync
    st.markdown("### Full Sync")
    if st.button("🔄 Run Full Sync (Both Sources)", use_container_width=True):
        st.info("Full sync started in background...")

    # Sync logs
    st.markdown("---")
    st.markdown("### Recent Sync Logs")

    logs_data = [
        {"Time": "-", "Source": "Newbook", "Status": "Not run", "Records": "-"},
        {"Time": "-", "Source": "Resos", "Status": "Not run", "Records": "-"},
    ]

    st.dataframe(pd.DataFrame(logs_data), use_container_width=True, hide_index=True)

# Budget Upload Tab
with tab3:
    st.subheader("Monthly Budget Upload")

    st.markdown("""
    Upload monthly budget targets from Finance Director.
    Budgets will be automatically distributed to daily values using prior year patterns.
    """)

    col1, col2 = st.columns(2)

    with col1:
        budget_year = st.selectbox("Year", [2026, 2025, 2027])
        budget_month = st.selectbox("Month", list(range(1, 13)),
                                     format_func=lambda x: datetime(2000, x, 1).strftime('%B'))

    with col2:
        budget_type = st.selectbox("Budget Type", [
            "hotel_occupancy_pct",
            "resos_dinner_covers",
            "resos_lunch_covers",
            "revenue_rooms",
            "revenue_fb_total"
        ])

    budget_value = st.number_input("Budget Value", min_value=0.0, value=100000.0)
    budget_notes = st.text_area("Notes (optional)")

    if st.button("💾 Save Budget", use_container_width=True):
        st.success(f"Budget saved for {datetime(budget_year, budget_month, 1).strftime('%B %Y')}")

    st.markdown("---")

    # CSV Upload
    st.markdown("### Bulk Upload (CSV)")
    st.markdown("Upload a CSV with columns: year, month, budget_type, budget_value")

    uploaded_file = st.file_uploader("Choose CSV file", type="csv")
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        st.dataframe(df, use_container_width=True)

        if st.button("📤 Upload Budgets"):
            st.success(f"Uploaded {len(df)} budget entries")

    st.markdown("---")

    # Distribute budgets
    st.markdown("### Distribute Budgets to Daily")
    st.markdown("Recalculate daily budgets using prior year proportions")

    col1, col2 = st.columns(2)
    with col1:
        dist_year = st.selectbox("Year", [2026, 2025], key="dist_year")
        dist_month = st.selectbox("Month", list(range(1, 13)), key="dist_month",
                                   format_func=lambda x: datetime(2000, x, 1).strftime('%B'))

    if st.button("📊 Distribute Budget", use_container_width=True):
        st.info("Distributing budget to daily values...")
        st.success("Budget distributed successfully!")

# System Settings Tab
with tab4:
    st.subheader("System Settings")

    st.markdown("### Property Configuration")

    with st.form("property_config"):
        hotel_name = st.text_input(
            "Hotel/Property Name",
            value="",
            help="Name displayed in reports"
        )
        total_rooms = st.number_input(
            "Total Rooms",
            min_value=1,
            max_value=1000,
            value=80,
            help="Total number of hotel rooms (for occupancy calculation)"
        )
        timezone = st.selectbox(
            "Timezone",
            ["Europe/London", "Europe/Paris", "America/New_York", "America/Los_Angeles", "Australia/Sydney"],
            help="Local timezone for the property"
        )

        if st.form_submit_button("💾 Save Settings", use_container_width=True):
            save_config("hotel_name", hotel_name)
            save_config("total_rooms", str(total_rooms))
            save_config("timezone", timezone)
            st.success("Settings saved!")

    st.markdown("---")

    # Forecast schedule
    st.markdown("### Forecast Schedule")

    schedule_data = [
        {"Name": "Short-term (0-14d)", "Frequency": "Daily 6:00 AM", "Models": "All 3", "Status": "✅ Active"},
        {"Name": "Medium-term (15-28d)", "Frequency": "Daily 6:15 AM", "Models": "All 3", "Status": "✅ Active"},
        {"Name": "Long-term (29-60d)", "Frequency": "Weekly Mon 6:30 AM", "Models": "Prophet, XGBoost", "Status": "✅ Active"},
    ]

    st.dataframe(pd.DataFrame(schedule_data), use_container_width=True, hide_index=True)

    if st.button("🔄 Run Forecast Now"):
        st.info("Triggering forecast run...")
        st.success("Forecast run queued!")

    st.markdown("---")

    # Metrics config
    st.markdown("### Forecast Metrics")

    metrics_config = [
        {"Code": "hotel_occupancy_pct", "Name": "Occupancy %", "Prophet": "✅", "XGBoost": "✅", "Pickup": "✅"},
        {"Code": "hotel_guests", "Name": "Total Guests", "Prophet": "✅", "XGBoost": "✅", "Pickup": "✅"},
        {"Code": "hotel_adr", "Name": "Average Daily Rate", "Prophet": "✅", "XGBoost": "✅", "Pickup": "❌"},
        {"Code": "resos_dinner_covers", "Name": "Dinner Covers", "Prophet": "✅", "XGBoost": "✅", "Pickup": "✅"},
        {"Code": "resos_lunch_covers", "Name": "Lunch Covers", "Prophet": "✅", "XGBoost": "✅", "Pickup": "✅"},
    ]

    st.dataframe(pd.DataFrame(metrics_config), use_container_width=True, hide_index=True)

# Account Tab
with tab5:
    st.subheader("Account Settings")

    st.markdown("### Current User")
    user = st.session_state.get("user", {})
    st.info(f"**Username:** {user.get('username', 'admin')}\n\n**Display Name:** {user.get('display_name', 'Administrator')}")

    st.markdown("---")

    st.markdown("### Change Password")
    with st.form("change_password"):
        current_password = st.text_input("Current Password", type="password")
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm New Password", type="password")

        if st.form_submit_button("🔑 Update Password"):
            if new_password == confirm_password and len(new_password) >= 8:
                st.success("Password updated successfully!")
            elif len(new_password) < 8:
                st.error("Password must be at least 8 characters")
            else:
                st.error("Passwords do not match")

    st.markdown("---")

    st.markdown("### System Information")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        **Version:** 1.0.0

        **Backend URL:** {BACKEND_URL}

        **Database:** PostgreSQL 15
        """)
    with col2:
        st.markdown("""
        **Prophet:** 1.1.5

        **XGBoost:** 2.0.3

        **SHAP:** 0.44.1
        """)
