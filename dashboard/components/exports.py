"""
Export utilities for downloading data
"""
import io
import pandas as pd
import streamlit as st
from datetime import date
from typing import Dict, List, Optional


def create_csv_download(
    df: pd.DataFrame,
    filename: str,
    button_label: str = "📥 Download CSV"
) -> None:
    """
    Create a CSV download button for a DataFrame

    Args:
        df: DataFrame to export
        filename: Name of the file to download
        button_label: Label for the download button
    """
    csv = df.to_csv(index=False)
    st.download_button(
        label=button_label,
        data=csv,
        file_name=filename,
        mime="text/csv"
    )


def create_excel_download(
    sheets: Dict[str, pd.DataFrame],
    filename: str,
    button_label: str = "📥 Download Excel"
) -> None:
    """
    Create an Excel download button with multiple sheets

    Args:
        sheets: Dictionary of sheet_name: DataFrame
        filename: Name of the file to download
        button_label: Label for the download button
    """
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    output.seek(0)

    st.download_button(
        label=button_label,
        data=output,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def export_forecast_report(
    daily_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    variance_df: pd.DataFrame,
    from_date: date,
    to_date: date
) -> None:
    """
    Create a comprehensive forecast report export

    Args:
        daily_df: Daily forecast data
        weekly_df: Weekly summary data
        variance_df: Budget variance data
        from_date: Report start date
        to_date: Report end date
    """
    sheets = {
        'Daily Forecast': daily_df,
        'Weekly Summary': weekly_df,
        'Budget Variance': variance_df
    }

    filename = f"forecast_report_{from_date}_{to_date}.xlsx"
    create_excel_download(sheets, filename, "📥 Download Full Report")


def format_dataframe_for_export(
    df: pd.DataFrame,
    date_columns: List[str] = None,
    currency_columns: List[str] = None,
    percentage_columns: List[str] = None
) -> pd.DataFrame:
    """
    Format a DataFrame for clean export

    Args:
        df: DataFrame to format
        date_columns: Columns to format as dates
        currency_columns: Columns to format as currency
        percentage_columns: Columns to format as percentages

    Returns:
        Formatted DataFrame copy
    """
    export_df = df.copy()

    # Format date columns
    if date_columns:
        for col in date_columns:
            if col in export_df.columns:
                export_df[col] = pd.to_datetime(export_df[col]).dt.strftime('%Y-%m-%d')

    # Round numeric columns
    numeric_cols = export_df.select_dtypes(include=['float64', 'float32']).columns
    for col in numeric_cols:
        if currency_columns and col in currency_columns:
            export_df[col] = export_df[col].round(2)
        elif percentage_columns and col in percentage_columns:
            export_df[col] = export_df[col].round(1)
        else:
            export_df[col] = export_df[col].round(2)

    return export_df
