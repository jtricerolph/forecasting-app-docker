"""
Reusable table formatting utilities
"""
import pandas as pd
import streamlit as st
from typing import Dict, List, Optional


def format_forecast_table(
    df: pd.DataFrame,
    date_col: str = 'Date',
    value_cols: List[str] = None,
    precision: int = 1
) -> pd.DataFrame:
    """
    Format a forecast dataframe for display

    Args:
        df: DataFrame to format
        date_col: Date column name
        value_cols: Columns to format as numbers
        precision: Decimal places

    Returns:
        Formatted DataFrame
    """
    display_df = df.copy()

    # Format date
    if date_col in display_df.columns:
        if pd.api.types.is_datetime64_any_dtype(display_df[date_col]):
            display_df[date_col] = display_df[date_col].dt.strftime('%a %d %b')

    return display_df


def highlight_variance(val, threshold: float = 5.0):
    """
    Style function to highlight positive/negative variance

    Args:
        val: Cell value
        threshold: Threshold for highlighting

    Returns:
        CSS style string
    """
    if pd.isna(val):
        return ''
    try:
        if float(val) > threshold:
            return 'background-color: #d4edda; color: #155724'
        elif float(val) < -threshold:
            return 'background-color: #f8d7da; color: #721c24'
    except:
        pass
    return ''


def highlight_best_model(row, model_cols: List[str]):
    """
    Style function to highlight the best (lowest error) model in a row

    Args:
        row: DataFrame row
        model_cols: List of model column names

    Returns:
        List of CSS styles for each column
    """
    styles = [''] * len(row)

    # Find minimum value among model columns
    model_values = {col: row[col] for col in model_cols if col in row.index and pd.notna(row[col])}

    if model_values:
        min_col = min(model_values, key=model_values.get)
        for i, col in enumerate(row.index):
            if col == min_col:
                styles[i] = 'background-color: #d4edda'

    return styles


def create_status_badge(status: str) -> str:
    """
    Create an HTML badge for status display

    Args:
        status: Status string (ok, warning, error)

    Returns:
        HTML string with styled badge
    """
    colors = {
        'ok': ('#155724', '#d4edda'),
        'success': ('#155724', '#d4edda'),
        'warning': ('#856404', '#fff3cd'),
        'error': ('#721c24', '#f8d7da'),
        'discrepancy': ('#721c24', '#f8d7da')
    }

    text_color, bg_color = colors.get(status.lower(), ('#6c757d', '#e2e3e5'))

    return f'<span style="background-color: {bg_color}; color: {text_color}; padding: 2px 8px; border-radius: 4px; font-size: 0.85em;">{status}</span>'


def format_currency(val, symbol: str = '£') -> str:
    """Format a value as currency"""
    try:
        return f'{symbol}{float(val):,.2f}'
    except:
        return str(val)


def format_percentage(val, precision: int = 1) -> str:
    """Format a value as percentage"""
    try:
        return f'{float(val):.{precision}f}%'
    except:
        return str(val)


def format_change(val, precision: int = 1) -> str:
    """Format a value as change with sign"""
    try:
        return f'{float(val):+.{precision}f}'
    except:
        return str(val)
