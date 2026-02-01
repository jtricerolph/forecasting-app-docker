"""
Shared date picker component with quick-fill buttons for all dashboard pages.
"""
from datetime import date, timedelta
import streamlit as st
import calendar


def get_quick_date_ranges():
    """
    Return dictionary of quick date range presets.
    All ranges are calculated relative to today.
    """
    today = date.today()

    # Calculate week boundaries (Mon-Sun)
    # Monday is 0, Sunday is 6
    days_since_monday = today.weekday()
    this_week_start = today - timedelta(days=days_since_monday)
    this_week_end = this_week_start + timedelta(days=6)
    last_week_start = this_week_start - timedelta(days=7)
    last_week_end = last_week_start + timedelta(days=6)

    # Calculate month boundaries
    this_month_start = today.replace(day=1)
    last_day_this_month = calendar.monthrange(today.year, today.month)[1]
    this_month_end = today.replace(day=last_day_this_month)

    # Last month
    if today.month == 1:
        last_month_start = date(today.year - 1, 12, 1)
        last_month_end = date(today.year - 1, 12, 31)
    else:
        last_month_start = date(today.year, today.month - 1, 1)
        last_day_last_month = calendar.monthrange(today.year, today.month - 1)[1]
        last_month_end = date(today.year, today.month - 1, last_day_last_month)

    # Next month
    if today.month == 12:
        next_month_start = date(today.year + 1, 1, 1)
        next_month_end = date(today.year + 1, 1, 31)
    else:
        next_month_start = date(today.year, today.month + 1, 1)
        last_day_next_month = calendar.monthrange(today.year, today.month + 1)[1]
        next_month_end = date(today.year, today.month + 1, last_day_next_month)

    # Year boundaries
    this_year_start = date(today.year, 1, 1)
    this_year_end = date(today.year, 12, 31)

    return {
        "Last Week": (last_week_start, last_week_end),
        "This Week": (this_week_start, this_week_end),
        "Last Month": (last_month_start, last_month_end),
        "This Month": (this_month_start, this_month_end),
        "Next Month": (next_month_start, next_month_end),
        "Next 3 Months": (today, today + timedelta(days=90)),
        "Next 6 Months": (today, today + timedelta(days=180)),
        "This Year": (this_year_start, this_year_end),
        "Year from Today": (today, today + timedelta(days=365)),
    }


def render_date_picker_with_quickfill(
    key_prefix: str = "date",
    default_start: date = None,
    default_end: date = None,
    show_metric_selector: bool = False,
    metric_options: list = None,
    metric_format_func=None
):
    """
    Render date picker with quick-fill buttons.

    Args:
        key_prefix: Unique prefix for session state keys
        default_start: Default start date (default: 7 days ago)
        default_end: Default end date (default: 28 days from now)
        show_metric_selector: Whether to show metric dropdown
        metric_options: List of metric options for dropdown
        metric_format_func: Function to format metric display names

    Returns:
        tuple: (start_date, end_date) or (start_date, end_date, metric) if show_metric_selector
    """
    today = date.today()

    # Set defaults
    if default_start is None:
        default_start = today - timedelta(days=7)
    if default_end is None:
        default_end = today + timedelta(days=28)

    # Initialize session state for dates
    start_key = f"{key_prefix}_start"
    end_key = f"{key_prefix}_end"

    if start_key not in st.session_state:
        st.session_state[start_key] = default_start
    if end_key not in st.session_state:
        st.session_state[end_key] = default_end

    # Quick-fill buttons row
    quick_ranges = get_quick_date_ranges()

    st.markdown("**Quick Select:**")

    # Create button rows - 5 buttons per row for better layout
    button_names = list(quick_ranges.keys())

    # Row 1: Last Week, This Week, Last Month, This Month, Next Month
    cols1 = st.columns(5)
    for i, name in enumerate(button_names[:5]):
        with cols1[i]:
            if st.button(name, key=f"{key_prefix}_quick_{name}", use_container_width=True):
                start, end = quick_ranges[name]
                st.session_state[start_key] = start
                st.session_state[end_key] = end
                st.rerun()

    # Row 2: Next 3 Months, Next 6 Months, This Year, Year from Today
    cols2 = st.columns(4)
    for i, name in enumerate(button_names[5:]):
        with cols2[i]:
            if st.button(name, key=f"{key_prefix}_quick_{name}", use_container_width=True):
                start, end = quick_ranges[name]
                st.session_state[start_key] = start
                st.session_state[end_key] = end
                st.rerun()

    st.markdown("")  # Spacing

    # Date inputs row
    if show_metric_selector and metric_options:
        col1, col2, col3 = st.columns([1, 1, 2])
    else:
        col1, col2 = st.columns(2)

    with col1:
        start_date = st.date_input(
            "From",
            value=st.session_state[start_key],
            key=f"{key_prefix}_start_input",
            help="Start date for the data range"
        )
        st.session_state[start_key] = start_date

    with col2:
        end_date = st.date_input(
            "To",
            value=st.session_state[end_key],
            key=f"{key_prefix}_end_input",
            help="End date for the data range"
        )
        st.session_state[end_key] = end_date

    if show_metric_selector and metric_options:
        with col3:
            metric = st.selectbox(
                "Metric",
                metric_options,
                format_func=metric_format_func or (lambda x: x),
                help="Select the metric to display"
            )
        return start_date, end_date, metric

    return start_date, end_date


def render_compact_date_picker(
    key_prefix: str = "date",
    default_start: date = None,
    default_end: date = None,
):
    """
    Render a more compact date picker with dropdown for quick ranges.

    Args:
        key_prefix: Unique prefix for session state keys
        default_start: Default start date
        default_end: Default end date

    Returns:
        tuple: (start_date, end_date)
    """
    today = date.today()

    if default_start is None:
        default_start = today - timedelta(days=7)
    if default_end is None:
        default_end = today + timedelta(days=28)

    start_key = f"{key_prefix}_start"
    end_key = f"{key_prefix}_end"

    if start_key not in st.session_state:
        st.session_state[start_key] = default_start
    if end_key not in st.session_state:
        st.session_state[end_key] = default_end

    quick_ranges = get_quick_date_ranges()

    col1, col2, col3 = st.columns([1, 1, 1])

    with col1:
        start_date = st.date_input(
            "From",
            value=st.session_state[start_key],
            key=f"{key_prefix}_start_input"
        )
        st.session_state[start_key] = start_date

    with col2:
        end_date = st.date_input(
            "To",
            value=st.session_state[end_key],
            key=f"{key_prefix}_end_input"
        )
        st.session_state[end_key] = end_date

    with col3:
        preset = st.selectbox(
            "Quick Select",
            ["Custom"] + list(quick_ranges.keys()),
            key=f"{key_prefix}_preset"
        )
        if preset != "Custom":
            start, end = quick_ranges[preset]
            if start != st.session_state[start_key] or end != st.session_state[end_key]:
                st.session_state[start_key] = start
                st.session_state[end_key] = end
                st.rerun()

    return start_date, end_date
