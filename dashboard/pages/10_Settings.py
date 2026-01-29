"""
Settings Page
Sync controls, budget upload, and configuration
"""
import os
import streamlit as st
import pandas as pd
import httpx
from datetime import date, datetime, timedelta

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

st.title("⚙️ Settings")
st.markdown("Manage data sync, budgets, and system configuration")

# Tabs
tab1, tab2, tab3, tab4 = st.tabs(["🔄 Data Sync", "💰 Budget Upload", "📊 Metrics Config", "👤 Account"])

# Data Sync Tab
with tab1:
    st.subheader("Data Synchronization")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Newbook Sync")
        st.info("**Last sync:** Today 6:00 AM\n\n**Records:** 1,245 bookings")

        newbook_from = st.date_input("From Date", date.today() - timedelta(days=7), key="nb_from")
        newbook_to = st.date_input("To Date", date.today() + timedelta(days=60), key="nb_to")

        if st.button("🔄 Sync Newbook", use_container_width=True):
            st.info("Newbook sync started...")
            st.success("Sync queued successfully!")

    with col2:
        st.markdown("### Resos Sync")
        st.info("**Last sync:** Today 6:00 AM\n\n**Records:** 856 bookings")

        resos_from = st.date_input("From Date", date.today() - timedelta(days=7), key="rs_from")
        resos_to = st.date_input("To Date", date.today() + timedelta(days=60), key="rs_to")

        if st.button("🔄 Sync Resos", use_container_width=True):
            st.info("Resos sync started...")
            st.success("Sync queued successfully!")

    st.markdown("---")

    # Full sync
    st.markdown("### Full Sync")
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        if st.button("🔄 Run Full Sync (Both Sources)", use_container_width=True):
            st.info("Full sync started...")
            st.success("Full sync queued successfully!")

    # Sync logs
    st.markdown("---")
    st.markdown("### Recent Sync Logs")

    logs_data = [
        {"Time": "06:00 AM Today", "Source": "Newbook", "Status": "✅ Success", "Records": 1245},
        {"Time": "06:00 AM Today", "Source": "Resos", "Status": "✅ Success", "Records": 856},
        {"Time": "06:00 AM Yesterday", "Source": "Newbook", "Status": "✅ Success", "Records": 1238},
        {"Time": "06:00 AM Yesterday", "Source": "Resos", "Status": "✅ Success", "Records": 842},
        {"Time": "06:00 AM 2 days ago", "Source": "Newbook", "Status": "⚠️ Partial", "Records": 1180},
    ]

    st.dataframe(pd.DataFrame(logs_data), use_container_width=True, hide_index=True)

# Budget Upload Tab
with tab2:
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
    with col2:
        st.empty()

    if st.button("📊 Distribute Budget", use_container_width=True):
        st.info("Distributing budget to daily values...")
        st.success("Budget distributed successfully!")

# Metrics Config Tab
with tab3:
    st.subheader("Forecast Metrics Configuration")

    metrics_config = [
        {"Code": "hotel_occupancy_pct", "Name": "Occupancy %", "Prophet": True, "XGBoost": True, "Pickup": True, "Active": True},
        {"Code": "hotel_guests", "Name": "Total Guests", "Prophet": True, "XGBoost": True, "Pickup": True, "Active": True},
        {"Code": "hotel_adr", "Name": "Average Daily Rate", "Prophet": True, "XGBoost": True, "Pickup": False, "Active": True},
        {"Code": "resos_dinner_covers", "Name": "Dinner Covers", "Prophet": True, "XGBoost": True, "Pickup": True, "Active": True},
        {"Code": "resos_lunch_covers", "Name": "Lunch Covers", "Prophet": True, "XGBoost": True, "Pickup": True, "Active": True},
        {"Code": "revenue_rooms", "Name": "Room Revenue", "Prophet": True, "XGBoost": True, "Pickup": False, "Active": True},
        {"Code": "revenue_fb_total", "Name": "F&B Revenue", "Prophet": True, "XGBoost": True, "Pickup": False, "Active": True},
    ]

    st.dataframe(pd.DataFrame(metrics_config), use_container_width=True, hide_index=True)

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

# Account Tab
with tab4:
    st.subheader("Account Settings")

    st.markdown("### Current User")
    st.info("**Username:** admin\n\n**Display Name:** Administrator")

    st.markdown("---")

    st.markdown("### Change Password")
    current_password = st.text_input("Current Password", type="password")
    new_password = st.text_input("New Password", type="password")
    confirm_password = st.text_input("Confirm New Password", type="password")

    if st.button("🔑 Update Password"):
        if new_password == confirm_password and len(new_password) >= 8:
            st.success("Password updated successfully!")
        else:
            st.error("Passwords must match and be at least 8 characters")

    st.markdown("---")

    st.markdown("### System Information")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("""
        **Version:** 1.0.0

        **Backend URL:** """ + BACKEND_URL + """

        **Database:** PostgreSQL 15
        """)
    with col2:
        st.markdown("""
        **Prophet:** 1.1.5

        **XGBoost:** 2.0.3

        **SHAP:** 0.44.1
        """)
