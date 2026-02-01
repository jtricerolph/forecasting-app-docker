import React from 'react'

// Color palette
export const colors = {
  // Primary
  primary: '#1a1a2e',
  primaryLight: '#2d2d44',
  primaryDark: '#16213e',

  // Accent
  accent: '#e94560',
  accentHover: '#d63d56',

  // Backgrounds
  background: '#f5f5f5',
  surface: '#ffffff',
  surfaceHover: '#fafafa',

  // Text
  text: '#1a1a2e',
  textSecondary: '#666666',
  textMuted: '#999999',
  textLight: '#ffffff',

  // Borders
  border: '#e0e0e0',
  borderLight: '#eeeeee',
  borderFocus: '#1a1a2e',

  // Status
  success: '#22c55e',
  successBg: '#dcfce7',
  warning: '#f59e0b',
  warningBg: '#fef3c7',
  error: '#dc2626',
  errorBg: '#fee2e2',
  info: '#3b82f6',
  infoBg: '#dbeafe',
}

// Spacing scale
export const spacing = {
  xs: '0.25rem',
  sm: '0.5rem',
  md: '1rem',
  lg: '1.5rem',
  xl: '2rem',
  xxl: '3rem',
}

// Border radius
export const radius = {
  sm: '4px',
  md: '6px',
  lg: '8px',
  xl: '12px',
  full: '9999px',
}

// Shadows
export const shadows = {
  sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
  md: '0 2px 8px rgba(0, 0, 0, 0.08)',
  lg: '0 4px 20px rgba(0, 0, 0, 0.12)',
  xl: '0 10px 40px rgba(0, 0, 0, 0.2)',
}

// Typography
export const typography = {
  fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",

  // Font sizes
  xs: '0.75rem',
  sm: '0.875rem',
  base: '1rem',
  lg: '1.125rem',
  xl: '1.25rem',
  xxl: '1.5rem',
  xxxl: '1.75rem',
  display: '2.5rem',

  // Font weights
  normal: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
}

// Transitions
export const transitions = {
  fast: '0.1s ease',
  normal: '0.2s ease',
  slow: '0.3s ease',
}

// Common component styles
export const components: Record<string, React.CSSProperties> = {
  // Buttons
  buttonBase: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
    padding: `${spacing.sm} ${spacing.md}`,
    borderRadius: radius.md,
    fontSize: typography.sm,
    fontWeight: typography.semibold,
    cursor: 'pointer',
    transition: `background ${transitions.normal}, transform ${transitions.fast}`,
    border: 'none',
    outline: 'none',
  },
  buttonPrimary: {
    background: colors.accent,
    color: colors.textLight,
  },
  buttonSecondary: {
    background: colors.primary,
    color: colors.textLight,
  },
  buttonOutline: {
    background: 'transparent',
    color: colors.primary,
    border: `1px solid ${colors.border}`,
  },
  buttonGhost: {
    background: 'transparent',
    color: colors.text,
  },
  buttonSmall: {
    padding: `${spacing.xs} ${spacing.sm}`,
    fontSize: typography.xs,
  },
  buttonLarge: {
    padding: `${spacing.md} ${spacing.lg}`,
    fontSize: typography.base,
  },

  // Cards
  card: {
    background: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.lg,
    boxShadow: shadows.md,
  },
  cardHover: {
    transition: `transform ${transitions.normal}, box-shadow ${transitions.normal}`,
  },

  // Inputs
  input: {
    width: '100%',
    padding: `${spacing.sm} ${spacing.md}`,
    borderRadius: radius.md,
    border: `1px solid ${colors.border}`,
    fontSize: typography.base,
    outline: 'none',
    transition: `border-color ${transitions.normal}`,
  },
  inputLabel: {
    display: 'block',
    marginBottom: spacing.xs,
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.text,
  },

  // Typography
  title: {
    fontSize: typography.xxxl,
    fontWeight: typography.bold,
    color: colors.text,
    margin: 0,
  },
  subtitle: {
    fontSize: typography.base,
    color: colors.textSecondary,
    margin: 0,
  },
  heading: {
    fontSize: typography.xl,
    fontWeight: typography.semibold,
    color: colors.text,
    margin: 0,
  },
  label: {
    fontSize: typography.xs,
    fontWeight: typography.medium,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },

  // Status badges
  badge: {
    display: 'inline-flex',
    alignItems: 'center',
    padding: `${spacing.xs} ${spacing.sm}`,
    borderRadius: radius.full,
    fontSize: typography.xs,
    fontWeight: typography.medium,
  },
  badgeSuccess: {
    background: colors.successBg,
    color: colors.success,
  },
  badgeWarning: {
    background: colors.warningBg,
    color: colors.warning,
  },
  badgeError: {
    background: colors.errorBg,
    color: colors.error,
  },
  badgeInfo: {
    background: colors.infoBg,
    color: colors.info,
  },

  // Dividers
  divider: {
    height: '1px',
    background: colors.borderLight,
    border: 'none',
    margin: `${spacing.md} 0`,
  },

  // Status indicator (left border)
  statusBorder: {
    borderLeft: '4px solid',
    paddingLeft: spacing.md,
  },
}

// Helper to merge styles
export const mergeStyles = (...styles: (React.CSSProperties | undefined)[]): React.CSSProperties => {
  return Object.assign({}, ...styles.filter(Boolean))
}

// Helper to create button style with variant
export const buttonStyle = (
  variant: 'primary' | 'secondary' | 'outline' | 'ghost' = 'primary',
  size: 'small' | 'medium' | 'large' = 'medium'
): React.CSSProperties => {
  const variantStyles = {
    primary: components.buttonPrimary,
    secondary: components.buttonSecondary,
    outline: components.buttonOutline,
    ghost: components.buttonGhost,
  }
  const sizeStyles = {
    small: components.buttonSmall,
    medium: {},
    large: components.buttonLarge,
  }
  return mergeStyles(components.buttonBase, variantStyles[variant], sizeStyles[size])
}

// Helper to create badge style with status
export const badgeStyle = (
  status: 'success' | 'warning' | 'error' | 'info' = 'info'
): React.CSSProperties => {
  const statusStyles = {
    success: components.badgeSuccess,
    warning: components.badgeWarning,
    error: components.badgeError,
    info: components.badgeInfo,
  }
  return mergeStyles(components.badge, statusStyles[status])
}
