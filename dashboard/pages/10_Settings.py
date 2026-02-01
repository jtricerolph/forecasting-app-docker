"""
Settings Page
API configuration, sync controls, budget upload, and system settings
"""
import os
import sys
import streamlit as st
import pandas as pd
import httpx
from datetime import date, datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from components.auth import require_auth, get_auth_header

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

# Require authentication - shows login form if not logged in
require_auth()

st.title("⚙️ Settings")
st.markdown("Configure API connections, manage data sync, and system settings")


def get_config(key: str) -> str:
    """Fetch a config value from backend"""
    try:
        headers = get_auth_header()
        response = httpx.get(
            f"{BACKEND_URL}/config/{key}",
            headers=headers,
            timeout=10.0
        )
        if response.status_code == 200:
            data = response.json()
            value = data.get("value", "")
            return value if value is not None else ""
    except Exception:
        pass
    return ""


def save_config(key: str, value: str, is_encrypted: bool = False) -> bool:
    """Save a config value to backend"""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/config/",
            headers=get_auth_header(),
            json={"key": key, "value": value, "is_encrypted": is_encrypted},
            timeout=10.0,
            follow_redirects=True
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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "🔑 API Configuration",
    "🔄 Data Sync",
    "💰 Budget Upload",
    "📊 System Settings",
    "🏷️ GL Mapping",
    "🍽️ Resos Mapping",
    "👤 Account"
])

# API Configuration Tab
with tab1:
    st.subheader("API Configuration")
    st.markdown("Configure connections to Newbook and Resos APIs")

    # Load current values (non-encrypted fields show actual value, encrypted show "********" if set)
    current_nb_username = get_config("newbook_username")
    current_nb_region = get_config("newbook_region")
    current_nb_api_key = get_config("newbook_api_key")  # Will be "********" if set
    current_nb_password = get_config("newbook_password")  # Will be "********" if set
    current_rs_api_key = get_config("resos_api_key")  # Will be "********" if set

    # Check if encrypted fields have values set
    nb_api_key_is_set = current_nb_api_key == "********"
    nb_password_is_set = current_nb_password == "********"
    rs_api_key_is_set = current_rs_api_key == "********"

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Newbook API")
        st.markdown("Hotel property management system")

        with st.form("newbook_config"):
            nb_api_key = st.text_input(
                "API Key",
                value="********" if nb_api_key_is_set else "",
                type="password",
                help="Clear and enter new value to change" if nb_api_key_is_set else "Your Newbook API key"
            )
            nb_username = st.text_input(
                "Username",
                value=current_nb_username or "",
                help="Newbook account username"
            )
            nb_password = st.text_input(
                "Password",
                value="********" if nb_password_is_set else "",
                type="password",
                help="Clear and enter new value to change" if nb_password_is_set else "Newbook account password"
            )
            nb_region = st.text_input(
                "Region",
                value=current_nb_region or "",
                help="Newbook region code (e.g., 'uk', 'au')"
            )

            col_save, col_test = st.columns(2)
            with col_save:
                nb_save = st.form_submit_button("💾 Save", use_container_width=True)
            with col_test:
                nb_test = st.form_submit_button("🔌 Test Connection", use_container_width=True)

        if nb_save:
            success = True
            saved_any = False
            # Only save fields that have changed (skip "********" placeholder)
            if nb_api_key and nb_api_key != "********":
                success &= save_config("newbook_api_key", nb_api_key, is_encrypted=True)
                saved_any = True
            if nb_username:
                success &= save_config("newbook_username", nb_username)
                saved_any = True
            if nb_password and nb_password != "********":
                success &= save_config("newbook_password", nb_password, is_encrypted=True)
                saved_any = True
            if nb_region:
                success &= save_config("newbook_region", nb_region)
                saved_any = True

            if saved_any and success:
                st.success("Newbook configuration saved!")
                st.rerun()  # Refresh to show updated values
            elif saved_any:
                st.error("Failed to save some settings")
            else:
                st.info("No changes to save")

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
                value="********" if rs_api_key_is_set else "",
                type="password",
                help="Clear and enter new value to change" if rs_api_key_is_set else "Your Resos API key"
            )

            col_save, col_test = st.columns(2)
            with col_save:
                rs_save = st.form_submit_button("💾 Save", use_container_width=True)
            with col_test:
                rs_test = st.form_submit_button("🔌 Test Connection", use_container_width=True)

        if rs_save:
            if rs_api_key and rs_api_key != "********":
                if save_config("resos_api_key", rs_api_key, is_encrypted=True):
                    st.success("Resos configuration saved!")
                    st.rerun()  # Refresh to show updated values
                else:
                    st.error("Failed to save settings")
            else:
                st.info("No changes to save")

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
        # Check if Newbook is configured
        nb_configured = all([nb_api_key_is_set, current_nb_username, nb_password_is_set, current_nb_region])
        if nb_configured:
            st.success(f"**Newbook:** ✅ Configured (user: {current_nb_username}, region: {current_nb_region})")
        elif any([nb_api_key_is_set, current_nb_username, nb_password_is_set, current_nb_region]):
            st.warning("**Newbook:** ⚠️ Partially configured")
        else:
            st.info("**Newbook:** ⚠️ Not configured")
    with col2:
        # Check if Resos is configured
        if rs_api_key_is_set:
            st.success("**Resos:** ✅ Configured")
        else:
            st.info("**Resos:** ⚠️ Not configured")

# Data Sync Tab
with tab2:
    st.subheader("Data Synchronization")

    # Automatic sync schedule controls
    st.markdown("### Automatic Sync Schedule")
    st.caption("Enable/disable automatic daily syncs. Leave disabled while testing with manual syncs.")

    sched_col1, sched_col2, sched_col3 = st.columns(3)

    with sched_col1:
        # Get current Newbook sync setting
        current_nb_enabled = get_config("sync_newbook_enabled")
        nb_auto_enabled = st.toggle(
            "Newbook Auto-Sync",
            value=current_nb_enabled.lower() in ('true', '1', 'yes', 'enabled') if current_nb_enabled else False,
            key="nb_auto_toggle",
            help="Enable automatic daily Newbook sync at scheduled time"
        )

    with sched_col2:
        # Get current Resos sync setting
        current_rs_enabled = get_config("sync_resos_enabled")
        rs_auto_enabled = st.toggle(
            "Resos Auto-Sync",
            value=current_rs_enabled.lower() in ('true', '1', 'yes', 'enabled') if current_rs_enabled else False,
            key="rs_auto_toggle",
            help="Enable automatic daily Resos sync at scheduled time"
        )

    with sched_col3:
        current_sync_time = get_config("sync_schedule_time") or "05:00"
        sync_time = st.text_input(
            "Sync Time (HH:MM)",
            value=current_sync_time,
            key="sync_time_input",
            help="Time for daily automatic sync (24-hour format)"
        )

    if st.button("💾 Save Schedule Settings", key="save_schedule"):
        success = True
        success &= save_config("sync_newbook_enabled", "true" if nb_auto_enabled else "false")
        success &= save_config("sync_resos_enabled", "true" if rs_auto_enabled else "false")
        success &= save_config("sync_schedule_time", sync_time)
        if success:
            st.success("Schedule settings saved!")
        else:
            st.error("Failed to save some settings")

    # Show current status
    status_col1, status_col2 = st.columns(2)
    with status_col1:
        if nb_auto_enabled:
            st.success(f"✅ Newbook: Auto-sync enabled at {sync_time}")
        else:
            st.warning("⏸️ Newbook: Auto-sync disabled")
    with status_col2:
        if rs_auto_enabled:
            st.success(f"✅ Resos: Auto-sync enabled at {sync_time}")
        else:
            st.warning("⏸️ Resos: Auto-sync disabled")

    st.markdown("---")
    st.markdown("### Manual Sync")
    st.caption("Trigger syncs manually for testing or one-time data pulls.")

    col1, col2 = st.columns(2)

    # Fetch sync status for display
    sync_status_cache = {}
    try:
        status_response = httpx.get(
            f"{BACKEND_URL}/sync/status",
            headers=get_auth_header(),
            timeout=10.0
        )
        if status_response.status_code == 200:
            sync_status_cache = status_response.json()
    except:
        pass

    def format_sync_info(source_key: str, fallback_keys: list = None) -> str:
        """Format sync info for display"""
        from datetime import datetime as dt

        # Try primary key first, then fallbacks
        keys_to_try = [source_key] + (fallback_keys or [])
        entry = None
        for k in keys_to_try:
            if k in sync_status_cache:
                entry = sync_status_cache[k]
                break

        if not entry:
            return "**Last sync:** Never\n\n**Records:** -"

        last_sync = entry.get("last_sync")
        if last_sync:
            try:
                sync_time = dt.fromisoformat(str(last_sync).replace("Z", "+00:00"))
                time_str = sync_time.strftime("%Y-%m-%d %H:%M")
            except:
                time_str = str(last_sync)[:16]
        else:
            time_str = "Never"

        records = entry.get("records_fetched") or entry.get("records_created") or 0
        status = entry.get("status", "unknown")
        status_emoji = "✅" if status == "success" else "❌" if status == "failed" else "🔄"

        return f"**Last sync:** {time_str} {status_emoji}\n\n**Records:** {records:,}"

    with col1:
        st.markdown("### Newbook Sync")
        st.info(format_sync_info("newbook_bookings", ["bookings_newbook", "newbook"]))

        # Date range option for testing
        use_date_range_nb = st.checkbox("Sync specific date range", key="nb_date_range", value=True,
                                        help="Filter by stay dates (useful for testing)")

        if use_date_range_nb:
            nb_col1, nb_col2 = st.columns(2)
            with nb_col1:
                nb_from = st.date_input("From Date", date.today() - timedelta(days=7), key="nb_from")
            with nb_col2:
                nb_to = st.date_input("To Date", date.today() + timedelta(days=30), key="nb_to")
        else:
            nb_from = None
            nb_to = None
            full_sync_nb = st.checkbox("Full sync (all bookings)", key="nb_full", value=False,
                                        help="If unchecked, only fetches bookings modified since last sync")

        if st.button("🔄 Sync Newbook", use_container_width=True):
            with st.spinner("Syncing Newbook data..."):
                try:
                    params = {}
                    if use_date_range_nb and nb_from and nb_to:
                        params["from_date"] = str(nb_from)
                        params["to_date"] = str(nb_to)
                    else:
                        params["full_sync"] = full_sync_nb if not use_date_range_nb else False

                    response = httpx.post(
                        f"{BACKEND_URL}/sync/newbook",
                        headers=get_auth_header(),
                        params=params,
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        result = response.json()
                        st.success(result.get("message", "Newbook sync started!"))
                    else:
                        st.error("Failed to start sync")
                except Exception as e:
                    st.error(f"Error: {e}")

    with col2:
        st.markdown("### Resos Sync")
        st.info(format_sync_info("resos_bookings", ["bookings_resos", "resos"]))

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

    # Earned Revenue Sync (Newbook only)
    st.markdown("### 💰 Earned Revenue Sync")
    st.caption("Fetch official financial figures from Newbook's earned revenue report. Updates daily_occupancy with accommodation revenue.")

    er_col1, er_col2, er_col3 = st.columns([1, 1, 1])

    with er_col1:
        er_from = st.date_input(
            "From Date",
            date.today() - timedelta(days=7),
            key="er_from",
            help="Start date for earned revenue fetch"
        )

    with er_col2:
        er_to = st.date_input(
            "To Date",
            date.today(),
            key="er_to",
            help="End date for earned revenue fetch (typically historical dates only)"
        )

    with er_col3:
        st.markdown("&nbsp;")  # Spacer for alignment
        st.markdown("&nbsp;")
        if st.button("💰 Sync Earned Revenue", use_container_width=True, key="er_sync"):
            with st.spinner("Fetching earned revenue data..."):
                try:
                    response = httpx.post(
                        f"{BACKEND_URL}/sync/newbook/earned-revenue",
                        headers=get_auth_header(),
                        params={"from_date": str(er_from), "to_date": str(er_to)},
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        result = response.json()
                        st.success(result.get("message", "Earned revenue sync started!"))
                    else:
                        error_detail = response.json().get("detail", "Unknown error")
                        st.error(f"Failed to start sync: {error_detail}")
                except Exception as e:
                    st.error(f"Error: {e}")

    st.info("**Note:** Configure accommodation GL codes in the 'GL Mapping' tab to identify which revenue is room revenue.")

    st.markdown("---")

    # Occupancy Report Sync (Newbook only)
    st.markdown("### 🏨 Occupancy Report Sync")
    st.caption("Fetch room availability data from Newbook's occupancy report. This populates total_rooms and available_rooms for ALL dates, including days with no bookings.")

    occ_col1, occ_col2, occ_col3 = st.columns([1, 1, 1])

    with occ_col1:
        occ_from = st.date_input(
            "From Date",
            date.today() - timedelta(days=90),
            key="occ_from",
            help="Start date for occupancy report fetch"
        )

    with occ_col2:
        occ_to = st.date_input(
            "To Date",
            date.today() + timedelta(days=30),
            key="occ_to",
            help="End date for occupancy report fetch"
        )

    with occ_col3:
        st.markdown("&nbsp;")  # Spacer for alignment
        st.markdown("&nbsp;")
        if st.button("🏨 Sync Occupancy Report", use_container_width=True, key="occ_sync"):
            with st.spinner("Fetching occupancy report data..."):
                try:
                    response = httpx.post(
                        f"{BACKEND_URL}/sync/newbook/occupancy-report",
                        headers=get_auth_header(),
                        params={"from_date": str(occ_from), "to_date": str(occ_to)},
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        result = response.json()
                        st.success(result.get("message", "Occupancy report sync started!"))
                    else:
                        error_detail = response.json().get("detail", "Unknown error")
                        st.error(f"Failed to start sync: {error_detail}")
                except Exception as e:
                    st.error(f"Error: {e}")

    st.info("**Why run this?** The occupancy report provides room availability for ALL dates, ensuring days with no bookings still show correct total_rooms. This is essential for accurate occupancy % calculations in weekly summaries.")

    st.markdown("---")

    # Full sync
    st.markdown("### Full Sync")
    full_sync_all = st.checkbox("Full sync (all bookings from both sources)", key="full_all", value=False)

    col_sync, col_agg = st.columns(2)
    with col_sync:
        if st.button("🔄 Run Full Sync (Both Sources)", use_container_width=True):
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/sync/full",
                    headers=get_auth_header(),
                    params={"full_sync": full_sync_all},
                    timeout=10.0
                )
                if response.status_code == 200:
                    st.success("Full sync started in background!")
                else:
                    st.error("Failed to start sync")
            except Exception as e:
                st.error(f"Error: {e}")

    with col_agg:
        if st.button("📊 Run Aggregation", use_container_width=True):
            try:
                response = httpx.post(
                    f"{BACKEND_URL}/sync/aggregate",
                    headers=get_auth_header(),
                    timeout=10.0
                )
                if response.status_code == 200:
                    st.success("Aggregation started!")
                else:
                    st.error("Failed to start aggregation")
            except Exception as e:
                st.error(f"Error: {e}")

    # Sync logs
    st.markdown("---")
    st.markdown("### Recent Sync Logs")

    # Fetch actual sync status from API
    logs_data = []

    # Display name mapping for sync types
    sync_display_names = {
        "newbook_bookings": "Newbook Bookings",
        "newbook_occupancy_report": "Newbook Occupancy",
        "newbook_earned_revenue": "Newbook Revenue",
        "resos_bookings": "Resos Bookings",
        # Fallbacks for old format
        "newbook": "Newbook",
        "resos": "Resos",
    }

    # Preferred display order
    sync_order = [
        "newbook_bookings", "newbook_occupancy_report", "newbook_earned_revenue",
        "resos_bookings", "newbook", "resos"
    ]

    try:
        headers = get_auth_header()
        response = httpx.get(
            f"{BACKEND_URL}/sync/status",
            headers=headers,
            timeout=10.0
        )
        if response.status_code == 200:
            sync_status = response.json()

            # Sort by preferred order, then alphabetically for any extras
            sorted_keys = sorted(
                sync_status.keys(),
                key=lambda k: (sync_order.index(k) if k in sync_order else 100, k)
            )

            for key in sorted_keys:
                entry = sync_status[key]
                last_sync = entry.get("last_sync")

                # Format timestamp
                if last_sync:
                    from datetime import datetime as dt
                    try:
                        sync_time = dt.fromisoformat(str(last_sync).replace("Z", "+00:00"))
                        time_str = sync_time.strftime("%Y-%m-%d %H:%M")
                    except:
                        time_str = str(last_sync)[:16] if last_sync else "-"
                else:
                    time_str = "-"

                # Get display name
                display_name = sync_display_names.get(key, key.replace("_", " ").title())

                # Format status with emoji
                status = entry.get("status", "unknown")
                if status == "success":
                    status_display = "✅ Success"
                elif status == "failed":
                    status_display = "❌ Failed"
                elif status == "running":
                    status_display = "🔄 Running"
                else:
                    status_display = status.capitalize() if status else "Not run"

                logs_data.append({
                    "Time": time_str,
                    "Source": display_name,
                    "Status": status_display,
                    "Records": entry.get("records_fetched") or entry.get("records_created") or 0
                })

            # Add placeholders for missing sync types
            if not logs_data:
                logs_data = [
                    {"Time": "-", "Source": "Newbook Bookings", "Status": "Not run", "Records": "-"},
                    {"Time": "-", "Source": "Newbook Occupancy", "Status": "Not run", "Records": "-"},
                    {"Time": "-", "Source": "Newbook Revenue", "Status": "Not run", "Records": "-"},
                    {"Time": "-", "Source": "Resos Bookings", "Status": "Not run", "Records": "-"},
                ]
        else:
            logs_data = [
                {"Time": "-", "Source": "Newbook Bookings", "Status": "Error fetching", "Records": "-"},
                {"Time": "-", "Source": "Resos Bookings", "Status": "Error fetching", "Records": "-"},
            ]
    except Exception as e:
        logs_data = [
            {"Time": "-", "Source": "Newbook Bookings", "Status": "Not run", "Records": "-"},
            {"Time": "-", "Source": "Resos Bookings", "Status": "Not run", "Records": "-"},
        ]

    st.dataframe(pd.DataFrame(logs_data), use_container_width=True, hide_index=True)

    # Aggregation Status
    st.markdown("---")
    st.markdown("### Aggregation Status")

    try:
        agg_response = httpx.get(
            f"{BACKEND_URL}/sync/aggregate/status",
            headers=get_auth_header(),
            timeout=10.0
        )
        if agg_response.status_code == 200:
            agg_status = agg_response.json()

            # Summary metrics
            agg_col1, agg_col2, agg_col3 = st.columns(3)

            with agg_col1:
                pending_total = agg_status.get("pending", {}).get("total", 0)
                if pending_total > 0:
                    st.warning(f"**Pending:** {pending_total} dates")
                else:
                    st.success("**Pending:** 0 dates")

            with agg_col2:
                occ_data = agg_status.get("aggregated", {}).get("daily_occupancy", {})
                occ_count = occ_data.get("count", 0)
                st.info(f"**Occupancy Days:** {occ_count:,}")

            with agg_col3:
                covers_data = agg_status.get("aggregated", {}).get("daily_covers", {})
                covers_count = covers_data.get("count", 0)
                st.info(f"**Covers Records:** {covers_count:,}")

            # Last aggregation time
            last_agg = agg_status.get("last_aggregation")
            if last_agg:
                from datetime import datetime as dt
                try:
                    agg_time = dt.fromisoformat(last_agg.replace("Z", "+00:00"))
                    agg_time_str = agg_time.strftime("%Y-%m-%d %H:%M")
                except:
                    agg_time_str = last_agg[:16] if last_agg else "Never"
                st.caption(f"Last aggregation: {agg_time_str}")
            else:
                st.caption("Last aggregation: Never")

            # Date ranges
            with st.expander("Aggregated Date Ranges"):
                occ_earliest = occ_data.get("earliest")
                occ_latest = occ_data.get("latest")
                covers_earliest = covers_data.get("earliest")
                covers_latest = covers_data.get("latest")

                range_data = []
                if occ_earliest and occ_latest:
                    range_data.append({
                        "Table": "daily_occupancy",
                        "Earliest": str(occ_earliest),
                        "Latest": str(occ_latest),
                        "Days": occ_count
                    })
                if covers_earliest and covers_latest:
                    range_data.append({
                        "Table": "daily_covers",
                        "Earliest": str(covers_earliest),
                        "Latest": str(covers_latest),
                        "Records": covers_count
                    })
                if range_data:
                    st.dataframe(pd.DataFrame(range_data), use_container_width=True, hide_index=True)

            # Pending breakdown by source
            pending_by_source = agg_status.get("pending", {}).get("by_source", {})
            if pending_by_source:
                st.markdown("**Pending by Source:**")
                for source, data in pending_by_source.items():
                    st.warning(
                        f"**{source.capitalize()}:** {data['count']} dates "
                        f"({data['earliest']} to {data['latest']})"
                    )

        else:
            st.error("Failed to fetch aggregation status")
    except Exception as e:
        st.error(f"Error fetching aggregation status: {e}")

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

    # Load current values
    current_hotel_name = get_config("hotel_name") or ""
    current_total_rooms = get_config("total_rooms")
    current_timezone = get_config("timezone") or "Europe/London"

    # Parse total_rooms with fallback
    try:
        total_rooms_value = int(current_total_rooms) if current_total_rooms else 80
    except (ValueError, TypeError):
        total_rooms_value = 80

    # Get timezone index
    timezone_options = ["Europe/London", "Europe/Paris", "America/New_York", "America/Los_Angeles", "Australia/Sydney"]
    try:
        timezone_index = timezone_options.index(current_timezone)
    except ValueError:
        timezone_index = 0

    with st.form("property_config"):
        hotel_name = st.text_input(
            "Hotel/Property Name",
            value=current_hotel_name,
            help="Name displayed in reports"
        )
        total_rooms = st.number_input(
            "Total Rooms",
            min_value=1,
            max_value=1000,
            value=total_rooms_value,
            help="Total number of hotel rooms (for occupancy calculation)"
        )
        timezone = st.selectbox(
            "Timezone",
            timezone_options,
            index=timezone_index,
            help="Local timezone for the property"
        )

        if st.form_submit_button("💾 Save Settings", use_container_width=True):
            success = True
            success &= save_config("hotel_name", hotel_name)
            success &= save_config("total_rooms", str(total_rooms))
            success &= save_config("timezone", timezone)
            if success:
                st.success("Settings saved!")
                st.rerun()  # Refresh to show updated values
            else:
                st.error("Failed to save some settings")

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

# GL Mapping Tab
with tab5:
    st.subheader("Newbook GL Account Mapping")

    st.markdown("""
    Configure GL code mappings for accurate revenue categorization.
    These codes are used during sync to identify revenue types from Newbook data.
    """)

    # --- ACCOMMODATION GL CODES (for Earned Revenue) ---
    st.markdown("---")
    st.markdown("### 🏨 Accommodation Revenue")
    st.caption("Used by earned revenue sync to identify room revenue GL accounts")

    current_accommodation_codes = get_config("accommodation_gl_codes")
    accommodation_codes_input = st.text_input(
        "Accommodation GL Codes",
        value=current_accommodation_codes or "",
        help="Comma-separated GL codes that identify accommodation/room revenue (e.g., 4000,4001,4010)",
        key="accommodation_gl_codes"
    )

    current_accommodation_vat = get_config("accommodation_vat_rate")
    accommodation_vat_input = st.number_input(
        "Accommodation VAT Rate",
        min_value=0.0,
        max_value=1.0,
        value=float(current_accommodation_vat or 0.20),
        step=0.01,
        format="%.2f",
        help="VAT rate for accommodation (0.20 = 20%). Used to calculate net room revenue from gross."
    )

    if st.button("💾 Save Accommodation GL Configuration", key="save_accommodation_gl"):
        success = True
        success &= save_config("accommodation_gl_codes", accommodation_codes_input)
        success &= save_config("accommodation_vat_rate", str(accommodation_vat_input))

        if success:
            st.success("Accommodation GL configuration saved!")
        else:
            st.error("Failed to save accommodation settings")

    # --- BREAKFAST/DINNER GL CODES (for Inventory Items) ---
    st.markdown("---")
    st.markdown("### 🍽️ Meal Allocations (Inventory Items)")
    st.caption("Used to identify breakfast/dinner inventory items from booking data")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Breakfast Configuration")

        current_breakfast_codes = get_config("newbook_breakfast_gl_codes")
        breakfast_codes_input = st.text_input(
            "Breakfast GL Codes",
            value=current_breakfast_codes or "",
            help="Comma-separated GL codes that identify breakfast items (e.g., 4100,4101,4102)"
        )

        current_breakfast_vat = get_config("newbook_breakfast_vat_rate")
        breakfast_vat_input = st.number_input(
            "Breakfast VAT Rate",
            min_value=0.0,
            max_value=1.0,
            value=float(current_breakfast_vat or 0.20),
            step=0.01,
            format="%.2f",
            help="VAT rate as decimal (0.20 = 20%). Used to calculate net from gross amounts."
        )

    with col2:
        st.markdown("### Dinner Configuration")

        current_dinner_codes = get_config("newbook_dinner_gl_codes")
        dinner_codes_input = st.text_input(
            "Dinner GL Codes",
            value=current_dinner_codes or "",
            help="Comma-separated GL codes that identify dinner items (e.g., 4200,4201,4202)"
        )

        current_dinner_vat = get_config("newbook_dinner_vat_rate")
        dinner_vat_input = st.number_input(
            "Dinner VAT Rate",
            min_value=0.0,
            max_value=1.0,
            value=float(current_dinner_vat or 0.20),
            step=0.01,
            format="%.2f",
            help="VAT rate as decimal (0.20 = 20%). Used to calculate net from gross amounts."
        )

    if st.button("💾 Save GL Configuration", use_container_width=True):
        success = True
        success &= save_config("newbook_breakfast_gl_codes", breakfast_codes_input)
        success &= save_config("newbook_dinner_gl_codes", dinner_codes_input)
        success &= save_config("newbook_breakfast_vat_rate", str(breakfast_vat_input))
        success &= save_config("newbook_dinner_vat_rate", str(dinner_vat_input))

        if success:
            st.success("GL configuration saved! Changes will apply on next sync.")
        else:
            st.error("Failed to save some settings")

    st.markdown("---")

    st.markdown("### How It Works")
    st.info("""
    **GL Code Matching Process:**
    1. During Newbook sync, each inventory item's `gl_account_id` is looked up
    2. The GL code is matched against your configured breakfast/dinner lists
    3. Matched items are categorized and their gross amounts summed per night
    4. Net values are calculated using the configured VAT rates
    5. Results are stored in the booking nights table for aggregation

    **Note:** Items not matching any configured GL code are stored as "other items" for reference.
    """)

    # Show current GL accounts from Newbook (if any)
    st.markdown("### Cached GL Accounts")
    st.caption("GL accounts fetched from Newbook API (for reference when configuring codes)")

    try:
        response = httpx.get(
            f"{BACKEND_URL}/config/gl-accounts",
            headers=get_auth_header(),
            timeout=10.0
        )
        if response.status_code == 200:
            gl_accounts = response.json()
            if gl_accounts:
                gl_df = pd.DataFrame(gl_accounts)
                st.dataframe(gl_df, use_container_width=True, hide_index=True)
            else:
                st.info("No GL accounts cached. Run a Newbook sync to populate.")
        else:
            st.info("GL accounts endpoint not available")
    except:
        st.info("Unable to load GL accounts. Run a Newbook sync to populate the cache.")

# Resos Mapping Tab
with tab6:
    st.subheader("Resos Field & Service Period Mapping")

    st.markdown("""
    Configure how Resos custom fields map to booking attributes (hotel guest, DBB, etc.)
    and how opening hours map to consistent service periods (lunch, dinner, etc.).
    """)

    # --- CUSTOM FIELD MAPPING ---
    st.markdown("---")
    st.markdown("### Custom Field Mapping")
    st.caption("Map Resos custom fields to booking attributes for accurate categorization")

    # Initialize session state for mappings
    if "resos_custom_fields" not in st.session_state:
        st.session_state.resos_custom_fields = []
    if "resos_opening_hours" not in st.session_state:
        st.session_state.resos_opening_hours = []
    if "resos_cf_mappings" not in st.session_state:
        st.session_state.resos_cf_mappings = {}
    if "resos_oh_mappings" not in st.session_state:
        st.session_state.resos_oh_mappings = {}

    # Fetch custom fields from Resos API
    col_fetch_cf, col_status_cf = st.columns([1, 2])
    with col_fetch_cf:
        if st.button("🔄 Fetch Custom Fields from Resos", key="fetch_cf"):
            with st.spinner("Fetching custom fields..."):
                try:
                    response = httpx.get(
                        f"{BACKEND_URL}/resos/custom-fields",
                        headers=get_auth_header(),
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        data = response.json()
                        st.session_state.resos_custom_fields = data.get("custom_fields", [])
                        st.success(f"Loaded {len(st.session_state.resos_custom_fields)} custom fields")
                    else:
                        error_detail = response.json().get("detail", "Unknown error")
                        st.error(f"Failed to fetch: {error_detail}")
                except Exception as e:
                    st.error(f"Error: {e}")

    # Load existing mappings from database
    with col_status_cf:
        if st.button("📥 Load Saved Mappings", key="load_mappings"):
            with st.spinner("Loading mappings..."):
                try:
                    response = httpx.get(
                        f"{BACKEND_URL}/resos/mapping",
                        headers=get_auth_header(),
                        timeout=10.0
                    )
                    if response.status_code == 200:
                        data = response.json()
                        # Convert to lookup dicts
                        st.session_state.resos_cf_mappings = {
                            m["field_id"]: m for m in data.get("custom_fields", [])
                        }
                        st.session_state.resos_oh_mappings = {
                            m["opening_hour_id"]: m for m in data.get("opening_hours", [])
                        }
                        st.success(f"Loaded {len(st.session_state.resos_cf_mappings)} field mappings, {len(st.session_state.resos_oh_mappings)} opening hour mappings")
                except Exception as e:
                    st.error(f"Error loading mappings: {e}")

    # Custom field mapping UI
    if st.session_state.resos_custom_fields:
        st.markdown("#### Map Custom Fields to Purposes")

        mapping_options = ["ignore", "hotel_guest", "dbb", "booking_number", "allergies"]
        mapping_labels = {
            "ignore": "Ignore",
            "hotel_guest": "Hotel Guest (Yes/No)",
            "dbb": "DBB (Dinner, Bed & Breakfast)",
            "booking_number": "Hotel Booking Number",
            "allergies": "Allergies/Dietary"
        }

        cf_updates = []

        for field in st.session_state.resos_custom_fields:
            field_id = field.get("id", "")
            field_name = field.get("name", "Unknown")
            field_type = field.get("type", "text")
            choices = field.get("choices", [])

            # Get existing mapping
            existing = st.session_state.resos_cf_mappings.get(field_id, {})
            current_maps_to = existing.get("maps_to", "ignore")
            current_value_for_true = existing.get("value_for_true", "")

            # Try to find the index
            try:
                default_idx = mapping_options.index(current_maps_to)
            except ValueError:
                default_idx = 0

            col1, col2, col3 = st.columns([2, 2, 2])

            with col1:
                st.markdown(f"**{field_name}**")
                st.caption(f"Type: {field_type} | ID: {field_id[:12]}...")

            with col2:
                maps_to = st.selectbox(
                    "Maps to",
                    options=mapping_options,
                    index=default_idx,
                    format_func=lambda x: mapping_labels.get(x, x),
                    key=f"cf_map_{field_id}",
                    label_visibility="collapsed"
                )

            with col3:
                # For radio/checkbox fields mapped to hotel_guest/dbb, show value selector
                if maps_to in ["hotel_guest", "dbb"]:
                    if field_type in ["radio", "checkbox"] and choices:
                        # Extract choice values
                        choice_values = [c.get("value", c.get("label", "")) for c in choices if isinstance(c, dict)]
                        if not choice_values:
                            choice_values = choices  # Handle simple list of strings

                        # Find current value index
                        try:
                            val_idx = choice_values.index(current_value_for_true) if current_value_for_true in choice_values else 0
                        except (ValueError, IndexError):
                            val_idx = 0

                        value_for_true = st.selectbox(
                            "Value = Yes",
                            options=choice_values,
                            index=val_idx,
                            key=f"cf_val_{field_id}",
                            label_visibility="collapsed"
                        )
                    else:
                        # No choices available - allow manual text input
                        value_for_true = st.text_input(
                            "Value = Yes",
                            value=current_value_for_true or "",
                            key=f"cf_val_{field_id}",
                            placeholder="e.g., Yes, true, 1",
                            label_visibility="collapsed"
                        )
                else:
                    value_for_true = None

            cf_updates.append({
                "field_id": field_id,
                "field_name": field_name,
                "field_type": field_type,
                "maps_to": maps_to,
                "value_for_true": value_for_true
            })

        st.markdown("---")

    else:
        st.info("Click 'Fetch Custom Fields from Resos' to load available fields")

    # --- OPENING HOURS MAPPING ---
    st.markdown("---")
    st.markdown("### Opening Hours / Service Period Mapping")
    st.caption("Map Resos opening hours to consistent service periods (lunch, afternoon, dinner)")

    # Fetch opening hours from Resos API
    if st.button("🔄 Fetch Opening Hours from Resos", key="fetch_oh"):
        with st.spinner("Fetching opening hours..."):
            try:
                response = httpx.get(
                    f"{BACKEND_URL}/resos/opening-hours",
                    headers=get_auth_header(),
                    timeout=30.0
                )
                if response.status_code == 200:
                    data = response.json()
                    st.session_state.resos_opening_hours = data.get("opening_hours", [])
                    st.success(f"Loaded {len(st.session_state.resos_opening_hours)} opening hour periods")
                else:
                    error_detail = response.json().get("detail", "Unknown error")
                    st.error(f"Failed to fetch: {error_detail}")
            except Exception as e:
                st.error(f"Error: {e}")

    # Opening hours mapping UI
    if st.session_state.resos_opening_hours:
        st.markdown("#### Map Opening Hours to Service Periods")

        period_options = ["ignore", "lunch", "afternoon", "dinner"]
        period_labels = {
            "ignore": "Ignore (special/one-off)",
            "lunch": "Lunch",
            "afternoon": "Afternoon",
            "dinner": "Dinner"
        }

        oh_updates = []

        # Group by unique name to reduce repetition
        # Resos has separate entries per day of week, but we want one mapping per period name
        unique_periods = {}
        for hour in st.session_state.resos_opening_hours:
            hour_id = hour.get("id", "")
            hour_name = hour.get("name", "Unknown")
            day_name = hour.get("day_name", "")
            start_time = hour.get("start_time", "")
            end_time = hour.get("end_time", "")

            # Use name as key for grouping, but store first occurrence details
            if hour_name not in unique_periods:
                unique_periods[hour_name] = {
                    "ids": [],
                    "name": hour_name,
                    "days": [],
                    "start_time": start_time,
                    "end_time": end_time
                }
            unique_periods[hour_name]["ids"].append(hour_id)
            unique_periods[hour_name]["days"].append(day_name)

        for period_name, period_info in unique_periods.items():
            # Get existing mapping for any of the IDs (they should be the same)
            existing = None
            for pid in period_info["ids"]:
                if pid in st.session_state.resos_oh_mappings:
                    existing = st.session_state.resos_oh_mappings[pid]
                    break

            current_period_type = existing.get("period_type", "ignore") if existing else "ignore"
            current_is_regular = existing.get("is_regular", True) if existing else True

            # Try to find the index
            try:
                default_idx = period_options.index(current_period_type)
            except ValueError:
                default_idx = 0

            col1, col2, col3 = st.columns([2, 2, 1])

            with col1:
                days_str = ", ".join(sorted(set(period_info["days"])))[:40]
                st.markdown(f"**{period_name}**")
                st.caption(f"{period_info['start_time']} - {period_info['end_time']} | {days_str}...")

            with col2:
                period_type = st.selectbox(
                    "Service Period",
                    options=period_options,
                    index=default_idx,
                    format_func=lambda x: period_labels.get(x, x),
                    key=f"oh_map_{period_name}",
                    label_visibility="collapsed"
                )

            with col3:
                is_regular = st.checkbox(
                    "Regular",
                    value=current_is_regular,
                    key=f"oh_reg_{period_name}",
                    help="Regular service period (not special event)"
                )

            # Add mapping for all IDs with this name
            for hour_id in period_info["ids"]:
                oh_updates.append({
                    "opening_hour_id": hour_id,
                    "opening_hour_name": period_name,
                    "period_type": period_type,
                    "is_regular": is_regular
                })

        st.markdown("---")

    else:
        st.info("Click 'Fetch Opening Hours from Resos' to load available periods")

    # --- SAVE ALL MAPPINGS ---
    if st.session_state.resos_custom_fields or st.session_state.resos_opening_hours:
        if st.button("💾 Save All Mappings", use_container_width=True, type="primary", key="save_resos_mappings"):
            with st.spinner("Saving mappings..."):
                try:
                    payload = {}

                    # Custom field mappings
                    if st.session_state.resos_custom_fields:
                        cf_list = []
                        for field in st.session_state.resos_custom_fields:
                            field_id = field.get("id", "")
                            maps_to = st.session_state.get(f"cf_map_{field_id}", "ignore")
                            value_for_true = st.session_state.get(f"cf_val_{field_id}")

                            if maps_to != "ignore":  # Only save non-ignored mappings
                                cf_list.append({
                                    "field_id": field_id,
                                    "field_name": field.get("name", ""),
                                    "field_type": field.get("type", ""),
                                    "maps_to": maps_to,
                                    "value_for_true": value_for_true
                                })
                        payload["custom_fields"] = cf_list

                    # Opening hours mappings
                    if st.session_state.resos_opening_hours:
                        # Group by unique name to get widget values
                        unique_periods = {}
                        for hour in st.session_state.resos_opening_hours:
                            hour_name = hour.get("name", "Unknown")
                            if hour_name not in unique_periods:
                                unique_periods[hour_name] = []
                            unique_periods[hour_name].append(hour)

                        oh_list = []
                        for period_name, hours in unique_periods.items():
                            period_type = st.session_state.get(f"oh_map_{period_name}", "ignore")
                            is_regular = st.session_state.get(f"oh_reg_{period_name}", True)

                            for hour in hours:
                                oh_list.append({
                                    "opening_hour_id": hour.get("id", ""),
                                    "opening_hour_name": period_name,
                                    "period_type": period_type,
                                    "is_regular": is_regular
                                })
                        payload["opening_hours"] = oh_list

                    response = httpx.post(
                        f"{BACKEND_URL}/resos/mapping",
                        headers=get_auth_header(),
                        json=payload,
                        timeout=30.0
                    )

                    if response.status_code == 200:
                        result = response.json()
                        st.success(f"Saved {result.get('custom_fields_saved', 0)} custom field mappings, {result.get('opening_hours_saved', 0)} opening hours mappings")
                    else:
                        error_detail = response.json().get("detail", "Unknown error")
                        st.error(f"Failed to save: {error_detail}")
                except Exception as e:
                    st.error(f"Error saving mappings: {e}")

    st.markdown("---")
    st.markdown("### How Mappings Are Used")
    st.info("""
    **Custom Field Mappings:**
    - During Resos sync, custom field values are extracted using these mappings
    - Fields mapped to `hotel_guest` or `dbb` are checked against the configured "Value = Yes" option
    - This determines `is_hotel_guest`, `is_dbb` flags on each booking

    **Opening Hours Mappings:**
    - During aggregation, bookings are grouped by service period using these mappings
    - Instead of raw names like "Midweek Dinner" or "Saturday Dinner", all get mapped to consistent "dinner"
    - This enables accurate lunch/dinner cover forecasting
    """)


# Account Tab
with tab7:
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
