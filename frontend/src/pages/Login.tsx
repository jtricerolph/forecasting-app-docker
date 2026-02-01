import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { authApi } from '../utils/api'
import { colors, spacing, radius, shadows, typography, components, buttonStyle, mergeStyles } from '../utils/theme'

interface LoginProps {
  onLogin: (token: string, user: { id: number; username: string; display_name: string }) => void
}

const Login: React.FC<LoginProps> = ({ onLogin }) => {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const loginResponse = await authApi.login(username, password)
      localStorage.setItem('token', loginResponse.access_token)

      const user = await authApi.getMe()
      onLogin(loginResponse.access_token, { id: user.id, username: user.username, display_name: user.display_name })
      navigate('/')
    } catch {
      setError('Invalid username or password')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <h1 style={components.title}>Forecasting</h1>
        <p style={mergeStyles(components.subtitle, { marginBottom: spacing.xl, textAlign: 'center' })}>
          Sign in to continue
        </p>

        <form onSubmit={handleSubmit} style={styles.form}>
          {error && <div style={styles.error}>{error}</div>}

          <div style={styles.inputGroup}>
            <label style={components.inputLabel}>Username</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              style={components.input}
              placeholder="Enter username"
              required
              autoFocus
            />
          </div>

          <div style={styles.inputGroup}>
            <label style={components.inputLabel}>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={components.input}
              placeholder="Enter password"
              required
            />
          </div>

          <button
            type="submit"
            style={mergeStyles(
              buttonStyle('primary', 'large'),
              { width: '100%', marginTop: spacing.sm },
              loading ? { opacity: 0.7, cursor: 'not-allowed' } : {}
            )}
            disabled={loading}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: `linear-gradient(135deg, ${colors.primary} 0%, ${colors.primaryDark} 50%, #0f3460 100%)`,
    padding: spacing.md,
  },
  card: {
    background: colors.surface,
    borderRadius: radius.xl,
    padding: spacing.xl,
    width: '100%',
    maxWidth: '400px',
    boxShadow: shadows.xl,
    textAlign: 'center',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: spacing.lg,
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
    textAlign: 'left',
  },
  error: {
    background: colors.errorBg,
    color: colors.error,
    padding: spacing.sm,
    borderRadius: radius.md,
    fontSize: typography.sm,
    textAlign: 'center',
  },
}

export default Login
