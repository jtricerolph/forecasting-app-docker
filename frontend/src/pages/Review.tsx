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

type ReportPage = 'occupancy' | 'bookings' | 'rates' | 'ave_rate' | 'revenue' | 'pickup_3d' | 'restaurant_bookings' | 'restaurant_covers'

interface MenuGroup {
  group: string
  items: { id: ReportPage; label: string }[]
}

const Review: React.FC = () => {
  const { reportId } = useParams<{ reportId?: string }>()
  const navigate = useNavigate()
  const activePage = (reportId as ReportPage) || 'occupancy'

  const menuGroups: MenuGroup[] = [
    {
      group: 'Hotel',
      items: [
        { id: 'occupancy', label: 'Occupancy' },
        { id: 'bookings', label: 'Bookings' },
        { id: 'rates', label: 'Rate Totals' },
        { id: 'ave_rate', label: 'Ave Rate' },
        { id: 'revenue', label: 'Revenue' },
        { id: 'pickup_3d', label: '3D Pickup' },
      ]
    },
    {
      group: 'Restaurant',
      items: [
        { id: 'restaurant_bookings', label: 'Bookings' },
        { id: 'restaurant_covers', label: 'Covers' },
      ]
    }
  ]

  const handlePageChange = (id: ReportPage) => {
    navigate(`/review/${id}`)
  }

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        <h3 style={styles.sidebarTitle}>History</h3>
        <nav style={styles.nav}>
          {menuGroups.map((group) => (
            <div key={group.group} style={styles.navGroup}>
              <div style={styles.navGroupTitle}>{group.group}</div>
              {group.items.map((item) => (
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
            </div>
          ))}
        </nav>
      </div>

      <main style={styles.content}>
        {activePage === 'occupancy' && <OccupancyReport />}
        {activePage === 'bookings' && <BookingsReport />}
        {activePage === 'rates' && <GuestRatesReport />}
        {activePage === 'ave_rate' && <AverageRatesReport />}
        {activePage === 'revenue' && <RevenueReport />}
        {activePage === 'pickup_3d' && <PickupVisualization />}
        {activePage === 'restaurant_bookings' && <RestaurantBookingsReport />}
        {activePage === 'restaurant_covers' && <RestaurantCoversReport />}
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
  // Parse as UTC to avoid DST/timezone issues
  const [year, month, day] = dateStr.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day))
}

const getStartOfWeek = (date: Date): Date => {
  const day = date.getUTCDay()
  const diff = date.getUTCDate() - day + (day === 0 ? -6 : 1) // Monday
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), diff))
}

// Get comparison start date that aligns with same day of week
const getComparisonStartDate = (
  startDate: Date,
  comparisonType: ComparisonType,
  consolidation: ConsolidationType
): Date => {
  if (comparisonType === 'previous_period') {
    // Calculate the period length and go back that many days
    // This is handled in the component by subtracting the period length
    return startDate
  } else {
    // Previous year - align to same day of week using 364-day offset (52 weeks)
    // This ensures perfect DOW alignment regardless of leap years
    // Use UTC to avoid DST/timezone issues
    if (consolidation === 'day') {
      // For daily, go back exactly 364 days (52 weeks) to match DOW
      const priorDate = new Date(Date.UTC(
        startDate.getUTCFullYear(),
        startDate.getUTCMonth(),
        startDate.getUTCDate() - 364
      ))
      return priorDate
    } else if (consolidation === 'week') {
      // For weekly, go back 52 weeks to align week boundaries
      const priorDate = new Date(Date.UTC(
        startDate.getUTCFullYear(),
        startDate.getUTCMonth(),
        startDate.getUTCDate() - 364
      ))
      return getStartOfWeek(priorDate)
    } else if (consolidation === 'month') {
      // For monthly, use same month last year (DOW doesn't matter for monthly)
      return new Date(Date.UTC(startDate.getUTCFullYear() - 1, startDate.getUTCMonth(), 1))
    }

    // Default fallback: 364-day offset
    const priorDate = new Date(Date.UTC(
      startDate.getUTCFullYear(),
      startDate.getUTCMonth(),
      startDate.getUTCDate() - 364
    ))
    return priorDate
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
  const [showBudget, setShowBudget] = useState(false)

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

  // Fetch budget data for comparison
  const { data: budgetData } = useQuery<{ date: string; budget_type: string; budget_value: number }[]>({
    queryKey: ['revenue-budget', startDate, endDate],
    queryFn: async () => {
      const params = new URLSearchParams({
        from_date: startDate,
        to_date: endDate,
      })
      const response = await fetch(`/api/budget/daily?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: showBudget,
  })

  // Organize budget data by date and type
  const budgetByDate = useMemo(() => {
    if (!budgetData) return {}
    const byDate: Record<string, Record<string, number>> = {}
    budgetData.forEach(d => {
      if (!byDate[d.date]) byDate[d.date] = {}
      byDate[d.date][d.budget_type] = d.budget_value
    })
    return byDate
  }, [budgetData])

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

    // Build budget series from budgetByDate
    let budgetAccomSeries: (number | null)[] = []
    let budgetDrySeries: (number | null)[] = []
    let budgetWetSeries: (number | null)[] = []

    if (showBudget && Object.keys(budgetByDate).length > 0) {
      budgetAccomSeries = mainData.map((d) => budgetByDate[d.date]?.net_accom ?? null)
      budgetDrySeries = mainData.map((d) => budgetByDate[d.date]?.net_dry ?? null)
      budgetWetSeries = mainData.map((d) => budgetByDate[d.date]?.net_wet ?? null)
    }

    return {
      labels, mainDates, comparisonDates: comparisonDatesArr,
      mainAccomSeries, mainDrySeries, mainWetSeries,
      compAccomSeries, compDrySeries, compWetSeries,
      budgetAccomSeries, budgetDrySeries, budgetWetSeries
    }
  }, [mainData, comparisonData, consolidation, comparison, showBudget, budgetByDate])

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

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Budget</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setShowBudget(!showBudget)}
              style={{
                ...styles.toggleButton,
                ...(showBudget ? styles.toggleButtonActive : {}),
              }}
            >
              {showBudget ? 'Hide Budget' : 'Show Budget'}
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
              // Budget traces - dashed purple
              ...(showBudget && chartData.budgetWetSeries && chartData.budgetWetSeries.some(v => v !== null)
                ? [{
                    x: chartData.labels,
                    y: chartData.budgetWetSeries,
                    type: 'scatter' as const,
                    mode: 'lines' as const,
                    name: 'Budget Wet',
                    line: { color: '#81c784', width: 2, dash: 'dot' as const },
                    hovertemplate: 'Budget Wet: £%{y:,.2f}<extra></extra>',
                  }]
                : []),
              ...(showBudget && chartData.budgetDrySeries && chartData.budgetDrySeries.some(v => v !== null)
                ? [{
                    x: chartData.labels,
                    y: chartData.budgetDrySeries,
                    type: 'scatter' as const,
                    mode: 'lines' as const,
                    name: 'Budget Dry',
                    line: { color: '#64b5f6', width: 2, dash: 'dot' as const },
                    hovertemplate: 'Budget Dry: £%{y:,.2f}<extra></extra>',
                  }]
                : []),
              ...(showBudget && chartData.budgetAccomSeries && chartData.budgetAccomSeries.some(v => v !== null)
                ? [{
                    x: chartData.labels,
                    y: chartData.budgetAccomSeries,
                    type: 'scatter' as const,
                    mode: 'lines' as const,
                    name: 'Budget Accom',
                    line: { color: '#ba68c8', width: 2, dash: 'dot' as const },
                    hovertemplate: 'Budget Accom: £%{y:,.2f}<extra></extra>',
                  }]
                : []),
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
// 3D PICKUP VISUALIZATION
// ============================================

// ============================================
// RESTAURANT BOOKINGS REPORT
// ============================================

interface RestaurantBookingsDataPoint {
  date: string
  total_bookings: number
  breakfast_bookings: number
  lunch_bookings: number
  afternoon_bookings: number
  dinner_bookings: number
  other_bookings: number
}

const RestaurantBookingsReport: React.FC = () => {
  const today = new Date()
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() - 1)
  const defaultStart = new Date(defaultEnd)
  defaultStart.setMonth(defaultEnd.getMonth() - 1)

  const [startDate, setStartDate] = useState(formatDate(defaultStart))
  const [endDate, setEndDate] = useState(formatDate(defaultEnd))
  const [consolidation, setConsolidation] = useState<ConsolidationType>('day')
  const [comparison, setComparison] = useState<ComparisonType>('previous_year')
  const [servicePeriod, setServicePeriod] = useState<'all' | 'breakfast' | 'lunch' | 'afternoon' | 'dinner'>('all')

  const handleQuickSelect = (type: QuickSelectType) => {
    const end = new Date()
    end.setDate(end.getDate() - 1)
    const start = new Date(end)

    switch (type) {
      case '7days': start.setDate(end.getDate() - 6); break
      case '14days': start.setDate(end.getDate() - 13); break
      case '1month': start.setMonth(end.getMonth() - 1); break
      case '3months': start.setMonth(end.getMonth() - 3); break
      case '6months': start.setMonth(end.getMonth() - 6); break
      case '1year': start.setFullYear(end.getFullYear() - 1); break
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

  const { data: mainData, isLoading: mainLoading } = useQuery<RestaurantBookingsDataPoint[]>({
    queryKey: ['restaurant-bookings', startDate, endDate, consolidation],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, consolidation })
      const response = await fetch(`/api/reports/restaurant-bookings?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch restaurant bookings data')
      return response.json()
    },
  })

  const { data: comparisonData } = useQuery<RestaurantBookingsDataPoint[]>({
    queryKey: ['restaurant-bookings-comparison', comparisonDates?.start, comparisonDates?.end, consolidation],
    queryFn: async () => {
      if (!comparisonDates) return []
      const params = new URLSearchParams({ start_date: comparisonDates.start, end_date: comparisonDates.end, consolidation })
      const response = await fetch(`/api/reports/restaurant-bookings?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch comparison data')
      return response.json()
    },
    enabled: !!comparisonDates,
  })

  const chartData = useMemo(() => {
    if (!mainData) return { labels: [], traces: [] }

    const labels = mainData.map(d => d.date)

    const traces: any[] = []

    // Add period-specific traces based on filter
    if (servicePeriod === 'all' || servicePeriod === 'breakfast') {
      traces.push({
        x: labels,
        y: mainData.map(d => d.breakfast_bookings),
        type: 'bar',
        name: 'Breakfast',
        marker: { color: '#FF6B6B' },
      })
    }
    if (servicePeriod === 'all' || servicePeriod === 'lunch') {
      traces.push({
        x: labels,
        y: mainData.map(d => d.lunch_bookings),
        type: 'bar',
        name: 'Lunch',
        marker: { color: '#4ECDC4' },
      })
    }
    if (servicePeriod === 'all' || servicePeriod === 'afternoon') {
      traces.push({
        x: labels,
        y: mainData.map(d => d.afternoon_bookings),
        type: 'bar',
        name: 'Afternoon',
        marker: { color: '#45B7D1' },
      })
    }
    if (servicePeriod === 'all' || servicePeriod === 'dinner') {
      traces.push({
        x: labels,
        y: mainData.map(d => d.dinner_bookings),
        type: 'bar',
        name: 'Dinner',
        marker: { color: '#96CEB4' },
      })
    }

    if (comparisonData && comparisonData.length > 0) {
      // Get comparison value based on selected period
      const getComparisonValue = (d: RestaurantBookingsDataPoint) => {
        if (servicePeriod === 'breakfast') return d.breakfast_bookings
        if (servicePeriod === 'lunch') return d.lunch_bookings
        if (servicePeriod === 'afternoon') return d.afternoon_bookings
        if (servicePeriod === 'dinner') return d.dinner_bookings
        return d.total_bookings
      }

      traces.push({
        x: labels,
        y: comparisonData.map(getComparisonValue),
        type: 'scatter',
        mode: 'lines+markers',
        name: servicePeriod === 'all' ? 'Comparison Total' : `Comparison ${servicePeriod.charAt(0).toUpperCase() + servicePeriod.slice(1)}`,
        line: { color: colors.textMuted, dash: 'dot', width: 2 },
        marker: { size: 6 },
      })
    }

    return { labels, traces }
  }, [mainData, comparisonData, servicePeriod])

  const totalBookings = mainData?.reduce((sum, d) => sum + d.total_bookings, 0) || 0

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <h2 style={styles.sectionTitle}>Restaurant Bookings</h2>
      </div>

      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Start Date</label>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={styles.dateInput} />
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>End Date</label>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={styles.dateInput} />
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Consolidation</label>
          <select value={consolidation} onChange={(e) => setConsolidation(e.target.value as ConsolidationType)} style={styles.monthSelect}>
            <option value="day">Day</option>
            <option value="week">Week</option>
            <option value="month">Month</option>
          </select>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Service Period</label>
          <select value={servicePeriod} onChange={(e) => setServicePeriod(e.target.value as any)} style={styles.monthSelect}>
            <option value="all">All Periods</option>
            <option value="breakfast">Breakfast</option>
            <option value="lunch">Lunch</option>
            <option value="afternoon">Afternoon</option>
            <option value="dinner">Dinner</option>
          </select>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Comparison</label>
          <select value={comparison} onChange={(e) => setComparison(e.target.value as ComparisonType)} style={styles.monthSelect}>
            <option value="none">None</option>
            <option value="previous_period">Previous Period</option>
            <option value="previous_year">Previous Year</option>
          </select>
        </div>
      </div>

      <div style={styles.quickSelect}>
        <span style={styles.quickSelectLabel}>Quick select:</span>
        {(['7days', '14days', '1month', '3months', '6months', '1year'] as QuickSelectType[]).map((type) => (
          <button key={type} onClick={() => handleQuickSelect(type)} style={styles.quickSelectButton}>
            {type === '7days' ? '7 days' : type === '14days' ? '14 days' : type === '1month' ? '1 month' : type === '3months' ? '3 months' : type === '6months' ? '6 months' : '1 year'}
          </button>
        ))}
      </div>

      {mainLoading ? (
        <div style={styles.loading}>Loading...</div>
      ) : (
        <>
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Total Bookings</div>
              <div style={styles.summaryValue}>{totalBookings.toLocaleString()}</div>
            </div>
          </div>

          <div style={styles.chartContainer}>
            <Plot
              data={chartData.traces}
              layout={{
                barmode: 'stack',
                title: { text: 'Restaurant Bookings by Period' },
                xaxis: { title: { text: 'Date' } },
                yaxis: { title: { text: 'Bookings' } },
                plot_bgcolor: colors.background,
                paper_bgcolor: colors.background,
                font: { color: colors.text },
                hovermode: 'closest',
                showlegend: true,
                legend: { orientation: 'h', y: -0.2 },
              }}
              config={{ responsive: true }}
              style={{ width: '100%', height: '500px' }}
            />
          </div>
        </>
      )}
    </div>
  )
}


// ============================================
// RESTAURANT COVERS REPORT
// ============================================

interface RestaurantCoversDataPoint {
  date: string
  total_covers: number
  breakfast_covers: number
  lunch_covers: number
  afternoon_covers: number
  dinner_covers: number
  other_covers: number
  hotel_guest_covers: number
  non_hotel_guest_covers: number
}

const RestaurantCoversReport: React.FC = () => {
  const today = new Date()
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() - 1)
  const defaultStart = new Date(defaultEnd)
  defaultStart.setMonth(defaultEnd.getMonth() - 1)

  const [startDate, setStartDate] = useState(formatDate(defaultStart))
  const [endDate, setEndDate] = useState(formatDate(defaultEnd))
  const [consolidation, setConsolidation] = useState<ConsolidationType>('day')
  const [comparison, setComparison] = useState<ComparisonType>('previous_year')
  const [servicePeriod, setServicePeriod] = useState<'all' | 'breakfast' | 'lunch' | 'afternoon' | 'dinner'>('all')

  const handleQuickSelect = (type: QuickSelectType) => {
    const end = new Date()
    end.setDate(end.getDate() - 1)
    const start = new Date(end)

    switch (type) {
      case '7days': start.setDate(end.getDate() - 6); break
      case '14days': start.setDate(end.getDate() - 13); break
      case '1month': start.setMonth(end.getMonth() - 1); break
      case '3months': start.setMonth(end.getMonth() - 3); break
      case '6months': start.setMonth(end.getMonth() - 6); break
      case '1year': start.setFullYear(end.getFullYear() - 1); break
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

  const { data: mainData, isLoading: mainLoading } = useQuery<RestaurantCoversDataPoint[]>({
    queryKey: ['restaurant-covers', startDate, endDate, consolidation],
    queryFn: async () => {
      const params = new URLSearchParams({ start_date: startDate, end_date: endDate, consolidation })
      const response = await fetch(`/api/reports/restaurant-covers?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch restaurant covers data')
      return response.json()
    },
  })

  const { data: comparisonData } = useQuery<RestaurantCoversDataPoint[]>({
    queryKey: ['restaurant-covers-comparison', comparisonDates?.start, comparisonDates?.end, consolidation],
    queryFn: async () => {
      if (!comparisonDates) return []
      const params = new URLSearchParams({ start_date: comparisonDates.start, end_date: comparisonDates.end, consolidation })
      const response = await fetch(`/api/reports/restaurant-covers?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch comparison data')
      return response.json()
    },
    enabled: !!comparisonDates,
  })

  const chartData = useMemo(() => {
    if (!mainData) return { labels: [], traces: [] }

    const labels = mainData.map(d => d.date)

    const traces: any[] = []

    // Add period-specific traces based on filter
    if (servicePeriod === 'all' || servicePeriod === 'breakfast') {
      traces.push({
        x: labels,
        y: mainData.map(d => d.breakfast_covers),
        type: 'bar',
        name: 'Breakfast',
        marker: { color: '#FF6B6B' },
      })
    }
    if (servicePeriod === 'all' || servicePeriod === 'lunch') {
      traces.push({
        x: labels,
        y: mainData.map(d => d.lunch_covers),
        type: 'bar',
        name: 'Lunch',
        marker: { color: '#4ECDC4' },
      })
    }
    if (servicePeriod === 'all' || servicePeriod === 'afternoon') {
      traces.push({
        x: labels,
        y: mainData.map(d => d.afternoon_covers),
        type: 'bar',
        name: 'Afternoon',
        marker: { color: '#45B7D1' },
      })
    }
    if (servicePeriod === 'all' || servicePeriod === 'dinner') {
      traces.push({
        x: labels,
        y: mainData.map(d => d.dinner_covers),
        type: 'bar',
        name: 'Dinner',
        marker: { color: '#96CEB4' },
      })
    }

    if (comparisonData && comparisonData.length > 0) {
      // Get comparison value based on selected period
      const getComparisonValue = (d: RestaurantCoversDataPoint) => {
        if (servicePeriod === 'breakfast') return d.breakfast_covers
        if (servicePeriod === 'lunch') return d.lunch_covers
        if (servicePeriod === 'afternoon') return d.afternoon_covers
        if (servicePeriod === 'dinner') return d.dinner_covers
        return d.total_covers
      }

      traces.push({
        x: labels,
        y: comparisonData.map(getComparisonValue),
        type: 'scatter',
        mode: 'lines+markers',
        name: servicePeriod === 'all' ? 'Comparison Total' : `Comparison ${servicePeriod.charAt(0).toUpperCase() + servicePeriod.slice(1)}`,
        line: { color: colors.textMuted, dash: 'dot', width: 2 },
        marker: { size: 6 },
      })
    }

    return { labels, traces }
  }, [mainData, comparisonData, servicePeriod])

  const totalCovers = mainData?.reduce((sum, d) => sum + d.total_covers, 0) || 0
  const hotelGuestCovers = mainData?.reduce((sum, d) => sum + d.hotel_guest_covers, 0) || 0
  const nonHotelGuestCovers = mainData?.reduce((sum, d) => sum + d.non_hotel_guest_covers, 0) || 0

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <h2 style={styles.sectionTitle}>Restaurant Covers</h2>
      </div>

      <div style={styles.controlsGrid}>
        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Start Date</label>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} style={styles.dateInput} />
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>End Date</label>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} style={styles.dateInput} />
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Consolidation</label>
          <select value={consolidation} onChange={(e) => setConsolidation(e.target.value as ConsolidationType)} style={styles.monthSelect}>
            <option value="day">Day</option>
            <option value="week">Week</option>
            <option value="month">Month</option>
          </select>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Service Period</label>
          <select value={servicePeriod} onChange={(e) => setServicePeriod(e.target.value as any)} style={styles.monthSelect}>
            <option value="all">All Periods</option>
            <option value="breakfast">Breakfast</option>
            <option value="lunch">Lunch</option>
            <option value="afternoon">Afternoon</option>
            <option value="dinner">Dinner</option>
          </select>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Comparison</label>
          <select value={comparison} onChange={(e) => setComparison(e.target.value as ComparisonType)} style={styles.monthSelect}>
            <option value="none">None</option>
            <option value="previous_period">Previous Period</option>
            <option value="previous_year">Previous Year</option>
          </select>
        </div>
      </div>

      <div style={styles.quickSelect}>
        <span style={styles.quickSelectLabel}>Quick select:</span>
        {(['7days', '14days', '1month', '3months', '6months', '1year'] as QuickSelectType[]).map((type) => (
          <button key={type} onClick={() => handleQuickSelect(type)} style={styles.quickSelectButton}>
            {type === '7days' ? '7 days' : type === '14days' ? '14 days' : type === '1month' ? '1 month' : type === '3months' ? '3 months' : type === '6months' ? '6 months' : '1 year'}
          </button>
        ))}
      </div>

      {mainLoading ? (
        <div style={styles.loading}>Loading...</div>
      ) : (
        <>
          <div style={styles.summaryGrid}>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Total Covers</div>
              <div style={styles.summaryValue}>{totalCovers.toLocaleString()}</div>
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Hotel Guests</div>
              <div style={styles.summaryValue}>{hotelGuestCovers.toLocaleString()}</div>
            </div>
            <div style={styles.summaryCard}>
              <div style={styles.summaryLabel}>Non-Hotel Guests</div>
              <div style={styles.summaryValue}>{nonHotelGuestCovers.toLocaleString()}</div>
            </div>
          </div>

          <div style={styles.chartContainer}>
            <Plot
              data={chartData.traces}
              layout={{
                barmode: 'stack',
                title: { text: 'Restaurant Covers by Period' },
                xaxis: { title: { text: 'Date' } },
                yaxis: { title: { text: 'Covers' } },
                plot_bgcolor: colors.background,
                paper_bgcolor: colors.background,
                font: { color: colors.text },
                hovermode: 'closest',
                showlegend: true,
                legend: { orientation: 'h', y: -0.2 },
              }}
              config={{ responsive: true }}
              style={{ width: '100%', height: '500px' }}
            />
          </div>
        </>
      )}
    </div>
  )
}


// ============================================
// PICKUP 3D VISUALIZATION
// ============================================

interface Pickup3DData {
  start_date: string
  end_date: string
  metric: string
  consolidation: string
  arrival_dates: string[]
  lead_times: number[]
  surface_data: (number | null)[][]
  final_values: (number | null)[]
}

type Pickup3DConsolidationType = 'day' | 'week'

const PickupVisualization: React.FC = () => {
  const today = new Date()
  const defaultEnd = new Date(today)
  defaultEnd.setDate(today.getDate() - 1) // Yesterday
  const defaultStart = new Date(defaultEnd)
  defaultStart.setMonth(defaultEnd.getMonth() - 1) // 1 month ago

  const [startDate, setStartDate] = useState(formatDate(defaultStart))
  const [endDate, setEndDate] = useState(formatDate(defaultEnd))
  const [metric, setMetric] = useState<'rooms' | 'occupancy'>('rooms')
  const [consolidation, setConsolidation] = useState<Pickup3DConsolidationType>('day')

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

  const { data: pickupData, isLoading, error } = useQuery<Pickup3DData>({
    queryKey: ['pickup-3d', startDate, endDate, metric, consolidation],
    queryFn: async () => {
      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        metric: metric,
        consolidation: consolidation,
      })
      const response = await fetch(`/api/reports/pickup-3d?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch pickup data')
      return response.json()
    },
  })

  // Prepare Plotly data
  const plotData = useMemo(() => {
    if (!pickupData || !pickupData.surface_data?.length) return null

    const { arrival_dates, lead_times, surface_data, final_values } = pickupData

    // X-axis: Format dates based on consolidation
    const xLabels = arrival_dates.map(d => {
      const date = new Date(d)
      if (consolidation === 'week') {
        return `${date.getMonth() + 1}/${date.getDate()}`
      }
      // For daily, show day number or short date depending on range
      if (arrival_dates.length <= 31) {
        return date.getDate().toString()
      }
      return `${date.getMonth() + 1}/${date.getDate()}`
    })

    // Y-axis: Lead times (days out)
    const yLabels = lead_times.map(lt => lt.toString())

    // Z data is already [lead_time][arrival_date]
    const z = surface_data

    return {
      z,
      x: xLabels,
      y: yLabels,
      finalValues: final_values,
      arrivalDates: arrival_dates,
    }
  }, [pickupData, consolidation])

  const metricLabel = metric === 'rooms' ? 'Room Nights' : 'Occupancy %'

  // Format date range for title
  const formatDateRange = () => {
    const start = parseDate(startDate)
    const end = parseDate(endDate)
    const startStr = start.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
    const endStr = end.toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })
    return `${startStr} - ${endStr}`
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <h2 style={styles.sectionTitle}>3D Pickup Visualization</h2>
        <p style={styles.hint}>
          Visualize how bookings accumulated over time for each arrival date
        </p>
      </div>

      {/* Controls Row 1: Date Range */}
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
            <button
              onClick={() => setConsolidation('day')}
              style={{
                ...styles.toggleButton,
                ...(consolidation === 'day' ? styles.toggleButtonActive : {}),
              }}
            >
              Daily
            </button>
            <button
              onClick={() => setConsolidation('week')}
              style={{
                ...styles.toggleButton,
                ...(consolidation === 'week' ? styles.toggleButtonActive : {}),
              }}
            >
              Weekly
            </button>
          </div>
        </div>

        <div style={styles.controlGroup}>
          <label style={styles.controlLabel}>Metric</label>
          <div style={styles.buttonGroup}>
            <button
              onClick={() => setMetric('rooms')}
              style={{
                ...styles.toggleButton,
                ...(metric === 'rooms' ? styles.toggleButtonActive : {}),
              }}
            >
              Room Nights
            </button>
            <button
              onClick={() => setMetric('occupancy')}
              style={{
                ...styles.toggleButton,
                ...(metric === 'occupancy' ? styles.toggleButtonActive : {}),
              }}
            >
              Occupancy %
            </button>
          </div>
        </div>
      </div>

      {/* Quick Select Row */}
      <div style={styles.quickSelect}>
        <span style={styles.quickSelectLabel}>Quick:</span>
        {(['7days', '14days', '1month', '3months', '6months', '1year'] as QuickSelectType[]).map((type) => (
          <button
            key={type}
            onClick={() => handleQuickSelect(type)}
            style={styles.quickSelectButton}
          >
            {type === '7days' ? '7d' :
             type === '14days' ? '14d' :
             type === '1month' ? '1m' :
             type === '3months' ? '3m' :
             type === '6months' ? '6m' : '1y'}
          </button>
        ))}
        <select
          onChange={(e) => handleMonthSelect(e.target.value)}
          value=""
          style={styles.monthSelect}
        >
          <option value="">Select Month...</option>
          {monthOptions.map((month, idx) => (
            <option key={idx} value={idx}>{month.label}</option>
          ))}
        </select>
      </div>

      {/* 3D Chart */}
      <div style={pickup3dStyles.chartContainer}>
        {isLoading ? (
          <div style={styles.loading}>Loading pickup data...</div>
        ) : error ? (
          <div style={pickup3dStyles.error}>Error loading data. Please try again.</div>
        ) : !plotData ? (
          <div style={styles.emptyState}>
            No pickup data available for this date range.
          </div>
        ) : (
          <Plot
            data={[
              // Pickup surface
              {
                type: 'surface' as const,
                z: plotData.z,
                x: plotData.x,
                y: plotData.y,
                colorscale: [
                  [0, '#fff5f0'],
                  [0.2, '#fee0d2'],
                  [0.4, '#fc9272'],
                  [0.6, '#ef3b2c'],
                  [0.8, '#cb181d'],
                  [1, '#67000d']
                ],
                opacity: 0.92,
                name: 'Bookings',
                showscale: true,
                colorbar: {
                  title: { text: metricLabel },
                  titleside: 'right' as const,
                  thickness: 15,
                  len: 0.6,
                },
                hovertemplate:
                  'Date: %{x}<br>' +
                  'Lead Time: %{y} days<br>' +
                  `${metricLabel}: %{z:.1f}<extra></extra>`,
              } as Partial<Plotly.PlotData>,
              // Final values line (d0 - arrival day)
              ...(plotData.finalValues.some(v => v !== null && v > 0) ? [{
                type: 'scatter3d' as const,
                mode: 'lines+markers' as const,
                x: plotData.x,
                y: plotData.x.map(() => '0'), // All at lead time 0
                z: plotData.finalValues,
                line: {
                  color: 'rgba(233, 69, 96, 1)',
                  width: 6,
                },
                marker: {
                  size: 5,
                  color: 'rgba(233, 69, 96, 1)',
                },
                name: 'Final (Day of Arrival)',
                hovertemplate:
                  'Date: %{x}<br>' +
                  `Final ${metricLabel}: %{z:.1f}<extra></extra>`,
              } as Partial<Plotly.PlotData>] : []),
            ]}
            layout={{
              title: {
                text: `${metricLabel} Pickup - ${formatDateRange()}`,
                font: { size: 16 },
              },
              scene: {
                xaxis: {
                  title: { text: consolidation === 'week' ? 'Week Starting' : 'Arrival Date' },
                  tickfont: { size: 10 },
                },
                yaxis: {
                  title: { text: 'Lead Time (Days Out)' },
                  tickfont: { size: 10 },
                  autorange: 'reversed' as const, // 0 at front, higher values at back
                },
                zaxis: {
                  title: { text: metricLabel },
                  tickfont: { size: 10 },
                },
                camera: {
                  eye: { x: 1.8, y: -1.8, z: 1.0 },
                },
              },
              margin: { l: 0, r: 0, t: 50, b: 0 },
              paper_bgcolor: 'transparent',
              font: { family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif' },
            }}
            style={{ width: '100%', height: '550px' }}
            config={{
              displayModeBar: true,
              displaylogo: false,
              modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
            }}
          />
        )}
      </div>

      {/* Explanation */}
      <div style={pickup3dStyles.explanation}>
        <h4 style={pickup3dStyles.explanationTitle}>How to Read This Chart</h4>
        <ul style={pickup3dStyles.explanationList}>
          <li><strong>X-axis ({consolidation === 'week' ? 'Week Starting' : 'Arrival Date'}):</strong> Each {consolidation === 'week' ? 'week' : 'day'} in the selected range</li>
          <li><strong>Y-axis (Lead Time):</strong> Days before arrival when bookings were recorded (0 = arrival day, 30 = 30 days before)</li>
          <li><strong>Z-axis (Height/Color):</strong> {metric === 'rooms' ? 'Number of rooms booked' : 'Occupancy percentage'}</li>
          <li><strong>Surface shape:</strong> The surface rises as you move toward lead time 0 (front), showing how bookings accumulated over time</li>
          <li><strong>Red line at the front:</strong> Final values on the day of arrival</li>
        </ul>
        <p style={pickup3dStyles.explanationNote}>
          Tip: Click and drag to rotate the view. Use scroll to zoom. Double-click to reset.
        </p>
      </div>
    </div>
  )
}

const pickup3dStyles: Record<string, React.CSSProperties> = {
  controls: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginBottom: spacing.lg,
    alignItems: 'flex-end',
  },
  controlGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  select: {
    padding: `${spacing.sm} ${spacing.md}`,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.sm,
    background: colors.surface,
    color: colors.text,
    cursor: 'pointer',
    minWidth: '120px',
  },
  chartContainer: {
    marginBottom: spacing.lg,
    minHeight: '550px',
    background: colors.background,
    borderRadius: radius.lg,
    overflow: 'hidden',
  },
  error: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '550px',
    color: colors.error,
  },
  explanation: {
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.md,
    marginTop: spacing.md,
  },
  explanationTitle: {
    margin: `0 0 ${spacing.sm} 0`,
    fontSize: typography.base,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  explanationList: {
    margin: 0,
    paddingLeft: spacing.lg,
    color: colors.textSecondary,
    fontSize: typography.sm,
    lineHeight: 1.6,
  },
  explanationNote: {
    margin: `${spacing.sm} 0 0 0`,
    fontSize: typography.xs,
    color: colors.textMuted,
    fontStyle: 'italic',
  },
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
    gap: spacing.md,
  },
  navGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  navGroupTitle: {
    padding: `${spacing.xs} ${spacing.sm}`,
    fontSize: typography.xs,
    fontWeight: typography.semibold,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginTop: spacing.xs,
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
