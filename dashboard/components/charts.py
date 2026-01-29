"""
Reusable Plotly chart components
"""
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from typing import List, Optional, Dict

# Standard color palette
COLORS = {
    'prophet': '#1f77b4',
    'xgboost': '#ff7f0e',
    'pickup': '#2ca02c',
    'actual': '#d62728',
    'budget': '#9467bd',
    'positive': '#2ca02c',
    'negative': '#d62728',
    'neutral': '#7f7f7f'
}


def forecast_comparison_chart(
    df: pd.DataFrame,
    date_col: str = 'Date',
    models: List[str] = ['Prophet', 'XGBoost', 'Pickup'],
    title: str = 'Forecast Comparison',
    y_label: str = 'Value',
    show_confidence: bool = True,
    height: int = 400
) -> go.Figure:
    """
    Create a forecast comparison chart with multiple models

    Args:
        df: DataFrame with date column and model columns
        date_col: Name of date column
        models: List of model column names to plot
        title: Chart title
        y_label: Y-axis label
        show_confidence: Show confidence intervals if available
        height: Chart height in pixels

    Returns:
        Plotly Figure object
    """
    fig = go.Figure()

    for model in models:
        if model in df.columns:
            color = COLORS.get(model.lower(), '#7f7f7f')

            # Add confidence interval if available
            if show_confidence and f'{model}_Lower' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df[date_col], y=df[f'{model}_Upper'],
                    mode='lines', line=dict(width=0),
                    showlegend=False
                ))
                fig.add_trace(go.Scatter(
                    x=df[date_col], y=df[f'{model}_Lower'],
                    mode='lines', line=dict(width=0),
                    fill='tonexty', fillcolor=f'rgba{tuple(list(px.colors.hex_to_rgb(color)) + [0.2])}',
                    showlegend=False
                ))

            # Main line
            fig.add_trace(go.Scatter(
                x=df[date_col], y=df[model],
                name=model,
                line=dict(color=color, width=2)
            ))

    # Add actual if present
    if 'Actual' in df.columns:
        actual_df = df.dropna(subset=['Actual'])
        fig.add_trace(go.Scatter(
            x=actual_df[date_col], y=actual_df['Actual'],
            name='Actual',
            mode='markers',
            marker=dict(color=COLORS['actual'], size=10, symbol='star')
        ))

    # Add budget if present
    if 'Budget' in df.columns:
        fig.add_trace(go.Scatter(
            x=df[date_col], y=df['Budget'],
            name='Budget',
            line=dict(color=COLORS['budget'], width=2, dash='dash')
        ))

    fig.update_layout(
        title=title,
        xaxis_title='Date',
        yaxis_title=y_label,
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        height=height,
        hovermode='x unified'
    )

    return fig


def variance_bar_chart(
    df: pd.DataFrame,
    date_col: str = 'Date',
    variance_col: str = 'Variance_Pct',
    title: str = 'Variance Analysis',
    height: int = 350
) -> go.Figure:
    """
    Create a variance bar chart with positive/negative coloring

    Args:
        df: DataFrame with date and variance columns
        date_col: Name of date column
        variance_col: Name of variance column
        title: Chart title
        height: Chart height

    Returns:
        Plotly Figure object
    """
    colors = [COLORS['positive'] if v >= 0 else COLORS['negative'] for v in df[variance_col]]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=df[date_col],
        y=df[variance_col],
        marker_color=colors,
        text=df[variance_col].round(1),
        textposition='outside'
    ))

    fig.update_layout(
        title=title,
        xaxis_title='Date',
        yaxis_title='Variance %',
        height=height
    )

    return fig


def model_accuracy_chart(
    accuracy_df: pd.DataFrame,
    models: List[str] = ['Prophet', 'XGBoost', 'Pickup'],
    title: str = 'Model Accuracy Comparison',
    height: int = 350
) -> go.Figure:
    """
    Create a grouped bar chart comparing model accuracy metrics

    Args:
        accuracy_df: DataFrame with Model column and metric columns (MAE, RMSE, MAPE)
        models: List of models to include
        title: Chart title
        height: Chart height

    Returns:
        Plotly Figure object
    """
    fig = go.Figure()

    metrics = ['MAE', 'RMSE', 'MAPE (%)']

    for metric in metrics:
        if metric in accuracy_df.columns:
            fig.add_trace(go.Bar(
                name=metric,
                x=accuracy_df['Model'],
                y=accuracy_df[metric],
                text=accuracy_df[metric].round(2),
                textposition='outside'
            ))

    fig.update_layout(
        barmode='group',
        title=title,
        xaxis_title='Model',
        yaxis_title='Error',
        height=height,
        legend=dict(orientation='h', yanchor='bottom', y=1.02)
    )

    return fig


def pickup_curve_chart(
    curve_df: pd.DataFrame,
    title: str = 'Pickup Curve',
    height: int = 350
) -> go.Figure:
    """
    Create a pickup curve chart with confidence bands

    Args:
        curve_df: DataFrame with Days_Out, Avg_Pct, Std_Dev columns
        title: Chart title
        height: Chart height

    Returns:
        Plotly Figure object
    """
    fig = go.Figure()

    # Confidence band
    if 'Std_Dev' in curve_df.columns:
        fig.add_trace(go.Scatter(
            x=curve_df['Days_Out'],
            y=curve_df['Avg_Pct'] + curve_df['Std_Dev'],
            mode='lines', line=dict(width=0),
            showlegend=False
        ))
        fig.add_trace(go.Scatter(
            x=curve_df['Days_Out'],
            y=curve_df['Avg_Pct'] - curve_df['Std_Dev'],
            mode='lines', line=dict(width=0),
            fill='tonexty', fillcolor='rgba(31, 119, 180, 0.2)',
            showlegend=False
        ))

    # Main curve
    fig.add_trace(go.Scatter(
        x=curve_df['Days_Out'],
        y=curve_df['Avg_Pct'],
        mode='lines+markers',
        name='Avg % of Final',
        line=dict(color=COLORS['prophet'], width=3)
    ))

    fig.update_layout(
        title=title,
        xaxis_title='Days Before Stay',
        yaxis_title='% of Final Value',
        xaxis=dict(autorange='reversed'),
        height=height
    )

    return fig


def heatmap_chart(
    pivot_df: pd.DataFrame,
    title: str = 'Heatmap',
    color_scale: str = 'RdYlGn',
    height: int = 300
) -> go.Figure:
    """
    Create a heatmap from a pivot table

    Args:
        pivot_df: Pivot table DataFrame
        title: Chart title
        color_scale: Plotly color scale name
        height: Chart height

    Returns:
        Plotly Figure object
    """
    fig = px.imshow(
        pivot_df,
        color_continuous_scale=color_scale,
        aspect='auto',
        text_auto='.1f'
    )

    fig.update_layout(
        title=title,
        height=height
    )

    return fig
