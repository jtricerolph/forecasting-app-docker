"""
Shared authentication component for all pages
"""
import os
import streamlit as st
import httpx
from datetime import datetime, timedelta

try:
    import extra_streamlit_components as stx
    COOKIES_AVAILABLE = True
except ImportError:
    COOKIES_AVAILABLE = False

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
COOKIE_NAME = "forecast_auth_token"
COOKIE_EXPIRY_DAYS = 7


@st.cache_resource(experimental_allow_widgets=True)
def get_cookie_manager():
    """Get or create a singleton cookie manager instance"""
    if not COOKIES_AVAILABLE:
        return None
    return stx.CookieManager()


def init_session_state():
    """Initialize session state variables, restoring from cookie if available"""
    if "token" not in st.session_state:
        st.session_state.token = None
    if "user" not in st.session_state:
        st.session_state.user = None

    # Try to restore token from cookie if not in session state
    if st.session_state.token is None and COOKIES_AVAILABLE:
        cookie_manager = get_cookie_manager()
        if cookie_manager:
            saved_token = cookie_manager.get(COOKIE_NAME)
            if saved_token:
                # Verify the token is still valid
                try:
                    response = httpx.get(
                        f"{BACKEND_URL}/auth/me",
                        headers={"Authorization": f"Bearer {saved_token}"},
                        timeout=5.0
                    )
                    if response.status_code == 200:
                        st.session_state.token = saved_token
                        st.session_state.user = response.json()
                    else:
                        # Token expired/invalid, clear cookie
                        cookie_manager.delete(COOKIE_NAME)
                except Exception:
                    # Backend unavailable or error, don't use cookie
                    pass


def save_token_to_cookie(token: str):
    """Save token to cookie for persistence across refreshes"""
    if COOKIES_AVAILABLE:
        cookie_manager = get_cookie_manager()
        if cookie_manager:
            expires = datetime.now() + timedelta(days=COOKIE_EXPIRY_DAYS)
            cookie_manager.set(COOKIE_NAME, token, expires_at=expires)


def clear_token_cookie():
    """Clear the auth token cookie"""
    if COOKIES_AVAILABLE:
        cookie_manager = get_cookie_manager()
        if cookie_manager:
            cookie_manager.delete(COOKIE_NAME)


def show_login_form():
    """Display login form and handle authentication"""
    st.markdown("### Login Required")

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


def require_auth():
    """
    Check if user is authenticated. If not, show login form and stop.
    Call this at the top of any page that requires authentication.

    Returns True if authenticated, shows login and stops if not.
    """
    init_session_state()

    if st.session_state.token is None:
        show_login_form()
        st.stop()
        return False

    return True


def get_auth_header():
    """Get authorization header from session"""
    token = st.session_state.get("token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def logout():
    """Log out the current user"""
    st.session_state.token = None
    st.session_state.user = None
    clear_token_cookie()
    st.rerun()
