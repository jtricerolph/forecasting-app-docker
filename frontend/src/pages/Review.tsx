import React, { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  colors,
  spacing,
  radius,
  typography,
  shadows,
} from '../utils/theme'
import Plot from 'react-plotly.js'

type ReportPage = 'occupancy' | 'bookings' | 'rates' | 'ave_rate' | 'revenue'

const Review: React.FC = () => {
  const { reportId } = useParams<{ reportId?: string }>()
  const navigate = useNavigate()
  const activePage = (reportId as ReportPage) || 'occupancy'

  const menuItems: { id: ReportPage; label: string }[] = [
    { id: 'occupancy', label: 'Occupancy' },
    { id: 'bookings', label: 'Bookings' },
    { id: 'rates', label: 'Rate Totals' },
    { id: 'ave_rate', label: 'Ave Rate' },
    { id: 'revenue', label: 'Revenue' },
  ]

  const handlePageChange = (id: ReportPage) => {
    navigate(`/review/${id}`)
  }

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        <h3 style={styles.sidebarTitle}>History</h3>
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
        {activePage === 'occupancy' && <OccupancyReport />}
        {activePage === 'bookings' && <BookingsReport />}
        {activePage === 'rates' && <GuestRatesReport />}
        {activePage === 'ave_rate' && <AverageRatesReport />}
        {activePage === 'revenue' && <RevenueReport />}
      </main>
    </div>
  )
}

// ============================================
// DATE HELPERS
// ============================================

const formatDate = (date: Date): string => {
  return date.toISOString().split('T')[0]
}

const parseDate = (dateStr: string): Date => {
  return new Date(dateStr + 'T00:00:00')
}

const getStartOfWeek = (date: Date): Date => {
  const d = new Date(date)
  const day = d.getDay()
  const diff = d.getDate() - day + (day === 0 ? -6 : 1) // Monday
  d.setDate(diff)
  return d
}

const getDayOfWeekOffset = (date: Date, targetDayOfWeek: number): number => {
  const dayOfWeek = date.getDay()
  let offset = targetDayOfWeek - dayOfWeek
  // Round to nearest: prefer smallest adjustment
  if (offset > 3) offset -= 7   // If forward 4+ days, go back instead
  if (offset < -3) offset += 7  // If back 4+ days, go forward instead
  return offset
}

// Get comparison start date that aligns with same day of week
const getComparisonStartDate = (
  startDate: Date,
  comparisonType: ComparisonType,
  consolidation: ConsolidationType
): Date => {
  const dayOfWeek = startDate.getDay()

  if (comparisonType === 'previous_period') {
    // Calculate the period length and go back that many days
    // This is handled in the component by subtracting the period length
    return startDate
  } else {
    // Previous year - align to same day of week
    const lastYear = new Date(startDate)
    lastYear.setFullYear(lastYear.getFullYear() - 1)

    if (consolidation === 'day') {
      // For daily, align to same day of week
      const offset = getDayOfWeekOffset(lastYear, dayOfWeek)
      lastYear.setDate(lastYear.getDate() + offset)
    } else if (consolidation === 'week') {
      // For weekly, get start of same week number approximately
      const weekOfYear = Math.floor((startDate.getTime() - new Date(startDate.getFullYear(), 0, 1).getTime()) / (7 * 24 * 60 * 60 * 1000))
      const startOfYear = new Date(lastYear.getFullYear(), 0, 1)
      const weekStart = getStartOfWeek(startOfYear)
      weekStart.setDate(weekStart.getDate() + weekOfYear * 7)
      return weekStart
    } else if (consolidation === 'month') {
      // For monthly, use same month last year
      return new Date(lastYear.getFullYear(), startDate.getMonth(), 1)
    }

    return lastYear
  }
}

type ConsolidationType = 'day' | 'week' | 'month'
type ComparisonType = 'none' | 'previous_period' | 'previous_year'
type QuickSelectType = '7days' | '14days' | '1month' | '3months' | '6months' | '1year'
type OccupancyType = 'bookable' | 'total' | 'both'

// Generate last 12 months (current month first, going backwards)
const getLast12Months = () => {
  const months: { label: string; start: string; end: string }[] = []
  const now = new Date()

  for (let i = 0; i < 12; i++) {
    const date = new Date(now.getFullYear(), now.getMonth() - i, 1)
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

interface OccupancyDataPoint {
  date: string
  total_occupancy_pct: number | null
  bookable_occupancy_pct: number | null
  booking_count: number
  rooms_count: number
  bookable_count: number
}

// ============================================
// OCCUPANCY REPORT
// ============================================

const OccupancyReport: React.FC = () => {
  const today = new Date()
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() - 1) // Yesterday
  const defaultStart = new Date(defaultEnd)
  defaultStart.setMonth(defaultEnd.getMonth() - 1) // 1 month ago

  const [startDate, setStartDate] = useState(formatDate(defaultStart))
  const [endDate, setEndDate] = useState(formatDate(defaultEnd))
  const [consolidation, setConsolidation] = useState<ConsolidationType>('day')
  const [comparison, setComparison] = useState<ComparisonType>('previous_year')
  const [occupancyType, setOccupancyType] = useState<OccupancyType>('both')
  const [showTable, setShowTable] = useState(false)

  // Generate month options (last 12 months)
  const monthOptions = useMemo(() => getLast12Months(), [])

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  // Quick select handlers
  const handleQuickSelect = (type: QuickSelectType) => {
    const end = new Date()
    end.setDate(end.getDate() - 1) // Yesterday
    const start = new Date(end)

    switch (type) {
      case '7days':
        start.setDate(end.getDate() - 6)
        break
      case '14days':
        start.setDate(end.getDate() - 13)
        break
      case '1month':
        start.setMonth(end.getMonth() - 1)
        break
      case '3months':
        start.setMonth(end.getMonth() - 3)
        break
      case '6months':
        start.setMonth(end.getMonth() - 6)
        break
      case '1year':
        start.setFullYear(end.getFullYear() - 1)
        break
    }

    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  // Calculate comparison date range
  const comparisonDates = useMemo(() => {
    if (comparison === 'none') return null

    const start = parseDate(startDate)
    const end = parseDate(endDate)
    const periodDays = Math.ceil((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1

    if (comparison === 'previous_period') {
      const compEnd = new Date(start)
      compEnd.setDate(start.getDate() - 1)
      const compStart = new Date(compEnd)
      compStart.setDate(compEnd.getDate() - periodDays + 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    } else {
      // Previous year - align to same day of week
      const compStart = getComparisonStartDate(start, comparison, consolidation)
      const compEnd = new Date(compStart)
      compEnd.setDate(compStart.getDate() + periodDays - 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    }
  }, [startDate, endDate, comparison, consolidation])

  // Fetch main data
  const { data: mainData, isLoading: mainLoading } = useQuery<OccupancyDataPoint[]>({
    queryKey: ['occupancy-report', startDate, endDate, consolidation],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        consolidation,
      })
      const response = await fetch(`/api/reports/occupancy?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch occupancy data')
      return response.json()
    },
  })

  // Fetch comparison data
  const { data: comparisonData, isLoading: comparisonLoading } = useQuery<OccupancyDataPoint[]>({
    queryKey: ['occupancy-report-comparison', comparisonDates?.start, comparisonDates?.end, consolidation],
    queryFn: async () => {
      if (!comparisonDates) return []
      const params = new URLSearchParams({
        start_date: comparisonDates.start,
        end_date: comparisonDates.end,
        consolidation,
      })
      const response = await fetch(`/api/reports/occupancy?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch comparison data')
      return response.json()
    },
    enabled: !!comparisonDates,
  })

  // Process data for chart
  const chartData = useMemo(() => {
    if (!mainData) return {
      labels: [], mainSeries: [], comparisonSeries: [], mainDates: [], comparisonDates: [],
      mainTotalSeries: [], mainBookableSeries: [], compTotalSeries: [], compBookableSeries: []
    }

    // Check if date range spans more than 11 months (to determine if we need year in labels)
    const rangeStart = parseDate(mainData[0]?.date || '')
    const rangeEnd = parseDate(mainData[mainData.length - 1]?.date || '')
    const rangeMonths = (rangeEnd.getFullYear() - rangeStart.getFullYear()) * 12 + (rangeEnd.getMonth() - rangeStart.getMonth())
    const includeYear = rangeMonths >= 11 // Include year if range is 11+ months to avoid duplicate labels

    const formatLabel = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return includeYear
          ? date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })
          : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return includeYear
          ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })}`
          : `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
      }
    }

    const formatDateWithDay = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
      }
    }

    const labels = mainData.map(d => formatLabel(d.date))
    const mainDates = mainData.map(d => formatDateWithDay(d.date))

    // For 'both' mode, we need separate series for total and bookable
    const mainTotalSeries = mainData.map(d => d.total_occupancy_pct ?? 0)
    const mainBookableSeries = mainData.map(d => d.bookable_occupancy_pct ?? 0)

    // Single series for non-both modes
    const getOccupancy = (d: OccupancyDataPoint) =>
      occupancyType === 'bookable' ? (d.bookable_occupancy_pct ?? 0) : (d.total_occupancy_pct ?? 0)
    const mainSeries = mainData.map(d => getOccupancy(d))

    // Align comparison data with main data points
    let comparisonSeries: (number | null)[] = []
    let compTotalSeries: (number | null)[] = []
    let compBookableSeries: (number | null)[] = []
    let comparisonDates: string[] = []

    if (comparisonData && comparisonData.length > 0 && comparison !== 'none') {
      comparisonSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return getOccupancy(comparisonData[index])
        }
        return null
      })
      compTotalSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return comparisonData[index].total_occupancy_pct ?? 0
        }
        return null
      })
      compBookableSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return comparisonData[index].bookable_occupancy_pct ?? 0
        }
        return null
      })
      comparisonDates = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return formatDateWithDay(comparisonData[index].date)
        }
        return ''
      })
    }

    return {
      labels, mainSeries, comparisonSeries, mainDates, comparisonDates,
      mainTotalSeries, mainBookableSeries, compTotalSeries, compBookableSeries
    }
  }, [mainData, comparisonData, consolidation, comparison, occupancyType])

  const isLoading = mainLoading || (comparison !== 'none' && comparisonLoading)

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Occupancy Report</h2>
          <p style={styles.hint}>
            View occupancy trends over time with optional comparison to previous periods
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        {/* Date Range */}
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Date Range</label>
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

        {/* Consolidation */}
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Consolidation</label>
          <div style={styles.buttonGroup}>
            {(['day', 'week', 'month'] as ConsolidationType[]).map((type) => (
              <button
                key={type}
                onClick={() => setConsolidation(type)}
                style={{
                  ...styles.toggleButton,
                  ...(consolidation === type ? styles.toggleButtonActive : {}),
                }}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {/* Comparison */}
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Compare To</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setComparison('none')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'none' ? styles.toggleButtonActive : {}),
              }}
            >
              None
            </button>
            <button
              onClick={() => setComparison('previous_period')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'previous_period' ? styles.toggleButtonActive : {}),
              }}
            >
              Prev Period
            </button>
            <button
              onClick={() => setComparison('previous_year')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'previous_year' ? styles.toggleButtonActive : {}),
              }}
            >
              Prev Year
            </button>
          </div>
        </div>

        {/* Occupancy Type */}
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Occupancy Type</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setOccupancyType('bookable')}
              style={{
                ...styles.toggleButton,
                ...(occupancyType === 'bookable' ? styles.toggleButtonActive : {}),
              }}
            >
              Bookable
            </button>
            <button
              onClick={() => setOccupancyType('total')}
              style={{
                ...styles.toggleButton,
                ...(occupancyType === 'total' ? styles.toggleButtonActive : {}),
              }}
            >
              Total
            </button>
            <button
              onClick={() => setOccupancyType('both')}
              style={{
                ...styles.toggleButton,
                ...(occupancyType === 'both' ? styles.toggleButtonActive : {}),
              }}
            >
              Both
            </button>
          </div>
        </div>
      </div>

      {/* Quick Select */}
      <div style={styles.quickSelect}>
        <span style={styles.quickSelectLabel}>Quick select:</span>
        {[
          { type: '7days' as QuickSelectType, label: '7 days' },
          { type: '14days' as QuickSelectType, label: '14 days' },
          { type: '1month' as QuickSelectType, label: '1 month' },
          { type: '3months' as QuickSelectType, label: '3 months' },
          { type: '6months' as QuickSelectType, label: '6 months' },
          { type: '1year' as QuickSelectType, label: '1 year' },
        ].map(({ type, label }) => (
          <button
            key={type}
            onClick={() => handleQuickSelect(type)}
            style={styles.quickSelectButton}
          >
            {label}
          </button>
        ))}
        <select
          onChange={(e) => handleMonthSelect(e.target.value)}
          style={styles.monthSelect}
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

      {/* Comparison Info */}
      {comparison !== 'none' && comparisonDates && (
        <div style={styles.comparisonInfo}>
          Comparing with: {comparisonDates.start} to {comparisonDates.end}
        </div>
      )}

      {/* Chart */}
      <div style={styles.chartContainer}>
        {isLoading ? (
          <div style={styles.loading}>Loading occupancy data...</div>
        ) : chartData.labels.length === 0 ? (
          <div style={styles.emptyState}>
            No occupancy data available for the selected date range
          </div>
        ) : (
          <Plot
            data={occupancyType === 'both' ? [
              // Order: Bookable Prior -> Total Prior -> Bookable Current -> Total Current
              // Prior Bookable (pale blue) - bottom layer
              ...(comparison !== 'none' && chartData.compBookableSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compBookableSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Bookable',
                    line: { color: '#93c5fd', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Bookable: %{y:.1f}%<extra></extra>',
                  }]
                : []),
              // Prior Total (blue)
              ...(comparison !== 'none' && chartData.compTotalSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compTotalSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Total',
                    line: { color: '#3b82f6', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Total: %{y:.1f}%<extra></extra>',
                  }]
                : []),
              // Current Bookable (pink)
              {
                x: chartData.labels,
                y: chartData.mainBookableSeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Bookable',
                line: { color: '#f8a5b6', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Bookable: %{y:.1f}%<extra></extra>',
              },
              // Current Total (red) - top layer
              {
                x: chartData.labels,
                y: chartData.mainTotalSeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Total',
                line: { color: '#e94560', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Total: %{y:.1f}%<extra></extra>',
              },
            ] : [
              // Single series mode - prior first, then current on top
              ...(comparison !== 'none' && chartData.comparisonSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.comparisonSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: comparison === 'previous_year' ? 'Previous Year' : 'Previous Period',
                    line: { color: '#3b82f6', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>%{y:.1f}%<extra></extra>',
                  }]
                : []),
              {
                x: chartData.labels,
                y: chartData.mainSeries,
                customdata: chartData.mainDates,
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Current Period',
                line: { color: '#e94560', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>%{y:.1f}%<extra></extra>',
              },
            ]}
            layout={{
              autosize: true,
              height: 400,
              margin: { l: 50, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', color: '#666' },
              xaxis: {
                showgrid: false,
                tickangle: -45,
                nticks: Math.min(chartData.labels.length, 15),
              },
              yaxis: {
                title: { text: occupancyType === 'both' ? 'Occupancy %' : (occupancyType === 'bookable' ? 'Bookable Occupancy %' : 'Total Occupancy %') },
                gridcolor: '#eee',
                zeroline: false,
              },
              hovermode: 'x unified',
              showlegend: occupancyType === 'both' || comparison !== 'none',
              legend: { orientation: 'h', y: 1.15 },
            }}
            config={{
              displayModeBar: true,
              responsive: true,
              modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
            }}
            style={{ width: '100%', height: '400px' }}
          />
        )}
      </div>

      {/* Summary Stats */}
      {mainData && mainData.length > 0 && (() => {
        // For 'both' mode, show bookable stats in summary (chart shows both visually)
        const getOcc = (d: OccupancyDataPoint) =>
          (occupancyType === 'bookable' || occupancyType === 'both') ? (d.bookable_occupancy_pct ?? 0) : (d.total_occupancy_pct ?? 0)
        const mainAvg = mainData.reduce((sum, d) => sum + getOcc(d), 0) / mainData.length
        const mainPeak = Math.max(...mainData.map(d => getOcc(d)))
        const mainLowest = Math.min(...mainData.map(d => getOcc(d)))
        const mainRoomNights = mainData.reduce((sum, d) => sum + d.booking_count, 0)

        const hasComparison = comparison !== 'none' && comparisonData && comparisonData.length > 0

        const compAvg = hasComparison ? comparisonData.reduce((sum, d) => sum + getOcc(d), 0) / comparisonData.length : 0
        const compPeak = hasComparison ? Math.max(...comparisonData.map(d => getOcc(d))) : 0
        const compLowest = hasComparison ? Math.min(...comparisonData.map(d => getOcc(d))) : 0
        const compRoomNights = hasComparison ? comparisonData.reduce((sum, d) => sum + d.booking_count, 0) : 0

        const formatDiff = (current: number, previous: number, isPercent: boolean = true) => {
          const diff = current - previous
          const sign = diff >= 0 ? '+' : ''
          return `${sign}${diff.toFixed(isPercent ? 1 : 0)}${isPercent ? '%' : ''}`
        }

        const summaryLabel = occupancyType === 'both' ? ' (Bookable)' : ''

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Average Occupancy{summaryLabel}</div>
              <div style={styles.summaryValue}>{mainAvg.toFixed(1)}%</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{compAvg.toFixed(1)}%</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainAvg >= compAvg ? colors.success : colors.error
                  }}>({formatDiff(mainAvg, compAvg)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Peak Occupancy</div>
              <div style={styles.summaryValue}>{mainPeak.toFixed(1)}%</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{compPeak.toFixed(1)}%</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainPeak >= compPeak ? colors.success : colors.error
                  }}>({formatDiff(mainPeak, compPeak)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Lowest Occupancy</div>
              <div style={styles.summaryValue}>{mainLowest.toFixed(1)}%</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{compLowest.toFixed(1)}%</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainLowest >= compLowest ? colors.success : colors.error
                  }}>({formatDiff(mainLowest, compLowest)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Total Room Nights</div>
              <div style={styles.summaryValue}>{mainRoomNights.toLocaleString()}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{compRoomNights.toLocaleString()}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainRoomNights >= compRoomNights ? colors.success : colors.error
                  }}>({formatDiff(mainRoomNights, compRoomNights, false)})</span>
                </div>
              )}
            </div>
          </div>
        )
      })()}

      {/* Data Table */}
      {mainData && mainData.length > 0 && (
        <div style={styles.tableSection}>
          <button
            onClick={() => setShowTable(!showTable)}
            style={styles.tableToggle}
          >
            {showTable ? '▼ Hide Data Table' : '▶ Show Data Table'}
          </button>
          {showTable && (
            <div style={styles.tableWrapper}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.tableHeader}>Date</th>
                    <th style={styles.tableHeaderRight}>Total %</th>
                    <th style={styles.tableHeaderRight}>Bookable %</th>
                    <th style={styles.tableHeaderRight}>Bookings</th>
                    {comparison !== 'none' && comparisonData && (
                      <>
                        <th style={styles.tableHeaderRight}>Prior Total %</th>
                        <th style={styles.tableHeaderRight}>Prior Bookable %</th>
                        <th style={styles.tableHeaderRight}>Prior Bookings</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {mainData.map((row, index) => {
                    const compRow = comparisonData && index < comparisonData.length ? comparisonData[index] : null
                    const date = parseDate(row.date)
                    const dateLabel = consolidation === 'day'
                      ? date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
                      : consolidation === 'week'
                        ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${new Date(date.getTime() + 6 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
                        : date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
                    return (
                      <tr key={row.date} style={index % 2 === 0 ? styles.tableRowEven : styles.tableRowOdd}>
                        <td style={styles.tableCell}>{dateLabel}</td>
                        <td style={styles.tableCellRight}>{(row.total_occupancy_pct ?? 0).toFixed(1)}%</td>
                        <td style={styles.tableCellRight}>{(row.bookable_occupancy_pct ?? 0).toFixed(1)}%</td>
                        <td style={styles.tableCellRight}>{row.booking_count}</td>
                        {comparison !== 'none' && comparisonData && (
                          <>
                            <td style={styles.tableCellRight}>{compRow ? `${(compRow.total_occupancy_pct ?? 0).toFixed(1)}%` : '-'}</td>
                            <td style={styles.tableCellRight}>{compRow ? `${(compRow.bookable_occupancy_pct ?? 0).toFixed(1)}%` : '-'}</td>
                            <td style={styles.tableCellRight}>{compRow ? compRow.booking_count : '-'}</td>
                          </>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================
// BOOKINGS REPORT
// ============================================

type BookingsDisplayType = 'bookings' | 'guests' | 'both'

interface BookingsDataPoint {
  date: string
  booking_count: number
  guests_count: number
  rooms_count: number
}

const BookingsReport: React.FC = () => {
  const today = new Date()
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() - 1)
  const defaultStart = new Date(defaultEnd)
  defaultStart.setMonth(defaultEnd.getMonth() - 1)

  const [startDate, setStartDate] = useState(formatDate(defaultStart))
  const [endDate, setEndDate] = useState(formatDate(defaultEnd))
  const [consolidation, setConsolidation] = useState<ConsolidationType>('day')
  const [comparison, setComparison] = useState<ComparisonType>('previous_year')
  const [displayType, setDisplayType] = useState<BookingsDisplayType>('both')
  const [showTable, setShowTable] = useState(false)

  // Generate month options (last 12 months)
  const monthOptions = useMemo(() => getLast12Months(), [])

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  const handleQuickSelect = (type: QuickSelectType) => {
    const end = new Date()
    end.setDate(end.getDate() - 1)
    const start = new Date(end)

    switch (type) {
      case '7days':
        start.setDate(end.getDate() - 6)
        break
      case '14days':
        start.setDate(end.getDate() - 13)
        break
      case '1month':
        start.setMonth(end.getMonth() - 1)
        break
      case '3months':
        start.setMonth(end.getMonth() - 3)
        break
      case '6months':
        start.setMonth(end.getMonth() - 6)
        break
      case '1year':
        start.setFullYear(end.getFullYear() - 1)
        break
    }

    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const comparisonDates = useMemo(() => {
    if (comparison === 'none') return null

    const start = parseDate(startDate)
    const end = parseDate(endDate)
    const periodDays = Math.ceil((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1

    if (comparison === 'previous_period') {
      const compEnd = new Date(start)
      compEnd.setDate(start.getDate() - 1)
      const compStart = new Date(compEnd)
      compStart.setDate(compEnd.getDate() - periodDays + 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    } else {
      const compStart = getComparisonStartDate(start, comparison, consolidation)
      const compEnd = new Date(compStart)
      compEnd.setDate(compStart.getDate() + periodDays - 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    }
  }, [startDate, endDate, comparison, consolidation])

  const { data: mainData, isLoading: mainLoading } = useQuery<BookingsDataPoint[]>({
    queryKey: ['bookings-report', startDate, endDate, consolidation],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        consolidation,
      })
      const response = await fetch(`/api/reports/bookings?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch bookings data')
      return response.json()
    },
  })

  const { data: comparisonData, isLoading: comparisonLoading } = useQuery<BookingsDataPoint[]>({
    queryKey: ['bookings-report-comparison', comparisonDates?.start, comparisonDates?.end, consolidation],
    queryFn: async () => {
      if (!comparisonDates) return []
      const params = new URLSearchParams({
        start_date: comparisonDates.start,
        end_date: comparisonDates.end,
        consolidation,
      })
      const response = await fetch(`/api/reports/bookings?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch comparison data')
      return response.json()
    },
    enabled: !!comparisonDates,
  })

  const chartData = useMemo(() => {
    if (!mainData) return {
      labels: [], mainSeries: [], comparisonSeries: [], mainDates: [], comparisonDates: [],
      mainBookingsSeries: [], mainGuestsSeries: [], compBookingsSeries: [], compGuestsSeries: []
    }

    const rangeStart = parseDate(mainData[0]?.date || '')
    const rangeEnd = parseDate(mainData[mainData.length - 1]?.date || '')
    const rangeMonths = (rangeEnd.getFullYear() - rangeStart.getFullYear()) * 12 + (rangeEnd.getMonth() - rangeStart.getMonth())
    const includeYear = rangeMonths >= 11

    const formatLabel = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return includeYear
          ? date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })
          : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return includeYear
          ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })}`
          : `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
      }
    }

    const formatDateWithDay = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
      }
    }

    const labels = mainData.map(d => formatLabel(d.date))
    const mainDates = mainData.map(d => formatDateWithDay(d.date))

    const mainBookingsSeries = mainData.map(d => d.booking_count)
    const mainGuestsSeries = mainData.map(d => d.guests_count)

    const getValue = (d: BookingsDataPoint) =>
      displayType === 'guests' ? d.guests_count : d.booking_count
    const mainSeries = mainData.map(d => getValue(d))

    let comparisonSeries: (number | null)[] = []
    let compBookingsSeries: (number | null)[] = []
    let compGuestsSeries: (number | null)[] = []
    let comparisonDatesArr: string[] = []

    if (comparisonData && comparisonData.length > 0 && comparison !== 'none') {
      comparisonSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return getValue(comparisonData[index])
        }
        return null
      })
      compBookingsSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return comparisonData[index].booking_count
        }
        return null
      })
      compGuestsSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return comparisonData[index].guests_count
        }
        return null
      })
      comparisonDatesArr = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return formatDateWithDay(comparisonData[index].date)
        }
        return ''
      })
    }

    return {
      labels, mainSeries, comparisonSeries, mainDates, comparisonDates: comparisonDatesArr,
      mainBookingsSeries, mainGuestsSeries, compBookingsSeries, compGuestsSeries
    }
  }, [mainData, comparisonData, consolidation, comparison, displayType])

  const isLoading = mainLoading || (comparison !== 'none' && comparisonLoading)

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Bookings Report</h2>
          <p style={styles.hint}>
            View booking counts and guest numbers over time with optional comparison
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Date Range</label>
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

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Consolidation</label>
          <div style={styles.buttonGroup}>
            {(['day', 'week', 'month'] as ConsolidationType[]).map((type) => (
              <button
                key={type}
                onClick={() => setConsolidation(type)}
                style={{
                  ...styles.toggleButton,
                  ...(consolidation === type ? styles.toggleButtonActive : {}),
                }}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Compare To</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setComparison('none')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'none' ? styles.toggleButtonActive : {}),
              }}
            >
              None
            </button>
            <button
              onClick={() => setComparison('previous_period')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'previous_period' ? styles.toggleButtonActive : {}),
              }}
            >
              Prev Period
            </button>
            <button
              onClick={() => setComparison('previous_year')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'previous_year' ? styles.toggleButtonActive : {}),
              }}
            >
              Prev Year
            </button>
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Display</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setDisplayType('bookings')}
              style={{
                ...styles.toggleButton,
                ...(displayType === 'bookings' ? styles.toggleButtonActive : {}),
              }}
            >
              Bookings
            </button>
            <button
              onClick={() => setDisplayType('guests')}
              style={{
                ...styles.toggleButton,
                ...(displayType === 'guests' ? styles.toggleButtonActive : {}),
              }}
            >
              Guests
            </button>
            <button
              onClick={() => setDisplayType('both')}
              style={{
                ...styles.toggleButton,
                ...(displayType === 'both' ? styles.toggleButtonActive : {}),
              }}
            >
              Both
            </button>
          </div>
        </div>
      </div>

      {/* Quick Select */}
      <div style={styles.quickSelect}>
        <span style={styles.quickSelectLabel}>Quick select:</span>
        {[
          { type: '7days' as QuickSelectType, label: '7 days' },
          { type: '14days' as QuickSelectType, label: '14 days' },
          { type: '1month' as QuickSelectType, label: '1 month' },
          { type: '3months' as QuickSelectType, label: '3 months' },
          { type: '6months' as QuickSelectType, label: '6 months' },
          { type: '1year' as QuickSelectType, label: '1 year' },
        ].map(({ type, label }) => (
          <button
            key={type}
            onClick={() => handleQuickSelect(type)}
            style={styles.quickSelectButton}
          >
            {label}
          </button>
        ))}
        <select
          onChange={(e) => handleMonthSelect(e.target.value)}
          style={styles.monthSelect}
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

      {/* Comparison Info */}
      {comparison !== 'none' && comparisonDates && (
        <div style={styles.comparisonInfo}>
          Comparing with: {comparisonDates.start} to {comparisonDates.end}
        </div>
      )}

      {/* Chart */}
      <div style={styles.chartContainer}>
        {isLoading ? (
          <div style={styles.loading}>Loading bookings data...</div>
        ) : chartData.labels.length === 0 ? (
          <div style={styles.emptyState}>
            No bookings data available for the selected date range
          </div>
        ) : (
          <Plot
            data={displayType === 'both' ? [
              // Order: Guests Prior -> Bookings Prior -> Guests Current -> Bookings Current
              ...(comparison !== 'none' && chartData.compGuestsSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compGuestsSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Guests',
                    line: { color: '#93c5fd', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Guests: %{y}<extra></extra>',
                  }]
                : []),
              ...(comparison !== 'none' && chartData.compBookingsSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compBookingsSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Bookings',
                    line: { color: '#3b82f6', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Bookings: %{y}<extra></extra>',
                  }]
                : []),
              {
                x: chartData.labels,
                y: chartData.mainGuestsSeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Guests',
                line: { color: '#f8a5b6', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Guests: %{y}<extra></extra>',
              },
              {
                x: chartData.labels,
                y: chartData.mainBookingsSeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Bookings',
                line: { color: '#e94560', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Bookings: %{y}<extra></extra>',
              },
            ] : [
              ...(comparison !== 'none' && chartData.comparisonSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.comparisonSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: comparison === 'previous_year' ? 'Previous Year' : 'Previous Period',
                    line: { color: '#3b82f6', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>%{y}<extra></extra>',
                  }]
                : []),
              {
                x: chartData.labels,
                y: chartData.mainSeries,
                customdata: chartData.mainDates,
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Current Period',
                line: { color: '#e94560', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>%{y}<extra></extra>',
              },
            ]}
            layout={{
              autosize: true,
              height: 400,
              margin: { l: 50, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', color: '#666' },
              xaxis: {
                showgrid: false,
                tickangle: -45,
                nticks: Math.min(chartData.labels.length, 15),
              },
              yaxis: {
                title: { text: displayType === 'both' ? 'Count' : (displayType === 'bookings' ? 'Bookings' : 'Guests') },
                gridcolor: '#eee',
                zeroline: false,
              },
              hovermode: 'x unified',
              showlegend: displayType === 'both' || comparison !== 'none',
              legend: { orientation: 'h', y: 1.15 },
            }}
            config={{
              displayModeBar: true,
              responsive: true,
              modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
            }}
            style={{ width: '100%', height: '400px' }}
          />
        )}
      </div>

      {/* Summary Stats */}
      {mainData && mainData.length > 0 && (() => {
        const getVal = (d: BookingsDataPoint) =>
          (displayType === 'guests' || displayType === 'both') ? d.guests_count : d.booking_count
        const mainTotal = mainData.reduce((sum, d) => sum + d.booking_count, 0)
        const mainGuests = mainData.reduce((sum, d) => sum + d.guests_count, 0)
        const mainAvg = mainData.reduce((sum, d) => sum + getVal(d), 0) / mainData.length
        const mainPeak = Math.max(...mainData.map(d => getVal(d)))

        const hasComparison = comparison !== 'none' && comparisonData && comparisonData.length > 0

        const compTotal = hasComparison ? comparisonData.reduce((sum, d) => sum + d.booking_count, 0) : 0
        const compGuests = hasComparison ? comparisonData.reduce((sum, d) => sum + d.guests_count, 0) : 0
        const compAvg = hasComparison ? comparisonData.reduce((sum, d) => sum + getVal(d), 0) / comparisonData.length : 0
        const compPeak = hasComparison ? Math.max(...comparisonData.map(d => getVal(d))) : 0

        const formatDiff = (current: number, previous: number, isDecimal: boolean = false) => {
          const diff = current - previous
          const sign = diff >= 0 ? '+' : ''
          return `${sign}${isDecimal ? diff.toFixed(1) : diff.toLocaleString()}`
        }

        const summaryLabel = displayType === 'both' ? ' (Guests)' : ''

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Total Bookings</div>
              <div style={styles.summaryValue}>{mainTotal.toLocaleString()}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{compTotal.toLocaleString()}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainTotal >= compTotal ? colors.success : colors.error
                  }}>({formatDiff(mainTotal, compTotal)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Total Guests</div>
              <div style={styles.summaryValue}>{mainGuests.toLocaleString()}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{compGuests.toLocaleString()}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainGuests >= compGuests ? colors.success : colors.error
                  }}>({formatDiff(mainGuests, compGuests)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Daily Average{summaryLabel}</div>
              <div style={styles.summaryValue}>{mainAvg.toFixed(1)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{compAvg.toFixed(1)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainAvg >= compAvg ? colors.success : colors.error
                  }}>({formatDiff(mainAvg, compAvg, true)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Peak Day{summaryLabel}</div>
              <div style={styles.summaryValue}>{mainPeak.toLocaleString()}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{compPeak.toLocaleString()}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainPeak >= compPeak ? colors.success : colors.error
                  }}>({formatDiff(mainPeak, compPeak)})</span>
                </div>
              )}
            </div>
          </div>
        )
      })()}

      {/* Data Table */}
      {mainData && mainData.length > 0 && (
        <div style={styles.tableSection}>
          <button
            onClick={() => setShowTable(!showTable)}
            style={styles.tableToggle}
          >
            {showTable ? '▼ Hide Data Table' : '▶ Show Data Table'}
          </button>
          {showTable && (
            <div style={styles.tableWrapper}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.tableHeader}>Date</th>
                    <th style={styles.tableHeaderRight}>Bookings</th>
                    <th style={styles.tableHeaderRight}>Guests</th>
                    {comparison !== 'none' && comparisonData && (
                      <>
                        <th style={styles.tableHeaderRight}>Prior Bookings</th>
                        <th style={styles.tableHeaderRight}>Prior Guests</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {mainData.map((row, index) => {
                    const compRow = comparisonData && index < comparisonData.length ? comparisonData[index] : null
                    const date = parseDate(row.date)
                    const dateLabel = consolidation === 'day'
                      ? date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
                      : consolidation === 'week'
                        ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${new Date(date.getTime() + 6 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
                        : date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
                    return (
                      <tr key={row.date} style={index % 2 === 0 ? styles.tableRowEven : styles.tableRowOdd}>
                        <td style={styles.tableCell}>{dateLabel}</td>
                        <td style={styles.tableCellRight}>{row.booking_count}</td>
                        <td style={styles.tableCellRight}>{row.guests_count}</td>
                        {comparison !== 'none' && comparisonData && (
                          <>
                            <td style={styles.tableCellRight}>{compRow ? compRow.booking_count : '-'}</td>
                            <td style={styles.tableCellRight}>{compRow ? compRow.guests_count : '-'}</td>
                          </>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================
// GUEST RATES REPORT
// ============================================

type RatesDisplayType = 'gross' | 'net' | 'both'

interface RatesDataPoint {
  date: string
  guest_rate_total: number
  net_booking_rev_total: number
  booking_count: number
  avg_guest_rate: number | null
  avg_net_rate: number | null
}

const GuestRatesReport: React.FC = () => {
  const today = new Date()
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() - 1)
  const defaultStart = new Date(defaultEnd)
  defaultStart.setMonth(defaultEnd.getMonth() - 1)

  const [startDate, setStartDate] = useState(formatDate(defaultStart))
  const [endDate, setEndDate] = useState(formatDate(defaultEnd))
  const [consolidation, setConsolidation] = useState<ConsolidationType>('day')
  const [comparison, setComparison] = useState<ComparisonType>('previous_year')
  const [displayType, setDisplayType] = useState<RatesDisplayType>('both')
  const [showTable, setShowTable] = useState(false)

  // Generate month options (last 12 months)
  const monthOptions = useMemo(() => getLast12Months(), [])

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  const handleQuickSelect = (type: QuickSelectType) => {
    const end = new Date()
    end.setDate(end.getDate() - 1)
    const start = new Date(end)

    switch (type) {
      case '7days':
        start.setDate(end.getDate() - 6)
        break
      case '14days':
        start.setDate(end.getDate() - 13)
        break
      case '1month':
        start.setMonth(end.getMonth() - 1)
        break
      case '3months':
        start.setMonth(end.getMonth() - 3)
        break
      case '6months':
        start.setMonth(end.getMonth() - 6)
        break
      case '1year':
        start.setFullYear(end.getFullYear() - 1)
        break
    }

    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const comparisonDates = useMemo(() => {
    if (comparison === 'none') return null

    const start = parseDate(startDate)
    const end = parseDate(endDate)
    const periodDays = Math.ceil((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1

    if (comparison === 'previous_period') {
      const compEnd = new Date(start)
      compEnd.setDate(start.getDate() - 1)
      const compStart = new Date(compEnd)
      compStart.setDate(compEnd.getDate() - periodDays + 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    } else {
      const compStart = getComparisonStartDate(start, comparison, consolidation)
      const compEnd = new Date(compStart)
      compEnd.setDate(compStart.getDate() + periodDays - 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    }
  }, [startDate, endDate, comparison, consolidation])

  const { data: mainData, isLoading: mainLoading } = useQuery<RatesDataPoint[]>({
    queryKey: ['rates-report', startDate, endDate, consolidation],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        consolidation,
      })
      const response = await fetch(`/api/reports/rates?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch rates data')
      return response.json()
    },
  })

  const { data: comparisonData, isLoading: comparisonLoading } = useQuery<RatesDataPoint[]>({
    queryKey: ['rates-report-comparison', comparisonDates?.start, comparisonDates?.end, consolidation],
    queryFn: async () => {
      if (!comparisonDates) return []
      const params = new URLSearchParams({
        start_date: comparisonDates.start,
        end_date: comparisonDates.end,
        consolidation,
      })
      const response = await fetch(`/api/reports/rates?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch comparison data')
      return response.json()
    },
    enabled: !!comparisonDates,
  })

  const chartData = useMemo(() => {
    if (!mainData) return {
      labels: [], mainSeries: [], comparisonSeries: [], mainDates: [], comparisonDates: [],
      mainGrossSeries: [], mainNetSeries: [], compGrossSeries: [], compNetSeries: []
    }

    const rangeStart = parseDate(mainData[0]?.date || '')
    const rangeEnd = parseDate(mainData[mainData.length - 1]?.date || '')
    const rangeMonths = (rangeEnd.getFullYear() - rangeStart.getFullYear()) * 12 + (rangeEnd.getMonth() - rangeStart.getMonth())
    const includeYear = rangeMonths >= 11

    const formatLabel = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return includeYear
          ? date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })
          : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return includeYear
          ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })}`
          : `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
      }
    }

    const formatDateWithDay = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
      }
    }

    const labels = mainData.map(d => formatLabel(d.date))
    const mainDates = mainData.map(d => formatDateWithDay(d.date))

    const mainGrossSeries = mainData.map(d => d.guest_rate_total)
    const mainNetSeries = mainData.map(d => d.net_booking_rev_total)

    const getValue = (d: RatesDataPoint) =>
      displayType === 'net' ? d.net_booking_rev_total : d.guest_rate_total
    const mainSeries = mainData.map(d => getValue(d))

    let comparisonSeries: (number | null)[] = []
    let compGrossSeries: (number | null)[] = []
    let compNetSeries: (number | null)[] = []
    let comparisonDatesArr: string[] = []

    if (comparisonData && comparisonData.length > 0 && comparison !== 'none') {
      comparisonSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return getValue(comparisonData[index])
        }
        return null
      })
      compGrossSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return comparisonData[index].guest_rate_total
        }
        return null
      })
      compNetSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return comparisonData[index].net_booking_rev_total
        }
        return null
      })
      comparisonDatesArr = mainData.map((_, index) => {
        if (index < comparisonData.length) {
          return formatDateWithDay(comparisonData[index].date)
        }
        return ''
      })
    }

    return {
      labels, mainSeries, comparisonSeries, mainDates, comparisonDates: comparisonDatesArr,
      mainGrossSeries, mainNetSeries, compGrossSeries, compNetSeries
    }
  }, [mainData, comparisonData, consolidation, comparison, displayType])

  const isLoading = mainLoading || (comparison !== 'none' && comparisonLoading)

  const formatCurrency = (value: number) => `£${value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Rate Totals Report</h2>
          <p style={styles.hint}>
            View gross tariff (calculated amount) and net revenue totals over time
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Date Range</label>
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

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Consolidation</label>
          <div style={styles.buttonGroup}>
            {(['day', 'week', 'month'] as ConsolidationType[]).map((type) => (
              <button
                key={type}
                onClick={() => setConsolidation(type)}
                style={{
                  ...styles.toggleButton,
                  ...(consolidation === type ? styles.toggleButtonActive : {}),
                }}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Compare To</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setComparison('none')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'none' ? styles.toggleButtonActive : {}),
              }}
            >
              None
            </button>
            <button
              onClick={() => setComparison('previous_period')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'previous_period' ? styles.toggleButtonActive : {}),
              }}
            >
              Prev Period
            </button>
            <button
              onClick={() => setComparison('previous_year')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'previous_year' ? styles.toggleButtonActive : {}),
              }}
            >
              Prev Year
            </button>
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Display</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setDisplayType('gross')}
              style={{
                ...styles.toggleButton,
                ...(displayType === 'gross' ? styles.toggleButtonActive : {}),
              }}
            >
              Gross
            </button>
            <button
              onClick={() => setDisplayType('net')}
              style={{
                ...styles.toggleButton,
                ...(displayType === 'net' ? styles.toggleButtonActive : {}),
              }}
            >
              Net
            </button>
            <button
              onClick={() => setDisplayType('both')}
              style={{
                ...styles.toggleButton,
                ...(displayType === 'both' ? styles.toggleButtonActive : {}),
              }}
            >
              Both
            </button>
          </div>
        </div>
      </div>

      {/* Quick Select */}
      <div style={styles.quickSelect}>
        <span style={styles.quickSelectLabel}>Quick select:</span>
        {[
          { type: '7days' as QuickSelectType, label: '7 days' },
          { type: '14days' as QuickSelectType, label: '14 days' },
          { type: '1month' as QuickSelectType, label: '1 month' },
          { type: '3months' as QuickSelectType, label: '3 months' },
          { type: '6months' as QuickSelectType, label: '6 months' },
          { type: '1year' as QuickSelectType, label: '1 year' },
        ].map(({ type, label }) => (
          <button
            key={type}
            onClick={() => handleQuickSelect(type)}
            style={styles.quickSelectButton}
          >
            {label}
          </button>
        ))}
        <select
          onChange={(e) => handleMonthSelect(e.target.value)}
          style={styles.monthSelect}
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

      {/* Comparison Info */}
      {comparison !== 'none' && comparisonDates && (
        <div style={styles.comparisonInfo}>
          Comparing with: {comparisonDates.start} to {comparisonDates.end}
        </div>
      )}

      {/* Chart */}
      <div style={styles.chartContainer}>
        {isLoading ? (
          <div style={styles.loading}>Loading rates data...</div>
        ) : chartData.labels.length === 0 ? (
          <div style={styles.emptyState}>
            No rates data available for the selected date range
          </div>
        ) : (
          <Plot
            data={displayType === 'both' ? [
              // Order: Net Prior -> Gross Prior -> Net Current -> Gross Current
              ...(comparison !== 'none' && chartData.compNetSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compNetSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Net',
                    line: { color: '#93c5fd', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Net: £%{y:,.2f}<extra></extra>',
                  }]
                : []),
              ...(comparison !== 'none' && chartData.compGrossSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compGrossSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Gross',
                    line: { color: '#3b82f6', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Gross: £%{y:,.2f}<extra></extra>',
                  }]
                : []),
              {
                x: chartData.labels,
                y: chartData.mainNetSeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Net',
                line: { color: '#f8a5b6', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Net: £%{y:,.2f}<extra></extra>',
              },
              {
                x: chartData.labels,
                y: chartData.mainGrossSeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Gross',
                line: { color: '#e94560', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Gross: £%{y:,.2f}<extra></extra>',
              },
            ] : [
              ...(comparison !== 'none' && chartData.comparisonSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.comparisonSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: comparison === 'previous_year' ? 'Previous Year' : 'Previous Period',
                    line: { color: '#3b82f6', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>£%{y:,.2f}<extra></extra>',
                  }]
                : []),
              {
                x: chartData.labels,
                y: chartData.mainSeries,
                customdata: chartData.mainDates,
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Current Period',
                line: { color: '#e94560', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>£%{y:,.2f}<extra></extra>',
              },
            ]}
            layout={{
              autosize: true,
              height: 400,
              margin: { l: 70, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', color: '#666' },
              xaxis: {
                showgrid: false,
                tickangle: -45,
                nticks: Math.min(chartData.labels.length, 15),
              },
              yaxis: {
                title: { text: displayType === 'both' ? 'Revenue (£)' : (displayType === 'gross' ? 'Gross Revenue (£)' : 'Net Revenue (£)') },
                gridcolor: '#eee',
                zeroline: false,
                tickprefix: '£',
              },
              hovermode: 'x unified',
              showlegend: displayType === 'both' || comparison !== 'none',
              legend: { orientation: 'h', y: 1.15 },
            }}
            config={{
              displayModeBar: true,
              responsive: true,
              modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
            }}
            style={{ width: '100%', height: '400px' }}
          />
        )}
      </div>

      {/* Summary Stats */}
      {mainData && mainData.length > 0 && (() => {
        const mainGrossTotal = mainData.reduce((sum, d) => sum + d.guest_rate_total, 0)
        const mainNetTotal = mainData.reduce((sum, d) => sum + d.net_booking_rev_total, 0)
        const mainBookings = mainData.reduce((sum, d) => sum + d.booking_count, 0)
        const mainAvgGross = mainBookings > 0 ? mainGrossTotal / mainBookings : 0
        const mainAvgNet = mainBookings > 0 ? mainNetTotal / mainBookings : 0

        const hasComparison = comparison !== 'none' && comparisonData && comparisonData.length > 0

        const compGrossTotal = hasComparison ? comparisonData.reduce((sum, d) => sum + d.guest_rate_total, 0) : 0
        const compNetTotal = hasComparison ? comparisonData.reduce((sum, d) => sum + d.net_booking_rev_total, 0) : 0
        const compBookings = hasComparison ? comparisonData.reduce((sum, d) => sum + d.booking_count, 0) : 0
        const compAvgGross = compBookings > 0 ? compGrossTotal / compBookings : 0
        const compAvgNet = compBookings > 0 ? compNetTotal / compBookings : 0

        const formatDiff = (current: number, previous: number) => {
          const diff = current - previous
          const sign = diff >= 0 ? '+' : ''
          return `${sign}£${Math.abs(diff).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
        }

        const formatDiffPercent = (current: number, previous: number) => {
          if (previous === 0) return '+N/A'
          const pctDiff = ((current - previous) / previous) * 100
          const sign = pctDiff >= 0 ? '+' : ''
          return `${sign}${pctDiff.toFixed(1)}%`
        }

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Total Gross Rate</div>
              <div style={styles.summaryValue}>{formatCurrency(mainGrossTotal)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{formatCurrency(compGrossTotal)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainGrossTotal >= compGrossTotal ? colors.success : colors.error
                  }}>({formatDiffPercent(mainGrossTotal, compGrossTotal)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Total Net-Gross Rate</div>
              <div style={styles.summaryValue}>{formatCurrency(mainNetTotal)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{formatCurrency(compNetTotal)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainNetTotal >= compNetTotal ? colors.success : colors.error
                  }}>({formatDiffPercent(mainNetTotal, compNetTotal)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Avg Gross Rate</div>
              <div style={styles.summaryValue}>{formatCurrency(mainAvgGross)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{formatCurrency(compAvgGross)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainAvgGross >= compAvgGross ? colors.success : colors.error
                  }}>({formatDiff(mainAvgGross, compAvgGross)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Avg Net-Gross Rate</div>
              <div style={styles.summaryValue}>{formatCurrency(mainAvgNet)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{formatCurrency(compAvgNet)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainAvgNet >= compAvgNet ? colors.success : colors.error
                  }}>({formatDiff(mainAvgNet, compAvgNet)})</span>
                </div>
              )}
            </div>
          </div>
        )
      })()}

      {/* Data Table */}
      {mainData && mainData.length > 0 && (
        <div style={styles.tableSection}>
          <button
            onClick={() => setShowTable(!showTable)}
            style={styles.tableToggle}
          >
            {showTable ? '▼ Hide Data Table' : '▶ Show Data Table'}
          </button>
          {showTable && (
            <div style={styles.tableWrapper}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.tableHeader}>Date</th>
                    <th style={styles.tableHeaderRight}>Gross</th>
                    <th style={styles.tableHeaderRight}>Net-Gross</th>
                    <th style={styles.tableHeaderRight}>Bookings</th>
                    <th style={styles.tableHeaderRight}>Avg Gross</th>
                    {comparison !== 'none' && comparisonData && (
                      <>
                        <th style={styles.tableHeaderRight}>Prior Gross</th>
                        <th style={styles.tableHeaderRight}>Prior Net-Gross</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {mainData.map((row, index) => {
                    const compRow = comparisonData && index < comparisonData.length ? comparisonData[index] : null
                    const date = parseDate(row.date)
                    const dateLabel = consolidation === 'day'
                      ? date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
                      : consolidation === 'week'
                        ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${new Date(date.getTime() + 6 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
                        : date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
                    const avgGross = row.booking_count > 0 ? row.guest_rate_total / row.booking_count : 0
                    return (
                      <tr key={row.date} style={index % 2 === 0 ? styles.tableRowEven : styles.tableRowOdd}>
                        <td style={styles.tableCell}>{dateLabel}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(row.guest_rate_total)}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(row.net_booking_rev_total)}</td>
                        <td style={styles.tableCellRight}>{row.booking_count}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(avgGross)}</td>
                        {comparison !== 'none' && comparisonData && (
                          <>
                            <td style={styles.tableCellRight}>{compRow ? formatCurrency(compRow.guest_rate_total) : '-'}</td>
                            <td style={styles.tableCellRight}>{compRow ? formatCurrency(compRow.net_booking_rev_total) : '-'}</td>
                          </>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================
// AVERAGE RATES REPORT
// ============================================

type AveRateDisplayType = 'both' | 'gross' | 'net'

const AverageRatesReport: React.FC = () => {
  const today = new Date()
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() - 1)
  const defaultStart = new Date(defaultEnd)
  defaultStart.setMonth(defaultEnd.getMonth() - 1)

  const [startDate, setStartDate] = useState(formatDate(defaultStart))
  const [endDate, setEndDate] = useState(formatDate(defaultEnd))
  const [consolidation, setConsolidation] = useState<ConsolidationType>('day')
  const [comparison, setComparison] = useState<ComparisonType>('previous_year')
  const [displayType, setDisplayType] = useState<AveRateDisplayType>('both')
  const [showTable, setShowTable] = useState(false)

  const monthOptions = useMemo(() => getLast12Months(), [])

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  const handleQuickSelect = (type: QuickSelectType) => {
    const end = new Date()
    end.setDate(end.getDate() - 1)
    const start = new Date(end)

    switch (type) {
      case '7days':
        start.setDate(end.getDate() - 6)
        break
      case '14days':
        start.setDate(end.getDate() - 13)
        break
      case '1month':
        start.setMonth(end.getMonth() - 1)
        break
      case '3months':
        start.setMonth(end.getMonth() - 3)
        break
      case '6months':
        start.setMonth(end.getMonth() - 6)
        break
      case '1year':
        start.setFullYear(end.getFullYear() - 1)
        break
    }

    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const comparisonDates = useMemo(() => {
    if (comparison === 'none') return null

    const start = parseDate(startDate)
    const end = parseDate(endDate)
    const periodDays = Math.ceil((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1

    if (comparison === 'previous_period') {
      const compEnd = new Date(start)
      compEnd.setDate(start.getDate() - 1)
      const compStart = new Date(compEnd)
      compStart.setDate(compEnd.getDate() - periodDays + 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    } else {
      const compStart = getComparisonStartDate(start, comparison, consolidation)
      const compEnd = new Date(compStart)
      compEnd.setDate(compStart.getDate() + periodDays - 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    }
  }, [startDate, endDate, comparison, consolidation])

  const { data: mainData, isLoading: mainLoading } = useQuery<RatesDataPoint[]>({
    queryKey: ['ave-rates-report', startDate, endDate, consolidation],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        consolidation,
      })
      const response = await fetch(`/api/reports/rates?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch rates data')
      return response.json()
    },
  })

  const { data: comparisonData, isLoading: comparisonLoading } = useQuery<RatesDataPoint[]>({
    queryKey: ['ave-rates-report-comparison', comparisonDates?.start, comparisonDates?.end, consolidation],
    queryFn: async () => {
      if (!comparisonDates) return []
      const params = new URLSearchParams({
        start_date: comparisonDates.start,
        end_date: comparisonDates.end,
        consolidation,
      })
      const response = await fetch(`/api/reports/rates?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch comparison data')
      return response.json()
    },
    enabled: !!comparisonDates,
  })

  const calcAvgGross = (d: RatesDataPoint) => d.booking_count > 0 ? d.guest_rate_total / d.booking_count : 0
  const calcAvgNet = (d: RatesDataPoint) => d.booking_count > 0 ? d.net_booking_rev_total / d.booking_count : 0

  const chartData = useMemo(() => {
    if (!mainData) return {
      labels: [], mainDates: [], comparisonDates: [],
      mainAvgGrossSeries: [], mainAvgNetSeries: [],
      compAvgGrossSeries: [], compAvgNetSeries: []
    }

    const rangeStart = parseDate(mainData[0]?.date || '')
    const rangeEnd = parseDate(mainData[mainData.length - 1]?.date || '')
    const rangeMonths = (rangeEnd.getFullYear() - rangeStart.getFullYear()) * 12 + (rangeEnd.getMonth() - rangeStart.getMonth())
    const includeYear = rangeMonths >= 11

    const formatLabel = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return includeYear
          ? date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })
          : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return includeYear
          ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })}`
          : `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
      }
    }

    const formatDateWithDay = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
      }
    }

    const labels = mainData.map(d => formatLabel(d.date))
    const mainDates = mainData.map(d => formatDateWithDay(d.date))
    const mainAvgGrossSeries = mainData.map(d => calcAvgGross(d))
    const mainAvgNetSeries = mainData.map(d => calcAvgNet(d))

    let compAvgGrossSeries: (number | null)[] = []
    let compAvgNetSeries: (number | null)[] = []
    let comparisonDatesArr: string[] = []

    if (comparisonData && comparisonData.length > 0 && comparison !== 'none') {
      compAvgGrossSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) return calcAvgGross(comparisonData[index])
        return null
      })
      compAvgNetSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) return calcAvgNet(comparisonData[index])
        return null
      })
      comparisonDatesArr = mainData.map((_, index) => {
        if (index < comparisonData.length) return formatDateWithDay(comparisonData[index].date)
        return ''
      })
    }

    return {
      labels, mainDates, comparisonDates: comparisonDatesArr,
      mainAvgGrossSeries, mainAvgNetSeries,
      compAvgGrossSeries, compAvgNetSeries
    }
  }, [mainData, comparisonData, consolidation, comparison])

  const isLoading = mainLoading || (comparison !== 'none' && comparisonLoading)
  const formatCurrency = (value: number) => `£${value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Average Rate Report</h2>
          <p style={styles.hint}>Average guest gross and net accommodation rate per booking</p>
        </div>
      </div>

      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Date Range</label>
          <div style={styles.dateInputs}>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={styles.dateInput} />
            <span style={styles.dateSeparator}>to</span>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={styles.dateInput} />
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Consolidation</label>
          <div style={styles.buttonGroup}>
            {(['day', 'week', 'month'] as ConsolidationType[]).map((type) => (
              <button key={type} onClick={() => setConsolidation(type)}
                style={{ ...styles.toggleButton, ...(consolidation === type ? styles.toggleButtonActive : {}) }}>
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Compare To</label>
          <div style={styles.buttonGroup}>
            <button onClick={() => setComparison('none')}
              style={{ ...styles.toggleButton, ...(comparison === 'none' ? styles.toggleButtonActive : {}) }}>None</button>
            <button onClick={() => setComparison('previous_period')}
              style={{ ...styles.toggleButton, ...(comparison === 'previous_period' ? styles.toggleButtonActive : {}) }}>Prev Period</button>
            <button onClick={() => setComparison('previous_year')}
              style={{ ...styles.toggleButton, ...(comparison === 'previous_year' ? styles.toggleButtonActive : {}) }}>Prev Year</button>
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Display</label>
          <div style={styles.buttonGroup}>
            <button onClick={() => setDisplayType('gross')}
              style={{ ...styles.toggleButton, ...(displayType === 'gross' ? styles.toggleButtonActive : {}) }}>Guest Gross</button>
            <button onClick={() => setDisplayType('net')}
              style={{ ...styles.toggleButton, ...(displayType === 'net' ? styles.toggleButtonActive : {}) }}>Gross Accom</button>
            <button onClick={() => setDisplayType('both')}
              style={{ ...styles.toggleButton, ...(displayType === 'both' ? styles.toggleButtonActive : {}) }}>Both</button>
          </div>
        </div>
      </div>

      <div style={styles.quickSelect}>
        <span style={styles.quickSelectLabel}>Quick select:</span>
        {[
          { type: '7days' as QuickSelectType, label: '7 days' },
          { type: '14days' as QuickSelectType, label: '14 days' },
          { type: '1month' as QuickSelectType, label: '1 month' },
          { type: '3months' as QuickSelectType, label: '3 months' },
          { type: '6months' as QuickSelectType, label: '6 months' },
          { type: '1year' as QuickSelectType, label: '1 year' },
        ].map(({ type, label }) => (
          <button key={type} onClick={() => handleQuickSelect(type)} style={styles.quickSelectButton}>
            {label}
          </button>
        ))}
        <select onChange={(e) => handleMonthSelect(e.target.value)} style={styles.monthSelect} defaultValue="">
          <option value="" disabled>Month...</option>
          {monthOptions.map((month, idx) => (<option key={idx} value={idx}>{month.label}</option>))}
        </select>
      </div>

      {isLoading ? (
        <div style={styles.loading}>Loading...</div>
      ) : mainData && mainData.length > 0 ? (
        <div>
          <div style={styles.chartContainer}>
            <Plot
              data={[
                ...(displayType !== 'net' ? [{
                  x: chartData.labels, y: chartData.mainAvgGrossSeries,
                  type: 'scatter' as const, mode: 'lines+markers' as const, name: 'Avg Guest Gross',
                  line: { color: colors.accent, width: 2 }, marker: { size: 6 },
                  text: chartData.mainDates, hovertemplate: '%{text}<br>Guest Gross: %{y:£,.2f}<extra></extra>',
                }] : []),
                ...(displayType !== 'gross' ? [{
                  x: chartData.labels, y: chartData.mainAvgNetSeries,
                  type: 'scatter' as const, mode: 'lines+markers' as const, name: 'Avg Gross Accom',
                  line: { color: colors.primary, width: 2 }, marker: { size: 6 },
                  text: chartData.mainDates, hovertemplate: '%{text}<br>Gross Accom: %{y:£,.2f}<extra></extra>',
                }] : []),
                ...(comparison !== 'none' && displayType !== 'net' && chartData.compAvgGrossSeries.length > 0 ? [{
                  x: chartData.labels, y: chartData.compAvgGrossSeries,
                  type: 'scatter' as const, mode: 'lines+markers' as const,
                  name: `Guest Gross (${comparison === 'previous_year' ? 'PY' : 'Prev'})`,
                  line: { color: colors.accent, width: 2, dash: 'dash' as const }, marker: { size: 6 },
                  text: chartData.comparisonDates, hovertemplate: '%{text}<br>Guest Gross: %{y:£,.2f}<extra></extra>', opacity: 0.6,
                }] : []),
                ...(comparison !== 'none' && displayType !== 'gross' && chartData.compAvgNetSeries.length > 0 ? [{
                  x: chartData.labels, y: chartData.compAvgNetSeries,
                  type: 'scatter' as const, mode: 'lines+markers' as const,
                  name: `Gross Accom (${comparison === 'previous_year' ? 'PY' : 'Prev'})`,
                  line: { color: colors.primary, width: 2, dash: 'dash' as const }, marker: { size: 6 },
                  text: chartData.comparisonDates, hovertemplate: '%{text}<br>Gross Accom: %{y:£,.2f}<extra></extra>', opacity: 0.6,
                }] : []),
              ]}
              layout={{
                autosize: true, height: 400, margin: { l: 60, r: 40, t: 20, b: 80 },
                xaxis: { tickangle: -45, tickfont: { size: 11 } },
                yaxis: { title: { text: 'Average Rate (£)' }, tickformat: ',.0f', tickprefix: '£', gridcolor: '#eee' },
                legend: { orientation: 'h', y: -0.25, x: 0.5, xanchor: 'center' },
                hovermode: 'x unified',
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
          </div>

          <div style={styles.summaryGrid}>
            {(() => {
              const totalBookings = mainData.reduce((sum, d) => sum + d.booking_count, 0)
              const totalGross = mainData.reduce((sum, d) => sum + d.guest_rate_total, 0)
              const totalNet = mainData.reduce((sum, d) => sum + d.net_booking_rev_total, 0)
              const avgGross = totalBookings > 0 ? totalGross / totalBookings : 0
              const avgNet = totalBookings > 0 ? totalNet / totalBookings : 0

              const hasComparison = comparison !== 'none' && comparisonData && comparisonData.length > 0
              const compTotalBookings = hasComparison ? comparisonData.reduce((sum, d) => sum + d.booking_count, 0) : 0
              const compTotalGross = hasComparison ? comparisonData.reduce((sum, d) => sum + d.guest_rate_total, 0) : 0
              const compTotalNet = hasComparison ? comparisonData.reduce((sum, d) => sum + d.net_booking_rev_total, 0) : 0
              const compAvgGross = compTotalBookings > 0 ? compTotalGross / compTotalBookings : 0
              const compAvgNet = compTotalBookings > 0 ? compTotalNet / compTotalBookings : 0

              const avgGrossChange = hasComparison && compAvgGross > 0 ? ((avgGross - compAvgGross) / compAvgGross) * 100 : null
              const avgNetChange = hasComparison && compAvgNet > 0 ? ((avgNet - compAvgNet) / compAvgNet) * 100 : null

              return (
                <>
                  <div style={styles.summaryCard}>
                    <div style={styles.summaryLabel}>Avg Guest Gross</div>
                    <div style={styles.summaryValue}>{formatCurrency(avgGross)}</div>
                    {avgGrossChange !== null && (
                      <div style={{ ...styles.summaryChange, color: avgGrossChange >= 0 ? colors.success : colors.error }}>
                        {avgGrossChange >= 0 ? '+' : ''}{avgGrossChange.toFixed(1)}% vs {comparison === 'previous_year' ? 'PY' : 'prev'}
                      </div>
                    )}
                  </div>
                  <div style={styles.summaryCard}>
                    <div style={styles.summaryLabel}>Avg Gross Accom</div>
                    <div style={styles.summaryValue}>{formatCurrency(avgNet)}</div>
                    {avgNetChange !== null && (
                      <div style={{ ...styles.summaryChange, color: avgNetChange >= 0 ? colors.success : colors.error }}>
                        {avgNetChange >= 0 ? '+' : ''}{avgNetChange.toFixed(1)}% vs {comparison === 'previous_year' ? 'PY' : 'prev'}
                      </div>
                    )}
                  </div>
                  <div style={styles.summaryCard}>
                    <div style={styles.summaryLabel}>Total Bookings</div>
                    <div style={styles.summaryValue}>{totalBookings.toLocaleString()}</div>
                    {hasComparison && compTotalBookings > 0 && (
                      <div style={{ ...styles.summaryChange, color: totalBookings >= compTotalBookings ? colors.success : colors.error }}>
                        {totalBookings >= compTotalBookings ? '+' : ''}{((totalBookings - compTotalBookings) / compTotalBookings * 100).toFixed(1)}% vs {comparison === 'previous_year' ? 'PY' : 'prev'}
                      </div>
                    )}
                  </div>
                </>
              )
            })()}
          </div>

          <button onClick={() => setShowTable(!showTable)} style={styles.tableToggle}>
            {showTable ? '▼ Hide Data Table' : '▶ Show Data Table'}
          </button>

          {showTable && (
            <div style={styles.tableWrapper}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.tableHeader}>Date</th>
                    <th style={styles.tableHeaderRight}>Bookings</th>
                    <th style={styles.tableHeaderRight}>Guest Gross</th>
                    <th style={styles.tableHeaderRight}>Gross Accom</th>
                    {comparison !== 'none' && comparisonData && (
                      <>
                        <th style={styles.tableHeaderRight}>Comp Bookings</th>
                        <th style={styles.tableHeaderRight}>Comp Guest Gross</th>
                        <th style={styles.tableHeaderRight}>Comp Gross Accom</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {mainData.map((row, index) => {
                    const compRow = comparisonData && comparisonData[index]
                    const avgGross = row.booking_count > 0 ? row.guest_rate_total / row.booking_count : 0
                    const avgNet = row.booking_count > 0 ? row.net_booking_rev_total / row.booking_count : 0
                    const compAvgGross = compRow && compRow.booking_count > 0 ? compRow.guest_rate_total / compRow.booking_count : 0
                    const compAvgNet = compRow && compRow.booking_count > 0 ? compRow.net_booking_rev_total / compRow.booking_count : 0

                    return (
                      <tr key={row.date}>
                        <td style={styles.tableCell}>{chartData.mainDates[index]}</td>
                        <td style={styles.tableCellRight}>{row.booking_count}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(avgGross)}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(avgNet)}</td>
                        {comparison !== 'none' && comparisonData && (
                          <>
                            <td style={styles.tableCellRight}>{compRow ? compRow.booking_count : '-'}</td>
                            <td style={styles.tableCellRight}>{compRow ? formatCurrency(compAvgGross) : '-'}</td>
                            <td style={styles.tableCellRight}>{compRow ? formatCurrency(compAvgNet) : '-'}</td>
                          </>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        <div style={styles.noData}>No data available for selected period</div>
      )}
    </div>
  )
}

// ============================================
// REVENUE REPORT
// ============================================

interface RevenueDataPoint {
  date: string
  accommodation: number
  dry: number
  wet: number
  total: number
}

const RevenueReport: React.FC = () => {
  const today = new Date()
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() - 1)
  const defaultStart = new Date(defaultEnd)
  defaultStart.setMonth(defaultEnd.getMonth() - 1)

  const [startDate, setStartDate] = useState(formatDate(defaultStart))
  const [endDate, setEndDate] = useState(formatDate(defaultEnd))
  const [consolidation, setConsolidation] = useState<ConsolidationType>('day')
  const [comparison, setComparison] = useState<ComparisonType>('previous_year')
  const [showTable, setShowTable] = useState(false)

  // Generate month options (last 12 months)
  const monthOptions = useMemo(() => getLast12Months(), [])

  const handleMonthSelect = (monthIndex: string) => {
    if (monthIndex === '') return
    const idx = parseInt(monthIndex, 10)
    const month = monthOptions[idx]
    if (month) {
      setStartDate(month.start)
      setEndDate(month.end)
    }
  }

  const handleQuickSelect = (type: QuickSelectType) => {
    const end = new Date()
    end.setDate(end.getDate() - 1)
    const start = new Date(end)

    switch (type) {
      case '7days':
        start.setDate(end.getDate() - 6)
        break
      case '14days':
        start.setDate(end.getDate() - 13)
        break
      case '1month':
        start.setMonth(end.getMonth() - 1)
        break
      case '3months':
        start.setMonth(end.getMonth() - 3)
        break
      case '6months':
        start.setMonth(end.getMonth() - 6)
        break
      case '1year':
        start.setFullYear(end.getFullYear() - 1)
        break
    }

    setStartDate(formatDate(start))
    setEndDate(formatDate(end))
  }

  const comparisonDates = useMemo(() => {
    if (comparison === 'none') return null

    const start = parseDate(startDate)
    const end = parseDate(endDate)
    const periodDays = Math.ceil((end.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1

    if (comparison === 'previous_period') {
      const compEnd = new Date(start)
      compEnd.setDate(start.getDate() - 1)
      const compStart = new Date(compEnd)
      compStart.setDate(compEnd.getDate() - periodDays + 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    } else {
      const compStart = getComparisonStartDate(start, comparison, consolidation)
      const compEnd = new Date(compStart)
      compEnd.setDate(compStart.getDate() + periodDays - 1)
      return { start: formatDate(compStart), end: formatDate(compEnd) }
    }
  }, [startDate, endDate, comparison, consolidation])

  const { data: mainData, isLoading: mainLoading } = useQuery<RevenueDataPoint[]>({
    queryKey: ['revenue-report', startDate, endDate, consolidation],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        consolidation,
      })
      const response = await fetch(`/api/reports/revenue?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch revenue data')
      return response.json()
    },
  })

  const { data: comparisonData, isLoading: comparisonLoading } = useQuery<RevenueDataPoint[]>({
    queryKey: ['revenue-report-comparison', comparisonDates?.start, comparisonDates?.end, consolidation],
    queryFn: async () => {
      if (!comparisonDates) return []
      const params = new URLSearchParams({
        start_date: comparisonDates.start,
        end_date: comparisonDates.end,
        consolidation,
      })
      const response = await fetch(`/api/reports/revenue?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch comparison data')
      return response.json()
    },
    enabled: !!comparisonDates,
  })

  const chartData = useMemo(() => {
    if (!mainData) return {
      labels: [], mainDates: [], comparisonDates: [],
      mainAccomSeries: [], mainDrySeries: [], mainWetSeries: [],
      compAccomSeries: [], compDrySeries: [], compWetSeries: []
    }

    const rangeStart = parseDate(mainData[0]?.date || '')
    const rangeEnd = parseDate(mainData[mainData.length - 1]?.date || '')
    const rangeMonths = (rangeEnd.getFullYear() - rangeStart.getFullYear()) * 12 + (rangeEnd.getMonth() - rangeStart.getMonth())
    const includeYear = rangeMonths >= 11

    const formatLabel = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return includeYear
          ? date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })
          : date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return includeYear
          ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: '2-digit' })}`
          : `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
      }
    }

    const formatDateWithDay = (dateStr: string): string => {
      const date = parseDate(dateStr)
      if (consolidation === 'day') {
        return date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
      } else if (consolidation === 'week') {
        const weekEnd = new Date(date)
        weekEnd.setDate(date.getDate() + 6)
        return `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${weekEnd.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
      } else {
        return date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
      }
    }

    const labels = mainData.map(d => formatLabel(d.date))
    const mainDates = mainData.map(d => formatDateWithDay(d.date))

    const mainAccomSeries = mainData.map(d => d.accommodation)
    const mainDrySeries = mainData.map(d => d.dry)
    const mainWetSeries = mainData.map(d => d.wet)

    let compAccomSeries: (number | null)[] = []
    let compDrySeries: (number | null)[] = []
    let compWetSeries: (number | null)[] = []
    let comparisonDatesArr: string[] = []

    if (comparisonData && comparisonData.length > 0 && comparison !== 'none') {
      compAccomSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) return comparisonData[index].accommodation
        return null
      })
      compDrySeries = mainData.map((_, index) => {
        if (index < comparisonData.length) return comparisonData[index].dry
        return null
      })
      compWetSeries = mainData.map((_, index) => {
        if (index < comparisonData.length) return comparisonData[index].wet
        return null
      })
      comparisonDatesArr = mainData.map((_, index) => {
        if (index < comparisonData.length) return formatDateWithDay(comparisonData[index].date)
        return ''
      })
    }

    return {
      labels, mainDates, comparisonDates: comparisonDatesArr,
      mainAccomSeries, mainDrySeries, mainWetSeries,
      compAccomSeries, compDrySeries, compWetSeries
    }
  }, [mainData, comparisonData, consolidation, comparison])

  const isLoading = mainLoading || (comparison !== 'none' && comparisonLoading)

  const formatCurrency = (value: number) => `£${value.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Revenue Report</h2>
          <p style={styles.hint}>
            View net revenue by category (Accommodation, Dry, Wet) over time
          </p>
        </div>
      </div>

      {/* Controls */}
      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Date Range</label>
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

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Consolidation</label>
          <div style={styles.buttonGroup}>
            {(['day', 'week', 'month'] as ConsolidationType[]).map((type) => (
              <button
                key={type}
                onClick={() => setConsolidation(type)}
                style={{
                  ...styles.toggleButton,
                  ...(consolidation === type ? styles.toggleButtonActive : {}),
                }}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Compare To</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setComparison('none')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'none' ? styles.toggleButtonActive : {}),
              }}
            >
              None
            </button>
            <button
              onClick={() => setComparison('previous_period')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'previous_period' ? styles.toggleButtonActive : {}),
              }}
            >
              Prev Period
            </button>
            <button
              onClick={() => setComparison('previous_year')}
              style={{
                ...styles.toggleButton,
                ...(comparison === 'previous_year' ? styles.toggleButtonActive : {}),
              }}
            >
              Prev Year
            </button>
          </div>
        </div>
      </div>

      {/* Quick Select */}
      <div style={styles.quickSelect}>
        <span style={styles.quickSelectLabel}>Quick select:</span>
        {[
          { type: '7days' as QuickSelectType, label: '7 days' },
          { type: '14days' as QuickSelectType, label: '14 days' },
          { type: '1month' as QuickSelectType, label: '1 month' },
          { type: '3months' as QuickSelectType, label: '3 months' },
          { type: '6months' as QuickSelectType, label: '6 months' },
          { type: '1year' as QuickSelectType, label: '1 year' },
        ].map(({ type, label }) => (
          <button
            key={type}
            onClick={() => handleQuickSelect(type)}
            style={styles.quickSelectButton}
          >
            {label}
          </button>
        ))}
        <select
          onChange={(e) => handleMonthSelect(e.target.value)}
          style={styles.monthSelect}
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

      {/* Comparison Info */}
      {comparison !== 'none' && comparisonDates && (
        <div style={styles.comparisonInfo}>
          Comparing with: {comparisonDates.start} to {comparisonDates.end}
        </div>
      )}

      {/* Chart */}
      <div style={styles.chartContainer}>
        {isLoading ? (
          <div style={styles.loading}>Loading revenue data...</div>
        ) : chartData.labels.length === 0 ? (
          <div style={styles.emptyState}>
            No revenue data available for the selected date range
          </div>
        ) : (
          <Plot
            data={[
              // Prior period traces (dashed) - bottom layer
              ...(comparison !== 'none' && chartData.compWetSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compWetSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Wet',
                    line: { color: '#a5d6a7', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Wet: £%{y:,.2f}<extra></extra>',
                  }]
                : []),
              ...(comparison !== 'none' && chartData.compDrySeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compDrySeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Dry',
                    line: { color: '#90caf9', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Dry: £%{y:,.2f}<extra></extra>',
                  }]
                : []),
              ...(comparison !== 'none' && chartData.compAccomSeries.length > 0
                ? [{
                    x: chartData.labels,
                    y: chartData.compAccomSeries,
                    customdata: chartData.comparisonDates,
                    type: 'scatter' as const,
                    mode: 'lines+markers' as const,
                    name: (comparison === 'previous_year' ? 'Prior Year' : 'Prior Period') + ' Accom',
                    line: { color: '#ce93d8', width: 2, dash: 'dash' as const },
                    marker: { size: 6 },
                    connectgaps: true,
                    hovertemplate: '<b>%{customdata}</b><br>Accommodation: £%{y:,.2f}<extra></extra>',
                  }]
                : []),
              // Current period traces (solid) - top layer
              {
                x: chartData.labels,
                y: chartData.mainWetSeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Wet',
                line: { color: '#4caf50', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Wet: £%{y:,.2f}<extra></extra>',
              },
              {
                x: chartData.labels,
                y: chartData.mainDrySeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Dry',
                line: { color: '#2196f3', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Dry: £%{y:,.2f}<extra></extra>',
              },
              {
                x: chartData.labels,
                y: chartData.mainAccomSeries,
                customdata: chartData.mainDates,
                type: 'scatter' as const,
                mode: 'lines+markers' as const,
                name: 'Current Accom',
                line: { color: '#9c27b0', width: 2 },
                marker: { size: 6 },
                hovertemplate: '<b>%{customdata}</b><br>Accommodation: £%{y:,.2f}<extra></extra>',
              },
            ]}
            layout={{
              autosize: true,
              height: 400,
              margin: { l: 70, r: 30, t: 30, b: 50 },
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              font: { family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif', color: '#666' },
              xaxis: {
                showgrid: false,
                tickangle: -45,
                nticks: Math.min(chartData.labels.length, 15),
              },
              yaxis: {
                title: { text: 'Revenue (£)' },
                gridcolor: '#eee',
                zeroline: false,
                tickprefix: '£',
              },
              hovermode: 'x unified',
              showlegend: true,
              legend: { orientation: 'h', y: 1.15 },
            }}
            config={{
              displayModeBar: true,
              responsive: true,
              modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
            }}
            style={{ width: '100%', height: '400px' }}
          />
        )}
      </div>

      {/* Summary Stats */}
      {mainData && mainData.length > 0 && (() => {
        const mainAccomTotal = mainData.reduce((sum, d) => sum + d.accommodation, 0)
        const mainDryTotal = mainData.reduce((sum, d) => sum + d.dry, 0)
        const mainWetTotal = mainData.reduce((sum, d) => sum + d.wet, 0)
        const mainTotal = mainAccomTotal + mainDryTotal + mainWetTotal

        const hasComparison = comparison !== 'none' && comparisonData && comparisonData.length > 0

        const compAccomTotal = hasComparison ? comparisonData.reduce((sum, d) => sum + d.accommodation, 0) : 0
        const compDryTotal = hasComparison ? comparisonData.reduce((sum, d) => sum + d.dry, 0) : 0
        const compWetTotal = hasComparison ? comparisonData.reduce((sum, d) => sum + d.wet, 0) : 0
        const compTotal = compAccomTotal + compDryTotal + compWetTotal

        const formatDiffPercent = (current: number, previous: number) => {
          if (previous === 0) return '+N/A'
          const pctDiff = ((current - previous) / previous) * 100
          const sign = pctDiff >= 0 ? '+' : ''
          return `${sign}${pctDiff.toFixed(1)}%`
        }

        return (
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Accommodation</div>
              <div style={styles.summaryValue}>{formatCurrency(mainAccomTotal)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{formatCurrency(compAccomTotal)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainAccomTotal >= compAccomTotal ? colors.success : colors.error
                  }}>({formatDiffPercent(mainAccomTotal, compAccomTotal)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Dry (Food)</div>
              <div style={styles.summaryValue}>{formatCurrency(mainDryTotal)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{formatCurrency(compDryTotal)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainDryTotal >= compDryTotal ? colors.success : colors.error
                  }}>({formatDiffPercent(mainDryTotal, compDryTotal)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Wet (Beverage)</div>
              <div style={styles.summaryValue}>{formatCurrency(mainWetTotal)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{formatCurrency(compWetTotal)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainWetTotal >= compWetTotal ? colors.success : colors.error
                  }}>({formatDiffPercent(mainWetTotal, compWetTotal)})</span>
                </div>
              )}
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Total Revenue</div>
              <div style={styles.summaryValue}>{formatCurrency(mainTotal)}</div>
              {hasComparison && (
                <div style={styles.summaryComparison}>
                  <span style={styles.comparisonValue}>{formatCurrency(compTotal)}</span>
                  <span style={{
                    ...styles.comparisonDiff,
                    color: mainTotal >= compTotal ? colors.success : colors.error
                  }}>({formatDiffPercent(mainTotal, compTotal)})</span>
                </div>
              )}
            </div>
          </div>
        )
      })()}

      {/* Data Table */}
      {mainData && mainData.length > 0 && (
        <div style={styles.tableSection}>
          <button
            onClick={() => setShowTable(!showTable)}
            style={styles.tableToggle}
          >
            {showTable ? '▼ Hide Data Table' : '▶ Show Data Table'}
          </button>
          {showTable && (
            <div style={styles.tableWrapper}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.tableHeader}>Date</th>
                    <th style={styles.tableHeaderRight}>Accom</th>
                    <th style={styles.tableHeaderRight}>Dry</th>
                    <th style={styles.tableHeaderRight}>Wet</th>
                    <th style={styles.tableHeaderRight}>Total</th>
                    {comparison !== 'none' && comparisonData && (
                      <>
                        <th style={styles.tableHeaderRight}>Prior Accom</th>
                        <th style={styles.tableHeaderRight}>Prior Dry</th>
                        <th style={styles.tableHeaderRight}>Prior Wet</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {mainData.map((row, index) => {
                    const compRow = comparisonData && index < comparisonData.length ? comparisonData[index] : null
                    const date = parseDate(row.date)
                    const dateLabel = consolidation === 'day'
                      ? date.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
                      : consolidation === 'week'
                        ? `${date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} - ${new Date(date.getTime() + 6 * 24 * 60 * 60 * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`
                        : date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
                    return (
                      <tr key={row.date} style={index % 2 === 0 ? styles.tableRowEven : styles.tableRowOdd}>
                        <td style={styles.tableCell}>{dateLabel}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(row.accommodation)}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(row.dry)}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(row.wet)}</td>
                        <td style={styles.tableCellRight}>{formatCurrency(row.total)}</td>
                        {comparison !== 'none' && comparisonData && (
                          <>
                            <td style={styles.tableCellRight}>{compRow ? formatCurrency(compRow.accommodation) : '-'}</td>
                            <td style={styles.tableCellRight}>{compRow ? formatCurrency(compRow.dry) : '-'}</td>
                            <td style={styles.tableCellRight}>{compRow ? formatCurrency(compRow.wet) : '-'}</td>
                          </>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================
// STYLES
// ============================================

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
    gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
    gap: spacing.lg,
    marginBottom: spacing.md,
  },
  controlGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.sm,
  },
  controlLabel: {
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.text,
  },
  dateInputs: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  dateInput: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.sm,
    outline: 'none',
    flex: 1,
  },
  dateSeparator: {
    color: colors.textMuted,
    fontSize: typography.sm,
  },
  buttonGroup: {
    display: 'flex',
    gap: '1px',
    background: colors.border,
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  toggleButton: {
    flex: 1,
    padding: `${spacing.sm} ${spacing.md}`,
    border: 'none',
    background: colors.background,
    fontSize: typography.sm,
    color: colors.textSecondary,
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  toggleButtonActive: {
    background: colors.accent,
    color: colors.textLight,
    fontWeight: typography.medium,
  },
  quickSelect: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.lg,
    flexWrap: 'wrap',
  },
  quickSelectLabel: {
    fontSize: typography.sm,
    color: colors.textMuted,
  },
  quickSelectButton: {
    padding: `${spacing.xs} ${spacing.sm}`,
    border: `1px solid ${colors.border}`,
    background: colors.surface,
    borderRadius: radius.md,
    fontSize: typography.xs,
    color: colors.textSecondary,
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  monthSelect: {
    padding: `${spacing.xs} ${spacing.sm}`,
    border: `1px solid ${colors.border}`,
    background: colors.surface,
    borderRadius: radius.md,
    fontSize: typography.xs,
    color: colors.text,
    cursor: 'pointer',
    minWidth: '100px',
  },
  comparisonInfo: {
    padding: spacing.sm,
    background: colors.infoBg,
    color: colors.info,
    borderRadius: radius.md,
    fontSize: typography.sm,
    marginBottom: spacing.lg,
  },
  chartContainer: {
    marginBottom: spacing.xl,
    minHeight: '400px',
  },
  loading: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '400px',
    color: colors.textSecondary,
  },
  emptyState: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '400px',
    color: colors.textMuted,
    background: colors.background,
    borderRadius: radius.md,
  },
  summaryGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    gap: spacing.md,
  },
  summaryCard: {
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.md,
    textAlign: 'center',
  },
  summaryLabel: {
    fontSize: typography.xs,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
    marginBottom: spacing.xs,
  },
  summaryValue: {
    fontSize: typography.xxl,
    fontWeight: typography.bold,
    color: colors.text,
  },
  summaryComparison: {
    marginTop: spacing.xs,
    fontSize: typography.sm,
    display: 'flex',
    justifyContent: 'center',
    gap: spacing.xs,
  },
  comparisonValue: {
    color: colors.textSecondary,
  },
  comparisonDiff: {
    fontWeight: typography.medium,
  },
  tableSection: {
    marginTop: spacing.xl,
  },
  tableToggle: {
    padding: `${spacing.sm} ${spacing.md}`,
    border: `1px solid ${colors.border}`,
    background: colors.background,
    borderRadius: radius.md,
    fontSize: typography.sm,
    color: colors.textSecondary,
    cursor: 'pointer',
    transition: 'all 0.15s',
    marginBottom: spacing.md,
  },
  tableWrapper: {
    overflowX: 'auto',
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    maxHeight: '400px',
    overflowY: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: typography.sm,
  },
  tableHeader: {
    padding: `${spacing.sm} ${spacing.md}`,
    textAlign: 'left',
    fontWeight: typography.semibold,
    color: colors.text,
    background: colors.background,
    borderBottom: `2px solid ${colors.border}`,
    position: 'sticky',
    top: 0,
  },
  tableHeaderRight: {
    padding: `${spacing.sm} ${spacing.md}`,
    textAlign: 'right',
    fontWeight: typography.semibold,
    color: colors.text,
    background: colors.background,
    borderBottom: `2px solid ${colors.border}`,
    position: 'sticky',
    top: 0,
  },
  tableRowEven: {
    background: colors.surface,
  },
  tableRowOdd: {
    background: colors.background,
  },
  tableCell: {
    padding: `${spacing.sm} ${spacing.md}`,
    borderBottom: `1px solid ${colors.border}`,
    color: colors.text,
  },
  tableCellRight: {
    padding: `${spacing.sm} ${spacing.md}`,
    borderBottom: `1px solid ${colors.border}`,
    color: colors.text,
    textAlign: 'right',
  },
}

export default Review
