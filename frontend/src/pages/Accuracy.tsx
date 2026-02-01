import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
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

type AccuracyPage = 'backtest' | 'accuracy' | 'weights'

interface BacktestStatus {
  model: string
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

const Accuracy: React.FC = () => {
  const [activePage, setActivePage] = useState<AccuracyPage>('backtest')

  const menuItems: { id: AccuracyPage; label: string }[] = [
    { id: 'backtest', label: 'Batch Backtest' },
    { id: 'accuracy', label: 'Accuracy Metrics' },
    { id: 'weights', label: 'Model Weights' },
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

  const handleRunBacktest = () => {
    runBacktestMutation.mutate(selectedModel)
  }

  const models = ['xgboost', 'pickup', 'prophet']

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
              onChange={(e) => setMetric(e.target.value)}
              style={styles.select}
            >
              <option value="occupancy">Occupancy</option>
              <option value="rooms">Rooms</option>
            </select>
          </div>
          <div style={styles.formGroup}>
            <label style={styles.label}>Model</label>
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              style={styles.select}
            >
              {models.map(m => (
                <option key={m} value={m}>{m.charAt(0).toUpperCase() + m.slice(1)}</option>
              ))}
            </select>
          </div>
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
          <div style={styles.statusGrid}>
            {statusData.map((status) => (
              <div key={status.model} style={styles.statusCard}>
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
              </div>
            ))}
          </div>
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
// ACCURACY METRICS PAGE
// ============================================

const AccuracyMetricsPage: React.FC = () => {
  const [metric, setMetric] = useState('occupancy')
  const [selectedModel, setSelectedModel] = useState<string | null>(null)

  // Fetch accuracy by bracket
  const { data: accuracyData, isLoading } = useQuery<AccuracyBracket[]>({
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
  })

  // Group data by bracket for comparison view
  const bracketOrder = ['0-7', '8-14', '15-30', '31-60', '61-90', '90+']
  const models = [...new Set(accuracyData?.map(d => d.model) || [])]

  const groupedByBracket = bracketOrder.map(bracket => ({
    bracket,
    models: models.map(model => {
      const data = accuracyData?.find(d => d.lead_bracket === bracket && d.model === model)
      return { model, ...data }
    })
  }))

  const getColorForMape = (mape: number | null): string => {
    if (mape === null) return colors.textMuted
    if (mape < 5) return colors.success
    if (mape < 10) return '#22c55e'
    if (mape < 15) return colors.warning
    if (mape < 25) return '#f59e0b'
    return colors.error
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Accuracy by Lead Time</h2>
          <p style={styles.hint}>
            Compare model accuracy (MAPE) across different forecast horizons.
          </p>
        </div>
        <div style={styles.filterRow}>
          <select
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            style={styles.select}
          >
            <option value="occupancy">Occupancy</option>
            <option value="rooms">Rooms</option>
          </select>
          <select
            value={selectedModel || ''}
            onChange={(e) => setSelectedModel(e.target.value || null)}
            style={styles.select}
          >
            <option value="">All Models</option>
            <option value="xgboost">XGBoost</option>
            <option value="pickup">Pickup</option>
            <option value="prophet">Prophet</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div style={styles.loading}>Loading accuracy data...</div>
      ) : accuracyData && accuracyData.length > 0 ? (
        <>
          {/* Comparison Table */}
          <div style={styles.tableContainer}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Lead Time</th>
                  {models.map(model => (
                    <th key={model} style={styles.th} colSpan={2}>
                      {model.toUpperCase()}
                    </th>
                  ))}
                </tr>
                <tr>
                  <th style={styles.thSub}>Days Out</th>
                  {models.map(model => (
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

          {/* Visual Comparison */}
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
      ) : (
        <div style={styles.emptyState}>
          No accuracy data available. Run backtests and backfill actuals first.
        </div>
      )}
    </div>
  )
}

// ============================================
// MODEL WEIGHTS PAGE
// ============================================

const ModelWeightsPage: React.FC = () => {
  const [metric, setMetric] = useState('occupancy')

  // Fetch model weights
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
  const models = [...new Set(weightsData?.map(d => d.model) || [])]

  const groupedByBracket = bracketOrder.map(bracket => {
    const bracketData = weightsData?.filter(d => d.lead_bracket === bracket) || []
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

          {/* Visual Weight Distribution */}
          <div style={{ marginTop: spacing.xl }}>
            <h3 style={styles.subsectionTitle}>Weight Distribution by Lead Time</h3>
            <div style={styles.weightDistribution}>
              {groupedByBracket.map(({ bracket, data }) => (
                <div key={bracket} style={styles.weightBracket}>
                  <div style={styles.weightBracketLabel}>{bracket} days</div>
                  <div style={styles.weightBars}>
                    {data.sort((a, b) => b.weight - a.weight).map(({ model, weight }) => (
                      <div key={model} style={styles.weightBarWrapper}>
                        <div
                          style={{
                            ...styles.weightBar,
                            height: `${weight * 100}%`,
                            background: model === 'xgboost' ? colors.accent :
                                       model === 'pickup' ? colors.primary :
                                       colors.info,
                          }}
                        />
                        <div style={styles.weightBarLabel}>{model}</div>
                        <div style={styles.weightBarValue}>{(weight * 100).toFixed(0)}%</div>
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
  weightDistribution: {
    display: 'flex',
    gap: spacing.lg,
    justifyContent: 'space-between',
    flexWrap: 'wrap',
  },
  weightBracket: {
    flex: '1 1 120px',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    minWidth: '100px',
  },
  weightBracketLabel: {
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.text,
    marginBottom: spacing.sm,
  },
  weightBars: {
    display: 'flex',
    gap: spacing.xs,
    height: '100px',
    alignItems: 'flex-end',
  },
  weightBarWrapper: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    width: '40px',
  },
  weightBar: {
    width: '30px',
    borderRadius: `${radius.sm} ${radius.sm} 0 0`,
    transition: 'height 0.3s ease',
  },
  weightBarLabel: {
    fontSize: typography.xs,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },
  weightBarValue: {
    fontSize: typography.xs,
    fontWeight: typography.medium,
    color: colors.text,
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
}

export default Accuracy
