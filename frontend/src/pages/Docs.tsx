import React, { useState, useMemo } from 'react'
import { colors, spacing, typography, radius, shadows, transitions } from '../utils/theme'

// Documentation content structured for rendering
const docsContent = {
  overview: {
    title: 'Overview',
    sections: [
      {
        id: 'intro',
        title: 'Introduction',
        content: `The Forecasting App is a comprehensive hotel forecasting system that integrates with Newbook PMS and Resos to provide accurate demand predictions using multiple machine learning models.

Key Features:
- Multi-model forecasting (Prophet, XGBoost, CatBoost, Pickup)
- Historical data analysis and visualization
- Automatic data synchronization
- Model accuracy tracking and comparison
- Budget comparison and variance analysis`
      },
      {
        id: 'tech-stack',
        title: 'Tech Stack',
        content: `Frontend: React 18, TypeScript, Vite, React Query
Backend: FastAPI, Python 3.11, SQLAlchemy
Database: PostgreSQL 15
ML Models: Prophet, XGBoost, CatBoost
Infrastructure: Docker Compose`
      },
      {
        id: 'quick-start',
        title: 'Quick Start',
        content: `1. Start the application: docker-compose up -d
2. Access the frontend: http://localhost:3080
3. Login with default credentials: admin / admin123
4. Configure Newbook/Resos in Settings
5. Run initial data sync
6. View forecasts on the Dashboard`
      }
    ]
  },
  frontend: {
    title: 'Frontend Guide',
    sections: [
      {
        id: 'pages',
        title: 'Application Pages',
        content: `Dashboard (/) - Main overview with key metrics and today's forecasts
History (/review) - Historical data browser with date range selection
Forecasts (/forecasts) - Multi-model forecast comparison and visualization
Accuracy (/accuracy) - Model performance metrics and analysis
Settings (/settings) - System configuration and data management
Docs (/docs) - Documentation and help`
      },
      {
        id: 'navigation',
        title: 'Navigation',
        content: `The application uses a top navigation bar with links to all main sections. The header displays the current user and provides logout functionality.

Routes support URL parameters for deep linking:
- /review/:reportId - Specific report view
- /forecasts/:forecastId - Specific forecast view`
      },
      {
        id: 'charts',
        title: 'Charts & Visualization',
        content: `The app uses two chart libraries:

Chart.js (SimpleChart) - For basic line, bar, and doughnut charts
Plotly.js (DetailChart) - For interactive, detailed visualizations

Chart colors follow a consistent palette:
- Blue (#2196F3) - Prophet model
- Green (#4CAF50) - XGBoost model
- Orange (#FF9800) - Pickup model
- Purple (#9C27B0) - CatBoost model
- Red (#F44336) - Actual values`
      },
      {
        id: 'theme',
        title: 'Theme System',
        content: `The app uses a centralized theme system (utils/theme.ts) providing:

Colors: Primary (#1a1a2e), Accent (#e94560), Status colors
Spacing: 8-point scale (4px, 8px, 16px, 24px, 32px, 48px)
Typography: System fonts with 8 font sizes
Shadows: 4 elevation levels
Transitions: Standard animation timings`
      }
    ]
  },
  backend: {
    title: 'Backend Guide',
    sections: [
      {
        id: 'architecture',
        title: 'Architecture',
        content: `The backend follows a layered architecture:

API Layer (api/) - FastAPI routers handling HTTP requests
Service Layer (services/) - Business logic and ML models
Job Layer (jobs/) - Scheduled background tasks
Data Layer (database.py) - SQLAlchemy ORM configuration

All database operations are async using asyncpg driver.`
      },
      {
        id: 'authentication',
        title: 'Authentication',
        content: `JWT-based authentication with 24-hour token expiry.

Login: POST /api/auth/login with username/password
Token: Returned as access_token, use as Bearer token
Protected: All endpoints except /auth/login require valid token

Password hashing uses bcrypt with 12 rounds.`
      },
      {
        id: 'models',
        title: 'Forecasting Models',
        content: `Prophet - Facebook's time series model with trend, seasonality, and holiday effects. Provides confidence intervals.

XGBoost - Gradient boosting with engineered features (day of week, month, lags, rolling averages). SHAP values for explainability.

CatBoost - Alternative gradient boosting with native categorical handling.

Pickup - Hotel industry pace model using booking lead-time snapshots. Compares current pace to prior year.`
      },
      {
        id: 'jobs',
        title: 'Scheduled Jobs',
        content: `Data syncs run on configurable schedules (default 05:00):
- sync_newbook_bookings - Fetch booking data
- sync_newbook_occupancy - Fetch occupancy report
- sync_newbook_revenue - Fetch earned revenue
- sync_resos - Fetch restaurant bookings

Processing jobs run after syncs:
- aggregate_bookings - Calculate daily stats
- update_metrics - Populate daily_metrics
- run_forecast - Generate predictions
- calculate_accuracy - Compare forecasts to actuals`
      }
    ]
  },
  api: {
    title: 'API Reference',
    sections: [
      {
        id: 'auth-endpoints',
        title: 'Authentication Endpoints',
        content: `POST /api/auth/login
Request: { "username": "string", "password": "string" }
Response: { "access_token": "jwt...", "token_type": "bearer" }

GET /api/auth/me
Response: { "id": 1, "username": "admin", "display_name": "Administrator" }

GET /api/auth/users - List all users
POST /api/auth/users - Create user
DELETE /api/auth/users/{id} - Delete user`
      },
      {
        id: 'forecast-endpoints',
        title: 'Forecast Endpoints',
        content: `GET /api/forecast/daily
Params: from_date, to_date, metric, model
Response: Array of daily forecasts with all models

GET /api/forecast/weekly
Params: weeks (default 8)
Response: Weekly aggregated forecasts

GET /api/forecast/comparison
Params: from_date, to_date, metric (required)
Response: Side-by-side model comparison with actuals

POST /api/forecast/regenerate
Params: from_date, to_date, models[]
Response: Triggers background forecast generation

GET /api/forecast/metrics
Response: List of available forecast metrics`
      },
      {
        id: 'sync-endpoints',
        title: 'Sync Endpoints',
        content: `GET /api/sync/status
Response: Last sync status for all sources

POST /api/sync/newbook
Params: full_sync, from_date, to_date
Response: Triggers booking sync

POST /api/sync/newbook/occupancy-report
Params: from_date, to_date
Response: Triggers occupancy report sync

POST /api/sync/newbook/earned-revenue
Params: from_date, to_date
Response: Triggers revenue sync

POST /api/sync/resos
Params: from_date, to_date
Response: Triggers restaurant booking sync

POST /api/sync/full - Sync all sources
POST /api/sync/aggregate - Run aggregation`
      },
      {
        id: 'historical-endpoints',
        title: 'Historical Data Endpoints',
        content: `GET /api/historical/occupancy
Params: from_date, to_date
Response: Daily occupancy data with rooms, guests, revenue

GET /api/historical/covers
Params: from_date, to_date, service_period
Response: Restaurant covers by service period

GET /api/historical/summary
Params: from_date, to_date
Response: Combined occupancy and covers summary`
      },
      {
        id: 'accuracy-endpoints',
        title: 'Accuracy Endpoints',
        content: `GET /api/accuracy/summary
Params: from_date (required), to_date (required)
Response: MAE, RMSE, MAPE for each model

GET /api/accuracy/by-model
Params: model, from_date, to_date, metric_type
Response: Detailed accuracy for specific model

GET /api/accuracy/by-lead-time
Params: from_date, to_date, metric_code
Response: Accuracy grouped by forecast lead time

GET /api/accuracy/best-model
Params: from_date, to_date
Response: Best model analysis by metric and time`
      },
      {
        id: 'config-endpoints',
        title: 'Configuration Endpoints',
        content: `GET /api/config/settings/newbook - Get Newbook settings
POST /api/config/settings/newbook - Update settings
POST /api/config/settings/newbook/test - Test connection

GET /api/config/room-categories - List room categories
POST /api/config/room-categories/fetch - Fetch from Newbook
PATCH /api/config/room-categories/bulk-update - Update inclusions

GET /api/config/gl-accounts - List GL accounts
POST /api/config/gl-accounts/fetch - Discover from revenue
PATCH /api/config/gl-accounts/bulk-update - Update mappings`
      },
      {
        id: 'special-dates-endpoints',
        title: 'Special Dates Endpoints',
        content: `GET /api/settings/special-dates
Response: List of configured holidays/events

POST /api/settings/special-dates
Body: { name, pattern_type, fixed_month, fixed_day, ... }
Pattern types: fixed, nth_weekday, relative_to_date

PUT /api/settings/special-dates/{id} - Update
DELETE /api/settings/special-dates/{id} - Delete

GET /api/settings/special-dates/resolve
Params: year
Response: Resolved dates for the year`
      }
    ]
  },
  database: {
    title: 'Database Schema',
    sections: [
      {
        id: 'auth-tables',
        title: 'Authentication Tables',
        content: `users - User accounts
- id (PK), username (UNIQUE), password_hash, display_name, is_active, created_at

system_config - Key-value configuration
- id (PK), config_key (UNIQUE), config_value, is_encrypted, description, updated_at`
      },
      {
        id: 'newbook-tables',
        title: 'Newbook Data Tables',
        content: `newbook_room_categories - Room types from Newbook
- site_id, site_name, room_count, is_included

newbook_gl_accounts - GL accounts for revenue mapping
- gl_account_id, gl_code, gl_name, department (accommodation/dry/wet)

newbook_bookings_data - Raw booking records
- newbook_id, arrival_date, departure_date, guests, status, total_amount, ...

newbook_earned_revenue_data - Revenue by GL account
- date, gl_account_id, amount_gross, amount_net

newbook_occupancy_report_data - Official occupancy numbers
- date, category_id, available, occupied, maintenance`
      },
      {
        id: 'stats-tables',
        title: 'Aggregated Statistics Tables',
        content: `newbook_bookings_stats - Daily aggregated stats
- date, rooms_count, booking_count, occupancy_pct, guests_count, revenue totals
- occupancy_by_category (JSONB), revenue_by_category (JSONB)

newbook_booking_pace - Lead-time snapshots
- arrival_date, d365..d0 (58 columns for bookings at each lead time)

newbook_net_revenue_data - Revenue by department
- date, accommodation, dry, wet`
      },
      {
        id: 'forecast-tables',
        title: 'Forecasting Tables',
        content: `forecast_metrics - Metric configuration
- metric_code, metric_name, unit, use_prophet, use_xgboost, use_pickup

daily_metrics - Actual values for training
- date, metric_code, actual_value

forecasts - Generated predictions
- forecast_date, forecast_type, model_type, predicted_value, lower_bound, upper_bound

actual_vs_forecast - Accuracy comparison
- date, metric_type, actual_value, prophet_*, xgboost_*, pickup_*, best_model

daily_budgets - Budget values
- date, budget_type, budget_value

forecast_snapshots - Historical forecasts for backtest
- snapshot_date, target_date, metric_code, days_out, model, forecast_value`
      },
      {
        id: 'explanation-tables',
        title: 'Model Explanation Tables',
        content: `prophet_decomposition - Prophet component breakdown
- forecast_date, trend, yearly_seasonality, weekly_seasonality, holiday_effects

xgboost_explanations - SHAP value explanations
- forecast_date, base_value, shap_values (JSONB), top_positive, top_negative

pickup_explanations - Pickup model details
- forecast_date, current_otb, comparison_date, pace_vs_prior_pct, projected_value`
      }
    ]
  },
  appendix: {
    title: 'Quick Reference',
    sections: [
      {
        id: 'default-credentials',
        title: 'Default Credentials',
        content: `Application Login:
Username: admin
Password: admin123 (change in production!)

Database:
Host: db (Docker) / localhost
Port: 5432
Database: forecast_data
User: forecast
Password: forecast_secret`
      },
      {
        id: 'urls',
        title: 'Access URLs',
        content: `Frontend: http://localhost:3081
Backend API: http://localhost:8001
Swagger UI: http://localhost:8001/docs
ReDoc: http://localhost:8001/redoc
Adminer (DB): http://localhost:8082`
      },
      {
        id: 'docker-commands',
        title: 'Docker Commands',
        content: `Start: docker-compose up -d
Stop: docker-compose down
Rebuild: docker-compose up -d --build
Logs: docker-compose logs -f [service]
Shell: docker exec -it [container] /bin/sh

Services: db, backend, frontend, adminer`
      },
      {
        id: 'metrics',
        title: 'Forecast Metrics',
        content: `hotel_occupancy_pct - Occupancy percentage (%)
hotel_room_nights - Rooms sold (count)
hotel_guests - Total guests (count)
hotel_arrivals - Check-ins (count)

Accuracy Metrics:
MAE - Mean Absolute Error
RMSE - Root Mean Square Error
MAPE - Mean Absolute Percentage Error`
      },
      {
        id: 'error-codes',
        title: 'HTTP Status Codes',
        content: `200 - Success
400 - Bad Request (invalid input)
401 - Unauthorized (invalid/missing token)
403 - Forbidden (insufficient permissions)
404 - Not Found
422 - Validation Error
500 - Internal Server Error`
      }
    ]
  }
}

type DocSectionKey = keyof typeof docsContent

const Docs: React.FC = () => {
  const [activeSection, setActiveSection] = useState<DocSectionKey>('overview')
  const [searchQuery, setSearchQuery] = useState('')
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['overview']))

  // Search through all content
  const searchResults = useMemo(() => {
    if (!searchQuery.trim()) return null

    const query = searchQuery.toLowerCase()
    const results: Array<{
      section: DocSectionKey
      sectionTitle: string
      subsection: string
      content: string
      matchIndex: number
    }> = []

    Object.entries(docsContent).forEach(([sectionKey, section]) => {
      section.sections.forEach((subsection) => {
        const contentLower = subsection.content.toLowerCase()
        const titleLower = subsection.title.toLowerCase()

        if (contentLower.includes(query) || titleLower.includes(query)) {
          const matchIndex = Math.max(contentLower.indexOf(query), titleLower.indexOf(query))
          results.push({
            section: sectionKey as DocSectionKey,
            sectionTitle: section.title,
            subsection: subsection.title,
            content: subsection.content.slice(0, 150) + '...',
            matchIndex
          })
        }
      })
    })

    return results
  }, [searchQuery])

  const toggleSection = (section: string) => {
    setExpandedSections(prev => {
      const newSet = new Set(prev)
      if (newSet.has(section)) {
        newSet.delete(section)
      } else {
        newSet.add(section)
      }
      return newSet
    })
  }

  const handleSearchResultClick = (section: DocSectionKey) => {
    setActiveSection(section)
    setExpandedSections(prev => new Set([...prev, section]))
    setSearchQuery('')
  }

  const currentContent = docsContent[activeSection]

  return (
    <div style={styles.container}>
      {/* Sidebar */}
      <aside style={styles.sidebar}>
        <div style={styles.sidebarHeader}>
          <h2 style={styles.sidebarTitle}>Documentation</h2>
        </div>

        {/* Search */}
        <div style={styles.searchContainer}>
          <input
            type="text"
            placeholder="Search docs..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={styles.searchInput}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              style={styles.clearSearch}
            >
              ×
            </button>
          )}
        </div>

        {/* Search Results */}
        {searchResults && searchResults.length > 0 && (
          <div style={styles.searchResults}>
            <div style={styles.searchResultsHeader}>
              {searchResults.length} result{searchResults.length !== 1 ? 's' : ''} found
            </div>
            {searchResults.slice(0, 10).map((result, idx) => (
              <button
                key={idx}
                onClick={() => handleSearchResultClick(result.section)}
                style={styles.searchResultItem}
              >
                <div style={styles.searchResultTitle}>{result.subsection}</div>
                <div style={styles.searchResultSection}>{result.sectionTitle}</div>
              </button>
            ))}
          </div>
        )}

        {/* Navigation */}
        {!searchResults && (
          <nav style={styles.nav}>
            {Object.entries(docsContent).map(([key, section]) => (
              <div key={key}>
                <button
                  onClick={() => {
                    setActiveSection(key as DocSectionKey)
                    toggleSection(key)
                  }}
                  style={{
                    ...styles.navItem,
                    ...(activeSection === key ? styles.navItemActive : {})
                  }}
                >
                  <span style={styles.navIcon}>
                    {expandedSections.has(key) ? '▼' : '▶'}
                  </span>
                  {section.title}
                </button>
                {expandedSections.has(key) && activeSection === key && (
                  <div style={styles.navSubItems}>
                    {section.sections.map((sub) => (
                      <a
                        key={sub.id}
                        href={`#${sub.id}`}
                        style={styles.navSubItem}
                      >
                        {sub.title}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </nav>
        )}

        {/* Quick Links */}
        <div style={styles.quickLinks}>
          <h3 style={styles.quickLinksTitle}>Quick Links</h3>
          <a href="#urls" onClick={() => setActiveSection('appendix')} style={styles.quickLink}>
            Access URLs
          </a>
          <a href="#default-credentials" onClick={() => setActiveSection('appendix')} style={styles.quickLink}>
            Default Credentials
          </a>
          <a href="#docker-commands" onClick={() => setActiveSection('appendix')} style={styles.quickLink}>
            Docker Commands
          </a>
          <a
            href="http://localhost:8001/docs"
            target="_blank"
            rel="noopener noreferrer"
            style={styles.quickLink}
          >
            Swagger UI ↗
          </a>
        </div>
      </aside>

      {/* Main Content */}
      <main style={styles.main}>
        <div style={styles.content}>
          <h1 style={styles.pageTitle}>{currentContent.title}</h1>

          {currentContent.sections.map((section) => (
            <section key={section.id} id={section.id} style={styles.section}>
              <h2 style={styles.sectionTitle}>{section.title}</h2>
              <div style={styles.sectionContent}>
                {section.content.split('\n\n').map((paragraph, idx) => (
                  <p key={idx} style={styles.paragraph}>
                    {paragraph.split('\n').map((line, lineIdx) => (
                      <React.Fragment key={lineIdx}>
                        {line}
                        {lineIdx < paragraph.split('\n').length - 1 && <br />}
                      </React.Fragment>
                    ))}
                  </p>
                ))}
              </div>
            </section>
          ))}

          {/* Page Navigation */}
          <div style={styles.pageNav}>
            {Object.keys(docsContent).map((key, idx, arr) => {
              if (key === activeSection) {
                return (
                  <div key={key} style={styles.pageNavButtons}>
                    {idx > 0 && (
                      <button
                        onClick={() => setActiveSection(arr[idx - 1] as DocSectionKey)}
                        style={styles.pageNavButton}
                      >
                        ← {docsContent[arr[idx - 1] as DocSectionKey].title}
                      </button>
                    )}
                    {idx < arr.length - 1 && (
                      <button
                        onClick={() => setActiveSection(arr[idx + 1] as DocSectionKey)}
                        style={{ ...styles.pageNavButton, marginLeft: 'auto' }}
                      >
                        {docsContent[arr[idx + 1] as DocSectionKey].title} →
                      </button>
                    )}
                  </div>
                )
              }
              return null
            })}
          </div>
        </div>
      </main>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    minHeight: 'calc(100vh - 60px)',
    background: colors.background,
  },
  sidebar: {
    width: '280px',
    background: colors.surface,
    borderRight: `1px solid ${colors.border}`,
    display: 'flex',
    flexDirection: 'column',
    position: 'sticky',
    top: '60px',
    height: 'calc(100vh - 60px)',
    overflowY: 'auto',
  },
  sidebarHeader: {
    padding: spacing.lg,
    borderBottom: `1px solid ${colors.borderLight}`,
  },
  sidebarTitle: {
    fontSize: typography.lg,
    fontWeight: typography.semibold,
    color: colors.text,
    margin: 0,
  },
  searchContainer: {
    padding: spacing.md,
    position: 'relative',
  },
  searchInput: {
    width: '100%',
    padding: `${spacing.sm} ${spacing.md}`,
    paddingRight: spacing.xl,
    fontSize: typography.sm,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    outline: 'none',
    boxSizing: 'border-box',
  },
  clearSearch: {
    position: 'absolute',
    right: spacing.lg,
    top: '50%',
    transform: 'translateY(-50%)',
    background: 'none',
    border: 'none',
    fontSize: typography.lg,
    color: colors.textMuted,
    cursor: 'pointer',
    padding: spacing.xs,
  },
  searchResults: {
    borderBottom: `1px solid ${colors.borderLight}`,
    maxHeight: '300px',
    overflowY: 'auto',
  },
  searchResultsHeader: {
    padding: `${spacing.xs} ${spacing.md}`,
    fontSize: typography.xs,
    color: colors.textMuted,
    background: colors.background,
  },
  searchResultItem: {
    display: 'block',
    width: '100%',
    padding: spacing.md,
    background: 'none',
    border: 'none',
    borderBottom: `1px solid ${colors.borderLight}`,
    cursor: 'pointer',
    textAlign: 'left',
    transition: `background ${transitions.fast}`,
  },
  searchResultTitle: {
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.text,
    marginBottom: spacing.xs,
  },
  searchResultSection: {
    fontSize: typography.xs,
    color: colors.textMuted,
  },
  nav: {
    flex: 1,
    padding: spacing.md,
  },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    width: '100%',
    padding: `${spacing.sm} ${spacing.md}`,
    background: 'none',
    border: 'none',
    borderRadius: radius.md,
    fontSize: typography.sm,
    fontWeight: typography.medium,
    color: colors.text,
    cursor: 'pointer',
    textAlign: 'left',
    transition: `all ${transitions.fast}`,
    marginBottom: spacing.xs,
  },
  navItemActive: {
    background: colors.primary,
    color: colors.textLight,
  },
  navIcon: {
    fontSize: typography.xs,
    marginRight: spacing.sm,
    width: '12px',
  },
  navSubItems: {
    marginLeft: spacing.lg,
    marginBottom: spacing.sm,
  },
  navSubItem: {
    display: 'block',
    padding: `${spacing.xs} ${spacing.md}`,
    fontSize: typography.xs,
    color: colors.textMuted,
    textDecoration: 'none',
    borderRadius: radius.sm,
    transition: `color ${transitions.fast}`,
  },
  quickLinks: {
    padding: spacing.md,
    borderTop: `1px solid ${colors.borderLight}`,
    marginTop: 'auto',
  },
  quickLinksTitle: {
    fontSize: typography.xs,
    fontWeight: typography.semibold,
    color: colors.textMuted,
    textTransform: 'uppercase',
    marginBottom: spacing.sm,
  },
  quickLink: {
    display: 'block',
    padding: `${spacing.xs} 0`,
    fontSize: typography.sm,
    color: colors.primary,
    textDecoration: 'none',
  },
  main: {
    flex: 1,
    padding: spacing.xl,
    maxWidth: '900px',
  },
  content: {
    background: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
    boxShadow: shadows.sm,
  },
  pageTitle: {
    fontSize: typography.xxxl,
    fontWeight: typography.bold,
    color: colors.text,
    marginBottom: spacing.xl,
    paddingBottom: spacing.md,
    borderBottom: `2px solid ${colors.primary}`,
  },
  section: {
    marginBottom: spacing.xl,
  },
  sectionTitle: {
    fontSize: typography.xl,
    fontWeight: typography.semibold,
    color: colors.text,
    marginBottom: spacing.md,
    paddingTop: spacing.md,
  },
  sectionContent: {
    fontSize: typography.base,
    lineHeight: 1.7,
    color: colors.text,
  },
  paragraph: {
    marginBottom: spacing.md,
    whiteSpace: 'pre-wrap',
    fontFamily: 'inherit',
  },
  pageNav: {
    marginTop: spacing.xxl,
    paddingTop: spacing.lg,
    borderTop: `1px solid ${colors.borderLight}`,
  },
  pageNavButtons: {
    display: 'flex',
    justifyContent: 'space-between',
  },
  pageNavButton: {
    padding: `${spacing.sm} ${spacing.md}`,
    background: colors.background,
    border: `1px solid ${colors.border}`,
    borderRadius: radius.md,
    fontSize: typography.sm,
    color: colors.text,
    cursor: 'pointer',
    transition: `all ${transitions.fast}`,
  },
}

export default Docs
