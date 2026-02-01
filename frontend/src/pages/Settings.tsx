import React, { useState } from 'react'
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

type SettingsPage = 'newbook' | 'users' | 'database' | 'special-dates' | 'tft-training'

const Settings: React.FC = () => {
  const [activePage, setActivePage] = useState<SettingsPage>('newbook')

  const menuItems: { id: SettingsPage; label: string }[] = [
    { id: 'newbook', label: 'Newbook' },
    { id: 'special-dates', label: 'Special Dates' },
    { id: 'tft-training', label: 'TFT Training' },
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
        {activePage === 'special-dates' && <SpecialDatesPage />}
        {activePage === 'tft-training' && <TFTTrainingPage />}
        {activePage === 'users' && <UsersPage />}
        {activePage === 'database' && <DatabasePage />}
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

  // Update a single category
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
              <label key={cat.id} style={styles.roomCategoryItem}>
                <input
                  type="checkbox"
                  checked={cat.is_included}
                  onChange={() => handleToggle(cat)}
                  style={styles.checkbox}
                />
                <span style={styles.roomCategoryName}>{cat.site_name}</span>
                <span style={styles.roomCategoryCount}>{cat.room_count} rooms</span>
              </label>
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
// TFT TRAINING PAGE
// ============================================

interface TFTSettings {
  encoder_length: number
  prediction_length: number
  hidden_size: number
  attention_heads: number
  learning_rate: number
  batch_size: number
  max_epochs: number
  training_days: number
  dropout: number
  use_gpu: boolean
  auto_retrain: boolean
  use_cached_model: boolean
  use_special_dates: boolean
  use_otb_data: boolean
  early_stop_patience: number
  early_stop_min_delta: number
  cpu_threads: number
}

interface TFTModel {
  id: number
  metric_code: string
  model_name: string
  file_path: string | null
  file_size_bytes: number | null
  trained_at: string
  training_config: Record<string, number | boolean>
  training_time_seconds: number | null
  validation_loss: number | null
  epochs_completed: number | null
  is_active: boolean
  created_by: string | null
  notes: string | null
}

interface TrainingJob {
  job_id: string
  metric_code: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  started_at: string | null
  completed_at: string | null
  progress_pct: number
  current_epoch: number
  total_epochs: number
  error_message: string | null
}

const TFTTrainingPage: React.FC = () => {
  const queryClient = useQueryClient()
  const [settings, setSettings] = useState<TFTSettings | null>(null)
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [trainingJob, setTrainingJob] = useState<TrainingJob | null>(null)
  const [selectedMetric, setSelectedMetric] = useState('hotel_occupancy_pct')
  const [modelName, setModelName] = useState('')
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'success' | 'error'>('idle')
  const [uploadMessage, setUploadMessage] = useState('')
  const fileInputRef = React.useRef<HTMLInputElement>(null)

  // Fetch TFT settings
  const { data: settingsData, isLoading: settingsLoading } = useQuery<TFTSettings>({
    queryKey: ['tft-settings'],
    queryFn: async () => {
      const response = await fetch('/api/config/tft-settings', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) throw new Error('Failed to fetch settings')
      return response.json()
    },
  })

  // Fetch TFT models
  const { data: models, isLoading: modelsLoading, refetch: refetchModels } = useQuery<TFTModel[]>({
    queryKey: ['tft-models'],
    queryFn: async () => {
      const response = await fetch('/api/config/tft-models', {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (!response.ok) return []
      return response.json()
    },
  })

  // Update local state when settings load
  React.useEffect(() => {
    if (settingsData) {
      setSettings(settingsData)
    }
  }, [settingsData])

  // Poll training job status
  React.useEffect(() => {
    if (trainingJob && ['pending', 'running'].includes(trainingJob.status)) {
      const interval = setInterval(async () => {
        try {
          const response = await fetch(`/api/config/tft-models/training-status/${trainingJob.job_id}`, {
            headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
          })
          if (response.ok) {
            const job: TrainingJob = await response.json()
            setTrainingJob(job)
            if (['completed', 'failed'].includes(job.status)) {
              clearInterval(interval)
              refetchModels()
            }
          }
        } catch {
          // Ignore polling errors
        }
      }, 2000)
      return () => clearInterval(interval)
    }
  }, [trainingJob, refetchModels])

  // Save settings
  const handleSaveSettings = async () => {
    if (!settings) return
    setSaveStatus('saving')
    try {
      const response = await fetch('/api/config/tft-settings', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify(settings)
      })
      if (response.ok) {
        setSaveStatus('saved')
        queryClient.invalidateQueries({ queryKey: ['tft-settings'] })
        setTimeout(() => setSaveStatus('idle'), 2000)
      } else {
        setSaveStatus('error')
        setTimeout(() => setSaveStatus('idle'), 3000)
      }
    } catch {
      setSaveStatus('error')
      setTimeout(() => setSaveStatus('idle'), 3000)
    }
  }

  // Start training
  const handleStartTraining = async () => {
    try {
      const name = modelName || `model_${new Date().toISOString().slice(0, 10)}`
      const response = await fetch('/api/config/tft-models/train', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('token')}`
        },
        body: JSON.stringify({ metric_code: selectedMetric, model_name: name })
      })
      if (response.ok) {
        const data = await response.json()
        setTrainingJob({
          job_id: data.job_id,
          metric_code: selectedMetric,
          status: 'pending',
          started_at: null,
          completed_at: null,
          progress_pct: 0,
          current_epoch: 0,
          total_epochs: settings?.max_epochs || 100,
          error_message: null
        })
        setModelName('')
      }
    } catch (err) {
      console.error('Failed to start training', err)
    }
  }

  // Download model
  const handleDownloadModel = async (model: TFTModel) => {
    try {
      const response = await fetch(`/api/config/tft-models/${model.id}/download`, {
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      if (response.ok) {
        const blob = await response.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${model.metric_code}_${model.model_name}.pt`
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch (err) {
      console.error('Failed to download model', err)
    }
  }

  // Upload model
  const handleUploadModel = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setUploadStatus('uploading')
    setUploadMessage('')

    const formData = new FormData()
    formData.append('file', file)
    formData.append('metric_code', selectedMetric)
    formData.append('model_name', modelName || `imported_${new Date().toISOString().slice(0, 10)}`)

    try {
      const response = await fetch('/api/config/tft-models/upload', {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` },
        body: formData
      })
      if (response.ok) {
        setUploadStatus('success')
        setUploadMessage('Model uploaded successfully')
        refetchModels()
        setModelName('')
      } else {
        const data = await response.json()
        setUploadStatus('error')
        setUploadMessage(data.detail || 'Upload failed')
      }
    } catch {
      setUploadStatus('error')
      setUploadMessage('Upload failed')
    }
    setTimeout(() => {
      setUploadStatus('idle')
      setUploadMessage('')
    }, 3000)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  // Activate model
  const handleActivateModel = async (model: TFTModel) => {
    try {
      await fetch(`/api/config/tft-models/${model.id}/activate`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      refetchModels()
    } catch (err) {
      console.error('Failed to activate model', err)
    }
  }

  // Delete model
  const handleDeleteModel = async (model: TFTModel) => {
    if (!confirm(`Delete model "${model.model_name}"?`)) return
    try {
      await fetch(`/api/config/tft-models/${model.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${localStorage.getItem('token')}` }
      })
      refetchModels()
    } catch (err) {
      console.error('Failed to delete model', err)
    }
  }

  const formatBytes = (bytes: number | null) => {
    if (!bytes) return '-'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  }

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return '-'
    if (seconds < 60) return `${seconds}s`
    return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  }

  return (
    <div style={styles.pageContent}>
      <h2 style={styles.pageTitle}>TFT Model Training</h2>
      <p style={styles.pageSubtitle}>
        Configure and train Temporal Fusion Transformer models for forecasting.
        Trained models can be exported and imported between machines.
      </p>

      {/* Settings Section */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Training Hyperparameters</h3>

        {settingsLoading ? (
          <div style={styles.loading}>Loading settings...</div>
        ) : settings ? (
          <>
            <div style={styles.settingsGrid}>
              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="How many days of past data the model looks at when making a prediction. Longer = more context but slower training. 90 days captures quarterly patterns.">Encoder Length</label>
                <input
                  type="number"
                  value={settings.encoder_length}
                  onChange={(e) => setSettings({ ...settings, encoder_length: parseInt(e.target.value) || 60 })}
                  style={styles.settingInput}
                  min={30}
                  max={180}
                />
                <span style={styles.settingHint}>Days of historical context</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Size of the neural network's hidden layers. Larger = more capacity to learn complex patterns but requires more data and training time. 64 is a good balance for most datasets.">Hidden Size</label>
                <select
                  value={settings.hidden_size}
                  onChange={(e) => setSettings({ ...settings, hidden_size: parseInt(e.target.value) })}
                  style={styles.settingSelect}
                >
                  <option value={32}>32 (Fast)</option>
                  <option value={64}>64 (Balanced)</option>
                  <option value={128}>128 (Accurate)</option>
                </select>
                <span style={styles.settingHint}>Model complexity</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Maximum number of training passes through the data. Training will stop earlier if early stopping triggers. Higher values allow more learning but increase training time.">Max Epochs</label>
                <input
                  type="number"
                  value={settings.max_epochs}
                  onChange={(e) => setSettings({ ...settings, max_epochs: parseInt(e.target.value) || 100 })}
                  style={styles.settingInput}
                  min={10}
                  max={500}
                />
                <span style={styles.settingHint}>Training iterations (ceiling)</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Number of epochs to wait for improvement before stopping. Higher values = train longer but risk overfitting. Lower values = stop sooner but might miss optimal performance. 10-20 is typical.">Early Stop Patience</label>
                <input
                  type="number"
                  value={settings.early_stop_patience ?? 10}
                  onChange={(e) => setSettings({ ...settings, early_stop_patience: parseInt(e.target.value) || 10 })}
                  style={styles.settingInput}
                  min={3}
                  max={50}
                />
                <span style={styles.settingHint}>Epochs without improvement before stopping</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Minimum reduction in validation loss to count as improvement. Smaller values = more sensitive to tiny improvements (trains longer). Larger values = only count significant improvements (stops sooner).">Early Stop Min Delta</label>
                <select
                  value={settings.early_stop_min_delta ?? 0.0001}
                  onChange={(e) => setSettings({ ...settings, early_stop_min_delta: parseFloat(e.target.value) })}
                  style={styles.settingSelect}
                >
                  <option value={0.00001}>0.00001 (Very sensitive)</option>
                  <option value={0.0001}>0.0001 (Default)</option>
                  <option value={0.001}>0.001 (Less sensitive)</option>
                  <option value={0.01}>0.01 (Least sensitive)</option>
                </select>
                <span style={styles.settingHint}>Minimum loss improvement to count</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="How fast the model learns. Lower = slower but more stable learning, less likely to overshoot. Higher = faster training but might miss optimal weights. 0.001 is a safe default.">Learning Rate</label>
                <select
                  value={settings.learning_rate}
                  onChange={(e) => setSettings({ ...settings, learning_rate: parseFloat(e.target.value) })}
                  style={styles.settingSelect}
                >
                  <option value={0.0001}>0.0001 (Slow)</option>
                  <option value={0.001}>0.001 (Default)</option>
                  <option value={0.01}>0.01 (Fast)</option>
                </select>
                <span style={styles.settingHint}>Training speed</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Number of samples processed before updating model weights. Larger batches = faster training, more memory usage, smoother gradients. Smaller batches = slower, less memory, more noise (can help escape local minima).">Batch Size</label>
                <select
                  value={settings.batch_size}
                  onChange={(e) => setSettings({ ...settings, batch_size: parseInt(e.target.value) })}
                  style={styles.settingSelect}
                >
                  <option value={32}>32</option>
                  <option value={64}>64</option>
                  <option value={128}>128</option>
                  <option value={256}>256</option>
                </select>
                <span style={styles.settingHint}>Samples per batch</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="How many days of historical data to use for training. More data = better seasonality capture but longer training. 2555 days (~7 years) captures multi-year trends. Minimum 365 for yearly patterns.">Training Days</label>
                <input
                  type="number"
                  value={settings.training_days}
                  onChange={(e) => setSettings({ ...settings, training_days: parseInt(e.target.value) || 2555 })}
                  style={styles.settingInput}
                  min={365}
                  max={3650}
                />
                <span style={styles.settingHint}>Historical data to use</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Use NVIDIA GPU for training if available. Significantly faster for large models/datasets. Requires CUDA-compatible GPU and drivers. Falls back to CPU if unavailable.">
                  <input
                    type="checkbox"
                    checked={settings.use_gpu}
                    onChange={(e) => setSettings({ ...settings, use_gpu: e.target.checked })}
                    style={styles.checkbox}
                  />
                  Use GPU
                </label>
                <span style={styles.settingHint}>CUDA acceleration if available</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Maximum CPU threads for training. Lower values prevent container lockup during training but train slower. Higher values train faster but may impact other services. 2-4 is recommended for shared containers.">CPU Threads</label>
                <select
                  value={settings.cpu_threads ?? 2}
                  onChange={(e) => setSettings({ ...settings, cpu_threads: parseInt(e.target.value) })}
                  style={styles.settingSelect}
                >
                  <option value={1}>1 (Minimal)</option>
                  <option value={2}>2 (Recommended)</option>
                  <option value={4}>4 (Faster)</option>
                  <option value={8}>8 (Fast, high resource use)</option>
                </select>
                <span style={styles.settingHint}>Prevents container lockup during training</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="When enabled, TFT preview uses the active trained model instead of training a new one. Much faster for previews. Disable to always train fresh (slower but uses current settings).">
                  <input
                    type="checkbox"
                    checked={settings.use_cached_model}
                    onChange={(e) => setSettings({ ...settings, use_cached_model: e.target.checked })}
                    style={styles.checkbox}
                  />
                  Use Cached Model
                </label>
                <span style={styles.settingHint}>Use trained model for previews</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Include holidays and special events (from Settings > Special Dates) as model features. Helps capture demand spikes around holidays. Model trained with this must have matching data at inference time.">
                  <input
                    type="checkbox"
                    checked={settings.use_special_dates}
                    onChange={(e) => setSettings({ ...settings, use_special_dates: e.target.checked })}
                    style={styles.checkbox}
                  />
                  Include Special Dates
                </label>
                <span style={styles.settingHint}>Use holidays/events from Settings as features</span>
              </div>

              <div style={styles.settingItem}>
                <label style={styles.settingLabel} title="Include On-The-Books booking data (reservations at 30d, 14d, 7d out) as features. Helps model learn pickup patterns and improve short-term accuracy. Requires booking_pace data to be populated.">
                  <input
                    type="checkbox"
                    checked={settings.use_otb_data}
                    onChange={(e) => setSettings({ ...settings, use_otb_data: e.target.checked })}
                    style={styles.checkbox}
                  />
                  Include OTB Data
                </label>
                <span style={styles.settingHint}>Use On-The-Books pickup patterns as features</span>
              </div>
            </div>

            <div style={styles.buttonRow}>
              <button
                onClick={handleSaveSettings}
                disabled={saveStatus === 'saving'}
                style={mergeStyles(
                  buttonStyle('primary'),
                  saveStatus === 'saved' ? { background: colors.success } : {}
                )}
              >
                {saveStatus === 'saving' ? 'Saving...' : saveStatus === 'saved' ? 'Saved!' : 'Save Settings'}
              </button>
            </div>
          </>
        ) : null}
      </div>

      {/* Training Section */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Train Model</h3>

        <div style={styles.trainControlRow}>
          <div style={styles.trainControl}>
            <label style={styles.settingLabel}>Metric</label>
            <select
              value={selectedMetric}
              onChange={(e) => setSelectedMetric(e.target.value)}
              style={styles.settingSelect}
              disabled={!!(trainingJob && ['pending', 'running'].includes(trainingJob.status))}
            >
              <option value="hotel_occupancy_pct">Hotel Occupancy %</option>
              <option value="hotel_room_nights">Hotel Room Nights</option>
            </select>
          </div>

          <div style={styles.trainControl}>
            <label style={styles.settingLabel}>Model Name (optional)</label>
            <input
              type="text"
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="e.g., weekly_retrain"
              style={styles.settingInput}
              disabled={!!(trainingJob && ['pending', 'running'].includes(trainingJob.status))}
            />
          </div>

          <button
            onClick={handleStartTraining}
            disabled={!!(trainingJob && ['pending', 'running'].includes(trainingJob.status))}
            style={buttonStyle('primary')}
          >
            {trainingJob && ['pending', 'running'].includes(trainingJob.status)
              ? 'Training...'
              : 'Start Training'}
          </button>
        </div>

        {trainingJob && (
          <div style={styles.trainingProgress}>
            <div style={styles.progressHeader}>
              <span>Training {trainingJob.metric_code}</span>
              <span style={styles.progressStatus}>
                {trainingJob.status === 'completed' ? 'Completed' :
                 trainingJob.status === 'failed' ? 'Failed' :
                 `Epoch ${trainingJob.current_epoch}/${trainingJob.total_epochs}`}
              </span>
            </div>
            <div style={styles.progressBarOuter}>
              <div
                style={{
                  ...styles.progressBarInner,
                  width: `${trainingJob.progress_pct}%`,
                  background: trainingJob.status === 'failed' ? colors.error :
                              trainingJob.status === 'completed' ? colors.success : colors.primary
                }}
              />
            </div>
            {trainingJob.error_message && (
              <div style={{ color: colors.error, marginTop: spacing.xs }}>{trainingJob.error_message}</div>
            )}
          </div>
        )}
      </div>

      {/* Import/Export Section */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Import Model</h3>
        <p style={styles.hint}>Import a trained model from another machine.</p>

        <div style={styles.buttonRow}>
          <input
            ref={fileInputRef}
            type="file"
            accept=".pt"
            onChange={handleUploadModel}
            style={{ display: 'none' }}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadStatus === 'uploading'}
            style={buttonStyle('outline')}
          >
            {uploadStatus === 'uploading' ? 'Uploading...' : 'Upload Model (.pt)'}
          </button>
          {uploadMessage && (
            <span style={{
              color: uploadStatus === 'success' ? colors.success : colors.error,
              marginLeft: spacing.sm
            }}>
              {uploadMessage}
            </span>
          )}
        </div>
      </div>

      {/* Models List Section */}
      <div style={styles.subsection}>
        <h3 style={styles.subsectionTitle}>Saved Models</h3>

        {modelsLoading ? (
          <div style={styles.loading}>Loading models...</div>
        ) : models && models.length > 0 ? (
          <div style={styles.modelsList}>
            {models.map((model) => (
              <div key={model.id} style={styles.modelCard}>
                <div style={styles.modelHeader}>
                  <span style={styles.modelName}>{model.model_name}</span>
                  {model.is_active && (
                    <span style={{ ...badgeStyle('success'), marginLeft: spacing.xs }}>Active</span>
                  )}
                </div>
                <div style={styles.modelMeta}>
                  <span>Metric: {model.metric_code}</span>
                  <span>Size: {formatBytes(model.file_size_bytes)}</span>
                  <span>Training: {formatDuration(model.training_time_seconds)}</span>
                  {model.validation_loss && <span>Loss: {model.validation_loss.toFixed(4)}</span>}
                  {model.epochs_completed && <span>Epochs: {model.epochs_completed}</span>}
                </div>
                <div style={styles.modelMeta}>
                  <span>Trained: {new Date(model.trained_at).toLocaleString()}</span>
                  {model.created_by && <span>By: {model.created_by}</span>}
                </div>
                <div style={styles.modelMeta}>
                  <span>Features: </span>
                  {model.training_config?.use_special_dates !== false && (
                    <span style={{ ...badgeStyle('info'), marginRight: spacing.xs }}>Special Dates</span>
                  )}
                  {model.training_config?.use_otb_data && (
                    <span style={{ ...badgeStyle('info'), marginRight: spacing.xs }}>OTB Data</span>
                  )}
                  {!model.training_config?.use_special_dates && !model.training_config?.use_otb_data && (
                    <span style={{ color: colors.textMuted }}>Base features only</span>
                  )}
                </div>
                <div style={styles.modelActions}>
                  <button
                    onClick={() => handleDownloadModel(model)}
                    style={buttonStyle('outline')}
                  >
                    Export
                  </button>
                  {!model.is_active && (
                    <button
                      onClick={() => handleActivateModel(model)}
                      style={buttonStyle('outline')}
                    >
                      Activate
                    </button>
                  )}
                  {!model.is_active && (
                    <button
                      onClick={() => handleDeleteModel(model)}
                      style={{ ...buttonStyle('outline'), color: colors.error, borderColor: colors.error }}
                    >
                      Delete
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={styles.emptyState}>
            No trained models yet. Train a model or import one to get started.
          </div>
        )}
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
  const [newUser, setNewUser] = useState({ username: '', password: '', display_name: '' })
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
      setNewUser({ username: '', password: '', display_name: '' })
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
        Browse and manage the database using Adminer. Login with: Server: <strong>db</strong>, Username: <strong>forecast</strong>, Password: <strong>forecast_secret</strong>, Database: <strong>forecast</strong>
      </p>

      <div style={styles.iframeContainer}>
        <iframe
          src="/adminer/?pgsql=db&username=forecast&db=forecast"
          style={styles.iframe}
          title="Database Browser"
        />
      </div>
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
  // TFT Training styles
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
