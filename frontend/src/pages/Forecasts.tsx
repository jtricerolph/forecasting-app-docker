import React, { useState, useMemo, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import {
  colors,
  spacing,
  radius,
  typography,
  shadows,
} from '../utils/theme'

type ForecastPage = 'accom' | 'dry' | 'wet' | 'total' | 'occupancy' | 'rooms' | 'preview' | 'prophet' | 'xgboost' | 'catboost' | 'blended' | 'pickup_v2' | 'compare' | 'accom_day' | 'accom_week' | 'accom_month' | 'bookings_day' | 'bookings_week' | 'bookings_month' | 'covers_day' | 'covers_week' | 'covers_month' | 'resos_dry_day' | 'resos_dry_week' | 'resos_dry_month' | 'resos_wet_day' | 'resos_wet_week' | 'resos_wet_month' | 'total_rev_day' | 'total_rev_week' | 'total_rev_month' | 'hotel_rev_day' | 'hotel_rev_week' | 'hotel_rev_month'
type MetricType = 'occupancy' | 'rooms' | 'guests' | 'ave_guest_rate' | 'arr' | 'net_accom' | 'net_dry' | 'net_wet' | 'total_rev'

// Consistent forecast model colors
const CHART_COLORS = {
  currentOtb: '#10b981',      // Green - confirmed/safe bookings
  pickup: '#ef4444',          // Red - pickup forecast
  prophet: '#3b82f6',         // Blue - prophet forecast
  prophetConfidence: 'rgba(59, 130, 246, 0.15)', // Light blue fill
  xgboost: '#fdba74',         // Light orange - xgboost forecast
  catboost: '#9467bd',        // Purple - catboost forecast
  blended: '#ea580c',         // Dark orange - blended forecast
  priorOtb: '#9ca3af',        // Gray dashed
  priorFinal: '#6b7280',      // Darker gray dotted
  priorFinalFill: 'rgba(107, 114, 128, 0.1)',
  budget: '#8b5cf6',          // Purple - budget target line
  futureOtb: '#06b6d4',       // Cyan - future OTB from bookings
}

// Revenue metrics that support budget comparison
const REVENUE_METRICS = ['net_accom', 'net_dry', 'net_wet', 'total_rev']

// Metrics that have OTB (on-the-books) data available
const OTB_METRICS = ['net_accom', 'occupancy', 'rooms']

// Helper to fetch and build budget trace for charts
const useBudgetData = (startDate: string, endDate: string, metric: MetricType, token: string | null) => {
  const { data: budgetData } = useQuery<{ date: string; budget_type: string; budget_value: number }[]>({
    queryKey: ['daily-budgets-chart', startDate, endDate, metric],
    queryFn: async () => {
      if (!REVENUE_METRICS.includes(metric)) return []
      const params = new URLSearchParams({
        from_date: startDate,
        to_date: endDate,
        budget_type: metric
      })
      const response = await fetch(`/api/budget/daily?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate && REVENUE_METRICS.includes(metric),
  })
  return budgetData
}

// Build budget trace for Plotly chart - returns any to avoid strict type conflicts with existing traces
const buildBudgetTrace = (budgetData: { date: string; budget_value: number }[] | undefined): any => {
  if (!budgetData || budgetData.length === 0) return null
  return {
    x: budgetData.map(d => d.date),
    y: budgetData.map(d => d.budget_value) as (number | null)[],
    type: 'scatter' as const,
    mode: 'lines' as const,
    name: 'Budget Target',
    line: { color: CHART_COLORS.budget, width: 2, dash: 'dash' as const },
    hovertemplate: 'Budget: £%{y:,.0f}<extra></extra>',
  }
}

interface PreviewDataPoint {
  date: string
  day_of_week: string
  lead_days: number
  current_otb: number | null
  prior_year_date: string
  prior_year_dow: string
  prior_year_otb: number | null
  prior_year_final: number | null
  expected_pickup: number | null
  forecast: number | null
  pace_vs_prior_pct: number | null
}

interface PreviewSummary {
  otb_total: number
  forecast_total: number
  prior_otb_total: number
  prior_final_total: number
  pace_pct: number | null
  days_count: number
}

interface PreviewResponse {
  data: PreviewDataPoint[]
  summary: PreviewSummary
}

interface PaceCurvePoint {
  days_out: number
  rooms: number | null
}

interface PaceCurveResponse {
  arrival_date: string
  day_of_week: string
  current_year: PaceCurvePoint[]
  prior_year: PaceCurvePoint[]
  final_value: number | null
  prior_year_final: number | null
}

interface ProphetDataPoint {
  date: string
  day_of_week: string
  current_otb: number | null
  prior_year_otb: number | null
  forecast: number | null
  forecast_lower: number | null
  forecast_upper: number | null
  prior_year_final: number | null
}

interface ProphetSummary {
  otb_total: number
  prior_otb_total: number
  forecast_total: number
  prior_final_total: number
  days_count: number
  days_forecasting_more: number
  days_forecasting_less: number
}

interface ProphetResponse {
  data: ProphetDataPoint[]
  summary: ProphetSummary
}

interface XGBoostDataPoint {
  date: string
  day_of_week: string
  current_otb: number | null
  prior_year_otb: number | null
  forecast: number | null
  prior_year_final: number | null
}

interface XGBoostSummary {
  otb_total: number
  prior_otb_total: number
  forecast_total: number
  prior_final_total: number
  days_count: number
  days_forecasting_more: number
  days_forecasting_less: number
}

interface XGBoostResponse {
  data: XGBoostDataPoint[]
  summary: XGBoostSummary
}

interface CatBoostDataPoint {
  date: string
  day_of_week: string
  current_otb: number | null
  prior_year_otb: number | null
  forecast: number | null
  prior_year_final: number | null
}

interface CatBoostSummary {
  otb_total: number
  prior_otb_total: number
  forecast_total: number
  prior_final_total: number
  days_count: number
  days_forecasting_more: number
  days_forecasting_less: number
}

interface CatBoostResponse {
  data: CatBoostDataPoint[]
  summary: CatBoostSummary
}

interface BlendedPreviewDataPoint {
  date: string
  day_of_week: string
  current_otb: number | null
  prior_year_otb: number | null
  blended_forecast: number | null
  prophet_forecast: number | null
  xgboost_forecast: number | null
  catboost_forecast: number | null
  budget_or_prior: number | null
  prior_year_final: number | null
}

interface BlendedPreviewSummary {
  otb_total: number
  prior_otb_total: number
  forecast_total: number
  prior_final_total: number
  days_count: number
  days_forecasting_more: number
  days_forecasting_less: number
  prophet_weight: number
  xgboost_weight: number
  catboost_weight: number
}

interface BlendedPreviewResponse {
  data: BlendedPreviewDataPoint[]
  summary: BlendedPreviewSummary
}

// Pickup-V2 interfaces
interface PickupV2DataPoint {
  date: string
  day_of_week: string
  lead_days: number
  prior_year_date: string
  current_otb_rev: number | null
  prior_year_otb_rev: number | null
  prior_year_final_rev: number | null
  expected_pickup_rev: number | null
  forecast: number
  upper_bound: number | null
  lower_bound: number | null
  ceiling: number | null
  // Scenario values
  at_prior_adr: number | null
  at_current_rate: number | null
  at_cheaper_50: number | null
  at_expensive_50: number | null
  // Pricing opportunity fields
  has_pricing_opportunity: boolean | null
  lost_potential: number | null
  rate_gap: number | null
  rate_vs_prior_pct: number | null
  pace_vs_prior_pct: number | null
  pickup_rooms_total: number | null
  // Weighted average rates per room for display (net)
  weighted_avg_prior_rate: number | null
  weighted_avg_current_rate: number | null
  // Gross rates (inc VAT) for UI display
  weighted_avg_prior_rate_gross: number | null
  weighted_avg_current_rate_gross: number | null
  // Listed rate at lead time (earliest bookings) - for rate comparison
  weighted_avg_listed_rate: number | null
  weighted_avg_listed_rate_gross: number | null
  // Effective rate = rate actually used in forecast (min of prior and current)
  effective_rate: number | null
  effective_rate_gross: number | null
  // Room metrics
  current_otb: number | null
  prior_year_otb: number | null
  prior_year_final: number | null
  expected_pickup: number | null
  floor: number | null
  category_breakdown: Record<string, any> | null
}

interface PickupV2Summary {
  otb_rev_total: number | null
  forecast_total: number
  upper_total: number | null
  lower_total: number | null
  prior_final_total: number | null
  avg_adr_position: number | null
  avg_pace_pct: number | null
  days_count: number
  // Pricing opportunity summary
  lost_potential_total: number | null
  opportunity_days_count: number | null
}

interface PickupV2Response {
  data: PickupV2DataPoint[]
  summary: PickupV2Summary
}

const Forecasts: React.FC = () => {
  const { forecastId } = useParams<{ forecastId?: string }>()
  const navigate = useNavigate()
  const activePage = (forecastId as ForecastPage) || 'hotel_rev_day'

  const revenueItems: { id: ForecastPage; label: string }[] = [
    { id: 'accom', label: 'Accommodation' },
    { id: 'dry', label: 'Dry (Food)' },
    { id: 'wet', label: 'Wet (Beverage)' },
    { id: 'total', label: 'Total Revenue' },
  ]

  const occupancyItems: { id: ForecastPage; label: string }[] = [
    { id: 'occupancy', label: 'Occupancy %' },
    { id: 'rooms', label: 'Room Nights' },
  ]

  // Combined Total Revenue (top of sidebar)
  const totalRevenueItems: { id: ForecastPage; label: string }[] = [
    { id: 'total_rev_day', label: 'Total by Day' },
    { id: 'total_rev_week', label: 'Total by Week' },
    { id: 'total_rev_month', label: 'Total by Month' },
  ]

  // Hotel Revenue section (accommodation)
  const hotelRevenueItems: { id: ForecastPage; label: string }[] = [
    { id: 'hotel_rev_day', label: 'Revenue by Day' },
    { id: 'hotel_rev_week', label: 'Revenue by Week' },
    { id: 'hotel_rev_month', label: 'Revenue by Month' },
  ]

  // Hotel Bookings section (room nights)
  const hotelBookingsItems: { id: ForecastPage; label: string }[] = [
    { id: 'bookings_day', label: 'Bookings by Day' },
    { id: 'bookings_week', label: 'Bookings by Week' },
    { id: 'bookings_month', label: 'Bookings by Month' },
  ]

  // Restaurant Revenue section
  const restaurantDryItems: { id: ForecastPage; label: string }[] = [
    { id: 'resos_dry_day', label: 'Dry by Day' },
    { id: 'resos_dry_week', label: 'Dry by Week' },
    { id: 'resos_dry_month', label: 'Dry by Month' },
  ]

  const restaurantWetItems: { id: ForecastPage; label: string }[] = [
    { id: 'resos_wet_day', label: 'Wet by Day' },
    { id: 'resos_wet_week', label: 'Wet by Week' },
    { id: 'resos_wet_month', label: 'Wet by Month' },
  ]

  // Restaurant Covers section
  const restaurantCoversItems: { id: ForecastPage; label: string }[] = [
    { id: 'covers_day', label: 'Covers by Day' },
    { id: 'covers_week', label: 'Covers by Week' },
    { id: 'covers_month', label: 'Covers by Month' },
  ]

  const previewItems: { id: ForecastPage; label: string }[] = [
    { id: 'preview', label: 'Pickup' },
    { id: 'pickup_v2', label: 'Pickup-V2 (Revenue)' },
    { id: 'prophet', label: 'Prophet' },
    { id: 'xgboost', label: 'XGBoost' },
    { id: 'catboost', label: 'CatBoost' },
    { id: 'blended', label: 'Blended' },
  ]

  // Collapsible state for Testing section (closed by default)
  const [testingExpanded, setTestingExpanded] = useState(false)

  const handlePageChange = (id: ForecastPage) => {
    navigate(`/forecasts/${id}`)
  }

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        {/* FORECASTS - Production models */}
        <h3 style={styles.sidebarTitle}>Forecasts</h3>
        <nav style={styles.nav}>
          {/* Combined Total Revenue Section */}
          <div style={styles.navSection}>Revenue (Combined Total)</div>
          {totalRevenueItems.map((item) => (
            <button
              key={item.id}
              onClick={() => handlePageChange(item.id)}
              style={{
                ...styles.navItem,
                ...styles.navItemIndented,
                ...(activePage === item.id ? styles.navItemActive : {}),
              }}
            >
              {item.label}
            </button>
          ))}

          {/* HOTEL Section */}
          <div style={{ ...styles.navSection, marginTop: spacing.lg, fontSize: typography.sm, fontWeight: typography.semibold, letterSpacing: '0.05em' }}>HOTEL</div>

          {/* Hotel Revenue (Accommodation) */}
          <div style={{ ...styles.navSection, marginTop: spacing.xs, paddingLeft: spacing.sm }}>Revenue</div>
          {hotelRevenueItems.map((item) => (
            <button
              key={item.id}
              onClick={() => handlePageChange(item.id)}
              style={{
                ...styles.navItem,
                ...styles.navItemIndented,
                ...(activePage === item.id ? styles.navItemActive : {}),
              }}
            >
              {item.label}
            </button>
          ))}

          {/* Hotel Bookings (Room Nights) */}
          <div style={{ ...styles.navSection, marginTop: spacing.xs, paddingLeft: spacing.sm }}>Bookings</div>
          {hotelBookingsItems.map((item) => (
            <button
              key={item.id}
              onClick={() => handlePageChange(item.id)}
              style={{
                ...styles.navItem,
                ...styles.navItemIndented,
                ...(activePage === item.id ? styles.navItemActive : {}),
              }}
            >
              {item.label}
            </button>
          ))}

          {/* RESTAURANT Section */}
          <div style={{ ...styles.navSection, marginTop: spacing.lg, fontSize: typography.sm, fontWeight: typography.semibold, letterSpacing: '0.05em' }}>RESTAURANT</div>

          {/* Dry (Food) Revenue */}
          <div style={{ ...styles.navSection, marginTop: spacing.xs, paddingLeft: spacing.sm }}>Dry (Food)</div>
          {restaurantDryItems.map((item) => (
            <button
              key={item.id}
              onClick={() => handlePageChange(item.id)}
              style={{
                ...styles.navItem,
                ...styles.navItemIndented,
                ...(activePage === item.id ? styles.navItemActive : {}),
              }}
            >
              {item.label}
            </button>
          ))}

          {/* Wet (Drinks) Revenue */}
          <div style={{ ...styles.navSection, marginTop: spacing.xs, paddingLeft: spacing.sm }}>Wet (Drinks)</div>
          {restaurantWetItems.map((item) => (
            <button
              key={item.id}
              onClick={() => handlePageChange(item.id)}
              style={{
                ...styles.navItem,
                ...styles.navItemIndented,
                ...(activePage === item.id ? styles.navItemActive : {}),
              }}
            >
              {item.label}
            </button>
          ))}

          {/* Covers */}
          <div style={{ ...styles.navSection, marginTop: spacing.xs, paddingLeft: spacing.sm }}>Covers</div>
          {restaurantCoversItems.map((item) => (
            <button
              key={item.id}
              onClick={() => handlePageChange(item.id)}
              style={{
                ...styles.navItem,
                ...styles.navItemIndented,
                ...(activePage === item.id ? styles.navItemActive : {}),
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>

        {/* TESTING FORECASTS - Development/preview models (collapsible) */}
        <h3
          style={{
            ...styles.sidebarTitle,
            marginTop: spacing.lg,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
          onClick={() => setTestingExpanded(!testingExpanded)}
        >
          <span>Testing Forecasts</span>
          <span style={{ fontSize: typography.sm, opacity: 0.7 }}>
            {testingExpanded ? '▼' : '▶'}
          </span>
        </h3>
        {testingExpanded && (
          <nav style={styles.nav}>
            {/* Revenue Section */}
            <div style={styles.navSection}>Revenue</div>
            {revenueItems.map((item) => (
              <button
                key={item.id}
                onClick={() => handlePageChange(item.id)}
                style={{
                  ...styles.navItem,
                  ...styles.navItemIndented,
                  ...(activePage === item.id ? styles.navItemActive : {}),
                }}
              >
                {item.label}
              </button>
            ))}

            {/* Occupancy Section */}
            <div style={{ ...styles.navSection, marginTop: spacing.md }}>Occupancy</div>
            {occupancyItems.map((item) => (
              <button
                key={item.id}
                onClick={() => handlePageChange(item.id)}
                style={{
                  ...styles.navItem,
                  ...styles.navItemIndented,
                  ...(activePage === item.id ? styles.navItemActive : {}),
                }}
              >
                {item.label}
              </button>
            ))}

            {/* Previews Section */}
            <div style={{ ...styles.navSection, marginTop: spacing.md }}>Previews</div>
            {previewItems.map((item) => (
              <button
                key={item.id}
                onClick={() => handlePageChange(item.id)}
                style={{
                  ...styles.navItem,
                  ...styles.navItemIndented,
                  ...(activePage === item.id ? styles.navItemActive : {}),
                }}
              >
                {item.label}
              </button>
            ))}

            {/* Compare Section */}
            <div style={{ ...styles.navSection, marginTop: spacing.md }}>Analysis</div>
            <button
              onClick={() => handlePageChange('compare')}
              style={{
                ...styles.navItem,
                ...styles.navItemIndented,
                ...(activePage === 'compare' ? styles.navItemActive : {}),
              }}
            >
              Compare Models
            </button>
            <button
              onClick={() => navigate('/accuracy')}
              style={{
                ...styles.navItem,
                ...styles.navItemIndented,
              }}
            >
              Accuracy Report
            </button>
          </nav>
        )}
      </div>

      <main style={styles.content}>
        {/* Combined Total Revenue (Accom + Dry + Wet) */}
        {activePage === 'total_rev_day' && <TotalRevenueForecast consolidation="daily" />}
        {activePage === 'total_rev_week' && <TotalRevenueForecast consolidation="weekly" />}
        {activePage === 'total_rev_month' && <TotalRevenueForecast consolidation="monthly" />}
        {/* Hotel Revenue (Accommodation) - Uses existing PickupV2Forecast */}
        {activePage === 'hotel_rev_day' && <PickupV2Forecast consolidation="daily" />}
        {activePage === 'hotel_rev_week' && <PickupV2Forecast consolidation="weekly" />}
        {activePage === 'hotel_rev_month' && <PickupV2Forecast consolidation="monthly" />}
        {/* Legacy accom routes (redirect to hotel_rev) */}
        {activePage === 'accom_day' && <PickupV2Forecast consolidation="daily" />}
        {activePage === 'accom_week' && <PickupV2Forecast consolidation="weekly" />}
        {activePage === 'accom_month' && <PickupV2Forecast consolidation="monthly" />}
        {/* Hotel Bookings (Room Nights) */}
        {activePage === 'bookings_day' && <PickupV2BookingsForecast consolidation="daily" />}
        {activePage === 'bookings_week' && <PickupV2BookingsForecast consolidation="weekly" />}
        {activePage === 'bookings_month' && <PickupV2BookingsForecast consolidation="monthly" />}
        {/* Restaurant Revenue - Dry (Food) */}
        {activePage === 'resos_dry_day' && <RestaurantRevenueForecast consolidation="daily" revenueType="dry" />}
        {activePage === 'resos_dry_week' && <RestaurantRevenueForecast consolidation="weekly" revenueType="dry" />}
        {activePage === 'resos_dry_month' && <RestaurantRevenueForecast consolidation="monthly" revenueType="dry" />}
        {/* Restaurant Revenue - Wet (Drinks) */}
        {activePage === 'resos_wet_day' && <RestaurantRevenueForecast consolidation="daily" revenueType="wet" />}
        {activePage === 'resos_wet_week' && <RestaurantRevenueForecast consolidation="weekly" revenueType="wet" />}
        {activePage === 'resos_wet_month' && <RestaurantRevenueForecast consolidation="monthly" revenueType="wet" />}
        {/* Restaurant Covers */}
        {activePage === 'covers_day' && <RestaurantCoversForecast consolidation="daily" />}
        {activePage === 'covers_week' && <RestaurantCoversForecast consolidation="weekly" />}
        {activePage === 'covers_month' && <RestaurantCoversForecast consolidation="monthly" />}
        {/* Testing Forecasts */}
        {activePage === 'accom' && <MetricForecast metric="net_accom" title="Accommodation Revenue" />}
        {activePage === 'dry' && <MetricForecast metric="net_dry" title="Dry Revenue (Food)" />}
        {activePage === 'wet' && <MetricForecast metric="net_wet" title="Wet Revenue (Beverage)" />}
        {activePage === 'total' && <MetricForecast metric="total_rev" title="Total Net Revenue" />}
        {activePage === 'occupancy' && <MetricForecast metric="occupancy" title="Occupancy %" />}
        {activePage === 'rooms' && <MetricForecast metric="rooms" title="Room Nights" />}
        {activePage === 'preview' && <ForecastPreview />}
        {activePage === 'prophet' && <ProphetPreview />}
        {activePage === 'xgboost' && <XGBoostPreview />}
        {activePage === 'catboost' && <CatBoostPreview />}
        {activePage === 'blended' && <BlendedPreview />}
        {activePage === 'pickup_v2' && <PickupV2Preview />}
        {activePage === 'compare' && <CompareForecasts />}
      </main>
    </div>
  )
}

// Helper to format date as YYYY-MM-DD without timezone issues
const formatDate = (date: Date): string => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

// Helper to generate next 12 months from current month
const getNext12Months = () => {
  const months: { label: string; start: string; end: string }[] = []
  const now = new Date()

  for (let i = 0; i < 12; i++) {
    const date = new Date(now.getFullYear(), now.getMonth() + i, 1)
    const year = date.getFullYear()
    const month = date.getMonth()

    // First day of month
    const startDate = new Date(year, month, 1)
    // Last day of month
    const endDate = new Date(year, month + 1, 0)

    const monthName = date.toLocaleString('default', { month: 'short' })

    months.push({
      label: `${monthName} ${year}`,
      start: formatDate(startDate),
      end: formatDate(endDate),
    })
  }

  return months
}

// ============================================
// METRIC FORECAST COMPONENT
// Combines actuals with blended forecast for a specific metric
// ============================================

interface MetricForecastProps {
  metric: MetricType
  title: string
}

interface ActualsDataPoint {
  date: string
  day_of_week: string
  actual_value: number | null
  prior_year_value: number | null
  budget_value: number | null
}

interface ActualsResponse {
  data: ActualsDataPoint[]
  summary: {
    actual_total: number
    prior_year_total: number
    budget_total: number
    days_with_actuals: number
    total_days: number
  }
}

const MetricForecast: React.FC<MetricForecastProps> = ({ metric, title }) => {
  const token = localStorage.getItem('token')

  // Default to current month, 1 month duration
  const today = new Date()
  const [selectedMonth, setSelectedMonth] = useState(() => `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`)
  const [duration, setDuration] = useState<'1' | '3' | '6' | '12'>('1')
  const [showTable, setShowTable] = useState(false)
  const [consolidation, setConsolidation] = useState<'daily' | 'weekly' | 'monthly'>('daily')

  // Generate month options (24 months back + current + 12 months forward)
  const monthOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const now = new Date()
    // Start 24 months ago, end 12 months ahead (37 months total)
    for (let i = -24; i <= 12; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() + i, 1)
      const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      const label = date.toLocaleString('default', { month: 'short', year: 'numeric' })
      options.push({ value, label })
    }
    return options
  }, [])

  // Calculate start and end dates based on selected month and duration
  const { startDate, endDate } = useMemo(() => {
    const [year, month] = selectedMonth.split('-').map(Number)
    const start = new Date(year, month - 1, 1)
    const durationMonths = parseInt(duration)
    const end = new Date(year, month - 1 + durationMonths, 0) // Last day of the final month
    return {
      startDate: formatDate(start),
      endDate: formatDate(end)
    }
  }, [selectedMonth, duration])

  // Fetch actuals data
  const { data: actualsData, isLoading: actualsLoading } = useQuery<ActualsResponse>({
    queryKey: ['actuals', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/actuals?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch actuals')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch all three model forecasts for blending
  const { data: prophetData, isLoading: prophetLoading } = useQuery<ProphetResponse>({
    queryKey: ['prophet-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/prophet-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch prophet forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  const { data: xgboostData, isLoading: xgboostLoading } = useQuery<XGBoostResponse>({
    queryKey: ['xgboost-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/xgboost-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch xgboost forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  const { data: catboostData, isLoading: catboostLoading } = useQuery<CatBoostResponse>({
    queryKey: ['catboost-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/catboost-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch catboost forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch budget data for revenue metrics
  const budgetData = useBudgetData(startDate, endDate, metric, token)

  const isLoading = actualsLoading || prophetLoading || xgboostLoading || catboostLoading
  const isRevenueMetric = REVENUE_METRICS.includes(metric)

  const metricLabel = {
    occupancy: 'Occupancy %',
    rooms: 'Room Nights',
    guests: 'Guests',
    ave_guest_rate: 'Ave Guest Rate',
    arr: 'ARR',
    net_accom: 'Net Accommodation Revenue',
    net_dry: 'Net Dry Revenue',
    net_wet: 'Net Wet Revenue',
    total_rev: 'Total Net Revenue',
  }[metric] || 'Value'

  const unit = {
    occupancy: '%',
    rooms: ' rooms',
    guests: ' guests',
    ave_guest_rate: '',
    arr: '',
    net_accom: '',
    net_dry: '',
    net_wet: '',
    total_rev: '',
  }[metric] || ''

  // Build budget map
  const budgetMap = useMemo(() => {
    const map: Record<string, number> = {}
    if (budgetData) {
      for (const b of budgetData) {
        map[b.date] = b.budget_value
      }
    }
    return map
  }, [budgetData])

  // Combine actuals + forecast data
  const combinedData = useMemo(() => {
    if (!actualsData?.data || !prophetData?.data || !xgboostData?.data || !catboostData?.data) return null

    const todayStr = formatDate(new Date())

    // Create a map of forecast data by date
    const forecastMap: Record<string, { prophet: number; xgboost: number; catboost: number; priorYearFinal: number | null }> = {}
    prophetData.data.forEach((row, idx) => {
      const xgRow = xgboostData.data[idx]
      const catRow = catboostData.data[idx]
      forecastMap[row.date] = {
        prophet: row.forecast ?? 0,
        xgboost: xgRow?.forecast ?? 0,
        catboost: catRow?.forecast ?? 0,
        priorYearFinal: row.prior_year_final,
      }
    })

    const combined = actualsData.data.map(row => {
      const hasActual = row.actual_value !== null && row.date < todayStr // Exclude today - day not finished
      const forecast = forecastMap[row.date]
      // Use budget from actuals API response, fallback to budgetMap for non-revenue metrics
      const budget = row.budget_value ?? budgetMap[row.date] ?? null
      // OTB value for future dates (accommodation revenue from bookings)
      const otbValue = (row as { otb_value?: number | null }).otb_value ?? null

      // Calculate blended forecast (60% model avg + 40% budget/prior year)
      let blendedForecast: number | null = null
      if (forecast) {
        const modelAvg = (forecast.prophet + forecast.xgboost + forecast.catboost) / 3
        // Temporarily using 100% model average (no budget/prior year weighting)
        blendedForecast = modelAvg

        // Floor cap: forecast can't be below OTB (confirmed bookings)
        // This applies to metrics where OTB represents guaranteed revenue/bookings
        if (otbValue !== null && otbValue > 0 && blendedForecast < otbValue) {
          blendedForecast = otbValue
        }
      }

      // Use actual if available, otherwise use blended forecast
      const displayValue = hasActual ? row.actual_value : blendedForecast

      return {
        date: row.date,
        day_of_week: row.day_of_week,
        actual_value: row.actual_value,
        prior_year_value: row.prior_year_value,
        budget_value: budget,
        otb_value: otbValue,
        blended_forecast: blendedForecast,
        display_value: displayValue,
        is_actual: hasActual,
        prior_year_final: forecast?.priorYearFinal ?? null,
      }
    })

    // Calculate summary statistics
    const actualsToDate = combined.filter(d => d.is_actual)
    const forecastRemaining = combined.filter(d => !d.is_actual)

    // For percentage metrics (occupancy), use averages; for others, use sums
    const isPctMetric = metric === 'occupancy'

    // Calculate totals (sums for revenue/rooms, will convert to avg for pct metrics)
    const actualSum = actualsToDate.reduce((sum, d) => sum + (d.actual_value ?? 0), 0)
    const actualBudgetSum = actualsToDate.reduce((sum, d) => sum + (d.budget_value ?? 0), 0)
    const actualPriorSum = actualsToDate.reduce((sum, d) => sum + (d.prior_year_value ?? 0), 0)

    const forecastSum = forecastRemaining.reduce((sum, d) => sum + (d.blended_forecast ?? 0), 0)
    const forecastBudgetSum = forecastRemaining.reduce((sum, d) => sum + (d.budget_value ?? 0), 0)
    const forecastPriorSum = forecastRemaining.reduce((sum, d) => sum + (d.prior_year_value ?? 0), 0)

    // For percentage metrics, convert sums to averages
    const actualTotal = isPctMetric && actualsToDate.length > 0 ? actualSum / actualsToDate.length : actualSum
    const actualBudgetTotal = isPctMetric && actualsToDate.length > 0 ? actualBudgetSum / actualsToDate.length : actualBudgetSum
    const actualPriorTotal = isPctMetric && actualsToDate.length > 0 ? actualPriorSum / actualsToDate.length : actualPriorSum

    const forecastTotal = isPctMetric && forecastRemaining.length > 0 ? forecastSum / forecastRemaining.length : forecastSum
    const forecastBudgetTotal = isPctMetric && forecastRemaining.length > 0 ? forecastBudgetSum / forecastRemaining.length : forecastBudgetSum
    const forecastPriorTotal = isPctMetric && forecastRemaining.length > 0 ? forecastPriorSum / forecastRemaining.length : forecastPriorSum

    // OTB totals for future dates (accommodation revenue)
    const otbSum = forecastRemaining.reduce((sum, d) => sum + (d.otb_value ?? 0), 0)
    const daysWithOtb = forecastRemaining.filter(d => d.otb_value !== null).length
    // For percentage metrics, average the OTB values
    const otbTotal = isPctMetric && daysWithOtb > 0 ? otbSum / daysWithOtb : otbSum

    // For percentage metrics, projected is weighted average of actual and forecast periods
    const totalDays = actualsToDate.length + forecastRemaining.length
    const projectedTotal = isPctMetric && totalDays > 0
      ? (actualSum + forecastSum) / totalDays
      : actualTotal + forecastTotal
    const totalBudget = isPctMetric && totalDays > 0
      ? (actualBudgetSum + forecastBudgetSum) / totalDays
      : actualBudgetTotal + forecastBudgetTotal
    const totalPriorYear = isPctMetric && totalDays > 0
      ? (actualPriorSum + forecastPriorSum) / totalDays
      : actualPriorTotal + forecastPriorTotal

    const budgetVariance = projectedTotal - totalBudget
    const budgetVariancePct = totalBudget > 0 ? ((projectedTotal / totalBudget) - 1) * 100 : 0
    const priorYearVariance = projectedTotal - totalPriorYear
    const priorYearVariancePct = totalPriorYear > 0 ? ((projectedTotal / totalPriorYear) - 1) * 100 : 0

    return {
      data: combined,
      summary: {
        actual_total: actualTotal,
        actual_budget_total: actualBudgetTotal,
        actual_prior_total: actualPriorTotal,
        actual_variance: actualTotal - actualBudgetTotal,
        actual_prior_variance: actualTotal - actualPriorTotal,
        forecast_total: forecastTotal,
        forecast_budget_total: forecastBudgetTotal,
        forecast_prior_total: forecastPriorTotal,
        forecast_variance: forecastTotal - forecastBudgetTotal,
        forecast_prior_variance: forecastTotal - forecastPriorTotal,
        otb_total: otbTotal,
        days_with_otb: daysWithOtb,
        projected_total: projectedTotal,
        total_budget: totalBudget,
        total_prior_year: totalPriorYear,
        budget_variance: budgetVariance,
        budget_variance_pct: budgetVariancePct,
        prior_year_variance: priorYearVariance,
        prior_year_variance_pct: priorYearVariancePct,
        days_actual: actualsToDate.length,
        days_forecast: forecastRemaining.length,
        is_pct_metric: isPctMetric,
      }
    }
  }, [actualsData, prophetData, xgboostData, catboostData, budgetMap, isRevenueMetric])

  // Consolidate data by week or month
  const consolidatedData = useMemo(() => {
    if (!combinedData?.data || consolidation === 'daily') return null

    const groups: Record<string, {
      label: string
      actual: number
      forecast: number
      otb: number
      budget: number
      priorYear: number
      days: number
      actualDays: number
      forecastDays: number
      otbDays: number
    }> = {}

    combinedData.data.forEach(d => {
      const dateObj = new Date(d.date)
      let groupKey: string
      let groupLabel: string

      if (consolidation === 'weekly') {
        // Get ISO week: year + week number
        const jan1 = new Date(dateObj.getFullYear(), 0, 1)
        const weekNum = Math.ceil(((dateObj.getTime() - jan1.getTime()) / 86400000 + jan1.getDay() + 1) / 7)
        groupKey = `${dateObj.getFullYear()}-W${String(weekNum).padStart(2, '0')}`
        // Get Monday of this week for label
        const dayOfWeek = dateObj.getDay()
        const monday = new Date(dateObj)
        monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
        groupLabel = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })})`
      } else {
        // Monthly
        groupKey = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}`
        groupLabel = dateObj.toLocaleString('default', { month: 'short', year: 'numeric' })
      }

      if (!groups[groupKey]) {
        groups[groupKey] = {
          label: groupLabel,
          actual: 0,
          forecast: 0,
          otb: 0,
          budget: 0,
          priorYear: 0,
          days: 0,
          actualDays: 0,
          forecastDays: 0,
          otbDays: 0
        }
      }

      if (d.is_actual) {
        groups[groupKey].actual += d.actual_value ?? 0
        groups[groupKey].actualDays++
      } else {
        // For forecast days, separate OTB from pure forecast
        const otbVal = d.otb_value ?? 0
        const fcVal = d.blended_forecast ?? 0
        groups[groupKey].otb += otbVal
        // Forecast is the remainder above OTB (can't be negative)
        groups[groupKey].forecast += Math.max(0, fcVal - otbVal)
        groups[groupKey].forecastDays++
        if (otbVal > 0) groups[groupKey].otbDays++
      }
      groups[groupKey].budget += d.budget_value ?? 0
      groups[groupKey].priorYear += d.prior_year_value ?? 0
      groups[groupKey].days++
    })

    // Convert to array sorted by key
    return Object.entries(groups)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, data]) => ({
        key,
        ...data,
        total: data.actual + data.otb + data.forecast,
        variance: (data.actual + data.otb + data.forecast) - data.budget,
        variancePct: data.budget > 0 ? (((data.actual + data.otb + data.forecast) / data.budget) - 1) * 100 : 0
      }))
  }, [combinedData, consolidation])

  // Build chart data - daily view
  const dailyChartData = useMemo(() => {
    if (!combinedData?.data) return []

    // Split data into actuals and forecast
    const actualDates: string[] = []
    const actualValues: (number | null)[] = []
    const forecastDates: string[] = []
    const forecastValues: (number | null)[] = []
    const priorYearValues: (number | null)[] = []
    const budgetValues: (number | null)[] = []
    const otbDates: string[] = []
    const otbValues: (number | null)[] = []
    const allDates: string[] = []

    combinedData.data.forEach(d => {
      allDates.push(d.date)
      priorYearValues.push(d.prior_year_value)
      budgetValues.push(d.budget_value)

      if (d.is_actual) {
        actualDates.push(d.date)
        actualValues.push(d.actual_value)
      } else {
        forecastDates.push(d.date)
        forecastValues.push(d.blended_forecast)
        // Collect OTB values for future dates
        if (d.otb_value !== null && d.otb_value !== undefined) {
          otbDates.push(d.date)
          otbValues.push(d.otb_value)
        }
      }
    })

    // Calculate prior year dates for hover
    const priorDates = allDates.map(d => {
      const date = new Date(d)
      date.setDate(date.getDate() - 364)
      return formatDate(date)
    })

    const traces: any[] = [
      // Prior year fill (bottom layer)
      {
        x: allDates,
        y: priorYearValues,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year',
        fill: 'tozeroy' as const,
        fillcolor: CHART_COLORS.priorFinalFill,
        line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
        customdata: priorDates,
        hovertemplate: `Prior Year (%{customdata}): %{y:,.0f}${unit}<extra></extra>`,
      },
    ]

    // Budget line (for any metric with budget data)
    if (budgetValues.some(v => v !== null)) {
      traces.push({
        x: allDates,
        y: budgetValues,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Budget',
        line: { color: CHART_COLORS.budget, width: 2, dash: 'dash' as const },
        hovertemplate: `Budget: %{y:,.0f}${unit}<extra></extra>`,
      })
    }

    // Actuals line (solid green)
    if (actualDates.length > 0) {
      traces.push({
        x: actualDates,
        y: actualValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Actual',
        line: { color: CHART_COLORS.currentOtb, width: 3 },
        marker: { size: 8 },
        hovertemplate: `Actual: %{y:,.0f}${unit}<extra></extra>`,
      })
    }

    // Forecast line (different style)
    if (forecastDates.length > 0) {
      // Add connecting point from last actual
      const connectDates = actualDates.length > 0
        ? [actualDates[actualDates.length - 1], ...forecastDates]
        : forecastDates
      const connectValues = actualDates.length > 0
        ? [actualValues[actualValues.length - 1], ...forecastValues]
        : forecastValues

      traces.push({
        x: connectDates,
        y: connectValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Forecast',
        line: { color: CHART_COLORS.blended, width: 2, dash: 'dot' as const },
        marker: { size: 6, symbol: 'circle-open' },
        hovertemplate: `Forecast: %{y:,.0f}${unit}<extra></extra>`,
      })
    }

    // Future OTB line (accommodation revenue from bookings) - only for net_accom metric
    if (otbDates.length > 0 && OTB_METRICS.includes(metric)) {
      traces.push({
        x: otbDates,
        y: otbValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Future OTB',
        line: { color: CHART_COLORS.futureOtb, width: 2 },
        marker: { size: 6, symbol: 'diamond' },
        hovertemplate: `OTB (Booked): £%{y:,.0f}<extra></extra>`,
      })
    }

    return traces
  }, [combinedData, unit, isRevenueMetric, metric])

  // Build chart data - consolidated (weekly/monthly) view
  const consolidatedChartData = useMemo(() => {
    if (!consolidatedData) return []

    const labels = consolidatedData.map(d => d.label)
    const actuals = consolidatedData.map(d => d.actual)
    const otbs = consolidatedData.map(d => d.otb)
    const forecasts = consolidatedData.map(d => d.forecast)
    const budgets = consolidatedData.map(d => d.budget)
    const priorYears = consolidatedData.map(d => d.priorYear)

    const traces: any[] = [
      // Stacked bar: Actuals (bottom) - green
      {
        x: labels,
        y: actuals,
        type: 'bar' as const,
        name: 'Actual',
        marker: { color: CHART_COLORS.currentOtb },
        hovertemplate: `Actual: £%{y:,.0f}<extra></extra>`,
      },
      // Stacked bar: OTB (middle) - cyan - only if net_accom metric
      {
        x: labels,
        y: otbs,
        type: 'bar' as const,
        name: 'OTB (Booked)',
        marker: { color: CHART_COLORS.futureOtb },
        hovertemplate: `OTB (Booked): £%{y:,.0f}<extra></extra>`,
        visible: OTB_METRICS.includes(metric),
      },
      // Stacked bar: Forecast (top) - orange
      {
        x: labels,
        y: forecasts,
        type: 'bar' as const,
        name: 'Forecast',
        marker: { color: CHART_COLORS.blended, opacity: 0.6 },
        hovertemplate: `Forecast: £%{y:,.0f}<extra></extra>`,
      },
      // Budget line
      {
        x: labels,
        y: budgets,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Budget',
        line: { color: CHART_COLORS.budget, width: 3 },
        marker: { size: 10, symbol: 'diamond' },
        hovertemplate: `Budget: £%{y:,.0f}<extra></extra>`,
      },
      // Prior Year line
      {
        x: labels,
        y: priorYears,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Prior Year',
        line: { color: CHART_COLORS.priorFinal, width: 2, dash: 'dot' as const },
        marker: { size: 6 },
        hovertemplate: `Prior Year: £%{y:,.0f}<extra></extra>`,
      },
    ]

    return traces
  }, [consolidatedData, metric])

  // Use appropriate chart data based on consolidation
  const chartData = consolidation === 'daily' ? dailyChartData : consolidatedChartData

  const formatValue = (val: number | null | undefined, isOccupancy: boolean = false) => {
    if (val === null || val === undefined) return '-'
    if (isOccupancy) return `${val.toFixed(1)}%`
    return val.toLocaleString(undefined, { maximumFractionDigits: 0 })
  }

  const formatCurrency = (val: number) => {
    if (isRevenueMetric) {
      return `£${val.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    }
    return formatValue(val, metric === 'occupancy')
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>{title}</h2>
          <p style={styles.hint}>
            Actual results to date combined with blended forecast for remaining days
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* From Month Selector */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>From</label>
          <select
            value={selectedMonth}
            onChange={(e) => setSelectedMonth(e.target.value)}
            style={styles.select}
          >
            {monthOptions.map((month) => (
              <option key={month.value} value={month.value}>
                {month.label}
              </option>
            ))}
          </select>
        </div>

        {/* Duration Selector */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Duration</label>
          <select
            value={duration}
            onChange={(e) => setDuration(e.target.value as '1' | '3' | '6' | '12')}
            style={styles.select}
          >
            <option value="1">1 Month</option>
            <option value="3">3 Months</option>
            <option value="6">6 Months</option>
            <option value="12">1 Year</option>
          </select>
        </div>

        {/* Date Range Display (read-only) */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Period</label>
          <div style={{
            padding: `${spacing.sm} ${spacing.md}`,
            background: colors.surface,
            borderRadius: radius.md,
            fontSize: typography.sm,
            color: colors.text,
          }}>
            {startDate} to {endDate}
          </div>
        </div>

        {/* Consolidation Selector */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>View</label>
          <select
            value={consolidation}
            onChange={(e) => setConsolidation(e.target.value as 'daily' | 'weekly' | 'monthly')}
            style={styles.select}
          >
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>
      </div>

      {/* Summary Stats */}
      {combinedData?.summary && (
        <div style={styles.summaryGrid}>
          {/* Actuals to Date */}
          <div style={styles.summaryCard}>
            <span style={styles.summaryLabel}>ACTUAL TO DATE ({combinedData.summary.days_actual} days)</span>
            {(() => {
              const isPct = combinedData.summary.is_pct_metric
              const formatVal = (v: number) => isPct ? `${v.toFixed(1)}%` : formatCurrency(v)
              const actualBudgetPct = combinedData.summary.actual_budget_total > 0
                ? ((combinedData.summary.actual_total / combinedData.summary.actual_budget_total) - 1) * 100
                : 0
              const actualPriorPct = combinedData.summary.actual_prior_total > 0
                ? ((combinedData.summary.actual_total / combinedData.summary.actual_prior_total) - 1) * 100
                : 0
              const hasBudget = combinedData.summary.actual_budget_total > 0
              return (
                <>
                  <span style={{
                    ...styles.summaryValue,
                    color: hasBudget ? (combinedData.summary.actual_variance >= 0 ? colors.success : colors.error) : colors.text,
                  }}>
                    {formatVal(combinedData.summary.actual_total)}
                    {hasBudget && (
                      <span style={{ fontSize: typography.base, marginLeft: spacing.sm }}>
                        {actualBudgetPct >= 0 ? '+' : ''}{actualBudgetPct.toFixed(1)}%
                      </span>
                    )}
                  </span>
                  {hasBudget && (
                    <span style={{
                      ...styles.summarySubtext,
                      color: combinedData.summary.actual_variance >= 0 ? colors.success : colors.error,
                    }}>
                      vs Budget: {formatVal(combinedData.summary.actual_budget_total)}
                      {' '}({combinedData.summary.actual_variance >= 0 ? '+' : ''}{formatVal(combinedData.summary.actual_variance)})
                    </span>
                  )}
                  {!hasBudget && (
                    <span style={styles.summarySubtext}>vs Budget: N/A</span>
                  )}
                  <span style={{
                    ...styles.summarySubtext,
                    color: actualPriorPct >= 0 ? colors.success : colors.error,
                  }}>
                    vs Last Year: {formatVal(combinedData.summary.actual_prior_total)}
                    {' '}({actualPriorPct >= 0 ? '+' : ''}{actualPriorPct.toFixed(1)}%)
                  </span>
                </>
              )
            })()}
          </div>

          {/* Pace vs Budget - Actual + OTB (only for OTB metrics) */}
          {OTB_METRICS.includes(metric) && (
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>PACE VS BUDGET</span>
              {(() => {
                const isPct = combinedData.summary.is_pct_metric
                const formatVal = (v: number) => isPct ? `${v.toFixed(1)}%` : formatCurrency(v)
                // For percentage metrics, calculate weighted average of actual and OTB
                // For count/revenue metrics, sum them
                const paceTotal = isPct
                  ? ((combinedData.summary.actual_total * combinedData.summary.days_actual) +
                     (combinedData.summary.otb_total * combinedData.summary.days_with_otb)) /
                    (combinedData.summary.days_actual + combinedData.summary.days_with_otb)
                  : combinedData.summary.actual_total + combinedData.summary.otb_total
                const hasBudget = combinedData.summary.total_budget > 0
                const paceOfBudgetPct = hasBudget
                  ? (paceTotal / combinedData.summary.total_budget) * 100
                  : 0
                const pacePriorPct = combinedData.summary.total_prior_year > 0
                  ? ((paceTotal / combinedData.summary.total_prior_year) - 1) * 100
                  : 0
                return (
                  <>
                    <span style={{ ...styles.summaryValue, color: CHART_COLORS.futureOtb }}>
                      {formatVal(paceTotal)}
                      {hasBudget && (
                        <span style={{ fontSize: typography.base, marginLeft: spacing.sm }}>
                          {paceOfBudgetPct.toFixed(1)}%
                        </span>
                      )}
                    </span>
                    {hasBudget ? (
                      <span style={styles.summarySubtext}>
                        of {formatVal(combinedData.summary.total_budget)} budget
                      </span>
                    ) : (
                      <span style={styles.summarySubtext}>vs Budget: N/A</span>
                    )}
                    <span style={{
                      ...styles.summarySubtext,
                      color: pacePriorPct >= 0 ? colors.success : colors.error,
                    }}>
                      vs Last Year: {formatVal(combinedData.summary.total_prior_year)}
                      {' '}({pacePriorPct >= 0 ? '+' : ''}{pacePriorPct.toFixed(1)}%)
                    </span>
                  </>
                )
              })()}
            </div>
          )}

          {/* Forecast Remaining */}
          <div style={styles.summaryCard}>
            <span style={styles.summaryLabel}>FORECAST REMAINING ({combinedData.summary.days_forecast} days)</span>
            {(() => {
              const isPct = combinedData.summary.is_pct_metric
              const formatVal = (v: number) => isPct ? `${v.toFixed(1)}%` : formatCurrency(v)
              const hasBudget = combinedData.summary.forecast_budget_total > 0
              const forecastBudgetPct = hasBudget
                ? ((combinedData.summary.forecast_total / combinedData.summary.forecast_budget_total) - 1) * 100
                : 0
              const forecastPriorPct = combinedData.summary.forecast_prior_total > 0
                ? ((combinedData.summary.forecast_total / combinedData.summary.forecast_prior_total) - 1) * 100
                : 0
              return (
                <>
                  <span style={{ ...styles.summaryValue, color: CHART_COLORS.blended }}>
                    {formatVal(combinedData.summary.forecast_total)}
                    {hasBudget && (
                      <span style={{ fontSize: typography.base, marginLeft: spacing.sm, color: forecastBudgetPct >= 0 ? colors.success : colors.error }}>
                        {forecastBudgetPct >= 0 ? '+' : ''}{forecastBudgetPct.toFixed(1)}%
                      </span>
                    )}
                  </span>
                  {hasBudget ? (
                    <span style={{
                      ...styles.summarySubtext,
                      color: combinedData.summary.forecast_variance >= 0 ? colors.success : colors.error,
                    }}>
                      vs Budget: {formatVal(combinedData.summary.forecast_budget_total)}
                      {' '}({combinedData.summary.forecast_variance >= 0 ? '+' : ''}{formatVal(combinedData.summary.forecast_variance)})
                    </span>
                  ) : (
                    <span style={styles.summarySubtext}>vs Budget: N/A</span>
                  )}
                  <span style={{
                    ...styles.summarySubtext,
                    color: forecastPriorPct >= 0 ? colors.success : colors.error,
                  }}>
                    vs Last Year: {formatVal(combinedData.summary.forecast_prior_total)}
                    {' '}({forecastPriorPct >= 0 ? '+' : ''}{forecastPriorPct.toFixed(1)}%)
                  </span>
                </>
              )
            })()}
          </div>

          {/* Projected Total */}
          <div style={styles.summaryCard}>
            <span style={styles.summaryLabel}>PROJECTED TOTAL</span>
            {(() => {
              const isPct = combinedData.summary.is_pct_metric
              const formatVal = (v: number) => isPct ? `${v.toFixed(1)}%` : formatCurrency(v)
              const hasBudget = combinedData.summary.total_budget > 0
              return (
                <>
                  <span style={{
                    ...styles.summaryValue,
                    color: hasBudget ? (combinedData.summary.budget_variance >= 0 ? colors.success : colors.error) : colors.text,
                  }}>
                    {formatVal(combinedData.summary.projected_total)}
                    {hasBudget && (
                      <span style={{ fontSize: typography.base, marginLeft: spacing.sm }}>
                        {combinedData.summary.budget_variance >= 0 ? '+' : ''}{combinedData.summary.budget_variance_pct.toFixed(1)}%
                      </span>
                    )}
                  </span>
                  {hasBudget ? (
                    <span style={{
                      ...styles.summarySubtext,
                      color: combinedData.summary.budget_variance >= 0 ? colors.success : colors.error,
                    }}>
                      vs Budget: {formatVal(combinedData.summary.total_budget)}
                      {' '}({combinedData.summary.budget_variance >= 0 ? '+' : ''}{formatVal(combinedData.summary.budget_variance)})
                    </span>
                  ) : (
                    <span style={styles.summarySubtext}>vs Budget: N/A</span>
                  )}
                  <span style={{
                    ...styles.summarySubtext,
                    color: combinedData.summary.prior_year_variance >= 0 ? colors.success : colors.error,
                  }}>
                    vs Last Year: {formatVal(combinedData.summary.total_prior_year)}
                    {' '}({combinedData.summary.prior_year_variance >= 0 ? '+' : ''}{combinedData.summary.prior_year_variance_pct.toFixed(1)}%)
                  </span>
                </>
              )
            })()}
          </div>
        </div>
      )}

      {/* Chart */}
      {isLoading ? (
        <div style={styles.loadingContainer}>Loading forecast data...</div>
      ) : combinedData?.data && combinedData.data.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={chartData}
            layout={{
              height: 400,
              margin: { l: 60, r: 30, t: 30, b: consolidation === 'daily' ? 50 : 80 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              barmode: consolidation === 'daily' ? undefined : 'stack' as const,
              xaxis: {
                title: { text: consolidation === 'daily' ? 'Date' : (consolidation === 'weekly' ? 'Week' : 'Month') },
                tickangle: -45,
                tickfont: { size: 10 },
                gridcolor: colors.border,
                zerolinecolor: colors.border,
              },
              yaxis: {
                title: { text: metricLabel },
                rangemode: 'tozero' as const,
                gridcolor: colors.border,
                zerolinecolor: colors.border,
                tickformat: isRevenueMetric ? ',.0f' : undefined,
              },
              legend: {
                orientation: 'h' as const,
                y: -0.25,
                x: 0.5,
                xanchor: 'center' as const,
              },
              hovermode: 'x unified' as const,
              shapes: (() => {
                const todayStr = formatDate(new Date())
                const todayInRange = consolidation === 'daily' && todayStr >= startDate && todayStr <= endDate
                return todayInRange ? [{
                  type: 'line',
                  x0: todayStr,
                  x1: todayStr,
                  y0: 0,
                  y1: 1,
                  yref: 'paper',
                  line: { color: colors.textSecondary, width: 1, dash: 'dot' },
                }] : []
              })(),
              annotations: (() => {
                const todayStr = formatDate(new Date())
                const todayInRange = consolidation === 'daily' && todayStr >= startDate && todayStr <= endDate
                return todayInRange ? [{
                  x: todayStr,
                  y: 1,
                  yref: 'paper',
                  text: 'Today',
                  showarrow: false,
                  font: { size: 10, color: colors.textSecondary },
                  yanchor: 'bottom',
                }] : []
              })(),
            }}
            style={{ width: '100%', height: '100%' }}
            config={{ responsive: true, displayModeBar: false }}
          />
        </div>
      ) : null}

      {/* Consolidated Breakdown Table */}
      {consolidation !== 'daily' && consolidatedData && consolidatedData.length > 0 && (
        <div style={{ marginTop: spacing.lg, overflowX: 'auto' }}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>{consolidation === 'weekly' ? 'Week' : 'Month'}</th>
                <th style={{ ...styles.th, textAlign: 'right' }}>Actual</th>
                {OTB_METRICS.includes(metric) && <th style={{ ...styles.th, textAlign: 'right' }}>OTB</th>}
                <th style={{ ...styles.th, textAlign: 'right' }}>Forecast</th>
                <th style={{ ...styles.th, textAlign: 'right' }}>Total</th>
                <th style={{ ...styles.th, textAlign: 'right' }}>Budget</th>
                <th style={{ ...styles.th, textAlign: 'right' }}>Variance</th>
                <th style={{ ...styles.th, textAlign: 'right' }}>%</th>
                <th style={{ ...styles.th, textAlign: 'right' }}>Prior Yr</th>
              </tr>
            </thead>
            <tbody>
              {consolidatedData.map((row) => (
                <tr key={row.key}>
                  <td style={styles.td}>{row.label}</td>
                  <td style={{ ...styles.td, textAlign: 'right' }}>
                    {row.actual > 0 ? formatCurrency(row.actual) : '-'}
                  </td>
                  {OTB_METRICS.includes(metric) && (
                    <td style={{ ...styles.td, textAlign: 'right', color: CHART_COLORS.futureOtb }}>
                      {row.otb > 0 ? formatCurrency(row.otb) : '-'}
                    </td>
                  )}
                  <td style={{ ...styles.td, textAlign: 'right', color: CHART_COLORS.blended }}>
                    {row.forecast > 0 ? formatCurrency(row.forecast) : '-'}
                  </td>
                  <td style={{ ...styles.td, textAlign: 'right', fontWeight: typography.semibold }}>
                    {formatCurrency(row.total)}
                  </td>
                  <td style={{ ...styles.td, textAlign: 'right' }}>
                    {formatCurrency(row.budget)}
                  </td>
                  <td style={{
                    ...styles.td,
                    textAlign: 'right',
                    color: row.variance >= 0 ? colors.success : colors.error
                  }}>
                    {row.variance >= 0 ? '+' : ''}{formatCurrency(row.variance)}
                  </td>
                  <td style={{
                    ...styles.td,
                    textAlign: 'right',
                    color: row.variancePct >= 0 ? colors.success : colors.error
                  }}>
                    {row.variancePct >= 0 ? '+' : ''}{row.variancePct.toFixed(1)}%
                  </td>
                  <td style={{ ...styles.td, textAlign: 'right', color: colors.textSecondary }}>
                    {formatCurrency(row.priorYear)}
                  </td>
                </tr>
              ))}
              {/* Totals row */}
              <tr style={{ background: colors.surface, fontWeight: typography.bold }}>
                <td style={styles.td}>TOTAL</td>
                <td style={{ ...styles.td, textAlign: 'right' }}>
                  {formatCurrency(consolidatedData.reduce((sum, r) => sum + r.actual, 0))}
                </td>
                {OTB_METRICS.includes(metric) && (
                  <td style={{ ...styles.td, textAlign: 'right', color: CHART_COLORS.futureOtb }}>
                    {formatCurrency(consolidatedData.reduce((sum, r) => sum + r.otb, 0))}
                  </td>
                )}
                <td style={{ ...styles.td, textAlign: 'right', color: CHART_COLORS.blended }}>
                  {formatCurrency(consolidatedData.reduce((sum, r) => sum + r.forecast, 0))}
                </td>
                <td style={{ ...styles.td, textAlign: 'right' }}>
                  {formatCurrency(consolidatedData.reduce((sum, r) => sum + r.total, 0))}
                </td>
                <td style={{ ...styles.td, textAlign: 'right' }}>
                  {formatCurrency(consolidatedData.reduce((sum, r) => sum + r.budget, 0))}
                </td>
                <td style={{
                  ...styles.td,
                  textAlign: 'right',
                  color: consolidatedData.reduce((sum, r) => sum + r.variance, 0) >= 0 ? colors.success : colors.error
                }}>
                  {consolidatedData.reduce((sum, r) => sum + r.variance, 0) >= 0 ? '+' : ''}
                  {formatCurrency(consolidatedData.reduce((sum, r) => sum + r.variance, 0))}
                </td>
                <td style={{
                  ...styles.td,
                  textAlign: 'right',
                  color: combinedData?.summary?.budget_variance_pct && combinedData.summary.budget_variance_pct >= 0 ? colors.success : colors.error
                }}>
                  {combinedData?.summary?.budget_variance_pct && combinedData.summary.budget_variance_pct >= 0 ? '+' : ''}
                  {combinedData?.summary?.budget_variance_pct?.toFixed(1)}%
                </td>
                <td style={{ ...styles.td, textAlign: 'right', color: colors.textSecondary }}>
                  {formatCurrency(consolidatedData.reduce((sum, r) => sum + r.priorYear, 0))}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Data Table Toggle */}
      {combinedData?.data && combinedData.data.length > 0 && (
        <>
          <button
            onClick={() => setShowTable(!showTable)}
            style={styles.toggleButton}
          >
            {showTable ? 'Hide Data Table' : 'Show Data Table'}
          </button>

          {showTable && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>DOW</th>
                    <th style={styles.th}>Actual/FC</th>
                    {OTB_METRICS.includes(metric) && <th style={styles.th}>OTB</th>}
                    <th style={styles.th}>Budget</th>
                    <th style={styles.th}>Prior Year</th>
                    <th style={styles.th}>Type</th>
                  </tr>
                </thead>
                <tbody>
                  {combinedData.data.map((row) => (
                    <tr key={row.date} style={{ background: row.is_actual ? 'rgba(16, 185, 129, 0.05)' : 'transparent' }}>
                      <td style={styles.td}>{row.date}</td>
                      <td style={styles.td}>{row.day_of_week}</td>
                      <td style={{
                        ...styles.td,
                        fontWeight: 600,
                        color: row.is_actual ? CHART_COLORS.currentOtb : CHART_COLORS.blended,
                      }}>
                        {formatValue(row.display_value, metric === 'occupancy')}
                      </td>
                      {OTB_METRICS.includes(metric) && (
                        <td style={{ ...styles.td, color: CHART_COLORS.futureOtb }}>
                          {row.otb_value !== null && row.otb_value !== undefined
                            ? formatValue(row.otb_value, false)
                            : '-'}
                        </td>
                      )}
                      <td style={{ ...styles.td, color: CHART_COLORS.budget }}>
                        {formatValue(row.budget_value, metric === 'occupancy')}
                      </td>
                      <td style={styles.td}>
                        {formatValue(row.prior_year_value, metric === 'occupancy')}
                      </td>
                      <td style={{
                        ...styles.td,
                        fontSize: typography.xs,
                        color: row.is_actual ? colors.success : colors.textSecondary,
                      }}>
                        {row.is_actual ? 'Actual' : 'Forecast'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const ForecastPreview: React.FC = () => {
  const token = localStorage.getItem('token')
  const paceCurveRef = useRef<HTMLDivElement>(null)

  // Default to next 30 days
  const today = new Date()
  const defaultStart = new Date(today)
  defaultStart.setDate(today.getDate() + 1)
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() + 30)

  const [startDate, setStartDate] = useState(defaultStart.toISOString().split('T')[0])
  const [endDate, setEndDate] = useState(defaultEnd.toISOString().split('T')[0])
  const [metric, setMetric] = useState<MetricType>('rooms')
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  const [showTable, setShowTable] = useState(true)

  // Generate month options
  const monthOptions = useMemo(() => getNext12Months(), [])

  // Quick select handlers
  const handleQuickSelect = (days: number) => {
    const start = new Date()
    start.setDate(start.getDate() + 1)
    const end = new Date()
    end.setDate(end.getDate() + days)
    setStartDate(start.toISOString().split('T')[0])
    setEndDate(end.toISOString().split('T')[0])
  }

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  // Fetch preview data
  const { data: previewData, isLoading: previewLoading } = useQuery<PreviewResponse>({
    queryKey: ['forecast-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        metric: metric,
      })
      const response = await fetch(`/api/forecast/preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch preview data')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch pace curve when a date is selected
  const { data: paceCurveData, isLoading: paceCurveLoading } = useQuery<PaceCurveResponse>({
    queryKey: ['pace-curve', selectedDate],
    queryFn: async () => {
      const params = new URLSearchParams({ arrival_date: selectedDate! })
      const response = await fetch(`/api/forecast/pace-curve?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch pace curve')
      return response.json()
    },
    enabled: !!token && !!selectedDate,
  })

  // Fetch budget data for revenue metrics
  const budgetData = useBudgetData(startDate, endDate, metric, token)

  // Build forecast chart data
  const forecastChartData = useMemo(() => {
    if (!previewData?.data) return []

    const dates = previewData.data.map((d) => d.date)
    const currentOtb = previewData.data.map((d) => d.current_otb)
    const priorYearOtb = previewData.data.map((d) => d.prior_year_otb)
    const priorYearFinal = previewData.data.map((d) => d.prior_year_final)
    const forecast = previewData.data.map((d) => d.forecast)

    // Calculate prior year dates (364 days for DOW alignment)
    const priorDates = previewData.data.map((d) => {
      const date = new Date(d.date)
      date.setDate(date.getDate() - 364)
      return date.toISOString().split('T')[0]
    })

    const unit = {
    occupancy: '%',
    rooms: ' rooms',
    guests: ' guests',
    ave_guest_rate: '',
    arr: '',
    net_accom: '',
    net_dry: '',
    net_wet: '',
    total_rev: '',
  }[metric] || ''

    return [
      {
        x: dates,
        y: priorYearFinal,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year Final',
        line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
        fill: 'tozeroy' as const,
        fillcolor: CHART_COLORS.priorFinalFill,
        customdata: priorDates,
        hovertemplate: `Prior Final: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
      },
      {
        x: dates,
        y: priorYearOtb,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year OTB',
        line: { color: CHART_COLORS.priorOtb, width: 2, dash: 'dash' as const },
        customdata: priorDates,
        hovertemplate: `Prior OTB: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
      },
      {
        x: dates,
        y: currentOtb,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Current OTB',
        line: { color: CHART_COLORS.currentOtb, width: 2 },
        marker: { size: 6 },
        hovertemplate: `Current OTB: %{y:.1f}${unit}<extra></extra>`,
      },
      {
        x: dates,
        y: forecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Pickup Forecast',
        line: { color: CHART_COLORS.pickup, width: 3 },
        marker: { size: 8 },
        hovertemplate: `Pickup: %{y:.1f}${unit}<extra></extra>`,
      },
    ].concat(buildBudgetTrace(budgetData) ? [buildBudgetTrace(budgetData)!] : [])
  }, [previewData, metric, budgetData])

  // Build pace curve chart data with calculated axis ranges
  const { paceCurveChartData, paceCurveXRange, paceCurveYMax } = useMemo(() => {
    if (!paceCurveData) return { paceCurveChartData: [], paceCurveXRange: null, paceCurveYMax: null }

    // Filter to only show data points with values
    const currentFiltered = paceCurveData.current_year.filter((p) => p.rooms !== null && p.rooms > 0)
    const priorFiltered = paceCurveData.prior_year.filter((p) => p.rooms !== null && p.rooms > 0)

    // Calculate x-axis range: from earliest data point to 0 (arrival)
    // Find max days_out with actual booking data
    const currentMaxDaysOut = currentFiltered.length > 0
      ? Math.max(...currentFiltered.map((p) => p.days_out))
      : 0
    const priorMaxDaysOut = priorFiltered.length > 0
      ? Math.max(...priorFiltered.map((p) => p.days_out))
      : 0
    const maxDaysOut = Math.max(currentMaxDaysOut, priorMaxDaysOut, 30) // At least 30 days

    // Calculate y-axis max for proper scaling
    const currentMaxRooms = currentFiltered.length > 0
      ? Math.max(...currentFiltered.map((p) => p.rooms as number))
      : 0
    const priorMaxRooms = priorFiltered.length > 0
      ? Math.max(...priorFiltered.map((p) => p.rooms as number))
      : 0
    const maxRooms = Math.max(currentMaxRooms, priorMaxRooms)

    // Include all points (even zeros) for smoother lines, but filter nulls
    const currentAllPoints = paceCurveData.current_year.filter((p) => p.rooms !== null && p.days_out <= maxDaysOut)
    const priorAllPoints = paceCurveData.prior_year.filter((p) => p.rooms !== null && p.days_out <= maxDaysOut)

    const chartData = [
      {
        x: priorAllPoints.map((p) => p.days_out),
        y: priorAllPoints.map((p) => p.rooms),
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: `Prior Year (${paceCurveData.day_of_week})`,
        line: { color: '#9ca3af', width: 2 },
        marker: { size: 4 },
      },
      {
        x: currentAllPoints.map((p) => p.days_out),
        y: currentAllPoints.map((p) => p.rooms),
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: `Current Year (${paceCurveData.day_of_week})`,
        line: { color: colors.accent, width: 2 },
        marker: { size: 6 },
      },
    ]

    return {
      paceCurveChartData: chartData,
      paceCurveXRange: [maxDaysOut + 5, -2] as [number, number], // Add padding, reversed for days-out
      paceCurveYMax: maxRooms * 1.1 // 10% padding above max
    }
  }, [paceCurveData])

  const metricLabel = {
    occupancy: 'Occupancy %',
    rooms: 'Room Nights',
    guests: 'Guests',
    ave_guest_rate: 'Ave Guest Rate',
    arr: 'ARR',
    net_accom: 'Net Accomm Rev',
    net_dry: 'Net Dry Rev',
    net_wet: 'Net Wet Rev',
    total_rev: 'Total Net Rev',
  }[metric] || 'Value'

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Live Pickup</h2>
          <p style={styles.hint}>
            Forecast = Current OTB + (Prior Year Final - Prior Year OTB)
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* Date Range */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Date Range</label>
          <div style={styles.dateInputs}>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.dateInput}
            />
            <span style={styles.dateSeparator}>to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.dateInput}
            />
          </div>
        </div>

        {/* Metric Dropdown - Pickup only supports pace-based metrics */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as MetricType)}
            style={styles.select}
          >
            <option value="occupancy">Occupancy %</option>
            <option value="rooms">Room Nights</option>
            <option value="guests">Guests</option>
            <option value="ave_guest_rate">Ave Guest Rate</option>
            <option value="arr">ARR (Net)</option>
            <option value="net_accom">Net Accomm Rev</option>
            <option value="net_dry">Net Dry Rev</option>
            <option value="net_wet">Net Wet Rev</option>
            <option value="total_rev">Total Net Rev</option>
          </select>
        </div>

        {/* Quick Selects */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Quick Select</label>
          <div style={styles.quickSelectGroup}>
            {[7, 14, 30, 60, 90].map((days) => (
              <button
                key={days}
                onClick={() => handleQuickSelect(days)}
                style={styles.quickSelectButton}
              >
                {days}d
              </button>
            ))}
          </div>
          <select
            onChange={(e) => handleMonthSelect(e.target.value)}
            style={{ ...styles.monthSelect, marginTop: spacing.xs }}
            defaultValue=""
          >
            <option value="" disabled>Month...</option>
            {monthOptions.map((month, idx) => (
              <option key={month.label} value={idx}>
                {month.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Stats */}
      {previewData?.summary && (() => {
        // Backend already returns averages for occupancy, totals for rooms
        const otbAvg = previewData.summary.otb_total
        const priorOtbAvg = previewData.summary.prior_otb_total
        const forecastAvg = previewData.summary.forecast_total
        const priorFinalAvg = previewData.summary.prior_final_total
        const otbDiff = otbAvg - priorOtbAvg
        const forecastDiff = forecastAvg - priorFinalAvg

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>CURRENT OTB</span>
              <span style={styles.summaryValue}>
                {metric === 'occupancy' ? `${otbAvg.toFixed(1)}%` : otbAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: otbDiff >= 0 ? colors.success : colors.error,
              }}>
                vs Prior OTB: {metric === 'occupancy' ? `${priorOtbAvg.toFixed(1)}%` : priorOtbAvg.toFixed(0)}
                {' '}({otbDiff >= 0 ? '+' : ''}{metric === 'occupancy' ? `${otbDiff.toFixed(1)}%` : otbDiff.toFixed(0)})
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>PICKUP FORECAST</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.pickup }}>
                {metric === 'occupancy' ? `${forecastAvg.toFixed(1)}%` : forecastAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: forecastDiff >= 0 ? colors.success : colors.error,
              }}>
                vs Prior Final: {metric === 'occupancy' ? `${priorFinalAvg.toFixed(1)}%` : priorFinalAvg.toFixed(0)}
                {' '}({forecastDiff >= 0 ? '+' : ''}{metric === 'occupancy' ? `${forecastDiff.toFixed(1)}%` : forecastDiff.toFixed(0)})
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>PACE VS PRIOR</span>
              <span
                style={{
                  ...styles.summaryValue,
                  color:
                    previewData.summary.pace_pct !== null
                      ? previewData.summary.pace_pct >= 0
                        ? colors.success
                        : colors.error
                      : colors.textSecondary,
                }}
              >
                {previewData.summary.pace_pct !== null
                  ? `${previewData.summary.pace_pct >= 0 ? '+' : ''}${previewData.summary.pace_pct.toFixed(1)}%`
                  : 'N/A'}
              </span>
              <span style={styles.summarySubtext}>OTB vs same DOW last year</span>
            </div>
          </div>
        )
      })()}

      {/* Forecast Chart */}
      {previewLoading ? (
        <div style={styles.loadingContainer}>Loading forecast data...</div>
      ) : previewData?.data && previewData.data.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={forecastChartData}
            layout={{
              height: 350,
              margin: { l: 50, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              xaxis: {
                showgrid: true,
                gridcolor: colors.border,
                tickangle: -45,
                hoverformat: '%a %d/%m/%y',
              },
              yaxis: {
                showgrid: true,
                gridcolor: colors.border,
                title: { text: metricLabel },
              },
              legend: {
                orientation: 'h',
                y: -0.2,
                x: 0.5,
                xanchor: 'center',
              },
              hovermode: 'x unified',
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%' }}
          />
        </div>
      ) : (
        <div style={styles.emptyContainer}>
          No snapshot data available for this date range. Run the pickup snapshot job first.
        </div>
      )}

      {/* Data Table */}
      {previewData?.data && previewData.data.length > 0 && (
        <>
          <button onClick={() => setShowTable(!showTable)} style={styles.tableToggle}>
            {showTable ? 'Hide' : 'Show'} Data Table
          </button>

          {showTable && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>DOW</th>
                    <th style={styles.th}>Lead</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Current OTB</th>
                    <th style={styles.th}>Prior Yr Date</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr Final</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Pickup</th>
                    <th style={{ ...styles.th, ...styles.thRight, fontWeight: typography.bold }}>
                      Forecast
                    </th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Pace</th>
                    <th style={styles.th}></th>
                  </tr>
                </thead>
                <tbody>
                  {previewData.data.map((row, idx) => (
                    <tr
                      key={row.date}
                      style={{
                        ...styles.tr,
                        backgroundColor:
                          selectedDate === row.date
                            ? colors.accent + '20'
                            : idx % 2 === 0
                              ? colors.surface
                              : colors.background,
                      }}
                    >
                      <td style={styles.td}>{row.date}</td>
                      <td style={styles.td}>{row.day_of_week}</td>
                      <td style={styles.td}>{row.lead_days}d</td>
                      <td style={{ ...styles.td, ...styles.tdRight }}>
                        {row.current_otb !== null ? row.current_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{
                        ...styles.td,
                        color: row.day_of_week === row.prior_year_dow ? colors.textSecondary : colors.error,
                        fontSize: typography.xs,
                      }}>
                        {row.prior_year_date} ({row.prior_year_dow})
                        {row.day_of_week !== row.prior_year_dow && ' ⚠️'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.prior_year_otb !== null ? row.prior_year_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.prior_year_final !== null ? row.prior_year_final.toFixed(1) : '-'}
                      </td>
                      <td
                        style={{
                          ...styles.td,
                          ...styles.tdRight,
                          color:
                            row.expected_pickup !== null
                              ? row.expected_pickup >= 0
                                ? colors.success
                                : colors.error
                              : colors.textMuted,
                        }}
                      >
                        {row.expected_pickup !== null
                          ? `${row.expected_pickup >= 0 ? '+' : ''}${row.expected_pickup.toFixed(1)}`
                          : '-'}
                      </td>
                      <td
                        style={{
                          ...styles.td,
                          ...styles.tdRight,
                          fontWeight: typography.semibold,
                          color: CHART_COLORS.pickup,
                        }}
                      >
                        {row.forecast !== null ? row.forecast.toFixed(1) : '-'}
                      </td>
                      <td
                        style={{
                          ...styles.td,
                          ...styles.tdRight,
                          color:
                            row.pace_vs_prior_pct !== null
                              ? row.pace_vs_prior_pct >= 0
                                ? colors.success
                                : colors.error
                              : colors.textMuted,
                        }}
                      >
                        {row.pace_vs_prior_pct !== null
                          ? `${row.pace_vs_prior_pct >= 0 ? '+' : ''}${row.pace_vs_prior_pct.toFixed(0)}%`
                          : '-'}
                      </td>
                      <td style={styles.td}>
                        <button
                          onClick={() => {
                            const newDate = selectedDate === row.date ? null : row.date
                            setSelectedDate(newDate)
                            if (newDate) {
                              setTimeout(() => {
                                paceCurveRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                              }, 100)
                            }
                          }}
                          style={styles.paceButton}
                        >
                          {selectedDate === row.date ? 'Hide' : 'Pace'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}

      {/* Pace Curve Chart */}
      {selectedDate && (
        <div ref={paceCurveRef} style={styles.paceCurveSection}>
          <h3 style={styles.paceCurveTitle}>
            Booking Pace Curve: {selectedDate} ({paceCurveData?.day_of_week})
          </h3>
          <p style={styles.hint}>
            Shows how bookings built up over time from 365 days out to arrival
          </p>

          {paceCurveLoading ? (
            <div style={styles.loadingContainer}>Loading pace curve...</div>
          ) : paceCurveData ? (
            <div style={styles.chartContainer}>
              <Plot
                data={paceCurveChartData}
                layout={{
                  height: 300,
                  margin: { l: 50, r: 30, t: 20, b: 50 },
                  paper_bgcolor: 'transparent',
                  plot_bgcolor: 'transparent',
                  font: { family: typography.fontFamily, color: colors.text },
                  xaxis: {
                    showgrid: true,
                    gridcolor: colors.border,
                    title: { text: 'Days Before Arrival' },
                    range: paceCurveXRange || undefined, // Dynamic range from first booking to arrival
                    hoverformat: '%a %d/%m/%y',
                  },
                  yaxis: {
                    showgrid: true,
                    gridcolor: colors.border,
                    title: { text: 'Rooms Booked' },
                    range: [0, paceCurveYMax || undefined], // Start at 0, dynamic max with padding
                    autorange: paceCurveYMax ? false : true,
                  },
                  legend: {
                    orientation: 'h',
                    y: -0.25,
                    x: 0.5,
                    xanchor: 'center',
                  },
                  hovermode: 'x unified',
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
          ) : (
            <div style={styles.emptyContainer}>No pace data available for this date.</div>
          )}
        </div>
      )}
    </div>
  )
}

const ProphetPreview: React.FC = () => {
  const token = localStorage.getItem('token')

  // Default to next 30 days, rooms metric (matching pickup page)
  const today = new Date()
  const defaultStart = new Date(today)
  defaultStart.setDate(today.getDate() + 1)
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() + 30)

  const [startDate, setStartDate] = useState(defaultStart.toISOString().split('T')[0])
  const [endDate, setEndDate] = useState(defaultEnd.toISOString().split('T')[0])
  const [metric, setMetric] = useState<MetricType>('rooms')
  const [showTable, setShowTable] = useState(false)

  // Generate month options
  const monthOptions = useMemo(() => getNext12Months(), [])

  // Quick select handlers
  const handleQuickSelect = (days: number) => {
    const start = new Date()
    start.setDate(start.getDate() + 1)
    const end = new Date()
    end.setDate(end.getDate() + days)
    setStartDate(start.toISOString().split('T')[0])
    setEndDate(end.toISOString().split('T')[0])
  }

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  // Fetch Prophet data
  const { data: prophetData, isLoading: prophetLoading } = useQuery<ProphetResponse>({
    queryKey: ['prophet-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        metric: metric,
      })
      const response = await fetch(`/api/forecast/prophet-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch Prophet forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch budget data for revenue metrics
  const budgetData = useBudgetData(startDate, endDate, metric, token)

  // Build Prophet chart data
  const prophetChartData = useMemo(() => {
    if (!prophetData?.data) return []

    const dates = prophetData.data.map((d) => d.date)
    const currentOtb = prophetData.data.map((d) => d.current_otb)
    const priorYearOtb = prophetData.data.map((d) => d.prior_year_otb)
    const forecast = prophetData.data.map((d) => d.forecast)
    const forecastLower = prophetData.data.map((d) => d.forecast_lower)
    const forecastUpper = prophetData.data.map((d) => d.forecast_upper)
    const priorYearFinal = prophetData.data.map((d) => d.prior_year_final)

    // Calculate prior year dates
    const priorDates = prophetData.data.map((d) => {
      const date = new Date(d.date)
      date.setDate(date.getDate() - 364)
      return date.toISOString().split('T')[0]
    })

    const unit = {
    occupancy: '%',
    rooms: ' rooms',
    guests: ' guests',
    ave_guest_rate: '',
    arr: '',
    net_accom: '',
    net_dry: '',
    net_wet: '',
    total_rev: '',
  }[metric] || ''

    return [
      // Confidence interval fill - light blue
      {
        x: [...dates, ...dates.slice().reverse()],
        y: [...forecastUpper, ...forecastLower.slice().reverse()],
        fill: 'toself' as const,
        fillcolor: CHART_COLORS.prophetConfidence,
        line: { color: 'transparent' },
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: '80% Confidence',
        showlegend: true,
        hoverinfo: 'skip' as const,
      },
      {
        x: dates,
        y: priorYearFinal,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year Final',
        line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
        fill: 'tozeroy' as const,
        fillcolor: CHART_COLORS.priorFinalFill,
        customdata: priorDates,
        hovertemplate: `Prior Final: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
      },
      {
        x: dates,
        y: priorYearOtb,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year OTB',
        line: { color: CHART_COLORS.priorOtb, width: 2, dash: 'dash' as const },
        customdata: priorDates,
        hovertemplate: `Prior OTB: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
      },
      {
        x: dates,
        y: currentOtb,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Current OTB',
        line: { color: CHART_COLORS.currentOtb, width: 2 },
        marker: { size: 6 },
        hovertemplate: `Current OTB: %{y:.1f}${unit}<extra></extra>`,
      },
      {
        x: dates,
        y: forecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Prophet Forecast',
        line: { color: CHART_COLORS.prophet, width: 3 },
        marker: { size: 8 },
        hovertemplate: `Prophet: %{y:.1f}${unit}<extra></extra>`,
      },
    ].concat(buildBudgetTrace(budgetData) ? [buildBudgetTrace(budgetData)!] : [])
  }, [prophetData, metric, budgetData])

  const metricLabel = {
    occupancy: 'Occupancy %',
    rooms: 'Room Nights',
    guests: 'Guests',
    ave_guest_rate: 'Ave Guest Rate',
    arr: 'ARR',
    net_accom: 'Net Accomm Rev',
    net_dry: 'Net Dry Rev',
    net_wet: 'Net Wet Rev',
    total_rev: 'Total Net Rev',
  }[metric] || 'Value'

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Live Prophet</h2>
          <p style={styles.hint}>
            Time series forecast using Facebook Prophet with weekly/yearly seasonality
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* Date Range */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Date Range</label>
          <div style={styles.dateInputs}>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.dateInput}
            />
            <span style={styles.dateSeparator}>to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.dateInput}
            />
          </div>
        </div>

        {/* Metric Dropdown */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as MetricType)}
            style={styles.select}
          >
            <option value="occupancy">Occupancy %</option>
            <option value="rooms">Room Nights</option>
            <option value="guests">Guests</option>
            <option value="ave_guest_rate">Ave Guest Rate</option>
            <option value="arr">ARR (Net)</option>
            <option value="net_accom">Net Accomm Rev</option>
            <option value="net_dry">Net Dry Rev</option>
            <option value="net_wet">Net Wet Rev</option>
            <option value="total_rev">Total Net Rev</option>
          </select>
        </div>

        {/* Quick Selects */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Quick Select</label>
          <div style={styles.quickSelectGroup}>
            {[7, 14, 30, 60, 90].map((days) => (
              <button
                key={days}
                onClick={() => handleQuickSelect(days)}
                style={styles.quickSelectButton}
              >
                {days}d
              </button>
            ))}
          </div>
          <select
            onChange={(e) => handleMonthSelect(e.target.value)}
            style={{ ...styles.monthSelect, marginTop: spacing.xs }}
            defaultValue=""
          >
            <option value="" disabled>Month...</option>
            {monthOptions.map((month, idx) => (
              <option key={month.label} value={idx}>
                {month.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Stats */}
      {prophetData?.summary && (() => {
        // Backend already returns averages for occupancy, totals for rooms
        const otbAvg = prophetData.summary.otb_total
        const priorOtbAvg = prophetData.summary.prior_otb_total
        const forecastAvg = prophetData.summary.forecast_total
        const priorFinalAvg = prophetData.summary.prior_final_total
        const otbDiff = otbAvg - priorOtbAvg
        const forecastDiff = forecastAvg - priorFinalAvg

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>CURRENT OTB</span>
              <span style={styles.summaryValue}>
                {metric === 'occupancy' ? `${otbAvg.toFixed(1)}%` : otbAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: otbDiff >= 0 ? colors.success : colors.error,
              }}>
                vs Prior OTB: {metric === 'occupancy' ? `${priorOtbAvg.toFixed(1)}%` : priorOtbAvg.toFixed(0)}
                {' '}({otbDiff >= 0 ? '+' : ''}{metric === 'occupancy' ? `${otbDiff.toFixed(1)}%` : otbDiff.toFixed(0)})
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>PROPHET FORECAST</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.prophet }}>
                {metric === 'occupancy' ? `${forecastAvg.toFixed(1)}%` : forecastAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: forecastDiff >= 0 ? colors.success : colors.error,
              }}>
                vs Prior Final: {metric === 'occupancy' ? `${priorFinalAvg.toFixed(1)}%` : priorFinalAvg.toFixed(0)}
                {' '}({forecastDiff >= 0 ? '+' : ''}{metric === 'occupancy' ? `${forecastDiff.toFixed(1)}%` : forecastDiff.toFixed(0)})
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>VS PRIOR YEAR</span>
              <div style={{ display: 'flex', gap: spacing.md, justifyContent: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ ...styles.summaryValue, color: colors.success, fontSize: typography.xl }}>
                    {prophetData.summary.days_forecasting_more}
                  </span>
                  <div style={{ fontSize: typography.xs, color: colors.success }}>days up</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ ...styles.summaryValue, color: colors.error, fontSize: typography.xl }}>
                    {prophetData.summary.days_forecasting_less}
                  </span>
                  <div style={{ fontSize: typography.xs, color: colors.error }}>days down</div>
                </div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Prophet Chart */}
      {prophetLoading ? (
        <div style={styles.loadingContainer}>Training Prophet model...</div>
      ) : prophetData?.data && prophetData.data.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={prophetChartData}
            layout={{
              height: 350,
              margin: { l: 50, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              xaxis: {
                showgrid: true,
                gridcolor: colors.border,
                tickangle: -45,
                hoverformat: '%a %d/%m/%y',
              },
              yaxis: {
                showgrid: true,
                gridcolor: colors.border,
                title: { text: metricLabel },
              },
              legend: {
                orientation: 'h',
                y: -0.2,
                x: 0.5,
                xanchor: 'center',
              },
              hovermode: 'x unified',
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%' }}
          />
        </div>
      ) : (
        <div style={styles.emptyContainer}>
          No forecast data available. Ensure sufficient historical data exists.
        </div>
      )}

      {/* Data Table */}
      {prophetData?.data && prophetData.data.length > 0 && (
        <>
          <button onClick={() => setShowTable(!showTable)} style={styles.tableToggle}>
            {showTable ? 'Hide' : 'Show'} Data Table
          </button>

          {showTable && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>DOW</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Current OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prophet</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Lower</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Upper</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr Final</th>
                  </tr>
                </thead>
                <tbody>
                  {prophetData.data.map((row, idx) => (
                    <tr
                      key={row.date}
                      style={{
                        ...styles.tr,
                        backgroundColor: idx % 2 === 0 ? colors.surface : colors.background,
                      }}
                    >
                      <td style={styles.td}>{row.date}</td>
                      <td style={styles.td}>{row.day_of_week}</td>
                      <td style={{ ...styles.td, ...styles.tdRight }}>
                        {row.current_otb !== null ? row.current_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.prior_year_otb !== null ? row.prior_year_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.prophet, fontWeight: typography.semibold }}>
                        {row.forecast !== null ? row.forecast.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.forecast_lower !== null ? row.forecast_lower.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.forecast_upper !== null ? row.forecast_upper.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textMuted }}>
                        {row.prior_year_final !== null ? row.prior_year_final.toFixed(1) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// XGBOOST PREVIEW COMPONENT
// ============================================

const XGBoostPreview: React.FC = () => {
  const token = localStorage.getItem('token')

  // Default to next 30 days, rooms metric (matching pickup page)
  const today = new Date()
  const defaultStart = new Date(today)
  defaultStart.setDate(today.getDate() + 1)
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() + 30)

  const [startDate, setStartDate] = useState(defaultStart.toISOString().split('T')[0])
  const [endDate, setEndDate] = useState(defaultEnd.toISOString().split('T')[0])
  const [metric, setMetric] = useState<MetricType>('rooms')
  const [showTable, setShowTable] = useState(false)

  // Generate month options
  const monthOptions = useMemo(() => getNext12Months(), [])

  // Quick select handlers
  const handleQuickSelect = (days: number) => {
    const start = new Date()
    start.setDate(start.getDate() + 1)
    const end = new Date()
    end.setDate(end.getDate() + days)
    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  // Fetch XGBoost forecast data
  const { data: xgboostData, isLoading: xgboostLoading } = useQuery<XGBoostResponse>({
    queryKey: ['xgboost-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        metric: metric,
      })
      const response = await fetch(`/api/forecast/xgboost-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch XGBoost forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch budget data for revenue metrics
  const budgetData = useBudgetData(startDate, endDate, metric, token)

  const metricLabel = {
    occupancy: 'Occupancy %',
    rooms: 'Room Nights',
    guests: 'Guests',
    ave_guest_rate: 'Ave Guest Rate',
    arr: 'ARR',
    net_accom: 'Net Accomm Rev',
    net_dry: 'Net Dry Rev',
    net_wet: 'Net Wet Rev',
    total_rev: 'Total Net Rev',
  }[metric] || 'Value'
  const unit = {
    occupancy: '%',
    rooms: ' rooms',
    guests: ' guests',
    ave_guest_rate: '',
    arr: '',
    net_accom: '',
    net_dry: '',
    net_wet: '',
    total_rev: '',
  }[metric] || ''

  // Build XGBoost chart data
  const xgboostChartData = useMemo(() => {
    if (!xgboostData?.data) return []

    const dates = xgboostData.data.map((d) => d.date)
    const currentOtb = xgboostData.data.map((d) => d.current_otb)
    const priorYearOtb = xgboostData.data.map((d) => d.prior_year_otb)
    const forecast = xgboostData.data.map((d) => d.forecast)
    const priorYearFinal = xgboostData.data.map((d) => d.prior_year_final)

    // Calculate prior year dates
    const priorDates = xgboostData.data.map((d) => {
      const date = new Date(d.date)
      date.setDate(date.getDate() - 364)
      return formatDate(date)
    })

    return [
      // Prior year final fill first (bottom layer)
      {
        x: dates,
        y: priorYearFinal,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year Final',
        line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
        fill: 'tozeroy' as const,
        fillcolor: CHART_COLORS.priorFinalFill,
        customdata: priorDates,
        hovertemplate: `Prior Final: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
      },
      // Prior year OTB
      {
        x: dates,
        y: priorYearOtb,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year OTB',
        line: { color: CHART_COLORS.priorOtb, width: 2, dash: 'dash' as const },
        customdata: priorDates,
        hovertemplate: `Prior OTB: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
      },
      // Current OTB - green
      {
        x: dates,
        y: currentOtb,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Current OTB',
        line: { color: CHART_COLORS.currentOtb, width: 2 },
        marker: { size: 6 },
        hovertemplate: `Current OTB: %{y:.1f}${unit}<extra></extra>`,
      },
      // XGBoost forecast - orange
      {
        x: dates,
        y: forecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'XGBoost Forecast',
        line: { color: CHART_COLORS.xgboost, width: 3 },
        marker: { size: 8, symbol: 'diamond' },
        hovertemplate: `XGBoost: %{y:.1f}${unit}<extra></extra>`,
      },
    ].concat(buildBudgetTrace(budgetData) ? [buildBudgetTrace(budgetData)!] : [])
  }, [xgboostData, unit, budgetData])

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Live XGBoost</h2>
          <p style={styles.hint}>
            Gradient boosting model trained on historical patterns with lag features
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* Date Range */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Date Range</label>
          <div style={styles.dateInputs}>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.dateInput}
            />
            <span style={styles.dateSeparator}>to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.dateInput}
            />
          </div>
        </div>

        {/* Metric Dropdown */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as MetricType)}
            style={styles.select}
          >
            <option value="occupancy">Occupancy %</option>
            <option value="rooms">Room Nights</option>
            <option value="guests">Guests</option>
            <option value="ave_guest_rate">Ave Guest Rate</option>
            <option value="arr">ARR (Net)</option>
            <option value="net_accom">Net Accomm Rev</option>
            <option value="net_dry">Net Dry Rev</option>
            <option value="net_wet">Net Wet Rev</option>
            <option value="total_rev">Total Net Rev</option>
          </select>
        </div>

        {/* Quick Selects */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Quick Select</label>
          <div style={styles.quickSelectGroup}>
            {[7, 14, 30, 60, 90].map((days) => (
              <button
                key={days}
                onClick={() => handleQuickSelect(days)}
                style={styles.quickSelectButton}
              >
                {days}d
              </button>
            ))}
          </div>
          <select
            onChange={(e) => handleMonthSelect(e.target.value)}
            style={{ ...styles.monthSelect, marginTop: spacing.xs }}
            defaultValue=""
          >
            <option value="" disabled>Month...</option>
            {monthOptions.map((month, idx) => (
              <option key={month.label} value={idx}>
                {month.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Stats */}
      {xgboostData?.summary && (() => {
        // Backend already returns averages for occupancy, totals for rooms
        const otbAvg = xgboostData.summary.otb_total
        const priorOtbAvg = xgboostData.summary.prior_otb_total
        const forecastAvg = xgboostData.summary.forecast_total
        const priorFinalAvg = xgboostData.summary.prior_final_total
        const otbDiff = otbAvg - priorOtbAvg
        const forecastDiff = forecastAvg - priorFinalAvg

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>CURRENT OTB</span>
              <span style={styles.summaryValue}>
                {metric === 'occupancy' ? `${otbAvg.toFixed(1)}%` : otbAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: otbDiff >= 0 ? colors.success : colors.error,
              }}>
                vs Prior OTB: {metric === 'occupancy' ? `${priorOtbAvg.toFixed(1)}%` : priorOtbAvg.toFixed(0)}
                {' '}({otbDiff >= 0 ? '+' : ''}{metric === 'occupancy' ? `${otbDiff.toFixed(1)}%` : otbDiff.toFixed(0)})
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>XGBOOST FORECAST</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.xgboost }}>
                {metric === 'occupancy' ? `${forecastAvg.toFixed(1)}%` : forecastAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: forecastDiff >= 0 ? colors.success : colors.error,
              }}>
                vs Prior Final: {metric === 'occupancy' ? `${priorFinalAvg.toFixed(1)}%` : priorFinalAvg.toFixed(0)}
                {' '}({forecastDiff >= 0 ? '+' : ''}{metric === 'occupancy' ? `${forecastDiff.toFixed(1)}%` : forecastDiff.toFixed(0)})
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>VS PRIOR YEAR</span>
              <div style={{ display: 'flex', gap: spacing.md, justifyContent: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ ...styles.summaryValue, color: colors.success, fontSize: typography.xl }}>
                    {xgboostData.summary.days_forecasting_more}
                  </span>
                  <div style={{ fontSize: typography.xs, color: colors.success }}>days up</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ ...styles.summaryValue, color: colors.error, fontSize: typography.xl }}>
                    {xgboostData.summary.days_forecasting_less}
                  </span>
                  <div style={{ fontSize: typography.xs, color: colors.error }}>days down</div>
                </div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* XGBoost Chart */}
      {xgboostLoading ? (
        <div style={styles.loadingContainer}>Training XGBoost model...</div>
      ) : xgboostData?.data && xgboostData.data.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={xgboostChartData}
            layout={{
              height: 350,
              margin: { l: 50, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              xaxis: {
                showgrid: true,
                gridcolor: colors.border,
                tickangle: -45,
                hoverformat: '%a %d/%m/%y',
              },
              yaxis: {
                showgrid: true,
                gridcolor: colors.border,
                title: { text: metricLabel },
              },
              legend: {
                orientation: 'h',
                y: -0.2,
                x: 0.5,
                xanchor: 'center',
              },
              hovermode: 'x unified',
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%' }}
          />
        </div>
      ) : (
        <div style={styles.emptyContainer}>
          No forecast data available. Ensure sufficient historical data exists.
        </div>
      )}

      {/* Data Table */}
      {xgboostData?.data && xgboostData.data.length > 0 && (
        <>
          <button onClick={() => setShowTable(!showTable)} style={styles.tableToggle}>
            {showTable ? 'Hide' : 'Show'} Data Table
          </button>

          {showTable && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>DOW</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Current OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>XGBoost</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr Final</th>
                  </tr>
                </thead>
                <tbody>
                  {xgboostData.data.map((row, idx) => (
                    <tr
                      key={row.date}
                      style={{
                        ...styles.tr,
                        backgroundColor: idx % 2 === 0 ? colors.surface : colors.background,
                      }}
                    >
                      <td style={styles.td}>{row.date}</td>
                      <td style={styles.td}>{row.day_of_week}</td>
                      <td style={{ ...styles.td, ...styles.tdRight }}>
                        {row.current_otb !== null ? row.current_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.prior_year_otb !== null ? row.prior_year_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.xgboost, fontWeight: typography.semibold }}>
                        {row.forecast !== null ? row.forecast.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textMuted }}>
                        {row.prior_year_final !== null ? row.prior_year_final.toFixed(1) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// CATBOOST PREVIEW COMPONENT
// ============================================

const CatBoostPreview: React.FC = () => {
  const token = localStorage.getItem('token')

  // Default to next 30 days, rooms metric (matching pickup page)
  const today = new Date()
  const defaultStart = new Date(today)
  defaultStart.setDate(today.getDate() + 1)
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() + 30)

  const [startDate, setStartDate] = useState(defaultStart.toISOString().split('T')[0])
  const [endDate, setEndDate] = useState(defaultEnd.toISOString().split('T')[0])
  const [metric, setMetric] = useState<MetricType>('rooms')
  const [showTable, setShowTable] = useState(false)

  // Generate month options
  const monthOptions = useMemo(() => getNext12Months(), [])

  // Quick select handlers
  const handleQuickSelect = (days: number) => {
    const start = new Date()
    start.setDate(start.getDate() + 1)
    const end = new Date()
    end.setDate(end.getDate() + days)
    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  // Fetch CatBoost forecast data
  const { data: catboostData, isLoading: catboostLoading } = useQuery<CatBoostResponse>({
    queryKey: ['catboost-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        metric: metric,
      })
      const response = await fetch(`/api/forecast/catboost-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch CatBoost forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch budget data for revenue metrics
  const budgetData = useBudgetData(startDate, endDate, metric, token)

  const metricLabel = {
    occupancy: 'Occupancy %',
    rooms: 'Room Nights',
    guests: 'Guests',
    ave_guest_rate: 'Ave Guest Rate',
    arr: 'ARR',
    net_accom: 'Net Accomm Rev',
    net_dry: 'Net Dry Rev',
    net_wet: 'Net Wet Rev',
    total_rev: 'Total Net Rev',
  }[metric] || 'Value'
  const unit = {
    occupancy: '%',
    rooms: ' rooms',
    guests: ' guests',
    ave_guest_rate: '',
    arr: '',
    net_accom: '',
    net_dry: '',
    net_wet: '',
    total_rev: '',
  }[metric] || ''

  // Build CatBoost chart data
  const catboostChartData = useMemo(() => {
    if (!catboostData?.data) return []

    const dates = catboostData.data.map((d) => d.date)
    const currentOtb = catboostData.data.map((d) => d.current_otb)
    const priorYearOtb = catboostData.data.map((d) => d.prior_year_otb)
    const forecast = catboostData.data.map((d) => d.forecast)
    const priorYearFinal = catboostData.data.map((d) => d.prior_year_final)

    // Calculate prior year dates
    const priorDates = catboostData.data.map((d) => {
      const date = new Date(d.date)
      date.setDate(date.getDate() - 364)
      return formatDate(date)
    })

    return [
      // Prior year final fill first (bottom layer)
      {
        x: dates,
        y: priorYearFinal,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year Final',
        line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
        fill: 'tozeroy' as const,
        fillcolor: CHART_COLORS.priorFinalFill,
        customdata: priorDates,
        hovertemplate: `Prior Final: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
      },
      // Prior year OTB
      {
        x: dates,
        y: priorYearOtb,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year OTB',
        line: { color: CHART_COLORS.priorOtb, width: 2, dash: 'dash' as const },
        customdata: priorDates,
        hovertemplate: `Prior OTB: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
      },
      // Current OTB - green
      {
        x: dates,
        y: currentOtb,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Current OTB',
        line: { color: CHART_COLORS.currentOtb, width: 2 },
        marker: { size: 6 },
        hovertemplate: `Current OTB: %{y:.1f}${unit}<extra></extra>`,
      },
      // CatBoost forecast - violet
      {
        x: dates,
        y: forecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'CatBoost Forecast',
        line: { color: CHART_COLORS.catboost, width: 3 },
        marker: { size: 8, symbol: 'diamond' },
        hovertemplate: `CatBoost: %{y:.1f}${unit}<extra></extra>`,
      },
    ].concat(buildBudgetTrace(budgetData) ? [buildBudgetTrace(budgetData)!] : [])
  }, [catboostData, unit, budgetData])

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Live CatBoost</h2>
          <p style={styles.hint}>
            Gradient boosting with native categorical feature support - no encoding needed
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* Date Range */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Date Range</label>
          <div style={styles.dateInputs}>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.dateInput}
            />
            <span style={styles.dateSeparator}>to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.dateInput}
            />
          </div>
        </div>

        {/* Metric Dropdown */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as MetricType)}
            style={styles.select}
          >
            <option value="occupancy">Occupancy %</option>
            <option value="rooms">Room Nights</option>
            <option value="guests">Guests</option>
            <option value="ave_guest_rate">Ave Guest Rate</option>
            <option value="arr">ARR (Net)</option>
            <option value="net_accom">Net Accomm Rev</option>
            <option value="net_dry">Net Dry Rev</option>
            <option value="net_wet">Net Wet Rev</option>
            <option value="total_rev">Total Net Rev</option>
          </select>
        </div>

        {/* Quick Selects */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Quick Select</label>
          <div style={styles.quickSelectGroup}>
            {[7, 14, 30, 60, 90].map((days) => (
              <button
                key={days}
                onClick={() => handleQuickSelect(days)}
                style={styles.quickSelectButton}
              >
                {days}d
              </button>
            ))}
          </div>
          <select
            onChange={(e) => handleMonthSelect(e.target.value)}
            style={{ ...styles.monthSelect, marginTop: spacing.xs }}
            defaultValue=""
          >
            <option value="" disabled>Month...</option>
            {monthOptions.map((month, idx) => (
              <option key={month.label} value={idx}>
                {month.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Stats */}
      {catboostData?.summary && (() => {
        const otbAvg = catboostData.summary.otb_total
        const priorOtbAvg = catboostData.summary.prior_otb_total
        const forecastAvg = catboostData.summary.forecast_total
        const priorFinalAvg = catboostData.summary.prior_final_total
        const otbDiff = otbAvg - priorOtbAvg
        const forecastDiff = forecastAvg - priorFinalAvg

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>CURRENT OTB</span>
              <span style={styles.summaryValue}>
                {metric === 'occupancy' ? `${otbAvg.toFixed(1)}%` : otbAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: otbDiff >= 0 ? colors.success : colors.error,
              }}>
                vs Prior OTB: {metric === 'occupancy' ? `${priorOtbAvg.toFixed(1)}%` : priorOtbAvg.toFixed(0)}
                {' '}({otbDiff >= 0 ? '+' : ''}{metric === 'occupancy' ? `${otbDiff.toFixed(1)}%` : otbDiff.toFixed(0)})
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>CATBOOST FORECAST</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.catboost }}>
                {metric === 'occupancy' ? `${forecastAvg.toFixed(1)}%` : forecastAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: forecastDiff >= 0 ? colors.success : colors.error,
              }}>
                vs Prior Final: {metric === 'occupancy' ? `${priorFinalAvg.toFixed(1)}%` : priorFinalAvg.toFixed(0)}
                {' '}({forecastDiff >= 0 ? '+' : ''}{metric === 'occupancy' ? `${forecastDiff.toFixed(1)}%` : forecastDiff.toFixed(0)})
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>VS PRIOR YEAR</span>
              <div style={{ display: 'flex', gap: spacing.md, justifyContent: 'center' }}>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ ...styles.summaryValue, color: colors.success, fontSize: typography.xl }}>
                    {catboostData.summary.days_forecasting_more}
                  </span>
                  <div style={{ fontSize: typography.xs, color: colors.success }}>days up</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ ...styles.summaryValue, color: colors.error, fontSize: typography.xl }}>
                    {catboostData.summary.days_forecasting_less}
                  </span>
                  <div style={{ fontSize: typography.xs, color: colors.error }}>days down</div>
                </div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* CatBoost Chart */}
      {catboostLoading ? (
        <div style={styles.loadingContainer}>Training CatBoost model...</div>
      ) : catboostData?.data && catboostData.data.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={catboostChartData}
            layout={{
              height: 350,
              margin: { l: 50, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              xaxis: {
                showgrid: true,
                gridcolor: colors.border,
                tickangle: -45,
                hoverformat: '%a %d/%m/%y',
              },
              yaxis: {
                showgrid: true,
                gridcolor: colors.border,
                title: { text: metricLabel },
              },
              legend: {
                orientation: 'h',
                y: -0.2,
                x: 0.5,
                xanchor: 'center',
              },
              hovermode: 'x unified',
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%' }}
          />
        </div>
      ) : (
        <div style={styles.emptyContainer}>
          No forecast data available. Ensure sufficient historical data exists.
        </div>
      )}

      {/* Data Table */}
      {catboostData?.data && catboostData.data.length > 0 && (
        <>
          <button onClick={() => setShowTable(!showTable)} style={styles.tableToggle}>
            {showTable ? 'Hide' : 'Show'} Data Table
          </button>

          {showTable && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>DOW</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Current OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>CatBoost</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr Final</th>
                  </tr>
                </thead>
                <tbody>
                  {catboostData.data.map((row, idx) => (
                    <tr
                      key={row.date}
                      style={{
                        ...styles.tr,
                        backgroundColor: idx % 2 === 0 ? colors.surface : colors.background,
                      }}
                    >
                      <td style={styles.td}>{row.date}</td>
                      <td style={styles.td}>{row.day_of_week}</td>
                      <td style={{ ...styles.td, ...styles.tdRight }}>
                        {row.current_otb !== null ? row.current_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.prior_year_otb !== null ? row.prior_year_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.catboost, fontWeight: typography.semibold }}>
                        {row.forecast !== null ? row.forecast.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textMuted }}>
                        {row.prior_year_final !== null ? row.prior_year_final.toFixed(1) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// BLENDED FORECAST COMPONENT
// ============================================

const BlendedPreview: React.FC = () => {
  const token = localStorage.getItem('token')

  // Default to next 30 days
  const today = new Date()
  const defaultStart = new Date(today)
  defaultStart.setDate(today.getDate() + 1)
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() + 30)

  const [startDate, setStartDate] = useState(defaultStart.toISOString().split('T')[0])
  const [endDate, setEndDate] = useState(defaultEnd.toISOString().split('T')[0])
  const [metric, setMetric] = useState<MetricType>('rooms')
  const [showTable, setShowTable] = useState(false)

  // Generate month options
  const monthOptions = useMemo(() => getNext12Months(), [])

  // Quick select handlers
  const handleQuickSelect = (days: number) => {
    const start = new Date()
    start.setDate(start.getDate() + 1)
    const end = new Date()
    end.setDate(end.getDate() + days)
    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  // Fetch blended forecast from backend (uses MAPE-weighted + 60/40 blend)
  const { data: blendedData, isLoading } = useQuery<BlendedPreviewResponse>({
    queryKey: ['blended-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/blended-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch blended forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  const isRevenueMetric = REVENUE_METRICS.includes(metric)

  const metricLabel = {
    occupancy: 'Occupancy %',
    rooms: 'Room Nights',
    guests: 'Guests',
    ave_guest_rate: 'Ave Guest Rate',
    arr: 'ARR',
    net_accom: 'Net Accomm Rev',
    net_dry: 'Net Dry Rev',
    net_wet: 'Net Wet Rev',
    total_rev: 'Total Net Rev',
  }[metric] || 'Value'

  const unit = {
    occupancy: '%',
    rooms: ' rooms',
    guests: ' guests',
    ave_guest_rate: '',
    arr: '',
    net_accom: '',
    net_dry: '',
    net_wet: '',
    total_rev: '',
  }[metric] || ''

  // Use backend blended forecast data (already MAPE-weighted + 60/40 blend)
  const blendedResults = useMemo(() => {
    if (!blendedData) return null

    return {
      data: blendedData.data,
      summary: blendedData.summary
    }
  }, [blendedData])

  // Build blended chart data
  const blendedChartData = useMemo(() => {
    if (!blendedResults?.data) return []

    const dates = blendedResults.data.map((d) => d.date)
    const currentOtb = blendedResults.data.map((d) => d.current_otb)
    const priorYearOtb = blendedResults.data.map((d) => d.prior_year_otb)
    const blendedForecast = blendedResults.data.map((d) => d.blended_forecast)
    const priorYearFinal = blendedResults.data.map((d) => d.prior_year_final)
    const budgetOrPrior = blendedResults.data.map((d) => d.budget_or_prior)

    // Calculate prior year dates for hover
    const priorDates = blendedResults.data.map((d) => {
      const date = new Date(d.date)
      date.setDate(date.getDate() - 364)
      return formatDate(date)
    })

    return [
      // Prior year final fill (bottom layer)
      {
        x: dates,
        y: priorYearFinal,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year Final',
        fill: 'tozeroy' as const,
        fillcolor: CHART_COLORS.priorFinalFill,
        line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
        customdata: priorDates,
        hovertemplate: `Prior Final (%{customdata}): %{y:.1f}${unit}<extra></extra>`,
      },
      // Prior year OTB
      {
        x: dates,
        y: priorYearOtb,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year OTB',
        line: { color: CHART_COLORS.priorOtb, width: 2, dash: 'dash' as const },
        customdata: priorDates,
        hovertemplate: `Prior OTB (%{customdata}): %{y:.1f}${unit}<extra></extra>`,
      },
      // Current OTB
      {
        x: dates,
        y: currentOtb,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Current OTB',
        line: { color: CHART_COLORS.currentOtb, width: 2 },
        marker: { size: 6 },
        hovertemplate: `Current OTB: %{y:.1f}${unit}<extra></extra>`,
      },
      // Blended forecast
      {
        x: dates,
        y: blendedForecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Blended Forecast',
        line: { color: CHART_COLORS.blended, width: 3 },
        marker: { size: 8 },
        hovertemplate: `Blended: %{y:.1f}${unit}<extra></extra>`,
      },
      // Budget or Prior Year (what contributes to blended)
      {
        x: dates,
        y: budgetOrPrior,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: isRevenueMetric ? 'Budget Target (40%)' : 'Prior Year (40%)',
        line: { color: CHART_COLORS.budget, width: 2, dash: 'dash' as const },
        hovertemplate: `${isRevenueMetric ? 'Budget' : 'Prior Year'}: %{y:.1f}${unit}<extra></extra>`,
      },
    ]
  }, [blendedResults, unit, isRevenueMetric])

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Live Blended</h2>
          <p style={styles.hint}>
            Equal-weighted ensemble combining Prophet, XGBoost, and CatBoost (60%) with{' '}
            {isRevenueMetric ? 'budget targets' : 'prior year patterns'} (40%)
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* Date Range */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Date Range</label>
          <div style={styles.dateInputs}>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.dateInput}
            />
            <span style={styles.dateSeparator}>to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.dateInput}
            />
          </div>
        </div>

        {/* Metric Dropdown */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as MetricType)}
            style={styles.select}
          >
            <option value="occupancy">Occupancy %</option>
            <option value="rooms">Room Nights</option>
            <option value="guests">Guests</option>
            <option value="ave_guest_rate">Ave Guest Rate</option>
            <option value="arr">ARR (Net)</option>
            <option value="net_accom">Net Accomm Rev</option>
            <option value="net_dry">Net Dry Rev</option>
            <option value="net_wet">Net Wet Rev</option>
            <option value="total_rev">Total Net Rev</option>
          </select>
        </div>

        {/* Quick Selects */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Quick Select</label>
          <div style={styles.quickSelectGroup}>
            {[7, 14, 30, 60, 90].map((days) => (
              <button
                key={days}
                onClick={() => handleQuickSelect(days)}
                style={styles.quickSelectButton}
              >
                {days}d
              </button>
            ))}
          </div>
          <select
            onChange={(e) => handleMonthSelect(e.target.value)}
            style={{ ...styles.monthSelect, marginTop: spacing.xs }}
            defaultValue=""
          >
            <option value="" disabled>Month...</option>
            {monthOptions.map((month, idx) => (
              <option key={month.label} value={idx}>
                {month.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Stats */}
      {blendedResults?.summary && (() => {
        const otbVal = blendedResults.summary.otb_total
        const priorOtbVal = blendedResults.summary.prior_otb_total
        const forecastVal = blendedResults.summary.forecast_total
        const priorFinalVal = blendedResults.summary.prior_final_total
        const otbDiff = otbVal - priorOtbVal
        const forecastDiff = forecastVal - priorFinalVal

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>CURRENT OTB</span>
              <span style={styles.summaryValue}>
                {metric === 'occupancy' ? `${otbVal.toFixed(1)}%` : otbVal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </span>
              <span style={{
                ...styles.summaryDiff,
                color: otbDiff >= 0 ? colors.success : colors.error
              }}>
                vs Prior OTB: {otbDiff >= 0 ? '+' : ''}{otbDiff.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>BLENDED FORECAST</span>
              <span style={{ ...styles.summaryValue, color: colors.success }}>
                {metric === 'occupancy' ? `${forecastVal.toFixed(1)}%` : forecastVal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </span>
              <span style={{
                ...styles.summaryDiff,
                color: forecastDiff >= 0 ? colors.success : colors.error
              }}>
                vs Prior Final: {forecastDiff >= 0 ? '+' : ''}{forecastDiff.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>VS PRIOR YEAR</span>
              <div style={{ display: 'flex', gap: spacing.md, justifyContent: 'center' }}>
                <div>
                  <span style={{ ...styles.summaryValue, color: colors.success, fontSize: '1.5rem' }}>
                    {blendedResults.summary.days_forecasting_more}
                  </span>
                  <span style={{ ...styles.summaryDiff, display: 'block' }}>days up</span>
                </div>
                <div>
                  <span style={{ ...styles.summaryValue, color: colors.error, fontSize: '1.5rem' }}>
                    {blendedResults.summary.days_forecasting_less}
                  </span>
                  <span style={{ ...styles.summaryDiff, display: 'block' }}>days down</span>
                </div>
              </div>
            </div>
          </div>
        )
      })()}

      {/* Model Weights Info */}
      {blendedResults?.summary && (
        <div style={{ ...styles.summaryCard, marginBottom: spacing.md, padding: spacing.sm }}>
          <span style={{ ...styles.summaryLabel, fontSize: '0.75rem' }}>MODEL BLEND (MAPE-weighted)</span>
          <div style={{ display: 'flex', gap: spacing.lg, justifyContent: 'center', marginTop: spacing.xs }}>
            <span style={{ color: CHART_COLORS.prophet }}>
              Prophet: {(blendedResults.summary.prophet_weight * 100).toFixed(1)}%
            </span>
            <span style={{ color: CHART_COLORS.xgboost }}>
              XGBoost: {(blendedResults.summary.xgboost_weight * 100).toFixed(1)}%
            </span>
            <span style={{ color: CHART_COLORS.catboost }}>
              CatBoost: {(blendedResults.summary.catboost_weight * 100).toFixed(1)}%
            </span>
          </div>
          <div style={{ marginTop: spacing.xs, fontSize: '0.7rem', color: colors.textSecondary }}>
            60% MAPE-Weighted Models + 40% {isRevenueMetric ? 'Budget' : 'Prior Year'}
          </div>
        </div>
      )}

      {/* Chart */}
      {isLoading ? (
        <div style={styles.loadingContainer}>Calculating blended forecast...</div>
      ) : blendedResults?.data && blendedResults.data.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={blendedChartData}
            layout={{
              height: 350,
              margin: { l: 50, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              xaxis: {
                title: { text: 'Date' },
                tickangle: -45,
                tickfont: { size: 10 },
                gridcolor: colors.border,
                zerolinecolor: colors.border,
              },
              yaxis: {
                title: { text: metricLabel },
                rangemode: 'tozero' as const,
                gridcolor: colors.border,
                zerolinecolor: colors.border,
              },
              legend: {
                orientation: 'h' as const,
                y: -0.25,
                x: 0.5,
                xanchor: 'center' as const,
              },
              hovermode: 'x unified' as const,
            }}
            style={{ width: '100%', height: '100%' }}
            config={{ responsive: true, displayModeBar: false }}
          />
        </div>
      ) : null}

      {/* Data Table Toggle */}
      {blendedResults?.data && blendedResults.data.length > 0 && (
        <>
          <button
            onClick={() => setShowTable(!showTable)}
            style={styles.toggleButton}
          >
            {showTable ? 'Hide Data Table' : 'Show Data Table'}
          </button>

          {showTable && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>DOW</th>
                    <th style={styles.th}>Current OTB</th>
                    <th style={styles.th}>Prior OTB</th>
                    <th style={styles.th}>Blended FC</th>
                    <th style={styles.th}>{isRevenueMetric ? 'Budget' : 'Prior Yr'}</th>
                    <th style={styles.th}>Prior Final</th>
                  </tr>
                </thead>
                <tbody>
                  {blendedResults.data.map((row) => (
                    <tr key={row.date}>
                      <td style={styles.td}>{row.date}</td>
                      <td style={styles.td}>{row.day_of_week}</td>
                      <td style={styles.td}>{row.current_otb?.toLocaleString(undefined, { maximumFractionDigits: 1 }) ?? '-'}</td>
                      <td style={styles.td}>{row.prior_year_otb?.toLocaleString(undefined, { maximumFractionDigits: 1 }) ?? '-'}</td>
                      <td style={{ ...styles.td, fontWeight: 600, color: colors.success }}>
                        {row.blended_forecast?.toLocaleString(undefined, { maximumFractionDigits: 1 }) ?? '-'}
                      </td>
                      <td style={{ ...styles.td, color: CHART_COLORS.budget }}>
                        {row.budget_or_prior?.toLocaleString(undefined, { maximumFractionDigits: 1 }) ?? '-'}
                      </td>
                      <td style={styles.td}>{row.prior_year_final?.toLocaleString(undefined, { maximumFractionDigits: 1 }) ?? '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// PICKUP-V2 FORECAST COMPONENT (Production)
// Clean revenue forecast using Pickup-V2 model
// ============================================

interface PickupV2ForecastProps {
  consolidation: 'daily' | 'weekly' | 'monthly'
}

const PickupV2Forecast: React.FC<PickupV2ForecastProps> = ({ consolidation }) => {
  const token = localStorage.getItem('token')
  const pickupTableRef = useRef<HTMLDivElement>(null)

  // Helper: get Monday of the week containing a date
  const getMondayOfWeek = (date: Date): Date => {
    const d = new Date(date)
    const day = d.getDay()
    const diff = day === 0 ? -6 : 1 - day // Adjust to Monday (day 0 = Sunday)
    d.setDate(d.getDate() + diff)
    d.setHours(0, 0, 0, 0)
    return d
  }

  // Helper: get ISO week number
  const getISOWeekNumber = (date: Date): number => {
    const d = new Date(date)
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() + 4 - (d.getDay() || 7))
    const yearStart = new Date(d.getFullYear(), 0, 1)
    return Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  }

  // Helper: get financial year start (August of the current FY)
  // Financial year runs Aug-Jul, so if we're in Jan-Jul, FY started previous August
  const getFinancialYearStart = (date: Date): string => {
    const year = date.getFullYear()
    const month = date.getMonth() // 0-indexed (0=Jan, 7=Aug)
    // If we're in Aug-Dec (months 7-11), FY started this year's August
    // If we're in Jan-Jul (months 0-6), FY started last year's August
    const fyStartYear = month >= 7 ? year : year - 1
    return `${fyStartYear}-08` // August
  }

  // Default values depend on consolidation type
  const today = new Date()
  const currentMonday = getMondayOfWeek(today)

  // For monthly: default to financial year (Aug-Jul); for daily: current month; for weekly: week-based
  const [selectedMonth, setSelectedMonth] = useState(() => {
    if (consolidation === 'monthly') {
      return getFinancialYearStart(today) // Start of financial year (August)
    }
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  })
  const [selectedWeek, setSelectedWeek] = useState(() => formatDate(currentMonday))
  // Monthly defaults to 12 months (full FY), daily to 1 month, weekly handled separately
  const [duration, setDuration] = useState<'1' | '3' | '6' | '12'>(
    consolidation === 'monthly' ? '12' : consolidation === 'daily' ? '1' : '3'
  )
  const [weekDuration, setWeekDuration] = useState<'4' | '8' | '13' | '26'>('13') // Default 13 weeks (~3 months)
  const [showTable, setShowTable] = useState(true) // Default to showing budget/forecast table
  const [showPickupTable, setShowPickupTable] = useState(false) // Pickup/rate data table
  const [useCustomDates, setUseCustomDates] = useState(false)
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')

  // Generate month options (24 months back + current + 12 months forward)
  const monthOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const now = new Date()
    for (let i = -24; i <= 12; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() + i, 1)
      const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      const label = date.toLocaleString('default', { month: 'short', year: 'numeric' })
      options.push({ value, label })
    }
    return options
  }, [])

  // Generate week options (52 weeks back + current + 26 weeks forward) - Mon-Sun weeks
  const weekOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const now = new Date()
    const currentMon = getMondayOfWeek(now)

    for (let i = -52; i <= 26; i++) {
      const monday = new Date(currentMon)
      monday.setDate(currentMon.getDate() + (i * 7))
      const sunday = new Date(monday)
      sunday.setDate(monday.getDate() + 6)

      const weekNum = getISOWeekNumber(monday)
      const value = formatDate(monday)
      const label = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })})`
      options.push({ value, label })
    }
    return options
  }, [])

  // Calculate start and end dates based on consolidation type and selection
  const { startDate, endDate } = useMemo(() => {
    if (useCustomDates && customStartDate && customEndDate) {
      return { startDate: customStartDate, endDate: customEndDate }
    }

    if (consolidation === 'weekly') {
      // Week-based: start from selected Monday, duration in weeks
      const start = new Date(selectedWeek)
      const durationWeeks = parseInt(weekDuration)
      const end = new Date(start)
      end.setDate(start.getDate() + (durationWeeks * 7) - 1) // End on Sunday of last week
      return {
        startDate: formatDate(start),
        endDate: formatDate(end)
      }
    } else {
      // Month-based for daily/monthly
      const [year, month] = selectedMonth.split('-').map(Number)
      const start = new Date(year, month - 1, 1)
      const durationMonths = parseInt(duration)
      const end = new Date(year, month - 1 + durationMonths, 0)
      return {
        startDate: formatDate(start),
        endDate: formatDate(end)
      }
    }
  }, [selectedMonth, selectedWeek, duration, weekDuration, consolidation, useCustomDates, customStartDate, customEndDate])

  // Fetch Pickup-V2 forecast from backend
  const { data: forecastData, isLoading: forecastLoading } = useQuery<PickupV2Response>({
    queryKey: ['pickup-v2-forecast', startDate, endDate],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric: 'net_accom' })
      const response = await fetch(`/api/forecast/pickup-v2-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch actuals data from newbook_net_revenue_data for past days
  const { data: actualsData, isLoading: actualsLoading } = useQuery<ActualsResponse>({
    queryKey: ['actuals-for-pickup-v2', startDate, endDate],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric: 'net_accom' })
      const response = await fetch(`/api/forecast/actuals?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch actuals')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch room categories for category name lookup
  const { data: roomCategories } = useQuery<{ site_id: string; site_name: string }[]>({
    queryKey: ['room-categories'],
    queryFn: async () => {
      const response = await fetch('/api/config/room-categories', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // Cache for 5 minutes
  })

  // Build category name map
  const categoryNameMap = useMemo(() => {
    const map: Record<string, string> = {}
    if (roomCategories) {
      for (const cat of roomCategories) {
        map[cat.site_id] = cat.site_name
      }
    }
    return map
  }, [roomCategories])

  const isLoading = forecastLoading || actualsLoading

  // Fetch budget data
  const budgetData = useBudgetData(startDate, endDate, 'net_accom', token)

  // Build budget map
  const budgetMap = useMemo(() => {
    const map: Record<string, number> = {}
    if (budgetData) {
      for (const b of budgetData) {
        map[b.date] = b.budget_value
      }
    }
    return map
  }, [budgetData])

  // Build actuals map (actual_value from newbook_net_revenue_data)
  const actualsMap = useMemo(() => {
    const map: Record<string, number> = {}
    if (actualsData?.data) {
      for (const a of actualsData.data) {
        if (a.actual_value !== null) {
          map[a.date] = a.actual_value
        }
      }
    }
    return map
  }, [actualsData])

  // Consolidate data for weekly/monthly views
  const consolidatedData = useMemo(() => {
    if (!forecastData?.data || consolidation === 'daily') return null

    const todayStr = formatDate(new Date())
    const groups: Record<string, {
      label: string
      startDate: string
      otb: number
      futureOtb: number  // OTB only for future days (for chart stacking)
      forecast: number
      actual: number  // Actual revenue for past days
      forecastRemaining: number  // Forecast for future days in partial periods
      priorYear: number
      budget: number
      days: number
      pastDays: number  // Count of past days in this period
      futureDays: number  // Count of future days in this period
    }> = {}

    forecastData.data.forEach(d => {
      const dateObj = new Date(d.date)
      let groupKey: string
      let groupLabel: string

      if (consolidation === 'weekly') {
        // Get Monday of this week (Mon-Sun week)
        const dayOfWeek = dateObj.getDay()
        const monday = new Date(dateObj)
        monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
        const sunday = new Date(monday)
        sunday.setDate(monday.getDate() + 6)

        // Use Monday date as key for consistent sorting
        groupKey = formatDate(monday)

        // ISO week number for label
        const d = new Date(monday)
        d.setDate(d.getDate() + 4 - (d.getDay() || 7))
        const yearStart = new Date(d.getFullYear(), 0, 1)
        const weekNum = Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)

        groupLabel = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })})`
      } else {
        groupKey = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}`
        groupLabel = dateObj.toLocaleString('default', { month: 'short', year: 'numeric' })
      }

      if (!groups[groupKey]) {
        groups[groupKey] = {
          label: groupLabel,
          startDate: d.date,
          otb: 0,
          futureOtb: 0,  // OTB only for future days (for chart stacking)
          forecast: 0,
          actual: 0,
          forecastRemaining: 0,
          priorYear: 0,
          budget: 0,
          days: 0,
          pastDays: 0,
          futureDays: 0
        }
      }

      const isPast = d.date < todayStr
      groups[groupKey].otb += d.current_otb_rev || 0  // Total OTB (for reference)
      groups[groupKey].forecast += d.forecast || 0
      groups[groupKey].priorYear += d.prior_year_final_rev || 0
      groups[groupKey].budget += budgetMap[d.date] || 0
      groups[groupKey].days++

      if (isPast) {
        // Past day - use actual revenue (OTB not relevant for past)
        groups[groupKey].actual += actualsMap[d.date] ?? 0
        groups[groupKey].pastDays++
      } else {
        // Future day - track OTB and forecast separately
        groups[groupKey].futureOtb += d.current_otb_rev || 0  // OTB for future days only
        groups[groupKey].forecastRemaining += d.forecast || 0
        groups[groupKey].futureDays++
      }
    })

    return Object.entries(groups)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, data]) => {
        // For display: projected = actual + forecastRemaining
        const projected = data.actual + data.forecastRemaining
        return {
          key,
          ...data,
          projected,
          variance: projected - data.priorYear,
          variancePct: data.priorYear > 0 ? ((projected / data.priorYear) - 1) * 100 : 0,
          budgetVariance: projected - data.budget,
          budgetVariancePct: data.budget > 0 ? ((projected / data.budget) - 1) * 100 : 0
        }
      })
  }, [forecastData, consolidation, budgetMap])

  // Build chart data
  const chartData = useMemo(() => {
    if (consolidation !== 'daily' && consolidatedData) {
      const labels = consolidatedData.map(d => d.label)
      const actuals = consolidatedData.map(d => d.actual)
      // futureOtb = OTB only for future days (already tracked in consolidation)
      const futureOtb = consolidatedData.map(d => d.futureOtb)
      // Pickup portion = forecast remaining minus future OTB (the expected additional revenue)
      const pickupPortion = consolidatedData.map((d) => {
        if (d.futureDays === 0) return 0
        return Math.max(0, d.forecastRemaining - d.futureOtb)  // Pickup = Forecast - OTB
      })
      const priorYear = consolidatedData.map(d => d.priorYear)
      const budget = consolidatedData.map(d => d.budget)

      // Stacked bars: Actual (green, bottom) + OTB (cyan, middle) + Pickup/Forecast (amber, top)
      // Total bar height = Actual + OTB + Pickup = Actual + Forecast (since Forecast = OTB + Pickup)
      // Lines: Prior Year (dotted) + Budget (dashed)
      const traces: any[] = [
        // Stacked bar: Actual (bottom) - green
        {
          x: labels,
          y: actuals,
          type: 'bar' as const,
          name: 'Actual',
          marker: { color: colors.success },  // Green for actuals
          hovertemplate: `Actual: £%{y:,.0f}<extra></extra>`,
        },
        // Stacked bar: Future OTB (middle) - cyan - already booked revenue
        {
          x: labels,
          y: futureOtb,
          type: 'bar' as const,
          name: 'OTB (Booked)',
          marker: { color: CHART_COLORS.futureOtb },  // Cyan for OTB
          hovertemplate: `OTB: £%{y:,.0f}<extra></extra>`,
        },
        // Stacked bar: Pickup/Forecast (top) - amber - expected additional pickup
        {
          x: labels,
          y: pickupPortion,
          type: 'bar' as const,
          name: 'Forecast',
          marker: { color: CHART_COLORS.blended },  // Amber for forecast/pickup
          hovertemplate: `Forecast (Pickup): £%{y:,.0f}<extra></extra>`,
        },
        // Prior Year as line (not stacked)
        {
          x: labels,
          y: priorYear,
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Prior Year',
          line: { color: CHART_COLORS.priorFinal, width: 2, dash: 'dot' as const },
          marker: { size: 6 },
          hovertemplate: `Prior Year: £%{y:,.0f}<extra></extra>`,
        },
      ]

      if (budget.some(b => b > 0)) {
        traces.push({
          x: labels,
          y: budget,
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Budget',
          line: { color: CHART_COLORS.budget, width: 2, dash: 'dash' as const },
          marker: { size: 8 },
          hovertemplate: `Budget: £%{y:,.0f}<extra></extra>`,
        })
      }

      return traces
    }

    if (!forecastData?.data) return []

    const todayStr = formatDate(new Date())
    const dates = forecastData.data.map(d => d.date)
    const priorFinal = forecastData.data.map(d => d.prior_year_final_rev)
    const priorOtb = forecastData.data.map(d => d.prior_year_otb_rev)
    const priorDates = forecastData.data.map(d => d.prior_year_date)

    // Split data into actuals (past) and future OTB
    const actualDates: string[] = []
    const actualValues: (number | null)[] = []
    const futureOtbDates: string[] = []
    const futureOtbValues: (number | null)[] = []
    const forecastDates: string[] = []
    const forecastValues: (number | null)[] = []
    const upperBoundValues: (number | null)[] = []
    const lowerBoundValues: (number | null)[] = []

    forecastData.data.forEach(d => {
      if (d.date < todayStr) {
        // Past dates - show actuals from newbook_net_revenue_data (green)
        actualDates.push(d.date)
        actualValues.push(actualsMap[d.date] ?? null)
      } else {
        // Future dates - show OTB in cyan and forecast in red
        futureOtbDates.push(d.date)
        futureOtbValues.push(d.current_otb_rev)
        forecastDates.push(d.date)
        forecastValues.push(d.forecast)
        upperBoundValues.push(d.upper_bound ?? null)
        lowerBoundValues.push(d.lower_bound ?? null)
      }
    })

    const traces: any[] = [
      // Prior year final fill (bottom layer)
      {
        x: dates,
        y: priorFinal,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year Final',
        fill: 'tozeroy' as const,
        fillcolor: CHART_COLORS.priorFinalFill,
        line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
        customdata: priorDates,
        hovertemplate: 'Prior Final (%{customdata}): £%{y:,.0f}<extra></extra>',
      },
      // Prior year OTB (dashed gray)
      {
        x: dates,
        y: priorOtb,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year OTB',
        line: { color: CHART_COLORS.priorOtb, width: 2, dash: 'dash' as const },
        customdata: priorDates,
        hovertemplate: 'Prior OTB (%{customdata}): £%{y:,.0f}<extra></extra>',
      },
    ]

    // Actuals (past dates) - solid green
    if (actualDates.length > 0) {
      traces.push({
        x: actualDates,
        y: actualValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Actual',
        line: { color: CHART_COLORS.currentOtb, width: 2 },
        marker: { size: 6 },
        hovertemplate: 'Actual: £%{y:,.0f}<extra></extra>',
      })
    }

    // Future OTB - cyan
    if (futureOtbDates.length > 0) {
      traces.push({
        x: futureOtbDates,
        y: futureOtbValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Future OTB',
        line: { color: CHART_COLORS.futureOtb, width: 2 },
        marker: { size: 6 },
        hovertemplate: 'Future OTB: £%{y:,.0f}<extra></extra>',
      })
    }

    // Upper/Lower bounds - filled area (add before forecast so forecast line is on top)
    if (forecastDates.length > 0 && upperBoundValues.some(v => v !== null)) {
      // Lower bound line (invisible, just for fill reference)
      traces.push({
        x: forecastDates,
        y: lowerBoundValues,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Lower Bound',
        line: { color: 'rgba(234, 88, 12, 0.3)', width: 1 },
        showlegend: false,
        hovertemplate: 'Lower: £%{y:,.0f}<extra></extra>',
      })
      // Upper bound with fill to lower bound
      traces.push({
        x: forecastDates,
        y: upperBoundValues,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Forecast Range',
        fill: 'tonexty' as const,
        fillcolor: 'rgba(234, 88, 12, 0.15)',
        line: { color: 'rgba(234, 88, 12, 0.3)', width: 1 },
        hovertemplate: 'Upper: £%{y:,.0f}<extra></extra>',
      })
    }

    // Forecast (future dates only) - amber to match summary
    if (forecastDates.length > 0) {
      traces.push({
        x: forecastDates,
        y: forecastValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Forecast',
        line: { color: CHART_COLORS.blended, width: 3 },
        marker: { size: 8 },
        hovertemplate: 'Forecast: £%{y:,.0f}<extra></extra>',
      })
    }

    // Budget trace
    const budgetTrace = buildBudgetTrace(budgetData)
    if (budgetTrace) traces.push(budgetTrace)

    return traces
  }, [forecastData, budgetData, consolidation, consolidatedData])

  // Today line for chart - only show if today falls within the selected period
  const todayLine = useMemo(() => {
    const todayStr = formatDate(new Date())
    // Don't show today line if period doesn't include today
    if (todayStr < startDate || todayStr > endDate) {
      return null
    }
    return {
      type: 'line' as const,
      x0: todayStr,
      x1: todayStr,
      y0: 0,
      y1: 1,
      yref: 'paper' as const,
      line: { color: '#f59e0b', width: 2, dash: 'dash' as const },
    }
  }, [startDate, endDate])

  // Calculate summary stats - split by actual (past) vs forecast (future)
  const summary = useMemo(() => {
    if (!forecastData?.data || forecastData.data.length === 0) return null

    const todayStr = formatDate(new Date())

    // Split data into past (actuals) and future (forecast)
    const pastDays = forecastData.data.filter(d => d.date < todayStr)
    const futureDays = forecastData.data.filter(d => d.date >= todayStr)

    // Actual to date (past days - use actual revenue from newbook_net_revenue_data)
    const actualTotal = pastDays.reduce((sum, d) => sum + (actualsMap[d.date] ?? 0), 0)
    const actualBudgetTotal = pastDays.reduce((sum, d) => sum + (budgetMap[d.date] || 0), 0)
    const actualPriorTotal = pastDays.reduce((sum, d) => sum + (d.prior_year_final_rev || 0), 0)

    // Future OTB (confirmed bookings)
    const futureOtbTotal = futureDays.reduce((sum, d) => sum + (d.current_otb_rev || 0), 0)

    // Pace = Actual + Future OTB
    const paceTotal = actualTotal + futureOtbTotal

    // Forecast remaining (future days - full forecast including pickup)
    const forecastRemainingTotal = futureDays.reduce((sum, d) => sum + (d.forecast || 0), 0)
    const forecastBudgetTotal = futureDays.reduce((sum, d) => sum + (budgetMap[d.date] || 0), 0)
    const forecastPriorTotal = futureDays.reduce((sum, d) => sum + (d.prior_year_final_rev || 0), 0)

    // Projected total = Actual + Forecast
    const projectedTotal = actualTotal + forecastRemainingTotal
    const totalBudget = actualBudgetTotal + forecastBudgetTotal
    const totalPriorYear = actualPriorTotal + forecastPriorTotal

    return {
      // Actual to date
      actualTotal,
      actualBudgetTotal,
      actualPriorTotal,
      actualVariance: actualTotal - actualBudgetTotal,
      daysActual: pastDays.length,
      // Pace (Actual + OTB)
      paceTotal,
      futureOtbTotal,
      // Forecast remaining
      forecastRemainingTotal,
      forecastBudgetTotal,
      forecastPriorTotal,
      forecastVariance: forecastRemainingTotal - forecastBudgetTotal,
      daysForecast: futureDays.length,
      // Projected total
      projectedTotal,
      totalBudget,
      totalPriorYear,
      budgetVariance: projectedTotal - totalBudget,
      budgetVariancePct: totalBudget > 0 ? ((projectedTotal / totalBudget) - 1) * 100 : 0,
      priorYearVariance: projectedTotal - totalPriorYear,
      priorYearVariancePct: totalPriorYear > 0 ? ((projectedTotal / totalPriorYear) - 1) * 100 : 0,
      daysCount: forecastData.data.length
    }
  }, [forecastData, budgetMap, actualsMap])

  const viewLabel = consolidation === 'daily' ? 'Day' : consolidation === 'weekly' ? 'Week' : 'Month'

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Accommodation Revenue by {viewLabel}</h2>
          <p style={styles.hint}>
            Room-based pickup model using prior year patterns with current rate adjustments
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* From Selector - Week-based for weekly, Month-based for daily/monthly */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>From {consolidation === 'weekly' ? 'Week' : 'Month'}</label>
          {consolidation === 'weekly' ? (
            <select
              value={selectedWeek}
              onChange={(e) => { setSelectedWeek(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {weekOptions.map((week) => (
                <option key={week.value} value={week.value}>{week.label}</option>
              ))}
            </select>
          ) : (
            <select
              value={selectedMonth}
              onChange={(e) => { setSelectedMonth(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {monthOptions.map((month) => (
                <option key={month.value} value={month.value}>{month.label}</option>
              ))}
            </select>
          )}
        </div>

        {/* Duration Selector - Weeks for weekly, Months for daily/monthly */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Duration</label>
          {consolidation === 'weekly' ? (
            <select
              value={weekDuration}
              onChange={(e) => { setWeekDuration(e.target.value as '4' | '8' | '13' | '26'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="4">4 Weeks</option>
              <option value="8">8 Weeks</option>
              <option value="13">13 Weeks (~3 Months)</option>
              <option value="26">26 Weeks (~6 Months)</option>
            </select>
          ) : (
            <select
              value={duration}
              onChange={(e) => { setDuration(e.target.value as '1' | '3' | '6' | '12'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="1">1 Month</option>
              <option value="3">3 Months</option>
              <option value="6">6 Months</option>
              <option value="12">1 Year</option>
            </select>
          )}
        </div>

        {/* Period Display */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Period</label>
          <div style={{
            padding: `${spacing.sm} ${spacing.md}`,
            background: colors.surface,
            borderRadius: radius.md,
            fontSize: typography.sm,
            color: colors.text,
          }}>
            {startDate} to {endDate}
          </div>
        </div>

        {/* Custom Date Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Custom Range</label>
          <div style={{ display: 'flex', gap: spacing.xs, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={useCustomDates}
              onChange={(e) => {
                setUseCustomDates(e.target.checked)
                if (e.target.checked && !customStartDate) {
                  setCustomStartDate(startDate)
                  setCustomEndDate(endDate)
                }
              }}
            />
            {useCustomDates && (
              <>
                <input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
                <span>to</span>
                <input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
              </>
            )}
          </div>
        </div>
      </div>

      {/* Summary Stats - 4 blocks matching MetricForecast */}
      {summary && (
        <div style={styles.summaryGrid}>
          {/* Actual to Date */}
          <div style={styles.summaryCard}>
            <span style={styles.summaryLabel}>ACTUAL TO DATE ({summary.daysActual} days)</span>
            {(() => {
              const actualBudgetPct = summary.actualBudgetTotal > 0
                ? ((summary.actualTotal / summary.actualBudgetTotal) - 1) * 100
                : 0
              const actualPriorPct = summary.actualPriorTotal > 0
                ? ((summary.actualTotal / summary.actualPriorTotal) - 1) * 100
                : 0
              const hasBudget = summary.actualBudgetTotal > 0
              return (
                <>
                  <span style={{
                    ...styles.summaryValue,
                    color: hasBudget ? (summary.actualVariance >= 0 ? colors.success : colors.error) : colors.text,
                  }}>
                    £{summary.actualTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    {hasBudget && (
                      <span style={{ fontSize: typography.base, marginLeft: spacing.sm }}>
                        {actualBudgetPct >= 0 ? '+' : ''}{actualBudgetPct.toFixed(1)}%
                      </span>
                    )}
                  </span>
                  {hasBudget ? (
                    <span style={{
                      ...styles.summarySubtext,
                      color: summary.actualVariance >= 0 ? colors.success : colors.error,
                    }}>
                      vs Budget: £{summary.actualBudgetTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      {' '}({summary.actualVariance >= 0 ? '+' : ''}£{summary.actualVariance.toLocaleString(undefined, { maximumFractionDigits: 0 })})
                    </span>
                  ) : (
                    <span style={styles.summarySubtext}>vs Budget: N/A</span>
                  )}
                  <span style={{
                    ...styles.summarySubtext,
                    color: actualPriorPct >= 0 ? colors.success : colors.error,
                  }}>
                    vs Last Year: £{summary.actualPriorTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    {' '}({actualPriorPct >= 0 ? '+' : ''}{actualPriorPct.toFixed(1)}%)
                  </span>
                </>
              )
            })()}
          </div>

          {/* OTB Pace (Actual + OTB) */}
          <div style={styles.summaryCard}>
            <span style={styles.summaryLabel}>OTB PACE</span>
            {(() => {
              const hasBudget = summary.totalBudget > 0
              const paceVariance = summary.paceTotal - summary.totalBudget
              const paceVariancePct = hasBudget
                ? ((summary.paceTotal / summary.totalBudget) - 1) * 100
                : 0
              const pacePriorPct = summary.totalPriorYear > 0
                ? ((summary.paceTotal / summary.totalPriorYear) - 1) * 100
                : 0
              return (
                <>
                  <span style={{ ...styles.summaryValue, color: '#9333ea' }}>
                    £{summary.paceTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                  {hasBudget ? (
                    <span style={{
                      ...styles.summarySubtext,
                      color: paceVariance >= 0 ? colors.success : colors.error,
                    }}>
                      vs Budget: £{summary.totalBudget.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      {' '}({paceVariancePct >= 0 ? '+' : ''}{paceVariancePct.toFixed(1)}%)
                    </span>
                  ) : (
                    <span style={styles.summarySubtext}>vs Budget: N/A</span>
                  )}
                  <span style={{
                    ...styles.summarySubtext,
                    color: pacePriorPct >= 0 ? colors.success : colors.error,
                  }}>
                    vs Last Year: £{summary.totalPriorYear.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    {' '}({pacePriorPct >= 0 ? '+' : ''}{pacePriorPct.toFixed(1)}%)
                  </span>
                </>
              )
            })()}
          </div>

          {/* Forecast Remaining */}
          <div style={styles.summaryCard}>
            <span style={styles.summaryLabel}>FORECAST REMAINING ({summary.daysForecast} days)</span>
            {(() => {
              // Remaining budget = total budget - actuals achieved (tracks progress toward meeting budget)
              // If actuals are ahead, less remaining budget needed; if behind, more needed
              const hasActuals = summary.daysActual > 0
              const remainingBudgetNeeded = hasActuals
                ? Math.max(0, summary.totalBudget - summary.actualTotal)
                : summary.forecastBudgetTotal
              const hasBudget = remainingBudgetNeeded > 0 || summary.totalBudget > 0
              const forecastVariance = summary.forecastRemainingTotal - remainingBudgetNeeded
              const forecastVariancePct = remainingBudgetNeeded > 0
                ? ((summary.forecastRemainingTotal / remainingBudgetNeeded) - 1) * 100
                : 0
              const forecastPriorPct = summary.forecastPriorTotal > 0
                ? ((summary.forecastRemainingTotal / summary.forecastPriorTotal) - 1) * 100
                : 0
              return (
                <>
                  <span style={{ ...styles.summaryValue, color: CHART_COLORS.blended }}>
                    £{summary.forecastRemainingTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                  {hasBudget ? (
                    <span style={{
                      ...styles.summarySubtext,
                      color: forecastVariance >= 0 ? colors.success : colors.error,
                    }}>
                      {hasActuals ? 'Remaining Budget: ' : 'vs Budget: '}
                      £{remainingBudgetNeeded.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      {' '}({forecastVariancePct >= 0 ? '+' : ''}{forecastVariancePct.toFixed(1)}%)
                    </span>
                  ) : (
                    <span style={styles.summarySubtext}>vs Budget: N/A</span>
                  )}
                  <span style={{
                    ...styles.summarySubtext,
                    color: forecastPriorPct >= 0 ? colors.success : colors.error,
                  }}>
                    vs Last Year: £{summary.forecastPriorTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    {' '}({forecastPriorPct >= 0 ? '+' : ''}{forecastPriorPct.toFixed(1)}%)
                  </span>
                </>
              )
            })()}
          </div>

          {/* Projected Total */}
          <div style={styles.summaryCard}>
            <span style={styles.summaryLabel}>PROJECTED TOTAL</span>
            {(() => {
              const hasBudget = summary.totalBudget > 0
              return (
                <>
                  <span style={{
                    ...styles.summaryValue,
                    color: hasBudget ? (summary.budgetVariance >= 0 ? colors.success : colors.error) : colors.text,
                  }}>
                    £{summary.projectedTotal.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    {hasBudget && (
                      <span style={{ fontSize: typography.base, marginLeft: spacing.sm }}>
                        {summary.budgetVariance >= 0 ? '+' : ''}{summary.budgetVariancePct.toFixed(1)}%
                      </span>
                    )}
                  </span>
                  {hasBudget ? (
                    <span style={{
                      ...styles.summarySubtext,
                      color: summary.budgetVariance >= 0 ? colors.success : colors.error,
                    }}>
                      vs Budget: £{summary.totalBudget.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      {' '}({summary.budgetVariance >= 0 ? '+' : ''}£{summary.budgetVariance.toLocaleString(undefined, { maximumFractionDigits: 0 })})
                    </span>
                  ) : (
                    <span style={styles.summarySubtext}>vs Budget: N/A</span>
                  )}
                  <span style={{
                    ...styles.summarySubtext,
                    color: summary.priorYearVariance >= 0 ? colors.success : colors.error,
                  }}>
                    vs Last Year: £{summary.totalPriorYear.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    {' '}({summary.priorYearVariance >= 0 ? '+' : ''}{summary.priorYearVariancePct.toFixed(1)}%)
                  </span>
                </>
              )
            })()}
          </div>

          {/* Lost Potential - clickable to open pickup table */}
          {consolidation === 'daily' && (
            <div
              style={{
                ...styles.summaryCard,
                backgroundColor: (forecastData?.summary?.lost_potential_total || 0) > 0 ? '#fef3c7' : '#d1fae5',
                borderColor: (forecastData?.summary?.lost_potential_total || 0) > 0 ? '#f59e0b' : '#10b981',
                borderWidth: 2,
                cursor: 'pointer',
              }}
              onClick={() => {
                setShowPickupTable(true)
                setTimeout(() => {
                  pickupTableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                }, 100)
              }}
              title="Click to view Pickup/Rate data"
            >
              {(forecastData?.summary?.lost_potential_total || 0) > 0 ? (
                <>
                  <span style={{ ...styles.summaryLabel, color: '#92400e' }}>LOST POTENTIAL</span>
                  <span style={{ ...styles.summaryValue, color: '#b45309' }}>
                    £{(forecastData?.summary?.lost_potential_total || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: '#92400e' }}>
                    {forecastData?.summary?.opportunity_days_count || 0} days with rate gaps
                  </span>
                  <span style={{ fontSize: typography.xs, color: '#78716c', marginTop: spacing.xs }}>
                    Click to view details →
                  </span>
                </>
              ) : (
                <>
                  <span style={{ ...styles.summaryLabel, color: '#047857' }}>RATE PERFORMANCE</span>
                  <span style={{ ...styles.summaryValue, color: '#059669' }}>On Track</span>
                  <span style={{ ...styles.summarySubtext, color: '#047857' }}>
                    No significant rate gaps
                  </span>
                  <span style={{ fontSize: typography.xs, color: '#78716c', marginTop: spacing.xs }}>
                    Click to view details →
                  </span>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Chart */}
      {isLoading ? (
        <div style={styles.loadingContainer}>Loading forecast...</div>
      ) : chartData.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={chartData}
            layout={{
              height: 350,
              margin: { l: 60, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              barmode: consolidation !== 'daily' ? 'stack' as const : undefined,
              xaxis: {
                title: { text: consolidation === 'daily' ? 'Date' : viewLabel },
                tickangle: -45,
                tickfont: { size: 10 },
                gridcolor: colors.border,
                zerolinecolor: colors.border,
                range: consolidation === 'daily' ? [startDate, endDate] : undefined,
              },
              yaxis: {
                title: { text: 'Revenue (£)' },
                rangemode: 'tozero' as const,
                gridcolor: colors.border,
                zerolinecolor: colors.border,
                tickformat: ',.0f',
                tickprefix: '£',
              },
              legend: { orientation: 'h' as const, y: -0.25, x: 0.5, xanchor: 'center' as const },
              hovermode: 'x unified' as const,
              shapes: consolidation === 'daily' && todayLine ? [todayLine] : [],
              annotations: consolidation === 'daily' && todayLine ? [{
                x: formatDate(new Date()),
                y: 1,
                yref: 'paper' as const,
                text: 'Today',
                showarrow: false,
                font: { color: '#f59e0b', size: 10 },
                yanchor: 'bottom' as const,
              }] : [],
            }}
            style={{ width: '100%', height: '100%' }}
            config={{ responsive: true, displayModeBar: false }}
          />
        </div>
      ) : null}

      {/* Budget/Forecast Table Toggle */}
      <button onClick={() => setShowTable(!showTable)} style={styles.dataTableToggle}>
        {showTable ? '▼ Hide Budget/Forecast Table' : '▶ Show Budget/Forecast Table'}
      </button>

      {/* Daily Budget/Forecast Table */}
      {showTable && consolidation === 'daily' && forecastData?.data && forecastData.data.length > 0 && (
        <div style={styles.tableContainer}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Date</th>
                <th style={{ ...styles.th, color: CHART_COLORS.futureOtb }}>OTB</th>
                <th style={{ ...styles.th, color: CHART_COLORS.blended }}>Forecast</th>
                <th style={styles.th}>Prior Year</th>
                <th style={styles.th}>vs Prior</th>
                <th style={styles.th}>Budget</th>
                <th style={styles.th}>vs Budget</th>
              </tr>
            </thead>
            <tbody>
              {(() => {
                const todayStr = formatDate(new Date())
                return forecastData.data.map((row) => {
                  const isPast = row.date < todayStr
                  const actualValue = actualsMap[row.date]
                  // For display: past dates use actual, future dates use forecast
                  const displayValue = isPast ? (actualValue ?? row.forecast) : row.forecast
                  const diff = (displayValue || 0) - (row.prior_year_final_rev || 0)
                  const budget = budgetMap[row.date] || 0
                  const budgetDiff = (displayValue || 0) - budget
                  // Short day name from day_of_week (e.g., "Monday" -> "Mon")
                  const shortDay = row.day_of_week?.substring(0, 3) || ''
                  return (
                    <tr key={row.date}>
                      <td style={styles.td}>{row.date} {shortDay}</td>
                      <td style={{ ...styles.td, color: CHART_COLORS.futureOtb }}>
                        £{row.current_otb_rev?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? '-'}
                      </td>
                      <td style={{
                        ...styles.td,
                        fontWeight: isPast ? 600 : 400,
                        fontStyle: isPast ? 'normal' : 'italic',
                        color: isPast ? colors.success : CHART_COLORS.blended,
                      }}>
                        £{displayValue?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? '-'}
                      </td>
                      <td style={styles.td}>£{row.prior_year_final_rev?.toLocaleString(undefined, { maximumFractionDigits: 0 }) ?? '-'}</td>
                      <td style={{ ...styles.td, color: diff >= 0 ? colors.success : colors.error }}>
                        {diff >= 0 ? '+' : ''}£{diff.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </td>
                      <td style={styles.td}>{budget > 0 ? `£${budget.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-'}</td>
                      <td style={{ ...styles.td, color: budgetDiff >= 0 ? colors.success : colors.error }}>
                        {budget > 0 ? `${budgetDiff >= 0 ? '+' : ''}£${budgetDiff.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-'}
                      </td>
                    </tr>
                  )
                })
              })()}
            </tbody>
          </table>
        </div>
      )}

      {/* Weekly/Monthly Table */}
      {showTable && consolidation !== 'daily' && consolidatedData && consolidatedData.length > 0 && (
        <div style={styles.tableContainer}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>{viewLabel}</th>
                <th style={styles.th}>Days</th>
                <th style={{ ...styles.th, color: colors.success }}>Actual</th>
                <th style={{ ...styles.th, color: CHART_COLORS.futureOtb }}>Future OTB</th>
                <th style={{ ...styles.th, color: CHART_COLORS.blended }}>Forecast</th>
                <th style={{ ...styles.th, fontWeight: 600 }}>Projected</th>
                <th style={styles.th}>Prior Year</th>
                <th style={styles.th}>vs Prior</th>
                <th style={styles.th}>Budget</th>
                <th style={styles.th}>vs Budget</th>
              </tr>
            </thead>
            <tbody>
              {consolidatedData.map((row) => (
                <tr key={row.key}>
                  <td style={styles.td}>{row.label}</td>
                  <td style={styles.td}>
                    {row.pastDays > 0 && row.futureDays > 0
                      ? `${row.pastDays}+${row.futureDays}`
                      : row.days}
                  </td>
                  <td style={{ ...styles.td, color: colors.success, fontWeight: row.pastDays > 0 ? 600 : 400 }}>
                    {row.actual > 0 ? `£${row.actual.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-'}
                  </td>
                  <td style={{ ...styles.td, color: CHART_COLORS.futureOtb }}>
                    {row.futureDays > 0 ? `£${row.otb.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-'}
                  </td>
                  <td style={{ ...styles.td, fontStyle: 'italic', color: CHART_COLORS.blended }}>
                    {row.forecastRemaining > 0 ? `£${row.forecastRemaining.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-'}
                  </td>
                  <td style={{ ...styles.td, fontWeight: 600 }}>
                    £{row.projected.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </td>
                  <td style={styles.td}>£{row.priorYear.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                  <td style={{ ...styles.td, color: row.variance >= 0 ? colors.success : colors.error }}>
                    {row.variance >= 0 ? '+' : ''}{row.variancePct.toFixed(1)}%
                  </td>
                  <td style={styles.td}>{row.budget > 0 ? `£${row.budget.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '-'}</td>
                  <td style={{ ...styles.td, color: row.budgetVariance >= 0 ? colors.success : colors.error }}>
                    {row.budget > 0 ? `${row.budgetVariance >= 0 ? '+' : ''}${row.budgetVariancePct.toFixed(1)}%` : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pickup/Rate Data Table Toggle - Daily only */}
      {consolidation === 'daily' && (
        <button onClick={() => setShowPickupTable(!showPickupTable)} style={styles.dataTableToggle}>
          {showPickupTable ? '▼ Hide Pickup/Rate Data' : '▶ Show Pickup/Rate Data'}
        </button>
      )}

      {/* Pickup/Rate Data Table */}
      {showPickupTable && consolidation === 'daily' && forecastData?.data && forecastData.data.length > 0 && (
        <div ref={pickupTableRef} style={{ ...styles.tableContainer, overflowX: 'auto' }}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Date</th>
                <th style={styles.th}>OTB Rms</th>
                <th style={styles.th}>Pickup Rms</th>
                <th style={styles.th}>Fcst Rms</th>
                <th style={{ ...styles.th, color: CHART_COLORS.futureOtb }}>OTB Rev</th>
                <th style={styles.th}>Pickup Calc</th>
                <th style={{ ...styles.th, fontWeight: 600, color: CHART_COLORS.blended }}>Forecast</th>
                <th style={styles.th}>LY OTB</th>
                <th style={styles.th}>Pace</th>
                <th style={styles.th}>LY Final</th>
                <th style={styles.th}>vs Final</th>
                <th style={{ ...styles.th, backgroundColor: '#fef3c7', color: '#92400e' }}>Curr Rate</th>
                <th style={{ ...styles.th, backgroundColor: '#fef3c7', color: '#92400e' }}>LY Rate</th>
                <th style={{ ...styles.th, backgroundColor: '#fef3c7', color: '#92400e' }}>Lost £</th>
                <th style={{ ...styles.th, backgroundColor: '#fef3c7', color: '#92400e' }}>Rate Gap</th>
              </tr>
            </thead>
            <tbody>
              {forecastData.data.map((row) => {
                const hasOpportunity = row.has_pricing_opportunity === true
                const rowStyle = hasOpportunity ? { backgroundColor: '#fef9e7' } : {}
                const pickupRooms = row.pickup_rooms_total || 0
                const otbRooms = row.current_otb || 0
                const forecastRooms = otbRooms + pickupRooms
                const priorOtbRev = row.prior_year_otb_rev || 0
                const priorFinalRev = row.prior_year_final_rev || 0
                const otbPacePct = priorOtbRev > 0 ? ((row.current_otb_rev || 0) - priorOtbRev) / priorOtbRev * 100 : 0
                const finalPacePct = priorFinalRev > 0 ? (row.forecast - priorFinalRev) / priorFinalRev * 100 : 0
                const shortDay = row.day_of_week?.substring(0, 3) || ''

                // Build tooltip for category breakdown with category names
                const categoryBreakdown = row.category_breakdown || {}
                const pickupTooltip = Object.entries(categoryBreakdown)
                  .filter(([_, data]: [string, any]) => data.pickup_rooms > 0)
                  .map(([catId, data]: [string, any]) => {
                    const catName = categoryNameMap[catId] || `Category ${catId}`
                    return `${catName}: ${data.pickup_rooms} rooms`
                  })
                  .join('\n') || 'No pickup expected'

                const pickupCalcTooltip = Object.entries(categoryBreakdown)
                  .filter(([_, data]: [string, any]) => data.pickup_rooms > 0)
                  .map(([catId, data]: [string, any]) => {
                    const catName = categoryNameMap[catId] || `Category ${catId}`
                    const netRate = data.prior_avg_rate?.toFixed(0) || '0'
                    const grossRate = data.prior_avg_rate_gross?.toFixed(0) || '0'
                    const pickupRev = data.forecast_pickup_rev?.toFixed(0) || '0'
                    return `${catName}: ${data.pickup_rooms} × £${netRate} (£${grossRate}) = £${pickupRev}`
                  })
                  .join('\n') || 'No pickup expected for this date'

                // Get effective rate with gross for display
                const effectiveNet = row.effective_rate?.toFixed(0) || row.weighted_avg_prior_rate?.toFixed(0) || '0'
                const effectiveGross = row.effective_rate_gross?.toFixed(0) || row.weighted_avg_prior_rate_gross?.toFixed(0) || '0'

                return (
                  <tr key={row.date} style={rowStyle}>
                    <td style={styles.td}>{row.date} {shortDay}</td>
                    <td style={styles.td}>{Math.round(otbRooms)}</td>
                    <td style={{ ...styles.td, cursor: 'help' }} title={pickupTooltip}>{pickupRooms}</td>
                    <td style={styles.td}>{Math.round(forecastRooms)}</td>
                    <td style={{ ...styles.td, color: CHART_COLORS.futureOtb }}>
                      £{(row.current_otb_rev || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td
                      style={{
                        ...styles.td,
                        fontSize: '0.85em',
                        cursor: 'help',
                        color: row.effective_rate && row.weighted_avg_prior_rate && row.effective_rate < row.weighted_avg_prior_rate
                          ? '#dc2626'
                          : '#6b7280'
                      }}
                      title={pickupCalcTooltip}
                    >
                      {pickupRooms} × £{effectiveNet} <span style={{ color: '#6b7280' }}>(£{effectiveGross})</span>
                      {row.effective_rate && row.weighted_avg_prior_rate && row.effective_rate < row.weighted_avg_prior_rate && (
                        <span title="Capped at current rate"> *</span>
                      )}
                    </td>
                    <td style={{ ...styles.td, fontWeight: 600, color: CHART_COLORS.blended }}>
                      £{row.forecast.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td style={styles.td}>
                      £{priorOtbRev.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td style={{ ...styles.td, color: otbPacePct >= 0 ? '#10b981' : '#ef4444' }}>
                      {otbPacePct >= 0 ? '+' : ''}{otbPacePct.toFixed(0)}%
                    </td>
                    <td style={styles.td}>
                      £{priorFinalRev.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td style={{ ...styles.td, color: finalPacePct >= 0 ? '#10b981' : '#ef4444' }}>
                      {finalPacePct >= 0 ? '+' : ''}{finalPacePct.toFixed(0)}%
                    </td>
                    <td style={{ ...styles.td, backgroundColor: hasOpportunity ? '#fef3c7' : 'transparent' }}>
                      {row.weighted_avg_current_rate
                        ? <>£{row.weighted_avg_current_rate.toFixed(0)} <span style={{ color: '#6b7280', fontSize: '0.85em' }}>(£{row.weighted_avg_current_rate_gross?.toFixed(0) || '-'})</span></>
                        : '-'}
                    </td>
                    <td style={{ ...styles.td, backgroundColor: hasOpportunity ? '#fef3c7' : 'transparent' }}>
                      {row.weighted_avg_listed_rate
                        ? <>£{row.weighted_avg_listed_rate.toFixed(0)} <span style={{ color: '#6b7280', fontSize: '0.85em' }}>(£{row.weighted_avg_listed_rate_gross?.toFixed(0) || '-'})</span></>
                        : '-'}
                    </td>
                    <td style={{
                      ...styles.td,
                      fontWeight: hasOpportunity ? 600 : 400,
                      color: hasOpportunity ? '#b45309' : '#6b7280',
                      backgroundColor: hasOpportunity ? '#fef3c7' : 'transparent',
                    }}>
                      {(row.lost_potential || 0) > 0
                        ? `£${(row.lost_potential || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                        : '-'}
                    </td>
                    <td style={{ ...styles.td, color: (row.rate_vs_prior_pct || 0) < 0 ? '#b45309' : '#10b981' }}>
                      {row.rate_vs_prior_pct !== null && row.rate_vs_prior_pct !== undefined
                        ? `${row.rate_vs_prior_pct >= 0 ? '+' : ''}${row.rate_vs_prior_pct.toFixed(1)}%`
                        : '-'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ============================================
// PICKUP-V2 BOOKINGS FORECAST COMPONENT (Room Nights)
// ============================================

interface PickupV2BookingsForecastProps {
  consolidation: 'daily' | 'weekly' | 'monthly'
}

const PickupV2BookingsForecast: React.FC<PickupV2BookingsForecastProps> = ({ consolidation }) => {
  const token = localStorage.getItem('token')

  // Helper: get Monday of the week containing a date
  const getMondayOfWeek = (date: Date): Date => {
    const d = new Date(date)
    const day = d.getDay()
    const diff = day === 0 ? -6 : 1 - day
    d.setDate(d.getDate() + diff)
    d.setHours(0, 0, 0, 0)
    return d
  }

  // Helper: get ISO week number
  const getISOWeekNumber = (date: Date): number => {
    const d = new Date(date)
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() + 4 - (d.getDay() || 7))
    const yearStart = new Date(d.getFullYear(), 0, 1)
    return Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  }

  // Helper: get financial year start (August)
  const getFinancialYearStart = (date: Date): string => {
    const year = date.getFullYear()
    const month = date.getMonth()
    const fyStartYear = month >= 7 ? year : year - 1
    return `${fyStartYear}-08`
  }

  const today = new Date()
  const currentMonday = getMondayOfWeek(today)

  const [selectedMonth, setSelectedMonth] = useState(() => {
    if (consolidation === 'monthly') {
      return getFinancialYearStart(today)
    }
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  })
  const [selectedWeek, setSelectedWeek] = useState(() => formatDate(currentMonday))
  const [duration, setDuration] = useState<'1' | '3' | '6' | '12'>(
    consolidation === 'monthly' ? '12' : consolidation === 'daily' ? '1' : '3'
  )
  const [weekDuration, setWeekDuration] = useState<'4' | '8' | '13' | '26'>('13')
  const [showTable, setShowTable] = useState(true)
  const [useCustomDates, setUseCustomDates] = useState(false)
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')

  // Generate month options
  const monthOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const now = new Date()
    for (let i = -24; i <= 12; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() + i, 1)
      const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      const label = date.toLocaleString('default', { month: 'short', year: 'numeric' })
      options.push({ value, label })
    }
    return options
  }, [])

  // Generate week options
  const weekOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const now = new Date()
    const currentMon = getMondayOfWeek(now)

    for (let i = -52; i <= 26; i++) {
      const monday = new Date(currentMon)
      monday.setDate(currentMon.getDate() + (i * 7))
      const sunday = new Date(monday)
      sunday.setDate(monday.getDate() + 6)

      const weekNum = getISOWeekNumber(monday)
      const value = formatDate(monday)
      const label = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })})`
      options.push({ value, label })
    }
    return options
  }, [])

  // Calculate start and end dates
  const { startDate, endDate } = useMemo(() => {
    if (useCustomDates && customStartDate && customEndDate) {
      return { startDate: customStartDate, endDate: customEndDate }
    }

    if (consolidation === 'weekly') {
      const start = new Date(selectedWeek)
      const durationWeeks = parseInt(weekDuration)
      const end = new Date(start)
      end.setDate(start.getDate() + (durationWeeks * 7) - 1)
      return { startDate: formatDate(start), endDate: formatDate(end) }
    } else {
      const [year, month] = selectedMonth.split('-').map(Number)
      const start = new Date(year, month - 1, 1)
      const durationMonths = parseInt(duration)
      const end = new Date(year, month - 1 + durationMonths, 0)
      return { startDate: formatDate(start), endDate: formatDate(end) }
    }
  }, [selectedMonth, selectedWeek, duration, weekDuration, consolidation, useCustomDates, customStartDate, customEndDate])

  // Fetch Pickup-V2 forecast with rooms metric
  const { data: forecastData, isLoading } = useQuery<PickupV2Response>({
    queryKey: ['pickup-v2-bookings', startDate, endDate],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric: 'rooms' })
      const response = await fetch(`/api/forecast/pickup-v2-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Consolidate data for weekly/monthly views
  const consolidatedData = useMemo(() => {
    if (!forecastData?.data || consolidation === 'daily') return null

    const todayStr = formatDate(new Date())
    const groups: Record<string, {
      label: string
      startDate: string
      otbRooms: number
      futureOtbRooms: number
      forecastRooms: number
      actualRooms: number
      forecastRemainingRooms: number
      priorYearFinal: number
      priorYearOtb: number
      priorActualRooms: number
      priorForecastRooms: number
      days: number
      pastDays: number
      futureDays: number
    }> = {}

    forecastData.data.forEach(d => {
      const dateObj = new Date(d.date)
      let groupKey: string
      let groupLabel: string

      if (consolidation === 'weekly') {
        const dayOfWeek = dateObj.getDay()
        const monday = new Date(dateObj)
        monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
        const sunday = new Date(monday)
        sunday.setDate(monday.getDate() + 6)
        groupKey = formatDate(monday)
        const weekD = new Date(monday)
        weekD.setDate(weekD.getDate() + 4 - (weekD.getDay() || 7))
        const yearStart = new Date(weekD.getFullYear(), 0, 1)
        const weekNum = Math.ceil((((weekD.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
        groupLabel = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })})`
      } else {
        groupKey = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}`
        groupLabel = dateObj.toLocaleString('default', { month: 'short', year: 'numeric' })
      }

      if (!groups[groupKey]) {
        groups[groupKey] = {
          label: groupLabel,
          startDate: d.date,
          otbRooms: 0,
          futureOtbRooms: 0,
          forecastRooms: 0,
          actualRooms: 0,
          forecastRemainingRooms: 0,
          priorYearFinal: 0,
          priorYearOtb: 0,
          priorActualRooms: 0,
          priorForecastRooms: 0,
          days: 0,
          pastDays: 0,
          futureDays: 0
        }
      }

      const isPast = d.date < todayStr
      const otb = d.current_otb || 0
      const forecast = (d.current_otb || 0) + (d.pickup_rooms_total || 0)  // OTB + pickup = total forecast rooms
      const priorFinal = d.prior_year_final || 0
      const priorOtb = d.prior_year_otb || 0

      groups[groupKey].otbRooms += otb
      groups[groupKey].forecastRooms += forecast
      groups[groupKey].priorYearFinal += priorFinal
      groups[groupKey].days++

      if (isPast) {
        // For past days, actual = OTB (what actually happened)
        groups[groupKey].actualRooms += otb
        groups[groupKey].priorActualRooms += priorFinal  // Prior year final for same past days
        groups[groupKey].pastDays++
      } else {
        groups[groupKey].futureOtbRooms += otb
        groups[groupKey].forecastRemainingRooms += forecast
        groups[groupKey].priorYearOtb += priorOtb  // Prior year OTB for future days
        groups[groupKey].priorForecastRooms += priorFinal  // Prior year final for future days
        groups[groupKey].futureDays++
      }
    })

    return Object.entries(groups)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, data]) => {
        const projected = data.actualRooms + data.forecastRemainingRooms
        return {
          key,
          ...data,
          projected,
          variance: projected - data.priorYearFinal,
          variancePct: data.priorYearFinal > 0 ? ((projected / data.priorYearFinal) - 1) * 100 : 0
        }
      })
  }, [forecastData, consolidation])

  // Build chart data
  const chartData = useMemo(() => {
    if (consolidation !== 'daily' && consolidatedData) {
      const labels = consolidatedData.map(d => d.label)
      const actuals = consolidatedData.map(d => d.actualRooms)
      const futureOtb = consolidatedData.map(d => d.futureOtbRooms)
      const pickupPortion = consolidatedData.map((d) => {
        if (d.futureDays === 0) return 0
        return Math.max(0, d.forecastRemainingRooms - d.futureOtbRooms)
      })
      const priorYear = consolidatedData.map(d => d.priorYearFinal)

      const traces: any[] = [
        {
          x: labels,
          y: actuals,
          type: 'bar' as const,
          name: 'Actual',
          marker: { color: colors.success },
          hovertemplate: `Actual: %{y:,.0f} rooms<extra></extra>`,
        },
        {
          x: labels,
          y: futureOtb,
          type: 'bar' as const,
          name: 'OTB (Booked)',
          marker: { color: CHART_COLORS.futureOtb },
          hovertemplate: `OTB: %{y:,.0f} rooms<extra></extra>`,
        },
        {
          x: labels,
          y: pickupPortion,
          type: 'bar' as const,
          name: 'Forecast (Pickup)',
          marker: { color: CHART_COLORS.blended },
          hovertemplate: `Forecast: %{y:,.0f} rooms<extra></extra>`,
        },
        {
          x: labels,
          y: priorYear,
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Prior Year',
          line: { color: CHART_COLORS.priorFinal, width: 2, dash: 'dot' as const },
          marker: { size: 6 },
          hovertemplate: `Prior Year: %{y:,.0f} rooms<extra></extra>`,
        },
      ]

      return traces
    }

    // Daily view
    if (!forecastData?.data) return []

    const todayStr = formatDate(new Date())
    const dates = forecastData.data.map(d => d.date)
    const priorFinal = forecastData.data.map(d => d.prior_year_final)

    // Split into actuals and future
    const actualDates: string[] = []
    const actualValues: (number | null)[] = []
    const futureOtbDates: string[] = []
    const futureOtbValues: (number | null)[] = []
    const forecastDates: string[] = []
    const forecastValues: (number | null)[] = []

    forecastData.data.forEach(d => {
      const otb = d.current_otb || 0
      const pickup = d.pickup_rooms_total || 0
      const forecast = otb + pickup

      if (d.date < todayStr) {
        actualDates.push(d.date)
        actualValues.push(otb)  // For past days, OTB = actual bookings
      } else {
        futureOtbDates.push(d.date)
        futureOtbValues.push(otb)
        forecastDates.push(d.date)
        forecastValues.push(forecast)
      }
    })

    const traces: any[] = [
      {
        x: dates,
        y: priorFinal,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Prior Year Final',
        fill: 'tozeroy' as const,
        fillcolor: CHART_COLORS.priorFinalFill,
        line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
      },
    ]

    if (actualDates.length > 0) {
      traces.push({
        x: actualDates,
        y: actualValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Actual',
        line: { color: colors.success, width: 3 },
        marker: { size: 6 },
      })
    }

    if (futureOtbDates.length > 0) {
      traces.push({
        x: futureOtbDates,
        y: futureOtbValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'OTB (Booked)',
        line: { color: CHART_COLORS.futureOtb, width: 2 },
        marker: { size: 5 },
        fill: 'tozeroy' as const,
        fillcolor: 'rgba(6, 182, 212, 0.2)',
      })
    }

    if (forecastDates.length > 0) {
      traces.push({
        x: forecastDates,
        y: forecastValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Forecast',
        line: { color: CHART_COLORS.blended, width: 3 },
        marker: { size: 6 },
      })
    }

    return traces
  }, [forecastData, consolidation, consolidatedData])

  // Summary stats
  const summary = useMemo(() => {
    if (!forecastData?.data || forecastData.data.length === 0) return null

    const todayStr = formatDate(new Date())
    const pastDays = forecastData.data.filter(d => d.date < todayStr)
    const futureDays = forecastData.data.filter(d => d.date >= todayStr)

    // Actual = OTB for past days (what actually happened)
    const actualTotal = pastDays.reduce((sum, d) => sum + (d.current_otb || 0), 0)
    // Prior year final for same past days
    const priorActualTotal = pastDays.reduce((sum, d) => sum + (d.prior_year_final || 0), 0)

    // Future OTB
    const futureOtbTotal = futureDays.reduce((sum, d) => sum + (d.current_otb || 0), 0)
    // Prior year OTB from today's perspective (for same future days)
    const priorOtbTotal = futureDays.reduce((sum, d) => sum + (d.prior_year_otb || 0), 0)

    // Forecast remaining = OTB + pickup for future days
    const forecastRemainingTotal = futureDays.reduce((sum, d) => sum + (d.current_otb || 0) + (d.pickup_rooms_total || 0), 0)
    // Prior year final for future days
    const priorForecastTotal = futureDays.reduce((sum, d) => sum + (d.prior_year_final || 0), 0)

    // Prior year total for full period
    const priorYearTotal = forecastData.data.reduce((sum, d) => sum + (d.prior_year_final || 0), 0)

    // OTB Pace = actual past + OTB future
    const otbPace = actualTotal + futureOtbTotal
    // Prior OTB pace = prior actual for past + prior OTB for future
    const priorOtbPace = priorActualTotal + priorOtbTotal

    // Projected total = actual + forecast remaining
    const projectedTotal = actualTotal + forecastRemainingTotal

    return {
      actualTotal,
      priorActualTotal,
      futureOtbTotal,
      priorOtbTotal,
      otbPace,
      priorOtbPace,
      forecastRemainingTotal,
      priorForecastTotal,
      projectedTotal,
      priorYearTotal,
      daysActual: pastDays.length,
      daysForecast: futureDays.length,
    }
  }, [forecastData])

  const viewLabel = consolidation === 'daily' ? 'Day' : consolidation === 'weekly' ? 'Week' : 'Month'

  // Today line for daily view
  const todayLine = useMemo(() => {
    const todayStr = formatDate(new Date())
    if (todayStr < startDate || todayStr > endDate) return null
    return {
      type: 'line' as const,
      x0: todayStr, x1: todayStr, y0: 0, y1: 1,
      yref: 'paper' as const,
      line: { color: '#f59e0b', width: 2, dash: 'dash' as const },
    }
  }, [startDate, endDate])

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Room Nights by {viewLabel}</h2>
          <p style={styles.hint}>
            Room-based pickup model showing booking counts
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.label}>From {consolidation === 'weekly' ? 'Week' : 'Month'}</label>
          {consolidation === 'weekly' ? (
            <select
              value={selectedWeek}
              onChange={(e) => { setSelectedWeek(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {weekOptions.map((week) => (
                <option key={week.value} value={week.value}>{week.label}</option>
              ))}
            </select>
          ) : (
            <select
              value={selectedMonth}
              onChange={(e) => { setSelectedMonth(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {monthOptions.map((month) => (
                <option key={month.value} value={month.value}>{month.label}</option>
              ))}
            </select>
          )}
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.label}>Duration</label>
          {consolidation === 'weekly' ? (
            <select
              value={weekDuration}
              onChange={(e) => { setWeekDuration(e.target.value as '4' | '8' | '13' | '26'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="4">4 Weeks</option>
              <option value="8">8 Weeks</option>
              <option value="13">13 Weeks (~3 Months)</option>
              <option value="26">26 Weeks (~6 Months)</option>
            </select>
          ) : (
            <select
              value={duration}
              onChange={(e) => { setDuration(e.target.value as '1' | '3' | '6' | '12'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="1">1 Month</option>
              <option value="3">3 Months</option>
              <option value="6">6 Months</option>
              <option value="12">1 Year</option>
            </select>
          )}
        </div>

        {/* Custom Date Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Custom Range</label>
          <div style={{ display: 'flex', gap: spacing.xs, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={useCustomDates}
              onChange={(e) => {
                setUseCustomDates(e.target.checked)
                if (e.target.checked && !customStartDate) {
                  setCustomStartDate(startDate)
                  setCustomEndDate(endDate)
                }
              }}
            />
            {useCustomDates && (
              <>
                <input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
                <span>to</span>
                <input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
              </>
            )}
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.label}>Period</label>
          <div style={{
            padding: `${spacing.sm} ${spacing.md}`,
            background: colors.surface,
            borderRadius: radius.md,
            fontSize: typography.sm,
            color: colors.text,
          }}>
            {startDate} to {endDate}
          </div>
        </div>
      </div>

      {/* Summary Blocks */}
      {summary && (() => {
        const actualDiff = summary.actualTotal - summary.priorActualTotal
        const actualPct = summary.priorActualTotal > 0 ? (actualDiff / summary.priorActualTotal) * 100 : 0

        const otbPaceDiff = summary.otbPace - summary.priorOtbPace
        const otbPacePct = summary.priorOtbPace > 0 ? (otbPaceDiff / summary.priorOtbPace) * 100 : 0
        const otbVsTotalDiff = summary.otbPace - summary.priorYearTotal
        const otbVsTotalPct = summary.priorYearTotal > 0 ? (otbVsTotalDiff / summary.priorYearTotal) * 100 : 0

        const forecastDiff = summary.forecastRemainingTotal - summary.priorForecastTotal
        const forecastPct = summary.priorForecastTotal > 0 ? (forecastDiff / summary.priorForecastTotal) * 100 : 0

        const projectedDiff = summary.projectedTotal - summary.priorYearTotal
        const projectedPct = summary.priorYearTotal > 0 ? (projectedDiff / summary.priorYearTotal) * 100 : 0

        return (
          <div style={styles.summaryGrid}>
            {/* Actual to Date */}
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>ACTUAL TO DATE ({summary.daysActual} days)</span>
              <span style={{ ...styles.summaryValue, color: colors.success }}>
                {summary.actualTotal.toLocaleString()}
              </span>
              <span style={{ ...styles.summarySubtext, color: actualDiff >= 0 ? colors.success : colors.error }}>
                vs LY: {summary.priorActualTotal.toLocaleString()} ({actualDiff >= 0 ? '+' : ''}{actualDiff.toLocaleString()}, {actualPct >= 0 ? '+' : ''}{actualPct.toFixed(1)}%)
              </span>
            </div>

            {/* OTB Pace */}
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>OTB PACE</span>
              <span style={{ ...styles.summaryValue, color: '#9333ea' }}>
                {summary.otbPace.toLocaleString()}
              </span>
              <span style={{ ...styles.summarySubtext, color: otbPaceDiff >= 0 ? colors.success : colors.error }}>
                vs LY OTB: {summary.priorOtbPace.toLocaleString()} ({otbPaceDiff >= 0 ? '+' : ''}{otbPaceDiff.toLocaleString()}, {otbPacePct >= 0 ? '+' : ''}{otbPacePct.toFixed(1)}%)
              </span>
              <span style={{ ...styles.summarySubtext, color: otbVsTotalDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                vs LY Total: {summary.priorYearTotal.toLocaleString()} ({otbVsTotalDiff >= 0 ? '+' : ''}{otbVsTotalDiff.toLocaleString()}, {otbVsTotalPct >= 0 ? '+' : ''}{otbVsTotalPct.toFixed(1)}%)
              </span>
            </div>

            {/* Forecast Remaining */}
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>FORECAST ({summary.daysForecast} days)</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.blended }}>
                {summary.forecastRemainingTotal.toLocaleString()}
              </span>
              <span style={{ ...styles.summarySubtext, color: forecastDiff >= 0 ? colors.success : colors.error }}>
                vs LY: {summary.priorForecastTotal.toLocaleString()} ({forecastDiff >= 0 ? '+' : ''}{forecastDiff.toLocaleString()}, {forecastPct >= 0 ? '+' : ''}{forecastPct.toFixed(1)}%)
              </span>
            </div>

            {/* Projected Total */}
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>PROJECTED TOTAL</span>
              <span style={{
                ...styles.summaryValue,
                color: projectedDiff >= 0 ? colors.success : colors.error,
              }}>
                {summary.projectedTotal.toLocaleString()}
              </span>
              <span style={{ ...styles.summarySubtext, color: projectedDiff >= 0 ? colors.success : colors.error }}>
                vs LY: {summary.priorYearTotal.toLocaleString()} ({projectedDiff >= 0 ? '+' : ''}{projectedDiff.toLocaleString()}, {projectedPct >= 0 ? '+' : ''}{projectedPct.toFixed(1)}%)
              </span>
            </div>
          </div>
        )
      })()}

      {/* Chart */}
      {isLoading ? (
        <div style={styles.loadingContainer}>Loading forecast...</div>
      ) : chartData.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={chartData}
            layout={{
              height: 350,
              margin: { l: 60, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              barmode: consolidation !== 'daily' ? 'stack' as const : undefined,
              xaxis: {
                title: { text: consolidation === 'daily' ? 'Date' : viewLabel },
                tickangle: -45,
                tickfont: { size: 10 },
                gridcolor: colors.border,
                zerolinecolor: colors.border,
                range: consolidation === 'daily' ? [startDate, endDate] : undefined,
              },
              yaxis: {
                title: { text: 'Room Nights' },
                rangemode: 'tozero' as const,
                gridcolor: colors.border,
                zerolinecolor: colors.border,
              },
              legend: { orientation: 'h' as const, y: -0.25, x: 0.5, xanchor: 'center' as const },
              hovermode: 'x unified' as const,
              shapes: consolidation === 'daily' && todayLine ? [todayLine] : [],
              annotations: consolidation === 'daily' && todayLine ? [{
                x: formatDate(new Date()),
                y: 1,
                yref: 'paper' as const,
                text: 'Today',
                showarrow: false,
                font: { color: '#f59e0b', size: 10 },
                yanchor: 'bottom' as const,
              }] : [],
            }}
            style={{ width: '100%', height: '100%' }}
            config={{ responsive: true, displayModeBar: false }}
          />
        </div>
      ) : null}

      {/* Table Toggle */}
      <button onClick={() => setShowTable(!showTable)} style={styles.dataTableToggle}>
        {showTable ? '▼ Hide Table' : '▶ Show Table'}
      </button>

      {/* Daily Table */}
      {showTable && consolidation === 'daily' && forecastData?.data && forecastData.data.length > 0 && (
        <div style={styles.tableContainer}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Date</th>
                <th style={{ ...styles.th, color: CHART_COLORS.futureOtb }}>OTB</th>
                <th style={styles.th}>Pickup</th>
                <th style={{ ...styles.th, color: CHART_COLORS.blended }}>Forecast</th>
                <th style={styles.th}>Prior Year</th>
                <th style={styles.th}>vs Prior</th>
              </tr>
            </thead>
            <tbody>
              {forecastData.data.map((row) => {
                const otb = row.current_otb || 0
                const pickup = row.pickup_rooms_total || 0
                const forecast = otb + pickup
                const priorFinal = row.prior_year_final || 0
                const diff = forecast - priorFinal
                const shortDay = row.day_of_week?.substring(0, 3) || ''
                return (
                  <tr key={row.date}>
                    <td style={styles.td}>{row.date} {shortDay}</td>
                    <td style={{ ...styles.td, color: CHART_COLORS.futureOtb }}>{otb}</td>
                    <td style={styles.td}>{pickup}</td>
                    <td style={{ ...styles.td, fontWeight: 600, color: CHART_COLORS.blended }}>{forecast}</td>
                    <td style={styles.td}>{priorFinal}</td>
                    <td style={{ ...styles.td, color: diff >= 0 ? colors.success : colors.error }}>
                      {diff >= 0 ? '+' : ''}{diff}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Weekly/Monthly Table */}
      {showTable && consolidation !== 'daily' && consolidatedData && consolidatedData.length > 0 && (
        <div style={styles.tableContainer}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>{viewLabel}</th>
                <th style={styles.th}>Days</th>
                <th style={{ ...styles.th, color: colors.success }}>Actual</th>
                <th style={{ ...styles.th, color: CHART_COLORS.futureOtb }}>Future OTB</th>
                <th style={{ ...styles.th, color: CHART_COLORS.blended }}>Forecast</th>
                <th style={{ ...styles.th, fontWeight: 600 }}>Projected</th>
                <th style={styles.th}>Prior Year</th>
                <th style={styles.th}>vs Prior</th>
              </tr>
            </thead>
            <tbody>
              {consolidatedData.map((row) => (
                <tr key={row.key}>
                  <td style={styles.td}>{row.label}</td>
                  <td style={styles.td}>
                    {row.pastDays > 0 && row.futureDays > 0 ? `${row.pastDays}+${row.futureDays}` : row.days}
                  </td>
                  <td style={{ ...styles.td, color: colors.success, fontWeight: row.pastDays > 0 ? 600 : 400 }}>
                    {row.actualRooms > 0 ? row.actualRooms : '-'}
                  </td>
                  <td style={{ ...styles.td, color: CHART_COLORS.futureOtb }}>
                    {row.futureDays > 0 ? row.futureOtbRooms : '-'}
                  </td>
                  <td style={{ ...styles.td, fontStyle: 'italic', color: CHART_COLORS.blended }}>
                    {row.forecastRemainingRooms > 0 ? row.forecastRemainingRooms : '-'}
                  </td>
                  <td style={{ ...styles.td, fontWeight: 600 }}>{row.projected}</td>
                  <td style={styles.td}>{row.priorYearFinal}</td>
                  <td style={{ ...styles.td, color: row.variance >= 0 ? colors.success : colors.error }}>
                    {row.variance >= 0 ? '+' : ''}{row.variancePct.toFixed(1)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ============================================
// PICKUP-V2 PREVIEW COMPONENT (Revenue Forecasting)
// ============================================

// Pickup-V2 specific colors
const PICKUP_V2_COLORS = {
  forecast: '#ef4444',              // Red - main forecast line
  confidenceFill: 'rgba(239, 68, 68, 0.15)', // Light red - confidence band fill
  upperBound: 'rgba(239, 68, 68, 0.5)',      // Medium red - upper bound
  lowerBound: 'rgba(239, 68, 68, 0.5)',      // Medium red - lower bound
  currentOtb: '#10b981',            // Green - current OTB
  priorFinal: '#6b7280',            // Gray - prior year final
  priorOtb: '#9ca3af',              // Light gray - prior year OTB
}

const PickupV2Preview: React.FC = () => {
  const token = localStorage.getItem('token')

  // Default to next 30 days
  const today = new Date()
  const defaultStart = new Date(today)
  defaultStart.setDate(today.getDate() + 1)
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() + 30)

  const [startDate, setStartDate] = useState(defaultStart.toISOString().split('T')[0])
  const [endDate, setEndDate] = useState(defaultEnd.toISOString().split('T')[0])
  const [metric, setMetric] = useState<'net_accom' | 'rooms' | 'occupancy'>('net_accom')
  const [showTable, setShowTable] = useState(false)

  // Generate month options
  const monthOptions = useMemo(() => getNext12Months(), [])

  // Quick select handlers
  const handleQuickSelect = (days: number) => {
    const start = new Date()
    start.setDate(start.getDate() + 1)
    const end = new Date()
    end.setDate(end.getDate() + days)
    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  // Fetch Pickup-V2 forecast from backend
  const { data: pickupV2Data, isLoading } = useQuery<PickupV2Response>({
    queryKey: ['pickup-v2-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric, include_details: 'true' })
      const response = await fetch(`/api/forecast/pickup-v2-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch pickup-v2 forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch room categories for category name lookup
  const { data: roomCategories } = useQuery<{ site_id: string; site_name: string }[]>({
    queryKey: ['room-categories'],
    queryFn: async () => {
      const response = await fetch('/api/config/room-categories', {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  })

  // Build category name map
  const categoryNameMap = useMemo(() => {
    const map: Record<string, string> = {}
    if (roomCategories) {
      for (const cat of roomCategories) {
        map[cat.site_id] = cat.site_name
      }
    }
    return map
  }, [roomCategories])

  const isRevenueMetric = metric === 'net_accom'

  const metricLabel = {
    net_accom: 'Net Accomm Rev',
    rooms: 'Room Nights',
    occupancy: 'Occupancy %',
  }[metric] || 'Value'

  const unit = {
    net_accom: '',
    rooms: ' rooms',
    occupancy: '%',
  }[metric] || ''

  // Build chart data with confidence bands
  const chartData = useMemo(() => {
    if (!pickupV2Data?.data) return []

    const dates = pickupV2Data.data.map((d) => d.date)
    const forecasts = pickupV2Data.data.map((d) => d.forecast)
    const upperBounds = pickupV2Data.data.map((d) => d.upper_bound)
    const lowerBounds = pickupV2Data.data.map((d) => d.lower_bound)
    const currentOtb = isRevenueMetric
      ? pickupV2Data.data.map((d) => d.current_otb_rev)
      : pickupV2Data.data.map((d) => d.current_otb)
    const priorFinal = isRevenueMetric
      ? pickupV2Data.data.map((d) => d.prior_year_final_rev)
      : pickupV2Data.data.map((d) => d.prior_year_final)
    const priorOtb = isRevenueMetric
      ? pickupV2Data.data.map((d) => d.prior_year_otb_rev)
      : pickupV2Data.data.map((d) => d.prior_year_otb)

    // Calculate prior year dates for hover
    const priorDates = pickupV2Data.data.map((d) => d.prior_year_date)

    const traces: any[] = []

    // Prior year final (bottom layer, filled)
    traces.push({
      x: dates,
      y: priorFinal,
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: 'Prior Year Final',
      fill: 'tozeroy' as const,
      fillcolor: 'rgba(107, 114, 128, 0.1)',
      line: { color: PICKUP_V2_COLORS.priorFinal, width: 1, dash: 'dot' as const },
      customdata: priorDates,
      hovertemplate: isRevenueMetric
        ? `Prior Final (%{customdata}): £%{y:,.0f}<extra></extra>`
        : `Prior Final (%{customdata}): %{y:.1f}${unit}<extra></extra>`,
    })

    // Prior year OTB
    traces.push({
      x: dates,
      y: priorOtb,
      type: 'scatter' as const,
      mode: 'lines' as const,
      name: 'Prior Year OTB',
      line: { color: PICKUP_V2_COLORS.priorOtb, width: 2, dash: 'dash' as const },
      customdata: priorDates,
      hovertemplate: isRevenueMetric
        ? `Prior OTB (%{customdata}): £%{y:,.0f}<extra></extra>`
        : `Prior OTB (%{customdata}): %{y:.1f}${unit}<extra></extra>`,
    })

    // Confidence band (only for revenue metrics)
    if (isRevenueMetric && upperBounds[0] !== null && lowerBounds[0] !== null) {
      // Upper bound (invisible line for fill reference)
      traces.push({
        x: dates,
        y: upperBounds,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Upper Bound',
        line: { color: PICKUP_V2_COLORS.upperBound, width: 1, dash: 'dot' as const },
        hovertemplate: `Upper: £%{y:,.0f}<extra></extra>`,
      })

      // Lower bound with fill to upper
      traces.push({
        x: dates,
        y: lowerBounds,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'Lower Bound',
        fill: 'tonexty' as const,
        fillcolor: PICKUP_V2_COLORS.confidenceFill,
        line: { color: PICKUP_V2_COLORS.lowerBound, width: 1, dash: 'dot' as const },
        hovertemplate: `Lower: £%{y:,.0f}<extra></extra>`,
      })
    }

    // Current OTB
    traces.push({
      x: dates,
      y: currentOtb,
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: 'Current OTB',
      line: { color: PICKUP_V2_COLORS.currentOtb, width: 2 },
      marker: { size: 6 },
      hovertemplate: isRevenueMetric
        ? `Current OTB: £%{y:,.0f}<extra></extra>`
        : `Current OTB: %{y:.1f}${unit}<extra></extra>`,
    })

    // Main forecast line
    traces.push({
      x: dates,
      y: forecasts,
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: 'Pickup-V2 Forecast',
      line: { color: PICKUP_V2_COLORS.forecast, width: 3 },
      marker: { size: 8 },
      hovertemplate: isRevenueMetric
        ? `Forecast: £%{y:,.0f}<extra></extra>`
        : `Forecast: %{y:.1f}${unit}<extra></extra>`,
    })

    return traces
  }, [pickupV2Data, isRevenueMetric, unit])

  // ADR Position indicator (0-1 scale: 0 = discounting heavily, 1 = premium pricing)
  const avgAdrPosition = pickupV2Data?.summary?.avg_adr_position ?? 0.5
  const adrPositionLabel = avgAdrPosition < 0.33 ? 'Discounting' : avgAdrPosition > 0.67 ? 'Premium' : 'Balanced'
  const adrPositionColor = avgAdrPosition < 0.33 ? '#ef4444' : avgAdrPosition > 0.67 ? '#10b981' : '#f59e0b'

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Pickup-V2 Revenue Forecast</h2>
          <p style={styles.hint}>
            Additive pickup methodology for revenue forecasting with confidence bands.
            {isRevenueMetric && ' Upper/lower bounds based on current vs. minimum historical rates.'}
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* Date Range */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Date Range</label>
          <div style={styles.dateInputs}>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.dateInput}
            />
            <span style={styles.dateSeparator}>to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.dateInput}
            />
          </div>
        </div>

        {/* Quick Select */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Quick Select</label>
          <div style={styles.quickButtons}>
            <button style={styles.quickButton} onClick={() => handleQuickSelect(7)}>7 Days</button>
            <button style={styles.quickButton} onClick={() => handleQuickSelect(14)}>14 Days</button>
            <button style={styles.quickButton} onClick={() => handleQuickSelect(30)}>30 Days</button>
            <button style={styles.quickButton} onClick={() => handleQuickSelect(90)}>90 Days</button>
          </div>
        </div>

        {/* Month Selector */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Select Month</label>
          <select style={styles.select} onChange={(e) => handleMonthSelect(e.target.value)} defaultValue="">
            <option value="">-- Select Month --</option>
            {monthOptions.map((month, idx) => (
              <option key={month.label} value={idx}>{month.label}</option>
            ))}
          </select>
        </div>

        {/* Metric Selector */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <select
            style={styles.select}
            value={metric}
            onChange={(e) => setMetric(e.target.value as 'net_accom' | 'rooms' | 'occupancy')}
          >
            <option value="net_accom">Accommodation Revenue</option>
            <option value="rooms">Room Nights</option>
            <option value="occupancy">Occupancy %</option>
          </select>
        </div>
      </div>

      {/* Summary Cards */}
      {pickupV2Data && (
        <div style={styles.summaryGrid}>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Current OTB</div>
            <div style={styles.summaryValue}>
              {isRevenueMetric
                ? `£${(pickupV2Data.summary.otb_rev_total || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                : pickupV2Data.summary.forecast_total.toFixed(1)}
            </div>
          </div>
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Forecast Total</div>
            <div style={styles.summaryValue}>
              {isRevenueMetric
                ? `£${pickupV2Data.summary.forecast_total.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                : pickupV2Data.summary.forecast_total.toFixed(1)}
            </div>
          </div>
          {isRevenueMetric && pickupV2Data.summary.upper_total && (
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Upper Bound</div>
              <div style={styles.summaryValue}>
                £{pickupV2Data.summary.upper_total.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
            </div>
          )}
          {isRevenueMetric && pickupV2Data.summary.lower_total && (
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Lower Bound</div>
              <div style={styles.summaryValue}>
                £{pickupV2Data.summary.lower_total.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
            </div>
          )}
          <div style={styles.summaryCard}>
            <div style={styles.summaryLabel}>Pace vs Prior</div>
            <div style={{
              ...styles.summaryValue,
              color: (pickupV2Data.summary.avg_pace_pct || 0) >= 0 ? '#10b981' : '#ef4444'
            }}>
              {(pickupV2Data.summary.avg_pace_pct || 0) >= 0 ? '+' : ''}
              {(pickupV2Data.summary.avg_pace_pct || 0).toFixed(1)}%
            </div>
          </div>
          {isRevenueMetric && (
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>ADR Position</div>
              <div style={{ ...styles.summaryValue, color: adrPositionColor }}>
                {(avgAdrPosition * 100).toFixed(0)}% ({adrPositionLabel})
              </div>
            </div>
          )}
          {/* Rate Comparison Summary - Always visible for revenue metrics */}
          {isRevenueMetric && (
            <div style={{
              ...styles.summaryCard,
              backgroundColor: (pickupV2Data.summary.lost_potential_total || 0) > 0 ? '#fef3c7' : '#d1fae5',
              borderColor: (pickupV2Data.summary.lost_potential_total || 0) > 0 ? '#f59e0b' : '#10b981',
              borderWidth: 2,
            }}>
              {(pickupV2Data.summary.lost_potential_total || 0) > 0 ? (
                <>
                  <div style={{ ...styles.summaryLabel, color: '#92400e' }}>Lost Potential</div>
                  <div style={{ ...styles.summaryValue, color: '#b45309' }}>
                    £{(pickupV2Data.summary.lost_potential_total || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#92400e', marginTop: '4px' }}>
                    {pickupV2Data.summary.opportunity_days_count} days below prior year rates
                  </div>
                </>
              ) : (
                <>
                  <div style={{ ...styles.summaryLabel, color: '#065f46' }}>Rate Position</div>
                  <div style={{ ...styles.summaryValue, color: '#047857' }}>
                    On Track
                  </div>
                  <div style={{ fontSize: '0.75rem', color: '#065f46', marginTop: '4px' }}>
                    Current rates matching or beating prior year
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      )}

      {/* Chart */}
      {isLoading ? (
        <div style={styles.loadingContainer}>Loading forecast...</div>
      ) : chartData.length > 0 ? (
        <Plot
          data={chartData}
          layout={{
            autosize: true,
            height: 500,
            margin: { t: 40, r: 40, b: 60, l: 80 },
            xaxis: {
              title: { text: 'Date' },
              tickformat: '%b %d',
              tickangle: -45,
            },
            yaxis: {
              title: { text: metricLabel },
              tickformat: isRevenueMetric ? ',.0f' : undefined,
              tickprefix: isRevenueMetric ? '£' : undefined,
            },
            legend: {
              orientation: 'h',
              y: -0.2,
              x: 0.5,
              xanchor: 'center',
            },
            hovermode: 'x unified',
            showlegend: true,
          }}
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: '100%' }}
        />
      ) : (
        <div style={styles.loadingContainer}>No data available for selected range</div>
      )}

      {/* Table Toggle */}
      <div style={{ marginTop: spacing.md }}>
        <button
          style={styles.quickButton}
          onClick={() => setShowTable(!showTable)}
        >
          {showTable ? 'Hide Table' : 'Show Data Table'}
        </button>
      </div>

      {/* Data Table */}
      {showTable && pickupV2Data?.data && (
        <div style={{ marginTop: spacing.md, overflowX: 'auto' }}>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Date</th>
                {isRevenueMetric && <th style={styles.th}>OTB Rms</th>}
                {isRevenueMetric && <th style={styles.th}>Pickup</th>}
                {isRevenueMetric && <th style={styles.th}>Fcst Rms</th>}
                <th style={styles.th}>OTB Rev</th>
                {isRevenueMetric && <th style={styles.th}>Pickup Calc</th>}
                <th style={{ ...styles.th, fontWeight: 600 }}>Forecast</th>
                <th style={styles.th}>LY OTB</th>
                <th style={styles.th}>Pace</th>
                <th style={styles.th}>LY Final</th>
                <th style={styles.th}>vs Final</th>
                {isRevenueMetric && <th style={{ ...styles.th, backgroundColor: '#fef3c7', color: '#92400e' }}>Curr Rate</th>}
                {isRevenueMetric && <th style={{ ...styles.th, backgroundColor: '#fef3c7', color: '#92400e' }}>LY Rate</th>}
                {isRevenueMetric && <th style={{ ...styles.th, backgroundColor: '#fef3c7', color: '#92400e' }}>Lost £</th>}
                {isRevenueMetric && <th style={{ ...styles.th, backgroundColor: '#fef3c7', color: '#92400e' }}>Rate Gap</th>}
              </tr>
            </thead>
            <tbody>
              {pickupV2Data.data.map((row) => {
                const hasOpportunity = row.has_pricing_opportunity === true
                const rowStyle = hasOpportunity ? { backgroundColor: '#fef9e7' } : {}
                const pickupRooms = row.pickup_rooms_total || 0
                const otbRooms = row.current_otb || 0
                const forecastRooms = otbRooms + pickupRooms
                const priorOtbRev = row.prior_year_otb_rev || 0
                const priorFinalRev = row.prior_year_final_rev || 0
                const otbPacePct = priorOtbRev > 0 ? ((row.current_otb_rev || 0) - priorOtbRev) / priorOtbRev * 100 : 0
                const finalPacePct = priorFinalRev > 0 ? (row.forecast - priorFinalRev) / priorFinalRev * 100 : 0

                // Build tooltip for category breakdown with category names
                const categoryBreakdown = row.category_breakdown || {}
                const pickupTooltip = Object.entries(categoryBreakdown)
                  .filter(([_, data]: [string, any]) => data.pickup_rooms > 0)
                  .map(([catId, data]: [string, any]) => {
                    const catName = categoryNameMap[catId] || `Category ${catId}`
                    return `${catName}: ${data.pickup_rooms} rooms`
                  })
                  .join('\n') || 'No pickup expected'

                const pickupCalcTooltip = Object.entries(categoryBreakdown)
                  .filter(([_, data]: [string, any]) => data.pickup_rooms > 0)
                  .map(([catId, data]: [string, any]) => {
                    const catName = categoryNameMap[catId] || `Category ${catId}`
                    const netRate = data.prior_avg_rate?.toFixed(0) || '0'
                    const grossRate = data.prior_avg_rate_gross?.toFixed(0) || '0'
                    const pickupRev = data.forecast_pickup_rev?.toFixed(0) || '0'
                    return `${catName}: ${data.pickup_rooms} × £${netRate} (£${grossRate}) = £${pickupRev}`
                  })
                  .join('\n') || 'No pickup expected for this date'

                return (
                  <tr key={row.date} style={rowStyle}>
                    <td style={styles.td}>{row.date} {row.day_of_week}</td>
                    {isRevenueMetric && <td style={styles.td}>{Math.round(otbRooms)}</td>}
                    {isRevenueMetric && <td style={{ ...styles.td, cursor: 'help' }} title={pickupTooltip}>{pickupRooms}</td>}
                    {isRevenueMetric && <td style={styles.td}>{Math.round(forecastRooms)}</td>}
                    <td style={styles.td}>
                      {isRevenueMetric
                        ? `£${(row.current_otb_rev || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                        : (row.current_otb || 0).toFixed(1)}
                    </td>
                    {isRevenueMetric && (
                      <td
                        style={{
                          ...styles.td,
                          fontSize: '0.85em',
                          cursor: 'help',
                          color: row.effective_rate && row.weighted_avg_prior_rate && row.effective_rate < row.weighted_avg_prior_rate
                            ? '#dc2626'
                            : '#6b7280'
                        }}
                        title={pickupCalcTooltip}
                      >
                        {pickupRooms} × £{row.effective_rate?.toFixed(0) || row.weighted_avg_prior_rate?.toFixed(0) || '0'} <span style={{ color: '#6b7280' }}>(£{row.effective_rate_gross?.toFixed(0) || row.weighted_avg_prior_rate_gross?.toFixed(0) || '0'})</span>
                        {row.effective_rate && row.weighted_avg_prior_rate && row.effective_rate < row.weighted_avg_prior_rate && (
                          <span title="Capped at current rate"> *</span>
                        )}
                      </td>
                    )}
                    <td style={{ ...styles.td, fontWeight: 600 }}>
                      {isRevenueMetric
                        ? `£${row.forecast.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                        : row.forecast.toFixed(1)}
                    </td>
                    <td style={styles.td}>
                      £{priorOtbRev.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td style={{
                      ...styles.td,
                      color: otbPacePct >= 0 ? '#10b981' : '#ef4444'
                    }}>
                      {otbPacePct >= 0 ? '+' : ''}{otbPacePct.toFixed(0)}%
                    </td>
                    <td style={styles.td}>
                      £{priorFinalRev.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </td>
                    <td style={{
                      ...styles.td,
                      color: finalPacePct >= 0 ? '#10b981' : '#ef4444'
                    }}>
                      {finalPacePct >= 0 ? '+' : ''}{finalPacePct.toFixed(0)}%
                    </td>
                    {isRevenueMetric && (
                      <td style={{
                        ...styles.td,
                        backgroundColor: hasOpportunity ? '#fef3c7' : 'transparent',
                      }}>
                        {row.weighted_avg_current_rate
                          ? <>£{row.weighted_avg_current_rate.toFixed(0)} <span style={{ color: '#6b7280', fontSize: '0.85em' }}>(£{row.weighted_avg_current_rate_gross?.toFixed(0) || '-'})</span></>
                          : '-'}
                      </td>
                    )}
                    {isRevenueMetric && (
                      <td style={{
                        ...styles.td,
                        backgroundColor: hasOpportunity ? '#fef3c7' : 'transparent',
                      }}>
                        {row.weighted_avg_listed_rate
                          ? <>£{row.weighted_avg_listed_rate.toFixed(0)} <span style={{ color: '#6b7280', fontSize: '0.85em' }}>(£{row.weighted_avg_listed_rate_gross?.toFixed(0) || '-'})</span></>
                          : '-'}
                      </td>
                    )}
                    {isRevenueMetric && (
                      <td style={{
                        ...styles.td,
                        fontWeight: hasOpportunity ? 600 : 400,
                        color: hasOpportunity ? '#b45309' : '#6b7280',
                        backgroundColor: hasOpportunity ? '#fef3c7' : 'transparent',
                      }}>
                        {(row.lost_potential || 0) > 0
                          ? `£${(row.lost_potential || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                          : '-'}
                      </td>
                    )}
                    {isRevenueMetric && (
                      <td style={{
                        ...styles.td,
                        color: (row.rate_vs_prior_pct || 0) < 0 ? '#b45309' : '#10b981',
                      }}>
                        {row.rate_vs_prior_pct !== null
                          ? `${(row.rate_vs_prior_pct || 0) >= 0 ? '+' : ''}${(row.rate_vs_prior_pct || 0).toFixed(1)}%`
                          : '-'}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// ============================================
// COMPARE FORECASTS COMPONENT
// ============================================

const CompareForecasts: React.FC = () => {
  const token = localStorage.getItem('token')

  // Default to next 30 days
  const today = new Date()
  const defaultStart = new Date(today)
  defaultStart.setDate(today.getDate() + 1)
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() + 30)

  const [startDate, setStartDate] = useState(defaultStart.toISOString().split('T')[0])
  const [endDate, setEndDate] = useState(defaultEnd.toISOString().split('T')[0])
  const [metric, setMetric] = useState<MetricType>('rooms')
  const [showTable, setShowTable] = useState(false)

  // Generate month options
  const monthOptions = useMemo(() => getNext12Months(), [])

  // Quick select handlers
  const handleQuickSelect = (days: number) => {
    const start = new Date()
    start.setDate(start.getDate() + 1)
    const end = new Date()
    end.setDate(end.getDate() + days)
    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  // Fetch all three forecasts in parallel
  const { data: pickupData, isLoading: pickupLoading } = useQuery<PreviewResponse>({
    queryKey: ['forecast-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch pickup forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  const { data: prophetData, isLoading: prophetLoading } = useQuery<ProphetResponse>({
    queryKey: ['prophet-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/prophet-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch prophet forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  const { data: xgboostData, isLoading: xgboostLoading } = useQuery<XGBoostResponse>({
    queryKey: ['xgboost-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/xgboost-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch xgboost forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  const { data: catboostData, isLoading: catboostLoading } = useQuery<CatBoostResponse>({
    queryKey: ['catboost-preview', startDate, endDate, metric],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, metric })
      const response = await fetch(`/api/forecast/catboost-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch catboost forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch budget data for revenue metrics
  const budgetData = useBudgetData(startDate, endDate, metric, token)

  // Calculate blended forecast client-side (temporarily 100% model average)
  const blendedCalc = useMemo(() => {
    if (!prophetData?.data || !xgboostData?.data || !catboostData?.data) return null

    return prophetData.data.map((prophetRow, idx) => {
      const xgboostRow = xgboostData.data[idx]
      const catboostRow = catboostData.data[idx]

      const prophetFc = prophetRow.forecast ?? 0
      const xgboostFc = xgboostRow?.forecast ?? 0
      const catboostFc = catboostRow?.forecast ?? 0

      // Equal weight average of the three models (1/3 each)
      const modelAvg = (prophetFc + xgboostFc + catboostFc) / 3

      // Temporarily using 100% model average (no budget/prior year weighting)
      let blendedForecast = modelAvg

      // Floor cap: forecast can't be below current OTB (confirmed bookings)
      const currentOtb = prophetRow.current_otb ?? 0
      if (currentOtb > 0 && blendedForecast < currentOtb) {
        blendedForecast = currentOtb
      }

      return {
        date: prophetRow.date,
        blended_forecast: blendedForecast,
      }
    })
  }, [prophetData, xgboostData, catboostData, budgetData, metric])

  const isLoading = pickupLoading || prophetLoading || xgboostLoading || catboostLoading
  const metricLabel = {
    occupancy: 'Occupancy %',
    rooms: 'Room Nights',
    guests: 'Guests',
    ave_guest_rate: 'Ave Guest Rate',
    arr: 'ARR',
    net_accom: 'Net Accomm Rev',
    net_dry: 'Net Dry Rev',
    net_wet: 'Net Wet Rev',
    total_rev: 'Total Net Rev',
  }[metric] || 'Value'
  const unit = {
    occupancy: '%',
    rooms: ' rooms',
    guests: ' guests',
    ave_guest_rate: '',
    arr: '',
    net_accom: '',
    net_dry: '',
    net_wet: '',
    total_rev: '',
  }[metric] || ''

  // Check if metric supports pace data (pickup, OTB)
  const isPaceMetric = metric === 'occupancy' || metric === 'rooms'

  // Merge all data into comparison chart
  const compareChartData = useMemo(() => {
    // For pace metrics, require pickup data; for others, only need prophet/xgboost/catboost
    if (isPaceMetric) {
      if (!pickupData?.data || !prophetData?.data || !xgboostData?.data || !catboostData?.data) return []
    } else {
      if (!prophetData?.data || !xgboostData?.data || !catboostData?.data) return []
    }

    // Use pickup data for dates if available, otherwise use prophet
    const primaryData = isPaceMetric && pickupData?.data ? pickupData.data : prophetData.data
    const dates = primaryData.map((d) => d.date)

    const prophetForecast = prophetData.data.map((d) => d.forecast)
    const xgboostForecast = xgboostData.data.map((d) => d.forecast)
    const catboostForecast = catboostData.data.map((d) => d.forecast)

    // Calculate prior year dates
    const priorDates = primaryData.map((d) => {
      const date = new Date(d.date)
      date.setDate(date.getDate() - 364)
      return formatDate(date)
    })

    const traces: any[] = []

    // Only include pace-related traces for occupancy/rooms
    if (isPaceMetric && pickupData?.data) {
      const currentOtb = pickupData.data.map((d) => d.current_otb)
      const priorYearOtb = pickupData.data.map((d) => d.prior_year_otb)
      const priorYearFinal = pickupData.data.map((d) => d.prior_year_final)
      const pickupForecast = pickupData.data.map((d) => d.forecast)

      traces.push(
        // Prior year final fill (bottom layer)
        {
          x: dates,
          y: priorYearFinal,
          type: 'scatter' as const,
          mode: 'lines' as const,
          name: 'Prior Year Final',
          line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
          fill: 'tozeroy' as const,
          fillcolor: CHART_COLORS.priorFinalFill,
          customdata: priorDates,
          hovertemplate: `Prior Final: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
        },
        // Prior year OTB
        {
          x: dates,
          y: priorYearOtb,
          type: 'scatter' as const,
          mode: 'lines' as const,
          name: 'Prior Year OTB',
          line: { color: CHART_COLORS.priorOtb, width: 2, dash: 'dash' as const },
          customdata: priorDates,
          hovertemplate: `Prior OTB: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
        },
        // Current OTB - green
        {
          x: dates,
          y: currentOtb,
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Current OTB',
          line: { color: CHART_COLORS.currentOtb, width: 2 },
          marker: { size: 6 },
          hovertemplate: `Current OTB: %{y:.1f}${unit}<extra></extra>`,
        },
        // Pickup forecast - red
        {
          x: dates,
          y: pickupForecast,
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Pickup',
          line: { color: CHART_COLORS.pickup, width: 2 },
          marker: { size: 6, symbol: 'circle' },
          hovertemplate: `Pickup: %{y:.1f}${unit}<extra></extra>`,
        }
      )
    } else {
      // For non-pace metrics, add prior year final from XGBoost data (no OTB/pace available)
      const priorYearFinal = xgboostData.data.map((d) => d.prior_year_final)

      traces.push(
        // Prior year final fill (bottom layer)
        {
          x: dates,
          y: priorYearFinal,
          type: 'scatter' as const,
          mode: 'lines' as const,
          name: 'Prior Year Final',
          line: { color: CHART_COLORS.priorFinal, width: 1, dash: 'dot' as const },
          fill: 'tozeroy' as const,
          fillcolor: CHART_COLORS.priorFinalFill,
          customdata: priorDates,
          hovertemplate: `Prior Final: %{y:.1f}${unit}<br>Comparing: %{customdata}<extra></extra>`,
        }
      )
    }

    // Always include ML model traces
    traces.push(
      // Prophet forecast - blue
      {
        x: dates,
        y: prophetForecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Prophet',
        line: { color: CHART_COLORS.prophet, width: 2 },
        marker: { size: 6, symbol: 'square' },
        hovertemplate: `Prophet: %{y:.1f}${unit}<extra></extra>`,
      },
      // XGBoost forecast - orange
      {
        x: dates,
        y: xgboostForecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'XGBoost',
        line: { color: CHART_COLORS.xgboost, width: 2 },
        marker: { size: 6, symbol: 'diamond' },
        hovertemplate: `XGBoost: %{y:.1f}${unit}<extra></extra>`,
      },
      // CatBoost forecast - purple
      {
        x: dates,
        y: catboostForecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'CatBoost',
        line: { color: CHART_COLORS.catboost, width: 2 },
        marker: { size: 6, symbol: 'triangle-up' },
        hovertemplate: `CatBoost: %{y:.1f}${unit}<extra></extra>`,
      }
    )

    // Add blended forecast trace if available (calculated client-side)
    if (blendedCalc) {
      const blendedForecast = blendedCalc.map((d) => d.blended_forecast)
      traces.push({
        x: dates,
        y: blendedForecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Blended',
        line: { color: CHART_COLORS.blended, width: 3 },
        marker: { size: 8, symbol: 'star' },
        hovertemplate: `Blended: %{y:.1f}${unit}<extra></extra>`,
      })
    }

    // Add budget trace if available
    const budgetTrace = buildBudgetTrace(budgetData)
    if (budgetTrace) {
      traces.push(budgetTrace)
    }

    return traces
  }, [pickupData, prophetData, xgboostData, catboostData, blendedCalc, unit, isPaceMetric, budgetData])

  // Merge data for table
  const tableData = useMemo(() => {
    // For pace metrics, require pickup; for others, just need ML models
    if (isPaceMetric) {
      if (!pickupData?.data || !prophetData?.data || !xgboostData?.data || !catboostData?.data) return []
    } else {
      if (!prophetData?.data || !xgboostData?.data || !catboostData?.data) return []
    }

    // Use pickup data as primary if available, otherwise use prophet
    const primaryData = isPaceMetric && pickupData?.data ? pickupData.data : prophetData.data

    return primaryData.map((row, idx) => {
      const pickup = isPaceMetric && pickupData?.data ? pickupData.data[idx] : null
      // For non-pace metrics, get prior_year_final from xgboost data
      const priorYearFinal = pickup?.prior_year_final ?? xgboostData.data[idx]?.prior_year_final ?? null
      return {
        date: row.date,
        day_of_week: row.day_of_week,
        current_otb: pickup?.current_otb ?? null,
        prior_year_otb: pickup?.prior_year_otb ?? null,
        prior_year_final: priorYearFinal,
        pickup_forecast: pickup?.forecast ?? null,
        prophet_forecast: prophetData.data[idx]?.forecast ?? null,
        xgboost_forecast: xgboostData.data[idx]?.forecast ?? null,
        catboost_forecast: catboostData.data[idx]?.forecast ?? null,
        blended_forecast: blendedCalc?.[idx]?.blended_forecast ?? null,
      }
    })
  }, [pickupData, prophetData, xgboostData, catboostData, blendedCalc, isPaceMetric])

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Compare Forecast Models</h2>
          <p style={styles.hint}>
            {isPaceMetric
              ? 'Side-by-side comparison of Pickup, Prophet, XGBoost, CatBoost, and Blended forecasts'
              : 'Side-by-side comparison of Prophet, XGBoost, CatBoost, and Blended forecasts (Pickup not available for this metric)'}
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* Date Range */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Date Range</label>
          <div style={styles.dateInputs}>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.dateInput}
            />
            <span style={styles.dateSeparator}>to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.dateInput}
            />
          </div>
        </div>

        {/* Metric Dropdown */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value as MetricType)}
            style={styles.select}
          >
            <option value="occupancy">Occupancy %</option>
            <option value="rooms">Room Nights</option>
            <option value="guests">Guests</option>
            <option value="ave_guest_rate">Ave Guest Rate</option>
            <option value="arr">ARR (Net)</option>
            <option value="net_accom">Net Accomm Rev</option>
            <option value="net_dry">Net Dry Rev</option>
            <option value="net_wet">Net Wet Rev</option>
            <option value="total_rev">Total Net Rev</option>
          </select>
        </div>

        {/* Quick Selects */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Quick Select</label>
          <div style={styles.quickSelectGroup}>
            {[7, 14, 30, 60, 90].map((days) => (
              <button
                key={days}
                onClick={() => handleQuickSelect(days)}
                style={styles.quickSelectButton}
              >
                {days}d
              </button>
            ))}
          </div>
          <select
            onChange={(e) => handleMonthSelect(e.target.value)}
            style={{ ...styles.monthSelect, marginTop: spacing.xs }}
            defaultValue=""
          >
            <option value="" disabled>Month...</option>
            {monthOptions.map((month, idx) => (
              <option key={month.label} value={idx}>
                {month.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Summary Stats - show averages for each model */}
      {prophetData?.summary && xgboostData?.summary && catboostData?.summary && (() => {
        // Use pickup for days_count if available, otherwise prophet
        const days = isPaceMetric && pickupData?.summary ? pickupData.summary.days_count : prophetData.summary.days_count
        const prophetAvg = metric === 'occupancy' ? prophetData.summary.forecast_total / days : prophetData.summary.forecast_total
        const xgboostAvg = metric === 'occupancy' ? xgboostData.summary.forecast_total / days : xgboostData.summary.forecast_total
        const catboostAvg = metric === 'occupancy' ? catboostData.summary.forecast_total / days : catboostData.summary.forecast_total

        // Only calculate pickup/prior stats for pace metrics
        const pickupAvg = isPaceMetric && pickupData?.summary
          ? (metric === 'occupancy' ? pickupData.summary.forecast_total / days : pickupData.summary.forecast_total)
          : null
        const priorFinalAvg = isPaceMetric && pickupData?.summary
          ? (metric === 'occupancy' ? pickupData.summary.prior_final_total / days : pickupData.summary.prior_final_total)
          : null

        return (
          <div style={styles.summaryGrid}>
            {/* Only show Pickup card for pace metrics */}
            {isPaceMetric && pickupAvg !== null && priorFinalAvg !== null && (
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>PICKUP</span>
                <span style={{ ...styles.summaryValue, color: CHART_COLORS.pickup }}>
                  {metric === 'occupancy' ? `${pickupAvg.toFixed(1)}%` : pickupAvg.toFixed(0)}
                </span>
                <span style={{
                  ...styles.summarySubtext,
                  color: pickupAvg >= priorFinalAvg ? colors.success : colors.error,
                }}>
                  vs Prior: {pickupAvg >= priorFinalAvg ? '+' : ''}{metric === 'occupancy' ? `${(pickupAvg - priorFinalAvg).toFixed(1)}%` : (pickupAvg - priorFinalAvg).toFixed(0)}
                </span>
              </div>
            )}
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>PROPHET</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.prophet }}>
                {metric === 'occupancy' ? `${prophetAvg.toFixed(1)}%` : prophetAvg.toFixed(0)}
              </span>
              {isPaceMetric && priorFinalAvg !== null ? (
                <span style={{
                  ...styles.summarySubtext,
                  color: prophetAvg >= priorFinalAvg ? colors.success : colors.error,
                }}>
                  vs Prior: {prophetAvg >= priorFinalAvg ? '+' : ''}{metric === 'occupancy' ? `${(prophetAvg - priorFinalAvg).toFixed(1)}%` : (prophetAvg - priorFinalAvg).toFixed(0)}
                </span>
              ) : (
                <span style={styles.summarySubtext}>{days} days total</span>
              )}
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>XGBOOST</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.xgboost }}>
                {metric === 'occupancy' ? `${xgboostAvg.toFixed(1)}%` : xgboostAvg.toFixed(0)}
              </span>
              {isPaceMetric && priorFinalAvg !== null ? (
                <span style={{
                  ...styles.summarySubtext,
                  color: xgboostAvg >= priorFinalAvg ? colors.success : colors.error,
                }}>
                  vs Prior: {xgboostAvg >= priorFinalAvg ? '+' : ''}{metric === 'occupancy' ? `${(xgboostAvg - priorFinalAvg).toFixed(1)}%` : (xgboostAvg - priorFinalAvg).toFixed(0)}
                </span>
              ) : (
                <span style={styles.summarySubtext}>{days} days total</span>
              )}
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>CATBOOST</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.catboost }}>
                {metric === 'occupancy' ? `${catboostAvg.toFixed(1)}%` : catboostAvg.toFixed(0)}
              </span>
              {isPaceMetric && priorFinalAvg !== null ? (
                <span style={{
                  ...styles.summarySubtext,
                  color: catboostAvg >= priorFinalAvg ? colors.success : colors.error,
                }}>
                  vs Prior: {catboostAvg >= priorFinalAvg ? '+' : ''}{metric === 'occupancy' ? `${(catboostAvg - priorFinalAvg).toFixed(1)}%` : (catboostAvg - priorFinalAvg).toFixed(0)}
                </span>
              ) : (
                <span style={styles.summarySubtext}>{days} days total</span>
              )}
            </div>
            {/* Only show Prior Year card for pace metrics */}
            {isPaceMetric && priorFinalAvg !== null && (
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>PRIOR YR FINAL</span>
                <span style={styles.summaryValue}>
                  {metric === 'occupancy' ? `${priorFinalAvg.toFixed(1)}%` : priorFinalAvg.toFixed(0)}
                </span>
                <span style={styles.summarySubtext}>baseline comparison</span>
              </div>
            )}
          </div>
        )
      })()}

      {/* Comparison Chart */}
      {isLoading ? (
        <div style={styles.loadingContainer}>Loading all forecast models...</div>
      ) : compareChartData.length > 0 ? (
        <div style={styles.chartContainer}>
          <Plot
            data={compareChartData}
            layout={{
              height: 400,
              margin: { l: 50, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: typography.fontFamily, color: colors.text },
              xaxis: {
                showgrid: true,
                gridcolor: colors.border,
                tickangle: -45,
                hoverformat: '%a %d/%m/%y',
              },
              yaxis: {
                showgrid: true,
                gridcolor: colors.border,
                title: { text: metricLabel },
              },
              legend: {
                orientation: 'h',
                y: -0.2,
                x: 0.5,
                xanchor: 'center',
              },
              hovermode: 'x unified',
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%' }}
          />
        </div>
      ) : (
        <div style={styles.emptyContainer}>
          No forecast data available for comparison.
        </div>
      )}

      {/* Data Table */}
      {tableData.length > 0 && (
        <>
          <button onClick={() => setShowTable(!showTable)} style={styles.tableToggle}>
            {showTable ? 'Hide' : 'Show'} Data Table
          </button>

          {showTable && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>DOW</th>
                    {isPaceMetric && <th style={{ ...styles.th, ...styles.thRight }}>OTB</th>}
                    {isPaceMetric && <th style={{ ...styles.th, ...styles.thRight }}>Prior OTB</th>}
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Final</th>
                    {isPaceMetric && <th style={{ ...styles.th, ...styles.thRight }}>Pickup</th>}
                    <th style={{ ...styles.th, ...styles.thRight }}>Prophet</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>XGBoost</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>CatBoost</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Blended</th>
                  </tr>
                </thead>
                <tbody>
                  {tableData.map((row, idx) => (
                    <tr
                      key={row.date}
                      style={{
                        ...styles.tr,
                        backgroundColor: idx % 2 === 0 ? colors.surface : colors.background,
                      }}
                    >
                      <td style={styles.td}>{row.date}</td>
                      <td style={styles.td}>{row.day_of_week}</td>
                      {isPaceMetric && (
                        <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.currentOtb }}>
                          {row.current_otb !== null ? row.current_otb.toFixed(1) : '-'}
                        </td>
                      )}
                      {isPaceMetric && (
                        <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                          {row.prior_year_otb !== null ? row.prior_year_otb.toFixed(1) : '-'}
                        </td>
                      )}
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textMuted }}>
                        {row.prior_year_final !== null ? row.prior_year_final.toFixed(1) : '-'}
                      </td>
                      {isPaceMetric && (
                        <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.pickup, fontWeight: typography.semibold }}>
                          {row.pickup_forecast !== null ? row.pickup_forecast.toFixed(1) : '-'}
                        </td>
                      )}
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.prophet, fontWeight: typography.semibold }}>
                        {row.prophet_forecast !== null ? row.prophet_forecast.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.xgboost, fontWeight: typography.semibold }}>
                        {row.xgboost_forecast !== null ? row.xgboost_forecast.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.catboost, fontWeight: typography.semibold }}>
                        {row.catboost_forecast !== null ? row.catboost_forecast.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.blended, fontWeight: typography.semibold }}>
                        {row.blended_forecast !== null ? row.blended_forecast.toFixed(1) : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// RESTAURANT COVERS FORECAST COMPONENT
// ============================================

interface CoversDataPoint {
  date: string
  day_of_week: string
  lead_days: number
  prior_year_date: string
  breakfast_otb: number
  breakfast_pickup: number
  breakfast_forecast: number
  breakfast_prior: number
  breakfast_hotel_guests_otb: number
  breakfast_hotel_guests_prior: number
  breakfast_calc: {
    night_before: string
    hotel_rooms_otb?: number
    hotel_guests_otb?: number
    pickup_rooms?: number
    guests_per_room?: number
    hotel_guests_prior?: number
    source: string
  } | null
  lunch_otb: number
  lunch_pickup: number
  lunch_forecast: number
  lunch_prior: number
  lunch_calc: {
    day_of_week: string
    lead_days: number
    pace_column: string
    lookback_weeks: number
    median_pickup: number
    source: string
  } | null
  dinner_otb: number
  dinner_resident_otb: number
  dinner_non_resident_otb: number
  dinner_resident_pickup: number
  dinner_non_resident_pickup: number
  dinner_forecast: number
  dinner_prior: number
  dinner_resident_calc: {
    hotel_guests_otb: number
    pickup_rooms: number
    guests_per_room: number
    pickup_guests: number
    forecasted_guests: number
    dining_rate: number
    forecasted_resident_covers: number
    resident_otb: number
    source: string
  } | null
  dinner_non_resident_calc: {
    day_of_week: string
    lead_days: number
    pace_column: string
    lookback_weeks: number
    median_pickup: number
    source: string
  } | null
  total_otb: number
  total_forecast: number
  total_prior: number
  pace_vs_prior_pct: number | null
  hotel_occupancy_pct: number
  hotel_rooms: number
}

interface CoversSummary {
  breakfast_otb: number
  breakfast_forecast: number
  breakfast_prior: number
  lunch_otb: number
  lunch_forecast: number
  lunch_prior: number
  dinner_otb: number
  dinner_forecast: number
  dinner_prior: number
  total_otb: number
  total_forecast: number
  total_prior: number
  days_count: number
}

interface CoversResponse {
  data: CoversDataPoint[]
  summary: CoversSummary
}

// Colors for stacked segments
const COVERS_COLORS = {
  breakfast: '#f59e0b',           // Amber - breakfast
  lunchResident: '#10b981',       // Green - lunch resident
  lunchNonResident: '#06b6d4',    // Cyan - lunch non-resident
  lunchPickup: '#a5f3fc',         // Light cyan - lunch pickup
  dinnerResident: '#8b5cf6',      // Purple - dinner resident
  dinnerNonResident: '#ef4444',   // Red - dinner non-resident
  dinnerResidentPickup: '#c4b5fd',// Light purple - dinner resident pickup
  dinnerNonResidentPickup: '#fca5a5', // Light red - dinner non-resident pickup
  priorYear: '#9ca3af',           // Gray - prior year line
}

interface RestaurantCoversForecastProps {
  consolidation: 'daily' | 'weekly' | 'monthly'
}

const RestaurantCoversForecast: React.FC<RestaurantCoversForecastProps> = ({ consolidation }) => {
  const token = localStorage.getItem('token')

  // Helper: get Monday of the week containing a date
  const getMondayOfWeek = (date: Date): Date => {
    const d = new Date(date)
    const day = d.getDay()
    const diff = day === 0 ? -6 : 1 - day
    d.setDate(d.getDate() + diff)
    d.setHours(0, 0, 0, 0)
    return d
  }

  // Helper: get ISO week number
  const getISOWeekNumber = (date: Date): number => {
    const d = new Date(date)
    d.setHours(0, 0, 0, 0)
    d.setDate(d.getDate() + 4 - (d.getDay() || 7))
    const yearStart = new Date(d.getFullYear(), 0, 1)
    return Math.ceil((((d.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
  }

  // Helper: get financial year start (August)
  const getFinancialYearStart = (date: Date): string => {
    const year = date.getFullYear()
    const month = date.getMonth()
    const fyStartYear = month >= 7 ? year : year - 1
    return `${fyStartYear}-08`
  }

  const today = new Date()
  const currentMonday = getMondayOfWeek(today)

  const [selectedMonth, setSelectedMonth] = useState(() => {
    if (consolidation === 'monthly') {
      return getFinancialYearStart(today)
    }
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  })
  const [selectedWeek, setSelectedWeek] = useState(() => formatDate(currentMonday))
  const [duration, setDuration] = useState<'1' | '3' | '6' | '12'>(
    consolidation === 'monthly' ? '12' : consolidation === 'daily' ? '1' : '3'
  )
  const [weekDuration, setWeekDuration] = useState<'4' | '8' | '13' | '26'>('13')
  const [showTable, setShowTable] = useState(true)
  const [useCustomDates, setUseCustomDates] = useState(false)
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')

  // Generate month options
  const monthOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const now = new Date()
    for (let i = -24; i <= 12; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() + i, 1)
      const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      const label = date.toLocaleString('default', { month: 'short', year: 'numeric' })
      options.push({ value, label })
    }
    return options
  }, [])

  // Generate week options
  const weekOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const now = new Date()
    const currentMon = getMondayOfWeek(now)

    for (let i = -52; i <= 26; i++) {
      const monday = new Date(currentMon)
      monday.setDate(currentMon.getDate() + (i * 7))
      const sunday = new Date(monday)
      sunday.setDate(monday.getDate() + 6)

      const weekNum = getISOWeekNumber(monday)
      const value = formatDate(monday)
      const label = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })})`
      options.push({ value, label })
    }
    return options
  }, [])

  // Calculate start and end dates
  const { startDate, endDate } = useMemo(() => {
    if (useCustomDates && customStartDate && customEndDate) {
      return { startDate: customStartDate, endDate: customEndDate }
    }
    if (consolidation === 'weekly') {
      const start = new Date(selectedWeek)
      const durationWeeks = parseInt(weekDuration)
      const end = new Date(start)
      end.setDate(start.getDate() + (durationWeeks * 7) - 1)
      return { startDate: formatDate(start), endDate: formatDate(end) }
    } else {
      const [year, month] = selectedMonth.split('-').map(Number)
      const start = new Date(year, month - 1, 1)
      const durationMonths = parseInt(duration)
      const end = new Date(year, month - 1 + durationMonths, 0)
      return { startDate: formatDate(start), endDate: formatDate(end) }
    }
  }, [selectedMonth, selectedWeek, duration, weekDuration, consolidation, useCustomDates, customStartDate, customEndDate])

  // Fetch covers forecast
  const { data: forecastData, isLoading } = useQuery<CoversResponse>({
    queryKey: ['covers-forecast', startDate, endDate],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate })
      const response = await fetch(`/api/forecast/covers-forecast?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch average spend settings for revenue calculation
  const { data: spendSettings } = useQuery({
    queryKey: ['resos-average-spend'],
    queryFn: async () => {
      const response = await fetch('/api/resos/average-spend', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!response.ok) return null
      return response.json()
    },
    enabled: !!token,
  })

  // Fetch F&B budgets for date range
  const { data: budgetData } = useQuery({
    queryKey: ['fb-budgets', startDate, endDate],
    queryFn: async () => {
      const params = new URLSearchParams({ from_date: startDate, to_date: endDate })
      const response = await fetch(`/api/budget/daily?${params}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!response.ok) return null
      const data = await response.json()
      // Extract net_dry and net_wet budgets
      return data.filter((b: any) => b.budget_type === 'net_dry' || b.budget_type === 'net_wet')
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Consolidate data for weekly/monthly views
  const consolidatedData = useMemo(() => {
    if (!forecastData?.data || consolidation === 'daily') return null

    const groups: Record<string, {
      label: string
      startDate: string
      // Breakfast
      breakfastOtb: number
      breakfastForecast: number
      breakfastPrior: number
      // Lunch
      lunchOtb: number
      lunchPickup: number
      lunchForecast: number
      lunchPrior: number
      // Dinner
      dinnerOtb: number
      dinnerResidentOtb: number
      dinnerNonResidentOtb: number
      dinnerForecast: number
      dinnerPrior: number
      // Totals
      totalOtb: number
      totalForecast: number
      totalPrior: number
      days: number
    }> = {}

    forecastData.data.forEach(d => {
      const dateObj = new Date(d.date)
      let groupKey: string
      let groupLabel: string

      if (consolidation === 'weekly') {
        const dayOfWeek = dateObj.getDay()
        const monday = new Date(dateObj)
        monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
        const sunday = new Date(monday)
        sunday.setDate(monday.getDate() + 6)
        groupKey = formatDate(monday)
        const weekD = new Date(monday)
        weekD.setDate(weekD.getDate() + 4 - (weekD.getDay() || 7))
        const yearStart = new Date(weekD.getFullYear(), 0, 1)
        const weekNum = Math.ceil((((weekD.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
        groupLabel = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })})`
      } else {
        groupKey = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}`
        groupLabel = dateObj.toLocaleString('default', { month: 'short', year: 'numeric' })
      }

      if (!groups[groupKey]) {
        groups[groupKey] = {
          label: groupLabel,
          startDate: d.date,
          breakfastOtb: 0,
          breakfastForecast: 0,
          breakfastPrior: 0,
          lunchOtb: 0,
          lunchPickup: 0,
          lunchForecast: 0,
          lunchPrior: 0,
          dinnerOtb: 0,
          dinnerResidentOtb: 0,
          dinnerNonResidentOtb: 0,
          dinnerForecast: 0,
          dinnerPrior: 0,
          totalOtb: 0,
          totalForecast: 0,
          totalPrior: 0,
          days: 0
        }
      }

      groups[groupKey].breakfastOtb += d.breakfast_otb
      groups[groupKey].breakfastForecast += d.breakfast_forecast
      groups[groupKey].breakfastPrior += d.breakfast_prior
      groups[groupKey].lunchOtb += d.lunch_otb
      groups[groupKey].lunchPickup += d.lunch_pickup
      groups[groupKey].lunchForecast += d.lunch_forecast
      groups[groupKey].lunchPrior += d.lunch_prior
      groups[groupKey].dinnerOtb += d.dinner_otb
      groups[groupKey].dinnerResidentOtb += d.dinner_resident_otb
      groups[groupKey].dinnerNonResidentOtb += d.dinner_non_resident_otb
      groups[groupKey].dinnerForecast += d.dinner_forecast
      groups[groupKey].dinnerPrior += d.dinner_prior
      groups[groupKey].totalOtb += d.total_otb
      groups[groupKey].totalForecast += d.total_forecast
      groups[groupKey].totalPrior += d.total_prior
      groups[groupKey].days++
    })

    return Object.entries(groups)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, data]) => ({
        key,
        ...data,
        variancePct: data.totalPrior > 0 ? ((data.totalForecast / data.totalPrior) - 1) * 100 : 0
      }))
  }, [forecastData, consolidation])

  // Build chart data - stacked bars by meal period and segment
  const chartData = useMemo(() => {
    if (consolidation !== 'daily' && consolidatedData) {
      const labels = consolidatedData.map(d => d.label)

      // Stacked bar traces for forecast
      const traces: any[] = [
        {
          x: labels,
          y: consolidatedData.map(d => d.breakfastForecast),
          type: 'bar' as const,
          name: 'Breakfast',
          marker: { color: COVERS_COLORS.breakfast },
          hovertemplate: `Breakfast: %{y:,.0f} covers<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => d.lunchOtb),
          type: 'bar' as const,
          name: 'Lunch OTB',
          marker: { color: COVERS_COLORS.lunchResident },
          hovertemplate: `Lunch OTB: %{y:,.0f} covers<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => d.lunchPickup),
          type: 'bar' as const,
          name: 'Lunch Pickup',
          marker: { color: COVERS_COLORS.lunchPickup },
          hovertemplate: `Lunch Pickup: %{y:,.0f} covers<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => d.dinnerResidentOtb),
          type: 'bar' as const,
          name: 'Dinner (Resident)',
          marker: { color: COVERS_COLORS.dinnerResident },
          hovertemplate: `Dinner Resident: %{y:,.0f} covers<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => d.dinnerNonResidentOtb),
          type: 'bar' as const,
          name: 'Dinner (Non-Res)',
          marker: { color: COVERS_COLORS.dinnerNonResident },
          hovertemplate: `Dinner Non-Resident: %{y:,.0f} covers<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => Math.max(0, d.dinnerForecast - d.dinnerOtb)),
          type: 'bar' as const,
          name: 'Dinner Pickup',
          marker: { color: COVERS_COLORS.dinnerNonResidentPickup },
          hovertemplate: `Dinner Pickup: %{y:,.0f} covers<extra></extra>`,
        },
      ]

      // Prior year line
      traces.push({
        x: labels,
        y: consolidatedData.map(d => d.totalPrior),
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Prior Year',
        line: { color: COVERS_COLORS.priorYear, width: 2, dash: 'dot' as const },
        marker: { size: 6 },
        hovertemplate: `Prior Year: %{y:,.0f} covers<extra></extra>`,
      })

      return { traces, labels }
    }

    // Daily view
    if (!forecastData?.data) return null

    // Separate past/future for different visualization
    const dates = forecastData.data.map(d => d.date)

    const traces: any[] = [
      {
        x: dates,
        y: forecastData.data.map(d => d.breakfast_forecast),
        type: 'bar' as const,
        name: 'Breakfast',
        marker: { color: COVERS_COLORS.breakfast },
        hovertemplate: `Breakfast: %{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: forecastData.data.map(d => d.lunch_otb),
        type: 'bar' as const,
        name: 'Lunch OTB',
        marker: { color: COVERS_COLORS.lunchResident },
        hovertemplate: `Lunch OTB: %{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: forecastData.data.map(d => d.lunch_pickup),
        type: 'bar' as const,
        name: 'Lunch Pickup',
        marker: { color: COVERS_COLORS.lunchPickup },
        hovertemplate: `Lunch Pickup: %{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: forecastData.data.map(d => d.dinner_resident_otb),
        type: 'bar' as const,
        name: 'Dinner (Resident)',
        marker: { color: COVERS_COLORS.dinnerResident },
        hovertemplate: `Dinner Resident: %{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: forecastData.data.map(d => d.dinner_non_resident_otb),
        type: 'bar' as const,
        name: 'Dinner (Non-Res)',
        marker: { color: COVERS_COLORS.dinnerNonResident },
        hovertemplate: `Dinner Non-Resident: %{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: forecastData.data.map(d => d.dinner_resident_pickup + d.dinner_non_resident_pickup),
        type: 'bar' as const,
        name: 'Dinner Pickup',
        marker: { color: COVERS_COLORS.dinnerNonResidentPickup },
        hovertemplate: `Dinner Pickup: %{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: forecastData.data.map(d => d.total_prior),
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Prior Year',
        line: { color: COVERS_COLORS.priorYear, width: 2, dash: 'dot' as const },
        marker: { size: 4 },
        hovertemplate: `Prior Year: %{y:,.0f}<extra></extra>`,
      },
    ]

    return { traces, labels: dates }
  }, [forecastData, consolidatedData, consolidation])

  // Calculate summary
  const summary = useMemo(() => {
    if (!forecastData?.summary) return null
    const s = forecastData.summary
    return {
      breakfastForecast: s.breakfast_forecast,
      breakfastPrior: s.breakfast_prior,
      lunchForecast: s.lunch_forecast,
      lunchPrior: s.lunch_prior,
      dinnerForecast: s.dinner_forecast,
      dinnerPrior: s.dinner_prior,
      totalForecast: s.total_forecast,
      totalPrior: s.total_prior,
      totalOtb: s.total_otb,
      daysCount: s.days_count
    }
  }, [forecastData])

  // Calculate revenue from covers × spend per head
  const revenueChartData = useMemo(() => {
    if (!forecastData?.data || !spendSettings) return null

    // Convert gross spend (inc VAT) to net spend (exc VAT) - UK VAT is 20%
    const VAT_RATE = 1.20
    const breakfastSpend = ((spendSettings.breakfast_food_spend || 0) + (spendSettings.breakfast_drinks_spend || 0)) / VAT_RATE
    const lunchSpend = ((spendSettings.lunch_food_spend || 0) + (spendSettings.lunch_drinks_spend || 0)) / VAT_RATE
    const dinnerSpend = ((spendSettings.dinner_food_spend || 0) + (spendSettings.dinner_drinks_spend || 0)) / VAT_RATE

    // Build budget lookup by date
    const budgetByDate: Record<string, { food: number; drinks: number }> = {}
    if (budgetData) {
      budgetData.forEach((b: any) => {
        if (!budgetByDate[b.date]) budgetByDate[b.date] = { food: 0, drinks: 0 }
        if (b.budget_type === 'net_dry') budgetByDate[b.date].food = b.budget_value
        else if (b.budget_type === 'net_wet') budgetByDate[b.date].drinks = b.budget_value
      })
    }

    if (consolidation !== 'daily' && consolidatedData) {
      // For weekly/monthly view, aggregate
      const labels = consolidatedData.map(d => d.label)

      // Group budget by week/month
      const budgetByGroup: Record<string, number> = {}
      if (budgetData) {
        budgetData.forEach((b: any) => {
          const dateObj = new Date(b.date)
          let groupKey: string
          if (consolidation === 'weekly') {
            const dayOfWeek = dateObj.getDay()
            const monday = new Date(dateObj)
            monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
            groupKey = monday.toISOString().split('T')[0]
          } else {
            groupKey = `${dateObj.getFullYear()}-${String(dateObj.getMonth() + 1).padStart(2, '0')}`
          }
          if (!budgetByGroup[groupKey]) budgetByGroup[groupKey] = 0
          budgetByGroup[groupKey] += b.budget_value || 0
        })
      }

      const forecastRevenue = consolidatedData.map(d =>
        (d.breakfastForecast * breakfastSpend) +
        (d.lunchForecast * lunchSpend) +
        (d.dinnerForecast * dinnerSpend)
      )

      const priorRevenue = consolidatedData.map(d =>
        (d.breakfastPrior * breakfastSpend) +
        (d.lunchPrior * lunchSpend) +
        (d.dinnerPrior * dinnerSpend)
      )

      const budgetValues = consolidatedData.map(d => budgetByGroup[d.key] || 0)

      const traces: any[] = [
        {
          x: labels,
          y: forecastRevenue,
          type: 'bar' as const,
          name: 'Forecast Net Revenue',
          marker: { color: colors.accent },
          hovertemplate: `Forecast: £%{y:,.0f}<extra></extra>`,
        },
        {
          x: labels,
          y: priorRevenue,
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Prior Year',
          line: { color: COVERS_COLORS.priorYear, width: 2, dash: 'dot' as const },
          marker: { size: 6 },
          hovertemplate: `Prior Year: £%{y:,.0f}<extra></extra>`,
        },
      ]

      // Add budget line if data exists
      if (budgetValues.some(v => v > 0)) {
        traces.push({
          x: labels,
          y: budgetValues,
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Budget',
          line: { color: colors.warning, width: 2 },
          marker: { size: 6 },
          hovertemplate: `Budget: £%{y:,.0f}<extra></extra>`,
        })
      }

      return { traces, labels }
    }

    // Daily view
    const dates = forecastData.data.map(d => d.date)

    const forecastRevenue = forecastData.data.map(d =>
      (d.breakfast_forecast * breakfastSpend) +
      (d.lunch_forecast * lunchSpend) +
      (d.dinner_forecast * dinnerSpend)
    )

    const priorRevenue = forecastData.data.map(d =>
      (d.breakfast_prior * breakfastSpend) +
      (d.lunch_prior * lunchSpend) +
      (d.dinner_prior * dinnerSpend)
    )

    const budgetValues = forecastData.data.map(d => {
      const b = budgetByDate[d.date]
      return b ? (b.food + b.drinks) : 0
    })

    const traces: any[] = [
      {
        x: dates,
        y: forecastRevenue,
        type: 'bar' as const,
        name: 'Forecast Net Revenue',
        marker: { color: colors.accent },
        hovertemplate: `Forecast: £%{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: priorRevenue,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Prior Year',
        line: { color: COVERS_COLORS.priorYear, width: 2, dash: 'dot' as const },
        marker: { size: 4 },
        hovertemplate: `Prior Year: £%{y:,.0f}<extra></extra>`,
      },
    ]

    // Add budget line if data exists
    if (budgetValues.some(v => v > 0)) {
      traces.push({
        x: dates,
        y: budgetValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Budget',
        line: { color: colors.warning, width: 2 },
        marker: { size: 4 },
        hovertemplate: `Budget: £%{y:,.0f}<extra></extra>`,
      })
    }

    return { traces, labels: dates }
  }, [forecastData, consolidatedData, consolidation, spendSettings, budgetData])

  // Calculate revenue summary
  const revenueSummary = useMemo(() => {
    if (!summary || !spendSettings) return null

    // Convert gross spend (inc VAT) to net spend (exc VAT) - UK VAT is 20%
    const VAT_RATE = 1.20
    const breakfastSpend = ((spendSettings.breakfast_food_spend || 0) + (spendSettings.breakfast_drinks_spend || 0)) / VAT_RATE
    const lunchSpend = ((spendSettings.lunch_food_spend || 0) + (spendSettings.lunch_drinks_spend || 0)) / VAT_RATE
    const dinnerSpend = ((spendSettings.dinner_food_spend || 0) + (spendSettings.dinner_drinks_spend || 0)) / VAT_RATE

    const forecastRevenue =
      (summary.breakfastForecast * breakfastSpend) +
      (summary.lunchForecast * lunchSpend) +
      (summary.dinnerForecast * dinnerSpend)

    const priorRevenue =
      (summary.breakfastPrior * breakfastSpend) +
      (summary.lunchPrior * lunchSpend) +
      (summary.dinnerPrior * dinnerSpend)

    // Calculate budget total
    let budgetTotal = 0
    if (budgetData) {
      budgetData.forEach((b: any) => {
        budgetTotal += b.budget_value || 0
      })
    }

    return {
      forecast: forecastRevenue,
      prior: priorRevenue,
      budget: budgetTotal,
      varianceVsPrior: priorRevenue > 0 ? ((forecastRevenue / priorRevenue) - 1) * 100 : 0,
      varianceVsBudget: budgetTotal > 0 ? ((forecastRevenue / budgetTotal) - 1) * 100 : 0,
    }
  }, [summary, spendSettings, budgetData])

  // Title based on consolidation
  const title = consolidation === 'daily' ? 'Restaurant Covers by Day' :
                consolidation === 'weekly' ? 'Restaurant Covers by Week' :
                'Restaurant Covers by Month'

  return (
    <div>
      <h2 style={styles.pageTitle}>{title}</h2>

      {/* Controls - matching accommodation pages */}
      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.label}>From {consolidation === 'weekly' ? 'Week' : 'Month'}</label>
          {consolidation === 'weekly' ? (
            <select
              value={selectedWeek}
              onChange={(e) => { setSelectedWeek(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {weekOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          ) : (
            <select
              value={selectedMonth}
              onChange={(e) => { setSelectedMonth(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {monthOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          )}
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.label}>Duration</label>
          {consolidation === 'weekly' ? (
            <select
              value={weekDuration}
              onChange={(e) => { setWeekDuration(e.target.value as '4' | '8' | '13' | '26'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="4">4 Weeks</option>
              <option value="8">8 Weeks</option>
              <option value="13">13 Weeks (~3 Months)</option>
              <option value="26">26 Weeks (~6 Months)</option>
            </select>
          ) : (
            <select
              value={duration}
              onChange={(e) => { setDuration(e.target.value as '1' | '3' | '6' | '12'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="1">1 Month</option>
              <option value="3">3 Months</option>
              <option value="6">6 Months</option>
              <option value="12">1 Year</option>
            </select>
          )}
        </div>

        {/* Custom Date Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Custom Range</label>
          <div style={{ display: 'flex', gap: spacing.xs, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={useCustomDates}
              onChange={(e) => {
                setUseCustomDates(e.target.checked)
                if (e.target.checked && !customStartDate) {
                  setCustomStartDate(startDate)
                  setCustomEndDate(endDate)
                }
              }}
            />
            {useCustomDates && (
              <>
                <input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
                <span>to</span>
                <input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
              </>
            )}
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.label}>Period</label>
          <div style={{
            padding: `${spacing.sm} ${spacing.md}`,
            background: colors.surface,
            borderRadius: radius.md,
            fontSize: typography.sm,
            color: colors.text,
          }}>
            {startDate} to {endDate}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div style={styles.loadingContainer}>Loading covers forecast...</div>
      ) : !forecastData?.data?.length ? (
        <div style={styles.emptyContainer}>No covers data available for this period</div>
      ) : (
        <>
          {/* Summary Cards */}
          {summary && (
            <div style={styles.summaryGrid}>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>Breakfast</span>
                <span style={styles.summaryValue}>{summary.breakfastForecast.toLocaleString()}</span>
                <span style={styles.summarySubtext}>
                  vs LY: {summary.breakfastPrior.toLocaleString()}
                  ({summary.breakfastPrior > 0 ? ((summary.breakfastForecast / summary.breakfastPrior - 1) * 100).toFixed(0) : 0}%)
                </span>
              </div>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>Lunch</span>
                <span style={styles.summaryValue}>{summary.lunchForecast.toLocaleString()}</span>
                <span style={styles.summarySubtext}>
                  vs LY: {summary.lunchPrior.toLocaleString()}
                  ({summary.lunchPrior > 0 ? ((summary.lunchForecast / summary.lunchPrior - 1) * 100).toFixed(0) : 0}%)
                </span>
              </div>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>Dinner</span>
                <span style={styles.summaryValue}>{summary.dinnerForecast.toLocaleString()}</span>
                <span style={styles.summarySubtext}>
                  vs LY: {summary.dinnerPrior.toLocaleString()}
                  ({summary.dinnerPrior > 0 ? ((summary.dinnerForecast / summary.dinnerPrior - 1) * 100).toFixed(0) : 0}%)
                </span>
              </div>
              <div style={{ ...styles.summaryCard, background: colors.infoBg }}>
                <span style={styles.summaryLabel}>Total Covers</span>
                <span style={{ ...styles.summaryValue, color: colors.accent }}>{summary.totalForecast.toLocaleString()}</span>
                <span style={styles.summarySubtext}>
                  vs LY: {summary.totalPrior.toLocaleString()}
                  ({summary.totalPrior > 0 ? ((summary.totalForecast / summary.totalPrior - 1) * 100).toFixed(0) : 0}%)
                </span>
              </div>
            </div>
          )}

          {/* Covers Chart */}
          {chartData && (
            <div style={styles.chartContainer}>
              <Plot
                data={chartData.traces}
                layout={{
                  height: 400,
                  margin: { t: 30, r: 30, b: 60, l: 60 },
                  barmode: 'stack',
                  xaxis: {
                    title: { text: consolidation === 'daily' ? 'Date' : consolidation === 'weekly' ? 'Week' : 'Month' },
                    tickangle: -45,
                  },
                  yaxis: { title: { text: 'Covers' } },
                  legend: {
                    orientation: 'h',
                    y: -0.2,
                    x: 0.5,
                    xanchor: 'center',
                  },
                  paper_bgcolor: 'transparent',
                  plot_bgcolor: 'transparent',
                  font: { color: colors.text },
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
          )}

          {/* Revenue Section */}
          {revenueChartData && spendSettings && (
            <>
              <h3 style={{ ...styles.sectionTitle, marginTop: spacing.xl }}>Net Revenue Forecast (exc VAT)</h3>

              {/* Revenue Summary */}
              {revenueSummary && (
                <div style={styles.summaryGrid}>
                  <div style={{ ...styles.summaryCard, background: colors.successBg }}>
                    <span style={styles.summaryLabel}>Forecast Net Revenue</span>
                    <span style={{ ...styles.summaryValue, color: colors.success }}>
                      £{revenueSummary.forecast.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                    <span style={styles.summarySubtext}>
                      vs LY: £{revenueSummary.prior.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      ({revenueSummary.varianceVsPrior >= 0 ? '+' : ''}{revenueSummary.varianceVsPrior.toFixed(0)}%)
                    </span>
                  </div>
                  {revenueSummary.budget > 0 && (
                    <div style={styles.summaryCard}>
                      <span style={styles.summaryLabel}>Budget</span>
                      <span style={styles.summaryValue}>
                        £{revenueSummary.budget.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </span>
                      <span style={{
                        ...styles.summarySubtext,
                        color: revenueSummary.varianceVsBudget >= 0 ? colors.success : colors.error
                      }}>
                        Forecast {revenueSummary.varianceVsBudget >= 0 ? '+' : ''}{revenueSummary.varianceVsBudget.toFixed(0)}% vs budget
                      </span>
                    </div>
                  )}
                  <div style={styles.summaryCard}>
                    <span style={styles.summaryLabel}>Net Spend/Cover</span>
                    <span style={styles.summaryValue} title={`Net (exc VAT):\nBreakfast: £${(((spendSettings.breakfast_food_spend || 0) + (spendSettings.breakfast_drinks_spend || 0)) / 1.20).toFixed(2)}\nLunch: £${(((spendSettings.lunch_food_spend || 0) + (spendSettings.lunch_drinks_spend || 0)) / 1.20).toFixed(2)}\nDinner: £${(((spendSettings.dinner_food_spend || 0) + (spendSettings.dinner_drinks_spend || 0)) / 1.20).toFixed(2)}`}>
                      £{summary ? (revenueSummary.forecast / summary.totalForecast).toFixed(0) : '-'}
                    </span>
                    <span style={styles.summarySubtext}>
                      weighted avg (exc VAT)
                    </span>
                  </div>
                </div>
              )}

              {/* Revenue Chart */}
              <div style={styles.chartContainer}>
                <Plot
                  data={revenueChartData.traces}
                  layout={{
                    height: 350,
                    margin: { t: 30, r: 30, b: 60, l: 70 },
                    xaxis: {
                      title: { text: consolidation === 'daily' ? 'Date' : consolidation === 'weekly' ? 'Week' : 'Month' },
                      tickangle: -45,
                    },
                    yaxis: {
                      title: { text: 'Revenue (£)' },
                      tickformat: ',.0f',
                      tickprefix: '£',
                    },
                    legend: {
                      orientation: 'h',
                      y: -0.2,
                      x: 0.5,
                      xanchor: 'center',
                    },
                    paper_bgcolor: 'transparent',
                    plot_bgcolor: 'transparent',
                    font: { color: colors.text },
                  }}
                  config={{ displayModeBar: false, responsive: true }}
                  style={{ width: '100%' }}
                />
              </div>
            </>
          )}

          {/* Table Toggle */}
          <button
            onClick={() => setShowTable(!showTable)}
            style={styles.tableToggle}
          >
            {showTable ? 'Hide Table' : 'Show Table'}
          </button>

          {/* Data Table */}
          {showTable && consolidation === 'daily' && forecastData?.data && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>Day</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Bfast</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Lunch</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Dinner Res</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Dinner Non-Res</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Dinner Total</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Total</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Hotel Occ</th>
                  </tr>
                </thead>
                <tbody>
                  {forecastData.data.map((row) => {
                    const todayStr = formatDate(new Date())
                    const isPast = row.date < todayStr
                    const isToday = row.date === todayStr

                    return (
                      <tr
                        key={row.date}
                        style={{
                          ...styles.tr,
                          background: isToday ? colors.infoBg :
                                     isPast ? colors.background : 'transparent',
                          opacity: isPast ? 0.7 : 1
                        }}
                      >
                        <td style={styles.td}>{row.date}</td>
                        <td style={styles.td}>{row.day_of_week}</td>
                        <td
                          style={{ ...styles.td, ...styles.tdRight, color: COVERS_COLORS.breakfast, cursor: row.breakfast_calc ? 'help' : 'default' }}
                          title={row.breakfast_calc ?
                            `Breakfast Calculation:\n` +
                            `─────────────────────\n` +
                            `Night before: ${row.breakfast_calc.night_before}\n` +
                            (row.breakfast_calc.source === 'pickupv2' ?
                              `Hotel rooms OTB: ${row.breakfast_calc.hotel_rooms_otb}\n` +
                              `Hotel guests OTB: ${row.breakfast_calc.hotel_guests_otb}\n` +
                              `Pickup rooms (pickupv2): ${row.breakfast_calc.pickup_rooms}\n` +
                              `× Guests/room: ${row.breakfast_calc.guests_per_room}\n` +
                              `= Pickup: ${row.breakfast_pickup} guests`
                              :
                              `Prior year guests: ${row.breakfast_calc.hotel_guests_prior}\n` +
                              `Source: ${row.breakfast_calc.source}`
                            )
                            : undefined}
                        >
                          {row.lead_days > 0 && row.breakfast_pickup > 0
                            ? `${row.breakfast_otb}+${row.breakfast_pickup}`
                            : row.breakfast_forecast}
                        </td>
                        <td
                          style={{ ...styles.td, ...styles.tdRight, fontWeight: typography.medium, cursor: row.lunch_calc ? 'help' : 'default' }}
                          title={row.lunch_calc ?
                            `Lunch Calculation:\n` +
                            `─────────────────────\n` +
                            `Day: ${row.lunch_calc.day_of_week}\n` +
                            `Lead days: ${row.lunch_calc.lead_days}\n` +
                            `Pace column: ${row.lunch_calc.pace_column}\n` +
                            `Lookback: ${row.lunch_calc.lookback_weeks} weeks\n` +
                            `─────────────────────\n` +
                            `Median pickup: ${row.lunch_calc.median_pickup}\n` +
                            `Source: ${row.lunch_calc.source}`
                            : undefined}
                        >
                          {row.lead_days > 0 && row.lunch_pickup > 0
                            ? `${row.lunch_otb}+${row.lunch_pickup}`
                            : row.lunch_forecast}
                        </td>
                        <td
                          style={{ ...styles.td, ...styles.tdRight, color: COVERS_COLORS.dinnerResident, cursor: row.dinner_resident_calc ? 'help' : 'default' }}
                          title={row.dinner_resident_calc ?
                            `Resident Dinner Calculation:\n` +
                            `─────────────────────\n` +
                            `Hotel Guests OTB: ${row.dinner_resident_calc.hotel_guests_otb}\n` +
                            `+ Pickup rooms: ${row.dinner_resident_calc.pickup_rooms}\n` +
                            `× Guests/room: ${row.dinner_resident_calc.guests_per_room}\n` +
                            `+ Pickup guests: ${row.dinner_resident_calc.pickup_guests}\n` +
                            `= Forecasted guests: ${row.dinner_resident_calc.forecasted_guests}\n` +
                            `─────────────────────\n` +
                            `Dining rate (${row.dinner_resident_calc.source}): ${row.dinner_resident_calc.dining_rate}%\n` +
                            `Forecasted resident covers: ${row.dinner_resident_calc.forecasted_resident_covers}\n` +
                            `- Resident OTB: ${row.dinner_resident_calc.resident_otb}\n` +
                            `= Pickup: ${row.dinner_resident_pickup} covers`
                            : undefined}
                        >
                          {row.lead_days > 0 && row.dinner_resident_pickup > 0
                            ? `${row.dinner_resident_otb}+${row.dinner_resident_pickup}` +
                              (row.dinner_resident_calc ? ` (${Math.round(row.dinner_resident_calc.forecasted_guests)})` : '')
                            : row.dinner_resident_otb}
                        </td>
                        <td
                          style={{ ...styles.td, ...styles.tdRight, color: COVERS_COLORS.dinnerNonResident, cursor: row.dinner_non_resident_calc ? 'help' : 'default' }}
                          title={row.dinner_non_resident_calc ?
                            `Non-Resident Dinner Calculation:\n` +
                            `─────────────────────\n` +
                            `Day: ${row.dinner_non_resident_calc.day_of_week}\n` +
                            `Lead days: ${row.dinner_non_resident_calc.lead_days}\n` +
                            `Pace column: ${row.dinner_non_resident_calc.pace_column}\n` +
                            `Lookback: ${row.dinner_non_resident_calc.lookback_weeks} weeks\n` +
                            `─────────────────────\n` +
                            `Median pickup: ${row.dinner_non_resident_calc.median_pickup}\n` +
                            `Source: ${row.dinner_non_resident_calc.source}`
                            : undefined}
                        >
                          {row.lead_days > 0 && row.dinner_non_resident_pickup > 0
                            ? `${row.dinner_non_resident_otb}+${row.dinner_non_resident_pickup}`
                            : row.dinner_non_resident_otb}
                        </td>
                        <td style={{ ...styles.td, ...styles.tdRight, fontWeight: typography.medium }}>
                          {row.dinner_forecast}
                        </td>
                        <td style={{ ...styles.td, ...styles.tdRight, fontWeight: typography.semibold, color: colors.accent }}>
                          {row.total_forecast}
                        </td>
                        <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                          {row.total_prior}
                        </td>
                        <td style={{ ...styles.td, ...styles.tdRight, color: colors.textMuted }}>
                          {row.hotel_occupancy_pct}%
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Consolidated Table */}
          {showTable && consolidation !== 'daily' && consolidatedData && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>{consolidation === 'weekly' ? 'Week' : 'Month'}</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Breakfast</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Lunch</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Dinner</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Total</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Yr</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Var %</th>
                  </tr>
                </thead>
                <tbody>
                  {consolidatedData.map((row) => (
                    <tr key={row.key} style={styles.tr}>
                      <td style={styles.td}>{row.label}</td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: COVERS_COLORS.breakfast }}>
                        {row.breakfastForecast.toLocaleString()}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight }}>
                        {row.lunchForecast.toLocaleString()}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight }}>
                        {row.dinnerForecast.toLocaleString()}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, fontWeight: typography.semibold, color: colors.accent }}>
                        {row.totalForecast.toLocaleString()}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.totalPrior.toLocaleString()}
                      </td>
                      <td style={{
                        ...styles.td,
                        ...styles.tdRight,
                        color: row.variancePct >= 0 ? colors.success : colors.error
                      }}>
                        {row.variancePct >= 0 ? '+' : ''}{row.variancePct.toFixed(1)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// RESTAURANT REVENUE FORECAST COMPONENT
// ============================================

interface RestaurantRevenueForecastProps {
  consolidation: 'daily' | 'weekly' | 'monthly'
  revenueType: 'dry' | 'wet'
}

const RestaurantRevenueForecast: React.FC<RestaurantRevenueForecastProps> = ({ consolidation, revenueType }) => {
  const token = localStorage.getItem('token')

  // Helper: get Monday of the week containing a date
  const getMondayOfWeek = (date: Date): Date => {
    const d = new Date(date)
    const day = d.getDay()
    const diff = day === 0 ? -6 : 1 - day
    d.setDate(d.getDate() + diff)
    d.setHours(0, 0, 0, 0)
    return d
  }

  // Helper: get financial year start (August)
  const getFinancialYearStart = (date: Date): string => {
    const year = date.getFullYear()
    const month = date.getMonth()
    const fyStartYear = month >= 7 ? year : year - 1  // Aug-Dec = same year, Jan-Jul = previous year
    return `${fyStartYear}-08`
  }

  // Generate month options (past 24 months + next 12 months for FY coverage)
  const monthOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const today = new Date()
    for (let i = -24; i <= 12; i++) {
      const date = new Date(today.getFullYear(), today.getMonth() + i, 1)
      options.push({
        value: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`,
        label: date.toLocaleString('default', { month: 'long', year: 'numeric' }),
      })
    }
    return options
  }, [])

  // Generate week options
  const weekOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const today = new Date()
    const currentMonday = getMondayOfWeek(today)
    for (let i = -26; i <= 26; i++) {
      const monday = new Date(currentMonday)
      monday.setDate(monday.getDate() + i * 7)
      const sunday = new Date(monday)
      sunday.setDate(monday.getDate() + 6)
      const weekD = new Date(monday)
      weekD.setDate(weekD.getDate() + 4 - (weekD.getDay() || 7))
      const yearStart = new Date(weekD.getFullYear(), 0, 1)
      const weekNum = Math.ceil((((weekD.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
      options.push({
        value: formatDate(monday),
        label: `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })})`,
      })
    }
    return options
  }, [])

  // State for date range
  const today = new Date()
  const [selectedMonth, setSelectedMonth] = useState(() => {
    // For monthly view, default to financial year start (August)
    if (consolidation === 'monthly') {
      return getFinancialYearStart(today)
    }
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  })
  const [selectedWeek, setSelectedWeek] = useState(() => formatDate(getMondayOfWeek(today)))
  // Daily view defaults to 1 month, monthly view defaults to 12 months (full FY)
  const [duration, setDuration] = useState<'1' | '3' | '6' | '12'>(consolidation === 'daily' ? '1' : '12')
  const [weekDuration, setWeekDuration] = useState<'4' | '8' | '13' | '26'>('13')  // Default 13 weeks for weekly
  const [useCustomDates, setUseCustomDates] = useState(false)
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')

  // Calculate date range
  const { startDate, endDate } = useMemo(() => {
    if (useCustomDates && customStartDate && customEndDate) {
      return { startDate: customStartDate, endDate: customEndDate }
    }
    if (consolidation === 'weekly') {
      const start = new Date(selectedWeek)
      const durationWeeks = parseInt(weekDuration)
      const end = new Date(start)
      end.setDate(start.getDate() + (durationWeeks * 7) - 1)
      return { startDate: formatDate(start), endDate: formatDate(end) }
    } else {
      const [year, month] = selectedMonth.split('-').map(Number)
      const start = new Date(year, month - 1, 1)
      const durationMonths = parseInt(duration)
      const end = new Date(year, month - 1 + durationMonths, 0)
      return { startDate: formatDate(start), endDate: formatDate(end) }
    }
  }, [selectedMonth, selectedWeek, duration, weekDuration, consolidation, useCustomDates, customStartDate, customEndDate])

  // Fetch revenue forecast (actual for past, forecast for future)
  const { data: revenueData, isLoading } = useQuery<{
    data: Array<{
      date: string
      day_of_week: string
      is_past: boolean
      actual_revenue: number
      otb_revenue: number
      pickup_revenue: number
      forecast_revenue: number
      prior_revenue: number
    }>
    summary: {
      actual_total: number
      prior_actual_total: number
      otb_total: number
      pickup_total: number
      forecast_remaining: number
      prior_future_total: number
      prior_year_total: number
      projected_total: number
      days_actual: number
      days_forecast: number
    }
  }>({
    queryKey: ['revenue-forecast', startDate, endDate, revenueType],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        revenue_type: revenueType
      })
      const response = await fetch(`/api/forecast/revenue-forecast?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch revenue forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch budgets for date range
  const budgetType = revenueType === 'dry' ? 'net_dry' : 'net_wet'
  const { data: budgetData } = useQuery({
    queryKey: ['fb-budgets-rev', startDate, endDate, budgetType],
    queryFn: async () => {
      const params = new URLSearchParams({ from_date: startDate, to_date: endDate, budget_type: budgetType })
      const response = await fetch(`/api/budget/daily?${params}`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!response.ok) return null
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Build consolidated data for weekly/monthly
  // Now uses actual revenue from DB for past, forecast for future
  const consolidatedData = useMemo(() => {
    if (!revenueData?.data || consolidation === 'daily') return null

    const groups: Record<string, {
      key: string
      label: string
      actualRevenue: number
      otbRevenue: number
      pickupRevenue: number
      priorRevenue: number
      budget: number
    }> = {}

    revenueData.data.forEach(d => {
      // Parse date string directly to avoid timezone issues
      const [year, month, day] = d.date.split('-').map(Number)
      let groupKey: string
      let groupLabel: string

      if (consolidation === 'weekly') {
        // Create date at noon local time to avoid timezone shifting
        const dateObj = new Date(year, month - 1, day, 12, 0, 0)
        const dayOfWeek = dateObj.getDay()
        const monday = new Date(dateObj)
        monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
        groupKey = formatDate(monday)
        const weekD = new Date(monday)
        weekD.setDate(weekD.getDate() + 4 - (weekD.getDay() || 7))
        const yearStart = new Date(weekD.getFullYear(), 0, 1)
        const weekNum = Math.ceil((((weekD.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
        groupLabel = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })})`
      } else {
        // Monthly: extract year-month directly from date string
        groupKey = `${year}-${String(month).padStart(2, '0')}`
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        groupLabel = `${monthNames[month - 1]} ${year}`
      }

      if (!groups[groupKey]) {
        groups[groupKey] = {
          key: groupKey,
          label: groupLabel,
          actualRevenue: 0,
          otbRevenue: 0,
          pickupRevenue: 0,
          priorRevenue: 0,
          budget: 0,
        }
      }

      // Past dates: use actual revenue from DB
      // Future dates: use OTB + pickup forecast
      if (d.is_past) {
        groups[groupKey].actualRevenue += d.actual_revenue
        groups[groupKey].otbRevenue += d.actual_revenue  // For chart display
      } else {
        groups[groupKey].otbRevenue += d.otb_revenue
        groups[groupKey].pickupRevenue += d.pickup_revenue
      }
      groups[groupKey].priorRevenue += d.prior_revenue
    })

    // Add budget data
    if (budgetData) {
      budgetData.forEach((b: any) => {
        // Parse date string directly to avoid timezone issues
        const [bYear, bMonth, bDay] = b.date.split('-').map(Number)
        let groupKey: string
        if (consolidation === 'weekly') {
          // Create date at noon local time to avoid timezone shifting
          const dateObj = new Date(bYear, bMonth - 1, bDay, 12, 0, 0)
          const dayOfWeek = dateObj.getDay()
          const monday = new Date(dateObj)
          monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
          groupKey = formatDate(monday)
        } else {
          // Monthly: extract year-month directly from date string
          groupKey = `${bYear}-${String(bMonth).padStart(2, '0')}`
        }
        if (groups[groupKey]) {
          groups[groupKey].budget += b.budget_value || 0
        }
      })
    }

    return Object.values(groups).sort((a, b) => a.key.localeCompare(b.key))
  }, [revenueData, consolidation, budgetData])

  // Build chart data with stacked Actual/OTB + Pickup bars
  const chartData = useMemo(() => {
    if (!revenueData?.data) return null

    const otbColor = revenueType === 'dry' ? colors.success : colors.info
    const pickupColor = revenueType === 'dry' ? '#4ade80' : '#67e8f9' // Lighter shade for pickup

    if (consolidation !== 'daily' && consolidatedData) {
      const labels = consolidatedData.map(d => d.label)
      const traces: any[] = [
        {
          x: labels,
          y: consolidatedData.map(d => d.otbRevenue),
          type: 'bar' as const,
          name: 'Actual/OTB',
          marker: { color: otbColor },
          hovertemplate: `Actual/OTB: £%{y:,.0f}<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => d.pickupRevenue),
          type: 'bar' as const,
          name: 'Pickup',
          marker: { color: pickupColor },
          hovertemplate: `Pickup: £%{y:,.0f}<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => d.priorRevenue),
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Prior Year',
          line: { color: COVERS_COLORS.priorYear, width: 2, dash: 'dot' as const },
          marker: { size: 6 },
          hovertemplate: `Prior Year: £%{y:,.0f}<extra></extra>`,
        },
      ]

      if (consolidatedData.some(d => d.budget > 0)) {
        traces.push({
          x: labels,
          y: consolidatedData.map(d => d.budget),
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Budget',
          line: { color: colors.warning, width: 2 },
          marker: { size: 6 },
          hovertemplate: `Budget: £%{y:,.0f}<extra></extra>`,
        })
      }

      return { traces, labels }
    }

    // Daily view - uses revenue data directly
    const dates = revenueData.data.map(d => d.date)

    // Build budget lookup
    const budgetByDate: Record<string, number> = {}
    if (budgetData) {
      budgetData.forEach((b: any) => {
        const budgetDate = typeof b.date === 'string' ? b.date.split('T')[0] : formatDate(new Date(b.date))
        budgetByDate[budgetDate] = b.budget_value || 0
      })
    }

    // For past: actual_revenue, for future: otb_revenue
    const otbRevenue = revenueData.data.map(d => d.is_past ? d.actual_revenue : d.otb_revenue)
    const pickupRevenue = revenueData.data.map(d => d.is_past ? 0 : d.pickup_revenue)
    const priorRevenue = revenueData.data.map(d => d.prior_revenue)
    const budgetValues = revenueData.data.map(d => budgetByDate[d.date] || 0)

    const traces: any[] = [
      {
        x: dates,
        y: otbRevenue,
        type: 'bar' as const,
        name: 'Actual/OTB',
        marker: { color: otbColor },
        hovertemplate: `Actual/OTB: £%{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: pickupRevenue,
        type: 'bar' as const,
        name: 'Pickup',
        marker: { color: pickupColor },
        hovertemplate: `Pickup: £%{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: priorRevenue,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Prior Year',
        line: { color: COVERS_COLORS.priorYear, width: 2, dash: 'dot' as const },
        marker: { size: 4 },
        hovertemplate: `Prior Year: £%{y:,.0f}<extra></extra>`,
      },
    ]

    if (budgetValues.some(v => v > 0)) {
      traces.push({
        x: dates,
        y: budgetValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Budget',
        line: { color: colors.warning, width: 2 },
        marker: { size: 4 },
        hovertemplate: `Budget: £%{y:,.0f}<extra></extra>`,
      })
    }

    return { traces, labels: dates }
  }, [revenueData, consolidatedData, consolidation, budgetData, revenueType])

  // Summary uses data from API - past is actual revenue, future is forecast
  const summary = useMemo(() => {
    if (!revenueData?.summary) return null

    const todayStr = formatDate(new Date())

    // Budget totals - normalize date format for comparison
    let totalBudget = 0
    let pastBudget = 0
    let futureBudget = 0
    if (budgetData && budgetData.length > 0) {
      budgetData.forEach((b: any) => {
        const budgetValue = b.budget_value || 0
        const budgetDate = typeof b.date === 'string' ? b.date.split('T')[0] : formatDate(new Date(b.date))
        totalBudget += budgetValue
        if (budgetDate < todayStr) {
          pastBudget += budgetValue
        } else {
          futureBudget += budgetValue
        }
      })
    }

    const s = revenueData.summary
    return {
      actualTotal: s.actual_total,
      priorActualTotal: s.prior_actual_total,
      pastBudget,
      futureOtbTotal: s.otb_total,
      priorFutureTotal: s.prior_future_total,
      futureBudget,
      otbPace: s.actual_total + s.otb_total,  // Actual + future OTB (no pickup)
      forecastRemainingTotal: s.forecast_remaining,
      projectedTotal: s.projected_total,
      priorYearTotal: s.prior_year_total,
      totalBudget,
      daysActual: s.days_actual,
      daysForecast: s.days_forecast,
    }
  }, [revenueData, budgetData])

  const title = revenueType === 'dry'
    ? `Restaurant Dry (Food) Revenue by ${consolidation === 'daily' ? 'Day' : consolidation === 'weekly' ? 'Week' : 'Month'}`
    : `Restaurant Wet (Drinks) Revenue by ${consolidation === 'daily' ? 'Day' : consolidation === 'weekly' ? 'Week' : 'Month'}`

  return (
    <div>
      <h2 style={styles.pageTitle}>{title}</h2>
      <p style={{ color: colors.textSecondary, marginBottom: spacing.lg, fontSize: typography.sm }}>
        Net revenue (exc VAT) - Actual from Newbook for past dates, forecast from covers × spend for future
      </p>

      {/* Controls - matching accommodation pages */}
      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.label}>From {consolidation === 'weekly' ? 'Week' : 'Month'}</label>
          {consolidation === 'weekly' ? (
            <select
              value={selectedWeek}
              onChange={(e) => { setSelectedWeek(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {weekOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          ) : (
            <select
              value={selectedMonth}
              onChange={(e) => { setSelectedMonth(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {monthOptions.map(opt => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          )}
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.label}>Duration</label>
          {consolidation === 'weekly' ? (
            <select
              value={weekDuration}
              onChange={(e) => { setWeekDuration(e.target.value as '4' | '8' | '13' | '26'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="4">4 Weeks</option>
              <option value="8">8 Weeks</option>
              <option value="13">13 Weeks (~3 Months)</option>
              <option value="26">26 Weeks (~6 Months)</option>
            </select>
          ) : (
            <select
              value={duration}
              onChange={(e) => { setDuration(e.target.value as '1' | '3' | '6' | '12'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="1">1 Month</option>
              <option value="3">3 Months</option>
              <option value="6">6 Months</option>
              <option value="12">1 Year</option>
            </select>
          )}
        </div>

        {/* Custom Date Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Custom Range</label>
          <div style={{ display: 'flex', gap: spacing.xs, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={useCustomDates}
              onChange={(e) => {
                setUseCustomDates(e.target.checked)
                if (e.target.checked && !customStartDate) {
                  setCustomStartDate(startDate)
                  setCustomEndDate(endDate)
                }
              }}
            />
            {useCustomDates && (
              <>
                <input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
                <span>to</span>
                <input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
              </>
            )}
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.label}>Period</label>
          <div style={{
            padding: `${spacing.sm} ${spacing.md}`,
            background: colors.surface,
            borderRadius: radius.md,
            fontSize: typography.sm,
            color: colors.text,
          }}>
            {startDate} to {endDate}
          </div>
        </div>
      </div>

      {isLoading ? (
        <div style={styles.loadingContainer}>Loading revenue forecast...</div>
      ) : !revenueData?.data?.length ? (
        <div style={styles.emptyContainer}>No data available for this period</div>
      ) : (
        <>
          {/* Summary Cards - 4 blocks matching accommodation pages */}
          {summary && (() => {
            const mainColor = revenueType === 'dry' ? colors.success : colors.info
            const fmt = (v: number) => `£${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`

            // Actual vs LY
            const actualDiff = summary.actualTotal - summary.priorActualTotal
            const actualPct = summary.priorActualTotal > 0 ? (actualDiff / summary.priorActualTotal) * 100 : 0
            // Actual vs Budget
            const actualVsBudgetDiff = summary.actualTotal - summary.pastBudget
            const actualVsBudgetPct = summary.pastBudget > 0 ? (actualVsBudgetDiff / summary.pastBudget) * 100 : 0

            // OTB Pace vs LY Total
            const otbVsLyDiff = summary.otbPace - summary.priorYearTotal
            const otbVsLyPct = summary.priorYearTotal > 0 ? (otbVsLyDiff / summary.priorYearTotal) * 100 : 0
            // OTB Pace vs Budget
            const otbVsBudgetDiff = summary.otbPace - summary.totalBudget
            const otbVsBudgetPct = summary.totalBudget > 0 ? (otbVsBudgetDiff / summary.totalBudget) * 100 : 0

            // Forecast Remaining vs LY
            const forecastDiff = summary.forecastRemainingTotal - summary.priorFutureTotal
            const forecastPct = summary.priorFutureTotal > 0 ? (forecastDiff / summary.priorFutureTotal) * 100 : 0
            // Forecast vs Future Budget
            const forecastVsBudgetDiff = summary.forecastRemainingTotal - summary.futureBudget
            const forecastVsBudgetPct = summary.futureBudget > 0 ? (forecastVsBudgetDiff / summary.futureBudget) * 100 : 0

            // Projected vs LY
            const projectedDiff = summary.projectedTotal - summary.priorYearTotal
            const projectedPct = summary.priorYearTotal > 0 ? (projectedDiff / summary.priorYearTotal) * 100 : 0
            // Projected vs Budget
            const projectedVsBudgetDiff = summary.projectedTotal - summary.totalBudget
            const projectedVsBudgetPct = summary.totalBudget > 0 ? (projectedVsBudgetDiff / summary.totalBudget) * 100 : 0

            return (
              <div style={styles.summaryGrid}>
                {/* Actual to Date */}
                <div style={styles.summaryCard}>
                  <span style={styles.summaryLabel}>ACTUAL TO DATE ({summary.daysActual} days)</span>
                  <span style={{ ...styles.summaryValue, color: mainColor }}>
                    {fmt(summary.actualTotal)}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: actualDiff >= 0 ? colors.success : colors.error }}>
                    vs LY: {fmt(summary.priorActualTotal)} ({actualDiff >= 0 ? '+' : ''}{fmt(actualDiff)}, {actualPct >= 0 ? '+' : ''}{actualPct.toFixed(0)}%)
                  </span>
                  {summary.pastBudget > 0 && (
                    <span style={{ ...styles.summarySubtext, color: actualVsBudgetDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                      vs Budget: {fmt(summary.pastBudget)} ({actualVsBudgetDiff >= 0 ? '+' : ''}{actualVsBudgetPct.toFixed(0)}%)
                    </span>
                  )}
                </div>

                {/* OTB Pace */}
                <div style={styles.summaryCard}>
                  <span style={styles.summaryLabel}>OTB PACE</span>
                  <span style={{ ...styles.summaryValue, color: '#9333ea' }}>
                    {fmt(summary.otbPace)}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: otbVsLyDiff >= 0 ? colors.success : colors.error }}>
                    vs LY Total: {fmt(summary.priorYearTotal)} ({otbVsLyDiff >= 0 ? '+' : ''}{fmt(otbVsLyDiff)}, {otbVsLyPct >= 0 ? '+' : ''}{otbVsLyPct.toFixed(0)}%)
                  </span>
                  {summary.totalBudget > 0 && (
                    <span style={{ ...styles.summarySubtext, color: otbVsBudgetDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                      vs Budget: {fmt(summary.totalBudget)} ({otbVsBudgetDiff >= 0 ? '+' : ''}{otbVsBudgetPct.toFixed(0)}%)
                    </span>
                  )}
                </div>

                {/* Forecast Remaining */}
                <div style={styles.summaryCard}>
                  <span style={styles.summaryLabel}>FORECAST REMAINING ({summary.daysForecast} days)</span>
                  <span style={{ ...styles.summaryValue, color: mainColor }}>
                    {fmt(summary.forecastRemainingTotal)}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: forecastDiff >= 0 ? colors.success : colors.error }}>
                    vs LY: {fmt(summary.priorFutureTotal)} ({forecastDiff >= 0 ? '+' : ''}{fmt(forecastDiff)}, {forecastPct >= 0 ? '+' : ''}{forecastPct.toFixed(0)}%)
                  </span>
                  {summary.futureBudget > 0 && (
                    <span style={{ ...styles.summarySubtext, color: forecastVsBudgetDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                      vs Budget: {fmt(summary.futureBudget)} ({forecastVsBudgetDiff >= 0 ? '+' : ''}{forecastVsBudgetPct.toFixed(0)}%)
                    </span>
                  )}
                </div>

                {/* Projected Total */}
                <div style={styles.summaryCard}>
                  <span style={styles.summaryLabel}>PROJECTED TOTAL</span>
                  <span style={{
                    ...styles.summaryValue,
                    color: projectedDiff >= 0 ? colors.success : colors.error,
                  }}>
                    {fmt(summary.projectedTotal)}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: projectedDiff >= 0 ? colors.success : colors.error }}>
                    vs LY: {fmt(summary.priorYearTotal)} ({projectedDiff >= 0 ? '+' : ''}{fmt(projectedDiff)}, {projectedPct >= 0 ? '+' : ''}{projectedPct.toFixed(0)}%)
                  </span>
                  {summary.totalBudget > 0 && (
                    <span style={{ ...styles.summarySubtext, color: projectedVsBudgetDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                      vs Budget: {fmt(summary.totalBudget)} ({projectedVsBudgetDiff >= 0 ? '+' : ''}{projectedVsBudgetPct.toFixed(0)}%)
                    </span>
                  )}
                </div>
              </div>
            )
          })()}

          {/* Chart */}
          {chartData && (
            <div style={styles.chartContainer}>
              <Plot
                data={chartData.traces}
                layout={{
                  height: 400,
                  margin: { t: 30, r: 30, b: 60, l: 70 },
                  barmode: 'stack',
                  xaxis: {
                    title: { text: consolidation === 'daily' ? 'Date' : consolidation === 'weekly' ? 'Week' : 'Month' },
                    tickangle: -45,
                  },
                  yaxis: {
                    title: { text: 'Revenue (£)' },
                    tickformat: ',.0f',
                    tickprefix: '£',
                  },
                  legend: {
                    orientation: 'h',
                    y: -0.2,
                    x: 0.5,
                    xanchor: 'center',
                  },
                  paper_bgcolor: 'transparent',
                  plot_bgcolor: 'transparent',
                  font: { color: colors.text },
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
          )}
        </>
      )}
    </div>
  )
}


// ============================================
// TOTAL REVENUE FORECAST (Combined: Accom + Dry + Wet)
// ============================================

interface TotalRevenueForecastProps {
  consolidation: 'daily' | 'weekly' | 'monthly'
}

const TotalRevenueForecast: React.FC<TotalRevenueForecastProps> = ({ consolidation }) => {
  const token = localStorage.getItem('token')

  // Helper: get Monday of the week containing a date
  const getMondayOfWeek = (date: Date): Date => {
    const d = new Date(date)
    const day = d.getDay()
    const diff = day === 0 ? -6 : 1 - day
    d.setDate(d.getDate() + diff)
    d.setHours(0, 0, 0, 0)
    return d
  }

  // Helper: get financial year start (August)
  const getFinancialYearStart = (date: Date): string => {
    const year = date.getFullYear()
    const month = date.getMonth()
    const fyStartYear = month >= 7 ? year : year - 1
    return `${fyStartYear}-08`
  }

  // Generate month options
  const monthOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const today = new Date()
    for (let i = -24; i <= 12; i++) {
      const date = new Date(today.getFullYear(), today.getMonth() + i, 1)
      options.push({
        value: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`,
        label: date.toLocaleString('default', { month: 'long', year: 'numeric' }),
      })
    }
    return options
  }, [])

  // Generate week options
  const weekOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const today = new Date()
    const currentMonday = getMondayOfWeek(today)
    for (let i = -26; i <= 26; i++) {
      const monday = new Date(currentMonday)
      monday.setDate(monday.getDate() + i * 7)
      const sunday = new Date(monday)
      sunday.setDate(monday.getDate() + 6)
      const weekD = new Date(monday)
      weekD.setDate(weekD.getDate() + 4 - (weekD.getDay() || 7))
      const yearStart = new Date(weekD.getFullYear(), 0, 1)
      const weekNum = Math.ceil((((weekD.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
      options.push({
        value: formatDate(monday),
        label: `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })})`,
      })
    }
    return options
  }, [])

  // State for date range
  const today = new Date()
  const [selectedMonth, setSelectedMonth] = useState(() => {
    if (consolidation === 'monthly') {
      return getFinancialYearStart(today)
    }
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  })
  const [selectedWeek, setSelectedWeek] = useState(() => formatDate(getMondayOfWeek(today)))
  // Daily view defaults to 1 month, monthly view defaults to 12 months (full FY)
  const [duration, setDuration] = useState<'1' | '3' | '6' | '12'>(consolidation === 'daily' ? '1' : '12')
  const [weekDuration, setWeekDuration] = useState<'4' | '8' | '13' | '26'>('13')
  const [useCustomDates, setUseCustomDates] = useState(false)
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')

  // Calculate date range
  const { startDate, endDate } = useMemo(() => {
    if (useCustomDates && customStartDate && customEndDate) {
      return { startDate: customStartDate, endDate: customEndDate }
    }
    if (consolidation === 'weekly') {
      const start = new Date(selectedWeek)
      const durationWeeks = parseInt(weekDuration)
      const end = new Date(start)
      end.setDate(start.getDate() + (durationWeeks * 7) - 1)
      return { startDate: formatDate(start), endDate: formatDate(end) }
    } else {
      const [year, month] = selectedMonth.split('-').map(Number)
      const start = new Date(year, month - 1, 1)
      const durationMonths = parseInt(duration)
      const end = new Date(year, month - 1 + durationMonths, 0)
      return { startDate: formatDate(start), endDate: formatDate(end) }
    }
  }, [selectedMonth, selectedWeek, duration, weekDuration, consolidation, useCustomDates, customStartDate, customEndDate])

  // Fetch combined revenue forecast
  const { data: revenueData, isLoading } = useQuery<{
    data: Array<{
      date: string
      day_of_week: string
      is_past: boolean
      actual_revenue: number
      otb_revenue: number
      pickup_revenue: number
      forecast_revenue: number
      prior_revenue: number
      actual_accom?: number
      actual_dry?: number
      actual_wet?: number
      otb_accom?: number
      otb_dry?: number
      otb_wet?: number
      pickup_accom?: number
      pickup_dry?: number
      pickup_wet?: number
    }>
    summary: {
      actual_total: number
      prior_actual_total: number
      otb_total: number
      pickup_total: number
      forecast_remaining: number
      prior_future_total: number
      prior_year_total: number
      projected_total: number
      days_actual: number
      days_forecast: number
    }
  }>({
    queryKey: ['combined-revenue-forecast', startDate, endDate],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
      })
      const response = await fetch(`/api/forecast/combined-revenue-forecast?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error('Failed to fetch combined revenue forecast')
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Fetch budget data - get all revenue budget types and sum them
  const { data: budgetData } = useQuery({
    queryKey: ['total-rev-budgets', startDate, endDate],
    queryFn: async () => {
      // Fetch all revenue budget types and sum them
      const budgetTypes = ['net_accom', 'net_dry', 'net_wet']
      const budgetByDate: Record<string, number> = {}

      for (const budgetType of budgetTypes) {
        const params = new URLSearchParams({ from_date: startDate, to_date: endDate, budget_type: budgetType })
        const response = await fetch(`/api/budget/daily?${params}`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (response.ok) {
          const data = await response.json()
          if (data && Array.isArray(data)) {
            data.forEach((b: { date: string; budget_value: number }) => {
              const dateKey = typeof b.date === 'string' ? b.date.split('T')[0] : b.date
              budgetByDate[dateKey] = (budgetByDate[dateKey] || 0) + (b.budget_value || 0)
            })
          }
        }
      }

      // Convert to array format
      return Object.entries(budgetByDate).map(([date, budget_value]) => ({
        date,
        budget_value
      }))
    },
    enabled: !!token && !!startDate && !!endDate,
  })

  // Build consolidated data for weekly/monthly views
  const consolidatedData = useMemo(() => {
    if (!revenueData?.data || consolidation === 'daily') return null

    const groups: Record<string, {
      key: string
      label: string
      actualRevenue: number
      otbRevenue: number
      pickupRevenue: number
      priorRevenue: number
      budget: number
    }> = {}

    revenueData.data.forEach(d => {
      const [year, month, day] = d.date.split('-').map(Number)
      let groupKey: string
      let groupLabel: string

      if (consolidation === 'weekly') {
        const dateObj = new Date(year, month - 1, day, 12, 0, 0)
        const dayOfWeek = dateObj.getDay()
        const monday = new Date(dateObj)
        monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
        groupKey = formatDate(monday)
        const weekD = new Date(monday)
        weekD.setDate(weekD.getDate() + 4 - (weekD.getDay() || 7))
        const yearStart = new Date(weekD.getFullYear(), 0, 1)
        const weekNum = Math.ceil((((weekD.getTime() - yearStart.getTime()) / 86400000) + 1) / 7)
        groupLabel = `W${weekNum} (${monday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })})`
      } else {
        groupKey = `${year}-${String(month).padStart(2, '0')}`
        const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        groupLabel = `${monthNames[month - 1]} ${year}`
      }

      if (!groups[groupKey]) {
        groups[groupKey] = {
          key: groupKey,
          label: groupLabel,
          actualRevenue: 0,
          otbRevenue: 0,
          pickupRevenue: 0,
          priorRevenue: 0,
          budget: 0,
        }
      }

      if (d.is_past) {
        groups[groupKey].actualRevenue += d.actual_revenue
        groups[groupKey].otbRevenue += d.actual_revenue
      } else {
        groups[groupKey].otbRevenue += d.otb_revenue
        groups[groupKey].pickupRevenue += d.pickup_revenue
      }
      groups[groupKey].priorRevenue += d.prior_revenue
    })

    // Add budget data
    if (budgetData) {
      budgetData.forEach((b: any) => {
        const [bYear, bMonth, bDay] = b.date.split('-').map(Number)
        let groupKey: string
        if (consolidation === 'weekly') {
          const dateObj = new Date(bYear, bMonth - 1, bDay, 12, 0, 0)
          const dayOfWeek = dateObj.getDay()
          const monday = new Date(dateObj)
          monday.setDate(dateObj.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1))
          groupKey = formatDate(monday)
        } else {
          groupKey = `${bYear}-${String(bMonth).padStart(2, '0')}`
        }
        if (groups[groupKey]) {
          groups[groupKey].budget += b.budget_value || 0
        }
      })
    }

    return Object.values(groups).sort((a, b) => a.key.localeCompare(b.key))
  }, [revenueData, consolidation, budgetData])

  // Build chart data with stacked bars
  const chartData = useMemo(() => {
    if (!revenueData?.data) return null

    if (consolidation !== 'daily' && consolidatedData) {
      const labels = consolidatedData.map(d => d.label)
      const traces: any[] = [
        {
          x: labels,
          y: consolidatedData.map(d => d.otbRevenue),
          type: 'bar' as const,
          name: 'Actual/OTB',
          marker: { color: colors.success },
          hovertemplate: `Actual/OTB: £%{y:,.0f}<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => d.pickupRevenue),
          type: 'bar' as const,
          name: 'Forecast (Pickup)',
          marker: { color: CHART_COLORS.blended },
          hovertemplate: `Forecast: £%{y:,.0f}<extra></extra>`,
        },
        {
          x: labels,
          y: consolidatedData.map(d => d.priorRevenue),
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Prior Year',
          line: { color: CHART_COLORS.priorFinal, width: 2, dash: 'dot' as const },
          marker: { size: 6 },
          hovertemplate: `Prior Year: £%{y:,.0f}<extra></extra>`,
        },
      ]

      if (consolidatedData.some(d => d.budget > 0)) {
        traces.push({
          x: labels,
          y: consolidatedData.map(d => d.budget),
          type: 'scatter' as const,
          mode: 'lines+markers' as const,
          name: 'Budget',
          line: { color: CHART_COLORS.budget, width: 2, dash: 'dash' as const },
          marker: { size: 6 },
          hovertemplate: `Budget: £%{y:,.0f}<extra></extra>`,
        })
      }

      return { traces, labels }
    }

    // Daily view
    const dates = revenueData.data.map(d => d.date)

    // Build budget lookup
    const budgetByDate: Record<string, number> = {}
    if (budgetData) {
      budgetData.forEach((b: any) => {
        const budgetDate = typeof b.date === 'string' ? b.date.split('T')[0] : formatDate(new Date(b.date))
        budgetByDate[budgetDate] = b.budget_value || 0
      })
    }

    const otbRevenue = revenueData.data.map(d => d.is_past ? d.actual_revenue : d.otb_revenue)
    const pickupRevenue = revenueData.data.map(d => d.is_past ? 0 : d.pickup_revenue)
    const priorRevenue = revenueData.data.map(d => d.prior_revenue)
    const budgetValues = revenueData.data.map(d => budgetByDate[d.date] || 0)

    const traces: any[] = [
      {
        x: dates,
        y: otbRevenue,
        type: 'bar' as const,
        name: 'Actual/OTB',
        marker: { color: colors.success },
        hovertemplate: `Actual/OTB: £%{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: pickupRevenue,
        type: 'bar' as const,
        name: 'Forecast (Pickup)',
        marker: { color: CHART_COLORS.blended },
        hovertemplate: `Forecast: £%{y:,.0f}<extra></extra>`,
      },
      {
        x: dates,
        y: priorRevenue,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Prior Year',
        line: { color: CHART_COLORS.priorFinal, width: 2, dash: 'dot' as const },
        marker: { size: 4 },
        hovertemplate: `Prior Year: £%{y:,.0f}<extra></extra>`,
      },
    ]

    if (budgetValues.some(v => v > 0)) {
      traces.push({
        x: dates,
        y: budgetValues,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'Budget',
        line: { color: CHART_COLORS.budget, width: 2, dash: 'dash' as const },
        marker: { size: 4 },
        hovertemplate: `Budget: £%{y:,.0f}<extra></extra>`,
      })
    }

    return { traces, labels: dates }
  }, [revenueData, consolidatedData, consolidation, budgetData])

  // Summary calculation
  const summary = useMemo(() => {
    if (!revenueData?.summary) return null

    const todayStr = formatDate(new Date())
    let totalBudget = 0
    let pastBudget = 0
    let futureBudget = 0
    if (budgetData && budgetData.length > 0) {
      budgetData.forEach((b: any) => {
        const budgetValue = b.budget_value || 0
        const budgetDate = typeof b.date === 'string' ? b.date.split('T')[0] : formatDate(new Date(b.date))
        totalBudget += budgetValue
        if (budgetDate < todayStr) {
          pastBudget += budgetValue
        } else {
          futureBudget += budgetValue
        }
      })
    }

    const s = revenueData.summary
    return {
      actualTotal: s.actual_total,
      priorActualTotal: s.prior_actual_total,
      pastBudget,
      futureOtbTotal: s.otb_total,
      priorFutureTotal: s.prior_future_total,
      futureBudget,
      otbPace: s.actual_total + s.otb_total,
      forecastRemainingTotal: s.forecast_remaining,
      projectedTotal: s.projected_total,
      priorYearTotal: s.prior_year_total,
      totalBudget,
      daysActual: s.days_actual,
      daysForecast: s.days_forecast,
    }
  }, [revenueData, budgetData])

  const title = `Combined Total Revenue by ${consolidation === 'daily' ? 'Day' : consolidation === 'weekly' ? 'Week' : 'Month'}`

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <h2 style={styles.sectionTitle}>{title}</h2>
        <p style={styles.hint}>
          Net revenue (exc VAT) - Accommodation + Dry (Food) + Wet (Drinks) combined. Actual from Newbook for past dates, forecast for future.
        </p>
      </div>

      {/* Controls - matching accommodation pages */}
      <div style={styles.controlsGrid}>
        {/* From Selector - Week-based for weekly, Month-based for daily/monthly */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>From {consolidation === 'weekly' ? 'Week' : 'Month'}</label>
          {consolidation === 'weekly' ? (
            <select
              value={selectedWeek}
              onChange={(e) => { setSelectedWeek(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {weekOptions.map((week) => (
                <option key={week.value} value={week.value}>{week.label}</option>
              ))}
            </select>
          ) : (
            <select
              value={selectedMonth}
              onChange={(e) => { setSelectedMonth(e.target.value); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              {monthOptions.map((month) => (
                <option key={month.value} value={month.value}>{month.label}</option>
              ))}
            </select>
          )}
        </div>

        {/* Duration Selector - Weeks for weekly, Months for daily/monthly */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Duration</label>
          {consolidation === 'weekly' ? (
            <select
              value={weekDuration}
              onChange={(e) => { setWeekDuration(e.target.value as '4' | '8' | '13' | '26'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="4">4 Weeks</option>
              <option value="8">8 Weeks</option>
              <option value="13">13 Weeks (~3 Months)</option>
              <option value="26">26 Weeks (~6 Months)</option>
            </select>
          ) : (
            <select
              value={duration}
              onChange={(e) => { setDuration(e.target.value as '1' | '3' | '6' | '12'); setUseCustomDates(false) }}
              style={styles.select}
              disabled={useCustomDates}
            >
              <option value="1">1 Month</option>
              <option value="3">3 Months</option>
              <option value="6">6 Months</option>
              <option value="12">1 Year</option>
            </select>
          )}
        </div>

        {/* Period Display */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Period</label>
          <div style={{
            padding: `${spacing.sm} ${spacing.md}`,
            background: colors.surface,
            borderRadius: radius.md,
            fontSize: typography.sm,
            color: colors.text,
          }}>
            {startDate} to {endDate}
          </div>
        </div>

        {/* Custom Date Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Custom Range</label>
          <div style={{ display: 'flex', gap: spacing.xs, alignItems: 'center' }}>
            <input
              type="checkbox"
              checked={useCustomDates}
              onChange={(e) => {
                setUseCustomDates(e.target.checked)
                if (e.target.checked && !customStartDate) {
                  setCustomStartDate(startDate)
                  setCustomEndDate(endDate)
                }
              }}
            />
            {useCustomDates && (
              <>
                <input
                  type="date"
                  value={customStartDate}
                  onChange={(e) => setCustomStartDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
                <span>to</span>
                <input
                  type="date"
                  value={customEndDate}
                  onChange={(e) => setCustomEndDate(e.target.value)}
                  style={{ ...styles.dateInput, width: '130px' }}
                />
              </>
            )}
          </div>
        </div>
      </div>

      {/* Loading state */}
      {isLoading ? (
        <div style={styles.emptyContainer}>Loading combined revenue data...</div>
      ) : (
        <>
          {/* Summary Cards - 4 blocks matching accommodation pages */}
          {summary && (() => {
            const fmt = (v: number) => `£${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`

            // Actual vs LY
            const actualDiff = summary.actualTotal - summary.priorActualTotal
            const actualPct = summary.priorActualTotal > 0 ? (actualDiff / summary.priorActualTotal) * 100 : 0
            // Actual vs Budget
            const actualVsBudgetDiff = summary.actualTotal - summary.pastBudget
            const actualVsBudgetPct = summary.pastBudget > 0 ? (actualVsBudgetDiff / summary.pastBudget) * 100 : 0

            // OTB Pace vs LY Total
            const otbVsLyDiff = summary.otbPace - summary.priorYearTotal
            const otbVsLyPct = summary.priorYearTotal > 0 ? (otbVsLyDiff / summary.priorYearTotal) * 100 : 0
            // OTB Pace vs Budget
            const otbVsBudgetDiff = summary.otbPace - summary.totalBudget
            const otbVsBudgetPct = summary.totalBudget > 0 ? (otbVsBudgetDiff / summary.totalBudget) * 100 : 0

            // Forecast Remaining vs LY
            const forecastDiff = summary.forecastRemainingTotal - summary.priorFutureTotal
            const forecastPct = summary.priorFutureTotal > 0 ? (forecastDiff / summary.priorFutureTotal) * 100 : 0
            // Forecast vs Future Budget
            const forecastVsBudgetDiff = summary.forecastRemainingTotal - summary.futureBudget
            const forecastVsBudgetPct = summary.futureBudget > 0 ? (forecastVsBudgetDiff / summary.futureBudget) * 100 : 0

            // Projected vs LY
            const projectedDiff = summary.projectedTotal - summary.priorYearTotal
            const projectedPct = summary.priorYearTotal > 0 ? (projectedDiff / summary.priorYearTotal) * 100 : 0
            // Projected vs Budget
            const projectedVsBudgetDiff = summary.projectedTotal - summary.totalBudget
            const projectedVsBudgetPct = summary.totalBudget > 0 ? (projectedVsBudgetDiff / summary.totalBudget) * 100 : 0

            return (
              <div style={styles.summaryGrid}>
                {/* Actual to Date */}
                <div style={styles.summaryCard}>
                  <span style={styles.summaryLabel}>ACTUAL TO DATE ({summary.daysActual} days)</span>
                  <span style={{ ...styles.summaryValue, color: colors.success }}>
                    {fmt(summary.actualTotal)}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: actualDiff >= 0 ? colors.success : colors.error }}>
                    vs LY: {fmt(summary.priorActualTotal)} ({actualDiff >= 0 ? '+' : ''}{fmt(actualDiff)}, {actualPct >= 0 ? '+' : ''}{actualPct.toFixed(0)}%)
                  </span>
                  {summary.pastBudget > 0 && (
                    <span style={{ ...styles.summarySubtext, color: actualVsBudgetDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                      vs Budget: {fmt(summary.pastBudget)} ({actualVsBudgetDiff >= 0 ? '+' : ''}{actualVsBudgetPct.toFixed(0)}%)
                    </span>
                  )}
                </div>

                {/* OTB Pace */}
                <div style={styles.summaryCard}>
                  <span style={styles.summaryLabel}>OTB PACE</span>
                  <span style={{ ...styles.summaryValue, color: '#9333ea' }}>
                    {fmt(summary.otbPace)}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: otbVsLyDiff >= 0 ? colors.success : colors.error }}>
                    vs LY Total: {fmt(summary.priorYearTotal)} ({otbVsLyDiff >= 0 ? '+' : ''}{fmt(otbVsLyDiff)}, {otbVsLyPct >= 0 ? '+' : ''}{otbVsLyPct.toFixed(0)}%)
                  </span>
                  {summary.totalBudget > 0 && (
                    <span style={{ ...styles.summarySubtext, color: otbVsBudgetDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                      vs Budget: {fmt(summary.totalBudget)} ({otbVsBudgetDiff >= 0 ? '+' : ''}{otbVsBudgetPct.toFixed(0)}%)
                    </span>
                  )}
                </div>

                {/* Forecast Remaining */}
                <div style={styles.summaryCard}>
                  <span style={styles.summaryLabel}>FORECAST REMAINING ({summary.daysForecast} days)</span>
                  <span style={{ ...styles.summaryValue, color: colors.success }}>
                    {fmt(summary.forecastRemainingTotal)}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: forecastDiff >= 0 ? colors.success : colors.error }}>
                    vs LY: {fmt(summary.priorFutureTotal)} ({forecastDiff >= 0 ? '+' : ''}{fmt(forecastDiff)}, {forecastPct >= 0 ? '+' : ''}{forecastPct.toFixed(0)}%)
                  </span>
                  {summary.futureBudget > 0 && (
                    <span style={{ ...styles.summarySubtext, color: forecastVsBudgetDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                      vs Budget: {fmt(summary.futureBudget)} ({forecastVsBudgetDiff >= 0 ? '+' : ''}{forecastVsBudgetPct.toFixed(0)}%)
                    </span>
                  )}
                </div>

                {/* Projected Total */}
                <div style={styles.summaryCard}>
                  <span style={styles.summaryLabel}>PROJECTED TOTAL</span>
                  <span style={{
                    ...styles.summaryValue,
                    color: projectedDiff >= 0 ? colors.success : colors.error,
                  }}>
                    {fmt(summary.projectedTotal)}
                  </span>
                  <span style={{ ...styles.summarySubtext, color: projectedDiff >= 0 ? colors.success : colors.error }}>
                    vs LY: {fmt(summary.priorYearTotal)} ({projectedDiff >= 0 ? '+' : ''}{fmt(projectedDiff)}, {projectedPct >= 0 ? '+' : ''}{projectedPct.toFixed(0)}%)
                  </span>
                  {summary.totalBudget > 0 && (
                    <span style={{ ...styles.summarySubtext, color: projectedVsBudgetDiff >= 0 ? colors.success : colors.error, marginTop: '2px' }}>
                      vs Budget: {fmt(summary.totalBudget)} ({projectedVsBudgetDiff >= 0 ? '+' : ''}{projectedVsBudgetPct.toFixed(0)}%)
                    </span>
                  )}
                </div>
              </div>
            )
          })()}

          {/* Chart */}
          {chartData && (
            <div style={styles.chartContainer}>
              <Plot
                data={chartData.traces}
                layout={{
                  height: 400,
                  margin: { t: 30, r: 30, b: 60, l: 70 },
                  barmode: 'stack',
                  xaxis: {
                    title: { text: consolidation === 'daily' ? 'Date' : consolidation === 'weekly' ? 'Week' : 'Month' },
                    tickangle: -45,
                  },
                  yaxis: {
                    title: { text: 'Revenue (£)' },
                    tickformat: ',.0f',
                    tickprefix: '£',
                  },
                  legend: {
                    orientation: 'h',
                    y: -0.2,
                    x: 0.5,
                    xanchor: 'center',
                  },
                  paper_bgcolor: 'transparent',
                  plot_bgcolor: 'transparent',
                  font: { color: colors.text },
                }}
                config={{ displayModeBar: false, responsive: true }}
                style={{ width: '100%' }}
              />
            </div>
          )}

          {/* Data Table */}
          {consolidatedData && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>{consolidation === 'weekly' ? 'Week' : 'Month'}</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Actual/OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Pickup</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Total</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Year</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>vs PY</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Budget</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>vs Budget</th>
                  </tr>
                </thead>
                <tbody>
                  {consolidatedData.map((row, idx) => {
                    const total = row.otbRevenue + row.pickupRevenue
                    const vsPY = row.priorRevenue > 0 ? ((total / row.priorRevenue) - 1) * 100 : 0
                    const vsBudget = row.budget > 0 ? ((total / row.budget) - 1) * 100 : 0
                    return (
                      <tr key={row.key} style={{ ...styles.tr, background: idx % 2 === 0 ? colors.background : 'transparent' }}>
                        <td style={styles.td}>{row.label}</td>
                        <td style={{ ...styles.td, ...styles.tdRight }}>£{row.otbRevenue.toLocaleString('en-GB', { maximumFractionDigits: 0 })}</td>
                        <td style={{ ...styles.td, ...styles.tdRight }}>£{row.pickupRevenue.toLocaleString('en-GB', { maximumFractionDigits: 0 })}</td>
                        <td style={{ ...styles.td, ...styles.tdRight, fontWeight: 'bold' }}>£{total.toLocaleString('en-GB', { maximumFractionDigits: 0 })}</td>
                        <td style={{ ...styles.td, ...styles.tdRight }}>£{row.priorRevenue.toLocaleString('en-GB', { maximumFractionDigits: 0 })}</td>
                        <td style={{ ...styles.td, ...styles.tdRight, color: vsPY >= 0 ? colors.success : colors.error }}>
                          {vsPY >= 0 ? '+' : ''}{vsPY.toFixed(1)}%
                        </td>
                        <td style={{ ...styles.td, ...styles.tdRight }}>
                          {row.budget > 0 ? `£${row.budget.toLocaleString('en-GB', { maximumFractionDigits: 0 })}` : '-'}
                        </td>
                        <td style={{ ...styles.td, ...styles.tdRight, color: vsBudget >= 0 ? colors.success : colors.error }}>
                          {row.budget > 0 ? `${vsBudget >= 0 ? '+' : ''}${vsBudget.toFixed(1)}%` : '-'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}


const styles: Record<string, React.CSSProperties> = {
  layout: {
    display: 'flex',
    gap: spacing.xl,
    padding: spacing.xl,
  },
  sidebar: {
    width: '200px',
    flexShrink: 0,
    background: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.md,
    boxShadow: shadows.md,
    height: 'fit-content',
    position: 'sticky',
    top: spacing.md,
  },
  sidebarTitle: {
    margin: `0 0 ${spacing.md} 0`,
    fontSize: typography.lg,
    color: colors.text,
    fontWeight: typography.semibold,
  },
  nav: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  navItem: {
    padding: `${spacing.sm} ${spacing.md}`,
    border: 'none',
    background: 'transparent',
    textAlign: 'left',
    cursor: 'pointer',
    borderRadius: radius.md,
    fontSize: typography.sm,
    color: colors.textSecondary,
    fontWeight: typography.normal,
    transition: 'all 0.15s ease',
  },
  navItemActive: {
    background: colors.accent,
    color: colors.textLight,
    fontWeight: typography.medium,
  },
  navSection: {
    padding: `${spacing.xs} ${spacing.sm}`,
    fontSize: typography.xs,
    fontWeight: typography.semibold,
    color: colors.textSecondary,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.5px',
    marginTop: spacing.xs,
  },
  navItemIndented: {
    paddingLeft: spacing.lg,
    fontSize: typography.sm,
  },
  content: {
    flex: 1,
    minWidth: 0,
  },
  section: {
    background: colors.surface,
    padding: spacing.lg,
    borderRadius: radius.xl,
    boxShadow: shadows.md,
  },
  sectionHeader: {
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    color: colors.text,
    margin: 0,
    marginBottom: spacing.xs,
    fontSize: typography.xxl,
    fontWeight: typography.semibold,
  },
  hint: {
    color: colors.textSecondary,
    margin: 0,
    fontSize: typography.sm,
  },
  controlsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: spacing.lg,
    marginBottom: spacing.lg,
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.lg,
  },
  controlGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  label: {
    fontSize: typography.xs,
    color: colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  dateInputs: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  dateInput: {
    padding: spacing.sm,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    fontSize: typography.sm,
    background: colors.surface,
    color: colors.text,
  },
  dateSeparator: {
    color: colors.textSecondary,
    fontSize: typography.sm,
  },
  toggleGroup: {
    display: 'flex',
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  toggleButton: {
    flex: 1,
    padding: `${spacing.sm} ${spacing.md}`,
    border: 'none',
    background: colors.surface,
    color: colors.textSecondary,
    fontSize: typography.sm,
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },
  toggleButtonActive: {
    background: colors.accent,
    color: colors.textLight,
  },
  dataTableToggle: {
    display: 'block',
    width: '100%',
    padding: `${spacing.sm} ${spacing.md}`,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    background: colors.surface,
    color: colors.textSecondary,
    fontSize: typography.sm,
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.15s ease',
    textAlign: 'center' as const,
  },
  quickSelectGroup: {
    display: 'flex',
    gap: spacing.xs,
  },
  quickSelectButton: {
    padding: `${spacing.xs} ${spacing.sm}`,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    background: colors.surface,
    color: colors.textSecondary,
    fontSize: typography.xs,
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },
  monthSelect: {
    padding: spacing.sm,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    background: colors.surface,
    color: colors.text,
    fontSize: typography.sm,
    cursor: 'pointer',
    minWidth: '140px',
  },
  select: {
    padding: spacing.sm,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    background: colors.surface,
    color: colors.text,
    fontSize: typography.sm,
    cursor: 'pointer',
    minWidth: '140px',
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    gap: spacing.md,
    marginBottom: spacing.lg,
  },
  summaryCard: {
    display: 'flex',
    flexDirection: 'column',
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.lg,
    textAlign: 'center',
  },
  summaryLabel: {
    fontSize: typography.xs,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: spacing.xs,
  },
  summaryValue: {
    fontSize: typography.xxl,
    fontWeight: typography.bold,
    color: colors.text,
  },
  summarySubtext: {
    fontSize: typography.xs,
    color: colors.textSecondary,
    marginTop: spacing.xs,
  },
  chartContainer: {
    marginBottom: spacing.lg,
  },
  loadingContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '300px',
    color: colors.textSecondary,
    fontSize: typography.base,
  },
  emptyContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '200px',
    color: colors.textMuted,
    fontSize: typography.base,
    background: colors.background,
    borderRadius: radius.md,
    marginBottom: spacing.lg,
  },
  tableToggle: {
    padding: `${spacing.sm} ${spacing.md}`,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    background: colors.surface,
    color: colors.textSecondary,
    fontSize: typography.sm,
    cursor: 'pointer',
    marginBottom: spacing.md,
  },
  tableContainer: {
    overflowX: 'auto',
    maxHeight: '400px',
    overflowY: 'auto',
    marginBottom: spacing.lg,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: typography.sm,
  },
  th: {
    padding: spacing.sm,
    textAlign: 'left',
    borderBottom: `2px solid ${colors.border}`,
    color: colors.textSecondary,
    fontWeight: typography.medium,
    position: 'sticky',
    top: 0,
    background: colors.surface,
    whiteSpace: 'nowrap',
  },
  thRight: {
    textAlign: 'right',
  },
  tr: {
    transition: 'background-color 0.1s ease',
  },
  td: {
    padding: spacing.sm,
    borderBottom: `1px solid ${colors.border}`,
    whiteSpace: 'nowrap',
  },
  tdRight: {
    textAlign: 'right',
  },
  paceButton: {
    padding: `${spacing.xs} ${spacing.sm}`,
    border: 'none',
    borderRadius: radius.sm,
    background: colors.accent,
    color: colors.textLight,
    fontSize: typography.xs,
    cursor: 'pointer',
  },
  paceCurveSection: {
    marginTop: spacing.lg,
    padding: spacing.lg,
    background: colors.background,
    borderRadius: radius.lg,
  },
  paceCurveTitle: {
    margin: 0,
    marginBottom: spacing.xs,
    fontSize: typography.lg,
    fontWeight: typography.semibold,
    color: colors.text,
  },
}

export default Forecasts
