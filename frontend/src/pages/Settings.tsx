import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authApi, UserWithDate } from '../utils/api'
import { useAuth } from '../App'
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

type SettingsPage = 'newbook' | 'resos' | 'users' | 'database' | 'special-dates' | 'budget' | 'tax-rates' | 'forecast-snapshots' | 'backup' | 'api-keys'

const Settings: React.FC = () => {
  const [activePage, setActivePage] = useState<SettingsPage>('newbook')

  const menuItems: { id: SettingsPage; label: string }[] = [
    { id: 'newbook', label: 'Newbook' },
    { id: 'resos', label: 'Resos' },
    { id: 'special-dates', label: 'Special Dates' },
    { id: 'budget', label: 'Budget' },
    { id: 'tax-rates', label: 'Tax Rates' },
    { id: 'forecast-snapshots', label: 'Forecast Snapshots' },
    { id: 'api-keys', label: 'API Keys' },
    { id: 'backup', label: 'Backup & Restore' },
    { id: 'users', label: 'Users' },
    { id: 'database', label: 'Database Browser' },
  ]

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        <h3 style={styles.sidebarTitle}>Settings</h3>
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
        {activePage === 'newbook' && <NewbookPage />}
        {activePage === 'resos' && <ResosPage />}
        {activePage === 'special-dates' && <SpecialDatesPage />}
        {activePage === 'budget' && <BudgetPage />}
        {activePage === 'tax-rates' && <TaxRatesPage />}
        {activePage === 'forecast-snapshots' && <ForecastSnapshotsPage />}
        {activePage === 'backup' && <BackupPage />}
        {activePage === 'users' && <UsersPage />}
        {activePage === 'database' && <DatabasePage />}
        {activePage === 'api-keys' && <ApiKeysPage />}
      </main>
    </div>
  )
}

// ============================================
// NEWBOOK SETTINGS PAGE
// ============================================

interface NewbookSettings {
  newbook_api_key: string | null
  newbook_api_key_set: boolean
  newbook_username: string | null
  newbook_password_set: boolean
  newbook_region: string | null
}

interface RoomCategory {
  id: number
  site_id: string
  site_name: string
  site_type: string | null
  room_count: number
  is_included: boolean
  display_order: number
}

// ============================================
// ROOM CATEGORIES SECTION
// ============================================

const RoomCategoriesSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [fetchStatus, setFetchStatus] = useState<'idle' | 'fetching' | 'success' | 'error'>('idle')
  const [fetchMessage, setFetchMessage] = useState('')

  // Fetch room categories
  const { data: roomCategories, isLoading } = useQuery<RoomCategory[]>({
    queryKey: ['room-categories'],
    queryFn: async () => {
      const response = await fetch('/api/config/room-categories', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Fetch from Newbook API
  const handleFetch = async () => {
    setFetchStatus('fetching')
    setFetchMessage('')
    try {
      const response = await fetch('/api/config/room-categories/fetch', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setFetchStatus('success')
        setFetchMessage(data.message || 'Room categories fetched successfully')
        queryClient.invalidateQueries({ queryKey: ['room-categories'] })
      } else {
        setFetchStatus('error')
        setFetchMessage(data.detail || 'Failed to fetch room categories')
      }
    } catch {
      setFetchStatus('error')
      setFetchMessage('Failed to fetch room categories')
    }
    setTimeout(() => {
      setFetchStatus('idle')
      setFetchMessage('')
    }, 5000)
  }

  // Update a single category (toggle included)
  const handleToggle = async (category: RoomCategory) => {
    try {
      await fetch('/api/config/room-categories/bulk-update', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          updates: [{ id: category.id, is_included: !category.is_included }]
        })
      })
      queryClient.invalidateQueries({ queryKey: ['room-categories'] })
    } catch (err) {
      console.error('Failed to update room category', err)
    }
  }

  // Update display order for a category
  const handleOrderChange = async (category: RoomCategory, newOrder: number) => {
    try {
      await fetch('/api/config/room-categories/bulk-update', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          updates: [{ id: category.id, display_order: newOrder }]
        })
      })
      queryClient.invalidateQueries({ queryKey: ['room-categories'] })
    } catch (err) {
      console.error('Failed to update display order', err)
    }
  }

  // Select/deselect all
  const handleSelectAll = async (include: boolean) => {
    if (!roomCategories?.length) return
    try {
      await fetch('/api/config/room-categories/bulk-update', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          updates: roomCategories.map(c => ({ id: c.id, is_included: include }))
        })
      })
      queryClient.invalidateQueries({ queryKey: ['room-categories'] })
    } catch (err) {
      console.error('Failed to update room categories', err)
    }
  }

  const includedRooms = roomCategories?.filter(c => c.is_included).reduce((sum, c) => sum + (c.room_count || 0), 0) || 0
  const includedTypes = roomCategories?.filter(c => c.is_included).length || 0

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Room Categories (for Occupancy)</h3>
      <p style={styles.hint}>
        Select which room types to include in occupancy and guest calculations. Exclude overflow rooms etc.
      </p>

      <div style={styles.buttonRow}>
        <button
          onClick={handleFetch}
          disabled={fetchStatus === 'fetching'}
          style={mergeStyles(
            buttonStyle('outline'),
            fetchStatus === 'success' ? { borderColor: colors.success, color: colors.success } : {},
            fetchStatus === 'error' ? { borderColor: colors.error, color: colors.error } : {}
          )}
        >
          {fetchStatus === 'fetching' ? 'Fetching...' : 'Fetch Room Categories'}
        </button>
        {roomCategories && roomCategories.length > 0 && (
          <>
            <button onClick={() => handleSelectAll(true)} style={buttonStyle('outline')}>
              Select All
            </button>
            <button onClick={() => handleSelectAll(false)} style={buttonStyle('outline')}>
              Deselect All
            </button>
          </>
        )}
      </div>

      {fetchMessage && (
        <div style={{
          ...styles.statusMessage,
          background: fetchStatus === 'success' ? colors.successBg : colors.errorBg,
          color: fetchStatus === 'success' ? colors.success : colors.error,
          marginTop: spacing.sm,
        }}>
          {fetchMessage}
        </div>
      )}

      {isLoading ? (
        <div style={styles.loading}>Loading room categories...</div>
      ) : roomCategories && roomCategories.length > 0 ? (
        <>
          <div style={styles.roomCategoryHeader}>
            <span style={styles.roomCategorySummary}>
              {includedRooms} rooms in {includedTypes} types selected
            </span>
          </div>
          <div style={styles.roomCategoryList}>
            {roomCategories.map((cat) => (
              <div key={cat.id} style={styles.roomCategoryItem}>
                <input
                  type="checkbox"
                  checked={cat.is_included}
                  onChange={() => handleToggle(cat)}
                  style={styles.checkbox}
                />
                <span style={styles.roomCategoryName}>{cat.site_name}</span>
                <span style={styles.roomCategoryCount}>{cat.room_count} rooms</span>
                <input
                  type="number"
                  value={cat.display_order}
                  onChange={(e) => handleOrderChange(cat, parseInt(e.target.value) || 0)}
                  style={styles.displayOrderInput}
                  min={0}
                  title="Display order (lower = first)"
                />
              </div>
            ))}
          </div>
        </>
      ) : (
        <div style={styles.emptyState}>
          No room categories loaded. Click "Fetch Room Categories" to load from Newbook.
        </div>
      )}
    </div>
  )
}

// ============================================
// GL REVENUE MAPPING SECTION
// ============================================

interface GLAccount {
  id: number
  gl_account_id: string
  gl_code: string | null
  gl_name: string | null
  gl_group_id: string | null
  gl_group_name: string | null
  department: 'accommodation' | 'dry' | 'wet' | null
  is_active: boolean
}

type Department = 'accommodation' | 'dry' | 'wet'

const DEPARTMENTS: { key: Department; label: string }[] = [
  { key: 'accommodation', label: 'Accommodation' },
  { key: 'dry', label: 'Dry (Food)' },
  { key: 'wet', label: 'Wet (Beverage)' },
]

const GLRevenueMappingSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [fetchStatus, setFetchStatus] = useState<'idle' | 'fetching' | 'success' | 'error'>('idle')
  const [fetchMessage, setFetchMessage] = useState('')
  const [modalDepartment, setModalDepartment] = useState<Department | null>(null)

  // Fetch GL accounts
  const { data: glAccounts, isLoading } = useQuery<GLAccount[]>({
    queryKey: ['gl-accounts'],
    queryFn: async () => {
      const response = await fetch('/api/config/gl-accounts', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Fetch from Newbook API
  const handleFetch = async () => {
    setFetchStatus('fetching')
    setFetchMessage('')
    try {
      const response = await fetch('/api/config/gl-accounts/fetch', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setFetchStatus('success')
        setFetchMessage(data.message || 'GL accounts fetched successfully')
        queryClient.invalidateQueries({ queryKey: ['gl-accounts'] })
      } else {
        setFetchStatus('error')
        setFetchMessage(data.detail || 'Failed to fetch GL accounts')
      }
    } catch {
      setFetchStatus('error')
      setFetchMessage('Failed to fetch GL accounts')
    }
    setTimeout(() => {
      setFetchStatus('idle')
      setFetchMessage('')
    }, 5000)
  }

  // Update department for accounts
  const handleUpdateDepartments = async (updates: { id: number; department: string | null }[]) => {
    try {
      await fetch('/api/config/gl-accounts/department', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ updates })
      })
      queryClient.invalidateQueries({ queryKey: ['gl-accounts'] })
    } catch (err) {
      console.error('Failed to update GL accounts', err)
    }
  }

  // Get accounts for a specific department
  const getAccountsForDepartment = (dept: Department) =>
    glAccounts?.filter(acc => acc.department === dept) || []

  // Remove account from department
  const handleRemoveFromDepartment = (accountId: number) => {
    handleUpdateDepartments([{ id: accountId, department: null }])
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>GL Revenue Mapping</h3>
      <p style={styles.hint}>
        Map GL accounts to revenue departments for aggregation. Fetch accounts first, then assign to each department.
      </p>

      <div style={styles.buttonRow}>
        <button
          onClick={handleFetch}
          disabled={fetchStatus === 'fetching'}
          style={mergeStyles(
            buttonStyle('outline'),
            fetchStatus === 'success' ? { borderColor: colors.success, color: colors.success } : {},
            fetchStatus === 'error' ? { borderColor: colors.error, color: colors.error } : {}
          )}
        >
          {fetchStatus === 'fetching' ? 'Fetching...' : 'Fetch GL Accounts'}
        </button>
        {glAccounts && glAccounts.length > 0 && (
          <span style={styles.glAccountCount}>{glAccounts.length} accounts loaded</span>
        )}
      </div>

      {fetchMessage && (
        <div style={{
          ...styles.statusMessage,
          background: fetchStatus === 'success' ? colors.successBg : colors.errorBg,
          color: fetchStatus === 'success' ? colors.success : colors.error,
          marginTop: spacing.sm,
        }}>
          {fetchMessage}
        </div>
      )}

      {isLoading ? (
        <div style={styles.loading}>Loading GL accounts...</div>
      ) : glAccounts && glAccounts.length > 0 ? (
        <div style={styles.departmentGrid}>
          {DEPARTMENTS.map(dept => {
            const deptAccounts = getAccountsForDepartment(dept.key)
            return (
              <div key={dept.key} style={styles.departmentColumn}>
                <div style={styles.departmentHeader}>
                  <span style={styles.departmentTitle}>{dept.label}</span>
                  <span style={styles.departmentCount}>{deptAccounts.length} accounts</span>
                </div>
                <div style={styles.departmentAccountList}>
                  {deptAccounts.length === 0 ? (
                    <div style={styles.departmentEmpty}>No accounts mapped</div>
                  ) : (
                    deptAccounts.map(acc => (
                      <div key={acc.id} style={styles.departmentAccountItem}>
                        <span style={styles.departmentAccountName}>
                          {acc.gl_name || acc.gl_code || acc.gl_account_id}
                        </span>
                        {acc.gl_code && <span style={styles.departmentAccountCode}>{acc.gl_code}</span>}
                        <button
                          onClick={() => handleRemoveFromDepartment(acc.id)}
                          style={styles.removeButton}
                          title="Remove from department"
                        >
                          ×
                        </button>
                      </div>
                    ))
                  )}
                </div>
                <button
                  onClick={() => setModalDepartment(dept.key)}
                  style={buttonStyle('outline')}
                >
                  Select Accounts
                </button>
              </div>
            )
          })}
        </div>
      ) : (
        <div style={styles.emptyState}>
          No GL accounts loaded. Click "Fetch GL Accounts" to load from Newbook.
        </div>
      )}

      {/* GL Account Selection Modal */}
      {modalDepartment && glAccounts && (
        <GLAccountModal
          department={modalDepartment}
          departmentLabel={DEPARTMENTS.find(d => d.key === modalDepartment)?.label || ''}
          glAccounts={glAccounts}
          onUpdate={handleUpdateDepartments}
          onClose={() => setModalDepartment(null)}
        />
      )}
    </div>
  )
}

// GL Account Selection Modal Component
interface GLAccountModalProps {
  department: Department
  departmentLabel: string
  glAccounts: GLAccount[]
  onUpdate: (updates: { id: number; department: string | null }[]) => void
  onClose: () => void
}

const GLAccountModal: React.FC<GLAccountModalProps> = ({
  department,
  departmentLabel,
  glAccounts,
  onUpdate,
  onClose
}) => {
  // Group accounts by gl_group_name
  const grouped: Record<string, GLAccount[]> = {}
  glAccounts.forEach(acc => {
    const groupName = acc.gl_group_name || 'Ungrouped'
    if (!grouped[groupName]) grouped[groupName] = []
    grouped[groupName].push(acc)
  })
  const sortedGroups = Object.keys(grouped).sort()

  // Check if account is selected for this department
  const isSelected = (acc: GLAccount) => acc.department === department

  // Toggle single account
  const handleToggle = (acc: GLAccount) => {
    if (isSelected(acc)) {
      onUpdate([{ id: acc.id, department: null }])
    } else {
      onUpdate([{ id: acc.id, department }])
    }
  }

  // Toggle entire group
  const handleGroupToggle = (groupAccounts: GLAccount[]) => {
    const allSelected = groupAccounts.every(acc => acc.department === department)
    if (allSelected) {
      // Deselect all in group
      onUpdate(groupAccounts.map(acc => ({ id: acc.id, department: null })))
    } else {
      // Select all in group
      onUpdate(groupAccounts.map(acc => ({ id: acc.id, department })))
    }
  }

  return (
    <div style={styles.modalOverlay} onClick={onClose}>
      <div style={styles.modalContent} onClick={e => e.stopPropagation()}>
        <div style={styles.modalHeader}>
          <h3 style={styles.modalTitle}>Select GL Accounts for {departmentLabel}</h3>
          <button onClick={onClose} style={styles.modalCloseButton}>×</button>
        </div>
        <div style={styles.modalBody}>
          {sortedGroups.map(groupName => {
            const groupAccounts = grouped[groupName]
            const selectedCount = groupAccounts.filter(acc => acc.department === department).length
            const allSelected = selectedCount === groupAccounts.length
            const someSelected = selectedCount > 0 && !allSelected

            return (
              <div key={groupName} style={styles.glGroup}>
                <label style={styles.glGroupHeader}>
                  <input
                    type="checkbox"
                    checked={allSelected}
                    ref={el => { if (el) el.indeterminate = someSelected }}
                    onChange={() => handleGroupToggle(groupAccounts)}
                    style={styles.checkbox}
                  />
                  <span style={styles.glGroupName}>{groupName}</span>
                  <span style={styles.glGroupCount}>({selectedCount}/{groupAccounts.length})</span>
                </label>
                <div style={styles.glGroupItems}>
                  {groupAccounts.map(acc => (
                    <label key={acc.id} style={styles.glItem}>
                      <input
                        type="checkbox"
                        checked={isSelected(acc)}
                        onChange={() => handleToggle(acc)}
                        style={styles.checkbox}
                      />
                      <span style={styles.glItemName}>{acc.gl_name || 'Unnamed'}</span>
                      {acc.gl_code && <span style={styles.glItemCode}>({acc.gl_code})</span>}
                      {acc.department && acc.department !== department && (
                        <span style={styles.glItemMapped}>
                          → {DEPARTMENTS.find(d => d.key === acc.department)?.label}
                        </span>
                      )}
                    </label>
                  ))}
                </div>
              </div>
            )
          })}
        </div>
        <div style={styles.modalFooter}>
          <button onClick={onClose} style={buttonStyle('primary')}>Done</button>
        </div>
      </div>
    </div>
  )
}

// ============================================
// BOOKINGS DATA SYNC SECTION
// ============================================

interface SyncStatus {
  last_successful_sync: {
    completed_at: string | null
    records_fetched: number | null
    records_created: number | null
    triggered_by: string | null
  } | null
  last_sync: {
    started_at: string | null
    completed_at: string | null
    status: string | null
    records_fetched: number | null
    error_message: string | null
    triggered_by: string | null
  } | null
  auto_sync: {
    enabled: boolean
    type: string
    time: string
  }
  total_records: number
}

interface SyncLog {
  id: number
  started_at: string
  completed_at: string | null
  status: string
  records_fetched: number | null
  records_created: number | null
  date_from: string | null
  date_to: string | null
  error_message: string | null
  triggered_by: string | null
}

const BookingsDataSyncSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'success' | 'error'>('idle')
  const [syncMessage, setSyncMessage] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [autoEnabled, setAutoEnabled] = useState(false)
  const [autoType, setAutoType] = useState('incremental')
  const [syncTime, setSyncTime] = useState('05:00')

  // Fetch sync status
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery<SyncStatus>({
    queryKey: ['bookings-sync-status'],
    queryFn: async () => {
      const response = await fetch('/api/sync/bookings-data/status', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch status')
      return response.json()
    },
    refetchInterval: syncStatus === 'syncing' ? 3000 : false,
  })

  // Fetch sync logs
  const { data: logs, isLoading: logsLoading } = useQuery<SyncLog[]>({
    queryKey: ['bookings-sync-logs'],
    queryFn: async () => {
      const response = await fetch('/api/sync/bookings-data/logs?limit=5', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    refetchInterval: syncStatus === 'syncing' ? 3000 : false,
  })

  // Update local state when status loads
  React.useEffect(() => {
    if (status?.auto_sync) {
      setAutoEnabled(status.auto_sync.enabled)
      setAutoType(status.auto_sync.type)
      setSyncTime(status.auto_sync.time || '05:00')
    }
    // Check if sync is currently running
    if (status?.last_sync?.status === 'running') {
      setSyncStatus('syncing')
    } else if (syncStatus === 'syncing' && status?.last_sync?.status !== 'running') {
      // Sync completed
      setSyncStatus(status?.last_sync?.status === 'success' ? 'success' : 'error')
      setSyncMessage(status?.last_sync?.status === 'success'
        ? `Synced ${status?.last_sync?.records_fetched || 0} bookings`
        : status?.last_sync?.error_message || 'Sync failed')
      setTimeout(() => {
        setSyncStatus('idle')
        setSyncMessage('')
      }, 5000)
      queryClient.invalidateQueries({ queryKey: ['bookings-sync-status'] })
      queryClient.invalidateQueries({ queryKey: ['bookings-sync-logs'] })
    }
  }, [status, syncStatus, queryClient])

  // Trigger sync
  const handleSync = async (mode: 'incremental' | 'staying_range') => {
    setSyncStatus('syncing')
    setSyncMessage('')
    try {
      let url = `/api/sync/bookings-data/sync?sync_mode=${mode}`
      if (mode === 'staying_range' && fromDate && toDate) {
        url += `&from_date=${fromDate}&to_date=${toDate}`
      }
      const response = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setSyncMessage(data.message || 'Sync started...')
        // Keep polling via refetchInterval
      } else {
        setSyncStatus('error')
        setSyncMessage(data.detail || 'Failed to start sync')
        setTimeout(() => {
          setSyncStatus('idle')
          setSyncMessage('')
        }, 5000)
      }
    } catch {
      setSyncStatus('error')
      setSyncMessage('Failed to start sync')
      setTimeout(() => {
        setSyncStatus('idle')
        setSyncMessage('')
      }, 5000)
    }
  }

  // Update auto sync config
  const handleAutoConfigSave = async () => {
    try {
      const response = await fetch('/api/sync/bookings-data/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          enabled: autoEnabled,
          sync_type: autoType,
          sync_time: syncTime
        })
      })
      if (response.ok) {
        refetchStatus()
      }
    } catch (err) {
      console.error('Failed to update config', err)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString()
  }

  const formatTrigger = (trigger: string | null) => {
    if (!trigger) return '-'
    if (trigger.startsWith('user:')) return trigger.replace('user:', '')
    if (trigger === 'scheduler') return 'Auto'
    return trigger
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Bookings Data Sync</h3>
      <p style={styles.hint}>
        Sync booking data from Newbook. Use date range for specific periods, or incremental for recent changes.
      </p>

      {statusLoading ? (
        <div style={styles.loading}>Loading sync status...</div>
      ) : (
        <>
          {/* Status summary */}
          <div style={styles.syncStatusRow}>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Total Records</span>
              <span style={styles.syncStatusValue}>{status?.total_records?.toLocaleString() || 0}</span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Last Sync</span>
              <span style={styles.syncStatusValue}>
                {status?.last_successful_sync?.completed_at
                  ? formatDate(status.last_successful_sync.completed_at)
                  : 'Never'}
              </span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Auto Sync</span>
              <span style={status?.auto_sync?.enabled ? styles.statusOk : styles.statusPending}>
                {status?.auto_sync?.enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          </div>

          {/* Sync controls */}
          <div style={styles.syncControlsSection}>
            {/* Incremental sync */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Incremental Update</h4>
              <p style={styles.syncControlHint}>
                Fetches bookings modified since last sync (or last 7 days if no history).
              </p>
              <button
                onClick={() => handleSync('incremental')}
                disabled={syncStatus === 'syncing'}
                style={mergeStyles(
                  buttonStyle('primary'),
                  syncStatus === 'syncing' ? { opacity: 0.7 } : {}
                )}
              >
                {syncStatus === 'syncing' ? 'Syncing...' : 'Run Incremental Sync'}
              </button>
            </div>

            {/* Date range sync */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Date Range Sync</h4>
              <p style={styles.syncControlHint}>
                Fetches bookings staying during the specified date range.
              </p>
              <div style={styles.syncDateRow}>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  style={styles.dateInput}
                />
                <span style={styles.dateTo}>to</span>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  style={styles.dateInput}
                />
              </div>
              <button
                onClick={() => handleSync('staying_range')}
                disabled={syncStatus === 'syncing' || !fromDate || !toDate}
                style={mergeStyles(
                  buttonStyle('outline'),
                  (syncStatus === 'syncing' || !fromDate || !toDate) ? { opacity: 0.7 } : {}
                )}
              >
                Sync Date Range
              </button>
            </div>

            {/* Auto sync config */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Automatic Sync</h4>
              <p style={styles.syncControlHint}>
                Enable scheduled daily sync at configured time.
              </p>
              <label style={styles.syncCheckboxLabel}>
                <input
                  type="checkbox"
                  checked={autoEnabled}
                  onChange={(e) => setAutoEnabled(e.target.checked)}
                  style={styles.checkbox}
                />
                Enable auto sync
              </label>
              <div style={styles.syncAutoRow}>
                <select
                  value={autoType}
                  onChange={(e) => setAutoType(e.target.value)}
                  style={styles.syncSelect}
                  disabled={!autoEnabled}
                >
                  <option value="incremental">Incremental</option>
                  <option value="full">Full (not recommended)</option>
                </select>
                <span style={styles.syncTimeLabel}>at</span>
                <input
                  type="time"
                  value={syncTime}
                  onChange={(e) => setSyncTime(e.target.value)}
                  style={styles.syncTimeInput}
                  disabled={!autoEnabled}
                />
              </div>
              <button
                onClick={handleAutoConfigSave}
                style={buttonStyle('outline')}
              >
                Save Settings
              </button>
            </div>
          </div>

          {/* Sync message */}
          {syncMessage && (
            <div style={{
              ...styles.statusMessage,
              background: syncStatus === 'success' ? colors.successBg :
                         syncStatus === 'error' ? colors.errorBg : colors.background,
              color: syncStatus === 'success' ? colors.success :
                     syncStatus === 'error' ? colors.error : colors.text,
              marginTop: spacing.md,
            }}>
              {syncMessage}
            </div>
          )}

          {/* Recent sync logs */}
          <div style={styles.syncLogsSection}>
            <h4 style={styles.syncLogsTitle}>Recent Syncs</h4>
            {logsLoading ? (
              <div style={styles.loading}>Loading logs...</div>
            ) : logs && logs.length > 0 ? (
              <div style={styles.syncLogsList}>
                {logs.map((log) => (
                  <div key={log.id} style={styles.syncLogItem}>
                    <div style={styles.syncLogMain}>
                      <span style={{
                        ...styles.syncLogStatus,
                        color: log.status === 'success' ? colors.success :
                               log.status === 'running' ? colors.accent :
                               colors.error
                      }}>
                        {log.status === 'running' ? '●' : log.status === 'success' ? '✓' : '✗'}
                      </span>
                      <span style={styles.syncLogDate}>{formatDate(log.started_at)}</span>
                      <span style={styles.syncLogRecords}>
                        {log.records_fetched !== null ? `${log.records_fetched} fetched` : ''}
                        {log.records_created !== null ? `, ${log.records_created} new` : ''}
                      </span>
                    </div>
                    <div style={styles.syncLogMeta}>
                      <span style={styles.syncLogTrigger}>{formatTrigger(log.triggered_by)}</span>
                      {log.date_from && log.date_to && (
                        <span style={styles.syncLogRange}>{log.date_from} → {log.date_to}</span>
                      )}
                    </div>
                    {log.error_message && (
                      <div style={styles.syncLogError}>{log.error_message}</div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={styles.emptyState}>No sync history yet.</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ============================================
// OCCUPANCY DATA SYNC SECTION
// ============================================

interface OccupancySyncStatus {
  last_successful_sync: {
    completed_at: string | null
    records_fetched: number | null
    records_created: number | null
    date_from: string | null
    date_to: string | null
    triggered_by: string | null
  } | null
  last_sync: {
    started_at: string | null
    completed_at: string | null
    status: string | null
    records_fetched: number | null
    date_from: string | null
    date_to: string | null
    error_message: string | null
    triggered_by: string | null
  } | null
  auto_sync: {
    enabled: boolean
    time: string
  }
  total_records: number
  data_range: {
    from: string | null
    to: string | null
  }
}

const OccupancyDataSyncSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'success' | 'error'>('idle')
  const [syncMessage, setSyncMessage] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [autoEnabled, setAutoEnabled] = useState(false)
  const [syncTime, setSyncTime] = useState('05:00')

  // Fetch sync status
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery<OccupancySyncStatus>({
    queryKey: ['occupancy-sync-status'],
    queryFn: async () => {
      const response = await fetch('/api/sync/occupancy-data/status', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch status')
      return response.json()
    },
    refetchInterval: syncStatus === 'syncing' ? 3000 : false,
  })

  // Fetch sync logs
  const { data: logs, isLoading: logsLoading } = useQuery<SyncLog[]>({
    queryKey: ['occupancy-sync-logs'],
    queryFn: async () => {
      const response = await fetch('/api/sync/occupancy-data/logs?limit=5', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    refetchInterval: syncStatus === 'syncing' ? 3000 : false,
  })

  // Update local state when status loads
  React.useEffect(() => {
    if (status?.auto_sync) {
      setAutoEnabled(status.auto_sync.enabled)
      setSyncTime(status.auto_sync.time || '05:00')
    }
    // Check if sync is currently running
    if (status?.last_sync?.status === 'running') {
      setSyncStatus('syncing')
    } else if (syncStatus === 'syncing' && status?.last_sync?.status !== 'running') {
      // Sync completed
      setSyncStatus(status?.last_sync?.status === 'success' ? 'success' : 'error')
      setSyncMessage(status?.last_sync?.status === 'success'
        ? `Synced ${status?.last_sync?.records_fetched || 0} records`
        : status?.last_sync?.error_message || 'Sync failed')
      setTimeout(() => {
        setSyncStatus('idle')
        setSyncMessage('')
      }, 5000)
      queryClient.invalidateQueries({ queryKey: ['occupancy-sync-status'] })
      queryClient.invalidateQueries({ queryKey: ['occupancy-sync-logs'] })
    }
  }, [status, syncStatus, queryClient])

  // Trigger sync
  const handleSync = async () => {
    setSyncStatus('syncing')
    setSyncMessage('')
    try {
      let url = '/api/sync/occupancy-data/sync'
      if (fromDate && toDate) {
        url += `?from_date=${fromDate}&to_date=${toDate}`
      }
      const response = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setSyncMessage(data.message || 'Sync started...')
        // Keep polling via refetchInterval
      } else {
        setSyncStatus('error')
        setSyncMessage(data.detail || 'Failed to start sync')
        setTimeout(() => {
          setSyncStatus('idle')
          setSyncMessage('')
        }, 5000)
      }
    } catch {
      setSyncStatus('error')
      setSyncMessage('Failed to start sync')
      setTimeout(() => {
        setSyncStatus('idle')
        setSyncMessage('')
      }, 5000)
    }
  }

  // Update auto sync config
  const handleAutoConfigSave = async () => {
    try {
      const response = await fetch('/api/sync/occupancy-data/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          enabled: autoEnabled,
          sync_time: syncTime
        })
      })
      if (response.ok) {
        refetchStatus()
      }
    } catch (err) {
      console.error('Failed to update config', err)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString()
  }

  const formatTrigger = (trigger: string | null) => {
    if (!trigger) return '-'
    if (trigger.startsWith('user:')) return trigger.replace('user:', '')
    if (trigger === 'scheduler') return 'Auto'
    return trigger
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Occupancy Report Data Sync</h3>
      <p style={styles.hint}>
        Sync occupancy report data from Newbook. This includes available rooms, occupied, maintenance, and revenue per category.
      </p>

      {statusLoading ? (
        <div style={styles.loading}>Loading sync status...</div>
      ) : (
        <>
          {/* Status summary */}
          <div style={styles.syncStatusRow}>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Total Records</span>
              <span style={styles.syncStatusValue}>{status?.total_records?.toLocaleString() || 0}</span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Data Range</span>
              <span style={styles.syncStatusValue}>
                {status?.data_range?.from && status?.data_range?.to
                  ? `${status.data_range.from} → ${status.data_range.to}`
                  : 'No data'}
              </span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Last Sync</span>
              <span style={styles.syncStatusValue}>
                {status?.last_successful_sync?.completed_at
                  ? formatDate(status.last_successful_sync.completed_at)
                  : 'Never'}
              </span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Auto Sync</span>
              <span style={status?.auto_sync?.enabled ? styles.statusOk : styles.statusPending}>
                {status?.auto_sync?.enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          </div>

          {/* Sync controls */}
          <div style={styles.syncControlsSection}>
            {/* Date range sync */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Manual Sync</h4>
              <p style={styles.syncControlHint}>
                Sync occupancy data for date range. Default: -7 to +365 days if not specified.
              </p>
              <div style={styles.syncDateRow}>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  style={styles.dateInput}
                  placeholder="From"
                />
                <span style={styles.dateTo}>to</span>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  style={styles.dateInput}
                  placeholder="To"
                />
              </div>
              <button
                onClick={handleSync}
                disabled={syncStatus === 'syncing'}
                style={mergeStyles(
                  buttonStyle('primary'),
                  syncStatus === 'syncing' ? { opacity: 0.7 } : {}
                )}
              >
                {syncStatus === 'syncing' ? 'Syncing...' : 'Run Sync'}
              </button>
            </div>

            {/* Auto sync config */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Automatic Sync</h4>
              <p style={styles.syncControlHint}>
                Enable scheduled daily sync at configured time (-7 to +365 days).
              </p>
              <label style={styles.syncCheckboxLabel}>
                <input
                  type="checkbox"
                  checked={autoEnabled}
                  onChange={(e) => setAutoEnabled(e.target.checked)}
                  style={styles.checkbox}
                />
                Enable auto sync
              </label>
              <div style={styles.syncAutoRow}>
                <span style={styles.syncTimeLabel}>Sync at</span>
                <input
                  type="time"
                  value={syncTime}
                  onChange={(e) => setSyncTime(e.target.value)}
                  style={styles.syncTimeInput}
                  disabled={!autoEnabled}
                />
              </div>
              <button
                onClick={handleAutoConfigSave}
                style={buttonStyle('outline')}
              >
                Save Settings
              </button>
            </div>
          </div>

          {/* Sync message */}
          {syncMessage && (
            <div style={{
              ...styles.statusMessage,
              background: syncStatus === 'success' ? colors.successBg :
                         syncStatus === 'error' ? colors.errorBg : colors.background,
              color: syncStatus === 'success' ? colors.success :
                     syncStatus === 'error' ? colors.error : colors.text,
              marginTop: spacing.md,
            }}>
              {syncMessage}
            </div>
          )}

          {/* Recent sync logs */}
          <div style={styles.syncLogsSection}>
            <h4 style={styles.syncLogsTitle}>Recent Syncs</h4>
            {logsLoading ? (
              <div style={styles.loading}>Loading logs...</div>
            ) : logs && logs.length > 0 ? (
              <div style={styles.syncLogsList}>
                {logs.map((log) => (
                  <div key={log.id} style={styles.syncLogItem}>
                    <div style={styles.syncLogMain}>
                      <span style={{
                        ...styles.syncLogStatus,
                        color: log.status === 'success' ? colors.success :
                               log.status === 'running' ? colors.accent :
                               colors.error
                      }}>
                        {log.status === 'running' ? '●' : log.status === 'success' ? '✓' : '✗'}
                      </span>
                      <span style={styles.syncLogDate}>{formatDate(log.started_at)}</span>
                      <span style={styles.syncLogRecords}>
                        {log.records_fetched !== null ? `${log.records_fetched} records` : ''}
                      </span>
                    </div>
                    <div style={styles.syncLogMeta}>
                      <span style={styles.syncLogTrigger}>{formatTrigger(log.triggered_by)}</span>
                      {log.date_from && log.date_to && (
                        <span style={styles.syncLogRange}>{log.date_from} → {log.date_to}</span>
                      )}
                    </div>
                    {log.error_message && (
                      <div style={styles.syncLogError}>{log.error_message}</div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={styles.emptyState}>No sync history yet.</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ============================================
// EARNED REVENUE DATA SYNC SECTION
// ============================================

interface EarnedRevenueSyncStatus {
  last_successful_sync: {
    completed_at: string | null
    records_fetched: number | null
    records_created: number | null
    date_from: string | null
    date_to: string | null
    triggered_by: string | null
  } | null
  last_sync: {
    started_at: string | null
    completed_at: string | null
    status: string | null
    records_fetched: number | null
    date_from: string | null
    date_to: string | null
    error_message: string | null
    triggered_by: string | null
  } | null
  auto_sync: {
    enabled: boolean
    time: string
  }
  total_records: number
  data_range: {
    from: string | null
    to: string | null
  }
}

const EarnedRevenueDataSyncSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'success' | 'error'>('idle')
  const [syncMessage, setSyncMessage] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [autoEnabled, setAutoEnabled] = useState(false)
  const [syncTime, setSyncTime] = useState('05:10')

  // Fetch sync status
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery<EarnedRevenueSyncStatus>({
    queryKey: ['earned-revenue-sync-status'],
    queryFn: async () => {
      const response = await fetch('/api/sync/earned-revenue-data/status', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch status')
      return response.json()
    },
    refetchInterval: syncStatus === 'syncing' ? 3000 : false,
  })

  // Fetch sync logs
  const { data: logs, isLoading: logsLoading } = useQuery<SyncLog[]>({
    queryKey: ['earned-revenue-sync-logs'],
    queryFn: async () => {
      const response = await fetch('/api/sync/earned-revenue-data/logs?limit=5', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    refetchInterval: syncStatus === 'syncing' ? 3000 : false,
  })

  // Update local state when status loads
  React.useEffect(() => {
    if (status?.auto_sync) {
      setAutoEnabled(status.auto_sync.enabled)
      setSyncTime(status.auto_sync.time || '05:10')
    }
    // Check if sync is currently running
    if (status?.last_sync?.status === 'running') {
      setSyncStatus('syncing')
    } else if (syncStatus === 'syncing' && status?.last_sync?.status !== 'running') {
      // Sync completed
      setSyncStatus(status?.last_sync?.status === 'success' ? 'success' : 'error')
      setSyncMessage(status?.last_sync?.status === 'success'
        ? `Synced ${status?.last_sync?.records_fetched || 0} records`
        : status?.last_sync?.error_message || 'Sync failed')
      setTimeout(() => {
        setSyncStatus('idle')
        setSyncMessage('')
      }, 5000)
      queryClient.invalidateQueries({ queryKey: ['earned-revenue-sync-status'] })
      queryClient.invalidateQueries({ queryKey: ['earned-revenue-sync-logs'] })
    }
  }, [status, syncStatus, queryClient])

  // Trigger sync
  const handleSync = async () => {
    setSyncStatus('syncing')
    setSyncMessage('')
    try {
      let url = '/api/sync/earned-revenue-data/sync'
      if (fromDate && toDate) {
        url += `?from_date=${fromDate}&to_date=${toDate}`
      }
      const response = await fetch(url, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setSyncMessage(data.message || 'Sync started...')
        // Keep polling via refetchInterval
      } else {
        setSyncStatus('error')
        setSyncMessage(data.detail || 'Failed to start sync')
        setTimeout(() => {
          setSyncStatus('idle')
          setSyncMessage('')
        }, 5000)
      }
    } catch {
      setSyncStatus('error')
      setSyncMessage('Failed to start sync')
      setTimeout(() => {
        setSyncStatus('idle')
        setSyncMessage('')
      }, 5000)
    }
  }

  // Update auto sync config
  const handleAutoConfigSave = async () => {
    try {
      const response = await fetch('/api/sync/earned-revenue-data/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          enabled: autoEnabled,
          sync_time: syncTime
        })
      })
      if (response.ok) {
        refetchStatus()
      }
    } catch (err) {
      console.error('Failed to update config', err)
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString()
  }

  const formatTrigger = (trigger: string | null) => {
    if (!trigger) return '-'
    if (trigger.startsWith('user:')) return trigger.replace('user:', '')
    if (trigger === 'scheduler') return 'Auto'
    return trigger
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Earned Revenue Data Sync</h3>
      <p style={styles.hint}>
        Sync earned revenue from Newbook (official GL figures). Used for revenue accuracy tracking.
      </p>

      {statusLoading ? (
        <div style={styles.loading}>Loading sync status...</div>
      ) : (
        <>
          {/* Status summary */}
          <div style={styles.syncStatusRow}>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Total Records</span>
              <span style={styles.syncStatusValue}>{status?.total_records?.toLocaleString() || 0}</span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Data Range</span>
              <span style={styles.syncStatusValue}>
                {status?.data_range?.from && status?.data_range?.to
                  ? `${status.data_range.from} → ${status.data_range.to}`
                  : 'No data'}
              </span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Last Sync</span>
              <span style={styles.syncStatusValue}>
                {status?.last_successful_sync?.completed_at
                  ? formatDate(status.last_successful_sync.completed_at)
                  : 'Never'}
              </span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Auto Sync</span>
              <span style={status?.auto_sync?.enabled ? styles.statusOk : styles.statusPending}>
                {status?.auto_sync?.enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          </div>

          {/* Sync controls */}
          <div style={styles.syncControlsSection}>
            {/* Date range sync */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Manual Sync</h4>
              <p style={styles.syncControlHint}>
                Sync earned revenue for date range. Default: last 7 days if not specified.
              </p>
              <div style={styles.syncDateRow}>
                <input
                  type="date"
                  value={fromDate}
                  onChange={(e) => setFromDate(e.target.value)}
                  style={styles.dateInput}
                  placeholder="From"
                />
                <span style={styles.dateTo}>to</span>
                <input
                  type="date"
                  value={toDate}
                  onChange={(e) => setToDate(e.target.value)}
                  style={styles.dateInput}
                  placeholder="To"
                />
              </div>
              <button
                onClick={handleSync}
                disabled={syncStatus === 'syncing'}
                style={mergeStyles(
                  buttonStyle('primary'),
                  syncStatus === 'syncing' ? { opacity: 0.7 } : {}
                )}
              >
                {syncStatus === 'syncing' ? 'Syncing...' : 'Run Sync'}
              </button>
            </div>

            {/* Auto sync config */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Automatic Sync</h4>
              <p style={styles.syncControlHint}>
                Enable scheduled daily sync at configured time (last 7 days).
              </p>
              <label style={styles.syncCheckboxLabel}>
                <input
                  type="checkbox"
                  checked={autoEnabled}
                  onChange={(e) => setAutoEnabled(e.target.checked)}
                  style={styles.checkbox}
                />
                Enable auto sync
              </label>
              <div style={styles.syncAutoRow}>
                <span style={styles.syncTimeLabel}>Sync at</span>
                <input
                  type="time"
                  value={syncTime}
                  onChange={(e) => setSyncTime(e.target.value)}
                  style={styles.syncTimeInput}
                  disabled={!autoEnabled}
                />
              </div>
              <button
                onClick={handleAutoConfigSave}
                style={buttonStyle('outline')}
              >
                Save Settings
              </button>
            </div>
          </div>

          {/* Sync message */}
          {syncMessage && (
            <div style={{
              ...styles.statusMessage,
              background: syncStatus === 'success' ? colors.successBg :
                         syncStatus === 'error' ? colors.errorBg : colors.background,
              color: syncStatus === 'success' ? colors.success :
                     syncStatus === 'error' ? colors.error : colors.text,
              marginTop: spacing.md,
            }}>
              {syncMessage}
            </div>
          )}

          {/* Recent sync logs */}
          <div style={styles.syncLogsSection}>
            <h4 style={styles.syncLogsTitle}>Recent Syncs</h4>
            {logsLoading ? (
              <div style={styles.loading}>Loading logs...</div>
            ) : logs && logs.length > 0 ? (
              <div style={styles.syncLogsList}>
                {logs.map((log) => (
                  <div key={log.id} style={styles.syncLogItem}>
                    <div style={styles.syncLogMain}>
                      <span style={{
                        ...styles.syncLogStatus,
                        color: log.status === 'success' ? colors.success :
                               log.status === 'running' ? colors.accent :
                               colors.error
                      }}>
                        {log.status === 'running' ? '●' : log.status === 'success' ? '✓' : '✗'}
                      </span>
                      <span style={styles.syncLogDate}>{formatDate(log.started_at)}</span>
                      <span style={styles.syncLogRecords}>
                        {log.records_fetched !== null ? `${log.records_fetched} records` : ''}
                      </span>
                    </div>
                    <div style={styles.syncLogMeta}>
                      <span style={styles.syncLogTrigger}>{formatTrigger(log.triggered_by)}</span>
                      {log.date_from && log.date_to && (
                        <span style={styles.syncLogRange}>{log.date_from} → {log.date_to}</span>
                      )}
                    </div>
                    {log.error_message && (
                      <div style={styles.syncLogError}>{log.error_message}</div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={styles.emptyState}>No sync history yet.</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ============================================
// CURRENT RATES DATA SYNC SECTION (Pickup-V2)
// ============================================

interface CurrentRatesSyncStatus {
  last_successful_sync: {
    completed_at: string | null
    records_fetched: number | null
    records_created: number | null
    triggered_by: string | null
  } | null
  last_sync: {
    started_at: string | null
    completed_at: string | null
    status: string | null
    records_fetched: number | null
    error_message: string | null
    triggered_by: string | null
  } | null
  auto_sync: {
    enabled: boolean
    time: string
  }
  total_records: number
  data_range: {
    from: string | null
    to: string | null
  }
  category_counts: Record<string, number>
}

const CurrentRatesDataSyncSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'success' | 'error'>('idle')
  const [syncMessage, setSyncMessage] = useState('')
  const [autoEnabled, setAutoEnabled] = useState(false)
  const [syncTime, setSyncTime] = useState('05:20')

  // Fetch sync status
  const { data: status, isLoading: statusLoading, refetch: refetchStatus } = useQuery<CurrentRatesSyncStatus>({
    queryKey: ['current-rates-sync-status'],
    queryFn: async () => {
      const response = await fetch('/api/sync/current-rates/status', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch status')
      return response.json()
    },
    refetchInterval: syncStatus === 'syncing' ? 3000 : false,
  })

  // Fetch sync logs
  const { data: logs, isLoading: logsLoading } = useQuery<SyncLog[]>({
    queryKey: ['current-rates-sync-logs'],
    queryFn: async () => {
      const response = await fetch('/api/sync/current-rates/logs?limit=5', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    refetchInterval: syncStatus === 'syncing' ? 3000 : false,
  })

  // Update local state when status loads
  React.useEffect(() => {
    if (status?.auto_sync) {
      setAutoEnabled(status.auto_sync.enabled)
      setSyncTime(status.auto_sync.time || '05:20')
    }
    // Check if sync is currently running
    if (status?.last_sync?.status === 'running') {
      setSyncStatus('syncing')
    } else if (syncStatus === 'syncing' && status?.last_sync?.status !== 'running') {
      // Sync completed
      setSyncStatus(status?.last_sync?.status === 'success' ? 'success' : 'error')
      setSyncMessage(status?.last_sync?.status === 'success'
        ? `Synced ${status?.last_sync?.records_fetched || 0} rates`
        : status?.last_sync?.error_message || 'Sync failed')
      setTimeout(() => {
        setSyncStatus('idle')
        setSyncMessage('')
      }, 5000)
      queryClient.invalidateQueries({ queryKey: ['current-rates-sync-status'] })
      queryClient.invalidateQueries({ queryKey: ['current-rates-sync-logs'] })
    }
  }, [status, syncStatus, queryClient])

  // Trigger sync
  const handleSync = async () => {
    setSyncStatus('syncing')
    setSyncMessage('')
    try {
      const response = await fetch('/api/sync/current-rates/sync', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setSyncMessage(data.message || 'Sync started...')
      } else {
        setSyncStatus('error')
        setSyncMessage(data.detail || 'Failed to start sync')
        setTimeout(() => {
          setSyncStatus('idle')
          setSyncMessage('')
        }, 5000)
      }
    } catch {
      setSyncStatus('error')
      setSyncMessage('Failed to start sync')
      setTimeout(() => {
        setSyncStatus('idle')
        setSyncMessage('')
      }, 5000)
    }
  }

  // Update auto sync config
  const handleAutoConfigSave = async () => {
    try {
      const response = await fetch('/api/sync/current-rates/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          enabled: autoEnabled,
          sync_time: syncTime
        })
      })
      if (response.ok) {
        refetchStatus()
      }
    } catch (err) {
      console.error('Failed to update config', err)
    }
  }

  // Cancel running sync
  const handleCancelSync = async () => {
    try {
      const response = await fetch('/api/sync/current-rates/cancel', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setSyncStatus('idle')
        setSyncMessage(data.message || 'Sync cancelled')
        queryClient.invalidateQueries({ queryKey: ['current-rates-sync-status'] })
        queryClient.invalidateQueries({ queryKey: ['current-rates-sync-logs'] })
        setTimeout(() => {
          setSyncMessage('')
        }, 3000)
      }
    } catch {
      console.error('Failed to cancel sync')
    }
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString()
  }

  const formatTrigger = (trigger: string | null) => {
    if (!trigger) return '-'
    if (trigger.startsWith('user:')) return trigger.replace('user:', '')
    if (trigger === 'scheduler') return 'Auto'
    return trigger
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Current Rates Sync (Pickup-V2)</h3>
      <p style={styles.hint}>
        Fetches current rack rates from Newbook for revenue forecast upper bounds.
        Used by Pickup-V2 model for confidence shading.
      </p>

      {statusLoading ? (
        <div style={styles.loading}>Loading sync status...</div>
      ) : (
        <>
          {/* Status summary */}
          <div style={styles.syncStatusRow}>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Total Rates</span>
              <span style={styles.syncStatusValue}>{status?.total_records?.toLocaleString() || 0}</span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Date Range</span>
              <span style={styles.syncStatusValue}>
                {status?.data_range?.from && status?.data_range?.to
                  ? `${status.data_range.from} → ${status.data_range.to}`
                  : 'No data'}
              </span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Last Sync</span>
              <span style={styles.syncStatusValue}>
                {status?.last_successful_sync?.completed_at
                  ? formatDate(status.last_successful_sync.completed_at)
                  : 'Never'}
              </span>
            </div>
            <div style={styles.syncStatusItem}>
              <span style={styles.syncStatusLabel}>Auto Sync</span>
              <span style={status?.auto_sync?.enabled ? styles.statusOk : styles.statusPending}>
                {status?.auto_sync?.enabled ? 'Enabled' : 'Disabled'}
              </span>
            </div>
          </div>

          {/* Category breakdown if data exists */}
          {status?.category_counts && Object.keys(status.category_counts).length > 0 && (
            <div style={{ ...styles.hint, marginTop: spacing.sm }}>
              Categories: {Object.entries(status.category_counts).map(([cat, count]) =>
                `${cat}: ${count} days`
              ).join(', ')}
            </div>
          )}

          {/* Sync controls */}
          <div style={styles.syncControlsSection}>
            {/* Manual sync */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Manual Sync</h4>
              <p style={styles.syncControlHint}>
                Fetch rates for all categories for the next 365 days.
                Takes ~3 minutes per category due to API rate limits.
              </p>
              <div style={{ display: 'flex', gap: spacing.sm }}>
                <button
                  onClick={handleSync}
                  disabled={syncStatus === 'syncing'}
                  style={mergeStyles(
                    buttonStyle('primary'),
                    syncStatus === 'syncing' ? { opacity: 0.7 } : {}
                  )}
                >
                  {syncStatus === 'syncing' ? 'Syncing...' : 'Fetch Current Rates'}
                </button>
                {syncStatus === 'syncing' && (
                  <button
                    onClick={handleCancelSync}
                    style={mergeStyles(buttonStyle('outline'), { borderColor: colors.error, color: colors.error })}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>

            {/* Auto sync config */}
            <div style={styles.syncControlBox}>
              <h4 style={styles.syncControlTitle}>Automatic Sync</h4>
              <p style={styles.syncControlHint}>
                Enable scheduled daily sync. Fetches rates for next 365 days.
              </p>
              <label style={styles.syncCheckboxLabel}>
                <input
                  type="checkbox"
                  checked={autoEnabled}
                  onChange={(e) => setAutoEnabled(e.target.checked)}
                  style={styles.checkbox}
                />
                Enable auto sync
              </label>
              <div style={styles.syncAutoRow}>
                <span style={styles.syncTimeLabel}>Sync at</span>
                <input
                  type="time"
                  value={syncTime}
                  onChange={(e) => setSyncTime(e.target.value)}
                  style={styles.syncTimeInput}
                  disabled={!autoEnabled}
                />
              </div>
              <button
                onClick={handleAutoConfigSave}
                style={buttonStyle('outline')}
              >
                Save Settings
              </button>
            </div>
          </div>

          {/* Sync message */}
          {syncMessage && (
            <div style={{
              ...styles.statusMessage,
              background: syncStatus === 'success' ? colors.successBg :
                         syncStatus === 'error' ? colors.errorBg : colors.background,
              color: syncStatus === 'success' ? colors.success :
                     syncStatus === 'error' ? colors.error : colors.text,
              marginTop: spacing.md,
            }}>
              {syncMessage}
            </div>
          )}

          {/* Recent sync logs */}
          <div style={styles.syncLogsSection}>
            <h4 style={styles.syncLogsTitle}>Recent Syncs</h4>
            {logsLoading ? (
              <div style={styles.loading}>Loading logs...</div>
            ) : logs && logs.length > 0 ? (
              <div style={styles.syncLogsList}>
                {logs.map((log) => (
                  <div key={log.id} style={styles.syncLogItem}>
                    <div style={styles.syncLogMain}>
                      <span style={{
                        ...styles.syncLogStatus,
                        color: log.status === 'success' ? colors.success :
                               log.status === 'running' ? colors.accent :
                               colors.error
                      }}>
                        {log.status === 'running' ? '●' : log.status === 'success' ? '✓' : '✗'}
                      </span>
                      <span style={styles.syncLogDate}>{formatDate(log.started_at)}</span>
                      <span style={styles.syncLogRecords}>
                        {log.records_fetched !== null ? `${log.records_fetched} rates` : ''}
                      </span>
                    </div>
                    <div style={styles.syncLogMeta}>
                      <span style={styles.syncLogTrigger}>{formatTrigger(log.triggered_by)}</span>
                      {log.status === 'running' && (
                        <button
                          onClick={handleCancelSync}
                          style={mergeStyles(buttonStyle('outline', 'small'), { marginLeft: spacing.sm, borderColor: colors.error, color: colors.error })}
                        >
                          Cancel
                        </button>
                      )}
                    </div>
                    {log.error_message && (
                      <div style={styles.syncLogError}>{log.error_message}</div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div style={styles.emptyState}>No sync history yet.</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

const NewbookPage: React.FC = () => {
  const [apiKey, setApiKey] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [region, setRegion] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle')
  const [testMessage, setTestMessage] = useState('')

  // Fetch current settings
  const { data: settings, isLoading } = useQuery({
    queryKey: ['newbook-settings'],
    queryFn: async () => {
      const response = await fetch('/api/config/settings/newbook', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch settings')
      return response.json() as Promise<NewbookSettings>
    },
    staleTime: 30000,
  })

  // Populate form when settings load
  React.useEffect(() => {
    if (settings) {
      setUsername(settings.newbook_username || '')
      setRegion(settings.newbook_region || '')
      // Don't populate password/api_key - they're masked
    }
  }, [settings])

  const handleSave = async () => {
    setSaveStatus('saving')
    try {
      const response = await fetch('/api/config/settings/newbook', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          newbook_api_key: apiKey || undefined,
          newbook_username: username || undefined,
          newbook_password: password || undefined,
          newbook_region: region || undefined,
        })
      })
      if (!response.ok) throw new Error('Failed to save')
      setSaveStatus('success')
      // Clear password fields after save
      setApiKey('')
      setPassword('')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus('idle'), 3000)
    }
  }

  const handleTestConnection = async () => {
    setTestStatus('testing')
    setTestMessage('')
    try {
      const response = await fetch('/api/config/settings/newbook/test', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setTestStatus('success')
        setTestMessage(data.message || 'Connection successful!')
      } else {
        setTestStatus('error')
        setTestMessage(data.detail || 'Connection failed')
      }
    } catch {
      setTestStatus('error')
      setTestMessage('Connection failed')
    }
    setTimeout(() => {
      setTestStatus('idle')
      setTestMessage('')
    }, 5000)
  }

  if (isLoading) {
    return (
      <div style={styles.section}>
        <div style={styles.loading}>Loading settings...</div>
      </div>
    )
  }

  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>Newbook Settings</h2>
      <p style={styles.hint}>Configure your Newbook API connection for hotel data synchronization.</p>

      <div style={styles.apiConfigRow}>
        {/* Left side - API Configuration */}
        <div style={styles.apiConfigLeft}>
          <h3 style={styles.subsectionTitle}>API Configuration</h3>

          <div style={styles.form}>
            <label style={styles.label}>
              <span>API Key</span>
              <div style={styles.inputWithStatus}>
                <input
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder={settings?.newbook_api_key_set ? '••••••••' : 'Enter API key'}
                  style={styles.input}
                />
                {settings?.newbook_api_key_set && (
                  <span style={styles.keyStatus}>Key configured</span>
                )}
              </div>
            </label>

            <label style={styles.label}>
              <span>Username</span>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Newbook account username"
                style={styles.input}
              />
            </label>

            <label style={styles.label}>
              <span>Password</span>
              <div style={styles.inputWithStatus}>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={settings?.newbook_password_set ? '••••••••' : 'Enter password'}
                  style={styles.input}
                />
                {settings?.newbook_password_set && (
                  <span style={styles.keyStatus}>Password configured</span>
                )}
              </div>
            </label>

            <label style={styles.label}>
              <span>Region</span>
              <input
                type="text"
                value={region}
                onChange={(e) => setRegion(e.target.value)}
                placeholder="e.g., uk, au"
                style={styles.input}
              />
            </label>

            <div style={styles.buttonRow}>
              <button
                onClick={handleSave}
                disabled={saveStatus === 'saving'}
                style={mergeStyles(
                  buttonStyle('primary'),
                  saveStatus === 'success' ? { background: colors.success } : {},
                  saveStatus === 'error' ? { background: colors.error } : {}
                )}
              >
                {saveStatus === 'saving' ? 'Saving...' :
                 saveStatus === 'success' ? 'Saved!' :
                 saveStatus === 'error' ? 'Error' : 'Save Settings'}
              </button>
              <button
                onClick={handleTestConnection}
                disabled={testStatus === 'testing'}
                style={buttonStyle('outline')}
              >
                {testStatus === 'testing' ? 'Testing...' : 'Test Connection'}
              </button>
            </div>

            {testMessage && (
              <div style={{
                ...styles.statusMessage,
                background: testStatus === 'success' ? colors.successBg : colors.errorBg,
                color: testStatus === 'success' ? colors.success : colors.error,
              }}>
                {testMessage}
              </div>
            )}
          </div>
        </div>

        {/* Right side - Connection Status */}
        <div style={styles.apiConfigRight}>
          <h3 style={styles.subsectionTitle}>Connection Status</h3>
          <div style={styles.statusGridVertical}>
            <div style={styles.statusItem}>
              <span style={styles.statusLabel}>API Key</span>
              <span style={settings?.newbook_api_key_set ? styles.statusOk : styles.statusPending}>
                {settings?.newbook_api_key_set ? 'Configured' : 'Not set'}
              </span>
            </div>
            <div style={styles.statusItem}>
              <span style={styles.statusLabel}>Username</span>
              <span style={settings?.newbook_username ? styles.statusOk : styles.statusPending}>
                {settings?.newbook_username || 'Not set'}
              </span>
            </div>
            <div style={styles.statusItem}>
              <span style={styles.statusLabel}>Password</span>
              <span style={settings?.newbook_password_set ? styles.statusOk : styles.statusPending}>
                {settings?.newbook_password_set ? 'Configured' : 'Not set'}
              </span>
            </div>
            <div style={styles.statusItem}>
              <span style={styles.statusLabel}>Region</span>
              <span style={settings?.newbook_region ? styles.statusOk : styles.statusPending}>
                {settings?.newbook_region || 'Not set'}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div style={styles.divider} />

      <RoomCategoriesSection />

      <div style={styles.divider} />

      <GLRevenueMappingSection />

      <div style={styles.divider} />

      <BookingsDataSyncSection />

      <div style={styles.divider} />

      <OccupancyDataSyncSection />

      <div style={styles.divider} />

      <EarnedRevenueDataSyncSection />

      <div style={styles.divider} />

      <CurrentRatesDataSyncSection />
    </div>
  )
}

// ============================================
// RESOS SETTINGS PAGE
// ============================================

interface ResosSettings {
  resos_api_key: string | null
  resos_api_key_set: boolean
}

interface ResosCustomField {
  id: string
  name: string
  type: string
  values?: string[]
}

interface CustomFieldMapping {
  custom_field_id: string
  mapping_type: string
}

interface ResosOpeningHour {
  id: string
  name: string
  start_time: string
  end_time: string
}

interface OpeningHourMapping {
  opening_hour_id: string
  period_type: string
  display_name?: string
}

interface ManualBreakfastPeriod {
  day_of_week: number
  start_time: string
  end_time: string
  is_active: boolean
}

const ResosPage: React.FC = () => {
  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>Resos Settings</h2>
      <p style={styles.hint}>Configure your Resos API connection and sync settings for restaurant reservation management.</p>

      <ResosAPIConfigSection />

      <div style={styles.divider} />

      <ResosCustomFieldMappingSection />

      <div style={styles.divider} />

      <ResosOpeningHoursMappingSection />

      <div style={styles.divider} />

      <ResosManualBreakfastSection />

      <div style={styles.divider} />

      <ResosAverageSpendSection />

      <div style={styles.divider} />

      <ResosSyncConfigSection />
    </div>
  )
}

// ============================================
// RESOS API CONFIGURATION SECTION
// ============================================

const ResosAPIConfigSection: React.FC = () => {
  const [apiKey, setApiKey] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [testStatus, setTestStatus] = useState<'idle' | 'testing' | 'success' | 'error'>('idle')
  const [testMessage, setTestMessage] = useState('')

  const { data: settings, isLoading } = useQuery({
    queryKey: ['resos-settings'],
    queryFn: async () => {
      const response = await fetch('/api/config/settings/resos', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch settings')
      return response.json() as Promise<ResosSettings>
    },
    staleTime: 30000,
  })

  const handleSave = async () => {
    setSaveStatus('saving')
    try {
      const response = await fetch('/api/config/settings/resos', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          resos_api_key: apiKey || undefined,
        })
      })
      if (!response.ok) throw new Error('Failed to save')
      setSaveStatus('success')
      setApiKey('')
      setTimeout(() => setSaveStatus('idle'), 3000)
    } catch {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus('idle'), 3000)
    }
  }

  const handleTestConnection = async () => {
    setTestStatus('testing')
    setTestMessage('')
    try {
      const response = await fetch('/api/config/settings/resos/test', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setTestStatus('success')
        setTestMessage(data.message || 'Connection successful!')
      } else {
        setTestStatus('error')
        setTestMessage(data.detail || 'Connection failed')
      }
    } catch {
      setTestStatus('error')
      setTestMessage('Connection failed')
    }
    setTimeout(() => {
      setTestStatus('idle')
      setTestMessage('')
    }, 5000)
  }

  if (isLoading) {
    return <div style={styles.loading}>Loading settings...</div>
  }

  return (
    <div style={styles.apiConfigRow}>
      <div style={styles.apiConfigLeft}>
        <h3 style={styles.subsectionTitle}>API Configuration</h3>

        <div style={styles.form}>
          <label style={styles.label}>
            <span>API Key</span>
            <div style={styles.inputWithStatus}>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={settings?.resos_api_key_set ? '••••••••' : 'Enter API key'}
                style={styles.input}
              />
              {settings?.resos_api_key_set && (
                <span style={styles.keyStatus}>Key configured</span>
              )}
            </div>
          </label>

          <div style={styles.buttonRow}>
            <button
              onClick={handleSave}
              disabled={saveStatus === 'saving'}
              style={mergeStyles(
                buttonStyle('primary'),
                saveStatus === 'success' ? { background: colors.success } : {},
                saveStatus === 'error' ? { background: colors.error } : {}
              )}
            >
              {saveStatus === 'saving' ? 'Saving...' :
               saveStatus === 'success' ? 'Saved!' :
               saveStatus === 'error' ? 'Error' : 'Save Settings'}
            </button>
            <button
              onClick={handleTestConnection}
              disabled={testStatus === 'testing'}
              style={buttonStyle('outline')}
            >
              {testStatus === 'testing' ? 'Testing...' : 'Test Connection'}
            </button>
          </div>

          {testMessage && (
            <div style={{
              ...styles.statusMessage,
              background: testStatus === 'success' ? colors.successBg : colors.errorBg,
              color: testStatus === 'success' ? colors.success : colors.error,
            }}>
              {testMessage}
            </div>
          )}
        </div>
      </div>

      <div style={styles.apiConfigRight}>
        <h3 style={styles.subsectionTitle}>Connection Status</h3>
        <div style={styles.statusGridVertical}>
          <div style={styles.statusItem}>
            <span style={styles.statusLabel}>API Key</span>
            <span style={settings?.resos_api_key_set ? styles.statusOk : styles.statusPending}>
              {settings?.resos_api_key_set ? 'Configured' : 'Not set'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ============================================
// RESOS CUSTOM FIELD MAPPING SECTION
// ============================================

const ResosCustomFieldMappingSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [fetchStatus, setFetchStatus] = useState<'idle' | 'fetching' | 'success' | 'error'>('idle')
  const [fetchMessage, setFetchMessage] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [customFieldMapping, setCustomFieldMapping] = useState<Record<string, string>>({})

  const { data: customFields, isLoading } = useQuery<ResosCustomField[]>({
    queryKey: ['resos-custom-fields-list'],
    queryFn: async () => {
      const response = await fetch('/api/resos/custom-fields', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  const { data: existingMappings } = useQuery<CustomFieldMapping[]>({
    queryKey: ['resos-custom-field-mapping'],
    queryFn: async () => {
      const response = await fetch('/api/resos/custom-field-mapping', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  React.useEffect(() => {
    if (existingMappings) {
      // Convert from array to simple mapping object: {mapping_type: field_id}
      const mappingObj: Record<string, string> = {}
      existingMappings.forEach(m => {
        mappingObj[m.mapping_type] = m.custom_field_id
      })
      setCustomFieldMapping(mappingObj)
    }
  }, [existingMappings])

  const handleFetch = async () => {
    setFetchStatus('fetching')
    setFetchMessage('')
    try {
      const response = await fetch('/api/resos/custom-fields', {
        method: 'GET',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setFetchStatus('success')
        setFetchMessage('Custom fields fetched successfully')
        queryClient.invalidateQueries({ queryKey: ['resos-custom-fields-list'] })
      } else {
        setFetchStatus('error')
        setFetchMessage(data.detail || 'Failed to fetch custom fields')
      }
    } catch {
      setFetchStatus('error')
      setFetchMessage('Failed to fetch custom fields')
    }
    setTimeout(() => {
      setFetchStatus('idle')
      setFetchMessage('')
    }, 5000)
  }

  const handleSaveMappings = async () => {
    setSaveStatus('saving')
    setSaveMessage('')
    try {
      // Convert mapping object back to array format for API
      const mappingsArray = Object.entries(customFieldMapping)
        .filter(([_, fieldId]) => fieldId) // Only include non-empty mappings
        .map(([mappingType, fieldId]) => ({
          custom_field_id: fieldId,
          mapping_type: mappingType
        }))

      const response = await fetch('/api/resos/custom-field-mapping', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ mappings: mappingsArray })
      })
      if (response.ok) {
        setSaveStatus('success')
        setSaveMessage('Mappings saved successfully')
        queryClient.invalidateQueries({ queryKey: ['resos-custom-field-mapping'] })
      } else {
        const data = await response.json()
        setSaveStatus('error')
        setSaveMessage(data.detail || 'Failed to save mappings')
      }
    } catch {
      setSaveStatus('error')
      setSaveMessage('Failed to save mappings')
    }
    setTimeout(() => {
      setSaveStatus('idle')
      setSaveMessage('')
    }, 5000)
  }

  // Define predefined mapping targets (like kitchen app)
  const mappingTargets = [
    { key: 'booking_number', label: 'Hotel Booking #', hint: 'Hotel booking reference number from Resos custom field' },
    { key: 'hotel_guest', label: 'Hotel Guest', hint: 'Yes/No field indicating if diner is a hotel guest' },
    { key: 'dbb', label: 'DBB (Dinner B&B)', hint: 'Yes/No field indicating Dinner Bed & Breakfast package guests' },
    { key: 'package', label: 'Package', hint: 'Yes/No field indicating package deal bookings' },
    { key: 'group_exclude', label: 'Group/Exclude', hint: 'Free-text field for group codes and exclusions (e.g., "#12345,NOT-#56789")' },
    { key: 'allergies', label: 'Allergies', hint: 'Multi-select or text field with allergy information' },
  ]

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Custom Field Mapping</h3>
      <p style={styles.hint}>
        Map Resos custom fields to booking data fields. Fetch custom fields first, then select which Resos field maps to each target.
      </p>

      <div style={styles.buttonRow}>
        <button
          onClick={handleFetch}
          disabled={fetchStatus === 'fetching'}
          style={mergeStyles(
            buttonStyle('outline'),
            fetchStatus === 'success' ? { borderColor: colors.success, color: colors.success } : {},
            fetchStatus === 'error' ? { borderColor: colors.error, color: colors.error } : {}
          )}
        >
          {fetchStatus === 'fetching' ? 'Fetching...' : 'Fetch Custom Fields'}
        </button>
        {customFields && customFields.length > 0 && (
          <span style={styles.glAccountCount}>{customFields.length} fields loaded</span>
        )}
      </div>

      {fetchMessage && (
        <div style={{
          ...styles.statusMessage,
          background: fetchStatus === 'success' ? colors.successBg : colors.errorBg,
          color: fetchStatus === 'success' ? colors.success : colors.error,
          marginTop: spacing.sm,
        }}>
          {fetchMessage}
        </div>
      )}

      {isLoading ? (
        <div style={styles.loading}>Loading custom fields...</div>
      ) : customFields && customFields.length > 0 ? (
        <>
          <div style={{ marginTop: spacing.lg, display: 'flex', flexDirection: 'column', gap: spacing.md }}>
            {mappingTargets.map((target) => (
              <div key={target.key} style={{
                display: 'flex',
                flexDirection: 'column',
                gap: spacing.xs,
              }}>
                <label style={{
                  fontWeight: typography.medium,
                  color: colors.text,
                  fontSize: typography.sm
                }}>
                  {target.label}
                </label>
                <select
                  value={customFieldMapping[target.key] || ''}
                  onChange={(e) => setCustomFieldMapping({
                    ...customFieldMapping,
                    [target.key]: e.target.value
                  })}
                  style={styles.select}
                >
                  <option value="">-- Select Field --</option>
                  {customFields.map((field) => (
                    <option key={field.id} value={field.id}>
                      {field.name} ({field.type})
                    </option>
                  ))}
                </select>
                <small style={{
                  ...styles.hint,
                  marginTop: 0,
                  fontSize: typography.xs
                }}>
                  {target.hint}
                </small>
              </div>
            ))}
          </div>

          <div style={{ ...styles.buttonRow, marginTop: spacing.lg }}>
            <button
              onClick={handleSaveMappings}
              disabled={saveStatus === 'saving'}
              style={mergeStyles(
                buttonStyle('primary'),
                saveStatus === 'success' ? { background: colors.success } : {},
                saveStatus === 'error' ? { background: colors.error } : {}
              )}
            >
              {saveStatus === 'saving' ? 'Saving...' :
               saveStatus === 'success' ? 'Saved!' :
               saveStatus === 'error' ? 'Error' : 'Save Mappings'}
            </button>
          </div>

          {saveMessage && (
            <div style={{
              ...styles.statusMessage,
              background: saveStatus === 'success' ? colors.successBg : colors.errorBg,
              color: saveStatus === 'success' ? colors.success : colors.error,
              marginTop: spacing.sm,
            }}>
              {saveMessage}
            </div>
          )}
        </>
      ) : (
        <div style={styles.emptyState}>
          No custom fields loaded. Click "Fetch Custom Fields" to load from Resos.
        </div>
      )}
    </div>
  )
}

// ============================================
// RESOS OPENING HOURS MAPPING SECTION
// ============================================

const ResosOpeningHoursMappingSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [fetchStatus, setFetchStatus] = useState<'idle' | 'fetching' | 'success' | 'error'>('idle')
  const [fetchMessage, setFetchMessage] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [mappings, setMappings] = useState<Record<string, OpeningHourMapping>>({})

  const { data: openingHours, isLoading } = useQuery<ResosOpeningHour[]>({
    queryKey: ['resos-opening-hours-list'],
    queryFn: async () => {
      const response = await fetch('/api/resos/opening-hours', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  const { data: existingMappings } = useQuery<OpeningHourMapping[]>({
    queryKey: ['resos-opening-hours-mapping'],
    queryFn: async () => {
      const response = await fetch('/api/resos/opening-hours-mapping', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  React.useEffect(() => {
    if (existingMappings) {
      const mappingObj: Record<string, OpeningHourMapping> = {}
      existingMappings.forEach(m => {
        mappingObj[m.opening_hour_id] = m
      })
      setMappings(mappingObj)
    }
  }, [existingMappings])

  const handleFetch = async () => {
    setFetchStatus('fetching')
    setFetchMessage('')
    try {
      const response = await fetch('/api/resos/opening-hours', {
        method: 'GET',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      const data = await response.json()
      if (response.ok) {
        setFetchStatus('success')
        setFetchMessage('Opening hours fetched successfully')
        queryClient.invalidateQueries({ queryKey: ['resos-opening-hours-list'] })
      } else {
        setFetchStatus('error')
        setFetchMessage(data.detail || 'Failed to fetch opening hours')
      }
    } catch {
      setFetchStatus('error')
      setFetchMessage('Failed to fetch opening hours')
    }
    setTimeout(() => {
      setFetchStatus('idle')
      setFetchMessage('')
    }, 5000)
  }

  const handleMappingChange = (hourId: string, periodType: string) => {
    setMappings(prev => ({
      ...prev,
      [hourId]: {
        opening_hour_id: hourId,
        period_type: periodType,
        display_name: prev[hourId]?.display_name
      }
    }))
  }

  const handleDisplayNameChange = (hourId: string, displayName: string) => {
    setMappings(prev => ({
      ...prev,
      [hourId]: {
        ...prev[hourId],
        opening_hour_id: hourId,
        period_type: prev[hourId]?.period_type || 'ignore',
        display_name: displayName || undefined
      }
    }))
  }

  const handleSaveMappings = async () => {
    setSaveStatus('saving')
    setSaveMessage('')
    try {
      const mappingsArray = Object.values(mappings).filter(m => m.period_type !== 'ignore')
      const response = await fetch('/api/resos/opening-hours-mapping', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ mappings: mappingsArray })
      })
      if (response.ok) {
        setSaveStatus('success')
        setSaveMessage('Mappings saved successfully')
        queryClient.invalidateQueries({ queryKey: ['resos-opening-hours-mapping'] })
      } else {
        const data = await response.json()
        setSaveStatus('error')
        setSaveMessage(data.detail || 'Failed to save mappings')
      }
    } catch {
      setSaveStatus('error')
      setSaveMessage('Failed to save mappings')
    }
    setTimeout(() => {
      setSaveStatus('idle')
      setSaveMessage('')
    }, 5000)
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Opening Hours Mapping</h3>
      <p style={styles.hint}>
        Map Resos opening hours to meal periods. Fetch opening hours first, then assign period types.
      </p>

      <div style={styles.buttonRow}>
        <button
          onClick={handleFetch}
          disabled={fetchStatus === 'fetching'}
          style={mergeStyles(
            buttonStyle('outline'),
            fetchStatus === 'success' ? { borderColor: colors.success, color: colors.success } : {},
            fetchStatus === 'error' ? { borderColor: colors.error, color: colors.error } : {}
          )}
        >
          {fetchStatus === 'fetching' ? 'Fetching...' : 'Fetch Opening Hours'}
        </button>
        {openingHours && openingHours.length > 0 && (
          <span style={styles.glAccountCount}>{openingHours.length} hours loaded</span>
        )}
      </div>

      {fetchMessage && (
        <div style={{
          ...styles.statusMessage,
          background: fetchStatus === 'success' ? colors.successBg : colors.errorBg,
          color: fetchStatus === 'success' ? colors.success : colors.error,
          marginTop: spacing.sm,
        }}>
          {fetchMessage}
        </div>
      )}

      {isLoading ? (
        <div style={styles.loading}>Loading opening hours...</div>
      ) : openingHours && openingHours.length > 0 ? (
        <>
          <div style={{ marginTop: spacing.lg }}>
            {openingHours.map((hour) => {
              const mapping = mappings[hour.id]
              const periodType = mapping?.period_type || 'ignore'

              return (
                <div key={hour.id} style={{
                  display: 'grid',
                  gridTemplateColumns: '2fr 2fr 2fr',
                  gap: spacing.md,
                  marginBottom: spacing.md,
                  alignItems: 'center',
                  padding: spacing.sm,
                  background: colors.background,
                  borderRadius: radius.md,
                  border: `1px solid ${colors.borderLight}`,
                }}>
                  <div>
                    <div style={{ fontWeight: typography.medium, color: colors.text }}>
                      {hour.name}
                    </div>
                    <div style={{ fontSize: typography.xs, color: colors.textMuted }}>
                      {hour.start_time} - {hour.end_time}
                    </div>
                  </div>
                  <select
                    value={periodType}
                    onChange={(e) => handleMappingChange(hour.id, e.target.value)}
                    style={styles.select}
                  >
                    <option value="ignore">Ignore</option>
                    <option value="breakfast">Breakfast</option>
                    <option value="lunch">Lunch</option>
                    <option value="afternoon">Afternoon</option>
                    <option value="dinner">Dinner</option>
                    <option value="other">Other</option>
                  </select>
                  <input
                    type="text"
                    value={mapping?.display_name || ''}
                    onChange={(e) => handleDisplayNameChange(hour.id, e.target.value)}
                    placeholder="Display name (optional)"
                    style={styles.input}
                    disabled={periodType === 'ignore'}
                  />
                </div>
              )
            })}
          </div>

          <div style={styles.buttonRow}>
            <button
              onClick={handleSaveMappings}
              disabled={saveStatus === 'saving'}
              style={mergeStyles(
                buttonStyle('primary'),
                saveStatus === 'success' ? { background: colors.success } : {},
                saveStatus === 'error' ? { background: colors.error } : {}
              )}
            >
              {saveStatus === 'saving' ? 'Saving...' :
               saveStatus === 'success' ? 'Saved!' :
               saveStatus === 'error' ? 'Error' : 'Save Mappings'}
            </button>
          </div>

          {saveMessage && (
            <div style={{
              ...styles.statusMessage,
              background: saveStatus === 'success' ? colors.successBg : colors.errorBg,
              color: saveStatus === 'success' ? colors.success : colors.error,
              marginTop: spacing.sm,
            }}>
              {saveMessage}
            </div>
          )}
        </>
      ) : (
        <div style={styles.emptyState}>
          No opening hours loaded. Click "Fetch Opening Hours" to load from Resos.
        </div>
      )}
    </div>
  )
}

// ============================================
// RESOS MANUAL BREAKFAST CONFIGURATION SECTION
// ============================================

const ResosManualBreakfastSection: React.FC = () => {
  const [enabled, setEnabled] = useState(false)
  const [periods, setPeriods] = useState<ManualBreakfastPeriod[]>([
    { day_of_week: 1, start_time: '07:00', end_time: '10:00', is_active: true },
    { day_of_week: 2, start_time: '07:00', end_time: '10:00', is_active: true },
    { day_of_week: 3, start_time: '07:00', end_time: '10:00', is_active: true },
    { day_of_week: 4, start_time: '07:00', end_time: '10:00', is_active: true },
    { day_of_week: 5, start_time: '07:00', end_time: '10:00', is_active: true },
    { day_of_week: 6, start_time: '08:00', end_time: '11:00', is_active: true },
    { day_of_week: 0, start_time: '08:00', end_time: '11:00', is_active: true },
  ])
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')

  const { data: existingPeriods, isLoading } = useQuery<{ enabled: boolean; periods: ManualBreakfastPeriod[] }>({
    queryKey: ['resos-manual-breakfast'],
    queryFn: async () => {
      const response = await fetch('/api/resos/manual-breakfast-periods', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return { enabled: false, periods: [] }
      return response.json()
    },
  })

  React.useEffect(() => {
    if (existingPeriods && existingPeriods.periods.length > 0) {
      setEnabled(existingPeriods.enabled)
      setPeriods(existingPeriods.periods)
    }
  }, [existingPeriods])

  const dayNames = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

  const handlePeriodChange = (index: number, field: keyof ManualBreakfastPeriod, value: string | boolean) => {
    const newPeriods = [...periods]
    newPeriods[index] = { ...newPeriods[index], [field]: value }
    setPeriods(newPeriods)
  }

  const handleSave = async () => {
    setSaveStatus('saving')
    setSaveMessage('')
    try {
      const response = await fetch('/api/resos/manual-breakfast-periods', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ enabled, periods })
      })
      if (response.ok) {
        setSaveStatus('success')
        setSaveMessage('Manual breakfast configuration saved successfully')
      } else {
        const data = await response.json()
        setSaveStatus('error')
        setSaveMessage(data.detail || 'Failed to save configuration')
      }
    } catch {
      setSaveStatus('error')
      setSaveMessage('Failed to save configuration')
    }
    setTimeout(() => {
      setSaveStatus('idle')
      setSaveMessage('')
    }, 5000)
  }

  if (isLoading) {
    return <div style={styles.loading}>Loading manual breakfast configuration...</div>
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Manual Breakfast Configuration</h3>
      <p style={styles.hint}>
        Configure breakfast periods manually instead of using Resos opening hours. Useful for custom scheduling.
      </p>

      <label style={{
        display: 'flex',
        alignItems: 'center',
        gap: spacing.sm,
        marginBottom: spacing.lg,
        cursor: 'pointer',
      }}>
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
          style={styles.checkbox}
        />
        <span style={{ fontWeight: typography.medium, color: colors.text }}>
          Enable manual breakfast configuration
        </span>
      </label>

      {enabled && (
        <>
          <div style={{ marginBottom: spacing.lg }}>
            {periods.map((period, index) => (
              <div key={period.day_of_week} style={{
                display: 'grid',
                gridTemplateColumns: '150px 120px 120px 100px',
                gap: spacing.md,
                marginBottom: spacing.sm,
                alignItems: 'center',
                padding: spacing.sm,
                background: colors.background,
                borderRadius: radius.md,
                border: `1px solid ${colors.borderLight}`,
              }}>
                <div style={{ fontWeight: typography.medium, color: colors.text }}>
                  {dayNames[period.day_of_week]}
                </div>
                <input
                  type="time"
                  value={period.start_time}
                  onChange={(e) => handlePeriodChange(index, 'start_time', e.target.value)}
                  style={styles.input}
                  disabled={!period.is_active}
                />
                <input
                  type="time"
                  value={period.end_time}
                  onChange={(e) => handlePeriodChange(index, 'end_time', e.target.value)}
                  style={styles.input}
                  disabled={!period.is_active}
                />
                <label style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: spacing.xs,
                  cursor: 'pointer',
                }}>
                  <input
                    type="checkbox"
                    checked={period.is_active}
                    onChange={(e) => handlePeriodChange(index, 'is_active', e.target.checked)}
                    style={styles.checkbox}
                  />
                  <span style={{ fontSize: typography.sm, color: colors.text }}>Active</span>
                </label>
              </div>
            ))}
          </div>

          <div style={styles.buttonRow}>
            <button
              onClick={handleSave}
              disabled={saveStatus === 'saving'}
              style={mergeStyles(
                buttonStyle('primary'),
                saveStatus === 'success' ? { background: colors.success } : {},
                saveStatus === 'error' ? { background: colors.error } : {}
              )}
            >
              {saveStatus === 'saving' ? 'Saving...' :
               saveStatus === 'success' ? 'Saved!' :
               saveStatus === 'error' ? 'Error' : 'Save Configuration'}
            </button>
          </div>

          {saveMessage && (
            <div style={{
              ...styles.statusMessage,
              background: saveStatus === 'success' ? colors.successBg : colors.errorBg,
              color: saveStatus === 'success' ? colors.success : colors.error,
              marginTop: spacing.sm,
            }}>
              {saveMessage}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// RESOS AVERAGE SPEND CONFIGURATION SECTION
// ============================================

const ResosAverageSpendSection: React.FC = () => {
  const queryClient = useQueryClient()
  const [breakfastFoodSpend, setBreakfastFoodSpend] = useState('')
  const [breakfastDrinksSpend, setBreakfastDrinksSpend] = useState('')
  const [lunchFoodSpend, setLunchFoodSpend] = useState('')
  const [lunchDrinksSpend, setLunchDrinksSpend] = useState('')
  const [dinnerFoodSpend, setDinnerFoodSpend] = useState('')
  const [dinnerDrinksSpend, setDinnerDrinksSpend] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')

  const { data: spendSettings, isLoading } = useQuery({
    queryKey: ['resos-average-spend'],
    queryFn: async () => {
      const response = await fetch('/api/resos/average-spend', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return null
      return response.json()
    },
  })

  // Update local state when settings load
  React.useEffect(() => {
    if (spendSettings) {
      setBreakfastFoodSpend(spendSettings.breakfast_food_spend?.toString() || '')
      setBreakfastDrinksSpend(spendSettings.breakfast_drinks_spend?.toString() || '')
      setLunchFoodSpend(spendSettings.lunch_food_spend?.toString() || '')
      setLunchDrinksSpend(spendSettings.lunch_drinks_spend?.toString() || '')
      setDinnerFoodSpend(spendSettings.dinner_food_spend?.toString() || '')
      setDinnerDrinksSpend(spendSettings.dinner_drinks_spend?.toString() || '')
    }
  }, [spendSettings])

  const handleSave = async () => {
    setSaveStatus('saving')
    setSaveMessage('')
    try {
      const response = await fetch('/api/resos/average-spend', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          breakfast_food_spend: parseFloat(breakfastFoodSpend) || 0,
          breakfast_drinks_spend: parseFloat(breakfastDrinksSpend) || 0,
          lunch_food_spend: parseFloat(lunchFoodSpend) || 0,
          lunch_drinks_spend: parseFloat(lunchDrinksSpend) || 0,
          dinner_food_spend: parseFloat(dinnerFoodSpend) || 0,
          dinner_drinks_spend: parseFloat(dinnerDrinksSpend) || 0
        })
      })
      if (response.ok) {
        setSaveStatus('success')
        setSaveMessage('Average spend settings saved successfully')
        queryClient.invalidateQueries({ queryKey: ['resos-average-spend'] })
      } else {
        const data = await response.json()
        setSaveStatus('error')
        setSaveMessage(data.detail || 'Failed to save settings')
      }
    } catch {
      setSaveStatus('error')
      setSaveMessage('Failed to save settings')
    }
    setTimeout(() => {
      setSaveStatus('idle')
      setSaveMessage('')
    }, 3000)
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Average Spend per Cover (Gross inc VAT)</h3>
      <p style={styles.hint}>
        Configure average spend values per cover for revenue forecasting. Enter gross amounts (including VAT) - the system will calculate net revenue at 20% VAT automatically. These are interim values until till integration provides live data.
      </p>

      {isLoading ? (
        <div style={styles.loading}>Loading settings...</div>
      ) : (
        <>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: spacing.lg,
            marginBottom: spacing.lg,
          }}>
            {/* Breakfast Section */}
            <div style={{
              padding: spacing.md,
              background: colors.background,
              borderRadius: radius.md,
              border: `1px solid ${colors.borderLight}`,
            }}>
              <h4 style={{ margin: 0, marginBottom: spacing.md, fontSize: typography.base, fontWeight: typography.medium }}>
                Breakfast
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
                <label style={styles.label}>
                  <span>Food Spend (£)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={breakfastFoodSpend}
                    onChange={(e) => setBreakfastFoodSpend(e.target.value)}
                    placeholder="e.g. 15.00"
                    style={styles.input}
                  />
                </label>
                <label style={styles.label}>
                  <span>Drinks Spend (£)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={breakfastDrinksSpend}
                    onChange={(e) => setBreakfastDrinksSpend(e.target.value)}
                    placeholder="e.g. 5.00"
                    style={styles.input}
                  />
                </label>
              </div>
            </div>

            {/* Lunch Section */}
            <div style={{
              padding: spacing.md,
              background: colors.background,
              borderRadius: radius.md,
              border: `1px solid ${colors.borderLight}`,
            }}>
              <h4 style={{ margin: 0, marginBottom: spacing.md, fontSize: typography.base, fontWeight: typography.medium }}>
                Lunch
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
                <label style={styles.label}>
                  <span>Food Spend (£)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={lunchFoodSpend}
                    onChange={(e) => setLunchFoodSpend(e.target.value)}
                    placeholder="e.g. 25.00"
                    style={styles.input}
                  />
                </label>
                <label style={styles.label}>
                  <span>Drinks Spend (£)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={lunchDrinksSpend}
                    onChange={(e) => setLunchDrinksSpend(e.target.value)}
                    placeholder="e.g. 12.00"
                    style={styles.input}
                  />
                </label>
              </div>
            </div>

            {/* Dinner Section */}
            <div style={{
              padding: spacing.md,
              background: colors.background,
              borderRadius: radius.md,
              border: `1px solid ${colors.borderLight}`,
            }}>
              <h4 style={{ margin: 0, marginBottom: spacing.md, fontSize: typography.base, fontWeight: typography.medium }}>
                Dinner
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: spacing.sm }}>
                <label style={styles.label}>
                  <span>Food Spend (£)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={dinnerFoodSpend}
                    onChange={(e) => setDinnerFoodSpend(e.target.value)}
                    placeholder="e.g. 45.00"
                    style={styles.input}
                  />
                </label>
                <label style={styles.label}>
                  <span>Drinks Spend (£)</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    value={dinnerDrinksSpend}
                    onChange={(e) => setDinnerDrinksSpend(e.target.value)}
                    placeholder="e.g. 20.00"
                    style={styles.input}
                  />
                </label>
              </div>
            </div>
          </div>

          <div style={styles.buttonRow}>
            <button
              onClick={handleSave}
              disabled={saveStatus === 'saving'}
              style={mergeStyles(
                buttonStyle('primary'),
                saveStatus === 'success' ? { background: colors.success } : {},
                saveStatus === 'error' ? { background: colors.error } : {}
              )}
            >
              {saveStatus === 'saving' ? 'Saving...' :
               saveStatus === 'success' ? 'Saved!' :
               saveStatus === 'error' ? 'Error' : 'Save Settings'}
            </button>
          </div>

          {saveMessage && (
            <div style={{
              ...styles.statusMessage,
              background: saveStatus === 'success' ? colors.successBg : colors.errorBg,
              color: saveStatus === 'success' ? colors.success : colors.error,
              marginTop: spacing.sm,
            }}>
              {saveMessage}
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ============================================
// RESOS SYNC CONFIGURATION SECTION
// ============================================

const ResosSyncConfigSection: React.FC = () => {
  const [autoSyncEnabled, setAutoSyncEnabled] = useState(false)
  const [syncTime, setSyncTime] = useState('03:00')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [saveMessage, setSaveMessage] = useState('')
  const [syncStatus, setSyncStatus] = useState<'idle' | 'syncing' | 'success' | 'error'>('idle')
  const [syncMessage, setSyncMessage] = useState('')

  const { data: syncConfig, isLoading: configLoading } = useQuery({
    queryKey: ['resos-sync-config'],
    queryFn: async () => {
      const response = await fetch('/api/sync/resos-bookings/config', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return null
      return response.json()
    },
  })

  const { data: lastSyncStatus, refetch: refetchStatus } = useQuery<SyncStatus>({
    queryKey: ['resos-sync-status'],
    queryFn: async () => {
      const response = await fetch('/api/sync/resos-bookings/status', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return {}
      return response.json()
    },
    refetchInterval: 30000,
  })

  React.useEffect(() => {
    if (syncConfig) {
      setAutoSyncEnabled(syncConfig.auto_sync_enabled || false)
      setSyncTime(syncConfig.sync_time || '03:00')
    }
  }, [syncConfig])

  React.useEffect(() => {
    const today = new Date()
    const sevenDaysAgo = new Date(today)
    sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7)

    setFromDate(sevenDaysAgo.toISOString().split('T')[0])
    setToDate(today.toISOString().split('T')[0])
  }, [])

  const handleSaveConfig = async () => {
    setSaveStatus('saving')
    setSaveMessage('')
    try {
      const response = await fetch('/api/sync/resos-bookings/config', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({
          auto_sync_enabled: autoSyncEnabled,
          sync_time: syncTime
        })
      })
      if (response.ok) {
        setSaveStatus('success')
        setSaveMessage('Sync configuration saved successfully')
      } else {
        const data = await response.json()
        setSaveStatus('error')
        setSaveMessage(data.detail || 'Failed to save configuration')
      }
    } catch {
      setSaveStatus('error')
      setSaveMessage('Failed to save configuration')
    }
    setTimeout(() => {
      setSaveStatus('idle')
      setSaveMessage('')
    }, 5000)
  }

  const handleTriggerSync = async () => {
    setSyncStatus('syncing')
    setSyncMessage('')
    try {
      // Build query params with from_date and to_date
      const params = new URLSearchParams()
      if (fromDate) params.append('from_date', fromDate)
      if (toDate) params.append('to_date', toDate)

      const response = await fetch(`/api/sync/resos-bookings/sync?${params.toString()}`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('token')}`
        }
      })
      const data = await response.json()
      if (response.ok) {
        setSyncStatus('success')
        setSyncMessage(data.message || 'Sync triggered successfully')
        refetchStatus()
      } else {
        setSyncStatus('error')
        setSyncMessage(data.detail || 'Failed to trigger sync')
      }
    } catch {
      setSyncStatus('error')
      setSyncMessage('Failed to trigger sync')
    }
    setTimeout(() => {
      setSyncStatus('idle')
      setSyncMessage('')
    }, 5000)
  }

  if (configLoading) {
    return <div style={styles.loading}>Loading sync configuration...</div>
  }

  return (
    <div style={styles.subsection}>
      <h3 style={styles.subsectionTitle}>Sync Configuration</h3>
      <p style={styles.hint}>
        Configure automatic synchronization or trigger manual syncs of booking data from Resos.
      </p>

      <div style={{ marginBottom: spacing.lg }}>
        <h4 style={{ ...styles.subsectionTitle, fontSize: typography.base, marginBottom: spacing.md }}>
          Automatic Sync
        </h4>

        <label style={{
          display: 'flex',
          alignItems: 'center',
          gap: spacing.sm,
          marginBottom: spacing.md,
          cursor: 'pointer',
        }}>
          <input
            type="checkbox"
            checked={autoSyncEnabled}
            onChange={(e) => setAutoSyncEnabled(e.target.checked)}
            style={styles.checkbox}
          />
          <span style={{ fontWeight: typography.medium, color: colors.text }}>
            Enable automatic sync
          </span>
        </label>

        {autoSyncEnabled && (
          <label style={styles.label}>
            <span>Sync Time (HH:MM)</span>
            <input
              type="time"
              value={syncTime}
              onChange={(e) => setSyncTime(e.target.value)}
              style={{ ...styles.input, maxWidth: '200px' }}
            />
          </label>
        )}

        <div style={styles.buttonRow}>
          <button
            onClick={handleSaveConfig}
            disabled={saveStatus === 'saving'}
            style={mergeStyles(
              buttonStyle('primary'),
              saveStatus === 'success' ? { background: colors.success } : {},
              saveStatus === 'error' ? { background: colors.error } : {}
            )}
          >
            {saveStatus === 'saving' ? 'Saving...' :
             saveStatus === 'success' ? 'Saved!' :
             saveStatus === 'error' ? 'Error' : 'Save Configuration'}
          </button>
        </div>

        {saveMessage && (
          <div style={{
            ...styles.statusMessage,
            background: saveStatus === 'success' ? colors.successBg : colors.errorBg,
            color: saveStatus === 'success' ? colors.success : colors.error,
            marginTop: spacing.sm,
          }}>
            {saveMessage}
          </div>
        )}
      </div>

      <div style={styles.divider} />

      <div style={{ marginTop: spacing.lg }}>
        <h4 style={{ ...styles.subsectionTitle, fontSize: typography.base, marginBottom: spacing.md }}>
          Manual Sync
        </h4>

        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: spacing.md,
          marginBottom: spacing.md,
        }}>
          <label style={styles.label}>
            <span>From Date</span>
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              style={styles.input}
            />
          </label>
          <label style={styles.label}>
            <span>To Date</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              style={styles.input}
            />
          </label>
        </div>

        <div style={styles.buttonRow}>
          <button
            onClick={handleTriggerSync}
            disabled={syncStatus === 'syncing'}
            style={mergeStyles(
              buttonStyle('outline'),
              syncStatus === 'success' ? { borderColor: colors.success, color: colors.success } : {},
              syncStatus === 'error' ? { borderColor: colors.error, color: colors.error } : {}
            )}
          >
            {syncStatus === 'syncing' ? 'Syncing...' : 'Trigger Sync'}
          </button>
        </div>

        {syncMessage && (
          <div style={{
            ...styles.statusMessage,
            background: syncStatus === 'success' ? colors.successBg : colors.errorBg,
            color: syncStatus === 'success' ? colors.success : colors.error,
            marginTop: spacing.sm,
          }}>
            {syncMessage}
          </div>
        )}

        {lastSyncStatus && lastSyncStatus.last_sync && (
          <div style={{
            marginTop: spacing.lg,
            padding: spacing.md,
            background: colors.background,
            borderRadius: radius.md,
            border: `1px solid ${colors.borderLight}`,
          }}>
            <h4 style={{ fontSize: typography.sm, fontWeight: typography.medium, marginBottom: spacing.sm, color: colors.text }}>
              Last Sync Status
            </h4>
            <div style={{ fontSize: typography.sm, color: colors.textSecondary }}>
              <div style={{ marginBottom: spacing.xs }}>
                <strong>Time:</strong> {lastSyncStatus.last_sync.completed_at
                  ? new Date(lastSyncStatus.last_sync.completed_at).toLocaleString()
                  : lastSyncStatus.last_sync.started_at
                    ? new Date(lastSyncStatus.last_sync.started_at).toLocaleString()
                    : 'N/A'}
              </div>
              {lastSyncStatus.last_sync.status && (
                <div style={{ marginBottom: spacing.xs }}>
                  <strong>Status:</strong>{' '}
                  <span style={{
                    color: lastSyncStatus.last_sync.status === 'success' ? colors.success : colors.error
                  }}>
                    {lastSyncStatus.last_sync.status}
                  </span>
                </div>
              )}
              {lastSyncStatus.last_sync.error_message && (
                <div>
                  <strong>Message:</strong> {lastSyncStatus.last_sync.error_message}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ============================================
// SPECIAL DATES PAGE
// ============================================

interface SpecialDate {
  id: number
  name: string
  pattern_type: 'fixed' | 'nth_weekday' | 'relative_to_date'
  fixed_month: number | null
  fixed_day: number | null
  nth_week: number | null
  weekday: number | null
  month: number | null
  relative_to_month: number | null
  relative_to_day: number | null
  relative_weekday: number | null
  relative_direction: string | null
  duration_days: number
  is_recurring: boolean
  one_off_year: number | null
  is_active: boolean
  created_at: string
}

interface ResolvedDate {
  name: string
  date: string
  day_of_week: string
}

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
const NTH_OPTIONS = [
  { value: 1, label: 'First' },
  { value: 2, label: 'Second' },
  { value: 3, label: 'Third' },
  { value: 4, label: 'Fourth' },
  { value: -1, label: 'Last' },
]

const SpecialDatesPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [editingDate, setEditingDate] = useState<SpecialDate | null>(null)
  const [previewYear, setPreviewYear] = useState(new Date().getFullYear())

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    pattern_type: 'fixed' as 'fixed' | 'nth_weekday' | 'relative_to_date',
    fixed_month: 1,
    fixed_day: 1,
    nth_week: 1,
    weekday: 0,
    month: 1,
    relative_to_month: 12,
    relative_to_day: 25,
    relative_weekday: 4,
    relative_direction: 'before',
    duration_days: 1,
    is_recurring: true,
    one_off_year: new Date().getFullYear(),
    is_active: true,
  })

  // Fetch special dates
  const { data: specialDates, isLoading } = useQuery<SpecialDate[]>({
    queryKey: ['special-dates'],
    queryFn: async () => {
      const response = await fetch('/api/settings/special-dates', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Fetch preview for year
  const { data: previewDates } = useQuery<ResolvedDate[]>({
    queryKey: ['special-dates-preview', previewYear],
    queryFn: async () => {
      const response = await fetch(`/api/settings/special-dates/preview?year=${previewYear}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Create mutation
  const createMutation = useMutation({
    mutationFn: async (data: typeof formData) => {
      const response = await fetch('/api/settings/special-dates', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(data)
      })
      if (!response.ok) throw new Error('Failed to create')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['special-dates'] })
      queryClient.invalidateQueries({ queryKey: ['special-dates-preview'] })
      setShowForm(false)
      resetForm()
    }
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: async ({ id, data }: { id: number, data: typeof formData }) => {
      const response = await fetch(`/api/settings/special-dates/${id}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(data)
      })
      if (!response.ok) throw new Error('Failed to update')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['special-dates'] })
      queryClient.invalidateQueries({ queryKey: ['special-dates-preview'] })
      setShowForm(false)
      setEditingDate(null)
      resetForm()
    }
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: async (id: number) => {
      const response = await fetch(`/api/settings/special-dates/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to delete')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['special-dates'] })
      queryClient.invalidateQueries({ queryKey: ['special-dates-preview'] })
    }
  })

  // Seed defaults mutation
  const seedMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch('/api/settings/special-dates/seed-defaults', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to seed')
      return response.json()
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['special-dates'] })
      queryClient.invalidateQueries({ queryKey: ['special-dates-preview'] })
    }
  })

  const resetForm = () => {
    setFormData({
      name: '',
      pattern_type: 'fixed',
      fixed_month: 1,
      fixed_day: 1,
      nth_week: 1,
      weekday: 0,
      month: 1,
      relative_to_month: 12,
      relative_to_day: 25,
      relative_weekday: 4,
      relative_direction: 'before',
      duration_days: 1,
      is_recurring: true,
      one_off_year: new Date().getFullYear(),
      is_active: true,
    })
  }

  const handleEdit = (sd: SpecialDate) => {
    setEditingDate(sd)
    setFormData({
      name: sd.name,
      pattern_type: sd.pattern_type,
      fixed_month: sd.fixed_month || 1,
      fixed_day: sd.fixed_day || 1,
      nth_week: sd.nth_week || 1,
      weekday: sd.weekday || 0,
      month: sd.month || 1,
      relative_to_month: sd.relative_to_month || 12,
      relative_to_day: sd.relative_to_day || 25,
      relative_weekday: sd.relative_weekday || 4,
      relative_direction: sd.relative_direction || 'before',
      duration_days: sd.duration_days || 1,
      is_recurring: sd.is_recurring,
      one_off_year: sd.one_off_year || new Date().getFullYear(),
      is_active: sd.is_active,
    })
    setShowForm(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingDate) {
      updateMutation.mutate({ id: editingDate.id, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  const getPatternDescription = (sd: SpecialDate): string => {
    if (sd.pattern_type === 'fixed') {
      return `${MONTHS[(sd.fixed_month || 1) - 1]} ${sd.fixed_day}`
    } else if (sd.pattern_type === 'nth_weekday') {
      const nth = NTH_OPTIONS.find(o => o.value === sd.nth_week)?.label || ''
      return `${nth} ${WEEKDAYS[sd.weekday || 0]} of ${MONTHS[(sd.month || 1) - 1]}`
    } else {
      return `${WEEKDAYS[sd.relative_weekday || 0]} ${sd.relative_direction} ${MONTHS[(sd.relative_to_month || 1) - 1]} ${sd.relative_to_day}`
    }
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Special Dates</h2>
          <p style={styles.hint}>
            Configure custom holidays and events for Prophet forecasting
          </p>
        </div>
        <div style={{ display: 'flex', gap: spacing.sm }}>
          {(!specialDates || specialDates.length === 0) && (
            <button
              onClick={() => seedMutation.mutate()}
              disabled={seedMutation.isPending}
              style={mergeStyles(buttonStyle('secondary'), { background: colors.textSecondary })}
            >
              {seedMutation.isPending ? 'Seeding...' : 'Seed Defaults'}
            </button>
          )}
          <button
            onClick={() => { resetForm(); setEditingDate(null); setShowForm(true) }}
            style={buttonStyle()}
          >
            Add Special Date
          </button>
        </div>
      </div>

      {/* Form Modal */}
      {showForm && (
        <div style={styles.formContainer}>
          <h3 style={{ margin: 0, marginBottom: spacing.md, color: colors.text }}>
            {editingDate ? 'Edit Special Date' : 'Add Special Date'}
          </h3>
          <form onSubmit={handleSubmit}>
            <div style={styles.formGrid}>
              <div style={styles.formGroup}>
                <label style={styles.label}>Name</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  style={styles.input}
                  placeholder="e.g., Valentine's Day"
                  required
                />
              </div>

              <div style={styles.formGroup}>
                <label style={styles.label}>Pattern Type</label>
                <select
                  value={formData.pattern_type}
                  onChange={(e) => setFormData({ ...formData, pattern_type: e.target.value as typeof formData.pattern_type })}
                  style={styles.select}
                >
                  <option value="fixed">Fixed Date (e.g., Feb 14)</option>
                  <option value="nth_weekday">Nth Weekday (e.g., 2nd Monday of May)</option>
                  <option value="relative_to_date">Relative to Date (e.g., Friday before Dec 25)</option>
                </select>
              </div>

              {/* Fixed Date Fields */}
              {formData.pattern_type === 'fixed' && (
                <>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Month</label>
                    <select
                      value={formData.fixed_month}
                      onChange={(e) => setFormData({ ...formData, fixed_month: parseInt(e.target.value) })}
                      style={styles.select}
                    >
                      {MONTHS.map((m, i) => (
                        <option key={i} value={i + 1}>{m}</option>
                      ))}
                    </select>
                  </div>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Day</label>
                    <input
                      type="number"
                      min={1}
                      max={31}
                      value={formData.fixed_day}
                      onChange={(e) => setFormData({ ...formData, fixed_day: parseInt(e.target.value) })}
                      style={styles.input}
                    />
                  </div>
                </>
              )}

              {/* Nth Weekday Fields */}
              {formData.pattern_type === 'nth_weekday' && (
                <>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Which</label>
                    <select
                      value={formData.nth_week}
                      onChange={(e) => setFormData({ ...formData, nth_week: parseInt(e.target.value) })}
                      style={styles.select}
                    >
                      {NTH_OPTIONS.map((o) => (
                        <option key={o.value} value={o.value}>{o.label}</option>
                      ))}
                    </select>
                  </div>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Weekday</label>
                    <select
                      value={formData.weekday}
                      onChange={(e) => setFormData({ ...formData, weekday: parseInt(e.target.value) })}
                      style={styles.select}
                    >
                      {WEEKDAYS.map((w, i) => (
                        <option key={i} value={i}>{w}</option>
                      ))}
                    </select>
                  </div>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Month</label>
                    <select
                      value={formData.month}
                      onChange={(e) => setFormData({ ...formData, month: parseInt(e.target.value) })}
                      style={styles.select}
                    >
                      {MONTHS.map((m, i) => (
                        <option key={i} value={i + 1}>{m}</option>
                      ))}
                    </select>
                  </div>
                </>
              )}

              {/* Relative to Date Fields */}
              {formData.pattern_type === 'relative_to_date' && (
                <>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Find</label>
                    <select
                      value={formData.relative_weekday}
                      onChange={(e) => setFormData({ ...formData, relative_weekday: parseInt(e.target.value) })}
                      style={styles.select}
                    >
                      {WEEKDAYS.map((w, i) => (
                        <option key={i} value={i}>{w}</option>
                      ))}
                    </select>
                  </div>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Direction</label>
                    <select
                      value={formData.relative_direction}
                      onChange={(e) => setFormData({ ...formData, relative_direction: e.target.value })}
                      style={styles.select}
                    >
                      <option value="before">Before</option>
                      <option value="after">After</option>
                    </select>
                  </div>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Reference Month</label>
                    <select
                      value={formData.relative_to_month}
                      onChange={(e) => setFormData({ ...formData, relative_to_month: parseInt(e.target.value) })}
                      style={styles.select}
                    >
                      {MONTHS.map((m, i) => (
                        <option key={i} value={i + 1}>{m}</option>
                      ))}
                    </select>
                  </div>
                  <div style={styles.formGroup}>
                    <label style={styles.label}>Reference Day</label>
                    <input
                      type="number"
                      min={1}
                      max={31}
                      value={formData.relative_to_day}
                      onChange={(e) => setFormData({ ...formData, relative_to_day: parseInt(e.target.value) })}
                      style={styles.input}
                    />
                  </div>
                </>
              )}

              {/* Common Fields */}
              <div style={styles.formGroup}>
                <label style={styles.label}>Duration (days)</label>
                <input
                  type="number"
                  min={1}
                  max={30}
                  value={formData.duration_days}
                  onChange={(e) => setFormData({ ...formData, duration_days: parseInt(e.target.value) })}
                  style={styles.input}
                />
              </div>

              <div style={styles.formGroup}>
                <label style={styles.label}>Recurrence</label>
                <select
                  value={formData.is_recurring ? 'recurring' : 'one-off'}
                  onChange={(e) => setFormData({ ...formData, is_recurring: e.target.value === 'recurring' })}
                  style={styles.select}
                >
                  <option value="recurring">Every Year</option>
                  <option value="one-off">One-off</option>
                </select>
              </div>

              {!formData.is_recurring && (
                <div style={styles.formGroup}>
                  <label style={styles.label}>Year</label>
                  <input
                    type="number"
                    min={2020}
                    max={2030}
                    value={formData.one_off_year}
                    onChange={(e) => setFormData({ ...formData, one_off_year: parseInt(e.target.value) })}
                    style={styles.input}
                  />
                </div>
              )}

              <div style={styles.formGroup}>
                <label style={{ ...styles.label, display: 'flex', alignItems: 'center', gap: spacing.sm }}>
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  />
                  Active
                </label>
              </div>
            </div>

            <div style={{ display: 'flex', gap: spacing.sm, marginTop: spacing.md }}>
              <button type="submit" style={buttonStyle()} disabled={createMutation.isPending || updateMutation.isPending}>
                {editingDate ? 'Update' : 'Create'}
              </button>
              <button
                type="button"
                onClick={() => { setShowForm(false); setEditingDate(null); resetForm() }}
                style={mergeStyles(buttonStyle('secondary'), { background: colors.textSecondary })}
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Existing Special Dates List */}
      <div style={styles.tableContainer}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.th}>Name</th>
              <th style={styles.th}>Pattern</th>
              <th style={styles.th}>Duration</th>
              <th style={styles.th}>Recurrence</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} style={{ ...styles.td, textAlign: 'center' }}>Loading...</td></tr>
            ) : specialDates && specialDates.length > 0 ? (
              specialDates.map((sd) => (
                <tr key={sd.id}>
                  <td style={styles.td}>{sd.name}</td>
                  <td style={{ ...styles.td, color: colors.textSecondary }}>{getPatternDescription(sd)}</td>
                  <td style={styles.td}>{sd.duration_days} day{sd.duration_days > 1 ? 's' : ''}</td>
                  <td style={styles.td}>{sd.is_recurring ? 'Every Year' : `${sd.one_off_year} only`}</td>
                  <td style={styles.td}>
                    <span style={mergeStyles(badgeStyle(sd.is_active ? 'success' : 'info'), {
                      background: sd.is_active ? colors.success : colors.textMuted
                    })}>
                      {sd.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td style={styles.td}>
                    <div style={{ display: 'flex', gap: spacing.xs }}>
                      <button
                        onClick={() => handleEdit(sd)}
                        style={{ ...styles.actionButton, color: colors.accent }}
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => {
                          if (confirm(`Delete "${sd.name}"?`)) {
                            deleteMutation.mutate(sd.id)
                          }
                        }}
                        style={{ ...styles.actionButton, color: colors.error }}
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              <tr><td colSpan={6} style={{ ...styles.td, textAlign: 'center', color: colors.textMuted }}>
                No special dates configured. Click "Seed Defaults" to add common dates.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Preview Section */}
      <div style={{ marginTop: spacing.xl }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: spacing.md, marginBottom: spacing.md }}>
          <h3 style={{ margin: 0, color: colors.text }}>Preview</h3>
          <select
            value={previewYear}
            onChange={(e) => setPreviewYear(parseInt(e.target.value))}
            style={styles.select}
          >
            {[2024, 2025, 2026, 2027].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: spacing.sm }}>
          {previewDates && previewDates.length > 0 ? (
            previewDates.map((pd, i) => (
              <div key={i} style={styles.previewCard}>
                <div style={{ fontWeight: typography.semibold }}>{pd.name}</div>
                <div style={{ fontSize: typography.sm, color: colors.textSecondary }}>
                  {pd.day_of_week} {pd.date}
                </div>
              </div>
            ))
          ) : (
            <p style={{ color: colors.textMuted }}>No dates to preview</p>
          )}
        </div>
      </div>
    </div>
  )
}

// ============================================
// USERS PAGE
// ============================================

const UsersPage: React.FC = () => {
  const { user: currentUser } = useAuth()
  const queryClient = useQueryClient()
  const [showAddForm, setShowAddForm] = useState(false)
  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '', role: 'admin' })
  const [error, setError] = useState('')

  const { data: users, isLoading } = useQuery({
    queryKey: ['users'],
    queryFn: authApi.getUsers,
  })

  const createMutation = useMutation({
    mutationFn: authApi.createUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
      setShowAddForm(false)
      setNewUser({ username: '', password: '', display_name: '', role: 'admin' })
      setError('')
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      setError(err.response?.data?.detail || 'Failed to create user')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: authApi.deleteUser,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] })
    },
    onError: (err: Error & { response?: { data?: { detail?: string } } }) => {
      alert(err.response?.data?.detail || 'Failed to delete user')
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newUser.username || !newUser.password) {
      setError('Username and password are required')
      return
    }
    createMutation.mutate({
      username: newUser.username,
      password: newUser.password,
      display_name: newUser.display_name || undefined,
      role: newUser.role,
    })
  }

  const handleDelete = (user: UserWithDate) => {
    if (user.id === currentUser?.id) {
      alert('Cannot delete your own account')
      return
    }
    if (confirm(`Delete user "${user.display_name || user.username}"?`)) {
      deleteMutation.mutate(user.id)
    }
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Users</h2>
          <p style={styles.hint}>Manage user accounts and access.</p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          style={buttonStyle('primary')}
        >
          {showAddForm ? 'Cancel' : 'Add User'}
        </button>
      </div>

      {showAddForm && (
        <div style={styles.addForm}>
          <form onSubmit={handleSubmit}>
            {error && <div style={styles.error}>{error}</div>}
            <div style={styles.formRow}>
              <div style={styles.formField}>
                <label style={styles.label}>Username</label>
                <input
                  type="text"
                  value={newUser.username}
                  onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
                  style={styles.input}
                  placeholder="Enter username"
                  required
                />
              </div>
              <div style={styles.formField}>
                <label style={styles.label}>Password</label>
                <input
                  type="password"
                  value={newUser.password}
                  onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
                  style={styles.input}
                  placeholder="Enter password"
                  required
                />
              </div>
              <div style={styles.formField}>
                <label style={styles.label}>Display Name</label>
                <input
                  type="text"
                  value={newUser.display_name}
                  onChange={(e) => setNewUser({ ...newUser, display_name: e.target.value })}
                  style={styles.input}
                  placeholder="Optional"
                />
              </div>
              <div style={styles.formField}>
                <label style={styles.label}>Role</label>
                <select
                  value={newUser.role}
                  onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
                  style={styles.input}
                >
                  <option value="admin">Admin</option>
                  <option value="staff">Staff</option>
                </select>
              </div>
              <button
                type="submit"
                style={mergeStyles(buttonStyle('secondary'), { alignSelf: 'flex-end' })}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading ? (
        <div style={styles.loading}>Loading users...</div>
      ) : (
        <div style={styles.userList}>
          {users?.map((user) => (
            <div key={user.id} style={styles.userCard}>
              <div style={styles.userInfo}>
                <div style={styles.userName}>
                  {user.display_name || user.username}
                  {user.id === currentUser?.id && (
                    <span style={badgeStyle('info')}> You</span>
                  )}
                </div>
                <div style={styles.userMeta}>
                  @{user.username}
                  {user.created_at && (
                    <span style={styles.userDate}>
                      {' • '}Added {new Date(user.created_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
              </div>
              <div style={styles.userActions}>
                <span style={badgeStyle(user.role === 'staff' ? 'warning' : 'info')}>
                  {user.role === 'staff' ? 'Staff' : 'Admin'}
                </span>
                <span style={user.is_active ? badgeStyle('success') : badgeStyle('error')}>
                  {user.is_active ? 'Active' : 'Inactive'}
                </span>
                {user.id !== currentUser?.id && (
                  <button
                    onClick={() => handleDelete(user)}
                    style={styles.deleteButton}
                    disabled={deleteMutation.isPending}
                    title="Delete user"
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ============================================
// DATABASE PAGE
// ============================================

const DatabasePage: React.FC = () => {
  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>Database Browser</h2>
      <p style={styles.hint}>
        Browse and manage the database using Adminer. Login with: Server: <strong>db</strong>, Username: <strong>forecast</strong>, Password: <strong>forecast_secret</strong>, Database: <strong>forecast_data</strong>
      </p>

      <div style={styles.iframeContainer}>
        <iframe
          src="/adminer/?pgsql=db&username=forecast&db=forecast_data"
          style={styles.iframe}
          title="Database Browser"
        />
      </div>
    </div>
  )
}

// ============================================
// BUDGET PAGE
// ============================================

interface MonthlyBudget {
  id: number
  year: number
  month: number
  budget_type: string
  budget_value: number
  notes: string | null
  created_at: string
  updated_at: string
}

interface DailyBudget {
  date: string
  budget_type: string
  budget_value: number
  distribution_method: string
  prior_year_pct: number | null
}

interface UploadResult {
  status: string
  filename: string
  records_created: number
  records_updated: number
  total_records: number
  errors: string[] | null
}

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const BudgetPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [selectedYear, setSelectedYear] = useState(new Date().getFullYear())
  const [selectedMonth, setSelectedMonth] = useState<number | null>(null)
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null)
  const [distributing, setDistributing] = useState(false)
  const [distributeStatus, setDistributeStatus] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)

  // Fetch monthly budgets for selected year
  const { data: monthlyBudgets, isLoading: loadingMonthly } = useQuery<MonthlyBudget[]>({
    queryKey: ['monthly-budgets', selectedYear],
    queryFn: async () => {
      const response = await fetch(`/api/budget/monthly?year=${selectedYear}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Fetch daily budgets for selected month
  const { data: dailyBudgets, isLoading: loadingDaily } = useQuery<DailyBudget[]>({
    queryKey: ['daily-budgets', selectedYear, selectedMonth],
    queryFn: async () => {
      if (selectedMonth === null) return []
      const startDate = `${selectedYear}-${String(selectedMonth).padStart(2, '0')}-01`
      const lastDay = new Date(selectedYear, selectedMonth, 0).getDate()
      const endDate = `${selectedYear}-${String(selectedMonth).padStart(2, '0')}-${lastDay}`
      const response = await fetch(`/api/budget/daily?from_date=${startDate}&to_date=${endDate}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
    enabled: selectedMonth !== null,
  })

  // Handle file upload
  const handleFileUpload = async (file: File) => {
    const validTypes = ['.csv', '.xlsx', '.xls']
    const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'))
    if (!validTypes.includes(ext)) {
      setUploadResult({
        status: 'error',
        filename: file.name,
        records_created: 0,
        records_updated: 0,
        total_records: 0,
        errors: ['Invalid file type. Please upload a CSV or Excel file.']
      })
      return
    }

    setUploading(true)
    setUploadResult(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await fetch('/api/budget/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        body: formData
      })
      const result = await response.json()
      if (response.ok) {
        setUploadResult(result)
        queryClient.invalidateQueries({ queryKey: ['monthly-budgets'] })
      } else {
        setUploadResult({
          status: 'error',
          filename: file.name,
          records_created: 0,
          records_updated: 0,
          total_records: 0,
          errors: [result.detail || 'Upload failed']
        })
      }
    } catch (err) {
      setUploadResult({
        status: 'error',
        filename: file.name,
        records_created: 0,
        records_updated: 0,
        total_records: 0,
        errors: ['Failed to upload file']
      })
    } finally {
      setUploading(false)
    }
  }

  // Handle drag and drop
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFileUpload(file)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(true)
  }

  const handleDragLeave = () => {
    setDragOver(false)
  }

  // Handle file input
  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFileUpload(file)
    e.target.value = '' // Reset input
  }

  // Download template
  const handleDownloadTemplate = async () => {
    try {
      const response = await fetch('/api/budget/template', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (response.ok) {
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `budget_template_${selectedYear}.xlsx`
        a.click()
        window.URL.revokeObjectURL(url)
      }
    } catch (err) {
      console.error('Failed to download template', err)
    }
  }

  // Distribute all budgets
  const handleDistributeAll = async () => {
    setDistributing(true)
    setDistributeStatus(null)
    let totalDays = 0

    try {
      for (let month = 1; month <= 12; month++) {
        const response = await fetch(`/api/budget/distribute?year=${selectedYear}&month=${month}`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
        })
        if (response.ok) {
          const result = await response.json()
          totalDays += result.days_distributed || 0
        }
      }
      setDistributeStatus(`Distributed ${totalDays} days successfully`)
      queryClient.invalidateQueries({ queryKey: ['daily-budgets'] })
    } catch (err) {
      setDistributeStatus('Failed to distribute budgets')
    } finally {
      setDistributing(false)
      setTimeout(() => setDistributeStatus(null), 5000)
    }
  }

  // Distribute single month
  const handleDistributeMonth = async (month: number) => {
    setDistributing(true)
    try {
      const response = await fetch(`/api/budget/distribute?year=${selectedYear}&month=${month}`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (response.ok) {
        queryClient.invalidateQueries({ queryKey: ['daily-budgets'] })
        setSelectedMonth(month)
      }
    } catch (err) {
      console.error('Failed to distribute budget', err)
    } finally {
      setDistributing(false)
    }
  }

  // Organize monthly budgets by month
  const budgetsByMonth: Record<number, Record<string, number>> = {}
  monthlyBudgets?.forEach(b => {
    if (!budgetsByMonth[b.month]) budgetsByMonth[b.month] = {}
    budgetsByMonth[b.month][b.budget_type] = b.budget_value
  })

  // Organize daily budgets by date
  const dailyByDate: Record<string, Record<string, number>> = {}
  let dailyTotals = { net_accom: 0, net_dry: 0, net_wet: 0 }
  dailyBudgets?.forEach(d => {
    if (!dailyByDate[d.date]) dailyByDate[d.date] = {}
    dailyByDate[d.date][d.budget_type] = d.budget_value
    if (d.budget_type in dailyTotals) {
      dailyTotals[d.budget_type as keyof typeof dailyTotals] += d.budget_value
    }
  })

  // Generate year options
  const currentYear = new Date().getFullYear()
  const yearOptions = [currentYear - 1, currentYear, currentYear + 1, currentYear + 2]

  // Format currency
  const formatCurrency = (value: number | undefined) => {
    if (value === undefined || value === null) return '-'
    return `£${value.toLocaleString('en-GB', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`
  }

  return (
    <div style={styles.section}>
      <h2 style={styles.sectionTitle}>Budget Management</h2>
      <p style={styles.hint}>
        Upload budget spreadsheets from FD and distribute to daily values for forecast comparison.
      </p>

      {/* Upload Section */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Upload Budget Spreadsheet</h3>
        <p style={styles.hint}>
          Upload a CSV or Excel file with format: Row labels (accom, dry, wet) in first column, month headers (mm/yy) across top.
        </p>

        <div
          style={{
            ...budgetStyles.dropZone,
            ...(dragOver ? budgetStyles.dropZoneActive : {})
          }}
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
        >
          <input
            type="file"
            accept=".csv,.xlsx,.xls"
            onChange={handleFileInput}
            style={budgetStyles.fileInput}
            id="budget-file-input"
          />
          <label htmlFor="budget-file-input" style={budgetStyles.dropZoneLabel}>
            {uploading ? 'Uploading...' : 'Drag & drop CSV or Excel file here, or click to browse'}
          </label>
        </div>

        <div style={styles.buttonRow}>
          <button onClick={handleDownloadTemplate} style={buttonStyle('outline')}>
            Download Template
          </button>
        </div>

        {uploadResult && (
          <div style={{
            ...styles.statusMessage,
            background: uploadResult.status === 'success' ? colors.successBg : colors.errorBg,
            color: uploadResult.status === 'success' ? colors.success : colors.error,
            marginTop: spacing.md
          }}>
            {uploadResult.status === 'success' ? (
              <>
                <strong>Upload successful!</strong> {uploadResult.records_created} created, {uploadResult.records_updated} updated
              </>
            ) : (
              <>
                <strong>Upload failed:</strong> {uploadResult.errors?.join(', ')}
              </>
            )}
          </div>
        )}
      </div>

      <div style={styles.divider} />

      {/* Monthly Budgets Table */}
      <div style={styles.subsection}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md }}>
          <h3 style={{ ...styles.subsectionTitle, margin: 0 }}>Monthly Budgets</h3>
          <select
            value={selectedYear}
            onChange={(e) => setSelectedYear(Number(e.target.value))}
            style={budgetStyles.yearSelect}
          >
            {yearOptions.map(y => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>

        {loadingMonthly ? (
          <div style={styles.loading}>Loading budgets...</div>
        ) : (
          <>
            <div style={budgetStyles.tableContainer}>
              <table style={budgetStyles.table}>
                <thead>
                  <tr>
                    <th style={budgetStyles.th}>Month</th>
                    <th style={budgetStyles.thRight}>Accommodation</th>
                    <th style={budgetStyles.thRight}>Dry</th>
                    <th style={budgetStyles.thRight}>Wet</th>
                    <th style={budgetStyles.thCenter}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {MONTH_NAMES.map((name, idx) => {
                    const month = idx + 1
                    const data = budgetsByMonth[month] || {}
                    const hasData = Object.keys(data).length > 0
                    return (
                      <tr key={month} style={budgetStyles.tr}>
                        <td style={budgetStyles.td}>{name}</td>
                        <td style={budgetStyles.tdRight}>{formatCurrency(data.net_accom)}</td>
                        <td style={budgetStyles.tdRight}>{formatCurrency(data.net_dry)}</td>
                        <td style={budgetStyles.tdRight}>{formatCurrency(data.net_wet)}</td>
                        <td style={budgetStyles.tdCenter}>
                          {hasData && (
                            <button
                              onClick={() => {
                                handleDistributeMonth(month)
                              }}
                              style={buttonStyle('ghost')}
                              disabled={distributing}
                            >
                              View Daily
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div style={{ ...styles.buttonRow, marginTop: spacing.md }}>
              <button
                onClick={handleDistributeAll}
                disabled={distributing || !monthlyBudgets?.length}
                style={buttonStyle('primary')}
              >
                {distributing ? 'Distributing...' : 'Distribute All to Daily'}
              </button>
              {distributeStatus && (
                <span style={{
                  color: distributeStatus.includes('Failed') ? colors.error : colors.success,
                  fontSize: typography.sm,
                  marginLeft: spacing.md
                }}>
                  {distributeStatus}
                </span>
              )}
            </div>
          </>
        )}
      </div>

      {/* Daily Distribution View */}
      {selectedMonth !== null && (
        <>
          <div style={styles.divider} />

          <div style={styles.subsection}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md }}>
              <h3 style={{ ...styles.subsectionTitle, margin: 0 }}>
                Daily Distribution - {MONTH_NAMES[selectedMonth - 1]} {selectedYear}
              </h3>
              <button
                onClick={() => setSelectedMonth(null)}
                style={buttonStyle('ghost')}
              >
                Close
              </button>
            </div>

            {loadingDaily ? (
              <div style={styles.loading}>Loading daily budgets...</div>
            ) : dailyBudgets && dailyBudgets.length > 0 ? (
              <div style={budgetStyles.tableContainer}>
                <table style={budgetStyles.table}>
                  <thead>
                    <tr>
                      <th style={budgetStyles.th}>Date</th>
                      <th style={budgetStyles.thRight}>Accommodation</th>
                      <th style={budgetStyles.thRight}>Dry</th>
                      <th style={budgetStyles.thRight}>Wet</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.keys(dailyByDate).sort().map(dateStr => {
                      const data = dailyByDate[dateStr]
                      const date = new Date(dateStr)
                      const dayName = date.toLocaleDateString('en-GB', { weekday: 'short' })
                      const dayNum = date.getDate()
                      return (
                        <tr key={dateStr} style={budgetStyles.tr}>
                          <td style={budgetStyles.td}>{dayName} {dayNum}</td>
                          <td style={budgetStyles.tdRight}>{formatCurrency(data.net_accom)}</td>
                          <td style={budgetStyles.tdRight}>{formatCurrency(data.net_dry)}</td>
                          <td style={budgetStyles.tdRight}>{formatCurrency(data.net_wet)}</td>
                        </tr>
                      )
                    })}
                    <tr style={budgetStyles.trTotal}>
                      <td style={{ ...budgetStyles.td, fontWeight: typography.semibold }}>Total</td>
                      <td style={{ ...budgetStyles.tdRight, fontWeight: typography.semibold }}>{formatCurrency(dailyTotals.net_accom)}</td>
                      <td style={{ ...budgetStyles.tdRight, fontWeight: typography.semibold }}>{formatCurrency(dailyTotals.net_dry)}</td>
                      <td style={{ ...budgetStyles.tdRight, fontWeight: typography.semibold }}>{formatCurrency(dailyTotals.net_wet)}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={styles.hint}>No daily budgets found. Click "Distribute All to Daily" to generate.</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}

// ============================================
// TAX RATES PAGE
// ============================================

interface TaxRate {
  id: number
  tax_type: string
  rate: number
  effective_from: string
  created_at: string | null
}

const TaxRatesPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [newRate, setNewRate] = useState('')
  const [newEffectiveFrom, setNewEffectiveFrom] = useState('')
  const [addingRate, setAddingRate] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Fetch all tax rates
  const { data: taxRates, isLoading } = useQuery<TaxRate[]>({
    queryKey: ['tax-rates'],
    queryFn: async () => {
      const response = await fetch('/api/config/tax-rates', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Group rates by type
  const ratesByType = (taxRates || []).reduce((acc, rate) => {
    if (!acc[rate.tax_type]) acc[rate.tax_type] = []
    acc[rate.tax_type].push(rate)
    return acc
  }, {} as Record<string, TaxRate[]>)

  const handleAddRate = async () => {
    if (!newRate || !newEffectiveFrom) {
      setError('Please enter both rate and effective date')
      return
    }

    const rateValue = parseFloat(newRate) / 100 // Convert percentage to decimal
    if (isNaN(rateValue) || rateValue < 0 || rateValue > 1) {
      setError('Rate must be a valid percentage between 0 and 100')
      return
    }

    setAddingRate(true)
    setError(null)

    try {
      const response = await fetch('/api/config/tax-rates', {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          tax_type: 'accommodation_vat',
          rate: rateValue,
          effective_from: newEffectiveFrom
        })
      })

      if (response.ok) {
        queryClient.invalidateQueries({ queryKey: ['tax-rates'] })
        setNewRate('')
        setNewEffectiveFrom('')
      } else {
        const data = await response.json()
        setError(data.detail || 'Failed to add tax rate')
      }
    } catch {
      setError('Failed to add tax rate')
    } finally {
      setAddingRate(false)
    }
  }

  const handleDeleteRate = async (id: number) => {
    if (!confirm('Are you sure you want to delete this tax rate?')) return

    try {
      const response = await fetch(`/api/config/tax-rates/${id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })

      if (response.ok) {
        queryClient.invalidateQueries({ queryKey: ['tax-rates'] })
      }
    } catch {
      // Silent fail
    }
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
  }

  return (
    <div>
      <h2 style={styles.pageTitle}>Tax Rates</h2>
      <p style={styles.hint}>
        Configure tax rates with effective dates. The most recent rate before a given date will be used for calculations.
        For example, if VAT changes from 20% to 22% on 1st April 2026, add a new entry with that date.
      </p>

      {/* Add New Rate Form */}
      <div style={taxRateStyles.addForm}>
        <h3 style={styles.sectionTitle}>Add Accommodation VAT Rate</h3>
        <div style={taxRateStyles.formRow}>
          <div style={taxRateStyles.inputGroup}>
            <label style={taxRateStyles.label}>Rate (%)</label>
            <input
              type="number"
              step="0.1"
              min="0"
              max="100"
              value={newRate}
              onChange={(e) => setNewRate(e.target.value)}
              placeholder="e.g. 20"
              style={taxRateStyles.input}
            />
          </div>
          <div style={taxRateStyles.inputGroup}>
            <label style={taxRateStyles.label}>Effective From</label>
            <input
              type="date"
              value={newEffectiveFrom}
              onChange={(e) => setNewEffectiveFrom(e.target.value)}
              style={taxRateStyles.input}
            />
          </div>
          <button
            onClick={handleAddRate}
            disabled={addingRate}
            style={mergeStyles(buttonStyle('primary'), { alignSelf: 'flex-end' })}
          >
            {addingRate ? 'Adding...' : 'Add Rate'}
          </button>
        </div>
        {error && <p style={taxRateStyles.error}>{error}</p>}
      </div>

      {/* Existing Rates */}
      <div style={taxRateStyles.ratesSection}>
        <h3 style={styles.sectionTitle}>Current Tax Rates</h3>

        {isLoading ? (
          <div style={styles.loading}>Loading tax rates...</div>
        ) : Object.keys(ratesByType).length === 0 ? (
          <p style={styles.hint}>No tax rates configured. Add your first rate above.</p>
        ) : (
          Object.entries(ratesByType).map(([taxType, rates]) => (
            <div key={taxType} style={taxRateStyles.rateGroup}>
              <h4 style={taxRateStyles.rateGroupTitle}>
                {taxType === 'accommodation_vat' ? 'Accommodation VAT' : taxType}
              </h4>
              <table style={budgetStyles.table}>
                <thead>
                  <tr>
                    <th style={budgetStyles.th}>Effective From</th>
                    <th style={budgetStyles.thRight}>Rate</th>
                    <th style={budgetStyles.thCenter}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {rates.map((rate, idx) => (
                    <tr key={rate.id} style={budgetStyles.tr}>
                      <td style={budgetStyles.td}>
                        {formatDate(rate.effective_from)}
                        {idx === 0 && (
                          <span style={taxRateStyles.currentBadge}>Current</span>
                        )}
                      </td>
                      <td style={budgetStyles.tdRight}>{(rate.rate * 100).toFixed(1)}%</td>
                      <td style={budgetStyles.tdCenter}>
                        <button
                          onClick={() => handleDeleteRate(rate.id)}
                          style={mergeStyles(buttonStyle('outline'), taxRateStyles.deleteBtn)}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

const taxRateStyles: Record<string, React.CSSProperties> = {
  addForm: {
    background: colors.surface,
    padding: spacing.lg,
    borderRadius: radius.lg,
    marginBottom: spacing.xl,
    border: `1px solid ${colors.border}`,
  },
  formRow: {
    display: 'flex',
    gap: spacing.md,
    alignItems: 'flex-end',
    flexWrap: 'wrap',
  },
  inputGroup: {
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
    padding: `${spacing.sm} ${spacing.md}`,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    background: colors.background,
    minWidth: '150px',
  },
  error: {
    color: colors.error,
    fontSize: typography.sm,
    marginTop: spacing.sm,
  },
  ratesSection: {
    marginTop: spacing.xl,
  },
  rateGroup: {
    marginBottom: spacing.lg,
  },
  rateGroupTitle: {
    fontSize: typography.base,
    fontWeight: typography.semibold,
    color: colors.text,
    marginBottom: spacing.sm,
  },
  currentBadge: {
    display: 'inline-block',
    marginLeft: spacing.sm,
    padding: `2px ${spacing.xs}`,
    fontSize: typography.xs,
    background: colors.success,
    color: 'white',
    borderRadius: radius.sm,
  },
  deleteBtn: {
    padding: `${spacing.xs} ${spacing.sm}`,
    fontSize: typography.xs,
  },
}

const budgetStyles: Record<string, React.CSSProperties> = {
  dropZone: {
    border: `2px dashed ${colors.border}`,
    borderRadius: radius.lg,
    padding: spacing.xl,
    textAlign: 'center',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    background: colors.background,
  },
  dropZoneActive: {
    borderColor: colors.accent,
    background: `${colors.accent}15`,
  },
  dropZoneLabel: {
    display: 'block',
    color: colors.textSecondary,
    fontSize: typography.sm,
    cursor: 'pointer',
  },
  fileInput: {
    display: 'none',
  },
  yearSelect: {
    padding: `${spacing.xs} ${spacing.sm}`,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    background: colors.surface,
    cursor: 'pointer',
  },
  tableContainer: {
    overflowX: 'auto',
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    fontSize: typography.sm,
  },
  th: {
    padding: spacing.sm,
    textAlign: 'left',
    background: colors.background,
    borderBottom: `1px solid ${colors.border}`,
    fontWeight: typography.medium,
    color: colors.textSecondary,
  },
  thRight: {
    padding: spacing.sm,
    textAlign: 'right',
    background: colors.background,
    borderBottom: `1px solid ${colors.border}`,
    fontWeight: typography.medium,
    color: colors.textSecondary,
  },
  thCenter: {
    padding: spacing.sm,
    textAlign: 'center',
    background: colors.background,
    borderBottom: `1px solid ${colors.border}`,
    fontWeight: typography.medium,
    color: colors.textSecondary,
  },
  tr: {
    borderBottom: `1px solid ${colors.borderLight}`,
  },
  trTotal: {
    background: colors.background,
    borderTop: `2px solid ${colors.border}`,
  },
  td: {
    padding: spacing.sm,
    color: colors.text,
  },
  tdRight: {
    padding: spacing.sm,
    textAlign: 'right',
    color: colors.text,
    fontFamily: 'monospace',
  },
  tdCenter: {
    padding: spacing.sm,
    textAlign: 'center',
  },
}

// ============================================
// BACKUP & RESTORE PAGE
// ============================================

interface BackupSettings {
  backup_frequency: string
  backup_retention_count: number
  backup_destination: string
  backup_time: string | null
  backup_last_run_at: string | null
  backup_last_status: string | null
}

interface BackupHistoryEntry {
  id: number
  backup_type: string
  status: string
  filename: string
  file_path: string
  file_size_bytes: number | null
  snapshot_count: number | null
  file_count: number | null
  started_at: string
  completed_at: string | null
  error_message: string | null
  created_by: string | null
}

const BackupPage: React.FC = () => {
  const queryClient = useQueryClient()
  const { token } = useAuth()
  const [backupMessage, setBackupMessage] = useState<string | null>(null)
  const [uploadDragActive, setUploadDragActive] = useState(false)
  const [restoreConfirmOpen, setRestoreConfirmOpen] = useState(false)
  const [restoreTarget, setRestoreTarget] = useState<File | number | null>(null)

  // State for settings form
  const [frequency, setFrequency] = useState('manual')
  const [retentionCount, setRetentionCount] = useState(7)
  const [backupTime, setBackupTime] = useState('02:00')

  // Fetch backup settings
  const { data: backupSettings } = useQuery<BackupSettings>({
    queryKey: ['backup-settings'],
    queryFn: async () => {
      const res = await fetch('/api/backup/settings', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to fetch backup settings')
      return res.json()
    }
  })

  // Sync form state when backup settings load
  useEffect(() => {
    if (backupSettings) {
      setFrequency(backupSettings.backup_frequency)
      setRetentionCount(backupSettings.backup_retention_count)
      if (backupSettings.backup_time) setBackupTime(backupSettings.backup_time)
    }
  }, [backupSettings])

  // Fetch backup history
  const { data: backupHistory, refetch: refetchHistory } = useQuery({
    queryKey: ['backup-history'],
    queryFn: async () => {
      const res = await fetch('/api/backup/history', {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to fetch backup history')
      return res.json() as Promise<BackupHistoryEntry[]>
    }
  })

  // Save settings mutation
  const saveSettingsMutation = useMutation({
    mutationFn: async (updates: any) => {
      const res = await fetch('/api/backup/settings', {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify(updates)
      })
      if (!res.ok) throw new Error('Failed to save settings')
      return res.json()
    },
    onSuccess: () => {
      setBackupMessage('Settings saved successfully')
      queryClient.invalidateQueries({ queryKey: ['backup-settings'] })
      setTimeout(() => setBackupMessage(null), 3000)
    },
    onError: (error: any) => {
      setBackupMessage(`Error: ${error.message}`)
      setTimeout(() => setBackupMessage(null), 5000)
    }
  })

  // Create backup mutation
  const createBackupMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/backup/create', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to create backup')
      return res.json()
    },
    onSuccess: (data) => {
      setBackupMessage(`Backup created: ${data.message}`)
      refetchHistory()
      setTimeout(() => setBackupMessage(null), 5000)
    },
    onError: (error: any) => {
      setBackupMessage(`Error: ${error.message}`)
      setTimeout(() => setBackupMessage(null), 5000)
    }
  })

  // Upload and restore mutation
  const uploadRestoreMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData()
      formData.append('file', file)
      const res = await fetch('/api/backup/upload-restore', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData
      })
      if (!res.ok) throw new Error('Failed to restore backup')
      return res.json()
    },
    onSuccess: () => {
      setBackupMessage('Restore successful! Redirecting to login...')
      setTimeout(() => {
        localStorage.removeItem('token')
        window.location.href = '/login'
      }, 2000)
    },
    onError: (error: any) => {
      setBackupMessage(`Error: ${error.message}`)
      setTimeout(() => setBackupMessage(null), 5000)
    }
  })

  // Restore from history mutation
  const restoreBackupMutation = useMutation({
    mutationFn: async (backupId: number) => {
      const res = await fetch(`/api/backup/${backupId}/restore`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to restore backup')
      return res.json()
    },
    onSuccess: () => {
      setBackupMessage('Restore successful! Redirecting to login...')
      setTimeout(() => {
        localStorage.removeItem('token')
        window.location.href = '/login'
      }, 2000)
    },
    onError: (error: any) => {
      setBackupMessage(`Error: ${error.message}`)
      setTimeout(() => setBackupMessage(null), 5000)
    }
  })

  // Delete backup mutation
  const deleteBackupMutation = useMutation({
    mutationFn: async (backupId: number) => {
      const res = await fetch(`/api/backup/${backupId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Failed to delete backup')
      return res.json()
    },
    onSuccess: () => {
      setBackupMessage('Backup deleted successfully')
      refetchHistory()
      setTimeout(() => setBackupMessage(null), 3000)
    },
    onError: (error: any) => {
      setBackupMessage(`Error: ${error.message}`)
      setTimeout(() => setBackupMessage(null), 5000)
    }
  })

  const handleSaveSettings = () => {
    saveSettingsMutation.mutate({
      frequency,
      retention_count: retentionCount,
      time: backupTime
    })
  }

  const handleCreateBackup = () => {
    createBackupMutation.mutate()
  }

  const handleFileUpload = (file: File) => {
    if (!file.name.endsWith('.zip')) {
      setBackupMessage('Error: Only ZIP files are accepted')
      setTimeout(() => setBackupMessage(null), 3000)
      return
    }
    setRestoreTarget(file)
    setRestoreConfirmOpen(true)
  }

  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setUploadDragActive(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setUploadDragActive(false)
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setUploadDragActive(false)

    const files = e.dataTransfer.files
    if (files && files[0]) {
      handleFileUpload(files[0])
    }
  }

  const handleDownload = async (backup: BackupHistoryEntry) => {
    try {
      const res = await fetch(`/api/backup/${backup.id}/download`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error('Download failed')
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = backup.filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (err) {
      setBackupMessage('Error: Download failed')
      setTimeout(() => setBackupMessage(null), 3000)
    }
  }

  const formatFileSize = (bytes: number | null): string => {
    if (!bytes) return '-'
    const mb = bytes / 1024 / 1024
    if (mb < 1) return `${(bytes / 1024).toFixed(1)} KB`
    if (mb < 1024) return `${mb.toFixed(1)} MB`
    return `${(mb / 1024).toFixed(1)} GB`
  }

  const formatDate = (dateStr: string | null): string => {
    if (!dateStr) return '-'
    return new Date(dateStr).toLocaleString()
  }

  const getStatusBadge = (status: string) => {
    const colors = {
      success: { bg: '#d4edda', color: '#155724', border: '#c3e6cb' },
      running: { bg: '#fff3cd', color: '#856404', border: '#ffeaa7' },
      failed: { bg: '#f8d7da', color: '#721c24', border: '#f5c6cb' }
    }
    const style = colors[status as keyof typeof colors] || colors.failed
    return (
      <span
        style={{
          padding: '0.25rem 0.5rem',
          borderRadius: radius.sm,
          fontSize: typography.xs,
          fontWeight: typography.semibold,
          background: style.bg,
          color: style.color,
          border: `1px solid ${style.border}`,
          textTransform: 'uppercase'
        }}
      >
        {status}
      </span>
    )
  }

  const getTypeBadge = (type: string) => {
    const isManual = type === 'manual'
    return (
      <span
        style={{
          padding: '0.25rem 0.5rem',
          borderRadius: radius.sm,
          fontSize: typography.xs,
          fontWeight: typography.medium,
          background: isManual ? '#e7f5ff' : '#f3f4f6',
          color: isManual ? '#1971c2' : '#4b5563',
          border: `1px solid ${isManual ? '#a5d8ff' : '#d1d5db'}`
        }}
      >
        {type}
      </span>
    )
  }

  const isOperationInProgress =
    createBackupMutation.isPending ||
    uploadRestoreMutation.isPending ||
    restoreBackupMutation.isPending ||
    deleteBackupMutation.isPending

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>Backup & Restore</h2>
          <p style={styles.hint}>
            Create and manage database backups for disaster recovery
          </p>
        </div>
      </div>

      {backupMessage && (
        <div
          style={{
            padding: spacing.md,
            marginBottom: spacing.lg,
            borderRadius: radius.md,
            background: backupMessage.startsWith('Error')
              ? colors.errorBg
              : '#d4edda',
            color: backupMessage.startsWith('Error') ? colors.error : '#155724',
            border: `1px solid ${backupMessage.startsWith('Error') ? colors.error : '#c3e6cb'}`,
            fontSize: typography.sm
          }}
        >
          {backupMessage}
        </div>
      )}

      {/* Backup Settings */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Backup Settings</h3>

        <div style={styles.formGroup}>
          <label style={styles.label}>Frequency</label>
          <select
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
            style={styles.select}
            disabled={isOperationInProgress}
          >
            <option value="manual">Manual Only</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </div>

        {frequency !== 'manual' && (
          <div style={styles.formGroup}>
            <label style={styles.label}>Backup Time</label>
            <input
              type="time"
              value={backupTime}
              onChange={(e) => setBackupTime(e.target.value)}
              style={styles.input}
              disabled={isOperationInProgress}
            />
          </div>
        )}

        <div style={styles.formGroup}>
          <label style={styles.label}>Retention Count</label>
          <input
            type="number"
            min="1"
            max="30"
            value={retentionCount}
            onChange={(e) => setRetentionCount(parseInt(e.target.value))}
            style={styles.input}
            disabled={isOperationInProgress}
          />
          <p style={styles.hint}>Number of backups to keep (older ones will be deleted)</p>
        </div>

        {backupSettings?.backup_last_run_at && (
          <div style={{ marginTop: spacing.md }}>
            <p style={{ ...styles.label, marginBottom: spacing.xs }}>Last Backup:</p>
            <p style={styles.hint}>
              {formatDate(backupSettings.backup_last_run_at)} -{' '}
              {getStatusBadge(backupSettings.backup_last_status || 'unknown')}
            </p>
          </div>
        )}

        <button
          onClick={handleSaveSettings}
          style={mergeStyles(
            buttonStyle(),
            isOperationInProgress ? { opacity: 0.6, cursor: 'not-allowed' } : {}
          )}
          disabled={isOperationInProgress}
        >
          {saveSettingsMutation.isPending ? 'Saving...' : 'Save Settings'}
        </button>
      </div>

      <div style={styles.divider} />

      {/* Manual Backup */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Create Backup</h3>
        <p style={styles.hint}>
          Create a full backup of your database and files. This may take several minutes.
        </p>
        <button
          onClick={handleCreateBackup}
          style={mergeStyles(
            buttonStyle(),
            { background: colors.success },
            isOperationInProgress ? { opacity: 0.6, cursor: 'not-allowed' } : {}
          )}
          disabled={isOperationInProgress}
        >
          {createBackupMutation.isPending ? 'Creating Backup...' : 'Create Backup Now'}
        </button>
      </div>

      <div style={styles.divider} />

      {/* Restore from File */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Restore from File</h3>
        <p style={styles.hint}>Upload a backup ZIP file to restore your data.</p>

        <div
          onDragEnter={handleDragEnter}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          style={{
            border: `2px dashed ${uploadDragActive ? colors.primary : colors.border}`,
            borderRadius: radius.md,
            padding: spacing.xl,
            textAlign: 'center',
            background: uploadDragActive ? '#fff5f7' : colors.surfaceHover,
            cursor: 'pointer',
            transition: 'all 0.2s'
          }}
          onClick={() => document.getElementById('backup-upload-input')?.click()}
        >
          <div style={{ fontSize: '3rem', marginBottom: spacing.sm }}>📦</div>
          <p style={{ margin: `${spacing.sm} 0`, fontWeight: typography.medium }}>
            {uploadDragActive ? 'Drop backup file here' : 'Drag and drop backup file here'}
          </p>
          <p style={{ margin: `${spacing.sm} 0`, fontSize: typography.sm, color: colors.textMuted }}>
            or{' '}
            <span style={{ color: colors.primary, textDecoration: 'underline' }}>
              click to browse
            </span>
          </p>
          <p style={{ margin: `${spacing.sm} 0`, fontSize: typography.xs, color: colors.textMuted }}>
            Only .zip backup files are accepted
          </p>
          <input
            type="file"
            accept=".zip"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) {
                handleFileUpload(file)
                e.target.value = ''
              }
            }}
            style={{ display: 'none' }}
            id="backup-upload-input"
          />
        </div>
      </div>

      <div style={styles.divider} />

      {/* Backup History */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Backup History</h3>

        {backupHistory && backupHistory.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Started</th>
                  <th style={styles.th}>Type</th>
                  <th style={styles.th}>Status</th>
                  <th style={styles.th}>Size</th>
                  <th style={styles.th}>Snapshots</th>
                  <th style={styles.th}>Files</th>
                  <th style={styles.th}>Created By</th>
                  <th style={styles.th}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {backupHistory.map((backup) => (
                  <tr key={backup.id}>
                    <td style={styles.td}>{formatDate(backup.started_at)}</td>
                    <td style={styles.td}>{getTypeBadge(backup.backup_type)}</td>
                    <td style={styles.td}>{getStatusBadge(backup.status)}</td>
                    <td style={styles.td}>{formatFileSize(backup.file_size_bytes)}</td>
                    <td style={styles.td}>
                      {backup.snapshot_count !== null ? backup.snapshot_count.toLocaleString() : '-'}
                    </td>
                    <td style={styles.td}>
                      {backup.file_count !== null ? backup.file_count.toLocaleString() : '-'}
                    </td>
                    <td style={styles.td}>
                      {backup.created_by || (
                        <span style={{ fontStyle: 'italic', color: colors.textMuted }}>scheduled</span>
                      )}
                    </td>
                    <td style={styles.td}>
                      <div style={{ display: 'flex', gap: spacing.xs }}>
                        <button
                          onClick={() => handleDownload(backup)}
                          disabled={backup.status !== 'success'}
                          style={mergeStyles(
                            buttonStyle('secondary'),
                            {
                              padding: `${spacing.xs} ${spacing.sm}`,
                              fontSize: typography.sm
                            },
                            backup.status !== 'success' ? { opacity: 0.5, cursor: 'not-allowed' } : {}
                          )}
                        >
                          Download
                        </button>
                        <button
                          onClick={() => {
                            setRestoreTarget(backup.id)
                            setRestoreConfirmOpen(true)
                          }}
                          disabled={backup.status !== 'success' || isOperationInProgress}
                          style={mergeStyles(
                            buttonStyle('secondary'),
                            {
                              padding: `${spacing.xs} ${spacing.sm}`,
                              fontSize: typography.sm,
                              background: '#f59e0b',
                              color: colors.textLight
                            },
                            (backup.status !== 'success' || isOperationInProgress) ? {
                              opacity: 0.5,
                              cursor: 'not-allowed'
                            } : {}
                          )}
                        >
                          Restore
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Delete backup "${backup.filename}"? This cannot be undone.`)) {
                              deleteBackupMutation.mutate(backup.id)
                            }
                          }}
                          disabled={isOperationInProgress}
                          style={mergeStyles(
                            buttonStyle('secondary'),
                            {
                              padding: `${spacing.xs} ${spacing.sm}`,
                              fontSize: typography.sm,
                              background: colors.error,
                              color: colors.textLight
                            },
                            isOperationInProgress ? { opacity: 0.5, cursor: 'not-allowed' } : {}
                          )}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={styles.hint}>No backups yet. Create your first backup above.</p>
        )}
      </div>

      {/* Restore Confirmation Modal */}
      {restoreConfirmOpen && (
        <div
          style={styles.modal}
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setRestoreConfirmOpen(false)
              setRestoreTarget(null)
            }
          }}
        >
          <div style={{ ...styles.modalContent, maxWidth: '600px' }}>
            <h3 style={{ marginTop: 0, display: 'flex', alignItems: 'center', gap: spacing.sm }}>
              <span style={{ fontSize: '1.5rem' }}>⚠️</span>
              Confirm Backup Restore
            </h3>

            <div
              style={{
                padding: spacing.md,
                background: '#fff3cd',
                border: '1px solid #ffc107',
                borderRadius: radius.md,
                marginBottom: spacing.md
              }}
            >
              <strong style={{ color: '#856404' }}>Warning: Data Restore Operation</strong>
              <p style={{ margin: `${spacing.sm} 0 0 0`, fontSize: typography.sm, color: '#856404' }}>
                This operation will restore data from the backup file. Please review:
              </p>
            </div>

            <ul style={{ marginLeft: spacing.lg, marginBottom: spacing.lg, lineHeight: 1.8 }}>
              <li>
                <strong>Database:</strong> Full database restore (all current data will be replaced)
              </li>
              <li>
                <strong>Files:</strong> Missing files will be restored
              </li>
              <li>
                <strong>Existing files:</strong> Will NOT be overwritten
              </li>
              <li>
                <strong>After restore:</strong> You will need to log in again
              </li>
            </ul>

            <div style={{ display: 'flex', gap: spacing.md, justifyContent: 'flex-end' }}>
              <button
                onClick={() => {
                  setRestoreConfirmOpen(false)
                  setRestoreTarget(null)
                }}
                style={{ ...buttonStyle, background: colors.textMuted }}
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (typeof restoreTarget === 'number') {
                    restoreBackupMutation.mutate(restoreTarget)
                  } else if (restoreTarget instanceof File) {
                    uploadRestoreMutation.mutate(restoreTarget)
                  }
                  setRestoreConfirmOpen(false)
                  setRestoreTarget(null)
                }}
                style={{ ...buttonStyle, background: colors.error }}
                disabled={isOperationInProgress}
              >
                {isOperationInProgress ? 'Restoring...' : 'Confirm Restore'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ============================================
// FORECAST SNAPSHOTS PAGE
// ============================================

interface ForecastSnapshotSettings {
  enabled: boolean
  time: string
  models: string
  days_ahead: number
}

const ForecastSnapshotsPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle')
  const [testStatus, setTestStatus] = useState<'idle' | 'running' | 'success' | 'error'>('idle')
  const [testMessage, setTestMessage] = useState('')

  // Fetch settings
  const { data: settings, isLoading } = useQuery<ForecastSnapshotSettings>({
    queryKey: ['forecast-snapshot-settings'],
    queryFn: async () => {
      const response = await fetch('/api/config/settings/forecast-snapshot', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch settings')
      return response.json()
    },
  })

  const [formData, setFormData] = useState<ForecastSnapshotSettings>({
    enabled: false,
    time: '06:00',
    models: 'prophet,xgboost,catboost,blended',
    days_ahead: 90
  })

  // Update form when settings load
  React.useEffect(() => {
    if (settings) {
      setFormData(settings)
    }
  }, [settings])

  const handleSave = async () => {
    setSaveStatus('saving')
    try {
      const response = await fetch('/api/config/settings/forecast-snapshot', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(formData)
      })

      if (response.ok) {
        setSaveStatus('success')
        queryClient.invalidateQueries({ queryKey: ['forecast-snapshot-settings'] })
      } else {
        setSaveStatus('error')
      }
    } catch {
      setSaveStatus('error')
    }

    setTimeout(() => setSaveStatus('idle'), 3000)
  }

  const handleTest = async () => {
    setTestStatus('running')
    setTestMessage('Running forecast snapshot...')

    try {
      const response = await fetch('/api/config/settings/forecast-snapshot/test', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })

      const data = await response.json()

      if (response.ok) {
        setTestStatus('success')
        setTestMessage(data.message || 'Forecast snapshot completed successfully')
      } else {
        setTestStatus('error')
        setTestMessage(data.detail || 'Forecast snapshot failed')
      }
    } catch (err) {
      setTestStatus('error')
      setTestMessage('Failed to run forecast snapshot')
    }

    setTimeout(() => {
      setTestStatus('idle')
      setTestMessage('')
    }, 8000)
  }

  if (isLoading) {
    return <div style={styles.loading}>Loading settings...</div>
  }

  return (
    <div>
      <div style={styles.header}>
        <h1 style={styles.title}>Forecast Snapshot Automation</h1>
        <p style={styles.hint}>
          Automatically create weekly forecast snapshots for all non-COVID metrics
        </p>
      </div>

      <div style={styles.section}>
        <h3 style={styles.sectionTitle}>Automation Settings</h3>

        {/* Enabled Toggle */}
        <div style={styles.formRow}>
          <div style={styles.formField}>
            <label style={styles.label}>
              <input
                type="checkbox"
                checked={formData.enabled}
                onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
              />
              <span style={{ marginLeft: spacing.sm }}>Enable weekly forecast snapshots</span>
            </label>
            <p style={styles.hint}>
              When enabled, forecast snapshots will be created automatically every Monday
            </p>
          </div>
        </div>

        {/* Time */}
        <div style={styles.formRow}>
          <div style={styles.formField}>
            <label style={styles.label}>Snapshot Time</label>
            <input
              type="time"
              value={formData.time}
              onChange={(e) => setFormData({ ...formData, time: e.target.value })}
              style={styles.input}
              disabled={!formData.enabled}
            />
            <p style={styles.hint}>
              Time to run the snapshot (default: 06:00)
            </p>
          </div>
        </div>

        {/* Models */}
        <div style={styles.formRow}>
          <div style={styles.formField}>
            <label style={styles.label}>Models</label>
            <input
              type="text"
              value={formData.models}
              onChange={(e) => setFormData({ ...formData, models: e.target.value })}
              style={styles.input}
              disabled={!formData.enabled}
              placeholder="prophet,xgboost,catboost,blended"
            />
            <p style={styles.hint}>
              Comma-separated list of models to run (prophet, xgboost, catboost, pickup, blended). Blended averages the other models.
            </p>
          </div>
        </div>

        {/* Days Ahead */}
        <div style={styles.formRow}>
          <div style={styles.formField}>
            <label style={styles.label}>Forecast Horizon (days)</label>
            <input
              type="number"
              value={formData.days_ahead}
              onChange={(e) => setFormData({ ...formData, days_ahead: parseInt(e.target.value) || 90 })}
              style={styles.input}
              disabled={!formData.enabled}
              min="1"
              max="365"
            />
            <p style={styles.hint}>
              Number of days ahead to forecast (default: 90)
            </p>
          </div>
        </div>

        {/* Save Button */}
        <div style={styles.actions}>
          <button
            onClick={handleSave}
            style={{
              ...buttonStyle(),
              ...(saveStatus === 'saving' ? { opacity: 0.6, cursor: 'wait' } : {})
            }}
            disabled={saveStatus === 'saving'}
          >
            {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'success' ? '✓ Saved' : 'Save Settings'}
          </button>

          <button
            onClick={handleTest}
            style={{
              ...buttonStyle('secondary'),
              ...(testStatus === 'running' || !formData.enabled ? { opacity: 0.6 } : {})
            }}
            disabled={testStatus === 'running' || !formData.enabled}
          >
            {testStatus === 'running' ? 'Running...' : 'Test Now'}
          </button>
        </div>

        {testMessage && (
          <div style={{
            padding: spacing.md,
            borderRadius: radius.md,
            marginTop: spacing.md,
            background: testStatus === 'error' ? colors.errorBg : colors.successBg,
            color: testStatus === 'error' ? colors.error : colors.success,
          }}>
            {testMessage}
          </div>
        )}
      </div>

      <div style={styles.infoBox}>
        <h4 style={{ margin: `0 0 ${spacing.sm} 0`, fontSize: typography.base }}>How it works</h4>
        <ul style={{ margin: 0, paddingLeft: spacing.lg, fontSize: typography.sm, lineHeight: 1.6 }}>
          <li>Forecast snapshots are created every Monday at the specified time</li>
          <li>Snapshots capture forecasts for all active metrics using the configured models</li>
          <li>The forecast horizon determines how many days ahead to predict</li>
          <li>Snapshots use standard models (without "_postcovid" suffix) that include all historical data</li>
          <li>Forecasts are stored in the database for historical comparison and trend analysis</li>
        </ul>
      </div>
    </div>
  )
}

// ============================================
// API KEYS PAGE
// ============================================

interface ApiKey {
  id: number
  key_prefix: string
  name: string
  is_active: boolean
  created_at: string
  last_used_at: string | null
  created_by: string | null
}

interface CreateApiKeyResponse {
  id: number
  key: string
  key_prefix: string
  name: string
}

const ApiKeysPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newKeyName, setNewKeyName] = useState('')
  const [createdKey, setCreatedKey] = useState<CreateApiKeyResponse | null>(null)
  const [showKeyModal, setShowKeyModal] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  const { data: apiKeys, isLoading } = useQuery<ApiKey[]>({
    queryKey: ['api-keys'],
    queryFn: async () => {
      const response = await fetch('/api/config/api-keys', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch API keys')
      return response.json()
    },
  })

  const createMutation = useMutation({
    mutationFn: async (name: string) => {
      const response = await fetch('/api/config/api-keys', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ name })
      })
      if (!response.ok) {
        const errData = await response.json()
        throw new Error(errData.detail || 'Failed to create API key')
      }
      return response.json()
    },
    onSuccess: (data: CreateApiKeyResponse) => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
      setCreatedKey(data)
      setShowKeyModal(true)
      setShowCreateForm(false)
      setNewKeyName('')
      setError('')
    },
    onError: (err: Error) => {
      setError(err.message)
    },
  })

  const revokeMutation = useMutation({
    mutationFn: async (keyId: number) => {
      const response = await fetch(`/api/config/api-keys/${keyId}/revoke`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to revoke API key')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: async (keyId: number) => {
      const response = await fetch(`/api/config/api-keys/${keyId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to delete API key')
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['api-keys'] })
    },
  })

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newKeyName.trim()) {
      setError('Please enter a name for the API key')
      return
    }
    createMutation.mutate(newKeyName.trim())
  }

  const handleRevoke = (key: ApiKey) => {
    if (confirm(`Revoke API key "${key.name}"? It will no longer work for API requests.`)) {
      revokeMutation.mutate(key.id)
    }
  }

  const handleDelete = (key: ApiKey) => {
    if (confirm(`Permanently delete API key "${key.name}"? This cannot be undone.`)) {
      deleteMutation.mutate(key.id)
    }
  }

  const handleCopyKey = async () => {
    if (createdKey) {
      await navigator.clipboard.writeText(createdKey.key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const closeKeyModal = () => {
    setShowKeyModal(false)
    setCreatedKey(null)
    setCopied(false)
  }

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Never'
    return new Date(dateStr).toLocaleString()
  }

  return (
    <div style={styles.section}>
      <div style={styles.sectionHeader}>
        <div>
          <h2 style={styles.sectionTitle}>API Keys</h2>
          <p style={styles.hint}>Generate API keys for external applications to access forecast data.</p>
        </div>
        <button
          onClick={() => setShowCreateForm(!showCreateForm)}
          style={buttonStyle('primary')}
        >
          {showCreateForm ? 'Cancel' : 'Generate New Key'}
        </button>
      </div>

      {showCreateForm && (
        <div style={styles.addForm}>
          <form onSubmit={handleCreate}>
            {error && <div style={styles.error}>{error}</div>}
            <div style={styles.formRow}>
              <div style={styles.formField}>
                <label style={styles.label}>Key Name</label>
                <input
                  type="text"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  style={styles.input}
                  placeholder="e.g., Kitchen Flash App"
                  required
                />
              </div>
              <button
                type="submit"
                style={mergeStyles(buttonStyle('secondary'), { alignSelf: 'flex-end' })}
                disabled={createMutation.isPending}
              >
                {createMutation.isPending ? 'Generating...' : 'Generate'}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading ? (
        <div style={styles.loading}>Loading API keys...</div>
      ) : apiKeys && apiKeys.length > 0 ? (
        <div style={styles.userList}>
          {apiKeys.map((key) => (
            <div key={key.id} style={styles.userCard}>
              <div style={styles.userInfo}>
                <div style={styles.userName}>
                  {key.name}
                  <span style={{
                    marginLeft: spacing.sm,
                    fontFamily: 'monospace',
                    fontSize: typography.sm,
                    color: colors.textSecondary,
                  }}>
                    {key.key_prefix}...
                  </span>
                </div>
                <div style={styles.userMeta}>
                  Created: {formatDate(key.created_at)}
                  <span style={styles.userDate}>
                    {' • '}Last used: {formatDate(key.last_used_at)}
                  </span>
                </div>
              </div>
              <div style={styles.userActions}>
                <span style={key.is_active ? badgeStyle('success') : badgeStyle('error')}>
                  {key.is_active ? 'Active' : 'Revoked'}
                </span>
                {key.is_active && (
                  <button
                    onClick={() => handleRevoke(key)}
                    style={mergeStyles(buttonStyle('secondary'), { padding: `${spacing.xs} ${spacing.sm}` })}
                    disabled={revokeMutation.isPending}
                    title="Revoke key"
                  >
                    Revoke
                  </button>
                )}
                <button
                  onClick={() => handleDelete(key)}
                  style={styles.deleteButton}
                  disabled={deleteMutation.isPending}
                  title="Delete key"
                >
                  ×
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.emptyState}>
          <p>No API keys created yet.</p>
          <p style={{ fontSize: typography.sm, color: colors.textSecondary }}>
            Generate an API key to allow external applications like Kitchen Flash to access forecast data.
          </p>
        </div>
      )}

      <div style={styles.infoBox}>
        <h4 style={{ margin: `0 0 ${spacing.sm} 0`, fontSize: typography.base }}>Using API Keys</h4>
        <ul style={{ margin: 0, paddingLeft: spacing.lg, fontSize: typography.sm, lineHeight: 1.6 }}>
          <li>Include the API key in requests using the <code>X-API-Key</code> header</li>
          <li>Example: <code>curl -H "X-API-Key: fk_..." /api/public/forecast/rooms</code></li>
          <li>Available endpoints: <code>/public/forecast/rooms</code>, <code>/public/forecast/covers</code>, <code>/public/forecast/revenue</code></li>
          <li>API keys provide read-only access to forecast data</li>
          <li>Revoked keys will no longer work for API requests</li>
        </ul>
      </div>

      {/* Key Created Modal */}
      {showKeyModal && createdKey && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
        }}>
          <div style={{
            background: colors.surface,
            borderRadius: radius.xl,
            padding: spacing.xl,
            maxWidth: '500px',
            width: '90%',
            boxShadow: shadows.lg,
          }}>
            <h3 style={{ margin: `0 0 ${spacing.md} 0`, color: colors.success }}>
              API Key Created
            </h3>
            <p style={{ margin: `0 0 ${spacing.md} 0`, color: colors.textSecondary }}>
              Copy this key now. You won't be able to see it again!
            </p>
            <div style={{
              background: colors.background,
              border: `1px solid ${colors.border}`,
              borderRadius: radius.lg,
              padding: spacing.md,
              fontFamily: 'monospace',
              fontSize: typography.sm,
              wordBreak: 'break-all',
              marginBottom: spacing.md,
            }}>
              {createdKey.key}
            </div>
            <div style={{ display: 'flex', gap: spacing.sm, justifyContent: 'flex-end' }}>
              <button
                onClick={handleCopyKey}
                style={mergeStyles(
                  buttonStyle('secondary'),
                  copied ? { background: colors.success, color: '#fff' } : {}
                )}
              >
                {copied ? 'Copied!' : 'Copy to Clipboard'}
              </button>
              <button
                onClick={closeKeyModal}
                style={buttonStyle('primary')}
              >
                Done
              </button>
            </div>
          </div>
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
  subsection: {
    marginTop: spacing.lg,
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
  divider: {
    height: '1px',
    background: colors.borderLight,
    margin: `${spacing.xl} 0`,
  },
  apiConfigRow: {
    display: 'flex',
    gap: spacing.xl,
    marginTop: spacing.lg,
  },
  apiConfigLeft: {
    flex: '0 0 400px',
  },
  apiConfigRight: {
    flex: '0 0 auto',
    minWidth: '200px',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.md,
  },
  label: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
    color: colors.text,
    fontSize: typography.sm,
    fontWeight: typography.medium,
  },
  input: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    outline: 'none',
    transition: 'border-color 0.2s',
  },
  inputWithStatus: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  keyStatus: {
    fontSize: typography.xs,
    color: colors.success,
  },
  buttonRow: {
    display: 'flex',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  statusMessage: {
    padding: spacing.sm,
    borderRadius: radius.md,
    fontSize: typography.sm,
  },
  statusGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    gap: spacing.md,
  },
  statusGridVertical: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.sm,
  },
  statusItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.md,
  },
  statusLabel: {
    fontSize: typography.xs,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  statusOk: {
    color: colors.success,
    fontWeight: typography.medium,
  },
  statusPending: {
    color: colors.textMuted,
  },
  loading: {
    color: colors.textSecondary,
    padding: spacing.lg,
    textAlign: 'center',
  },
  error: {
    background: colors.errorBg,
    color: colors.error,
    padding: spacing.sm,
    borderRadius: radius.md,
    fontSize: typography.sm,
    marginBottom: spacing.md,
  },
  addForm: {
    background: colors.background,
    borderRadius: radius.lg,
    padding: spacing.lg,
    marginBottom: spacing.lg,
  },
  formRow: {
    display: 'flex',
    gap: spacing.md,
    alignItems: 'flex-start',
    flexWrap: 'wrap',
  },
  formField: {
    flex: '1 1 200px',
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  userList: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.sm,
  },
  userCard: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.lg,
    border: `1px solid ${colors.borderLight}`,
  },
  userInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  userName: {
    fontWeight: typography.semibold,
    color: colors.text,
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  userMeta: {
    fontSize: typography.sm,
    color: colors.textSecondary,
  },
  userDate: {
    color: colors.textMuted,
  },
  userActions: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.md,
  },
  deleteButton: {
    width: '28px',
    height: '28px',
    borderRadius: radius.full,
    border: `1px solid ${colors.border}`,
    background: colors.surface,
    color: colors.textSecondary,
    fontSize: '1.25rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all 0.2s',
  },
  iframeContainer: {
    borderRadius: radius.lg,
    overflow: 'hidden',
    border: `1px solid ${colors.borderLight}`,
    height: 'calc(100vh - 280px)',
    minHeight: '500px',
  },
  iframe: {
    width: '100%',
    height: '100%',
    border: 'none',
  },
  // Room Categories styles
  roomCategoryHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  roomCategorySummary: {
    fontSize: typography.sm,
    color: colors.textSecondary,
    fontWeight: typography.medium,
  },
  roomCategoryList: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: spacing.sm,
    background: colors.background,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  roomCategoryItem: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.sm,
    borderRadius: radius.sm,
    cursor: 'pointer',
    transition: 'background 0.15s',
  },
  checkbox: {
    width: '18px',
    height: '18px',
    accentColor: colors.accent,
  },
  roomCategoryName: {
    flex: 1,
    fontSize: typography.sm,
    color: colors.text,
  },
  roomCategoryCount: {
    fontSize: typography.xs,
    color: colors.textMuted,
    marginRight: spacing.sm,
  },
  displayOrderInput: {
    width: '50px',
    padding: `${spacing.xs} ${spacing.sm}`,
    fontSize: typography.xs,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.sm,
    textAlign: 'center',
  },
  emptyState: {
    padding: spacing.lg,
    textAlign: 'center',
    color: colors.textSecondary,
    background: colors.background,
    borderRadius: radius.md,
    marginTop: spacing.md,
  },
  // GL Revenue Mapping styles
  glAccountCount: {
    fontSize: typography.sm,
    color: colors.textSecondary,
    marginLeft: spacing.md,
  },
  departmentGrid: {
    display: 'flex',
    gap: spacing.lg,
    marginTop: spacing.lg,
  },
  departmentColumn: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.sm,
  },
  departmentHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: spacing.sm,
    borderBottom: `1px solid ${colors.borderLight}`,
  },
  departmentTitle: {
    fontSize: typography.base,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  departmentCount: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  departmentAccountList: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
    minHeight: '120px',
    maxHeight: '200px',
    overflowY: 'auto',
    background: colors.background,
    borderRadius: radius.md,
    padding: spacing.sm,
  },
  departmentEmpty: {
    color: colors.textMuted,
    fontSize: typography.sm,
    fontStyle: 'italic',
    textAlign: 'center',
    padding: spacing.md,
  },
  departmentAccountItem: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.xs,
    borderRadius: radius.sm,
    background: colors.surface,
  },
  departmentAccountName: {
    flex: 1,
    fontSize: typography.sm,
    color: colors.text,
  },
  departmentAccountCode: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  removeButton: {
    width: '20px',
    height: '20px',
    borderRadius: radius.full,
    border: 'none',
    background: colors.borderLight,
    color: colors.textSecondary,
    fontSize: '14px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  // Modal styles
  modalOverlay: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    background: 'rgba(0, 0, 0, 0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
  },
  modalContent: {
    background: colors.surface,
    borderRadius: radius.xl,
    boxShadow: shadows.lg,
    width: '90%',
    maxWidth: '600px',
    maxHeight: '80vh',
    display: 'flex',
    flexDirection: 'column',
  },
  modalHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.lg,
    borderBottom: `1px solid ${colors.borderLight}`,
  },
  modalTitle: {
    margin: 0,
    fontSize: typography.lg,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  modalCloseButton: {
    width: '32px',
    height: '32px',
    borderRadius: radius.full,
    border: 'none',
    background: colors.background,
    color: colors.textSecondary,
    fontSize: '1.25rem',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalBody: {
    flex: 1,
    overflowY: 'auto',
    padding: spacing.lg,
  },
  modalFooter: {
    display: 'flex',
    justifyContent: 'flex-end',
    padding: spacing.lg,
    borderTop: `1px solid ${colors.borderLight}`,
  },
  // GL Group styles
  glGroup: {
    marginBottom: spacing.lg,
  },
  glGroupHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: `${spacing.sm} ${spacing.md}`,
    background: colors.background,
    borderLeft: `3px solid ${colors.accent}`,
    borderRadius: `0 ${radius.sm} ${radius.sm} 0`,
    cursor: 'pointer',
    fontWeight: typography.semibold,
    fontSize: typography.sm,
    color: colors.text,
  },
  glGroupName: {
    flex: 1,
  },
  glGroupCount: {
    fontSize: typography.xs,
    color: colors.textMuted,
    fontWeight: typography.normal,
  },
  glGroupItems: {
    paddingLeft: spacing.lg,
    borderLeft: `1px solid ${colors.borderLight}`,
    marginLeft: spacing.sm,
    marginTop: spacing.xs,
  },
  glItem: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.sm,
    cursor: 'pointer',
    borderRadius: radius.sm,
    transition: 'background 0.15s',
  },
  glItemName: {
    flex: 1,
    fontSize: typography.sm,
    color: colors.text,
  },
  glItemCode: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  glItemMapped: {
    fontSize: typography.xs,
    color: colors.warning,
    fontStyle: 'italic',
  },
  // Sync section styles
  syncStatusRow: {
    display: 'flex',
    gap: spacing.lg,
    marginTop: spacing.md,
    marginBottom: spacing.lg,
  },
  syncStatusItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.md,
    minWidth: '150px',
  },
  syncStatusLabel: {
    fontSize: typography.xs,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  syncStatusValue: {
    fontSize: typography.base,
    fontWeight: typography.medium,
    color: colors.text,
  },
  syncControlsSection: {
    display: 'flex',
    gap: spacing.lg,
    flexWrap: 'wrap',
  },
  syncControlBox: {
    flex: '1 1 250px',
    padding: spacing.md,
    background: colors.background,
    borderRadius: radius.md,
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.sm,
  },
  syncControlTitle: {
    margin: 0,
    fontSize: typography.sm,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  syncControlHint: {
    margin: 0,
    fontSize: typography.xs,
    color: colors.textMuted,
    marginBottom: spacing.xs,
  },
  syncDateRow: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  dateInput: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.sm,
    flex: 1,
  },
  dateTo: {
    fontSize: typography.sm,
    color: colors.textMuted,
  },
  syncCheckboxLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    fontSize: typography.sm,
    color: colors.text,
    cursor: 'pointer',
  },
  syncSelect: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.sm,
    background: colors.surface,
    flex: 1,
  },
  syncAutoRow: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  syncTimeLabel: {
    fontSize: typography.sm,
    color: colors.textMuted,
  },
  syncTimeInput: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.sm,
    background: colors.surface,
    width: '100px',
  },
  syncLogsSection: {
    marginTop: spacing.xl,
  },
  syncLogsTitle: {
    margin: `0 0 ${spacing.sm} 0`,
    fontSize: typography.sm,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  syncLogsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  syncLogItem: {
    padding: spacing.sm,
    background: colors.background,
    borderRadius: radius.sm,
    borderLeft: `3px solid ${colors.borderLight}`,
  },
  syncLogMain: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
  },
  syncLogStatus: {
    fontWeight: typography.bold,
    fontSize: typography.sm,
  },
  syncLogDate: {
    fontSize: typography.sm,
    color: colors.text,
  },
  syncLogRecords: {
    fontSize: typography.xs,
    color: colors.textMuted,
    marginLeft: 'auto',
  },
  syncLogMeta: {
    display: 'flex',
    gap: spacing.md,
    marginTop: spacing.xs,
    paddingLeft: spacing.lg,
  },
  syncLogTrigger: {
    fontSize: typography.xs,
    color: colors.textSecondary,
  },
  syncLogRange: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  syncLogError: {
    fontSize: typography.xs,
    color: colors.error,
    marginTop: spacing.xs,
    paddingLeft: spacing.lg,
  },
  // Table styles
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
    color: colors.textSecondary,
    fontWeight: typography.medium,
    whiteSpace: 'nowrap',
  },
  td: {
    padding: spacing.sm,
    borderBottom: `1px solid ${colors.borderLight}`,
    color: colors.text,
  },
  // Special Dates styles
  formContainer: {
    background: colors.background,
    padding: spacing.lg,
    borderRadius: radius.lg,
    marginBottom: spacing.lg,
    border: `1px solid ${colors.border}`,
  },
  formGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: spacing.md,
  },
  formGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  select: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    outline: 'none',
    background: colors.surface,
    color: colors.text,
    cursor: 'pointer',
  },
  previewCard: {
    padding: spacing.sm,
    background: colors.background,
    borderRadius: radius.md,
    border: `1px solid ${colors.borderLight}`,
    minWidth: '150px',
  },
  actionButton: {
    background: 'transparent',
    border: 'none',
    padding: spacing.xs,
    cursor: 'pointer',
    fontSize: typography.sm,
    fontWeight: typography.medium,
  },
  // Settings grid styles
  settingsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
    gap: spacing.md,
    marginBottom: spacing.md,
  },
  settingItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
  },
  settingLabel: {
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.text,
    display: 'flex',
    alignItems: 'center',
    gap: spacing.xs,
  },
  settingInput: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    background: colors.surface,
    color: colors.text,
    width: '100%',
  },
  settingSelect: {
    padding: spacing.sm,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    background: colors.surface,
    color: colors.text,
    cursor: 'pointer',
  },
  settingHint: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  trainControlRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: spacing.md,
    alignItems: 'flex-end',
    marginBottom: spacing.md,
  },
  trainControl: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.xs,
    minWidth: '200px',
  },
  trainingProgress: {
    background: colors.background,
    padding: spacing.md,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
  },
  progressHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
    fontSize: typography.sm,
    color: colors.text,
  },
  progressStatus: {
    fontWeight: typography.medium,
    color: colors.primary,
  },
  progressBarOuter: {
    height: '8px',
    background: colors.borderLight,
    borderRadius: radius.full,
    overflow: 'hidden',
  },
  progressBarInner: {
    height: '100%',
    background: colors.primary,
    transition: 'width 0.3s ease',
  },
  modelsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.md,
  },
  modelCard: {
    background: colors.background,
    padding: spacing.md,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
  },
  modelHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  modelName: {
    fontSize: typography.base,
    fontWeight: typography.semibold,
    color: colors.text,
  },
  modelMeta: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: spacing.md,
    fontSize: typography.sm,
    color: colors.textMuted,
    marginBottom: spacing.sm,
  },
  modelActions: {
    display: 'flex',
    gap: spacing.sm,
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTop: `1px solid ${colors.borderLight}`,
  },
}

export default Settings
