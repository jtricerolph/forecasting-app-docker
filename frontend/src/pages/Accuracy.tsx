import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import Plot from 'react-plotly.js'
import type Plotly from 'plotly.js'
import {
  colors,
  spacing,
  radius,
  typography,
  buttonStyle,
  badgeStyle,
  mergeStyles,
  shadows,
} from '../utils/theme'

type AccuracyPage = 'backtest' | 'accuracy' | 'weights' | 'progress'
type GroupByOption = 'lead_time' | 'day_of_week' | 'month'

// ============================================
// METRICS EXPLANATION COMPONENT
// ============================================

const MetricsLegend: React.FC<{ type: 'accuracy' | 'weights' }> = ({ type }) => {
  const [isExpanded, setIsExpanded] = useState(false)

  const accuracyMetrics = [
    {
      name: 'MAPE (Mean Absolute Percentage Error)',
      formula: '|Actual - Forecast| / Actual × 100',
      description: 'Average percentage deviation from actual values. Useful for comparing across different scales.',
      interpretation: 'Lower is better',
      guide: '< 10% = Excellent, 10-20% = Good, 20-30% = Fair, > 30% = Poor',
      color: colors.success,
    },
    {
      name: 'MAE (Mean Absolute Error)',
      formula: '|Actual - Forecast|',
      description: 'Average absolute difference between forecast and actual. In the same units as the metric (e.g., rooms or % occupancy).',
      interpretation: 'Lower is better',
      guide: 'Depends on metric scale - compare between models at the same lead time',
      color: colors.success,
    },
    {
      name: 'Sample Size (n)',
      formula: 'Count of forecast/actual pairs',
      description: 'Number of data points used to calculate the accuracy. Larger samples give more reliable metrics.',
      interpretation: 'Higher is more reliable',
      guide: 'n > 100 is statistically meaningful',
      color: colors.info,
    },
  ]

  const weightMetrics = [
    {
      name: 'Weight',
      formula: '(1/MAPE) / Sum(1/MAPE for all models)',
      description: 'Relative model performance based on inverse MAPE. Models with lower error get higher weight.',
      interpretation: 'Higher is better',
      guide: 'Weights sum to 100% within each lead time bracket. Use to blend model forecasts.',
      color: colors.success,
    },
    {
      name: 'Lead Time Bracket',
      formula: 'Days between forecast creation and target date',
      description: 'Grouping of forecasts by how far ahead they predicted. Models may excel at different horizons.',
      interpretation: 'Compare models within same bracket',
      guide: '0-7 = Short-term, 8-30 = Medium-term, 31+ = Long-term',
      color: colors.info,
    },
  ]

  const metrics = type === 'accuracy' ? accuracyMetrics : weightMetrics

  return (
    <div style={legendStyles.container}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        style={legendStyles.toggle}
      >
        <span style={legendStyles.toggleIcon}>{isExpanded ? '▼' : '▶'}</span>
        <span>Understanding the Metrics</span>
      </button>

      {isExpanded && (
        <div style={legendStyles.content}>
          {metrics.map((metric, idx) => (
            <div key={idx} style={legendStyles.metricCard}>
              <div style={legendStyles.metricHeader}>
                <span style={legendStyles.metricName}>{metric.name}</span>
                <span style={{
                  ...legendStyles.metricBadge,
                  background: metric.color,
                }}>
                  {metric.interpretation}
                </span>
              </div>
              <div style={legendStyles.metricFormula}>
                <code>{metric.formula}</code>
              </div>
              <p style={legendStyles.metricDescription}>{metric.description}</p>
              <div style={legendStyles.metricGuide}>
                <strong>Guide:</strong> {metric.guide}
              </div>
            </div>
          ))}

          {type === 'accuracy' && (
            <div style={legendStyles.colorGuide}>
              <strong>MAPE Color Scale:</strong>
              <div style={legendStyles.colorScale}>
                <span style={{ ...legendStyles.colorItem, background: colors.success }}>{'<5% Excellent'}</span>
                <span style={{ ...legendStyles.colorItem, background: '#22c55e' }}>{'5-10% Good'}</span>
                <span style={{ ...legendStyles.colorItem, background: colors.warning }}>{'10-15% Fair'}</span>
                <span style={{ ...legendStyles.colorItem, background: '#f59e0b' }}>{'15-25% Moderate'}</span>
                <span style={{ ...legendStyles.colorItem, background: colors.error }}>{'>25% Poor'}</span>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const legendStyles: Record<string, React.CSSProperties> = {
  container: {
    marginBottom: spacing.lg,
    background: colors.background,
    borderRadius: radius.lg,
    border: `1px solid ${colors.borderLight}`,
    overflow: 'hidden',
  },
  toggle: {
    width: '100%',
    padding: spacing.md,
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    color: colors.textSecondary,
    fontSize: typography.sm,
    fontWeight: typography.medium,
    textAlign: 'left',
  },
  toggleIcon: {
    fontSize: '10px',
    color: colors.textMuted,
  },
  content: {
    padding: spacing.md,
    paddingTop: 0,
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
    gap: spacing.md,
  },
  metricCard: {
    background: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    border: `1px solid ${colors.borderLight}`,
  },
  metricHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.xs,
    gap: spacing.sm,
  },
  metricName: {
    fontWeight: typography.semibold,
    color: colors.text,
    fontSize: typography.sm,
  },
  metricBadge: {
    fontSize: '10px',
    padding: '2px 6px',
    borderRadius: radius.sm,
    color: 'white',
    fontWeight: typography.medium,
    whiteSpace: 'nowrap',
  },
  metricFormula: {
    background: colors.background,
    padding: '4px 8px',
    borderRadius: radius.sm,
    marginBottom: spacing.xs,
    fontSize: typography.xs,
    fontFamily: 'monospace',
    color: colors.textSecondary,
  },
  metricDescription: {
    margin: `0 0 ${spacing.xs} 0`,
    fontSize: typography.xs,
    color: colors.textSecondary,
    lineHeight: 1.4,
  },
  metricGuide: {
    fontSize: typography.xs,
    color: colors.text,
    background: colors.background,
    padding: '4px 8px',
    borderRadius: radius.sm,
  },
  colorGuide: {
    gridColumn: '1 / -1',
    background: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    border: `1px solid ${colors.borderLight}`,
  },
  colorScale: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: spacing.xs,
    marginTop: spacing.xs,
  },
  colorItem: {
    padding: '4px 8px',
    borderRadius: radius.sm,
    fontSize: typography.xs,
    color: 'white',
    fontWeight: typography.medium,
  },
}

interface BacktestStatus {
  model: string
  metric_code: string
  total_snapshots: number
  with_actuals: number
  first_perception: string
  last_perception: string
  perception_dates: number
}

interface AccuracyBracket {
  model: string
  lead_bracket: string
  n: number
  mae: number | null
  mape: number | null
}

interface ModelWeight {
  model: string
  lead_bracket: string
  mape: number | null
  weight: number
}

interface ProductionWeight {
  metric_code: string
  snapshot_metric: string
  is_pace_metric: boolean
  models: {
    [key: string]: {
      mape: number | null
      weight: number
      sample_count: number
    }
  }
  total_samples: number
}

interface DayOfWeekAccuracy {
  model: string
  dow_num: number
  day_name: string
  n: number
  mae: number | null
  mape: number | null
}

interface MonthAccuracy {
  model: string
  month_num: number
  month_name: string
  n: number
  mae: number | null
  mape: number | null
}

const Accuracy: React.FC = () => {
  const [activePage, setActivePage] = useState<AccuracyPage>('backtest')

  const menuItems: { id: AccuracyPage; label: string }[] = [
    { id: 'backtest', label: 'Batch Backtest' },
    { id: 'accuracy', label: 'Accuracy Metrics' },
    { id: 'weights', label: 'Model Weights' },
    { id: 'progress', label: 'Forecast Progress' },
  ]

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        <h3 style={styles.sidebarTitle}>Accuracy</h3>
        <nav style={styles.nav}>
          {menuItems.map((item) => (
            <button
              key={item.id}
              onClick={() => setActivePage(item.id)}
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
        {activePage === 'backtest' && <BacktestPage />}
        {activePage === 'accuracy' && <AccuracyMetricsPage />}
        {activePage === 'weights' && <ModelWeightsPage />}
        {activePage === 'progress' && <ForecastProgressPage />}
      </main>
    </div>
  )
}

// ============================================
// BATCH BACKTEST PAGE
// ============================================

const BacktestPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [startDate, setStartDate] = useState('2025-01-06')
  const [endDate, setEndDate] = useState('2025-12-29')
  const [forecastDays, setForecastDays] = useState(365)
  const [selectedModel, setSelectedModel] = useState('xgboost')
  const [metric, setMetric] = useState('occupancy')
  const [excludeCovid, setExcludeCovid] = useState(false)
  const [runningModel, setRunningModel] = useState<string | null>(null)

  // Fetch backtest status
  const { data: statusData, isLoading: statusLoading } = useQuery<BacktestStatus[]>({
    queryKey: ['backtest-status'],
    queryFn: async () => {
      const response = await fetch('/api/backtest/batch/status', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    refetchInterval: runningModel ? 5000 : false,
  })

  // Run backtest mutation
  const runBacktestMutation = useMutation({
    mutationFn: async (model: string) => {
      const params = new URLSearchParams({
        start_perception: startDate,
        end_perception: endDate,
        forecast_days: forecastDays.toString(),
        metric: metric,
        model: model,
        exclude_covid: excludeCovid.toString(),
      })
      const response = await fetch(`/api/backtest/batch?${params}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to start backtest')
      return response.json()
    },
    onSuccess: (_, model) => {
      setRunningModel(model)
      queryClient.invalidateQueries({ queryKey: ['backtest-status'] })
    },
    onError: (error) => {
      console.error('Backtest error:', error)
      setRunningModel(null)
    }
  })

  // Backfill actuals mutation
  const backfillMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch('/api/backtest/backfill-actuals', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to backfill')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtest-status'] })
    }
  })

  // Delete model snapshots mutation
  const deleteModelMutation = useMutation({
    mutationFn: async ({ model, metricCode }: { model: string; metricCode: string }) => {
      const params = new URLSearchParams({ metric_code: metricCode })
      const response = await fetch(`/api/backtest/snapshots/${model}?${params}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to delete')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['backtest-status'] })
      queryClient.invalidateQueries({ queryKey: ['accuracy-by-bracket'] })
      queryClient.invalidateQueries({ queryKey: ['model-weights'] })
    }
  })

  const getMetricLabel = (code: string) => {
    const labels: Record<string, string> = {
      occupancy: 'Occupancy %',
      rooms: 'Room Nights',
      guests: 'Guests',
      ave_guest_rate: 'Ave Guest Rate',
      arr: 'ARR (Net)',
      net_accom: 'Net Accomm Rev',
      net_dry: 'Net Dry Rev',
      net_wet: 'Net Wet Rev',
    }
    return labels[code] || code.toUpperCase()
  }

  const handleDeleteModel = (model: string, metricCode: string) => {
    if (window.confirm(`Delete ${model.toUpperCase()} backtest data for ${getMetricLabel(metricCode)}? This cannot be undone.`)) {
      deleteModelMutation.mutate({ model, metricCode })
    }
  }

  const handleRunBacktest = () => {
    runBacktestMutation.mutate(selectedModel)
  }

  const models = ['xgboost', 'pickup', 'pickup_avg', 'prophet', 'catboost', 'blended']

  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>Batch Backtest</h2>
      <p style={styles.hint}>
        Run backtests from multiple perception dates (every Monday) to evaluate model accuracy by lead time.
      </p>

      {/* Run Backtest Controls */}
      <div style={styles.controlBox}>
        <h3 style={styles.subsectionTitle}>Run New Backtest</h3>
        <div style={styles.controlGrid}>
          <div style={styles.formGroup}>
            <label style={styles.label}>Start Date (First Monday)</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              style={styles.input}
            />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>End Date (Last Monday)</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              style={styles.input}
            />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>Forecast Days</label>
            <input
              type="number"
              value={forecastDays}
              onChange={(e) => setForecastDays(parseInt(e.target.value))}
              style={styles.input}
              min={30}
              max={365}
            />
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>Metric</label>
            <select
              value={metric}
              onChange={(e) => {
                setMetric(e.target.value)
                // Auto-switch from Pickup models for non-pace metrics
                if (!['occupancy', 'rooms'].includes(e.target.value) &&
                    (selectedModel === 'pickup' || selectedModel === 'pickup_avg')) {
                  setSelectedModel('xgboost')
                }
              }}
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
            </select>
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={styles.select}
            >
              {['occupancy', 'rooms'].includes(metric) ? (
                // All models available for pace-based metrics
                models.map(m => (
                  <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
                ))
              ) : (
                // XGBoost, CatBoost, Prophet for non-pace metrics (Pickup requires pace data)
                <>
                  <option value="xgboost">Xgboost</option>
                  <option value="catboost">Catboost</option>
                  <option value="prophet">Prophet</option>
                </>
              )}
            </select>
            {!['occupancy', 'rooms'].includes(metric) && (
              <span style={styles.checkboxHint}>
                Pickup models unavailable for this metric (requires booking pace data)
              </span>
            )}
          </div>
        </div>
        <div style={styles.checkboxRow}>
          <label style={styles.checkboxLabel}>
            <input
              type="checkbox"
              checked={excludeCovid}
              onChange={(e) => setExcludeCovid(e.target.checked)}
              style={styles.checkbox}
            />
            <span>Post-COVID Training Only</span>
          </label>
          <span style={styles.checkboxHint}>
            Train models using data from May 2021+ only (excludes COVID lockdown periods). Results stored with "_postcovid" suffix.
          </span>
        </div>
        <div style={styles.buttonRow}>
          <button
            onClick={handleRunBacktest}
            disabled={runBacktestMutation.isPending}
            style={buttonStyle('primary')}
          >
            {runBacktestMutation.isPending ? 'Starting...' : `Run ${selectedModel.toUpperCase()} Backtest`}
          </button>
          <button
            onClick={() => backfillMutation.mutate()}
            disabled={backfillMutation.isPending}
            style={buttonStyle('outline')}
          >
            {backfillMutation.isPending ? 'Backfilling...' : 'Backfill Actuals'}
          </button>
        </div>
        {runningModel && (
          <div style={styles.runningMessage}>
            {runningModel.toUpperCase()} backtest running in background. Status will update automatically.
          </div>
        )}
      </div>

      {/* Current Status */}
      <div style={{ marginTop: spacing.xl }}>
        <h3 style={styles.subsectionTitle}>Backtest Status</h3>
        {statusLoading ? (
          <div style={styles.loading}>Loading status...</div>
        ) : statusData && statusData.length > 0 ? (
          <>
            {/* Group by metric */}
            {[...new Set(statusData.map(s => s.metric_code))].sort().map(metricCode => (
              <div key={metricCode} style={{ marginBottom: spacing.lg }}>
                <h4 style={styles.metricGroupTitle}>
                  {getMetricLabel(metricCode)}
                </h4>
                <div style={styles.statusGrid}>
                  {statusData
                    .filter(s => s.metric_code === metricCode)
                    .map((status) => (
                      <div key={`${status.model}-${status.metric_code}`} style={styles.statusCard}>
                        <div style={styles.statusCardHeader}>
                          <span style={styles.statusCardModel}>{status.model.toUpperCase()}</span>
                          <span style={mergeStyles(
                            badgeStyle(status.with_actuals > 0 ? 'success' : 'warning')
                          )}>
                            {status.with_actuals > 0 ? 'Has Actuals' : 'Pending Actuals'}
                          </span>
                        </div>
                        <div style={styles.statusCardStats}>
                          <div style={styles.statItem}>
                            <span style={styles.statLabel}>Snapshots</span>
                            <span style={styles.statValue}>{status.total_snapshots.toLocaleString()}</span>
                          </div>
                          <div style={styles.statItem}>
                            <span style={styles.statLabel}>With Actuals</span>
                            <span style={styles.statValue}>{status.with_actuals.toLocaleString()}</span>
                          </div>
                          <div style={styles.statItem}>
                            <span style={styles.statLabel}>Perception Dates</span>
                            <span style={styles.statValue}>{status.perception_dates}</span>
                          </div>
                        </div>
                        <div style={styles.statusCardRange}>
                          {status.first_perception} to {status.last_perception}
                        </div>
                        <button
                          onClick={() => handleDeleteModel(status.model, status.metric_code)}
                          disabled={deleteModelMutation.isPending}
                          style={styles.deleteButton}
                          title={`Delete ${status.model} backtest data for ${status.metric_code}`}
                        >
                          {deleteModelMutation.isPending ? '...' : 'Delete'}
                        </button>
                      </div>
                    ))}
                </div>
              </div>
            ))}
          </>
        ) : (
          <div style={styles.emptyState}>
            No backtests run yet. Use the controls above to run your first backtest.
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================
// ACCURACY METRICS PAGE (Consolidated with Group By)
// ============================================

const AccuracyMetricsPage: React.FC = () => {
  const [metric, setMetric] = useState('occupancy')
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const [groupBy, setGroupBy] = useState<GroupByOption>('lead_time')

  // Fetch accuracy by bracket (lead time)
  const { data: bracketData, isLoading: bracketLoading } = useQuery<AccuracyBracket[]>({
    queryKey: ['accuracy-by-bracket', metric, selectedModel],
    queryFn: async () => {
      const params = new URLSearchParams({ metric_code: metric })
      if (selectedModel) params.append('model', selectedModel)
      const response = await fetch(`/api/backtest/accuracy-by-bracket?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: groupBy === 'lead_time',
  })

  // Fetch accuracy by day of week
  const { data: dowData, isLoading: dowLoading } = useQuery<DayOfWeekAccuracy[]>({
    queryKey: ['accuracy-by-dow', metric, selectedModel],
    queryFn: async () => {
      const params = new URLSearchParams({ metric_code: metric })
      if (selectedModel) params.append('model', selectedModel)
      const response = await fetch(`/api/backtest/accuracy-by-day-of-week?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: groupBy === 'day_of_week',
  })

  // Fetch accuracy by month
  const { data: monthData, isLoading: monthLoading } = useQuery<MonthAccuracy[]>({
    queryKey: ['accuracy-by-month', metric, selectedModel],
    queryFn: async () => {
      const params = new URLSearchParams({ metric_code: metric })
      if (selectedModel) params.append('model', selectedModel)
      const response = await fetch(`/api/backtest/accuracy-by-month?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: groupBy === 'month',
  })

  const isLoading = groupBy === 'lead_time' ? bracketLoading : groupBy === 'day_of_week' ? dowLoading : monthLoading

  const getColorForMape = (mape: number | null): string => {
    if (mape === null) return colors.textMuted
    if (mape < 5) return colors.success
    if (mape < 10) return '#22c55e'
    if (mape < 15) return colors.warning
    if (mape < 25) return '#f59e0b'
    return colors.error
  }

  const getTitle = () => {
    switch (groupBy) {
      case 'lead_time': return 'Accuracy by Lead Time'
      case 'day_of_week': return 'Accuracy by Day of Week'
      case 'month': return 'Accuracy by Month'
    }
  }

  const getHint = () => {
    switch (groupBy) {
      case 'lead_time': return 'Compare model accuracy (MAPE) across different forecast horizons.'
      case 'day_of_week': return 'Compare model accuracy across different days of the week. Useful for identifying weekday vs weekend patterns.'
      case 'month': return 'Compare model accuracy across different months. Useful for identifying seasonal patterns in forecast accuracy.'
    }
  }

  // Lead Time view data
  const bracketOrder = ['0-7', '8-14', '15-30', '31-60', '61-90', '90+']
  const bracketModels = [...new Set(bracketData?.map(d => d.model) || [])]
  const groupedByBracket = bracketOrder.map(bracket => ({
    bracket,
    models: bracketModels.map(model => {
      const data = bracketData?.find(d => d.lead_bracket === bracket && d.model === model)
      return { model, ...data }
    })
  }))

  // Day of Week view data
  const dayOrder = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
  const dowModels = [...new Set(dowData?.map(d => d.model) || [])]
  const groupedByDay = dayOrder.map(day => ({
    day,
    models: dowModels.map(model => {
      const data = dowData?.find(d => d.day_name === day && d.model === model)
      return { model, ...data }
    })
  }))

  // Month view data
  const monthOrder = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
  const monthModels = [...new Set(monthData?.map(d => d.model) || [])]
  const groupedByMonth = monthOrder.map(month => ({
    month,
    models: monthModels.map(model => {
      const data = monthData?.find(d => d.month_name === month && d.model === model)
      return { model, ...data }
    })
  }))

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>{getTitle()}</h2>
          <p style={styles.hint}>{getHint()}</p>
        </div>
        <div style={styles.filterRow}>
          <select
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as GroupByOption)}
            style={styles.select}
          >
            <option value="lead_time">Lead Time</option>
            <option value="day_of_week">Day of Week</option>
            <option value="month">Month</option>
          </select>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
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
          </select>
          <select
            value={selectedModel || ''}
            onChange={(e) => setSelectedModel(e.target.value || null)}
            style={styles.select}
          >
            <option value="">All Models</option>
            <optgroup label="Standard Training">
              <option value="xgboost">XGBoost</option>
              <option value="pickup">Pickup</option>
              <option value="prophet">Prophet</option>
              <option value="catboost">CatBoost</option>
            </optgroup>
            <optgroup label="Post-COVID Training (May 2021+)">
              <option value="xgboost_postcovid">XGBoost (Post-COVID)</option>
              <option value="pickup_postcovid">Pickup (Post-COVID)</option>
              <option value="prophet_postcovid">Prophet (Post-COVID)</option>
              <option value="catboost_postcovid">CatBoost (Post-COVID)</option>
            </optgroup>
          </select>
        </div>
      </div>

      <MetricsLegend type="accuracy" />

      {isLoading ? (
        <div style={styles.loading}>Loading accuracy data...</div>
      ) : (
        <>
          {/* LEAD TIME VIEW */}
          {groupBy === 'lead_time' && bracketData && bracketData.length > 0 && (
            <>
              <div style={styles.tableContainer}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Lead Time</th>
                      {bracketModels.map(model => (
                        <th key={model} style={styles.th} colSpan={2}>
                          {model.toUpperCase()}
                        </th>
                      ))}
                    </tr>
                    <tr>
                      <th style={styles.thSub}>Days Out</th>
                      {bracketModels.map(model => (
                        <React.Fragment key={model}>
                          <th style={styles.thSub}>MAPE %</th>
                          <th style={styles.thSub}>MAE</th>
                        </React.Fragment>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {groupedByBracket.map(({ bracket, models: modelData }) => (
                      <tr key={bracket}>
                        <td style={styles.td}>
                          <strong>{bracket}</strong> days
                        </td>
                        {modelData.map(({ model, mape, mae, n }) => (
                          <React.Fragment key={model}>
                            <td style={{
                              ...styles.td,
                              color: getColorForMape(mape ?? null),
                              fontWeight: typography.semibold,
                            }}>
                              {mape !== undefined && mape !== null ? `${mape.toFixed(1)}%` : '-'}
                              {n && <span style={styles.sampleSize}>n={n}</span>}
                            </td>
                            <td style={styles.td}>
                              {mae !== undefined && mae !== null ? mae.toFixed(2) : '-'}
                            </td>
                          </React.Fragment>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ marginTop: spacing.xl }}>
                <h3 style={styles.subsectionTitle}>MAPE Comparison</h3>
                <div style={styles.barChartContainer}>
                  {groupedByBracket.map(({ bracket, models: modelData }) => (
                    <div key={bracket} style={styles.barRow}>
                      <div style={styles.barLabel}>{bracket} days</div>
                      <div style={styles.barGroup}>
                        {modelData.map(({ model, mape }) => {
                          const width = mape ? Math.min(mape * 2, 100) : 0
                          return (
                            <div key={model} style={styles.barWrapper}>
                              <div style={styles.barModelLabel}>{model}</div>
                              <div style={styles.barTrack}>
                                <div
                                  style={{
                                    ...styles.bar,
                                    width: `${width}%`,
                                    background: model === 'xgboost' ? colors.accent :
                                               model === 'pickup' ? colors.primary :
                                               model === 'pickup_avg' ? '#17becf' :
                                               model === 'catboost' ? '#9467bd' :
                                               colors.info,
                                  }}
                                />
                              </div>
                              <div style={styles.barValue}>
                                {mape !== undefined && mape !== null ? `${mape.toFixed(1)}%` : '-'}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* DAY OF WEEK VIEW */}
          {groupBy === 'day_of_week' && dowData && dowData.length > 0 && (
            <>
              <div style={styles.tableContainer}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Day</th>
                      {dowModels.map(model => (
                        <th key={model} style={styles.th} colSpan={2}>
                          {model.toUpperCase()}
                        </th>
                      ))}
                    </tr>
                    <tr>
                      <th style={styles.thSub}>of Week</th>
                      {dowModels.map(model => (
                        <React.Fragment key={model}>
                          <th style={styles.thSub}>MAPE %</th>
                          <th style={styles.thSub}>MAE</th>
                        </React.Fragment>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {groupedByDay.map(({ day, models: modelData }) => (
                      <tr key={day}>
                        <td style={styles.td}>
                          <strong>{day}</strong>
                        </td>
                        {modelData.map(({ model, mape, mae, n }) => (
                          <React.Fragment key={model}>
                            <td style={{
                              ...styles.td,
                              color: getColorForMape(mape ?? null),
                              fontWeight: typography.semibold,
                            }}>
                              {mape !== undefined && mape !== null ? `${mape.toFixed(1)}%` : '-'}
                              {n && <span style={styles.sampleSize}>n={n}</span>}
                            </td>
                            <td style={styles.td}>
                              {mae !== undefined && mae !== null ? mae.toFixed(2) : '-'}
                            </td>
                          </React.Fragment>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ marginTop: spacing.xl }}>
                <h3 style={styles.subsectionTitle}>MAPE Comparison by Day</h3>
                <div style={styles.barChartContainer}>
                  {groupedByDay.map(({ day, models: modelData }) => (
                    <div key={day} style={styles.barRow}>
                      <div style={{ ...styles.barLabel, width: '100px' }}>{day}</div>
                      <div style={styles.barGroup}>
                        {modelData.map(({ model, mape }) => {
                          const width = mape ? Math.min(mape * 2, 100) : 0
                          return (
                            <div key={model} style={styles.barWrapper}>
                              <div style={styles.barModelLabel}>{model}</div>
                              <div style={styles.barTrack}>
                                <div
                                  style={{
                                    ...styles.bar,
                                    width: `${width}%`,
                                    background: model === 'xgboost' ? colors.accent :
                                               model === 'pickup' ? colors.primary :
                                               model === 'pickup_avg' ? '#17becf' :
                                               model === 'catboost' ? '#9467bd' :
                                               colors.info,
                                  }}
                                />
                              </div>
                              <div style={styles.barValue}>
                                {mape !== undefined && mape !== null ? `${mape.toFixed(1)}%` : '-'}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Weekday vs Weekend Summary */}
              <div style={styles.summaryBox}>
                <h4 style={styles.summaryTitle}>Weekday vs Weekend Pattern</h4>
                <div style={styles.summaryGrid}>
                  {dowModels.map(model => {
                    const weekdayData = dowData?.filter(d => d.model === model && ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'].includes(d.day_name)) || []
                    const weekendData = dowData?.filter(d => d.model === model && ['Saturday', 'Sunday'].includes(d.day_name)) || []
                    const weekdayMape = weekdayData.length > 0 ? weekdayData.reduce((sum, d) => sum + (d.mape || 0), 0) / weekdayData.length : null
                    const weekendMape = weekendData.length > 0 ? weekendData.reduce((sum, d) => sum + (d.mape || 0), 0) / weekendData.length : null
                    return (
                      <div key={model} style={styles.summaryItem}>
                        <span style={{
                          ...styles.summaryModel,
                          color: model === 'xgboost' ? colors.accent :
                                 model === 'pickup' ? colors.primary :
                                 model === 'pickup_avg' ? '#17becf' :
                                 model === 'catboost' ? '#9467bd' :
                                 colors.info,
                        }}>
                          {model.toUpperCase()}
                        </span>
                        <span style={styles.summaryBracket}>
                          Weekday: {weekdayMape ? `${weekdayMape.toFixed(1)}%` : '-'}
                        </span>
                        <span style={styles.summaryBracket}>
                          Weekend: {weekendMape ? `${weekendMape.toFixed(1)}%` : '-'}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </>
          )}

          {/* MONTH VIEW */}
          {groupBy === 'month' && monthData && monthData.length > 0 && (
            <>
              <div style={styles.tableContainer}>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Month</th>
                      {monthModels.map(model => (
                        <th key={model} style={styles.th} colSpan={2}>
                          {model.toUpperCase()}
                        </th>
                      ))}
                    </tr>
                    <tr>
                      <th style={styles.thSub}></th>
                      {monthModels.map(model => (
                        <React.Fragment key={model}>
                          <th style={styles.thSub}>MAPE %</th>
                          <th style={styles.thSub}>MAE</th>
                        </React.Fragment>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {groupedByMonth.map(({ month, models: modelData }) => (
                      <tr key={month}>
                        <td style={styles.td}>
                          <strong>{month}</strong>
                        </td>
                        {modelData.map(({ model, mape, mae, n }) => (
                          <React.Fragment key={model}>
                            <td style={{
                              ...styles.td,
                              color: getColorForMape(mape ?? null),
                              fontWeight: typography.semibold,
                            }}>
                              {mape !== undefined && mape !== null ? `${mape.toFixed(1)}%` : '-'}
                              {n && <span style={styles.sampleSize}>n={n}</span>}
                            </td>
                            <td style={styles.td}>
                              {mae !== undefined && mae !== null ? mae.toFixed(2) : '-'}
                            </td>
                          </React.Fragment>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div style={{ marginTop: spacing.xl }}>
                <h3 style={styles.subsectionTitle}>MAPE Comparison by Month</h3>
                <div style={styles.barChartContainer}>
                  {groupedByMonth.map(({ month, models: modelData }) => (
                    <div key={month} style={styles.barRow}>
                      <div style={{ ...styles.barLabel, width: '100px' }}>{month.slice(0, 3)}</div>
                      <div style={styles.barGroup}>
                        {modelData.map(({ model, mape }) => {
                          const width = mape ? Math.min(mape * 2, 100) : 0
                          return (
                            <div key={model} style={styles.barWrapper}>
                              <div style={styles.barModelLabel}>{model}</div>
                              <div style={styles.barTrack}>
                                <div
                                  style={{
                                    ...styles.bar,
                                    width: `${width}%`,
                                    background: model === 'xgboost' ? colors.accent :
                                               model === 'pickup' ? colors.primary :
                                               model === 'pickup_avg' ? '#17becf' :
                                               model === 'catboost' ? '#9467bd' :
                                               colors.info,
                                  }}
                                />
                              </div>
                              <div style={styles.barValue}>
                                {mape !== undefined && mape !== null ? `${mape.toFixed(1)}%` : '-'}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Best & Worst Months Summary */}
              <div style={styles.summaryBox}>
                <h4 style={styles.summaryTitle}>Best & Worst Months by Model</h4>
                <div style={styles.summaryGrid}>
                  {monthModels.map(model => {
                    const modelMonths = monthData?.filter(d => d.model === model && d.mape !== null) || []
                    const bestMonth = modelMonths.reduce((best, curr) =>
                      (best === null || (curr.mape !== null && curr.mape < (best.mape || Infinity))) ? curr : best,
                      null as MonthAccuracy | null
                    )
                    const worstMonth = modelMonths.reduce((worst, curr) =>
                      (worst === null || (curr.mape !== null && curr.mape > (worst.mape || 0))) ? curr : worst,
                      null as MonthAccuracy | null
                    )
                    return (
                      <div key={model} style={{ ...styles.summaryItem, flexDirection: 'column', alignItems: 'flex-start' }}>
                        <span style={{
                          ...styles.summaryModel,
                          color: model === 'xgboost' ? colors.accent :
                                 model === 'pickup' ? colors.primary :
                                 model === 'pickup_avg' ? '#17becf' :
                                 model === 'catboost' ? '#9467bd' :
                                 colors.info,
                          marginBottom: spacing.xs,
                        }}>
                          {model.toUpperCase()}
                        </span>
                        <span style={{ ...styles.summaryBracket, color: colors.success }}>
                          Best: {bestMonth?.month_name || '-'} ({bestMonth?.mape?.toFixed(1) || '-'}%)
                        </span>
                        <span style={{ ...styles.summaryBracket, color: colors.error }}>
                          Worst: {worstMonth?.month_name || '-'} ({worstMonth?.mape?.toFixed(1) || '-'}%)
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            </>
          )}

          {/* Empty state for each view */}
          {groupBy === 'lead_time' && (!bracketData || bracketData.length === 0) && (
            <div style={styles.emptyState}>
              No accuracy data available. Run backtests and backfill actuals first.
            </div>
          )}
          {groupBy === 'day_of_week' && (!dowData || dowData.length === 0) && (
            <div style={styles.emptyState}>
              No accuracy data available. Run backtests and backfill actuals first.
            </div>
          )}
          {groupBy === 'month' && (!monthData || monthData.length === 0) && (
            <div style={styles.emptyState}>
              No accuracy data available. Run backtests and backfill actuals first.
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// MODEL WEIGHTS PAGE
// ============================================

const ModelWeightsPage: React.FC = () => {
  const [metric, setMetric] = useState('occupancy')

  // Fetch production model weights (used by blended-weighted)
  const { data: productionWeights, isLoading: productionLoading } = useQuery<ProductionWeight[]>({
    queryKey: ['production-model-weights', metric],
    queryFn: async () => {
      const params = new URLSearchParams({ metric_code: metric })
      const response = await fetch(`/api/accuracy/model-weights?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Fetch model weights by lead time bracket
  const { data: weightsData, isLoading } = useQuery<ModelWeight[]>({
    queryKey: ['model-weights', metric],
    queryFn: async () => {
      const params = new URLSearchParams({ metric_code: metric })
      const response = await fetch(`/api/backtest/model-weights?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Group by bracket
  const bracketOrder = ['0-7', '8-14', '15-30', '31-60', '61-90', '90+']
  // Filter out ave_lower and ave_upper models - not needed on weights page
  const models = [...new Set(weightsData?.map(d => d.model) || [])].filter(
    m => !m.includes('lower') && !m.includes('upper')
  )

  const groupedByBracket = bracketOrder.map(bracket => {
    const bracketData = weightsData?.filter(d =>
      d.lead_bracket === bracket &&
      !d.model.includes('lower') &&
      !d.model.includes('upper')
    ) || []
    return { bracket, data: bracketData }
  })

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Model Weights</h2>
          <p style={styles.hint}>
            Weights derived from inverse MAPE. Lower error = higher weight. Use these for ensemble forecasting.
          </p>
        </div>
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
          style={styles.select}
        >
          <option value="occupancy">Occupancy</option>
          <option value="rooms">Rooms</option>
        </select>
      </div>

      <MetricsLegend type="weights" />

      {/* Production Weights Section */}
      {productionLoading ? (
        <div style={styles.loading}>Loading production weights...</div>
      ) : productionWeights && productionWeights.length > 0 ? (
        <div style={{ marginBottom: spacing.xl }}>
          <div style={styles.productionWeightsHeader}>
            <h3 style={styles.subsectionTitle}>Current Production Weights</h3>
            <p style={styles.productionWeightsHint}>
              These are the actual weights used by the blended-weighted forecast model.
              Calculated as simple average across all backtest data (not segmented by lead time).
            </p>
          </div>

          {productionWeights.map((metricData) => {
            const modelNames = Object.keys(metricData.models).sort()
            return (
              <div key={metricData.metric_code} style={styles.productionWeightsCard}>
                <div style={styles.productionWeightsCardHeader}>
                  <span style={styles.productionWeightsMetric}>
                    {metricData.is_pace_metric ? `${metric.toUpperCase()} (Pace Metric - includes Pickup)` : metric.toUpperCase()}
                  </span>
                  <span style={styles.productionWeightsSamples}>
                    {metricData.total_samples.toLocaleString()} total backtest samples
                  </span>
                </div>

                <div style={styles.productionWeightsGrid}>
                  {modelNames.map((modelName) => {
                    const model = metricData.models[modelName]
                    return (
                      <div key={modelName} style={styles.productionWeightItem}>
                        <div style={styles.productionWeightModelHeader}>
                          <span style={{
                            ...styles.productionWeightModelName,
                            color: modelName === 'xgboost' ? colors.accent :
                                   modelName === 'pickup' ? colors.primary :
                                   modelName === 'catboost' ? '#9467bd' :
                                   colors.info
                          }}>
                            {modelName.toUpperCase()}
                          </span>
                          <span style={styles.productionWeightValue}>
                            {(model.weight * 100).toFixed(1)}%
                          </span>
                        </div>
                        <div style={styles.productionWeightBarTrack}>
                          <div
                            style={{
                              ...styles.productionWeightBarFill,
                              width: `${model.weight * 100}%`,
                              background: modelName === 'xgboost' ? colors.accent :
                                         modelName === 'pickup' ? colors.primary :
                                         modelName === 'catboost' ? '#9467bd' :
                                         colors.info,
                            }}
                          />
                        </div>
                        <div style={styles.productionWeightStats}>
                          <span style={styles.productionWeightMape}>
                            MAPE: {model.mape !== null ? `${model.mape.toFixed(1)}%` : 'N/A'}
                          </span>
                          <span style={styles.productionWeightSamples}>
                            n = {model.sample_count.toLocaleString()}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>

                <div style={styles.productionWeightsNote}>
                  <strong>Note:</strong> Lower MAPE = Higher weight. Weights automatically update as more backtest data is collected.
                  These weights apply to Stage 1 of blended forecasting (before 60/40 budget blend).
                </div>
              </div>
            )
          })}
        </div>
      ) : null}

      {/* Lead Time Segmented Weights Section */}
      <div style={styles.leadTimeSection}>
        <h3 style={styles.subsectionTitle}>Weights by Lead Time Bracket</h3>
        <p style={styles.hint}>
          Model performance varies by forecast horizon. Below shows how weights change at different lead times.
        </p>
      </div>

      {isLoading ? (
        <div style={styles.loading}>Loading weights...</div>
      ) : weightsData && weightsData.length > 0 ? (
        <>
          {/* Weights Table */}
          <div style={styles.tableContainer}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Lead Time</th>
                  {models.map(model => (
                    <th key={model} style={styles.th}>
                      {model.toUpperCase()}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {groupedByBracket.map(({ bracket, data }) => (
                  <tr key={bracket}>
                    <td style={styles.td}>
                      <strong>{bracket}</strong> days
                    </td>
                    {models.map(model => {
                      const modelData = data.find(d => d.model === model)
                      const weight = modelData?.weight ?? 0
                      const isHighest = data.length > 0 &&
                        weight === Math.max(...data.map(d => d.weight))
                      return (
                        <td
                          key={model}
                          style={{
                            ...styles.td,
                            fontWeight: isHighest ? typography.bold : typography.normal,
                            color: isHighest ? colors.success : colors.text,
                          }}
                        >
                          {(weight * 100).toFixed(1)}%
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Visual Weight Distribution - Horizontal Bars */}
          <div style={{ marginTop: spacing.xl }}>
            <h3 style={styles.subsectionTitle}>Weight Distribution by Lead Time</h3>
            <div style={styles.weightGrid}>
              {groupedByBracket.map(({ bracket, data }) => (
                <div key={bracket} style={styles.weightCard}>
                  <div style={styles.weightCardHeader}>{bracket} days</div>
                  <div style={styles.weightCardBody}>
                    {data.sort((a, b) => b.weight - a.weight).map(({ model, weight }) => (
                      <div key={model} style={styles.weightRow}>
                        <div style={styles.weightModelName}>{model}</div>
                        <div style={styles.weightBarTrack}>
                          <div
                            style={{
                              ...styles.weightBarFill,
                              width: `${weight * 100}%`,
                              background: model === 'xgboost' ? colors.accent :
                                         model === 'pickup' ? colors.primary :
                                         model === 'pickup_avg' ? '#17becf' :
                                         model === 'catboost' ? '#9467bd' :
                                         colors.info,
                            }}
                          />
                        </div>
                        <div style={styles.weightPct}>{(weight * 100).toFixed(0)}%</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Summary */}
          <div style={styles.summaryBox}>
            <h4 style={styles.summaryTitle}>Best Model by Lead Time</h4>
            <div style={styles.summaryGrid}>
              {groupedByBracket.map(({ bracket, data }) => {
                const best = data.reduce((a, b) => a.weight > b.weight ? a : b, data[0])
                return (
                  <div key={bracket} style={styles.summaryItem}>
                    <span style={styles.summaryBracket}>{bracket} days:</span>
                    <span style={{
                      ...styles.summaryModel,
                      color: best?.model === 'xgboost' ? colors.accent :
                             best?.model === 'pickup' ? colors.primary :
                             best?.model === 'pickup_avg' ? '#17becf' :
                             best?.model === 'catboost' ? '#9467bd' :
                             colors.info,
                    }}>
                      {best?.model?.toUpperCase() || '-'}
                    </span>
                    <span style={styles.summaryWeight}>
                      ({((best?.weight || 0) * 100).toFixed(0)}%)
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </>
      ) : (
        <div style={styles.emptyState}>
          No weights available. Run backtests and backfill actuals to calculate model weights.
        </div>
      )}
    </div>
  )
}

// ============================================
// FORECAST PROGRESS PAGE (3D Visualization)
// ============================================

interface MonthlyProgressData {
  metric_code: string
  model: string
  year: number
  month: number
  target_dates: string[]
  perception_dates: string[]
  surface_data: (number | null)[][]
  actuals: (number | null)[]
}

const ForecastProgressPage: React.FC = () => {
  const currentDate = new Date()
  const [year, setYear] = useState(currentDate.getFullYear())
  const [month, setMonth] = useState(currentDate.getMonth()) // Previous month
  const [metric, setMetric] = useState('occupancy')
  const [model, setModel] = useState('blended')

  const metrics = [
    { value: 'occupancy', label: 'Occupancy %' },
    { value: 'rooms', label: 'Room Nights' },
    { value: 'guests', label: 'Guests' },
    { value: 'ave_guest_rate', label: 'Avg Guest Rate' },
    { value: 'arr', label: 'ARR' },
    { value: 'net_accom', label: 'Net Accom' },
    { value: 'net_dry', label: 'Net Dry' },
    { value: 'net_wet', label: 'Net Wet' },
  ]

  const models = [
    { value: 'blended', label: 'Blended' },
    { value: 'prophet', label: 'Prophet' },
    { value: 'xgboost', label: 'XGBoost' },
    { value: 'catboost', label: 'CatBoost' },
    { value: 'pickup', label: 'Pickup' },
  ]

  const months = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ]

  // Generate year options (last 2 years)
  const yearOptions = Array.from({ length: 3 }, (_, i) => currentDate.getFullYear() - 1 + i)

  const { data: progressData, isLoading, error } = useQuery<MonthlyProgressData>({
    queryKey: ['forecast-progress', year, month, metric, model],
    queryFn: async () => {
      const params = new URLSearchParams({
        year: year.toString(),
        month: (month + 1).toString(), // API expects 1-12
        metric_code: metric,
        model: model,
      })
      const response = await fetch(`/api/backtest/3d-monthly-progress?${params}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch progress data')
      return response.json()
    },
  })

  // Prepare Plotly data
  const plotData = React.useMemo(() => {
    if (!progressData || !progressData.surface_data?.length) return null

    const { target_dates, perception_dates, surface_data, actuals } = progressData

    // Format dates for display
    const xLabels = target_dates.map(d => {
      const date = new Date(d)
      return date.getDate().toString() // Just day number
    })

    const yLabels = perception_dates.map(d => {
      const date = new Date(d)
      return `${date.getMonth() + 1}/${date.getDate()}`
    })

    // Create Z data (transpose for Plotly surface)
    const z = surface_data

    // Actuals are shown as a single line at the end of the Y-axis (last perception date)
    // This represents the final actual values known after the target month passed
    const lastPerceptionIndex = perception_dates.length - 1
    const lastPerceptionLabel = yLabels[lastPerceptionIndex]

    return {
      z,
      x: xLabels,
      y: yLabels,
      actualValues: actuals,
      lastPerceptionLabel,
    }
  }, [progressData])

  const metricLabel = metrics.find(m => m.value === metric)?.label || metric

  return (
    <div style={progressStyles.container}>
      <div style={progressStyles.header}>
        <h2 style={progressStyles.title}>Forecast Progress</h2>
        <p style={progressStyles.subtitle}>
          See how forecasts evolved over time as the target month approached
        </p>
      </div>

      {/* Controls */}
      <div style={progressStyles.controls}>
        <div style={progressStyles.controlGroup}>
          <label style={progressStyles.label}>Year</label>
          <select
            value={year}
            onChange={(e) => setYear(parseInt(e.target.value))}
            style={progressStyles.select}
          >
            {yearOptions.map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div style={progressStyles.controlGroup}>
          <label style={progressStyles.label}>Month</label>
          <select
            value={month}
            onChange={(e) => setMonth(parseInt(e.target.value))}
            style={progressStyles.select}
          >
            {months.map((m, i) => (
              <option key={i} value={i}>{m}</option>
            ))}
          </select>
        </div>

        <div style={progressStyles.controlGroup}>
          <label style={progressStyles.label}>Metric</label>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            style={progressStyles.select}
          >
            {metrics.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>

        <div style={progressStyles.controlGroup}>
          <label style={progressStyles.label}>Model</label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={progressStyles.select}
          >
            {models.map(m => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* 3D Chart */}
      <div style={progressStyles.chartContainer}>
        {isLoading ? (
          <div style={progressStyles.loading}>Loading forecast data...</div>
        ) : error ? (
          <div style={progressStyles.error}>Error loading data. Make sure backtests have been run.</div>
        ) : !plotData ? (
          <div style={progressStyles.empty}>
            No forecast data available for {months[month]} {year}.
            <br />
            Run backtests for this period to generate data.
          </div>
        ) : (
          <Plot
            data={[
              // Forecast surface
              {
                type: 'surface' as const,
                z: plotData.z,
                x: plotData.x,
                y: plotData.y,
                colorscale: 'Viridis',
                opacity: 0.9,
                name: 'Forecast',
                showscale: true,
                colorbar: {
                  title: { text: metricLabel },
                  titleside: 'right',
                },
                hovertemplate:
                  'Day %{x}<br>' +
                  'Forecast from: %{y}<br>' +
                  `${metricLabel}: %{z:.1f}<extra></extra>`,
              } as Partial<Plotly.PlotData>,
              // Actuals line at the end of Y-axis (last perception date)
              // Shows as a red line representing the final actual values
              ...(plotData.actualValues.some(v => v !== null) ? [{
                type: 'scatter3d' as const,
                mode: 'lines+markers' as const,
                x: plotData.x,
                y: plotData.x.map(() => plotData.lastPerceptionLabel), // All points at last perception date
                z: plotData.actualValues,
                line: {
                  color: 'rgba(255, 99, 132, 1)',
                  width: 6,
                },
                marker: {
                  size: 4,
                  color: 'rgba(255, 99, 132, 1)',
                },
                name: 'Actual',
                hovertemplate:
                  'Day %{x}<br>' +
                  `Actual ${metricLabel}: %{z:.1f}<extra></extra>`,
              } as Partial<Plotly.PlotData>] : []),
            ]}
            layout={{
              title: {
                text: `${metricLabel} Forecast Evolution - ${months[month]} ${year}`,
                font: { size: 16 },
              },
              scene: {
                xaxis: {
                  title: { text: 'Day of Month' },
                  tickfont: { size: 10 },
                },
                yaxis: {
                  title: { text: 'Forecast Date' },
                  tickfont: { size: 10 },
                },
                zaxis: {
                  title: { text: metricLabel },
                  tickfont: { size: 10 },
                },
                camera: {
                  eye: { x: 1.5, y: 1.5, z: 1.2 },
                },
              },
              margin: { l: 0, r: 0, t: 40, b: 0 },
              paper_bgcolor: 'transparent',
              font: { family: 'Inter, system-ui, sans-serif' },
            }}
            style={{ width: '100%', height: '600px' }}
            config={{
              displayModeBar: true,
              displaylogo: false,
              modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
            }}
          />
        )}
      </div>

      {/* Explanation */}
      <div style={progressStyles.explanation}>
        <h4 style={progressStyles.explanationTitle}>How to Read This Chart</h4>
        <ul style={progressStyles.explanationList}>
          <li><strong>X-axis (Day of Month):</strong> Each day in {months[month]} {year}</li>
          <li><strong>Y-axis (Forecast Date):</strong> When each forecast was generated</li>
          <li><strong>Z-axis (Height/Color):</strong> The forecasted {metricLabel.toLowerCase()} value</li>
          <li><strong>Surface shape:</strong> As forecasts get closer to the target date (moving forward on Y), they typically converge toward the actual value</li>
          {plotData?.actualValues.some(v => v !== null) && (
            <li><strong>Red line at the end:</strong> Final actual values (shown at the last forecast date when actuals became known)</li>
          )}
        </ul>
      </div>
    </div>
  )
}

const progressStyles: Record<string, React.CSSProperties> = {
  container: {
    padding: spacing.md,
  },
  header: {
    marginBottom: spacing.lg,
  },
  title: {
    margin: 0,
    fontSize: typography.xl,
    fontWeight: typography.bold,
    color: colors.text,
  },
  subtitle: {
    margin: `${spacing.xs} 0 0 0`,
    fontSize: typography.sm,
    color: colors.textSecondary,
  },
  controls: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: spacing.md,
    marginBottom: spacing.lg,
    padding: spacing.md,
    background: colors.surface,
    borderRadius: radius.lg,
    border: `1px solid ${colors.borderLight}`,
  },
  controlGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
    minWidth: '140px',
  },
  label: {
    fontSize: typography.xs,
    fontWeight: typography.medium,
    color: colors.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  select: {
    padding: `${spacing.sm} ${spacing.md}`,
    fontSize: typography.sm,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    background: colors.background,
    color: colors.text,
    cursor: 'pointer',
    outline: 'none',
  },
  chartContainer: {
    background: colors.surface,
    borderRadius: radius.lg,
    border: `1px solid ${colors.borderLight}`,
    padding: spacing.md,
    minHeight: '600px',
  },
  loading: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '400px',
    color: colors.textSecondary,
    fontSize: typography.base,
  },
  error: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '400px',
    color: colors.error,
    fontSize: typography.base,
  },
  empty: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '400px',
    color: colors.textMuted,
    fontSize: typography.base,
    textAlign: 'center',
    lineHeight: 1.6,
  },
  explanation: {
    marginTop: spacing.lg,
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.lg,
    border: `1px solid ${colors.borderLight}`,
  },
  explanationTitle: {
    margin: `0 0 ${spacing.sm} 0`,
    fontSize: typography.sm,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  explanationList: {
    margin: 0,
    padding: `0 0 0 ${spacing.lg}`,
    fontSize: typography.sm,
    color: colors.textSecondary,
    lineHeight: 1.8,
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
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: spacing.lg,
  },
  sectionTitle: {
    color: colors.text,
    margin: 0,
    marginBottom: spacing.xs,
    fontSize: typography.xxl,
    fontWeight: typography.semibold,
  },
  subsectionTitle: {
    color: colors.text,
    margin: `0 0 ${spacing.md} 0`,
    fontSize: typography.lg,
    fontWeight: typography.medium,
  },
  hint: {
    color: colors.textSecondary,
    margin: 0,
    marginBottom: spacing.md,
    fontSize: typography.sm,
  },
  controlBox: {
    background: colors.background,
    padding: spacing.lg,
    borderRadius: radius.lg,
    marginTop: spacing.md,
  },
  controlGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
    gap: spacing.md,
    marginBottom: spacing.md,
  },
  formGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  label: {
    fontSize: typography.sm,
    color: colors.textSecondary,
    fontWeight: typography.medium,
  },
  input: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    outline: 'none',
  },
  select: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    background: colors.surface,
    cursor: 'pointer',
    outline: 'none',
  },
  buttonRow: {
    display: 'flex',
    gap: spacing.sm,
  },
  checkboxRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
    marginBottom: spacing.md,
    padding: spacing.sm,
    background: colors.surface,
    borderRadius: radius.md,
    border: `1px solid ${colors.borderLight}`,
  },
  checkboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    cursor: 'pointer',
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.text,
  },
  checkbox: {
    width: '18px',
    height: '18px',
    cursor: 'pointer',
  },
  checkboxHint: {
    fontSize: typography.xs,
    color: colors.textMuted,
    marginLeft: '26px',
  },
  runningMessage: {
    marginTop: spacing.md,
    padding: spacing.sm,
    background: colors.infoBg,
    color: colors.info,
    borderRadius: radius.md,
    fontSize: typography.sm,
  },
  statusGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
    gap: spacing.md,
  },
  statusCard: {
    background: colors.background,
    padding: spacing.md,
    borderRadius: radius.lg,
    border: `1px solid ${colors.borderLight}`,
  },
  statusCardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  statusCardModel: {
    fontSize: typography.lg,
    fontWeight: typography.bold,
    color: colors.text,
  },
  statusCardStats: {
    display: 'flex',
    gap: spacing.lg,
    marginBottom: spacing.sm,
  },
  statItem: {
    display: 'flex',
    flexDirection: 'column',
  },
  statLabel: {
    fontSize: typography.xs,
    color: colors.textMuted,
    textTransform: 'uppercase',
  },
  statValue: {
    fontSize: typography.lg,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  statusCardRange: {
    fontSize: typography.xs,
    color: colors.textMuted,
    borderTop: `1px solid ${colors.borderLight}`,
    paddingTop: spacing.sm,
  },
  deleteButton: {
    marginTop: spacing.sm,
    padding: `${spacing.xs} ${spacing.sm}`,
    fontSize: typography.xs,
    color: colors.error,
    background: 'transparent',
    border: `1px solid ${colors.error}`,
    borderRadius: radius.md,
    cursor: 'pointer',
    transition: 'all 0.2s',
  },
  metricGroupTitle: {
    fontSize: typography.base,
    fontWeight: 600,
    color: colors.textSecondary,
    marginBottom: spacing.sm,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.05em',
  },
  loading: {
    color: colors.textSecondary,
    padding: spacing.lg,
    textAlign: 'center',
  },
  emptyState: {
    padding: spacing.xl,
    textAlign: 'center',
    color: colors.textSecondary,
    background: colors.background,
    borderRadius: radius.lg,
  },
  filterRow: {
    display: 'flex',
    gap: spacing.sm,
  },
  tableContainer: {
    overflowX: 'auto',
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
    color: colors.text,
    fontWeight: typography.semibold,
    background: colors.background,
  },
  thSub: {
    padding: spacing.xs,
    textAlign: 'left',
    borderBottom: `1px solid ${colors.border}`,
    color: colors.textMuted,
    fontWeight: typography.normal,
    fontSize: typography.xs,
    background: colors.background,
  },
  td: {
    padding: spacing.sm,
    borderBottom: `1px solid ${colors.borderLight}`,
    color: colors.text,
  },
  sampleSize: {
    fontSize: typography.xs,
    color: colors.textMuted,
    marginLeft: spacing.xs,
  },
  barChartContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.md,
  },
  barRow: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  barLabel: {
    width: '80px',
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.text,
  },
  barGroup: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  barWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  barModelLabel: {
    width: '60px',
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  barTrack: {
    flex: 1,
    height: '12px',
    background: colors.borderLight,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  bar: {
    height: '100%',
    borderRadius: radius.sm,
    transition: 'width 0.3s ease',
  },
  barValue: {
    width: '50px',
    fontSize: typography.xs,
    color: colors.textSecondary,
    textAlign: 'right',
  },
  weightGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: spacing.md,
  },
  weightCard: {
    background: colors.background,
    borderRadius: radius.lg,
    padding: spacing.md,
    border: `1px solid ${colors.borderLight}`,
  },
  weightCardHeader: {
    fontSize: typography.sm,
    fontWeight: typography.semibold,
    color: colors.text,
    marginBottom: spacing.sm,
    paddingBottom: spacing.xs,
    borderBottom: `1px solid ${colors.borderLight}`,
  },
  weightCardBody: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  weightRow: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  weightModelName: {
    width: '60px',
    fontSize: typography.xs,
    color: colors.textSecondary,
    textTransform: 'capitalize',
  },
  weightBarTrack: {
    flex: 1,
    height: '8px',
    background: colors.borderLight,
    borderRadius: radius.sm,
    overflow: 'hidden',
  },
  weightBarFill: {
    height: '100%',
    borderRadius: radius.sm,
    transition: 'width 0.3s ease',
  },
  weightPct: {
    width: '36px',
    fontSize: typography.xs,
    fontWeight: typography.medium,
    color: colors.text,
    textAlign: 'right',
  },
  summaryBox: {
    marginTop: spacing.xl,
    padding: spacing.lg,
    background: colors.background,
    borderRadius: radius.lg,
  },
  summaryTitle: {
    margin: `0 0 ${spacing.md} 0`,
    fontSize: typography.base,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  summaryGrid: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: spacing.md,
  },
  summaryItem: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.xs,
    padding: `${spacing.xs} ${spacing.md}`,
    background: colors.surface,
    borderRadius: radius.md,
    border: `1px solid ${colors.borderLight}`,
  },
  summaryBracket: {
    fontSize: typography.sm,
    color: colors.textSecondary,
  },
  summaryModel: {
    fontSize: typography.sm,
    fontWeight: typography.bold,
  },
  summaryWeight: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  productionWeightsHeader: {
    marginBottom: spacing.md,
  },
  productionWeightsHint: {
    color: colors.textSecondary,
    margin: `${spacing.xs} 0 0 0`,
    fontSize: typography.sm,
    lineHeight: 1.5,
  },
  productionWeightsCard: {
    background: colors.background,
    borderRadius: radius.lg,
    padding: spacing.lg,
    border: `2px solid ${colors.accent}`,
    marginTop: spacing.md,
  },
  productionWeightsCardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.lg,
    paddingBottom: spacing.sm,
    borderBottom: `1px solid ${colors.borderLight}`,
  },
  productionWeightsMetric: {
    fontSize: typography.lg,
    fontWeight: typography.bold,
    color: colors.text,
  },
  productionWeightsSamples: {
    fontSize: typography.xs,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  productionWeightsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: spacing.md,
    marginBottom: spacing.md,
  },
  productionWeightItem: {
    background: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
    border: `1px solid ${colors.borderLight}`,
  },
  productionWeightModelHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  productionWeightModelName: {
    fontSize: typography.base,
    fontWeight: typography.bold,
  },
  productionWeightValue: {
    fontSize: typography.lg,
    fontWeight: typography.bold,
    color: colors.text,
  },
  productionWeightBarTrack: {
    height: '12px',
    background: colors.borderLight,
    borderRadius: radius.sm,
    overflow: 'hidden',
    marginBottom: spacing.sm,
  },
  productionWeightBarFill: {
    height: '100%',
    borderRadius: radius.sm,
    transition: 'width 0.3s ease',
  },
  productionWeightStats: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  productionWeightMape: {
    fontSize: typography.xs,
    color: colors.textSecondary,
  },
  productionWeightSamples: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  productionWeightsNote: {
    padding: spacing.sm,
    background: colors.infoBg,
    borderRadius: radius.md,
    fontSize: typography.xs,
    color: colors.text,
    lineHeight: 1.5,
    borderLeft: `3px solid ${colors.info}`,
  },
  leadTimeSection: {
    marginTop: spacing.xl,
    paddingTop: spacing.lg,
    borderTop: `2px solid ${colors.borderLight}`,
  },
}

export default Accuracy
