# Frontend Documentation

## Overview

The Forecasting App frontend is a React-based single-page application (SPA) built with TypeScript. It provides a comprehensive interface for viewing forecasts, analyzing historical data, and configuring system settings.

## Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| React | 18.2.0 | UI framework |
| TypeScript | 5.2 | Type-safe JavaScript |
| Vite | 5.0.11 | Build tool & dev server |
| React Router DOM | 6.21.1 | Client-side routing |
| TanStack React Query | 5.17.9 | Data fetching & caching |
| Axios | 1.6.5 | HTTP client |
| Plotly.js | 2.35.0 | Interactive charts |
| Chart.js | 4.4.1 | Simple charts |

## Project Structure

```
frontend/
├── src/
│   ├── App.tsx              # Main app component, routing, auth context
│   ├── main.tsx             # React entry point
│   ├── pages/               # Page components
│   │   ├── Login.tsx        # Authentication page
│   │   ├── Dashboard.tsx    # Main dashboard view
│   │   ├── Forecasts.tsx    # Forecast model comparison
│   │   ├── Review.tsx       # Historical data review
│   │   ├── Accuracy.tsx     # Model accuracy metrics
│   │   ├── Bookability.tsx  # Rate matrix & tariff availability
│   │   ├── CompetitorRates.tsx # Competitor rate comparison
│   │   ├── Settings.tsx     # System configuration
│   │   └── Docs.tsx         # Documentation viewer
│   ├── components/          # Reusable components
│   │   ├── SimpleChart.tsx  # Chart.js wrapper
│   │   ├── DetailChart.tsx  # Plotly.js wrapper
│   │   └── index.ts         # Component exports
│   └── utils/               # Utilities
│       ├── api.ts           # API client & auth interceptor
│       └── theme.ts         # Design system
├── public/                  # Static assets
├── Dockerfile               # Production build
├── nginx.conf               # Nginx reverse proxy config
└── package.json             # Dependencies
```

## Routing

| Path | Component | Description |
|------|-----------|-------------|
| `/login` | Login | User authentication |
| `/` | Dashboard | Main dashboard |
| `/review` | Review | Historical data browser |
| `/review/:reportId` | Review | Specific report view |
| `/forecasts` | Forecasts | Model comparison |
| `/forecasts/:forecastId` | Forecasts | Specific forecast view |
| `/accuracy` | Accuracy | Model accuracy analysis |
| `/bookability` | Bookability | Rate matrix & tariff availability |
| `/competitor-rates` | CompetitorRates | Competitor rate comparison |
| `/settings` | Settings | System configuration |
| `/docs` | Docs | Documentation viewer |

## Authentication

Authentication uses JWT tokens stored in localStorage:

```typescript
// Token storage
localStorage.setItem('token', accessToken)

// API interceptor automatically adds token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 401 responses redirect to login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)
```

### AuthContext

The app provides an AuthContext for managing user state:

```typescript
interface AuthContextType {
  user: { id: number; username: string; display_name: string } | null
  token: string | null
  logout: () => void
}

// Usage in components
const { user, logout } = useAuth()
```

## Theme System

The theme system provides consistent styling across the application:

### Colors

```typescript
colors: {
  primary: '#1a1a2e',      // Dark blue (header, primary elements)
  primaryLight: '#16213e', // Lighter blue
  accent: '#e94560',       // Red accent
  background: '#f5f5f5',   // Light gray background
  surface: '#ffffff',      // White cards/surfaces
  text: '#1a1a2e',         // Dark text
  textLight: '#ffffff',    // Light text
  textMuted: '#6c757d',    // Muted text
  success: '#28a745',      // Green
  warning: '#ffc107',      // Yellow
  error: '#dc3545',        // Red
  border: '#dee2e6',       // Border color
  borderLight: '#e9ecef',  // Light border
}
```

### Spacing Scale

```typescript
spacing: {
  xs: '4px',
  sm: '8px',
  md: '16px',
  lg: '24px',
  xl: '32px',
  xxl: '48px',
}
```

### Typography

```typescript
typography: {
  xs: '11px',
  sm: '13px',
  base: '14px',
  md: '16px',
  lg: '18px',
  xl: '20px',
  xxl: '24px',
  xxxl: '32px',
  regular: 400,
  medium: 500,
  semibold: 600,
  bold: 700,
}
```

### Chart Colors

```typescript
chartColors: [
  '#2196F3', // Blue - Prophet
  '#4CAF50', // Green - XGBoost
  '#FF9800', // Orange - Pickup
  '#9C27B0', // Purple - CatBoost
  '#F44336', // Red - Actual
]
```

## Pages

### Dashboard (`/`)

The main landing page showing:
- Quick summary metrics
- Today's forecasts vs actuals
- Weekly outlook
- Key performance indicators

### Review (`/review`)

Historical data analysis:
- Date range selection
- Occupancy data visualization
- Booking statistics
- Revenue metrics
- Export functionality

### Forecasts (`/forecasts`)

Model comparison and forecasting:
- Multi-model forecast display (Prophet, XGBoost, Pickup, CatBoost)
- Metric selection (occupancy, rooms, guests, arrivals)
- Date range filtering
- Prior year comparison
- Confidence intervals (Prophet)
- Interactive Plotly charts

### Accuracy (`/accuracy`)

Model performance analysis:
- MAE, RMSE, MAPE metrics
- Model win rates
- Accuracy by lead time
- Best model analysis
- Historical accuracy trends

### Bookability (`/bookability`)

Rate availability matrix showing Newbook rack rates per room category:
- Monthly date view with per-category rate grids
- Tariff rows with availability status (available/unavailable/no rooms)
- Multi-night minimum stay verification with badges
- Occupancy row showing rooms available/occupied/maintenance
- Single-date refresh button on each date column
- Booking.com availability section (linked from competitor scraper data)
- Issues panel highlighting unbookable date/category combinations

### Competitor Rates (`/competitor-rates`)

Competitor rate comparison with three tabs:
- **Rate Matrix** - Monthly grid of competitor hotel rates with availability status, crosshair hover, per-date scrape trigger, links to Booking.com
- **Hotels** - Manage competitor hotels (own/competitor/market tiers), star ratings, review scores, display order
- **Settings** - Scraper configuration (location, schedule), manual scrape trigger, scrape history, queue status, 365-day coverage grid with freshness indicators

### Settings (`/settings`)

System configuration with tabs:

1. **Newbook Settings** - API credentials and connection test
2. **Resos Settings** - Restaurant booking integration
3. **Room Categories** - Configure which room types to include
4. **GL Accounts** - Revenue mapping to departments
5. **Sync Settings** - Schedule automatic data syncs
6. **Special Dates** - Configure holidays/events for forecasting
7. **Users** - User management
8. **Database Browser** - Direct database access via Adminer

## Components

### SimpleChart

Chart.js-based component for basic charts:

```typescript
interface SimpleChartProps {
  type: 'line' | 'bar' | 'doughnut'
  data: ChartData
  options?: ChartOptions
  height?: number
}

// Usage
<SimpleChart
  type="line"
  data={{
    labels: dates,
    datasets: [{
      label: 'Occupancy',
      data: values,
      borderColor: chartColors[0],
    }]
  }}
  height={300}
/>
```

### DetailChart

Plotly.js-based component for interactive charts:

```typescript
interface DetailChartProps {
  data: PlotData[]
  layout?: Partial<Layout>
  config?: Partial<Config>
}

// Usage
<DetailChart
  data={[
    {
      x: dates,
      y: prophet,
      name: 'Prophet',
      type: 'scatter',
      mode: 'lines',
    },
    {
      x: dates,
      y: xgboost,
      name: 'XGBoost',
      type: 'scatter',
      mode: 'lines',
    }
  ]}
  layout={{
    title: 'Model Comparison',
    xaxis: { title: 'Date' },
    yaxis: { title: 'Value' },
  }}
/>
```

## API Client

The API client is configured in `utils/api.ts`:

```typescript
import api from './utils/api'

// GET request
const data = await api.get('/forecast/daily', {
  params: { from_date: '2024-01-01', to_date: '2024-01-31' }
})

// POST request
const result = await api.post('/sync/newbook', {}, {
  params: { full_sync: false }
})
```

### Pre-built API functions

```typescript
import { authApi } from './utils/api'

// Authentication
authApi.login(username, password)  // Returns { access_token, token_type }
authApi.getMe()                     // Returns current user
authApi.getUsers()                  // List all users
authApi.createUser(data)            // Create new user
authApi.deleteUser(userId)          // Delete user
```

## Data Fetching with React Query

The app uses TanStack React Query for efficient data fetching:

```typescript
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

// Query example
const { data, isLoading, error } = useQuery({
  queryKey: ['forecasts', fromDate, toDate],
  queryFn: () => api.get('/forecast/daily', {
    params: { from_date: fromDate, to_date: toDate }
  }).then(res => res.data)
})

// Mutation example
const queryClient = useQueryClient()
const mutation = useMutation({
  mutationFn: (data) => api.post('/sync/newbook', data),
  onSuccess: () => {
    queryClient.invalidateQueries(['sync-status'])
  }
})
```

## Building & Deployment

### Development

```bash
cd frontend
npm install
npm run dev    # Start dev server on http://localhost:5173
```

### Production Build

```bash
npm run build  # Creates dist/ folder
```

### Docker Deployment

The frontend Dockerfile creates a multi-stage build:
1. Node.js stage builds the React app
2. Nginx stage serves static files and proxies API requests

```dockerfile
# Build stage
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Production stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### Nginx Configuration

The nginx.conf handles:
- Static file serving from `/usr/share/nginx/html`
- API proxy: `/api/*` -> `backend:8000`
- Adminer proxy: `/adminer/*` -> `adminer:8080`
- SPA fallback: All routes serve `index.html`

## Environment Variables

No frontend-specific environment variables are required. The API base URL is configured to use `/api` which is proxied to the backend by nginx.

## Error Handling

Components should handle loading and error states:

```typescript
const { data, isLoading, error } = useQuery(...)

if (isLoading) return <LoadingSpinner />
if (error) return <ErrorMessage error={error} />
return <DataDisplay data={data} />
```

## Responsive Design

The app uses CSS-in-JS with responsive considerations:
- Max width containers (1400px)
- Flexible grid layouts
- Responsive padding and margins

## Performance Optimizations

1. **React Query caching** - Reduces redundant API calls
2. **Lazy loading** - Charts load on demand
3. **Memoization** - Complex calculations cached with useMemo
4. **Nginx gzip** - Compressed static assets
