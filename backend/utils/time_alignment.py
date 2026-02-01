"""
Time alignment utilities for prior year comparisons.

Ensures consistent comparison logic across the application:
- Daily: 364 days (52 weeks) for day-of-week alignment (Mon→Mon, Sat→Sat)
- Weekly: ISO week number matching (Week 6 2026 vs Week 6 2025)
- Monthly: Same month, prior year

This module should be used whenever comparing to prior year data.
"""
from datetime import date, timedelta
from typing import Tuple, Optional


def get_prior_year_daily(target_date: date) -> date:
    """
    Get the comparable date from prior year for daily comparisons.

    Uses 364 days (exactly 52 weeks) to ensure day-of-week alignment:
    - Monday → Monday
    - Saturday → Saturday

    Example:
        Wed 11 Feb 2026 → Wed 12 Feb 2025 (not 11 Feb 2025 which was a different day)

    Args:
        target_date: The date to find comparison for

    Returns:
        The prior year date with same day of week
    """
    return target_date - timedelta(days=364)


def get_prior_year_weekly(target_date: date) -> Tuple[int, int]:
    """
    Get the ISO week and year for weekly year-over-year comparison.

    Uses ISO week numbers so Week 6 of 2026 compares to Week 6 of 2025.
    This ensures full weeks are compared (Mon-Sun) regardless of calendar dates.

    Args:
        target_date: Any date within the target week

    Returns:
        Tuple of (year, week_number) for the comparison week
    """
    iso_cal = target_date.isocalendar()
    return (iso_cal.year - 1, iso_cal.week)


def get_prior_year_week_dates(target_date: date) -> Tuple[date, date]:
    """
    Get the start and end dates of the same ISO week in the prior year.

    Useful for querying data for the entire comparison week.

    Args:
        target_date: Any date within the target week

    Returns:
        Tuple of (week_start, week_end) for the prior year's matching week
    """
    iso_cal = target_date.isocalendar()
    prior_year = iso_cal.year - 1
    prior_week = iso_cal.week

    # Handle edge case: if prior year doesn't have this week number
    # (can happen with week 53), fall back to last week of prior year
    try:
        # Find the first day of the target week in prior year
        # Week 1 day 1 of the prior year
        jan_1_prior = date(prior_year, 1, 1)
        jan_1_iso = jan_1_prior.isocalendar()

        # Calculate days to add to get to the target week
        # First, get to week 1 day 1
        days_to_week_1 = (1 - jan_1_iso.weekday) % 7
        week_1_monday = jan_1_prior + timedelta(days=days_to_week_1)

        # Adjust if Jan 1 is in the previous year's last week
        if jan_1_iso.week != 1:
            week_1_monday = jan_1_prior + timedelta(days=(7 - jan_1_prior.weekday()))

        # Now add weeks to get to target week
        week_start = week_1_monday + timedelta(weeks=prior_week - 1)

        # Verify we got the right week
        if week_start.isocalendar().week != prior_week:
            # Fallback: use last week of prior year
            dec_28_prior = date(prior_year, 12, 28)  # Always in last week
            dec_28_iso = dec_28_prior.isocalendar()
            week_start = dec_28_prior - timedelta(days=dec_28_prior.weekday())

        week_end = week_start + timedelta(days=6)
        return (week_start, week_end)

    except (ValueError, AttributeError):
        # Fallback to simpler calculation
        prior_date = get_prior_year_daily(target_date)
        week_start = prior_date - timedelta(days=prior_date.weekday())
        week_end = week_start + timedelta(days=6)
        return (week_start, week_end)


def get_prior_year_monthly(target_date: date) -> Tuple[date, date]:
    """
    Get the start and end dates of the same month in the prior year.

    Args:
        target_date: Any date within the target month

    Returns:
        Tuple of (month_start, month_end) for the prior year's matching month
    """
    prior_year = target_date.year - 1
    month = target_date.month

    # First day of the month
    month_start = date(prior_year, month, 1)

    # Last day of the month
    if month == 12:
        month_end = date(prior_year + 1, 1, 1) - timedelta(days=1)
    else:
        month_end = date(prior_year, month + 1, 1) - timedelta(days=1)

    return (month_start, month_end)


# SQL helper constants for use in queries
SQL_PRIOR_YEAR_DAILY = "INTERVAL '364 days'"  # For daily comparisons
SQL_PRIOR_YEAR_OFFSET = 364  # Days offset for daily DOW alignment


def get_comparison_info(target_date: date) -> dict:
    """
    Get formatted comparison information for display.

    Useful for showing users what date/week is being compared.

    Args:
        target_date: The date being forecasted/analyzed

    Returns:
        Dict with comparison details
    """
    prior_daily = get_prior_year_daily(target_date)
    prior_week_year, prior_week_num = get_prior_year_weekly(target_date)

    day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

    return {
        "target_date": target_date,
        "target_day": day_names[target_date.weekday()],
        "target_iso_week": target_date.isocalendar().week,
        "prior_year_date": prior_daily,
        "prior_year_day": day_names[prior_daily.weekday()],  # Should match target_day
        "prior_year_iso_week": prior_week_num,
        "comparison_note": f"vs {day_names[prior_daily.weekday()]} {prior_daily.strftime('%d %b %Y')}"
    }
