"""
Model Explainability API endpoints
Explain why forecasts have specific values
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import get_db
from auth import get_current_user

router = APIRouter()


@router.get("/forecast")
async def explain_forecast(
    forecast_date: date = Query(...),
    forecast_type: str = Query(...),
    model: str = Query("prophet", description="Model: prophet, xgboost, pickup, tft"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get full breakdown of how a forecast was calculated.
    Returns different explanations based on model type.
    """
    # Get the forecast value
    forecast_query = """
        SELECT predicted_value, lower_bound, upper_bound, generated_at
        FROM forecasts
        WHERE forecast_date = :forecast_date
            AND forecast_type = :forecast_type
            AND model_type = :model
        ORDER BY generated_at DESC
        LIMIT 1
    """

    result = await db.execute(text(forecast_query), {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type,
        "model": model
    })
    forecast = result.fetchone()

    if not forecast:
        return {
            "forecast_date": forecast_date,
            "forecast_type": forecast_type,
            "model": model,
            "error": "No forecast found"
        }

    # Get model-specific explanation
    if model == "prophet":
        return await _get_prophet_explanation(db, forecast_date, forecast_type, forecast)
    elif model == "xgboost":
        return await _get_xgboost_explanation(db, forecast_date, forecast_type, forecast)
    elif model == "pickup":
        return await _get_pickup_explanation(db, forecast_date, forecast_type, forecast)
    elif model == "tft":
        return await _get_tft_explanation(db, forecast_date, forecast_type, forecast)
    else:
        return {
            "forecast_date": forecast_date,
            "forecast_type": forecast_type,
            "model": model,
            "predicted_value": float(forecast.predicted_value),
            "explanation": "No detailed explanation available for this model"
        }


async def _get_prophet_explanation(db, forecast_date, forecast_type, forecast):
    """Get Prophet model decomposition explanation"""
    query = """
        SELECT
            trend,
            yearly_seasonality,
            weekly_seasonality,
            daily_seasonality,
            holiday_effects,
            regressor_effects
        FROM prophet_decomposition
        WHERE forecast_date = :forecast_date
            AND forecast_type = :forecast_type
        ORDER BY generated_at DESC
        LIMIT 1
    """

    result = await db.execute(text(query), {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type
    })
    decomp = result.fetchone()

    explanation = {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type,
        "model": "prophet",
        "predicted_value": float(forecast.predicted_value),
        "lower_bound": float(forecast.lower_bound) if forecast.lower_bound else None,
        "upper_bound": float(forecast.upper_bound) if forecast.upper_bound else None,
        "generated_at": forecast.generated_at
    }

    if decomp:
        components = []
        if decomp.trend:
            components.append({
                "name": "Base trend",
                "value": float(decomp.trend),
                "description": "Long-term average trend"
            })
        if decomp.yearly_seasonality:
            components.append({
                "name": "Yearly seasonality",
                "value": float(decomp.yearly_seasonality),
                "description": "Annual pattern (e.g., summer peak, winter low)"
            })
        if decomp.weekly_seasonality:
            components.append({
                "name": "Weekly seasonality",
                "value": float(decomp.weekly_seasonality),
                "description": "Day-of-week pattern (e.g., weekend higher)"
            })
        if decomp.holiday_effects:
            for holiday, effect in decomp.holiday_effects.items():
                components.append({
                    "name": f"Holiday: {holiday}",
                    "value": float(effect),
                    "description": f"Effect of {holiday}"
                })

        explanation["components"] = components
        explanation["breakdown"] = {
            "trend": float(decomp.trend) if decomp.trend else 0,
            "yearly": float(decomp.yearly_seasonality) if decomp.yearly_seasonality else 0,
            "weekly": float(decomp.weekly_seasonality) if decomp.weekly_seasonality else 0,
            "holidays": decomp.holiday_effects
        }

    return explanation


async def _get_xgboost_explanation(db, forecast_date, forecast_type, forecast):
    """Get XGBoost SHAP explanation"""
    query = """
        SELECT
            base_value,
            feature_values,
            shap_values,
            top_positive,
            top_negative
        FROM xgboost_explanations
        WHERE forecast_date = :forecast_date
            AND forecast_type = :forecast_type
        ORDER BY generated_at DESC
        LIMIT 1
    """

    result = await db.execute(text(query), {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type
    })
    shap = result.fetchone()

    explanation = {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type,
        "model": "xgboost",
        "predicted_value": float(forecast.predicted_value),
        "generated_at": forecast.generated_at
    }

    if shap:
        explanation["base_value"] = float(shap.base_value) if shap.base_value else None
        explanation["feature_values"] = shap.feature_values
        explanation["shap_values"] = shap.shap_values
        explanation["top_drivers"] = {
            "positive": shap.top_positive or [],
            "negative": shap.top_negative or []
        }

        # Build human-readable summary
        summary_parts = []
        if shap.top_positive:
            for item in shap.top_positive[:3]:
                if isinstance(item, dict):
                    summary_parts.append(f"{item.get('feature', 'Unknown')} (+{item.get('contribution', 0):.1f})")
        if shap.top_negative:
            for item in shap.top_negative[:2]:
                if isinstance(item, dict):
                    summary_parts.append(f"{item.get('feature', 'Unknown')} ({item.get('contribution', 0):.1f})")

        explanation["summary"] = f"Main drivers: {', '.join(summary_parts)}" if summary_parts else None

    return explanation


async def _get_pickup_explanation(db, forecast_date, forecast_type, forecast):
    """Get Pickup model explanation"""
    query = """
        SELECT
            current_otb,
            days_out,
            comparison_date,
            comparison_otb,
            comparison_final,
            pickup_curve_pct,
            pickup_curve_stddev,
            pace_vs_prior_pct,
            projection_method,
            projected_value,
            confidence_note
        FROM pickup_explanations
        WHERE forecast_date = :forecast_date
            AND forecast_type = :forecast_type
        ORDER BY generated_at DESC
        LIMIT 1
    """

    result = await db.execute(text(query), {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type
    })
    pickup = result.fetchone()

    explanation = {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type,
        "model": "pickup",
        "predicted_value": float(forecast.predicted_value),
        "generated_at": forecast.generated_at
    }

    if pickup:
        explanation["current_state"] = {
            "on_the_books": float(pickup.current_otb) if pickup.current_otb is not None else None,
            "days_out": pickup.days_out
        }
        explanation["comparison"] = {
            "date": pickup.comparison_date,
            "otb_at_same_lead_time": float(pickup.comparison_otb) if pickup.comparison_otb is not None else None,
            "final_actual": float(pickup.comparison_final) if pickup.comparison_final is not None else None
        }
        explanation["pickup_curve"] = {
            "avg_pct_of_final": float(pickup.pickup_curve_pct) if pickup.pickup_curve_pct is not None else None,
            "std_dev": float(pickup.pickup_curve_stddev) if pickup.pickup_curve_stddev is not None else None
        }
        explanation["pace_analysis"] = {
            "vs_prior_year_pct": float(pickup.pace_vs_prior_pct) if pickup.pace_vs_prior_pct is not None else None,
            "projection_method": pickup.projection_method,
            "projected_final": float(pickup.projected_value) if pickup.projected_value else None
        }
        explanation["confidence_note"] = pickup.confidence_note

        # Build summary
        pace_str = ""
        if pickup.pace_vs_prior_pct:
            if pickup.pace_vs_prior_pct > 0:
                pace_str = f"{pickup.pace_vs_prior_pct:.1f}% ahead of last year's pace"
            else:
                pace_str = f"{abs(pickup.pace_vs_prior_pct):.1f}% behind last year's pace"

        explanation["summary"] = f"At {pickup.days_out} days out, {pace_str}" if pace_str else None

    return explanation


@router.get("/prophet")
async def get_prophet_decomposition(
    forecast_date: date = Query(...),
    forecast_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get Prophet decomposition (trend, seasonality, holidays) for a forecast.
    """
    return await _get_prophet_explanation(
        db, forecast_date, forecast_type,
        type('obj', (object,), {
            'predicted_value': 0,
            'lower_bound': None,
            'upper_bound': None,
            'generated_at': None
        })()
    )


@router.get("/xgboost")
async def get_xgboost_shap(
    forecast_date: date = Query(...),
    forecast_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get XGBoost SHAP values and feature contributions for a forecast.
    """
    return await _get_xgboost_explanation(
        db, forecast_date, forecast_type,
        type('obj', (object,), {
            'predicted_value': 0,
            'generated_at': None
        })()
    )


@router.get("/pickup")
async def get_pickup_breakdown(
    forecast_date: date = Query(...),
    forecast_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get Pickup model calculation breakdown for a forecast.
    """
    return await _get_pickup_explanation(
        db, forecast_date, forecast_type,
        type('obj', (object,), {
            'predicted_value': 0,
            'generated_at': None
        })()
    )


async def _get_tft_explanation(db, forecast_date, forecast_type, forecast):
    """Get TFT attention-based explanation"""
    query = """
        SELECT
            encoder_attention,
            decoder_attention,
            variable_importance,
            quantile_10,
            quantile_50,
            quantile_90,
            top_historical_drivers,
            top_future_drivers
        FROM tft_explanations
        WHERE forecast_date = :forecast_date
            AND forecast_type = :forecast_type
        ORDER BY generated_at DESC
        LIMIT 1
    """

    result = await db.execute(text(query), {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type
    })
    tft = result.fetchone()

    explanation = {
        "forecast_date": forecast_date,
        "forecast_type": forecast_type,
        "model": "tft",
        "predicted_value": float(forecast.predicted_value),
        "lower_bound": float(forecast.lower_bound) if forecast.lower_bound else None,
        "upper_bound": float(forecast.upper_bound) if forecast.upper_bound else None,
        "generated_at": forecast.generated_at
    }

    if tft:
        explanation["quantiles"] = {
            "p10": float(tft.quantile_10) if tft.quantile_10 else None,
            "p50": float(tft.quantile_50) if tft.quantile_50 else None,
            "p90": float(tft.quantile_90) if tft.quantile_90 else None
        }
        explanation["variable_importance"] = tft.variable_importance
        explanation["top_drivers"] = {
            "historical": tft.top_historical_drivers or [],
            "future_known": tft.top_future_drivers or []
        }
        explanation["attention"] = {
            "encoder": tft.encoder_attention,
            "decoder": tft.decoder_attention
        }

        # Build human-readable summary
        summary_parts = []
        if tft.top_historical_drivers:
            for item in tft.top_historical_drivers[:2]:
                if isinstance(item, dict):
                    summary_parts.append(
                        f"{item.get('feature', 'Unknown')} ({item.get('importance', 0):.2f})"
                    )
        if tft.top_future_drivers:
            for item in tft.top_future_drivers[:2]:
                if isinstance(item, dict):
                    summary_parts.append(
                        f"{item.get('feature', 'Unknown')} ({item.get('importance', 0):.2f})"
                    )

        explanation["summary"] = f"Key drivers: {', '.join(summary_parts)}" if summary_parts else None

    return explanation


@router.get("/tft")
async def get_tft_attention(
    forecast_date: date = Query(...),
    forecast_type: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get TFT attention weights and variable importance for a forecast.
    """
    return await _get_tft_explanation(
        db, forecast_date, forecast_type,
        type('obj', (object,), {
            'predicted_value': 0,
            'lower_bound': None,
            'upper_bound': None,
            'generated_at': None
        })()
    )
