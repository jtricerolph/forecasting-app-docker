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

type ForecastPage = 'preview' | 'prophet' | 'xgboost' | 'tft' | 'compare'

// Consistent forecast model colors
const CHART_COLORS = {
  currentOtb: '#10b981',      // Green - confirmed/safe bookings
  pickup: '#ef4444',          // Red - pickup forecast
  prophet: '#3b82f6',         // Blue - prophet forecast
  prophetConfidence: 'rgba(59, 130, 246, 0.15)', // Light blue fill
  xgboost: '#f97316',         // Orange - xgboost forecast
  tft: '#9467bd',             // Purple - TFT forecast
  tftConfidence: 'rgba(148, 103, 189, 0.15)', // Light purple fill
  priorOtb: '#9ca3af',        // Gray dashed
  priorFinal: '#6b7280',      // Darker gray dotted
  priorFinalFill: 'rgba(107, 114, 128, 0.1)',
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

interface TFTDataPoint {
  date: string
  day_of_week: string
  current_otb: number | null
  prior_year_otb: number | null
  forecast: number | null
  forecast_lower: number | null
  forecast_upper: number | null
  prior_year_final: number | null
}

interface TFTSummary {
  otb_total: number
  prior_otb_total: number
  forecast_total: number
  prior_final_total: number
  days_count: number
  days_forecasting_more: number
  days_forecasting_less: number
}

interface TFTResponse {
  data: TFTDataPoint[]
  summary: TFTSummary
}

interface TFTModel {
  id: number
  metric_code: string
  model_name: string
  is_active: boolean
  trained_at: string
  validation_loss: number | null
}

const Forecasts: React.FC = () => {
  const { forecastId } = useParams<{ forecastId?: string }>()
  const navigate = useNavigate()
  const activePage = (forecastId as ForecastPage) || 'preview'

  const menuItems: { id: ForecastPage; label: string }[] = [
    { id: 'preview', label: 'Live Pickup' },
    { id: 'prophet', label: 'Live Prophet' },
    { id: 'xgboost', label: 'Live XGBoost' },
    { id: 'tft', label: 'Live TFT' },
    { id: 'compare', label: 'Compare Models' },
  ]

  const handlePageChange = (id: ForecastPage) => {
    navigate(`/forecasts/${id}`)
  }

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        <h3 style={styles.sidebarTitle}>Forecasts</h3>
        <nav style={styles.nav}>
          {menuItems.map((item) => (
            <button
              key={item.id}
              onClick={() => handlePageChange(item.id)}
              style={{
                ...styles.navItem,
                ...(activePage === item.id ? styles.navItemActive : {}),
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      <main style={styles.content}>
        {activePage === 'preview' && <ForecastPreview />}
        {activePage === 'prophet' && <ProphetPreview />}
        {activePage === 'xgboost' && <XGBoostPreview />}
        {activePage === 'tft' && <TFTPreview />}
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
  const [metric, setMetric] = useState<'occupancy' | 'rooms'>('rooms')
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

    const unit = metric === 'occupancy' ? '%' : ' rooms'

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
    ]
  }, [previewData, metric])

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

  const metricLabel = metric === 'occupancy' ? 'Occupancy %' : 'Room Nights'

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

        {/* Metric Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <div style={styles.toggleGroup}>
            {(['occupancy', 'rooms'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                style={{
                  ...styles.toggleButton,
                  ...(metric === m ? styles.toggleButtonActive : {}),
                }}
              >
                {m === 'occupancy' ? 'Occupancy %' : 'Room Nights'}
              </button>
            ))}
          </div>
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
        const days = previewData.summary.days_count
        const otbAvg = metric === 'occupancy' ? previewData.summary.otb_total / days : previewData.summary.otb_total
        const priorOtbAvg = metric === 'occupancy' ? previewData.summary.prior_otb_total / days : previewData.summary.prior_otb_total
        const forecastAvg = metric === 'occupancy' ? previewData.summary.forecast_total / days : previewData.summary.forecast_total
        const priorFinalAvg = metric === 'occupancy' ? previewData.summary.prior_final_total / days : previewData.summary.prior_final_total
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
  const [metric, setMetric] = useState<'occupancy' | 'rooms'>('rooms')
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

    const unit = metric === 'occupancy' ? '%' : ' rooms'

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
    ]
  }, [prophetData, metric])

  const metricLabel = metric === 'occupancy' ? 'Occupancy %' : 'Room Nights'

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

        {/* Metric Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <div style={styles.toggleGroup}>
            {(['occupancy', 'rooms'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                style={{
                  ...styles.toggleButton,
                  ...(metric === m ? styles.toggleButtonActive : {}),
                }}
              >
                {m === 'occupancy' ? 'Occupancy %' : 'Room Nights'}
              </button>
            ))}
          </div>
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
        const days = prophetData.summary.days_count
        const otbAvg = metric === 'occupancy' ? prophetData.summary.otb_total / days : prophetData.summary.otb_total
        const priorOtbAvg = metric === 'occupancy' ? prophetData.summary.prior_otb_total / days : prophetData.summary.prior_otb_total
        const forecastAvg = metric === 'occupancy' ? prophetData.summary.forecast_total / days : prophetData.summary.forecast_total
        const priorFinalAvg = metric === 'occupancy' ? prophetData.summary.prior_final_total / days : prophetData.summary.prior_final_total
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
  const [metric, setMetric] = useState<'occupancy' | 'rooms'>('rooms')
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

  const metricLabel = metric === 'occupancy' ? 'Occupancy %' : 'Room Nights'
  const unit = metric === 'occupancy' ? '%' : ' rooms'

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
    ]
  }, [xgboostData, unit])

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

        {/* Metric Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <div style={styles.toggleGroup}>
            {(['occupancy', 'rooms'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                style={{
                  ...styles.toggleButton,
                  ...(metric === m ? styles.toggleButtonActive : {}),
                }}
              >
                {m === 'occupancy' ? 'Occupancy %' : 'Room Nights'}
              </button>
            ))}
          </div>
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
        const days = xgboostData.summary.days_count
        const otbAvg = metric === 'occupancy' ? xgboostData.summary.otb_total / days : xgboostData.summary.otb_total
        const priorOtbAvg = metric === 'occupancy' ? xgboostData.summary.prior_otb_total / days : xgboostData.summary.prior_otb_total
        const forecastAvg = metric === 'occupancy' ? xgboostData.summary.forecast_total / days : xgboostData.summary.forecast_total
        const priorFinalAvg = metric === 'occupancy' ? xgboostData.summary.prior_final_total / days : xgboostData.summary.prior_final_total
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
// TFT PREVIEW COMPONENT
// ============================================

const TFTPreview: React.FC = () => {
  const token = localStorage.getItem('token')

  // Default to next 30 days, rooms metric (matching other pages)
  const today = new Date()
  const defaultStart = new Date(today)
  defaultStart.setDate(today.getDate() + 1)
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() + 30)

  const [startDate, setStartDate] = useState(defaultStart.toISOString().split('T')[0])
  const [endDate, setEndDate] = useState(defaultEnd.toISOString().split('T')[0])
  const [metric, setMetric] = useState<'occupancy' | 'rooms'>('rooms')
  const [showTable, setShowTable] = useState(false)
  const [selectedModelId, setSelectedModelId] = useState<number | null>(null)
  const [shouldFetch, setShouldFetch] = useState(false)

  // Fetch available TFT models
  const { data: tftModels } = useQuery<TFTModel[]>({
    queryKey: ['tft-models'],
    queryFn: async () => {
      const response = await fetch('/api/config/tft-models', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: !!token,
    staleTime: 60000, // Cache for 1 minute
  })

  // Filter models for current metric
  const metricCode = metric === 'occupancy' ? 'hotel_occupancy_pct' : 'hotel_room_nights'
  const availableModels = tftModels?.filter(m => m.metric_code === metricCode) ?? []

  // Reset state when metric changes
  const handleMetricChange = (newMetric: 'occupancy' | 'rooms') => {
    setMetric(newMetric)
    setSelectedModelId(null)
    setShouldFetch(false)
  }

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

  // Fetch TFT forecast data
  const { data: tftData, isLoading: tftLoading, error: tftError } = useQuery<TFTResponse>({
    queryKey: ['tft-preview', startDate, endDate, metric, selectedModelId],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        metric: metric,
      })
      if (selectedModelId) {
        params.append('model_id', selectedModelId.toString())
      }
      const response = await fetch(`/api/forecast/tft-preview?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to fetch TFT forecast')
      }
      return response.json()
    },
    enabled: !!token && !!startDate && !!endDate && shouldFetch && availableModels.length > 0,
    retry: false,  // TFT can take time, don't retry automatically
  })

  const hasModels = availableModels.length > 0
  const metricLabel = metric === 'occupancy' ? 'Occupancy %' : 'Room Nights'
  const unit = metric === 'occupancy' ? '%' : ' rooms'

  // Build TFT chart data with confidence intervals
  const tftChartData = useMemo(() => {
    if (!tftData?.data) return []

    const dates = tftData.data.map((d) => d.date)
    const currentOtb = tftData.data.map((d) => d.current_otb)
    const priorYearOtb = tftData.data.map((d) => d.prior_year_otb)
    const forecast = tftData.data.map((d) => d.forecast)
    const forecastLower = tftData.data.map((d) => d.forecast_lower)
    const forecastUpper = tftData.data.map((d) => d.forecast_upper)
    const priorYearFinal = tftData.data.map((d) => d.prior_year_final)

    // Calculate prior year dates
    const priorDates = tftData.data.map((d) => {
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
      // TFT confidence interval (upper bound)
      {
        x: dates,
        y: forecastUpper,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'TFT Upper (90%)',
        line: { color: CHART_COLORS.tft, width: 0 },
        showlegend: false,
        hoverinfo: 'skip' as const,
      },
      // TFT confidence interval (lower bound with fill)
      {
        x: dates,
        y: forecastLower,
        type: 'scatter' as const,
        mode: 'lines' as const,
        name: 'TFT 80% CI',
        line: { color: CHART_COLORS.tft, width: 0 },
        fill: 'tonexty' as const,
        fillcolor: CHART_COLORS.tftConfidence,
        hoverinfo: 'skip' as const,
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
      // TFT forecast - purple
      {
        x: dates,
        y: forecast,
        type: 'scatter' as const,
        mode: 'lines+markers' as const,
        name: 'TFT Forecast',
        line: { color: CHART_COLORS.tft, width: 3 },
        marker: { size: 8, symbol: 'diamond' },
        customdata: tftData.data.map((d) => [d.forecast_lower, d.forecast_upper]),
        hovertemplate: `TFT: %{y:.1f}${unit}<br>Range: %{customdata[0]:.1f} - %{customdata[1]:.1f}<extra></extra>`,
      },
    ]
  }, [tftData, unit])

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Live TFT</h2>
          <p style={styles.hint}>
            Temporal Fusion Transformer with attention-based explainability and uncertainty quantiles
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.sm }}>
          <label style={{ ...styles.label, marginBottom: 0 }}>Model:</label>
          <select
            value={selectedModelId ?? ''}
            onChange={(e) => setSelectedModelId(e.target.value ? Number(e.target.value) : null)}
            style={{ ...styles.monthSelect, minWidth: '180px' }}
            disabled={availableModels.length === 0}
          >
            <option value="">Active Model</option>
            {availableModels.map(m => (
              <option key={m.id} value={m.id}>
                {m.model_name || `Model ${m.id}`}{m.is_active ? ' (active)' : ''}
              </option>
            ))}
          </select>
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
              onChange={(e) => { setStartDate(e.target.value); setShouldFetch(false) }}
              style={styles.dateInput}
            />
            <span style={styles.dateSeparator}>to</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => { setEndDate(e.target.value); setShouldFetch(false) }}
              style={styles.dateInput}
            />
          </div>
        </div>

        {/* Metric Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <div style={styles.toggleGroup}>
            {(['occupancy', 'rooms'] as const).map((m) => (
              <button
                key={m}
                onClick={() => handleMetricChange(m)}
                style={{
                  ...styles.toggleButton,
                  ...(metric === m ? styles.toggleButtonActive : {}),
                }}
              >
                {m === 'occupancy' ? 'Occupancy %' : 'Room Nights'}
              </button>
            ))}
          </div>
        </div>

        {/* Quick Selects */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Quick Select</label>
          <div style={styles.quickSelectGroup}>
            {[7, 14, 30, 60, 90].map((days) => (
              <button
                key={days}
                onClick={() => { handleQuickSelect(days); setShouldFetch(false) }}
                style={styles.quickSelectButton}
              >
                {days}d
              </button>
            ))}
          </div>
          <select
            onChange={(e) => { handleMonthSelect(e.target.value); setShouldFetch(false) }}
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

        {/* Generate Button */}
        <div style={{ ...styles.controlGroup, display: 'flex', alignItems: 'flex-end' }}>
          <button
            onClick={() => setShouldFetch(true)}
            disabled={!hasModels || tftLoading}
            style={{
              ...styles.quickSelectButton,
              padding: `${spacing.sm} ${spacing.lg}`,
              background: hasModels ? colors.primary : colors.textMuted,
              color: '#fff',
              fontWeight: typography.semibold,
              cursor: hasModels ? 'pointer' : 'not-allowed',
              opacity: hasModels ? 1 : 0.5,
            }}
          >
            {tftLoading ? 'Loading...' : 'Generate'}
          </button>
        </div>
      </div>

      {/* No Models Warning */}
      {!hasModels && (
        <div style={{ ...styles.loadingContainer, background: '#fff7ed', border: `1px solid #fed7aa` }}>
          <p style={{ ...styles.loadingText, color: '#ea580c' }}>
            No trained TFT models available for {metricLabel}. Train a model in Settings → TFT Training first.
          </p>
        </div>
      )}

      {/* Loading and Error States */}
      {tftLoading && (
        <div style={styles.loadingContainer}>
          <div style={styles.spinner} />
          <p style={styles.loadingText}>Loading TFT forecast...</p>
        </div>
      )}

      {tftError && (
        <div style={styles.errorContainer}>
          <p style={styles.errorText}>Error: {(tftError as Error).message}</p>
          <p style={styles.hint}>
            TFT requires at least 90 days of historical data and PyTorch dependencies.
          </p>
        </div>
      )}

      {/* Summary Cards */}
      {tftData && (
        <>
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>TFT Forecast</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.tft }}>
                {tftData.summary.forecast_total?.toFixed(1) ?? '-'}{unit}
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>Current OTB</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.currentOtb }}>
                {tftData.summary.otb_total?.toFixed(1) ?? '-'}{unit}
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>Prior Year Final</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.priorFinal }}>
                {tftData.summary.prior_final_total?.toFixed(1) ?? '-'}{unit}
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>Days Ahead of PY</span>
              <span style={styles.summaryValue}>
                {tftData.summary.days_forecasting_more ?? 0} / {tftData.summary.days_count ?? 0}
              </span>
            </div>
          </div>

          {/* Chart */}
          <div style={styles.chartContainer}>
            <Plot
              data={tftChartData}
              layout={{
                autosize: true,
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
                  rangemode: 'tozero',
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
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </div>

          {/* Data Table Toggle */}
          <button
            onClick={() => setShowTable(!showTable)}
            style={styles.tableToggle}
          >
            {showTable ? '▼ Hide Data Table' : '▶ Show Data Table'}
          </button>

          {showTable && (
            <div style={styles.tableContainer}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Date</th>
                    <th style={styles.th}>DOW</th>
                    <th style={styles.th}>Current OTB</th>
                    <th style={styles.th}>TFT Forecast</th>
                    <th style={styles.th}>TFT Lower</th>
                    <th style={styles.th}>TFT Upper</th>
                    <th style={styles.th}>Prior Year</th>
                  </tr>
                </thead>
                <tbody>
                  {tftData.data.map((row) => (
                    <tr key={row.date}>
                      <td style={styles.td}>{row.date}</td>
                      <td style={styles.td}>{row.day_of_week}</td>
                      <td style={styles.td}>{row.current_otb?.toFixed(1) ?? '-'}</td>
                      <td style={{ ...styles.td, color: CHART_COLORS.tft, fontWeight: 600 }}>
                        {row.forecast?.toFixed(1) ?? '-'}
                      </td>
                      <td style={styles.td}>{row.forecast_lower?.toFixed(1) ?? '-'}</td>
                      <td style={styles.td}>{row.forecast_upper?.toFixed(1) ?? '-'}</td>
                      <td style={styles.td}>{row.prior_year_final?.toFixed(1) ?? '-'}</td>
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
  const [metric, setMetric] = useState<'occupancy' | 'rooms'>('rooms')
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

  const isLoading = pickupLoading || prophetLoading || xgboostLoading
  const metricLabel = metric === 'occupancy' ? 'Occupancy %' : 'Room Nights'
  const unit = metric === 'occupancy' ? '%' : ' rooms'

  // Merge all data into comparison chart
  const compareChartData = useMemo(() => {
    if (!pickupData?.data || !prophetData?.data || !xgboostData?.data) return []

    const dates = pickupData.data.map((d) => d.date)
    const currentOtb = pickupData.data.map((d) => d.current_otb)
    const priorYearOtb = pickupData.data.map((d) => d.prior_year_otb)
    const priorYearFinal = pickupData.data.map((d) => d.prior_year_final)
    const pickupForecast = pickupData.data.map((d) => d.forecast)
    const prophetForecast = prophetData.data.map((d) => d.forecast)
    const xgboostForecast = xgboostData.data.map((d) => d.forecast)

    // Calculate prior year dates
    const priorDates = pickupData.data.map((d) => {
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
      },
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
    ]
  }, [pickupData, prophetData, xgboostData, unit])

  // Merge data for table
  const tableData = useMemo(() => {
    if (!pickupData?.data || !prophetData?.data || !xgboostData?.data) return []

    return pickupData.data.map((pickup, idx) => ({
      date: pickup.date,
      day_of_week: pickup.day_of_week,
      current_otb: pickup.current_otb,
      prior_year_otb: pickup.prior_year_otb,
      prior_year_final: pickup.prior_year_final,
      pickup_forecast: pickup.forecast,
      prophet_forecast: prophetData.data[idx]?.forecast ?? null,
      xgboost_forecast: xgboostData.data[idx]?.forecast ?? null,
    }))
  }, [pickupData, prophetData, xgboostData])

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Compare Forecast Models</h2>
          <p style={styles.hint}>
            Side-by-side comparison of Pickup, Prophet, and XGBoost forecasts
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

        {/* Metric Toggle */}
        <div style={styles.controlGroup}>
          <label style={styles.label}>Metric</label>
          <div style={styles.toggleGroup}>
            {(['occupancy', 'rooms'] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                style={{
                  ...styles.toggleButton,
                  ...(metric === m ? styles.toggleButtonActive : {}),
                }}
              >
                {m === 'occupancy' ? 'Occupancy %' : 'Room Nights'}
              </button>
            ))}
          </div>
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
      {pickupData?.summary && prophetData?.summary && xgboostData?.summary && (() => {
        const days = pickupData.summary.days_count
        const pickupAvg = metric === 'occupancy' ? pickupData.summary.forecast_total / days : pickupData.summary.forecast_total
        const prophetAvg = metric === 'occupancy' ? prophetData.summary.forecast_total / days : prophetData.summary.forecast_total
        const xgboostAvg = metric === 'occupancy' ? xgboostData.summary.forecast_total / days : xgboostData.summary.forecast_total
        const priorFinalAvg = metric === 'occupancy' ? pickupData.summary.prior_final_total / days : pickupData.summary.prior_final_total

        return (
          <div style={styles.summaryGrid}>
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
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>PROPHET</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.prophet }}>
                {metric === 'occupancy' ? `${prophetAvg.toFixed(1)}%` : prophetAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: prophetAvg >= priorFinalAvg ? colors.success : colors.error,
              }}>
                vs Prior: {prophetAvg >= priorFinalAvg ? '+' : ''}{metric === 'occupancy' ? `${(prophetAvg - priorFinalAvg).toFixed(1)}%` : (prophetAvg - priorFinalAvg).toFixed(0)}
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>XGBOOST</span>
              <span style={{ ...styles.summaryValue, color: CHART_COLORS.xgboost }}>
                {metric === 'occupancy' ? `${xgboostAvg.toFixed(1)}%` : xgboostAvg.toFixed(0)}
              </span>
              <span style={{
                ...styles.summarySubtext,
                color: xgboostAvg >= priorFinalAvg ? colors.success : colors.error,
              }}>
                vs Prior: {xgboostAvg >= priorFinalAvg ? '+' : ''}{metric === 'occupancy' ? `${(xgboostAvg - priorFinalAvg).toFixed(1)}%` : (xgboostAvg - priorFinalAvg).toFixed(0)}
              </span>
            </div>
            <div style={styles.summaryCard}>
              <span style={styles.summaryLabel}>PRIOR YR FINAL</span>
              <span style={styles.summaryValue}>
                {metric === 'occupancy' ? `${priorFinalAvg.toFixed(1)}%` : priorFinalAvg.toFixed(0)}
              </span>
              <span style={styles.summarySubtext}>baseline comparison</span>
            </div>
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
                    <th style={{ ...styles.th, ...styles.thRight }}>OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior OTB</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prior Final</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Pickup</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>Prophet</th>
                    <th style={{ ...styles.th, ...styles.thRight }}>XGBoost</th>
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
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.currentOtb }}>
                        {row.current_otb !== null ? row.current_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textSecondary }}>
                        {row.prior_year_otb !== null ? row.prior_year_otb.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: colors.textMuted }}>
                        {row.prior_year_final !== null ? row.prior_year_final.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.pickup, fontWeight: typography.semibold }}>
                        {row.pickup_forecast !== null ? row.pickup_forecast.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.prophet, fontWeight: typography.semibold }}>
                        {row.prophet_forecast !== null ? row.prophet_forecast.toFixed(1) : '-'}
                      </td>
                      <td style={{ ...styles.td, ...styles.tdRight, color: CHART_COLORS.xgboost, fontWeight: typography.semibold }}>
                        {row.xgboost_forecast !== null ? row.xgboost_forecast.toFixed(1) : '-'}
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
