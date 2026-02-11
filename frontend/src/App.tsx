import React, { createContext, useContext, useState, useEffect } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation, Link } from 'react-router-dom'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Settings from './pages/Settings'
import Review from './pages/Review'
import Forecasts from './pages/Forecasts'
import Accuracy from './pages/Accuracy'
import Bookability from './pages/Bookability'
import Docs from './pages/Docs'
import CompetitorRates from './pages/CompetitorRates'
import Reconciliation from './pages/Reconciliation'
import StaffCashUp from './pages/StaffCashUp'
import { authApi } from './utils/api'
import { colors, spacing, typography, radius, transitions, buttonStyle, mergeStyles } from './utils/theme'

interface AuthContextType {
  user: { id: number; username: string; display_name: string; role?: string } | null
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
  const [user, setUser] = useState<{ id: number; username: string; display_name: string; role?: string } | null>(null)
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'))
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const validateToken = async () => {
      const storedToken = localStorage.getItem('token')
      if (storedToken) {
        try {
          const userData = await authApi.getMe()
          setUser({ id: userData.id, username: userData.username, display_name: userData.display_name, role: userData.role || 'admin' })
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

  const handleLogin = (newToken: string, userData: { id: number; username: string; display_name: string; role?: string }) => {
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

  const isStaff = user?.role === 'staff'
  const defaultRoute = isStaff ? '/staff' : '/'

  // Admin-only route helper
  const adminRoute = (component: React.ReactNode) =>
    !token ? <Navigate to="/login" /> : isStaff ? <Navigate to="/staff" /> : component

  return (
    <AuthContext.Provider value={{ user, token, logout }}>
      <div style={styles.app}>
        {token && user && !isStaff && <Header />}
        {token && user && isStaff && <StaffHeader />}
        <main style={styles.main}>
          <Routes>
            <Route
              path="/login"
              element={token ? <Navigate to={defaultRoute} /> : <Login onLogin={handleLogin} />}
            />
            <Route
              path="/"
              element={adminRoute(<Dashboard />)}
            />
            <Route
              path="/settings"
              element={adminRoute(<Settings />)}
            />
            <Route
              path="/review"
              element={adminRoute(<Review />)}
            />
            <Route
              path="/review/:reportId"
              element={adminRoute(<Review />)}
            />
            <Route
              path="/forecasts"
              element={adminRoute(<Forecasts />)}
            />
            <Route
              path="/forecasts/:forecastId"
              element={adminRoute(<Forecasts />)}
            />
            <Route
              path="/accuracy"
              element={adminRoute(<Accuracy />)}
            />
            <Route
              path="/bookability"
              element={adminRoute(<Bookability />)}
            />
            <Route
              path="/competitor-rates"
              element={adminRoute(<CompetitorRates />)}
            />
            <Route
              path="/reconciliation"
              element={adminRoute(<Reconciliation />)}
            />
            <Route
              path="/reconciliation/:subPage"
              element={adminRoute(<Reconciliation />)}
            />
            <Route
              path="/docs"
              element={adminRoute(<Docs />)}
            />
            <Route
              path="/staff"
              element={token ? <StaffCashUp /> : <Navigate to="/login" />}
            />
            <Route
              path="/staff/:subPage"
              element={token ? <StaffCashUp /> : <Navigate to="/login" />}
            />
            <Route path="*" element={<Navigate to={defaultRoute} />} />
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

  // Simple nav items (no dropdown)
  const simpleNavItems = [
    { path: '/', label: 'Dashboard' },
    { path: '/review', label: 'History' },
  ]

  // Forecasts is now a simple nav item (Accuracy moved to Forecasts sidebar)
  // Keep the structure in case we want to add more items later

  // Remaining simple nav items
  const remainingNavItems = [
    { path: '/bookability', label: 'Bookability' },
    { path: '/competitor-rates', label: 'Competitors' },
    { path: '/reconciliation', label: 'Reconciliation' },
    { path: '/settings', label: 'Settings' },
    { path: '/docs', label: 'Docs' },
  ]

  return (
    <header style={styles.header}>
      <div style={styles.headerContent}>
        <div style={styles.logo}>Finance</div>
        <nav style={styles.nav}>
          {simpleNavItems.map((item) => (
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
          <Link
            to="/forecasts"
            style={{
              ...styles.navLink,
              ...(location.pathname.startsWith('/forecasts') ? styles.navLinkActive : {}),
            }}
          >
            Forecasts
          </Link>
          {remainingNavItems.map((item) => (
            <Link
              key={item.path}
              to={item.path}
              style={{
                ...styles.navLink,
                ...((item.path === '/reconciliation'
                  ? location.pathname.startsWith('/reconciliation')
                  : location.pathname === item.path) ? styles.navLinkActive : {}),
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

const StaffHeader: React.FC = () => {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <header style={styles.header}>
      <div style={styles.headerContent}>
        <div style={styles.logo}>Cash Up</div>
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
