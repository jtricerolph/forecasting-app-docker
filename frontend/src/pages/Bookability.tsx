import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import {
  colors,
  spacing,
  radius,
  typography,
  shadows,
  buttonStyle,
  badgeStyle,
  mergeStyles,
} from '../utils/theme'

// Format Date as YYYY-MM-DD using local time (avoids UTC/DST shift from toISOString)
const fmtDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// Types
interface CategoryInfo {
  category_id: string
  category_name: string
  room_count: number
}

interface TariffInfo {
  name: string
  description?: string
  rate: number | null
  average_nightly?: number
  available: boolean
  message: string
  sort_order?: number
  min_stay?: number | null
  available_for_min_stay?: boolean | null  // True if available when queried with min_stay nights
}

interface OccupancyInfo {
  occupied: number
  available: number
  maintenance: number
}

interface DateRateInfo {
  rate_gross: number | null
  rate_net: number | null
  tariffs: TariffInfo[]
  tariff_count: number
  occupancy?: OccupancyInfo
}

interface RateMatrixData {
  categories: CategoryInfo[]
  dates: string[]
  matrix: Record<string, Record<string, DateRateInfo>>
}

// Helper functions
const formatDateShort = (dateStr: string): string => {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-GB', { day: 'numeric' })
}

const formatDayOfWeek = (dateStr: string): string => {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-GB', { weekday: 'short' })
}

const isWeekend = (dateStr: string): boolean => {
  const date = new Date(dateStr + 'T00:00:00')
  const day = date.getDay()
  return day === 0 || day === 6
}

const formatCurrency = (value: number | null): string => {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'GBP',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

// Components
const MonthSelector: React.FC<{
  value: string
  onChange: (value: string) => void
}> = ({ value, onChange }) => {
  const handlePrevMonth = () => {
    const [year, month] = value.split('-').map(Number)
    const date = new Date(year, month - 2, 1)
    onChange(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`)
  }

  const handleNextMonth = () => {
    const [year, month] = value.split('-').map(Number)
    const date = new Date(year, month, 1)
    onChange(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`)
  }

  // Generate month options (current month + next 12 months)
  const monthOptions = useMemo(() => {
    const options: { value: string; label: string }[] = []
    const now = new Date()
    for (let i = 0; i < 13; i++) {
      const date = new Date(now.getFullYear(), now.getMonth() + i, 1)
      const monthValue = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
      const label = date.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' })
      options.push({ value: monthValue, label })
    }
    return options
  }, [])

  return (
    <div style={styles.monthSelector}>
      <button onClick={handlePrevMonth} style={buttonStyle('outline', 'small')}>
        &larr;
      </button>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={styles.monthDropdown}
      >
        {monthOptions.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      <button onClick={handleNextMonth} style={buttonStyle('outline', 'small')}>
        &rarr;
      </button>
    </div>
  )
}

const CategorySection: React.FC<{
  category: CategoryInfo
  dates: string[]
  rateData: Record<string, DateRateInfo>
  onRefreshDate?: (d: string) => void
  refreshingDate?: string | null
}> = ({ category, dates, rateData, onRefreshDate, refreshingDate }) => {
  // Collect all unique tariff names across all dates, preserving Newbook order
  const allTariffNames = useMemo(() => {
    const tariffMap = new Map<string, number>() // name -> sort_order
    for (const dateStr of dates) {
      const data = rateData[dateStr]
      if (data?.tariffs) {
        for (const tariff of data.tariffs) {
          // Only add if not already present (keep first occurrence's order)
          if (!tariffMap.has(tariff.name)) {
            tariffMap.set(tariff.name, tariff.sort_order ?? 999)
          }
        }
      }
    }
    // Sort by Newbook order (sort_order), not alphabetically
    return Array.from(tariffMap.entries())
      .sort((a, b) => a[1] - b[1])
      .map(([name]) => name)
  }, [dates, rateData])

  if (allTariffNames.length === 0) {
    return (
      <div style={styles.categorySection}>
        <h3 style={styles.categoryTitle}>
          {category.category_name}
          <span style={styles.roomCount}>({category.room_count} rooms)</span>
        </h3>
        <p style={styles.noData}>No rate data available for this period</p>
      </div>
    )
  }

  return (
    <div style={styles.categorySection}>
      <h3 style={styles.categoryTitle}>
        {category.category_name}
        <span style={styles.roomCount}>({category.room_count} rooms)</span>
      </h3>
      <div style={styles.tableContainer}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={mergeStyles(styles.th, styles.stickyCol)}>Tariff</th>
              {dates.map(dateStr => (
                <th
                  key={dateStr}
                  style={mergeStyles(
                    styles.th,
                    styles.dateHeader,
                    isWeekend(dateStr) ? styles.weekendHeader : {}
                  )}
                >
                  <div style={styles.dateHeaderContent}>
                    <span style={styles.dayOfWeek}>{formatDayOfWeek(dateStr)}</span>
                    <span style={styles.dayNum}>{formatDateShort(dateStr)}</span>
                    {onRefreshDate && (
                      <button
                        onClick={() => onRefreshDate(dateStr)}
                        disabled={refreshingDate !== null}
                        style={mergeStyles(
                          styles.scrapeBtn,
                          refreshingDate === dateStr ? styles.scrapeBtnActive : {}
                        )}
                        title={`Refresh ${dateStr}`}
                      >
                        {refreshingDate === dateStr ? '...' : '\u21BB'}
                      </button>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {/* Occupancy row */}
            <tr>
              <td style={mergeStyles(styles.td, styles.stickyCol, styles.occupancyLabel)}>
                Occupancy
              </td>
              {dates.map(dateStr => {
                const data = rateData[dateStr]
                const occ = data?.occupancy
                if (!occ) {
                  return (
                    <td
                      key={dateStr}
                      style={mergeStyles(
                        styles.td,
                        styles.occupancyCell,
                        isWeekend(dateStr) ? styles.weekendCell : {}
                      )}
                    >
                      -
                    </td>
                  )
                }
                const bookableRooms = occ.available - occ.maintenance
                const roomsLeft = bookableRooms - occ.occupied
                const isFull = roomsLeft <= 0
                const occPercent = bookableRooms > 0
                  ? Math.round((occ.occupied / bookableRooms) * 100)
                  : 100
                const isHighOccupancy = occPercent >= 80 && !isFull
                const hasOffline = occ.maintenance > 0

                // Determine occupancy cell style: green=available, amber=>80%, red=full
                const getOccupancyStyle = () => {
                  if (isFull) return styles.occupancyFull
                  if (isHighOccupancy) return styles.occupancyHigh
                  return styles.occupancyAvailable
                }

                return (
                  <td
                    key={dateStr}
                    style={mergeStyles(
                      styles.td,
                      styles.occupancyCell,
                      isWeekend(dateStr) ? styles.weekendCell : {},
                      getOccupancyStyle()
                    )}
                    title={`${occ.occupied} of ${bookableRooms} bookable rooms occupied${hasOffline ? ` (${occ.maintenance} offline)` : ''} - ${roomsLeft} left`}
                  >
                    <span style={styles.occupancyText}>
                      {occ.occupied}/{occ.available}
                      {hasOffline && <span style={styles.maintenanceBadge}>({occ.maintenance})</span>}
                    </span>
                  </td>
                )
              })}
            </tr>
            {allTariffNames.map(tariffName => (
              <tr key={tariffName}>
                <td style={mergeStyles(styles.td, styles.stickyCol, styles.tariffNameCell)}>
                  {tariffName}
                </td>
                {dates.map(dateStr => {
                  const data = rateData[dateStr]
                  const tariff = data?.tariffs?.find(t => t.name === tariffName)
                  const occupancy = data?.occupancy
                  // No rooms available when all bookable rooms are occupied
                  const noRoomsAvailable = occupancy &&
                    (occupancy.available - occupancy.maintenance - occupancy.occupied) <= 0

                  if (!tariff) {
                    return (
                      <td
                        key={dateStr}
                        style={mergeStyles(
                          styles.td,
                          styles.tariffCell,
                          isWeekend(dateStr) ? styles.weekendCell : {},
                          noRoomsAvailable ? styles.cellNoRooms : styles.cellNoData
                        )}
                        title={noRoomsAvailable ? 'No rooms available' : undefined}
                      >
                        -
                      </td>
                    )
                  }

                  // Determine cell styling based on availability
                  // A tariff is considered "available" if:
                  // - available: true, OR
                  // - has min_stay > 1 AND multi-night re-query confirmed it's bookable
                  const isEffectivelyAvailable = tariff.available ||
                    (tariff.min_stay && tariff.min_stay > 1 && tariff.available_for_min_stay === true)

                  // Only show min_stay badge on confirmed-available tariffs
                  const minStayBadge = isEffectivelyAvailable && !noRoomsAvailable && tariff.min_stay && tariff.min_stay > 1 ? (
                    <span style={styles.minStayBadge} title={`Minimum ${tariff.min_stay} nights`}>
                      {tariff.min_stay}
                    </span>
                  ) : null

                  const getCellStyle = () => {
                    if (noRoomsAvailable) return styles.cellNoRooms
                    if (isEffectivelyAvailable) return styles.cellAvailable
                    return styles.cellUnavailable
                  }

                  // Build tooltip text
                  const getTooltip = () => {
                    if (noRoomsAvailable) return `${tariffName}: No rooms available`
                    if (isEffectivelyAvailable) {
                      const minStayNote = tariff.min_stay && tariff.min_stay > 1 ? ` (Min ${tariff.min_stay} nights)` : ''
                      return `${tariffName}: ${formatCurrency(tariff.rate)}${minStayNote}`
                    }
                    return `${tariffName}: ${tariff.message || 'Not available'}`
                  }

                  return (
                    <td
                      key={dateStr}
                      style={mergeStyles(
                        styles.td,
                        styles.tariffCell,
                        isWeekend(dateStr) ? styles.weekendCell : {},
                        getCellStyle(),
                        !isEffectivelyAvailable && !noRoomsAvailable ? { textDecoration: 'line-through' } : {}
                      )}
                      title={getTooltip()}
                    >
                      <span style={styles.cellContent}>
                        {tariff.rate !== null ? formatCurrency(tariff.rate) : (isEffectivelyAvailable ? 'Y' : 'N')}
                        {minStayBadge}
                      </span>
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Helper to format scrape age
const formatScrapeAge = (isoStr: string | null): string => {
  if (!isoStr) return ''
  const diff = Date.now() - new Date(isoStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

interface BookingAvailabilityData {
  has_own_hotel: boolean
  dates_checked: number
  dates_available: number
  dates_sold_out: number
  dates_no_data: number
  latest_scrape: string | null
  dates: Record<string, { status: string; rate: number | null }>
}

const BookingComSection: React.FC<{ dates: string[]; fromDate: string; toDate: string }> = ({ dates, fromDate, toDate }) => {
  const token = localStorage.getItem('token')
  const { data } = useQuery<BookingAvailabilityData>({
    queryKey: ['booking-availability', fromDate, toDate],
    queryFn: async () => {
      const params = new URLSearchParams({ from_date: fromDate, to_date: toDate })
      const res = await fetch(`/api/competitor-rates/booking-availability?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) return null
      return res.json()
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  })

  if (!data || !data.has_own_hotel) return null

  return (
    <div style={styles.categorySection}>
      <h3 style={styles.categoryTitle}>
        <span>Booking.com</span>
        <span style={styles.roomCount}>
          {data.latest_scrape ? `Scraped ${formatScrapeAge(data.latest_scrape)}` : 'No scrape data'}
          {' \u00b7 '}
          <Link to="/competitor-rates" style={{ color: colors.primary, textDecoration: 'none', fontSize: typography.sm }}>
            View details
          </Link>
        </span>
      </h3>
      <div style={styles.tableContainer}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={mergeStyles(styles.th, styles.stickyCol)}>Rate</th>
              {dates.map(dateStr => (
                <th
                  key={dateStr}
                  style={mergeStyles(
                    styles.th,
                    styles.dateHeader,
                    isWeekend(dateStr) ? styles.weekendHeader : {}
                  )}
                >
                  <div style={styles.dateHeaderContent}>
                    <span style={styles.dayOfWeek}>{formatDayOfWeek(dateStr)}</span>
                    <span style={styles.dayNum}>{formatDateShort(dateStr)}</span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={mergeStyles(styles.td, styles.stickyCol, styles.tariffNameCell)}>
                Best Available
              </td>
              {dates.map(dateStr => {
                const entry = data.dates[dateStr]
                const isAvailable = entry?.status === 'available'
                const isSoldOut = entry?.status === 'sold_out'

                const getCellStyle = () => {
                  if (!entry) return styles.cellNoData
                  if (isAvailable && entry.rate) return styles.cellAvailable
                  if (isSoldOut) return styles.bookingCellSoldOut
                  return styles.cellNoData
                }

                return (
                  <td
                    key={dateStr}
                    style={mergeStyles(
                      styles.td,
                      styles.tariffCell,
                      isWeekend(dateStr) ? styles.weekendCell : {},
                      getCellStyle()
                    )}
                    title={
                      !entry ? 'No data'
                        : isAvailable ? `Booking.com: ${formatCurrency(entry.rate)}`
                        : isSoldOut ? 'Sold out on Booking.com'
                        : 'No data'
                    }
                  >
                    {!entry ? '-'
                      : isAvailable && entry.rate ? formatCurrency(entry.rate)
                      : isSoldOut ? 'Sold'
                      : '-'}
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

const LoadingSpinner: React.FC = () => (
  <div style={styles.loading}>
    <div style={styles.spinner} />
    <span>Loading rate data...</span>
  </div>
)

const ErrorMessage: React.FC<{ message: string }> = ({ message }) => (
  <div style={styles.error}>
    <span style={styles.errorIcon}>!</span>
    {message}
  </div>
)

// Main Component
const Bookability: React.FC = () => {
  const queryClient = useQueryClient()
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const today = new Date()
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  })
  const [refreshingDate, setRefreshingDate] = useState<string | null>(null)

  // Calculate date range from selected month
  const { fromDate, toDate } = useMemo(() => {
    const [year, month] = selectedMonth.split('-').map(Number)
    const start = new Date(year, month - 1, 1)
    const end = new Date(year, month, 0) // Last day of month
    return {
      fromDate: fmtDate(start),
      toDate: fmtDate(end),
    }
  }, [selectedMonth])

  // Single-date refresh mutation
  const token = localStorage.getItem('token')
  const dateRefreshM = useMutation({
    mutationFn: async (d: string) => {
      setRefreshingDate(d)
      const res = await fetch(`/api/bookability/refresh-date/${d}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('Refresh failed')
      return res.json()
    },
    onSuccess: () => {
      // Refetch after a short delay to allow background task to complete
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['rate-matrix'] })
        setRefreshingDate(null)
      }, 3000)
    },
    onError: () => setRefreshingDate(null),
  })

  // Fetch rate matrix data
  const { data, isLoading, error, refetch } = useQuery<RateMatrixData>({
    queryKey: ['rate-matrix', fromDate, toDate],
    queryFn: async () => {
      const params = new URLSearchParams({ from_date: fromDate, to_date: toDate })
      const res = await fetch(`/api/bookability/rate-matrix?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || 'Failed to fetch rate matrix')
      }
      return res.json()
    },
    enabled: !!token,
  })

  // Calculate summary stats - focus on unbookable dates (rooms available but no rates)
  const summary = useMemo(() => {
    if (!data) return null

    let totalDateCategories = 0
    let unbookableDateCategories = 0
    let unbookableIssues: { category: string; date: string; roomsLeft: number }[] = []

    for (const cat of data.categories) {
      const catData = data.matrix[cat.category_id]
      if (!catData) continue

      for (const dateStr of data.dates) {
        const dayData = catData[dateStr]
        if (!dayData) continue

        // Check if rooms are available (bookable = available - maintenance - occupied)
        const occ = dayData.occupancy
        const bookableRooms = occ ? occ.available - occ.maintenance : 0
        const roomsLeft = occ ? bookableRooms - occ.occupied : 0
        const hasRoomsAvailable = roomsLeft > 0

        // Only count dates where rooms are available
        if (hasRoomsAvailable) {
          totalDateCategories++

          // Check if ANY tariff is available for booking
          // A tariff is "bookable" if:
          // - available: true (single-night available), OR
          // - has min_stay > 1 AND available_for_min_stay: true (verified via multi-night query)
          const hasAnyAvailableRate = dayData.tariffs?.some(t => {
            if (t.available) return true
            // If has min_stay requirement and verified available for that stay length
            if (t.min_stay && t.min_stay > 1 && t.available_for_min_stay === true) return true
            return false
          }) ?? false

          if (!hasAnyAvailableRate && dayData.tariffs && dayData.tariffs.length > 0) {
            // Rooms available but no rates bookable - this is a problem!
            unbookableDateCategories++
            unbookableIssues.push({
              category: cat.category_name,
              date: dateStr,
              roomsLeft: roomsLeft,
            })
          }
        }
      }
    }

    return {
      totalDateCategories,
      unbookableDateCategories,
      unbookablePercent: totalDateCategories > 0
        ? ((unbookableDateCategories / totalDateCategories) * 100).toFixed(1)
        : '0',
      issues: unbookableIssues.slice(0, 10),
      hasMoreIssues: unbookableIssues.length > 10,
      totalIssues: unbookableIssues.length,
    }
  }, [data])

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.headerTop}>
          <div>
            <h1 style={styles.title}>Rate Availability</h1>
            <p style={styles.subtitle}>
              View tariff availability across all room categories
            </p>
          </div>
          <div style={styles.headerActions}>
            <MonthSelector value={selectedMonth} onChange={setSelectedMonth} />
            <button
              onClick={() => refetch()}
              style={buttonStyle('outline', 'small')}
              disabled={isLoading}
            >
              Refresh
            </button>
          </div>
        </div>

        {/* Summary Stats */}
        {summary && (
          <div style={styles.summaryBar}>
            <div style={styles.summaryItem}>
              <span style={styles.summaryValue}>{data?.categories.length || 0}</span>
              <span style={styles.summaryLabel}>Room Types</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={styles.summaryValue}>{data?.dates.length || 0}</span>
              <span style={styles.summaryLabel}>Days</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={mergeStyles(
                styles.summaryValue,
                summary.unbookableDateCategories > 0 ? { color: colors.error } : { color: colors.success }
              )}>
                {summary.unbookableDateCategories}
              </span>
              <span style={styles.summaryLabel}>Unbookable</span>
            </div>
            <div style={styles.summaryItem}>
              <span style={badgeStyle(summary.unbookableDateCategories > 0 ? 'warning' : 'success')}>
                {summary.unbookablePercent}% blocked
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Content */}
      <div style={styles.content}>
        {isLoading && <LoadingSpinner />}
        {error && <ErrorMessage message={(error as Error).message} />}
        {data && data.categories.length === 0 && (
          <div style={styles.noData}>
            No room categories configured. Please set up room categories in Settings.
          </div>
        )}
        {data && data.categories.map((category) => (
          <CategorySection
            key={category.category_id}
            category={category}
            dates={data.dates}
            rateData={data.matrix[category.category_id] || {}}
            onRefreshDate={(d: string) => dateRefreshM.mutate(d)}
            refreshingDate={refreshingDate}
          />
        ))}

        {/* Booking.com as a section matching category layout */}
        {data && data.dates.length > 0 && (
          <BookingComSection dates={data.dates} fromDate={fromDate} toDate={toDate} />
        )}
      </div>

      {/* Issues Panel */}
      {summary && summary.unbookableDateCategories > 0 && (
        <div style={styles.issuesPanel}>
          <h3 style={styles.issuesTitle}>
            Unbookable Dates ({summary.totalIssues})
          </h3>
          <p style={styles.issuesSubtitle}>
            Dates with rooms available but no rates bookable
          </p>
          <div style={styles.issuesList}>
            {summary.issues.map((issue, idx) => (
              <div key={idx} style={styles.issueItem}>
                <span style={styles.issueCategory}>{issue.category}</span>
                <span style={styles.issueDate}>{issue.date}</span>
                <span style={styles.issueMessage}>{issue.roomsLeft} room{issue.roomsLeft !== 1 ? 's' : ''} available, no rates</span>
              </div>
            ))}
            {summary.hasMoreIssues && (
              <div style={styles.moreIssues}>
                +{summary.totalIssues - 10} more issues
              </div>
            )}
          </div>
        </div>
      )}

      {/* Legend */}
      <div style={styles.legend}>
        <span style={styles.legendTitle}>Legend:</span>
        <span style={mergeStyles(styles.legendItem, styles.cellAvailable)}>Available</span>
        <span style={mergeStyles(styles.legendItem, styles.cellUnavailable)}>Unavailable</span>
        <span style={mergeStyles(styles.legendItem, styles.cellNoRooms)}>No Rooms</span>
        <span style={mergeStyles(styles.legendItem, styles.cellNoData)}>No Data</span>
      </div>
    </div>
  )
}

// Styles
const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: spacing.lg,
    maxWidth: '100%',
    margin: '0 auto',
  },
  header: {
    marginBottom: spacing.lg,
  },
  headerTop: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.md,
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  title: {
    fontSize: typography.xxl,
    fontWeight: typography.bold,
    color: colors.text,
    margin: 0,
  },
  subtitle: {
    fontSize: typography.sm,
    color: colors.textSecondary,
    margin: `${spacing.xs} 0 0`,
  },
  headerActions: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.md,
  },
  monthSelector: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  monthDropdown: {
    fontSize: typography.base,
    fontWeight: typography.medium,
    color: colors.text,
    padding: `${spacing.xs} ${spacing.sm}`,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    background: colors.surface,
    cursor: 'pointer',
    minWidth: '160px',
  },
  monthDisplay: {
    fontSize: typography.lg,
    fontWeight: typography.semibold,
    color: colors.text,
    minWidth: '150px',
    textAlign: 'center',
  },
  summaryBar: {
    display: 'flex',
    gap: spacing.lg,
    padding: spacing.md,
    background: colors.surface,
    borderRadius: radius.lg,
    boxShadow: shadows.sm,
    flexWrap: 'wrap',
  },
  summaryItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: spacing.xs,
  },
  summaryValue: {
    fontSize: typography.xl,
    fontWeight: typography.bold,
    color: colors.text,
  },
  summaryLabel: {
    fontSize: typography.xs,
    color: colors.textMuted,
    textTransform: 'uppercase',
  },
  content: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.lg,
  },
  categorySection: {
    background: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    boxShadow: shadows.md,
  },
  categoryTitle: {
    fontSize: typography.lg,
    fontWeight: typography.semibold,
    color: colors.text,
    marginBottom: spacing.md,
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  roomCount: {
    fontSize: typography.sm,
    fontWeight: typography.normal,
    color: colors.textMuted,
  },
  tableContainer: {
    overflowX: 'auto',
    maxWidth: '100%',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: typography.sm,
    minWidth: '800px',
  },
  th: {
    padding: spacing.sm,
    borderBottom: `2px solid ${colors.border}`,
    textAlign: 'center',
    fontWeight: typography.semibold,
    color: colors.text,
    whiteSpace: 'nowrap',
    background: colors.surface,
  },
  td: {
    padding: spacing.sm,
    borderBottom: `1px solid ${colors.borderLight}`,
    textAlign: 'center',
    whiteSpace: 'nowrap',
  },
  stickyCol: {
    position: 'sticky',
    left: 0,
    background: colors.surface,
    zIndex: 10,
    textAlign: 'left',
    minWidth: '150px',
    maxWidth: '200px',
    borderRight: `1px solid ${colors.border}`,
  },
  dateHeader: {
    minWidth: '50px',
    padding: `${spacing.xs} ${spacing.xs}`,
  },
  dateHeaderContent: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '2px',
  },
  dayOfWeek: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  dayNum: {
    fontSize: typography.sm,
    fontWeight: typography.semibold,
  },
  weekendHeader: {
    background: colors.background,
  },
  weekendCell: {
    // Light border to indicate weekend, doesn't override availability colors
    borderLeft: `2px solid ${colors.border}`,
  },
  tariffNameCell: {
    fontWeight: typography.medium,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  tariffCell: {
    cursor: 'pointer',
    position: 'relative',
    transition: `background ${spacing.xs}`,
    fontSize: typography.xs,
  },
  cellContent: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '2px',
  },
  minStayBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '14px',
    height: '14px',
    borderRadius: radius.full,
    background: colors.warning,
    color: colors.textLight,
    fontSize: '9px',
    fontWeight: typography.bold,
    marginLeft: '2px',
    flexShrink: 0,
  },
  cellAvailable: {
    background: colors.successBg,
    color: colors.success,
  },
  cellUnavailable: {
    background: colors.errorBg,
    color: colors.error,
    textDecoration: 'line-through',
  },
  cellNoRooms: {
    background: '#e0e0e0',
    color: colors.textMuted,
  },
  cellNoData: {
    background: colors.background,
    color: colors.textMuted,
  },
  bookingCellSoldOut: {
    background: colors.errorBg,
    color: colors.error,
    fontWeight: typography.medium,
  },
  occupancyLabel: {
    fontWeight: typography.semibold,
    color: colors.primary,
    background: '#f0f4ff',
  },
  occupancyCell: {
    fontSize: typography.xs,
    color: colors.textSecondary,
    background: colors.background,
  },
  occupancyText: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '2px',
  },
  maintenanceBadge: {
    color: colors.warning,
    marginLeft: '2px',
  },
  occupancyAvailable: {
    background: colors.successBg,
    color: colors.success,
    fontWeight: typography.medium,
  },
  occupancyHigh: {
    background: colors.warningBg,
    color: colors.warning,
    fontWeight: typography.medium,
  },
  occupancyFull: {
    background: colors.errorBg,
    color: colors.error,
    fontWeight: typography.medium,
  },
  tooltip: {
    position: 'absolute',
    bottom: '100%',
    left: '50%',
    transform: 'translateX(-50%)',
    background: colors.primary,
    color: colors.textLight,
    padding: spacing.sm,
    borderRadius: radius.md,
    fontSize: typography.xs,
    whiteSpace: 'nowrap',
    zIndex: 100,
    boxShadow: shadows.lg,
    minWidth: '150px',
  },
  tooltipTitle: {
    fontWeight: typography.semibold,
    marginBottom: spacing.xs,
  },
  tooltipDesc: {
    color: 'rgba(255,255,255,0.8)',
    marginBottom: spacing.xs,
  },
  tooltipRate: {
    marginBottom: spacing.xs,
  },
  tooltipAvailable: {
    color: colors.success,
    fontWeight: typography.medium,
  },
  tooltipUnavailable: {
    color: colors.error,
    fontWeight: typography.medium,
  },
  loading: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xxl,
    gap: spacing.md,
    color: colors.textSecondary,
  },
  spinner: {
    width: '40px',
    height: '40px',
    border: `3px solid ${colors.borderLight}`,
    borderTop: `3px solid ${colors.primary}`,
    borderRadius: radius.full,
    animation: 'spin 1s linear infinite',
  },
  error: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.lg,
    background: colors.errorBg,
    color: colors.error,
    borderRadius: radius.lg,
  },
  errorIcon: {
    width: '24px',
    height: '24px',
    borderRadius: radius.full,
    background: colors.error,
    color: colors.textLight,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontWeight: typography.bold,
  },
  noData: {
    textAlign: 'center',
    padding: spacing.xl,
    color: colors.textMuted,
  },
  issuesPanel: {
    marginTop: spacing.lg,
    background: colors.warningBg,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  issuesTitle: {
    fontSize: typography.base,
    fontWeight: typography.semibold,
    color: colors.warning,
    marginBottom: spacing.xs,
  },
  issuesSubtitle: {
    fontSize: typography.sm,
    color: colors.textSecondary,
    marginBottom: spacing.md,
  },
  issuesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.sm,
  },
  issueItem: {
    display: 'flex',
    gap: spacing.sm,
    fontSize: typography.sm,
    flexWrap: 'wrap',
  },
  issueCategory: {
    fontWeight: typography.semibold,
    color: colors.text,
  },
  issueTariff: {
    color: colors.textSecondary,
  },
  issueDate: {
    color: colors.textMuted,
  },
  issueMessage: {
    color: colors.error,
    fontStyle: 'italic',
  },
  moreIssues: {
    color: colors.textMuted,
    fontStyle: 'italic',
    marginTop: spacing.sm,
  },
  legend: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.lg,
    padding: spacing.md,
    background: colors.surface,
    borderRadius: radius.lg,
    fontSize: typography.sm,
  },
  legendTitle: {
    fontWeight: typography.semibold,
    color: colors.text,
  },
  legendItem: {
    padding: `${spacing.xs} ${spacing.sm}`,
    borderRadius: radius.sm,
    fontSize: typography.xs,
  },
  scrapeBtn: {
    background: 'none',
    border: `1px solid ${colors.borderLight}`,
    borderRadius: radius.sm,
    cursor: 'pointer',
    fontSize: '10px',
    lineHeight: 1,
    padding: '2px 4px',
    color: colors.textMuted,
    opacity: 0.6,
    transition: 'opacity 0.15s',
  },
  scrapeBtnActive: {
    opacity: 1,
    color: colors.primary,
    borderColor: colors.primary,
  },
}

export default Bookability
