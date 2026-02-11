import React from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { CashUpPage, FloatCountPage } from './Reconciliation'
import { colors, spacing, radius, typography, shadows } from '../utils/theme'

// ============================================
// TYPES
// ============================================

type StaffPage = 'cash-up' | 'petty-cash' | 'change-tin'

interface MenuGroup {
  group: string
  items: { id: StaffPage; label: string }[]
}

// ============================================
// MAIN COMPONENT
// ============================================

const StaffCashUp: React.FC = () => {
  const { subPage } = useParams<{ subPage?: string }>()
  const navigate = useNavigate()
  const activePage = (subPage as StaffPage) || 'cash-up'

  const menuGroups: MenuGroup[] = [
    {
      group: 'Daily',
      items: [
        { id: 'cash-up', label: 'Cash Up' },
      ]
    },
    {
      group: 'Floats',
      items: [
        { id: 'petty-cash', label: 'Petty Cash' },
        { id: 'change-tin', label: 'Change Tin' },
      ]
    }
  ]

  const handlePageChange = (id: StaffPage) => {
    navigate(id === 'cash-up' ? '/staff' : `/staff/${id}`)
  }

  return (
    <div style={styles.layout}>
      <div style={styles.sidebar}>
        <h3 style={styles.sidebarTitle}>Cash Up</h3>
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
        {activePage === 'cash-up' && <CashUpPage canFinalize={false} />}
        {activePage === 'petty-cash' && <FloatCountPage countType="petty_cash" title="Petty Cash" showReceipts={true} />}
        {activePage === 'change-tin' && <FloatCountPage countType="change_tin" title="Change Tin" showReceipts={false} />}
      </main>
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
}

export default StaffCashUp
