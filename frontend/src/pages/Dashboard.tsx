import React from 'react'
import { spacing, typography, components, mergeStyles } from '../utils/theme'

const Dashboard: React.FC = () => {
  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={components.title}>Dashboard</h1>
        <p style={components.subtitle}>Welcome to the Forecasting System</p>
      </div>

      <div style={styles.content}>
        <div style={mergeStyles(components.card, { textAlign: 'center' })}>
          <div style={styles.cardIcon}>📊</div>
          <h3 style={components.heading}>Ready for Features</h3>
          <p style={mergeStyles(components.subtitle, { marginTop: spacing.sm })}>
            This is a clean starting point. Features will be added incrementally.
          </p>
        </div>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    padding: spacing.xl,
    maxWidth: '1400px',
    margin: '0 auto',
  },
  header: {
    marginBottom: spacing.xl,
  },
  content: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
    gap: spacing.lg,
  },
  cardIcon: {
    fontSize: typography.display,
    marginBottom: spacing.md,
  },
}

export default Dashboard
