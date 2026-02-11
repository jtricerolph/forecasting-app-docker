import React, { useState, useMemo, useRef, useCallback, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '../App'
import api from '../utils/api'
import { colors, spacing, radius, typography, shadows, buttonStyle, badgeStyle, mergeStyles } from '../utils/theme'

// ============================================
// TYPES
// ============================================

type ReconPage = 'cash-up' | 'history' | 'multi-day' | 'petty-cash' | 'change-tin' | 'safe-cash' | 'recon-settings'

interface MenuGroup {
  group: string
  items: { id: ReconPage; label: string }[]
}

interface DenomEntry {
  count_type: 'float' | 'takings'
  denomination_type: 'note' | 'coin'
  denomination_value: number
  quantity: number | null
  value_entered: number | null
  total_amount: number
}

interface CardMachine {
  machine_name: string
  total_amount: number
  amex_amount: number
  visa_mc_amount: number
}

interface ReconRow {
  category: string
  banked_amount: number
  reported_amount: number
  variance: number
}

const GBP_NOTES = [50, 20, 10, 5]
const GBP_COINS = [2, 1, 0.50, 0.20, 0.10, 0.05, 0.02, 0.01]
const ALL_DENOMS = [...GBP_NOTES, ...GBP_COINS]

const formatCurrency = (v: number) => `£${v.toFixed(2)}`
const denomLabel = (v: number) => v >= 1 ? `£${v.toFixed(0)}` : `${(v * 100).toFixed(0)}p`

// ============================================
// MAIN COMPONENT
// ============================================

const Reconciliation: React.FC = () => {
  const { subPage } = useParams<{ subPage?: string }>()
  const navigate = useNavigate()
  const activePage = (subPage as ReconPage) || 'cash-up'

  const menuGroups: MenuGroup[] = [
    {
      group: 'Daily',
      items: [
        { id: 'cash-up', label: 'Cash Up' },
        { id: 'history', label: 'History' },
        { id: 'multi-day', label: 'Multi-Day Report' },
      ]
    },
    {
      group: 'Floats',
      items: [
        { id: 'petty-cash', label: 'Petty Cash' },
        { id: 'change-tin', label: 'Change Tin' },
        { id: 'safe-cash', label: 'Safe Cash' },
      ]
    },
    {
      group: 'Admin',
      items: [
        { id: 'recon-settings', label: 'Settings' },
      ]
    }
  ]

  const handlePageChange = (id: ReconPage) => {
    navigate(id === 'cash-up' ? '/reconciliation' : `/reconciliation/${id}`)
  }

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        <h3 style={styles.sidebarTitle}>Reconciliation</h3>
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
        {activePage === 'cash-up' && <CashUpPage canFinalize={true} />}
        {activePage === 'history' && <HistoryPage />}
        {activePage === 'multi-day' && <MultiDayReportPage />}
        {activePage === 'petty-cash' && <FloatCountPage countType="petty_cash" title="Petty Cash" showReceipts={true} />}
        {activePage === 'change-tin' && <FloatCountPage countType="change_tin" title="Change Tin" showReceipts={false} />}
        {activePage === 'safe-cash' && <FloatCountPage countType="safe_cash" title="Safe Cash" showReceipts={false} />}
        {activePage === 'recon-settings' && <ReconSettingsPage />}
      </main>
    </div>
  )
}

// ============================================
// CASH UP PAGE
// ============================================

export const CashUpPage: React.FC<{ canFinalize?: boolean }> = ({ canFinalize = true }) => {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0])
  const [cashUpId, setCashUpId] = useState<number | null>(null)
  const [cashUpStatus, setCashUpStatus] = useState<string>('')
  const [dateChecked, setDateChecked] = useState(false)
  const [isDirty, setIsDirty] = useState(false)
  const [notes, setNotes] = useState('')

  // Denomination state
  const [floatQuantities, setFloatQuantities] = useState<Record<number, number>>({})
  const [takingsQuantities, setTakingsQuantities] = useState<Record<number, number>>({})

  // Card machine state
  const [cardMachines, setCardMachines] = useState<CardMachine[]>([
    { machine_name: 'Front Desk', total_amount: 0, amex_amount: 0, visa_mc_amount: 0 },
    { machine_name: 'Restaurant/Bar', total_amount: 0, amex_amount: 0, visa_mc_amount: 0 },
  ])

  // Newbook data
  const [newbookTotals, setNewbookTotals] = useState<Record<string, number> | null>(null)
  const [newbookLoading, setNewbookLoading] = useState(false)

  // Reconciliation rows
  const [reconRows, setReconRows] = useState<ReconRow[]>([])

  // Calculate denomination totals
  const floatTotal = useMemo(() =>
    ALL_DENOMS.reduce((sum, d) => sum + (floatQuantities[d] || 0) * d, 0), [floatQuantities])
  const takingsTotal = useMemo(() =>
    ALL_DENOMS.reduce((sum, d) => sum + (takingsQuantities[d] || 0) * d, 0), [takingsQuantities])

  // Card totals
  const totalCardVisamc = useMemo(() =>
    cardMachines.reduce((sum, c) => sum + c.visa_mc_amount, 0), [cardMachines])
  const totalCardAmex = useMemo(() =>
    cardMachines.reduce((sum, c) => sum + c.amex_amount, 0), [cardMachines])

  const checkDate = async () => {
    if (isDirty && !confirm('You have unsaved changes. Continue?')) return
    setDateChecked(false)
    setCashUpId(null)
    setCashUpStatus('')
    try {
      const res = await api.get(`/reconciliation/cash-ups/by-date/${selectedDate}`)
      const data = res.data
      setCashUpId(data.cash_up.id)
      setCashUpStatus(data.cash_up.status)
      loadCashUpData(data)
      setDateChecked(true)
    } catch (e: any) {
      if (e.response?.status === 404) {
        setDateChecked(true)
        resetForm()
      }
    }
  }

  const loadCashUpData = (data: any) => {
    setNotes(data.cash_up.notes || '')
    // Load denominations
    const fq: Record<number, number> = {}
    const tq: Record<number, number> = {}
    for (const d of data.denominations || []) {
      if (d.count_type === 'float') fq[d.denomination_value] = d.quantity || 0
      else tq[d.denomination_value] = d.quantity || 0
    }
    setFloatQuantities(fq)
    setTakingsQuantities(tq)
    // Load card machines
    if (data.card_machines?.length) {
      setCardMachines(data.card_machines.map((c: any) => ({
        machine_name: c.machine_name,
        total_amount: c.total_amount,
        amex_amount: c.amex_amount,
        visa_mc_amount: c.visa_mc_amount,
      })))
    }
    // Load reconciliation
    if (data.reconciliation?.length) {
      setReconRows(data.reconciliation)
      // Extract Newbook totals from reported amounts
      const totals: Record<string, number> = {}
      for (const r of data.reconciliation) {
        const key = r.category === 'Cash' ? 'cash' :
          r.category === 'PDQ Visa/MC' ? 'manual_visa_mc' :
          r.category === 'PDQ Amex' ? 'manual_amex' :
          r.category === 'Gateway Visa/MC' ? 'gateway_visa_mc' :
          r.category === 'Gateway Amex' ? 'gateway_amex' : 'bacs'
        totals[key] = r.reported_amount
      }
      setNewbookTotals(totals)
    }
    setIsDirty(false)
  }

  const resetForm = () => {
    setFloatQuantities({})
    setTakingsQuantities({})
    setCardMachines([
      { machine_name: 'Front Desk', total_amount: 0, amex_amount: 0, visa_mc_amount: 0 },
      { machine_name: 'Restaurant/Bar', total_amount: 0, amex_amount: 0, visa_mc_amount: 0 },
    ])
    setNewbookTotals(null)
    setReconRows([])
    setNotes('')
    setIsDirty(false)
  }

  const createCashUp = async () => {
    try {
      const res = await api.post('/reconciliation/cash-ups', { session_date: selectedDate })
      setCashUpId(res.data.id)
      setCashUpStatus('draft')
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Failed to create cash-up')
    }
  }

  const fetchNewbookData = async () => {
    setNewbookLoading(true)
    try {
      const res = await api.get(`/reconciliation/newbook/payments/${selectedDate}`)
      setNewbookTotals(res.data.totals)
      updateReconRows(res.data.totals)
      setIsDirty(true)
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Failed to fetch Newbook data')
    }
    setNewbookLoading(false)
  }

  const updateReconRows = (reported: Record<string, number>) => {
    const banked = {
      cash: takingsTotal,
      manual_visa_mc: totalCardVisamc,
      manual_amex: totalCardAmex,
      gateway_visa_mc: 0,
      gateway_amex: 0,
      bacs: 0,
    }
    const categories = [
      { label: 'Cash', key: 'cash' },
      { label: 'PDQ Visa/MC', key: 'manual_visa_mc' },
      { label: 'PDQ Amex', key: 'manual_amex' },
      { label: 'Gateway Visa/MC', key: 'gateway_visa_mc' },
      { label: 'Gateway Amex', key: 'gateway_amex' },
      { label: 'BACS', key: 'bacs' },
    ]
    setReconRows(categories.map(c => ({
      category: c.label,
      banked_amount: parseFloat((banked[c.key as keyof typeof banked] || 0).toFixed(2)),
      reported_amount: parseFloat((reported[c.key] || 0).toFixed(2)),
      variance: parseFloat(((banked[c.key as keyof typeof banked] || 0) - (reported[c.key] || 0)).toFixed(2)),
    })))
  }

  // Recalculate recon when banked amounts change
  useEffect(() => {
    if (newbookTotals) {
      updateReconRows(newbookTotals)
    }
  }, [takingsTotal, totalCardVisamc, totalCardAmex])

  const buildDenominations = (): DenomEntry[] => {
    const denoms: DenomEntry[] = []
    for (const d of ALL_DENOMS) {
      if (floatQuantities[d]) {
        denoms.push({
          count_type: 'float', denomination_type: d >= 5 ? 'note' : 'coin',
          denomination_value: d, quantity: floatQuantities[d], value_entered: null,
          total_amount: parseFloat((floatQuantities[d] * d).toFixed(2)),
        })
      }
      if (takingsQuantities[d]) {
        denoms.push({
          count_type: 'takings', denomination_type: d >= 5 ? 'note' : 'coin',
          denomination_value: d, quantity: takingsQuantities[d], value_entered: null,
          total_amount: parseFloat((takingsQuantities[d] * d).toFixed(2)),
        })
      }
    }
    return denoms
  }

  const saveCashUp = async (finalize = false) => {
    if (!cashUpId) {
      await createCashUp()
      return
    }
    try {
      await api.put(`/reconciliation/cash-ups/${cashUpId}`, {
        denominations: buildDenominations(),
        card_machines: cardMachines,
        reconciliation: reconRows,
        notes,
        total_float_counted: parseFloat(floatTotal.toFixed(2)),
        total_cash_counted: parseFloat(takingsTotal.toFixed(2)),
      })
      if (finalize) {
        await api.post(`/reconciliation/cash-ups/${cashUpId}/finalize`)
        setCashUpStatus('final')
      }
      setIsDirty(false)
      queryClient.invalidateQueries({ queryKey: ['cash-ups'] })
    } catch (e: any) {
      alert(e.response?.data?.detail || 'Failed to save')
    }
  }

  const updateCardMachine = (idx: number, field: string, value: number) => {
    setCardMachines(prev => {
      const updated = [...prev]
      const machine = { ...updated[idx], [field]: value }
      if (field === 'total_amount' || field === 'amex_amount') {
        machine.visa_mc_amount = parseFloat((machine.total_amount - machine.amex_amount).toFixed(2))
      }
      updated[idx] = machine
      return updated
    })
    setIsDirty(true)
  }

  const isFinal = cashUpStatus === 'final'

  return (
    <div>
      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>Daily Cash Up</h2>

        {/* Date Selection */}
        <div style={{ display: 'flex', gap: spacing.md, alignItems: 'center', marginBottom: spacing.lg }}>
          <input type="date" value={selectedDate} onChange={e => setSelectedDate(e.target.value)}
            style={styles.input} />
          <button onClick={checkDate} style={mergeStyles(buttonStyle('primary'), { padding: `${spacing.sm} ${spacing.lg}` })}>
            Check Date
          </button>
          {dateChecked && !cashUpId && (
            <button onClick={createCashUp} style={mergeStyles(buttonStyle('accent'), { padding: `${spacing.sm} ${spacing.lg}` })}>
              Create New
            </button>
          )}
          {cashUpStatus && (
            <span style={cashUpStatus === 'final' ? badgeStyle('success') : badgeStyle('warning')}>
              {cashUpStatus.toUpperCase()}
            </span>
          )}
          {isDirty && <span style={badgeStyle('error')}>UNSAVED CHANGES</span>}
        </div>

        {(cashUpId || (dateChecked && !cashUpId)) && (
          <>
            {/* Denomination Tables */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.lg, marginBottom: spacing.lg }}>
              <DenomTable title="Till Float" quantities={floatQuantities}
                onChange={(d, v) => { setFloatQuantities(p => ({ ...p, [d]: v })); setIsDirty(true) }}
                total={floatTotal} disabled={isFinal} />
              <DenomTable title="Cash Takings" quantities={takingsQuantities}
                onChange={(d, v) => { setTakingsQuantities(p => ({ ...p, [d]: v })); setIsDirty(true) }}
                total={takingsTotal} disabled={isFinal} />
            </div>

            {/* Card Machines */}
            <h3 style={{ ...styles.sectionSubtitle, marginTop: spacing.lg }}>Card Machines</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.lg, marginBottom: spacing.lg }}>
              {cardMachines.map((machine, idx) => (
                <div key={machine.machine_name} style={styles.card}>
                  <h4 style={{ margin: `0 0 ${spacing.sm} 0`, color: colors.text }}>{machine.machine_name}</h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: spacing.sm, alignItems: 'center' }}>
                    <label style={styles.label}>Total:</label>
                    <input type="number" step="0.01" value={machine.total_amount || ''} disabled={isFinal}
                      onChange={e => updateCardMachine(idx, 'total_amount', parseFloat(e.target.value) || 0)}
                      onFocus={e => e.target.select()} style={styles.numberInput} />
                    <label style={styles.label}>Amex:</label>
                    <input type="number" step="0.01" value={machine.amex_amount || ''} disabled={isFinal}
                      onChange={e => updateCardMachine(idx, 'amex_amount', parseFloat(e.target.value) || 0)}
                      onFocus={e => e.target.select()} style={styles.numberInput} />
                    <label style={styles.label}>Visa/MC:</label>
                    <div style={{ ...styles.numberInput, background: colors.background, color: colors.textMuted }}>
                      {formatCurrency(machine.visa_mc_amount)}
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Newbook Fetch */}
            <div style={{ display: 'flex', gap: spacing.md, alignItems: 'center', marginBottom: spacing.lg }}>
              <button onClick={fetchNewbookData} disabled={newbookLoading || isFinal}
                style={mergeStyles(buttonStyle('primary'), { padding: `${spacing.sm} ${spacing.lg}` })}>
                {newbookLoading ? 'Fetching...' : 'Fetch Newbook Data'}
              </button>
              {newbookTotals && <span style={{ color: colors.success, fontSize: typography.sm }}>Newbook data loaded</span>}
            </div>

            {/* Reconciliation Table */}
            {reconRows.length > 0 && (
              <>
                <h3 style={styles.sectionSubtitle}>Reconciliation</h3>
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>Category</th>
                      <th style={{ ...styles.th, background: '#e8f5e9' }}>Banked</th>
                      <th style={{ ...styles.th, background: '#fff3e0' }}>Reported</th>
                      <th style={styles.th}>Variance</th>
                    </tr>
                  </thead>
                  <tbody>
                    {reconRows.map(row => (
                      <tr key={row.category}>
                        <td style={styles.td}>{row.category}</td>
                        <td style={{ ...styles.tdRight, background: '#f1f8e9' }}>{formatCurrency(row.banked_amount)}</td>
                        <td style={{ ...styles.tdRight, background: '#fff8e1' }}>{formatCurrency(row.reported_amount)}</td>
                        <td style={{
                          ...styles.tdRight,
                          color: row.variance === 0 ? colors.textMuted : row.variance > 0 ? colors.success : colors.error,
                          fontWeight: typography.semibold as any,
                        }}>
                          {row.variance > 0 ? '+' : ''}{formatCurrency(row.variance)}
                        </td>
                      </tr>
                    ))}
                    <tr style={{ fontWeight: typography.bold as any }}>
                      <td style={styles.td}>Total</td>
                      <td style={{ ...styles.tdRight, background: '#f1f8e9' }}>
                        {formatCurrency(reconRows.reduce((s, r) => s + r.banked_amount, 0))}
                      </td>
                      <td style={{ ...styles.tdRight, background: '#fff8e1' }}>
                        {formatCurrency(reconRows.reduce((s, r) => s + r.reported_amount, 0))}
                      </td>
                      <td style={styles.tdRight}>
                        {formatCurrency(reconRows.reduce((s, r) => s + r.variance, 0))}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </>
            )}

            {/* Notes */}
            <div style={{ marginTop: spacing.lg }}>
              <label style={styles.label}>Notes</label>
              <textarea value={notes} onChange={e => { setNotes(e.target.value); setIsDirty(true) }}
                disabled={isFinal} rows={3} style={{ ...styles.input, width: '100%', resize: 'vertical' }} />
            </div>

            {/* Action Buttons */}
            {!isFinal && (
              <div style={{ display: 'flex', gap: spacing.md, marginTop: spacing.lg }}>
                <button onClick={() => saveCashUp(false)}
                  style={mergeStyles(buttonStyle('primary'), { padding: `${spacing.sm} ${spacing.xl}` })}>
                  Save Draft
                </button>
                {canFinalize && cashUpId && (
                  <button onClick={() => { if (confirm('Finalize this cash-up? It cannot be edited after.')) saveCashUp(true) }}
                    style={mergeStyles(buttonStyle('accent'), { padding: `${spacing.sm} ${spacing.xl}` })}>
                    Finalize
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ============================================
// DENOMINATION TABLE COMPONENT
// ============================================

const DenomTable: React.FC<{
  title: string
  quantities: Record<number, number>
  onChange: (denom: number, qty: number) => void
  total: number
  disabled: boolean
}> = ({ title, quantities, onChange, total, disabled }) => (
  <div style={styles.card}>
    <h4 style={{ margin: `0 0 ${spacing.sm} 0`, color: colors.text }}>{title}</h4>
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th style={styles.thSmall}>Denom</th>
          <th style={styles.thSmall}>Qty</th>
          <th style={{ ...styles.thSmall, textAlign: 'right' }}>Total</th>
        </tr>
      </thead>
      <tbody>
        {ALL_DENOMS.map(d => {
          const qty = quantities[d] || 0
          const rowTotal = qty * d
          return (
            <tr key={d} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
              <td style={{ padding: `${spacing.xs} ${spacing.sm}`, fontSize: typography.sm }}>{denomLabel(d)}</td>
              <td style={{ padding: spacing.xs }}>
                <input type="number" min="0" value={qty || ''} disabled={disabled}
                  onChange={e => onChange(d, parseInt(e.target.value) || 0)}
                  onFocus={e => e.target.select()}
                  style={{ ...styles.numberInputSmall, width: '70px' }} />
              </td>
              <td style={{ padding: `${spacing.xs} ${spacing.sm}`, textAlign: 'right', fontSize: typography.sm, color: colors.textSecondary }}>
                {rowTotal > 0 ? formatCurrency(rowTotal) : ''}
              </td>
            </tr>
          )
        })}
      </tbody>
      <tfoot>
        <tr style={{ borderTop: `2px solid ${colors.border}` }}>
          <td colSpan={2} style={{ padding: spacing.sm, fontWeight: typography.bold as any }}>Total</td>
          <td style={{ padding: spacing.sm, textAlign: 'right', fontWeight: typography.bold as any, fontSize: typography.md }}>
            {formatCurrency(total)}
          </td>
        </tr>
      </tfoot>
    </table>
  </div>
)

// ============================================
// HISTORY PAGE
// ============================================

const HistoryPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [page, setPage] = useState(1)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const navigate = useNavigate()

  const { data, isLoading } = useQuery({
    queryKey: ['cash-ups', statusFilter, dateFrom, dateTo, page],
    queryFn: () => api.get('/reconciliation/cash-ups', {
      params: { status: statusFilter || undefined, date_from: dateFrom || undefined, date_to: dateTo || undefined, page, per_page: 20 }
    }).then(r => r.data),
  })

  const bulkFinalize = useMutation({
    mutationFn: (ids: number[]) => api.post('/reconciliation/cash-ups/bulk-finalize', { ids }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cash-ups'] })
      setSelectedIds(new Set())
    },
  })

  const deleteCashUp = useMutation({
    mutationFn: (id: number) => api.delete(`/reconciliation/cash-ups/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['cash-ups'] }),
  })

  const toggleSelect = (id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>Cash Up History</h2>
      <div style={{ display: 'flex', gap: spacing.md, marginBottom: spacing.lg, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1) }} style={styles.input}>
          <option value="">All Status</option>
          <option value="draft">Draft</option>
          <option value="final">Final</option>
        </select>
        <input type="date" value={dateFrom} onChange={e => { setDateFrom(e.target.value); setPage(1) }} style={styles.input} />
        <span style={{ color: colors.textMuted }}>to</span>
        <input type="date" value={dateTo} onChange={e => { setDateTo(e.target.value); setPage(1) }} style={styles.input} />
        {selectedIds.size > 0 && (
          <button onClick={() => bulkFinalize.mutate(Array.from(selectedIds))}
            style={mergeStyles(buttonStyle('accent'), { padding: `${spacing.sm} ${spacing.lg}` })}>
            Finalize Selected ({selectedIds.size})
          </button>
        )}
      </div>

      {isLoading ? (
        <p style={{ color: colors.textMuted }}>Loading...</p>
      ) : (
        <>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}></th>
                <th style={styles.th}>Date</th>
                <th style={styles.th}>Status</th>
                <th style={styles.th}>Cash Total</th>
                <th style={styles.th}>Float Total</th>
                <th style={styles.th}>Created By</th>
                <th style={styles.th}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {data?.cash_ups?.map((cu: any) => (
                <tr key={cu.id}>
                  <td style={styles.td}>
                    {cu.status === 'draft' && (
                      <input type="checkbox" checked={selectedIds.has(cu.id)} onChange={() => toggleSelect(cu.id)} />
                    )}
                  </td>
                  <td style={styles.td}>{cu.session_date}</td>
                  <td style={styles.td}>
                    <span style={cu.status === 'final' ? badgeStyle('success') : badgeStyle('warning')}>
                      {cu.status}
                    </span>
                  </td>
                  <td style={styles.tdRight}>{formatCurrency(cu.total_cash_counted)}</td>
                  <td style={styles.tdRight}>{formatCurrency(cu.total_float_counted)}</td>
                  <td style={styles.td}>{cu.created_by_name}</td>
                  <td style={styles.td}>
                    <div style={{ display: 'flex', gap: spacing.xs }}>
                      <button onClick={() => navigate('/reconciliation')}
                        style={{ ...styles.linkBtn, color: colors.accent }}>
                        {cu.status === 'draft' ? 'Edit' : 'View'}
                      </button>
                      {cu.status === 'draft' && (
                        <button onClick={() => { if (confirm('Delete this draft?')) deleteCashUp.mutate(cu.id) }}
                          style={{ ...styles.linkBtn, color: colors.error }}>
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Pagination */}
          {data && data.total_pages > 1 && (
            <div style={{ display: 'flex', gap: spacing.sm, justifyContent: 'center', marginTop: spacing.lg }}>
              {Array.from({ length: data.total_pages }, (_, i) => i + 1).map(p => (
                <button key={p} onClick={() => setPage(p)}
                  style={p === page ? mergeStyles(buttonStyle('primary'), { padding: `${spacing.xs} ${spacing.sm}` })
                    : mergeStyles(buttonStyle('outline'), { padding: `${spacing.xs} ${spacing.sm}` })}>
                  {p}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// MULTI-DAY REPORT PAGE
// ============================================

const MultiDayReportPage: React.FC = () => {
  const [startDate, setStartDate] = useState(new Date(Date.now() - 7 * 86400000).toISOString().split('T')[0])
  const [numDays, setNumDays] = useState(7)
  const [selectedCells, setSelectedCells] = useState<Set<string>>(new Set())
  const [isSelecting, setIsSelecting] = useState(false)
  const [selectionStart, setSelectionStart] = useState<{ row: number; col: number } | null>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['multi-day-report', startDate, numDays],
    queryFn: () => api.get('/reconciliation/reports/multi-day', {
      params: { start_date: startDate, num_days: numDays }
    }).then(r => r.data),
    enabled: false,
  })

  // Cell selection for Excel copy-paste
  const getCellId = (table: string, row: number, col: number) => `${table}-${row}-${col}`

  const handleCellMouseDown = (table: string, row: number, col: number, e: React.MouseEvent) => {
    if (e.shiftKey && selectionStart) {
      // Range selection
      const newSelection = new Set<string>()
      const minR = Math.min(selectionStart.row, row)
      const maxR = Math.max(selectionStart.row, row)
      const minC = Math.min(selectionStart.col, col)
      const maxC = Math.max(selectionStart.col, col)
      for (let r = minR; r <= maxR; r++) {
        for (let c = minC; c <= maxC; c++) {
          newSelection.add(getCellId(table, r, c))
        }
      }
      setSelectedCells(newSelection)
    } else {
      setSelectedCells(new Set([getCellId(table, row, col)]))
      setSelectionStart({ row, col })
      setIsSelecting(true)
    }
  }

  const handleCellMouseEnter = (table: string, row: number, col: number) => {
    if (!isSelecting || !selectionStart) return
    const newSelection = new Set<string>()
    const minR = Math.min(selectionStart.row, row)
    const maxR = Math.max(selectionStart.row, row)
    const minC = Math.min(selectionStart.col, col)
    const maxC = Math.max(selectionStart.col, col)
    for (let r = minR; r <= maxR; r++) {
      for (let c = minC; c <= maxC; c++) {
        newSelection.add(getCellId(table, r, c))
      }
    }
    setSelectedCells(newSelection)
  }

  useEffect(() => {
    const handleMouseUp = () => setIsSelecting(false)
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'c' && selectedCells.size > 0) {
        e.preventDefault()
        copySelectedToClipboard()
      }
    }
    document.addEventListener('mouseup', handleMouseUp)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mouseup', handleMouseUp)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [selectedCells])

  const copySelectedToClipboard = () => {
    if (selectedCells.size === 0) return
    // Parse cell IDs to get rows and cols
    const cells: { row: number; col: number; el: HTMLElement | null }[] = []
    selectedCells.forEach(id => {
      const el = document.querySelector(`[data-cell-id="${id}"]`) as HTMLElement
      const parts = id.split('-')
      cells.push({ row: parseInt(parts[1]), col: parseInt(parts[2]), el })
    })

    // Group by row
    const rowMap = new Map<number, Map<number, string>>()
    cells.forEach(c => {
      if (!rowMap.has(c.row)) rowMap.set(c.row, new Map())
      const text = c.el?.textContent?.trim() || ''
      // Smart number extraction: strip £, ▼, ▲, commas
      const numMatch = text.replace(/[£,▼▲+]/g, '').match(/[-]?[\d]+\.?\d*/)
      rowMap.get(c.row)!.set(c.col, numMatch ? numMatch[0] : text)
    })

    // Build tab-separated text
    const sortedRows = Array.from(rowMap.keys()).sort((a, b) => a - b)
    const lines = sortedRows.map(r => {
      const cols = rowMap.get(r)!
      const sortedCols = Array.from(cols.keys()).sort((a, b) => a - b)
      return sortedCols.map(c => cols.get(c) || '').join('\t')
    })

    navigator.clipboard.writeText(lines.join('\n'))
  }

  // Selection tooltip calculations
  const selectionStats = useMemo(() => {
    if (selectedCells.size < 2) return null
    const values: number[] = []
    selectedCells.forEach(id => {
      const el = document.querySelector(`[data-cell-id="${id}"]`) as HTMLElement
      if (el) {
        const text = el.textContent?.replace(/[£,▼▲+]/g, '') || ''
        const num = parseFloat(text)
        if (!isNaN(num)) values.push(num)
      }
    })
    if (values.length < 2) return null
    const sum = values.reduce((a, b) => a + b, 0)
    return { count: values.length, sum: sum.toFixed(2), avg: (sum / values.length).toFixed(2) }
  }, [selectedCells])

  const cellStyle = (table: string, row: number, col: number): React.CSSProperties => ({
    ...styles.tdRight,
    userSelect: 'text',
    cursor: 'cell',
    ...(selectedCells.has(getCellId(table, row, col)) ? {
      backgroundColor: '#cce4ff',
      outline: '2px solid #0078d4',
    } : {}),
  })

  const RECON_KEYS = ['cash', 'manual_visa_mc', 'manual_amex', 'gateway_visa_mc', 'gateway_amex', 'bacs']
  const RECON_LABELS = ['Cash', 'PDQ V/MC', 'PDQ Amex', 'Gw V/MC', 'Gw Amex', 'BACS']

  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>Multi-Day Report</h2>
      <div style={{ display: 'flex', gap: spacing.md, marginBottom: spacing.lg, alignItems: 'center' }}>
        <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} style={styles.input} />
        <label style={styles.label}>Days:</label>
        <input type="number" min={1} max={365} value={numDays} onChange={e => setNumDays(parseInt(e.target.value) || 7)}
          style={{ ...styles.numberInput, width: '80px' }} />
        <button onClick={() => refetch()} disabled={isLoading}
          style={mergeStyles(buttonStyle('primary'), { padding: `${spacing.sm} ${spacing.lg}` })}>
          {isLoading ? 'Generating...' : 'Generate Report'}
        </button>
      </div>

      {selectionStats && (
        <div style={styles.selectionTooltip}>
          Count: {selectionStats.count} | Sum: {selectionStats.sum} | Avg: {selectionStats.avg}
        </div>
      )}

      {data?.reconciliation_summary && (
        <>
          <h3 style={styles.sectionSubtitle}>Daily Reconciliation Summary</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: spacing.md, marginBottom: spacing.xl }}>
            {/* BANKED Table */}
            <div>
              <div style={{ background: '#e8f5e9', padding: spacing.sm, textAlign: 'center', fontWeight: typography.bold as any, borderRadius: `${radius.md} ${radius.md} 0 0` }}>
                BANKED
              </div>
              <table style={{ ...styles.table, borderRadius: 0 }}>
                <thead>
                  <tr>
                    <th style={styles.thSmall}>Date</th>
                    {RECON_LABELS.map(l => <th key={l} style={styles.thSmall}>{l}</th>)}
                    <th style={styles.thSmall}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.reconciliation_summary.rows.map((row: any, ri: number) => (
                    <tr key={row.date}>
                      <td style={styles.td}>{row.date}</td>
                      {RECON_KEYS.map((k, ci) => (
                        <td key={k} data-cell-id={getCellId('banked', ri, ci)}
                          style={cellStyle('banked', ri, ci)}
                          onMouseDown={e => handleCellMouseDown('banked', ri, ci, e)}
                          onMouseEnter={() => handleCellMouseEnter('banked', ri, ci)}>
                          {(row.banked[k] || 0).toFixed(2)}
                        </td>
                      ))}
                      <td data-cell-id={getCellId('banked', ri, 6)}
                        style={{ ...cellStyle('banked', ri, 6), fontWeight: typography.semibold as any }}
                        onMouseDown={e => handleCellMouseDown('banked', ri, 6, e)}
                        onMouseEnter={() => handleCellMouseEnter('banked', ri, 6)}>
                        {row.banked_total.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ fontWeight: typography.bold as any }}>
                    <td style={styles.td}>Total</td>
                    {RECON_KEYS.map(k => (
                      <td key={k} style={styles.tdRight}>{(data.reconciliation_summary.totals.banked[k] || 0).toFixed(2)}</td>
                    ))}
                    <td style={styles.tdRight}>{data.reconciliation_summary.totals.banked_total.toFixed(2)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>

            {/* REPORTED Table */}
            <div>
              <div style={{ background: '#fff3e0', padding: spacing.sm, textAlign: 'center', fontWeight: typography.bold as any, borderRadius: `${radius.md} ${radius.md} 0 0` }}>
                REPORTED
              </div>
              <table style={{ ...styles.table, borderRadius: 0 }}>
                <thead>
                  <tr>
                    <th style={styles.thSmall}>Date</th>
                    {RECON_LABELS.map(l => <th key={l} style={styles.thSmall}>{l}</th>)}
                    <th style={styles.thSmall}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.reconciliation_summary.rows.map((row: any, ri: number) => (
                    <tr key={row.date}>
                      <td style={styles.td}>{row.date}</td>
                      {RECON_KEYS.map((k, ci) => (
                        <td key={k} data-cell-id={getCellId('reported', ri, ci)}
                          style={cellStyle('reported', ri, ci)}
                          onMouseDown={e => handleCellMouseDown('reported', ri, ci, e)}
                          onMouseEnter={() => handleCellMouseEnter('reported', ri, ci)}>
                          {(row.reported[k] || 0).toFixed(2)}
                        </td>
                      ))}
                      <td data-cell-id={getCellId('reported', ri, 6)}
                        style={{ ...cellStyle('reported', ri, 6), fontWeight: typography.semibold as any }}
                        onMouseDown={e => handleCellMouseDown('reported', ri, 6, e)}
                        onMouseEnter={() => handleCellMouseEnter('reported', ri, 6)}>
                        {row.reported_total.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr style={{ fontWeight: typography.bold as any }}>
                    <td style={styles.td}>Total</td>
                    {RECON_KEYS.map(k => (
                      <td key={k} style={styles.tdRight}>{(data.reconciliation_summary.totals.reported[k] || 0).toFixed(2)}</td>
                    ))}
                    <td style={styles.tdRight}>{data.reconciliation_summary.totals.reported_total.toFixed(2)}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>

          {/* Variance Row */}
          <h4 style={{ margin: `0 0 ${spacing.sm}`, color: colors.text }}>Variance (Banked - Reported)</h4>
          <table style={{ ...styles.table, marginBottom: spacing.xl }}>
            <thead>
              <tr>
                {RECON_LABELS.map(l => <th key={l} style={styles.thSmall}>{l}</th>)}
                <th style={styles.thSmall}>Total</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                {RECON_KEYS.map(k => {
                  const v = data.reconciliation_summary.totals.variance[k] || 0
                  return (
                    <td key={k} style={{
                      ...styles.tdRight,
                      color: v === 0 ? colors.textMuted : v > 0 ? colors.success : colors.error,
                      fontWeight: typography.semibold as any,
                    }}>
                      {v > 0 ? '+' : ''}{v.toFixed(2)}
                    </td>
                  )
                })}
                <td style={{
                  ...styles.tdRight,
                  fontWeight: typography.bold as any,
                }}>
                  {(data.reconciliation_summary.totals.banked_total - data.reconciliation_summary.totals.reported_total).toFixed(2)}
                </td>
              </tr>
            </tbody>
          </table>
        </>
      )}

      {data?.occupancy?.rows?.length > 0 && (
        <>
          <h3 style={styles.sectionSubtitle}>Occupancy Statistics</h3>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.thSmall}>Date</th>
                <th style={styles.thSmall}>Rooms</th>
                <th style={styles.thSmall}>People</th>
                <th style={styles.thSmall}>Gross Sales</th>
              </tr>
            </thead>
            <tbody>
              {data.occupancy.rows.map((row: any, ri: number) => (
                <tr key={row.date}>
                  <td style={styles.td}>{row.date}</td>
                  <td data-cell-id={getCellId('occ', ri, 0)} style={cellStyle('occ', ri, 0)}
                    onMouseDown={e => handleCellMouseDown('occ', ri, 0, e)}
                    onMouseEnter={() => handleCellMouseEnter('occ', ri, 0)}>
                    {row.rooms_sold}
                  </td>
                  <td data-cell-id={getCellId('occ', ri, 1)} style={cellStyle('occ', ri, 1)}
                    onMouseDown={e => handleCellMouseDown('occ', ri, 1, e)}
                    onMouseEnter={() => handleCellMouseEnter('occ', ri, 1)}>
                    {row.total_people}
                  </td>
                  <td data-cell-id={getCellId('occ', ri, 2)} style={cellStyle('occ', ri, 2)}
                    onMouseDown={e => handleCellMouseDown('occ', ri, 2, e)}
                    onMouseEnter={() => handleCellMouseEnter('occ', ri, 2)}>
                    {row.gross_sales.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  )
}

// ============================================
// FLOAT COUNT PAGE (Petty Cash / Change Tin / Safe Cash)
// ============================================

export const FloatCountPage: React.FC<{
  countType: string
  title: string
  showReceipts: boolean
}> = ({ countType, title, showReceipts }) => {
  const queryClient = useQueryClient()
  const [quantities, setQuantities] = useState<Record<number, number>>({})
  const [receipts, setReceipts] = useState<{ value: number; description: string }[]>([])
  const [notes, setNotes] = useState('')

  const FLOAT_DENOMS = countType === 'change_tin'
    ? [2, 1, 0.50, 0.20, 0.10, 0.05]  // Change tin: no notes, no tiny coins
    : ALL_DENOMS.filter(d => d >= 0.05) // Petty cash / safe: 5p and above

  const { data: settings } = useQuery({
    queryKey: ['recon-settings'],
    queryFn: () => api.get('/reconciliation/settings').then(r => r.data),
  })

  const { data: history } = useQuery({
    queryKey: ['float-counts', countType],
    queryFn: () => api.get('/reconciliation/float-counts', { params: { count_type: countType, per_page: 10 } }).then(r => r.data),
  })

  const cashTotal = useMemo(() =>
    FLOAT_DENOMS.reduce((sum, d) => sum + (quantities[d] || 0) * d, 0), [quantities])
  const receiptsTotal = useMemo(() =>
    receipts.reduce((sum, r) => sum + (r.value || 0), 0), [receipts])
  const grandTotal = cashTotal + receiptsTotal

  const targetKey = countType === 'petty_cash' ? 'petty_cash_target'
    : countType === 'safe_cash' ? 'safe_cash_target' : 'petty_cash_target'
  const target = parseFloat(settings?.[targetKey] || '0')
  const variance = grandTotal - target

  const saveMutation = useMutation({
    mutationFn: () => api.post('/reconciliation/float-counts', {
      count_type: countType,
      denominations: FLOAT_DENOMS.filter(d => quantities[d]).map(d => ({
        denomination_value: d, quantity: quantities[d] || 0,
        total_amount: parseFloat(((quantities[d] || 0) * d).toFixed(2)),
      })),
      receipts: receipts.map(r => ({ receipt_value: r.value, receipt_description: r.description })),
      total_counted: parseFloat(cashTotal.toFixed(2)),
      total_receipts: parseFloat(receiptsTotal.toFixed(2)),
      target_amount: target,
      variance: parseFloat(variance.toFixed(2)),
      notes,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['float-counts', countType] })
      setQuantities({})
      setReceipts([])
      setNotes('')
    },
  })

  return (
    <div>
      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>{title}</h2>
        <div style={{ display: 'grid', gridTemplateColumns: showReceipts ? '1fr 1fr' : '1fr', gap: spacing.lg }}>
          {/* Denomination Count */}
          <div style={styles.card}>
            <h4 style={{ margin: `0 0 ${spacing.sm}`, color: colors.text }}>Denomination Count</h4>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={styles.thSmall}>Denom</th>
                  <th style={styles.thSmall}>Qty</th>
                  <th style={{ ...styles.thSmall, textAlign: 'right' }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {FLOAT_DENOMS.map(d => (
                  <tr key={d} style={{ borderBottom: `1px solid ${colors.borderLight}` }}>
                    <td style={{ padding: spacing.xs, fontSize: typography.sm }}>{denomLabel(d)}</td>
                    <td style={{ padding: spacing.xs }}>
                      <input type="number" min="0" value={quantities[d] || ''}
                        onChange={e => setQuantities(p => ({ ...p, [d]: parseInt(e.target.value) || 0 }))}
                        onFocus={e => e.target.select()} style={{ ...styles.numberInputSmall, width: '70px' }} />
                    </td>
                    <td style={{ padding: spacing.xs, textAlign: 'right', fontSize: typography.sm }}>
                      {(quantities[d] || 0) * d > 0 ? formatCurrency((quantities[d] || 0) * d) : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr style={{ borderTop: `2px solid ${colors.border}` }}>
                  <td colSpan={2} style={{ padding: spacing.sm, fontWeight: typography.bold as any }}>Cash Total</td>
                  <td style={{ padding: spacing.sm, textAlign: 'right', fontWeight: typography.bold as any }}>{formatCurrency(cashTotal)}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          {/* Receipts */}
          {showReceipts && (
            <div style={styles.card}>
              <h4 style={{ margin: `0 0 ${spacing.sm}`, color: colors.text }}>Receipts</h4>
              {receipts.map((r, i) => (
                <div key={i} style={{ display: 'flex', gap: spacing.sm, marginBottom: spacing.sm, alignItems: 'center' }}>
                  <input type="number" step="0.01" placeholder="£" value={r.value || ''}
                    onChange={e => {
                      const updated = [...receipts]
                      updated[i] = { ...updated[i], value: parseFloat(e.target.value) || 0 }
                      setReceipts(updated)
                    }}
                    style={{ ...styles.numberInput, width: '100px' }} />
                  <input type="text" placeholder="Description" value={r.description}
                    onChange={e => {
                      const updated = [...receipts]
                      updated[i] = { ...updated[i], description: e.target.value }
                      setReceipts(updated)
                    }}
                    style={{ ...styles.input, flex: 1 }} />
                  <button onClick={() => setReceipts(prev => prev.filter((_, j) => j !== i))}
                    style={{ ...styles.linkBtn, color: colors.error }}>Remove</button>
                </div>
              ))}
              <button onClick={() => setReceipts(prev => [...prev, { value: 0, description: '' }])}
                style={mergeStyles(buttonStyle('outline'), { padding: `${spacing.xs} ${spacing.md}` })}>
                + Add Receipt
              </button>
              <div style={{ marginTop: spacing.md, fontWeight: typography.semibold as any }}>
                Receipts Total: {formatCurrency(receiptsTotal)}
              </div>
            </div>
          )}
        </div>

        {/* Summary */}
        <div style={{ ...styles.card, marginTop: spacing.lg }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: spacing.lg, textAlign: 'center' }}>
            <div>
              <div style={{ fontSize: typography.sm, color: colors.textMuted }}>Grand Total</div>
              <div style={{ fontSize: typography.xxl, fontWeight: typography.bold as any }}>{formatCurrency(grandTotal)}</div>
            </div>
            <div>
              <div style={{ fontSize: typography.sm, color: colors.textMuted }}>Target</div>
              <div style={{ fontSize: typography.xxl, fontWeight: typography.bold as any }}>{formatCurrency(target)}</div>
            </div>
            <div>
              <div style={{ fontSize: typography.sm, color: colors.textMuted }}>Variance</div>
              <div style={{
                fontSize: typography.xxl, fontWeight: typography.bold as any,
                color: variance === 0 ? colors.textMuted : variance > 0 ? colors.success : colors.error,
              }}>
                {variance > 0 ? '+' : ''}{formatCurrency(variance)}
              </div>
            </div>
          </div>
        </div>

        <div style={{ marginTop: spacing.lg }}>
          <label style={styles.label}>Notes</label>
          <textarea value={notes} onChange={e => setNotes(e.target.value)} rows={2}
            style={{ ...styles.input, width: '100%', resize: 'vertical' }} />
        </div>

        <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}
          style={mergeStyles(buttonStyle('primary'), { marginTop: spacing.lg, padding: `${spacing.sm} ${spacing.xl}` })}>
          {saveMutation.isPending ? 'Saving...' : 'Save Count'}
        </button>
      </div>

      {/* History */}
      {history?.float_counts?.length > 0 && (
        <div style={{ ...styles.section, marginTop: spacing.lg }}>
          <h3 style={styles.sectionSubtitle}>Recent Counts</h3>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Date</th>
                <th style={styles.th}>Counted</th>
                <th style={styles.th}>Target</th>
                <th style={styles.th}>Variance</th>
                <th style={styles.th}>By</th>
              </tr>
            </thead>
            <tbody>
              {history.float_counts.map((fc: any) => (
                <tr key={fc.id}>
                  <td style={styles.td}>{new Date(fc.count_date).toLocaleDateString()}</td>
                  <td style={styles.tdRight}>{formatCurrency(fc.total_counted + fc.total_receipts)}</td>
                  <td style={styles.tdRight}>{formatCurrency(fc.target_amount)}</td>
                  <td style={{
                    ...styles.tdRight,
                    color: fc.variance === 0 ? colors.textMuted : fc.variance > 0 ? colors.success : colors.error,
                  }}>
                    {fc.variance > 0 ? '+' : ''}{formatCurrency(fc.variance)}
                  </td>
                  <td style={styles.td}>{fc.created_by_name}</td>
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
// SETTINGS PAGE
// ============================================

const ReconSettingsPage: React.FC = () => {
  const queryClient = useQueryClient()
  const { data: settings, isLoading } = useQuery({
    queryKey: ['recon-settings'],
    queryFn: () => api.get('/reconciliation/settings').then(r => r.data),
  })

  const [tillFloat, setTillFloat] = useState('')
  const [threshold, setThreshold] = useState('')
  const [reportDays, setReportDays] = useState('')
  const [pettyCashTarget, setPettyCashTarget] = useState('')
  const [safeCashTarget, setSafeCashTarget] = useState('')

  useEffect(() => {
    if (settings) {
      setTillFloat(settings.expected_till_float || '300.00')
      setThreshold(settings.variance_threshold || '10.00')
      setReportDays(settings.default_report_days || '7')
      setPettyCashTarget(settings.petty_cash_target || '200.00')
      setSafeCashTarget(settings.safe_cash_target || '0.00')
    }
  }, [settings])

  const saveMutation = useMutation({
    mutationFn: () => api.post('/reconciliation/settings', {
      expected_till_float: parseFloat(tillFloat),
      variance_threshold: parseFloat(threshold),
      default_report_days: parseInt(reportDays),
      petty_cash_target: parseFloat(pettyCashTarget),
      safe_cash_target: parseFloat(safeCashTarget),
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['recon-settings'] })
    },
  })

  if (isLoading) return <p style={{ color: colors.textMuted }}>Loading settings...</p>

  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>Reconciliation Settings</h2>
      <p style={{ color: colors.textMuted, fontSize: typography.sm, marginBottom: spacing.lg }}>
        Newbook API credentials are managed in the main Settings page.
      </p>

      <div style={{ display: 'grid', gridTemplateColumns: '200px 1fr', gap: spacing.md, alignItems: 'center', maxWidth: '500px' }}>
        <label style={styles.label}>Expected Till Float (£):</label>
        <input type="number" step="0.01" value={tillFloat} onChange={e => setTillFloat(e.target.value)} style={styles.numberInput} />

        <label style={styles.label}>Variance Threshold (£):</label>
        <input type="number" step="0.01" value={threshold} onChange={e => setThreshold(e.target.value)} style={styles.numberInput} />

        <label style={styles.label}>Default Report Days:</label>
        <input type="number" min={1} max={365} value={reportDays} onChange={e => setReportDays(e.target.value)} style={styles.numberInput} />

        <label style={styles.label}>Petty Cash Target (£):</label>
        <input type="number" step="0.01" value={pettyCashTarget} onChange={e => setPettyCashTarget(e.target.value)} style={styles.numberInput} />

        <label style={styles.label}>Safe Cash Target (£):</label>
        <input type="number" step="0.01" value={safeCashTarget} onChange={e => setSafeCashTarget(e.target.value)} style={styles.numberInput} />
      </div>

      <button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}
        style={mergeStyles(buttonStyle('primary'), { marginTop: spacing.xl, padding: `${spacing.sm} ${spacing.xl}` })}>
        {saveMutation.isPending ? 'Saving...' : 'Save Settings'}
      </button>
      {saveMutation.isSuccess && <span style={{ color: colors.success, marginLeft: spacing.md }}>Settings saved</span>}
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
  sectionTitle: {
    color: colors.text,
    margin: `0 0 ${spacing.lg}`,
    fontSize: typography.xxl,
    fontWeight: typography.semibold,
  },
  sectionSubtitle: {
    color: colors.text,
    margin: `0 0 ${spacing.md}`,
    fontSize: typography.lg,
    fontWeight: typography.semibold,
  },
  card: {
    background: colors.surface,
    border: `1px solid ${colors.borderLight}`,
    borderRadius: radius.lg,
    padding: spacing.md,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    borderRadius: radius.md,
    overflow: 'hidden',
  },
  th: {
    padding: `${spacing.sm} ${spacing.md}`,
    textAlign: 'left',
    fontSize: typography.xs,
    fontWeight: typography.semibold,
    color: colors.textMuted,
    borderBottom: `2px solid ${colors.border}`,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  thSmall: {
    padding: `${spacing.xs} ${spacing.sm}`,
    textAlign: 'left',
    fontSize: typography.xs,
    fontWeight: typography.semibold,
    color: colors.textMuted,
    borderBottom: `1px solid ${colors.border}`,
  },
  td: {
    padding: `${spacing.sm} ${spacing.md}`,
    fontSize: typography.sm,
    borderBottom: `1px solid ${colors.borderLight}`,
    color: colors.text,
  },
  tdRight: {
    padding: `${spacing.sm} ${spacing.md}`,
    fontSize: typography.sm,
    borderBottom: `1px solid ${colors.borderLight}`,
    color: colors.text,
    textAlign: 'right',
    fontVariantNumeric: 'tabular-nums',
  },
  input: {
    padding: `${spacing.sm} ${spacing.md}`,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    fontSize: typography.sm,
    color: colors.text,
    background: colors.surface,
  },
  numberInput: {
    padding: `${spacing.sm} ${spacing.md}`,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    fontSize: typography.sm,
    color: colors.text,
    background: colors.surface,
    textAlign: 'right',
  },
  numberInputSmall: {
    padding: `${spacing.xs} ${spacing.sm}`,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.sm,
    fontSize: typography.sm,
    color: colors.text,
    textAlign: 'right',
  },
  label: {
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.textSecondary,
  },
  linkBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: typography.sm,
    textDecoration: 'underline',
    padding: 0,
  },
  selectionTooltip: {
    position: 'sticky',
    top: '70px',
    zIndex: 50,
    background: colors.primary,
    color: colors.textLight,
    padding: `${spacing.xs} ${spacing.md}`,
    borderRadius: radius.md,
    fontSize: typography.sm,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
}

export default Reconciliation
