import React, { createContext, useContext, useState, useEffect } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation, Link } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Review from './pages/Review'
import Forecasts from './pages/Forecasts'
import Accuracy from './pages/Accuracy'
import { authApi } from './utils/api'
import { colors, spacing, typography, radius, transitions, buttonStyle, mergeStyles } from './utils/theme'

interface AuthContextType {
  user: { id: number; username: string; display_name: string } | null
  token: string | null
  logout: () => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}

const App: React.FC = () => {
  const [user, setUser] = useState<{ id: number; username: string; display_name: string } | null>(null)
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const validateToken = async () => {
      const storedToken = localStorage.getItem('token')
      if (storedToken) {
        try {
          const userData = await authApi.getMe()
          setUser({ id: userData.id, username: userData.username, display_name: userData.display_name })
          setToken(storedToken)
        } catch {
          localStorage.removeItem('token')
          setToken(null)
          setUser(null)
        }
      }
      setLoading(false)
    }
    validateToken()
  }, [])

  const handleLogin = (newToken: string, userData: { id: number; username: string; display_name: string }) => {
    setToken(newToken)
    setUser(userData)
    localStorage.setItem('token', newToken)
  }

  const logout = () => {
    setToken(null)
    setUser(null)
    localStorage.removeItem('token')
  }

  if (loading) {
    return (
      <div style={styles.loading}>
        <div style={styles.spinner} />
      </div>
    )
  }

  return (
    <AuthContext.Provider value={{ user, token, logout }}>
      <div style={styles.app}>
        {token && user && <Header />}
        <main style={styles.main}>
          <Routes>
            <Route
              path="/login"
              element={token ? <Navigate to="/" /> : <Login onLogin={handleLogin} />}
            />
            <Route
              path="/"
              element={token ? <Dashboard /> : <Navigate to="/login" />}
            />
            <Route
              path="/settings"
              element={token ? <Settings /> : <Navigate to="/login" />}
            />
            <Route
              path="/review"
              element={token ? <Review /> : <Navigate to="/login" />}
            />
            <Route
              path="/review/:reportId"
              element={token ? <Review /> : <Navigate to="/login" />}
            />
            <Route
              path="/forecasts"
              element={token ? <Forecasts /> : <Navigate to="/login" />}
            />
            <Route
              path="/forecasts/:forecastId"
              element={token ? <Forecasts /> : <Navigate to="/login" />}
            />
            <Route
              path="/accuracy"
              element={token ? <Accuracy /> : <Navigate to="/login" />}
            />
            <Route path="*" element={<Navigate to="/" />} />
          </Routes>
        </main>
      </div>
    </AuthContext.Provider>
  )
}

const Header: React.FC = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const navItems = [
    { path: '/', label: 'Dashboard' },
    { path: '/review', label: 'History' },
    { path: '/forecasts', label: 'Forecasts' },
    { path: '/accuracy', label: 'Accuracy' },
    { path: '/settings', label: 'Settings' },
  ]

  return (
    <header style={styles.header}>
      <div style={styles.headerContent}>
        <div style={styles.logo}>Forecasting</div>
        <nav style={styles.nav}>
          {navItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              style={{
                ...styles.navLink,
                ...(location.pathname === item.path ? styles.navLinkActive : {}),
              }}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div style={styles.userSection}>
          <span style={styles.userName}>{user?.display_name || user?.username}</span>
          <button onClick={handleLogout} style={styles.logoutButton}>
            Logout
          </button>
        </div>
      </div>
    </header>
  )
}

const styles: Record<string, React.CSSProperties> = {
  app: {
    minHeight: '100vh',
    display: 'flex',
    flexDirection: 'column',
    background: colors.background,
  },
  main: {
    flex: 1,
  },
  loading: {
    minHeight: '100vh',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    background: colors.background,
  },
  spinner: {
    width: '40px',
    height: '40px',
    border: `3px solid ${colors.borderLight}`,
    borderTop: `3px solid ${colors.primary}`,
    borderRadius: radius.full,
    animation: 'spin 1s linear infinite',
  },
  header: {
    background: colors.primary,
    color: colors.textLight,
    position: 'sticky',
    top: 0,
    zIndex: 100,
  },
  headerContent: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: `0 ${spacing.lg}`,
    height: '60px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  logo: {
    fontSize: typography.xl,
    fontWeight: typography.bold,
  },
  nav: {
    display: 'flex',
    gap: spacing.xs,
  },
  navLink: {
    color: 'rgba(255, 255, 255, 0.7)',
    textDecoration: 'none',
    padding: `${spacing.sm} ${spacing.md}`,
    borderRadius: radius.md,
    fontSize: typography.sm,
    fontWeight: typography.medium,
    transition: `all ${transitions.normal}`,
  },
  navLinkActive: {
    color: colors.textLight,
    background: 'rgba(255, 255, 255, 0.1)',
  },
  userSection: {
    display: 'flex',
    alignItems: 'center',
    gap: spacing.md,
  },
  userName: {
    fontSize: typography.sm,
    opacity: 0.9,
  },
  logoutButton: mergeStyles(buttonStyle('outline'), {
    color: colors.textLight,
    borderColor: 'rgba(255, 255, 255, 0.3)',
    padding: `${spacing.xs} ${spacing.sm}`,
    fontSize: typography.xs,
  }),
}

export default App
