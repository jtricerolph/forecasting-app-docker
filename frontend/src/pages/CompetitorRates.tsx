import React, { useState, useMemo, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import api from '../utils/api'
import {
  colors,
  spacing,
  radius,
  typography,
  shadows,
  buttonStyle,
  badgeStyle,
  mergeStyles,
  components,
} from '../utils/theme'

// Format Date as YYYY-MM-DD using local time (avoids UTC/DST shift from toISOString)
const fmtDate = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

// ============================================
// TYPES
// ============================================

interface ScraperStatus {
  enabled: boolean
  paused: boolean
  pause_until: string | null
  backend: string
  location_configured: boolean
  location_name: string | null
  last_scrape: {
    batch_id: string
    scrape_type: string
    started_at: string | null
    completed_at: string | null
    status: string
    hotels_found: number | null
    rates_scraped: number | null
    error_message: string | null
  } | null
}

interface Hotel {
  id: number
  booking_com_id: string
  name: string
  booking_com_url: string | null
  star_rating: number | null
  review_score: number | null
  review_count: number | null
  tier: 'own' | 'competitor' | 'market'
  display_order: number
  notes: string | null
  first_seen_at: string | null
  last_seen_at: string | null
}

interface RateMatrixResponse {
  from_date: string
  to_date: string
  dates: string[]
  hotels: {
    id: number
    name: string
    tier: string
    display_order: number
    star_rating: number | null
    review_score: number | null
    booking_com_url: string | null
  }[]
  rates: Record<number, Record<string, {
    availability_status: string
    rate_gross: number | null
    room_type: string | null
    breakfast_included: boolean | null
    free_cancellation: boolean | null
    no_prepayment: boolean | null
    rooms_left: number | null
    scraped_at: string | null
  }>>
}

interface ScheduleInfo {
  daily_time: string
  today: string
  weekday: string
  tiers: {
    high: { description: string; dates_today: number; range: string | null }
    medium: { description: string; dates_today: number; range: string | null }
    low: { description: string; dates_today: number; range: string | null }
  }
  total_dates_today: number
}

interface QueueStatus {
  statuses: Record<string, { count: number; earliest: string | null; latest: string | null }>
  retries_pending: number
  total_pending: number
  total_completed: number
  total_failed: number
}

interface CoverageEntry {
  date: string
  tier: 'high' | 'medium' | 'low' | 'none'
  last_scraped: string | null
  next_expected: string | null
}

interface CoverageResponse {
  today: string
  coverage: CoverageEntry[]
}

interface ScrapeHistoryEntry {
  batch_id: string
  scrape_type: string
  started_at: string | null
  completed_at: string | null
  status: string
  dates_queued: number | null
  dates_completed: number | null
  dates_failed: number | null
  hotels_found: number | null
  rates_scraped: number | null
  error_message: string | null
  blocked_at: string | null
  resume_after: string | null
}

// ============================================
// HELPERS
// ============================================

const formatCurrency = (value: number | null): string => {
  if (value === null || value === undefined) return '-'
  return new Intl.NumberFormat('en-GB', {
    style: 'currency',
    currency: 'GBP',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

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

const formatDateTime = (iso: string | null): string => {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

const formatScrapeAge = (iso: string | null): string => {
  if (!iso) return ''
  const scraped = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - scraped.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  return `${diffDays}d ago`
}

const tierColor = (tier: string) => {
  switch (tier) {
    case 'own': return colors.info
    case 'competitor': return colors.warning
    case 'market': return colors.textMuted
    default: return colors.textMuted
  }
}

// ============================================
// TABS
// ============================================

type TabId = 'matrix' | 'hotels' | 'settings'

// ============================================
// STATUS PANEL
// ============================================

const StatusPanel: React.FC<{ status: ScraperStatus | undefined, isLoading: boolean }> = ({ status, isLoading }) => {
  if (isLoading) return <div style={styles.statusBar}>Loading status...</div>
  if (!status) return null

  return (
    <div style={styles.statusBar}>
      <div style={styles.statusItem}>
        <span style={styles.statusLabel}>Scraper</span>
        <span style={badgeStyle(status.enabled ? 'success' : 'error')}>
          {status.enabled ? 'Enabled' : 'Disabled'}
        </span>
      </div>
      {status.paused && (
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>Status</span>
          <span style={badgeStyle('warning')}>
            Paused{status.pause_until ? ` until ${formatDateTime(status.pause_until)}` : ''}
          </span>
        </div>
      )}
      <div style={styles.statusItem}>
        <span style={styles.statusLabel}>Location</span>
        <span style={{ fontSize: typography.sm, color: status.location_configured ? colors.text : colors.textMuted }}>
          {status.location_name || 'Not configured'}
        </span>
      </div>
      <div style={styles.statusItem}>
        <span style={styles.statusLabel}>Backend</span>
        <span style={{ fontSize: typography.xs, color: colors.textMuted }}>{status.backend}</span>
      </div>
      {status.last_scrape && (
        <div style={styles.statusItem}>
          <span style={styles.statusLabel}>Last Scrape</span>
          <span style={badgeStyle(
            status.last_scrape.status === 'completed' ? 'success' :
            status.last_scrape.status === 'blocked' ? 'warning' :
            status.last_scrape.status === 'running' ? 'info' : 'error'
          )}>
            {status.last_scrape.status}
          </span>
          <span style={{ fontSize: typography.xs, color: colors.textMuted }}>
            {formatDateTime(status.last_scrape.completed_at || status.last_scrape.started_at)}
            {status.last_scrape.hotels_found ? ` | ${status.last_scrape.hotels_found} hotels, ${status.last_scrape.rates_scraped} rates` : ''}
          </span>
        </div>
      )}
    </div>
  )
}

// ============================================
// SETTINGS TAB
// ============================================

const SettingsTab: React.FC = () => {
  const queryClient = useQueryClient()
  const [locationName, setLocationName] = useState('')
  const [pages, setPages] = useState(2)
  const [adults, setAdults] = useState(2)
  const [scrapeFrom, setScrapeFrom] = useState(() => fmtDate(new Date()))
  const [scrapeTo, setScrapeTo] = useState(() => {
    const d = new Date()
    d.setDate(d.getDate() + 7)
    return fmtDate(d)
  })

  const { data: status } = useQuery<ScraperStatus>({
    queryKey: ['scraper-status'],
    queryFn: async () => (await api.get('/competitor-rates/status')).data,
  })

  const { data: history } = useQuery<ScrapeHistoryEntry[]>({
    queryKey: ['scrape-history'],
    queryFn: async () => (await api.get('/competitor-rates/scrape-history?limit=10')).data,
  })

  const { data: scheduleInfo } = useQuery<ScheduleInfo>({
    queryKey: ['schedule-info'],
    queryFn: async () => (await api.get('/competitor-rates/schedule-info')).data,
  })

  const { data: queueStatus } = useQuery<QueueStatus>({
    queryKey: ['queue-status'],
    queryFn: async () => (await api.get('/competitor-rates/queue-status')).data,
    refetchInterval: 30000,
  })

  const { data: coverage } = useQuery<CoverageResponse>({
    queryKey: ['scrape-coverage'],
    queryFn: async () => (await api.get('/competitor-rates/scrape-coverage')).data,
    staleTime: 60000,
  })

  const setLocationMutation = useMutation({
    mutationFn: async () => {
      return (await api.post('/competitor-rates/config/location', {
        location_name: locationName,
        pages_to_scrape: pages,
        adults: adults,
      })).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scraper-status'] })
      setLocationName('')
    },
  })

  const enableMutation = useMutation({
    mutationFn: async (enabled: boolean) => {
      return (await api.post(`/competitor-rates/config/enable?enabled=${enabled}`)).data
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scraper-status'] }),
  })

  const unpauseMutation = useMutation({
    mutationFn: async () => (await api.post('/competitor-rates/config/unpause')).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['scraper-status'] }),
  })

  const scrapeMutation = useMutation({
    mutationFn: async () => {
      return (await api.post('/competitor-rates/scrape', {
        from_date: scrapeFrom,
        to_date: scrapeTo,
      })).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scraper-status'] })
      queryClient.invalidateQueries({ queryKey: ['scrape-history'] })
    },
  })

  return (
    <div style={styles.settingsGrid}>
      {/* Location Configuration */}
      <div style={styles.card}>
        <h3 style={styles.cardTitle}>Location Configuration</h3>
        <p style={styles.cardDescription}>
          Set the location for competitor rate scraping.
          {status?.location_name && (
            <> Currently: <strong>{status.location_name}</strong></>
          )}
        </p>
        <div style={styles.formRow}>
          <div style={styles.formGroup}>
            <label style={components.inputLabel}>Location Name</label>
            <input
              type="text"
              value={locationName}
              onChange={e => setLocationName(e.target.value)}
              placeholder="e.g. Bowness-on-Windermere"
              style={components.input}
            />
          </div>
          <div style={styles.formGroupSmall}>
            <label style={components.inputLabel}>Pages</label>
            <input
              type="number"
              value={pages}
              onChange={e => setPages(parseInt(e.target.value) || 2)}
              min={1}
              max={5}
              style={components.input}
            />
          </div>
          <div style={styles.formGroupSmall}>
            <label style={components.inputLabel}>Adults</label>
            <input
              type="number"
              value={adults}
              onChange={e => setAdults(parseInt(e.target.value) || 2)}
              min={1}
              max={4}
              style={components.input}
            />
          </div>
        </div>
        <button
          onClick={() => setLocationMutation.mutate()}
          disabled={!locationName || setLocationMutation.isPending}
          style={mergeStyles(
            buttonStyle('primary'),
            { marginTop: spacing.md, opacity: !locationName ? 0.5 : 1 }
          )}
        >
          {setLocationMutation.isPending ? 'Saving...' : 'Set Location'}
        </button>
        {setLocationMutation.isError && (
          <p style={styles.errorText}>
            {(setLocationMutation.error as any)?.response?.data?.detail || 'Failed to set location'}
          </p>
        )}
      </div>

      {/* Scraper Controls */}
      <div style={styles.card}>
        <h3 style={styles.cardTitle}>Scraper Controls</h3>
        <div style={styles.controlRow}>
          <button
            onClick={() => enableMutation.mutate(!status?.enabled)}
            style={buttonStyle(status?.enabled ? 'outline' : 'secondary')}
          >
            {status?.enabled ? 'Disable Scraper' : 'Enable Scraper'}
          </button>
          {status?.paused && (
            <button
              onClick={() => unpauseMutation.mutate()}
              style={buttonStyle('primary')}
            >
              Unpause Scraper
            </button>
          )}
        </div>
      </div>

      {/* Schedule Info */}
      <div style={styles.card}>
        <h3 style={styles.cardTitle}>Automatic Schedule</h3>
        {scheduleInfo ? (
          <div>
            <p style={styles.cardDescription}>
              Runs daily at <strong>{scheduleInfo.daily_time}</strong> ({scheduleInfo.weekday})
            </p>
            <div style={styles.scheduleGrid}>
              {Object.entries(scheduleInfo.tiers).map(([key, tier]) => (
                <div key={key} style={styles.scheduleTier}>
                  <div style={styles.scheduleTierHeader}>
                    <span style={styles.scheduleTierName}>{key}</span>
                    <span style={badgeStyle(tier.dates_today > 0 ? 'info' : 'warning')}>
                      {tier.dates_today} dates
                    </span>
                  </div>
                  <p style={styles.scheduleTierDesc}>{tier.description}</p>
                  {tier.range && (
                    <p style={styles.scheduleTierRange}>{tier.range}</p>
                  )}
                </div>
              ))}
            </div>
            <p style={{ fontSize: typography.sm, color: colors.text, marginTop: spacing.md, fontWeight: typography.semibold as any }}>
              Total today: {scheduleInfo.total_dates_today} dates
            </p>
          </div>
        ) : (
          <p style={styles.noData}>Loading schedule...</p>
        )}

        {/* Queue Status */}
        {queueStatus && (queueStatus.total_pending > 0 || queueStatus.total_failed > 0) && (
          <div style={mergeStyles(styles.queuePanel, { marginTop: spacing.md })}>
            <h4 style={{ margin: `0 0 ${spacing.sm}`, fontSize: typography.sm, color: colors.text }}>Queue</h4>
            <div style={styles.queueStats}>
              {queueStatus.total_pending > 0 && (
                <span style={badgeStyle('info')}>{queueStatus.total_pending} pending</span>
              )}
              {queueStatus.retries_pending > 0 && (
                <span style={badgeStyle('warning')}>{queueStatus.retries_pending} retries</span>
              )}
              {queueStatus.total_completed > 0 && (
                <span style={badgeStyle('success')}>{queueStatus.total_completed} done</span>
              )}
              {queueStatus.total_failed > 0 && (
                <span style={badgeStyle('error')}>{queueStatus.total_failed} failed</span>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Manual Scrape */}
      <div style={styles.card}>
        <h3 style={styles.cardTitle}>Manual Scrape</h3>
        <p style={styles.cardDescription}>
          Trigger a one-off scrape for a date range. Runs in background.
        </p>
        <div style={styles.formRow}>
          <div style={styles.formGroup}>
            <label style={components.inputLabel}>From Date</label>
            <input
              type="date"
              value={scrapeFrom}
              onChange={e => setScrapeFrom(e.target.value)}
              style={components.input}
            />
          </div>
          <div style={styles.formGroup}>
            <label style={components.inputLabel}>To Date</label>
            <input
              type="date"
              value={scrapeTo}
              onChange={e => setScrapeTo(e.target.value)}
              style={components.input}
            />
          </div>
        </div>
        <button
          onClick={() => scrapeMutation.mutate()}
          disabled={scrapeMutation.isPending || !status?.location_configured}
          style={mergeStyles(
            buttonStyle('primary'),
            { marginTop: spacing.md, opacity: (!status?.location_configured) ? 0.5 : 1 }
          )}
        >
          {scrapeMutation.isPending ? 'Starting...' : 'Start Scrape'}
        </button>
        {!status?.location_configured && (
          <p style={styles.hintText}>Configure a location first</p>
        )}
        {scrapeMutation.isSuccess && (
          <p style={{ color: colors.success, fontSize: typography.sm, marginTop: spacing.sm }}>
            Scrape started! Check status for progress.
          </p>
        )}
        {scrapeMutation.isError && (
          <p style={styles.errorText}>
            {(scrapeMutation.error as any)?.response?.data?.detail || 'Failed to start scrape'}
          </p>
        )}
      </div>

      {/* Scrape History */}
      <div style={mergeStyles(styles.card, { gridColumn: '1 / -1' })}>
        <h3 style={styles.cardTitle}>Scrape History</h3>
        {history && history.length > 0 ? (
          <div style={styles.historyTable}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Type</th>
                  <th style={styles.th}>Started</th>
                  <th style={styles.th}>Status</th>
                  <th style={styles.th}>Hotels</th>
                  <th style={styles.th}>Rates</th>
                  <th style={styles.th}>Error</th>
                </tr>
              </thead>
              <tbody>
                {history.map(entry => (
                  <tr key={entry.batch_id}>
                    <td style={styles.td}>{entry.scrape_type}</td>
                    <td style={styles.td}>{formatDateTime(entry.started_at)}</td>
                    <td style={styles.td}>
                      <span style={badgeStyle(
                        entry.status === 'completed' ? 'success' :
                        entry.status === 'blocked' ? 'warning' :
                        entry.status === 'running' ? 'info' : 'error'
                      )}>
                        {entry.status}
                      </span>
                    </td>
                    <td style={styles.td}>{entry.hotels_found ?? '-'}</td>
                    <td style={styles.td}>{entry.rates_scraped ?? '-'}</td>
                    <td style={mergeStyles(styles.td, { maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis' })}>
                      {entry.error_message || '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={styles.noData}>No scrape history yet</p>
        )}
      </div>

      {/* Scrape Coverage - 365 day view */}
      <div style={mergeStyles(styles.card, { gridColumn: '1 / -1' })}>
        <h3 style={styles.cardTitle}>Scrape Coverage (365 days)</h3>
        <p style={styles.cardDescription}>
          Each cell is a date. Color shows freshness of data; letter shows priority (H=high, M=medium, L=low).
        </p>
        {coverage ? <CoverageGrid coverage={coverage} /> : <p style={styles.noData}>Loading coverage...</p>}
      </div>
    </div>
  )
}

// ============================================
// COVERAGE GRID
// ============================================

const freshnessColor = (lastScraped: string | null): React.CSSProperties => {
  if (!lastScraped) return { background: '#e8e8e8', color: colors.textMuted }
  const hours = (Date.now() - new Date(lastScraped).getTime()) / 3600000
  if (hours < 24) return { background: '#c6efce', color: '#1a7a2e' }       // green - fresh
  if (hours < 72) return { background: '#fff3cd', color: '#856404' }       // yellow - 1-3 days
  if (hours < 168) return { background: '#ffe0b2', color: '#e65100' }      // orange - 3-7 days
  if (hours < 336) return { background: '#f8d7da', color: '#721c24' }      // red - 7-14 days
  return { background: '#c62828', color: '#ffffff' }                        // dark red - >14 days
}

const tierLabel = (tier: string) => {
  switch (tier) {
    case 'high': return 'H'
    case 'medium': return 'M'
    case 'low': return 'L'
    default: return '-'
  }
}

const CoverageGrid: React.FC<{ coverage: CoverageResponse }> = ({ coverage }) => {
  // Group by month
  const months = useMemo(() => {
    const grouped: Record<string, CoverageEntry[]> = {}
    for (const entry of coverage.coverage) {
      const monthKey = entry.date.substring(0, 7) // YYYY-MM
      if (!grouped[monthKey]) grouped[monthKey] = []
      grouped[monthKey].push(entry)
    }
    return Object.entries(grouped)
  }, [coverage.coverage])

  const formatMonthLabel = (monthKey: string) => {
    const [y, m] = monthKey.split('-')
    const d = new Date(parseInt(y), parseInt(m) - 1, 1)
    return d.toLocaleDateString('en-GB', { month: 'short', year: 'numeric' })
  }

  const formatDateLabel = (dateStr: string) => {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric' })
  }

  const formatAge = (iso: string | null): string => {
    if (!iso) return 'Never scraped'
    const hours = (Date.now() - new Date(iso).getTime()) / 3600000
    if (hours < 1) return `${Math.floor(hours * 60)}m ago`
    if (hours < 24) return `${Math.floor(hours)}h ago`
    return `${Math.floor(hours / 24)}d ago`
  }

  return (
    <div style={styles.coverageContainer}>
      {/* Legend */}
      <div style={styles.coverageLegend}>
        <span style={mergeStyles(styles.coverageLegendItem, { background: '#c6efce' })}>{'<'}24h</span>
        <span style={mergeStyles(styles.coverageLegendItem, { background: '#fff3cd' })}>1-3d</span>
        <span style={mergeStyles(styles.coverageLegendItem, { background: '#ffe0b2' })}>3-7d</span>
        <span style={mergeStyles(styles.coverageLegendItem, { background: '#f8d7da' })}>7-14d</span>
        <span style={mergeStyles(styles.coverageLegendItem, { background: '#c62828', color: '#fff' })}>{'>'} 14d</span>
        <span style={mergeStyles(styles.coverageLegendItem, { background: '#e8e8e8' })}>Never</span>
        <span style={{ marginLeft: spacing.md, fontSize: typography.xs, color: colors.textMuted }}>
          H=High M=Medium L=Low priority
        </span>
      </div>
      {months.map(([monthKey, entries]) => (
        <div key={monthKey} style={styles.coverageMonth}>
          <div style={styles.coverageMonthLabel}>{formatMonthLabel(monthKey)}</div>
          <div style={styles.coverageCells}>
            {entries.map(entry => (
              <div
                key={entry.date}
                style={mergeStyles(styles.coverageCell, freshnessColor(entry.last_scraped))}
                title={`${formatDateLabel(entry.date)}\nTier: ${entry.tier}\nLast: ${formatAge(entry.last_scraped)}\nNext: ${entry.next_expected || 'N/A'}`}
              >
                <span style={styles.coverageCellDay}>
                  {new Date(entry.date + 'T00:00:00').getDate()}
                </span>
                <span style={styles.coverageCellTier}>
                  {tierLabel(entry.tier)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ============================================
// HOTELS TAB
// ============================================

const HotelsTab: React.FC = () => {
  const queryClient = useQueryClient()
  const [tierFilter, setTierFilter] = useState<string>('')

  const { data: hotels, isLoading } = useQuery<Hotel[]>({
    queryKey: ['competitor-hotels', tierFilter],
    queryFn: async () => {
      const params = tierFilter ? `?tier=${tierFilter}` : ''
      return (await api.get(`/competitor-rates/hotels${params}`)).data
    },
  })

  const tierMutation = useMutation({
    mutationFn: async ({ hotelId, tier }: { hotelId: number, tier: string }) => {
      return (await api.put(`/competitor-rates/hotels/${hotelId}/tier`, { tier })).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitor-hotels'] })
    },
  })

  const grouped = useMemo(() => {
    if (!hotels) return { own: [], competitor: [], market: [] }
    return {
      own: hotels.filter(h => h.tier === 'own'),
      competitor: hotels.filter(h => h.tier === 'competitor'),
      market: hotels.filter(h => h.tier === 'market'),
    }
  }, [hotels])

  const HotelCard: React.FC<{ hotel: Hotel }> = ({ hotel }) => (
    <div style={mergeStyles(styles.hotelCard, { borderLeft: `4px solid ${tierColor(hotel.tier)}` })}>
      <div style={styles.hotelHeader}>
        <div style={styles.hotelInfo}>
          <span style={styles.hotelName}>{hotel.name}</span>
          <div style={styles.hotelMeta}>
            {hotel.star_rating && <span>{hotel.star_rating} stars</span>}
            {hotel.review_score && <span>Score: {hotel.review_score}</span>}
            {hotel.review_count && <span>({hotel.review_count} reviews)</span>}
          </div>
        </div>
        <div style={styles.hotelActions}>
          <select
            value={hotel.tier}
            onChange={e => tierMutation.mutate({ hotelId: hotel.id, tier: e.target.value })}
            style={mergeStyles(styles.tierSelect, { borderColor: tierColor(hotel.tier) })}
          >
            <option value="own">Own Hotel</option>
            <option value="competitor">Competitor</option>
            <option value="market">Market</option>
          </select>
        </div>
      </div>
      <div style={styles.hotelFooter}>
        <span style={{ fontSize: typography.xs, color: colors.textMuted }}>
          ID: {hotel.booking_com_id}
        </span>
        {hotel.last_seen_at && (
          <span style={{ fontSize: typography.xs, color: colors.textMuted }}>
            Last seen: {formatDateTime(hotel.last_seen_at)}
          </span>
        )}
      </div>
    </div>
  )

  if (isLoading) {
    return (
      <div style={styles.loading}>
        <div style={styles.spinner} />
        <span>Loading hotels...</span>
      </div>
    )
  }

  return (
    <div>
      {/* Filter */}
      <div style={styles.filterRow}>
        <span style={styles.filterLabel}>Filter:</span>
        {['', 'own', 'competitor', 'market'].map(t => (
          <button
            key={t}
            onClick={() => setTierFilter(t)}
            style={mergeStyles(
              buttonStyle(tierFilter === t ? 'secondary' : 'outline', 'small'),
              tierFilter === t ? {} : { opacity: 0.7 }
            )}
          >
            {t || 'All'} {t && hotels ? `(${grouped[t as keyof typeof grouped]?.length || 0})` : hotels ? `(${hotels.length})` : ''}
          </button>
        ))}
      </div>

      {/* Hotels */}
      {!hotels || hotels.length === 0 ? (
        <div style={styles.emptyState}>
          <h3 style={{ margin: 0, color: colors.text }}>No Hotels Discovered</h3>
          <p style={{ color: colors.textSecondary, margin: `${spacing.sm} 0 0` }}>
            Run a scrape to discover hotels in your configured location.
          </p>
        </div>
      ) : (
        <div>
          {/* Own Hotel */}
          {grouped.own.length > 0 && (
            <div style={styles.tierSection}>
              <h3 style={mergeStyles(styles.tierHeader, { color: colors.info })}>
                Your Hotel ({grouped.own.length})
              </h3>
              {grouped.own.map(h => <HotelCard key={h.id} hotel={h} />)}
            </div>
          )}

          {/* Competitors */}
          {grouped.competitor.length > 0 && (
            <div style={styles.tierSection}>
              <h3 style={mergeStyles(styles.tierHeader, { color: colors.warning })}>
                Competitors ({grouped.competitor.length})
              </h3>
              {grouped.competitor.map(h => <HotelCard key={h.id} hotel={h} />)}
            </div>
          )}

          {/* Market */}
          {grouped.market.length > 0 && (
            <div style={styles.tierSection}>
              <h3 style={mergeStyles(styles.tierHeader, { color: colors.textMuted })}>
                Market ({grouped.market.length})
              </h3>
              {grouped.market.map(h => <HotelCard key={h.id} hotel={h} />)}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ============================================
// RATE MATRIX TAB
// ============================================

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

const RateMatrixTab: React.FC = () => {
  const [selectedMonth, setSelectedMonth] = useState(() => {
    const today = new Date()
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`
  })
  const [includeMarket, setIncludeMarket] = useState(false)
  const [hoveredCell, setHoveredCell] = useState<{ row: number; col: number } | null>(null)
  const [scrapingDate, setScrapingDate] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const dateScrapeM = useMutation({
    mutationFn: async (d: string) => {
      setScrapingDate(d)
      return (await api.post('/competitor-rates/scrape', { from_date: d, to_date: d })).data
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['competitor-matrix'] })
      queryClient.invalidateQueries({ queryKey: ['scraper-status'] })
      setScrapingDate(null)
    },
    onError: () => setScrapingDate(null),
  })

  const onCellEnter = useCallback((row: number, col: number) => {
    setHoveredCell({ row, col })
  }, [])
  const onCellLeave = useCallback(() => setHoveredCell(null), [])

  const { fromDate, toDate } = useMemo(() => {
    const [year, month] = selectedMonth.split('-').map(Number)
    return {
      fromDate: fmtDate(new Date(year, month - 1, 1)),
      toDate: fmtDate(new Date(year, month, 0)),
    }
  }, [selectedMonth])

  const { data, isLoading, error } = useQuery<RateMatrixResponse>({
    queryKey: ['competitor-matrix', fromDate, toDate, includeMarket],
    queryFn: async () => {
      const params = new URLSearchParams({
        from_date: fromDate,
        to_date: toDate,
        include_market: includeMarket.toString(),
      })
      return (await api.get(`/competitor-rates/matrix?${params}`)).data
    },
  })

  const dates = data?.dates || []
  const rates = data?.rates || {}

  // Sort hotels: own first, then competitor, then market
  const hotels = useMemo(() => {
    const tierPriority: Record<string, number> = { own: 0, competitor: 1, market: 2 }
    return [...(data?.hotels || [])].sort((a, b) => {
      const ta = tierPriority[a.tier] ?? 9
      const tb = tierPriority[b.tier] ?? 9
      if (ta !== tb) return ta - tb
      return (a.display_order ?? 999) - (b.display_order ?? 999)
    })
  }, [data?.hotels])

  // Compute latest scraped_at per date column across all hotels
  const scrapedAtByDate = useMemo(() => {
    const result: Record<string, string | null> = {}
    for (const d of dates) {
      let latest: string | null = null
      for (const hotel of hotels) {
        const rate = (rates[hotel.id] || {})[d]
        if (rate?.scraped_at) {
          if (!latest || rate.scraped_at > latest) {
            latest = rate.scraped_at
          }
        }
      }
      result[d] = latest
    }
    return result
  }, [dates, hotels, rates])

  if (isLoading) {
    return (
      <div style={styles.loading}>
        <div style={styles.spinner} />
        <span>Loading rate matrix...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={styles.errorBox}>
        {(error as any)?.response?.data?.detail || 'Failed to load rate matrix'}
      </div>
    )
  }

  return (
    <div>
      {/* Controls */}
      <div style={styles.matrixControls}>
        <MonthSelector value={selectedMonth} onChange={setSelectedMonth} />
        <label style={styles.checkboxLabel}>
          <input
            type="checkbox"
            checked={includeMarket}
            onChange={e => setIncludeMarket(e.target.checked)}
          />
          Include market hotels
        </label>
      </div>

      {hotels.length === 0 ? (
        <div style={styles.emptyState}>
          <h3 style={{ margin: 0, color: colors.text }}>No Rate Data</h3>
          <p style={{ color: colors.textSecondary, margin: `${spacing.sm} 0 0` }}>
            Run a scrape and categorize hotels as competitors to see rate comparisons.
          </p>
        </div>
      ) : (
        <div style={styles.matrixContainer}>
          <table style={styles.matrixTable}>
            <thead>
              <tr>
                <th style={mergeStyles(styles.matrixTh, styles.stickyCol)}>Hotel</th>
                {dates.map((d, colIdx) => {
                  const scrapeAge = formatScrapeAge(scrapedAtByDate[d])
                  const isColHovered = hoveredCell?.col === colIdx
                  return (
                    <th
                      key={d}
                      style={mergeStyles(
                        styles.matrixTh,
                        styles.dateHeader,
                        isWeekend(d) ? styles.weekendHeader : {},
                        isColHovered ? styles.crosshairCol : {}
                      )}
                      title={scrapedAtByDate[d] ? `Scraped: ${new Date(scrapedAtByDate[d]!).toLocaleString('en-GB')}` : 'No data scraped'}
                    >
                      <div style={styles.dateHeaderContent}>
                        <span style={styles.dayOfWeek}>{formatDayOfWeek(d)}</span>
                        <span style={styles.dayNum}>{formatDateShort(d)}</span>
                        {scrapeAge ? (
                          <span style={styles.scrapeAge}>{scrapeAge}</span>
                        ) : null}
                        <button
                          onClick={() => dateScrapeM.mutate(d)}
                          disabled={scrapingDate !== null}
                          style={mergeStyles(
                            styles.scrapeBtn,
                            scrapingDate === d ? styles.scrapeBtnActive : {}
                          )}
                          title={`Scrape ${d}`}
                        >
                          {scrapingDate === d ? '...' : '\u21BB'}
                        </button>
                      </div>
                    </th>
                  )
                })}
              </tr>
            </thead>
            <tbody>
              {hotels.map((hotel, rowIdx) => {
                const hotelRates = rates[hotel.id] || {}
                const isRowHovered = hoveredCell?.row === rowIdx
                return (
                  <tr key={hotel.id}>
                    <td style={mergeStyles(
                      styles.matrixTd, styles.stickyCol, styles.hotelNameCell,
                      isRowHovered ? styles.crosshairRow : {}
                    )}>
                      <div style={styles.matrixHotelInfo}>
                        <span
                          style={mergeStyles(styles.tierDot, { background: tierColor(hotel.tier) })}
                        />
                        <span style={styles.matrixHotelName}>{hotel.name}</span>
                        {hotel.star_rating && (
                          <span style={styles.matrixStars}>{hotel.star_rating}*</span>
                        )}
                      </div>
                    </td>
                    {dates.map((d, colIdx) => {
                      const rate = hotelRates[d]
                      const isAvailable = rate?.availability_status === 'available'
                      const isSoldOut = rate?.availability_status === 'sold_out'

                      let cellStyle: React.CSSProperties = styles.matrixCellEmpty
                      if (rate) {
                        if (isAvailable && rate.rate_gross) {
                          cellStyle = styles.matrixCellAvailable
                        } else if (isSoldOut) {
                          cellStyle = styles.matrixCellSoldOut
                        } else {
                          cellStyle = styles.matrixCellNoRate
                        }
                      }

                      const tooltip = rate ? [
                        rate.room_type,
                        rate.breakfast_included ? 'Breakfast incl.' : null,
                        rate.free_cancellation ? 'Free cancel' : null,
                        rate.rooms_left ? `${rate.rooms_left} left` : null,
                      ].filter(Boolean).join(' | ') : ''

                      // Build booking.com link: strip existing date/guest params, add ours
                      let bookingUrl: string | null = null
                      if (hotel.booking_com_url) {
                        const checkin = d
                        const co = new Date(d + 'T00:00:00')
                        co.setDate(co.getDate() + 1)
                        const checkout = fmtDate(co)
                        try {
                          const url = new URL(hotel.booking_com_url)
                          const stripParams = ['checkin', 'checkout', 'group_adults', 'group_children', 'req_adults', 'req_children', 'no_rooms']
                          stripParams.forEach(p => url.searchParams.delete(p))
                          url.searchParams.set('checkin', checkin)
                          url.searchParams.set('checkout', checkout)
                          url.searchParams.set('group_adults', '2')
                          bookingUrl = url.toString()
                        } catch {
                          // Fallback if URL parsing fails
                          bookingUrl = hotel.booking_com_url
                        }
                      }

                      const cellContent = rate ? (
                        isAvailable && rate.rate_gross
                          ? formatCurrency(rate.rate_gross)
                          : isSoldOut
                            ? 'Sold'
                            : '-'
                      ) : ''

                      const isRowH = hoveredCell?.row === rowIdx
                      const isColH = hoveredCell?.col === colIdx
                      const isCellH = isRowH && isColH

                      return (
                        <td
                          key={d}
                          style={mergeStyles(
                            styles.matrixTd,
                            cellStyle,
                            isWeekend(d) ? styles.weekendCell : {},
                            isRowH || isColH ? styles.crosshairHighlight : {},
                            isCellH ? styles.crosshairCell : {}
                          )}
                          title={tooltip}
                          onMouseEnter={() => onCellEnter(rowIdx, colIdx)}
                          onMouseLeave={onCellLeave}
                        >
                          {bookingUrl ? (
                            <a
                              href={bookingUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              style={styles.matrixCellLink}
                            >
                              {cellContent}
                            </a>
                          ) : cellContent}
                        </td>
                      )
                    })}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Legend */}
      <div style={styles.legend}>
        <span style={styles.legendTitle}>Legend:</span>
        <span style={mergeStyles(styles.legendItem, styles.matrixCellAvailable)}>Available</span>
        <span style={mergeStyles(styles.legendItem, styles.matrixCellSoldOut)}>Sold Out</span>
        <span style={mergeStyles(styles.legendItem, styles.matrixCellNoRate)}>No Rate</span>
        <span style={mergeStyles(styles.legendItem, styles.matrixCellEmpty)}>No Data</span>
        <span style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: spacing.sm, fontSize: typography.xs }}>
          <span style={mergeStyles(styles.tierDot, { background: colors.info })} /> Own
          <span style={mergeStyles(styles.tierDot, { background: colors.warning })} /> Competitor
          <span style={mergeStyles(styles.tierDot, { background: colors.textMuted })} /> Market
        </span>
      </div>
    </div>
  )
}

// ============================================
// MAIN COMPONENT
// ============================================

const CompetitorRates: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('matrix')

  const { data: status, isLoading: statusLoading } = useQuery<ScraperStatus>({
    queryKey: ['scraper-status'],
    queryFn: async () => (await api.get('/competitor-rates/status')).data,
    refetchInterval: 30000,
  })

  const tabs: { id: TabId; label: string }[] = [
    { id: 'matrix', label: 'Rate Matrix' },
    { id: 'hotels', label: 'Hotels' },
    { id: 'settings', label: 'Scraper Settings' },
  ]

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.pageHeader}>
        <div>
          <h1 style={styles.title}>Competitor Rates</h1>
          <p style={styles.subtitle}>
            Compare rates across competitor hotels from Booking.com
          </p>
        </div>
      </div>

      {/* Status Bar */}
      <StatusPanel status={status} isLoading={statusLoading} />

      {/* Tabs */}
      <div style={styles.tabBar}>
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={mergeStyles(
              styles.tab,
              activeTab === tab.id ? styles.tabActive : {}
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div style={styles.tabContent}>
        {activeTab === 'matrix' && <RateMatrixTab />}
        {activeTab === 'hotels' && <HotelsTab />}
        {activeTab === 'settings' && <SettingsTab />}
      </div>
    </div>
  )
}

// ============================================
// STYLES
// ============================================

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: spacing.lg,
    maxWidth: '100%',
    margin: '0 auto',
  },
  pageHeader: {
    marginBottom: spacing.md,
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

  // Status bar
  statusBar: {
    display: 'flex',
    gap: spacing.lg,
    padding: spacing.md,
    background: colors.surface,
    borderRadius: radius.lg,
    boxShadow: shadows.sm,
    marginBottom: spacing.md,
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  statusItem: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  statusLabel: {
    fontSize: typography.xs,
    color: colors.textMuted,
    textTransform: 'uppercase',
    fontWeight: typography.medium,
  },

  // Tabs
  tabBar: {
    display: 'flex',
    gap: spacing.xs,
    borderBottom: `2px solid ${colors.borderLight}`,
    marginBottom: spacing.lg,
  },
  tab: {
    padding: `${spacing.sm} ${spacing.lg}`,
    background: 'transparent',
    border: 'none',
    borderBottom: '2px solid transparent',
    cursor: 'pointer',
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.textSecondary,
    marginBottom: '-2px',
    transition: `all 0.2s`,
  },
  tabActive: {
    color: colors.primary,
    borderBottomColor: colors.primary,
    fontWeight: typography.semibold,
  },
  tabContent: {
    minHeight: '300px',
  },

  // Cards
  card: {
    background: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    boxShadow: shadows.md,
  },
  cardTitle: {
    fontSize: typography.lg,
    fontWeight: typography.semibold,
    color: colors.text,
    margin: `0 0 ${spacing.xs}`,
  },
  cardDescription: {
    fontSize: typography.sm,
    color: colors.textSecondary,
    margin: `0 0 ${spacing.md}`,
  },

  // Settings
  settingsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))',
    gap: spacing.lg,
  },
  formRow: {
    display: 'flex',
    gap: spacing.md,
    flexWrap: 'wrap',
  },
  formGroup: {
    flex: 1,
    minWidth: '200px',
  },
  formGroupSmall: {
    width: '80px',
  },
  controlRow: {
    display: 'flex',
    gap: spacing.md,
    flexWrap: 'wrap',
  },
  errorText: {
    color: colors.error,
    fontSize: typography.sm,
    marginTop: spacing.sm,
  },
  hintText: {
    color: colors.textMuted,
    fontSize: typography.xs,
    marginTop: spacing.sm,
    fontStyle: 'italic',
  },

  // Hotels
  filterRow: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.lg,
    flexWrap: 'wrap',
  },
  filterLabel: {
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.textSecondary,
  },
  tierSection: {
    marginBottom: spacing.lg,
  },
  tierHeader: {
    fontSize: typography.base,
    fontWeight: typography.semibold,
    margin: `0 0 ${spacing.sm}`,
  },
  hotelCard: {
    background: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    boxShadow: shadows.sm,
    marginBottom: spacing.sm,
  },
  hotelHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.md,
  },
  hotelInfo: {
    flex: 1,
  },
  hotelName: {
    fontSize: typography.sm,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  hotelMeta: {
    display: 'flex',
    gap: spacing.md,
    fontSize: typography.xs,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },
  hotelActions: {
    display: 'flex',
    gap: spacing.sm,
  },
  tierSelect: {
    padding: `${spacing.xs} ${spacing.sm}`,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.xs,
    cursor: 'pointer',
    background: colors.surface,
  },
  hotelFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTop: `1px solid ${colors.borderLight}`,
  },
  emptyState: {
    textAlign: 'center',
    padding: spacing.xxl,
    background: colors.surface,
    borderRadius: radius.xl,
    boxShadow: shadows.sm,
  },

  // Rate Matrix
  matrixControls: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.lg,
    marginBottom: spacing.lg,
    flexWrap: 'wrap',
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
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    fontSize: typography.sm,
    color: colors.textSecondary,
    cursor: 'pointer',
  },
  matrixContainer: {
    overflowX: 'auto',
    background: colors.surface,
    borderRadius: radius.xl,
    boxShadow: shadows.md,
  },
  matrixTable: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: typography.xs,
    minWidth: '800px',
  },
  matrixTh: {
    padding: spacing.sm,
    borderBottom: `2px solid ${colors.border}`,
    textAlign: 'center',
    fontWeight: typography.semibold,
    color: colors.text,
    whiteSpace: 'nowrap',
    background: colors.surface,
    fontSize: typography.xs,
  },
  matrixTd: {
    padding: `${spacing.xs} ${spacing.sm}`,
    borderBottom: `1px solid ${colors.borderLight}`,
    textAlign: 'center',
    whiteSpace: 'nowrap',
    fontSize: typography.xs,
  },
  stickyCol: {
    position: 'sticky',
    left: 0,
    background: colors.surface,
    zIndex: 10,
    textAlign: 'left',
    minWidth: '180px',
    maxWidth: '220px',
    borderRight: `1px solid ${colors.border}`,
  },
  hotelNameCell: {
    fontWeight: typography.medium,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  matrixHotelInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  tierDot: {
    width: '8px',
    height: '8px',
    borderRadius: radius.full,
    flexShrink: 0,
    display: 'inline-block',
  },
  matrixHotelName: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  matrixStars: {
    color: colors.warning,
    fontSize: typography.xs,
    flexShrink: 0,
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
  scrapeAge: {
    fontSize: '9px',
    color: colors.success,
    fontWeight: typography.normal,
    opacity: 0.8,
    lineHeight: 1,
  },
  weekendHeader: {
    background: colors.background,
  },
  weekendCell: {
    borderLeft: `2px solid ${colors.border}`,
  },
  matrixCellAvailable: {
    background: colors.successBg,
    color: colors.success,
    fontWeight: typography.semibold,
  },
  matrixCellSoldOut: {
    background: colors.errorBg,
    color: colors.error,
  },
  matrixCellNoRate: {
    background: colors.warningBg,
    color: colors.warning,
  },
  matrixCellEmpty: {
    background: colors.background,
    color: colors.textMuted,
  },
  matrixCellLink: {
    color: 'inherit',
    textDecoration: 'none',
    display: 'block',
    width: '100%',
    height: '100%',
  } as React.CSSProperties,
  crosshairHighlight: {
    boxShadow: `inset 0 0 0 1px ${colors.primary}33`,
    background: `${colors.primary}08`,
  },
  crosshairCell: {
    boxShadow: `inset 0 0 0 2px ${colors.primary}`,
  },
  crosshairRow: {
    boxShadow: `inset 0 0 0 1px ${colors.primary}33`,
    background: `${colors.primary}08`,
  },
  crosshairCol: {
    boxShadow: `inset 0 0 0 1px ${colors.primary}33`,
    background: `${colors.primary}08`,
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

  // Shared
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: typography.sm,
  },
  th: {
    padding: spacing.sm,
    borderBottom: `2px solid ${colors.border}`,
    textAlign: 'left',
    fontWeight: typography.semibold,
    color: colors.text,
    whiteSpace: 'nowrap',
    fontSize: typography.xs,
  },
  td: {
    padding: spacing.sm,
    borderBottom: `1px solid ${colors.borderLight}`,
    fontSize: typography.sm,
  },
  historyTable: {
    overflowX: 'auto',
  },
  noData: {
    textAlign: 'center',
    padding: spacing.lg,
    color: colors.textMuted,
    fontSize: typography.sm,
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
    flexWrap: 'wrap',
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
  errorBox: {
    padding: spacing.lg,
    background: colors.errorBg,
    color: colors.error,
    borderRadius: radius.lg,
  },

  // Schedule
  scheduleGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.sm,
  },
  scheduleTier: {
    padding: spacing.sm,
    background: colors.background,
    borderRadius: radius.md,
  },
  scheduleTierHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  scheduleTierName: {
    fontSize: typography.sm,
    fontWeight: typography.semibold,
    color: colors.text,
    textTransform: 'capitalize',
  },
  scheduleTierDesc: {
    fontSize: typography.xs,
    color: colors.textSecondary,
    margin: `${spacing.xs} 0 0`,
  },
  scheduleTierRange: {
    fontSize: typography.xs,
    color: colors.textMuted,
    margin: `2px 0 0`,
    fontFamily: 'monospace',
  },
  queuePanel: {
    padding: spacing.sm,
    background: colors.background,
    borderRadius: radius.md,
  },
  queueStats: {
    display: 'flex',
    gap: spacing.sm,
    flexWrap: 'wrap',
  },

  // Coverage grid
  coverageContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.md,
  },
  coverageLegend: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    fontSize: typography.xs,
    flexWrap: 'wrap',
  },
  coverageLegendItem: {
    padding: `2px ${spacing.sm}`,
    borderRadius: radius.sm,
    fontSize: typography.xs,
  },
  coverageMonth: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: spacing.sm,
  },
  coverageMonthLabel: {
    fontSize: typography.xs,
    fontWeight: typography.semibold,
    color: colors.text,
    minWidth: '70px',
    paddingTop: '3px',
    flexShrink: 0,
  },
  coverageCells: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '3px',
  },
  coverageCell: {
    width: '32px',
    height: '28px',
    borderRadius: '3px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'default',
    lineHeight: 1,
    border: '1px solid rgba(0,0,0,0.06)',
  },
  coverageCellDay: {
    fontSize: '9px',
    fontWeight: typography.semibold,
  },
  coverageCellTier: {
    fontSize: '7px',
    opacity: 0.7,
  },
}

export default CompetitorRates
