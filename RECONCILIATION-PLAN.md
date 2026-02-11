# Reconciliation Module - Implementation Plan

## Context

The WordPress plugin `hotel-cashup-reconciliation` provides daily cash reconciliation for hotel operations - denomination counting, card machine reconciliation, Newbook PMS payment verification, float management, and multi-day reporting. This plan replicates all of that functionality as a "Reconciliation" main menu item within the `forecasting-app-docker` app, following the existing architecture patterns exactly (React + TypeScript frontend, FastAPI backend, PostgreSQL database).

**Key design decisions:**
- **Newbook credentials**: Reuse existing credentials from the main Settings page (`system_config` table) - no duplication
- **Excel-friendly tables**: Multi-day report tables replicate the WordPress plugin's spreadsheet-like cell selection, tab-separated clipboard copy, and selection tooltip (count/sum/average)
- **Staff access**: Separate `/staff` route with stripped-down UI for frontline staff (Cash Up, Petty Cash, Change Tin only) using existing JWT login with a new `role` column on `users` table (`admin` | `staff`)

---

## Files to Modify

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Add imports, routes for Reconciliation + Staff page, nav menu item, role-based routing |
| `backend/main.py` | Register new `reconciliation` router |
| `backend/auth.py` | Add `role` field to user responses, include role in JWT token |
| `backend/services/newbook_client.py` | Add `get_transaction_flow()` and `get_gl_account_list()` methods |
| `db/init_clean.sql` | Add `role` column to `users`, add 11 new `recon_*` tables + `system_config` entries |
| `docker-compose.yml` | Add `recon_uploads` volume for receipt photos |

## Files to Create

| File | Purpose |
|------|---------|
| `frontend/src/pages/Reconciliation.tsx` | Full admin page with sidebar nav and 7 sub-pages |
| `frontend/src/pages/StaffCashUp.tsx` | Simplified staff-only page (Cash Up, Petty Cash, Change Tin) |
| `backend/api/reconciliation.py` | FastAPI router - all CRUD, Newbook fetch, reports, settings endpoints |
| `backend/services/reconciliation_service.py` | Business logic - payment categorization, variance calc, report aggregation |

---

## 1. Database Schema (11 `recon_*` tables in `init_clean.sql`)

All tables use `recon_` prefix, `SERIAL PRIMARY KEY`, `DECIMAL(10,2)` for money, and `CASCADE DELETE` on child FKs.

| Table | Purpose | Key Columns |
|-------|---------|-------------|
| `recon_cash_ups` | Daily sessions | `session_date` (UNIQUE), `status` (draft/final), `total_float_counted`, `total_cash_counted`, `created_by` FK users |
| `recon_denominations` | Denomination counts | `cash_up_id` FK, `count_type` (float/takings), `denomination_value`, `quantity`, `total_amount` |
| `recon_card_machines` | Card machine data | `cash_up_id` FK, `machine_name`, `total_amount`, `amex_amount`, `visa_mc_amount` |
| `recon_payment_records` | Cached Newbook payments | `newbook_payment_id`, `card_type`, `amount`, `transaction_method`, `payment_date` |
| `recon_reconciliation` | Variance results | `cash_up_id` FK, `category`, `banked_amount`, `reported_amount`, `variance` |
| `recon_daily_stats` | Daily operational stats | `business_date` (UNIQUE), `gross_sales`, `rooms_sold`, `total_people` |
| `recon_sales_breakdown` | Net sales by GL category | `business_date`, `category`, `net_amount` |
| `recon_float_counts` | Float counting sessions | `count_type` (petty_cash/change_tin/safe_cash), `total_counted`, `target_amount`, `variance` |
| `recon_float_denominations` | Float denomination detail | `float_count_id` FK, `denomination_value`, `quantity`, `total_amount` |
| `recon_float_receipts` | Petty cash receipts | `float_count_id` FK, `receipt_value`, `receipt_description` |
| `recon_attachments` | Receipt photos | `cash_up_id` FK, `file_name`, `file_path`, `file_type`, `file_size` |

**User role column** added to existing `users` table:
```sql
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'admin';
-- Existing users default to 'admin'; new staff accounts created with role='staff'
```

**Reconciliation settings** stored in existing `system_config` table with `recon_` prefix keys:
- `recon_expected_till_float` (300.00), `recon_variance_threshold` (10.00), `recon_default_report_days` (7)
- `recon_petty_cash_target` (200.00), `recon_change_tin_breakdown` (JSON), `recon_safe_cash_target` (0.00)
- `recon_denominations` (JSON: notes + coins), `recon_sales_breakdown_columns` (JSON)

**No Newbook credential duplication** - the reconciliation module reads `newbook_api_key`, `newbook_username`, `newbook_password`, `newbook_region` from the existing `system_config` entries managed by the main Settings page.

---

## 2. Backend API (`backend/api/reconciliation.py`)

Router prefix: `/reconciliation`, all endpoints require `Depends(get_current_user)`.

### Cash Up CRUD
- `GET /cash-ups` - List with filters (status, date_from, date_to, page, per_page)
- `GET /cash-ups/{id}` - Full cash-up with denominations, cards, reconciliation, attachments
- `GET /cash-ups/by-date/{date}` - Check/load by date
- `POST /cash-ups` - Create (409 if date exists)
- `PUT /cash-ups/{id}` - Update denominations, cards, reconciliation, notes
- `POST /cash-ups/{id}/finalize` - Draft -> final
- `DELETE /cash-ups/{id}` - Delete drafts only
- `POST /cash-ups/bulk-finalize` - Finalize multiple by IDs

### Newbook Integration
- `GET /newbook/payments/{date}` - Fetch + categorize payments from Newbook API
- `GET /newbook/daily-stats/{date}` - Fetch occupancy, sales, debtors/creditors

### Reports
- `GET /reports/multi-day` - Multi-day report (start_date, num_days params) returns 3 tables

### Float Counts
- `GET /float-counts` - List with filters (count_type, date range)
- `GET /float-counts/{id}` - Detail with denominations + receipts
- `POST /float-counts` - Create (petty_cash, change_tin, or safe_cash)
- `PUT /float-counts/{id}` - Update
- `DELETE /float-counts/{id}` - Delete

### Attachments
- `POST /cash-ups/{id}/attachments` - Upload (multipart, JPEG/PNG/PDF, 5MB max)
- `DELETE /attachments/{id}` - Delete
- `GET /attachments/{id}/download` - Download file

### Settings (reconciliation-specific only; Newbook creds managed by main Settings page)
- `GET /settings` - Get all `recon_*` from system_config
- `POST /settings` - Update recon-specific settings
- `POST /settings/refresh-gl-accounts` - Fetch GL accounts from Newbook using existing credentials

---

## 3. Business Logic (`backend/services/reconciliation_service.py`)

Key functions ported from the WordPress plugin's PHP:

- **`identify_card_type(transaction)`** - Categorize Newbook payments: cash, visa_mc, amex, bacs, other
- **`categorize_payments(raw_transactions)`** - Group into 6 reconciliation categories: Cash, PDQ Visa/MC, PDQ Amex, Gateway Visa/MC, Gateway Amex, BACS
- **`calculate_payment_totals(payments)`** - Sum amounts per category
- **`parse_till_transactions(description)`** - Extract "Ticket: {n} - {type}" patterns
- **`build_multi_day_report(data)`** - Aggregate 3 tables: daily recon summary, sales breakdown, occupancy stats
- **Amount conversion**: Newbook negative amounts -> positive revenue: `amount = -float(item_amount)`
- **Variance**: `variance = banked - reported` (green=balanced, red=short, amber=over)

---

## 4. Newbook Client Extensions (`backend/services/newbook_client.py`)

Add two new methods following the existing `get_occupancy_report` pattern:

- **`get_transaction_flow(from_date, to_date)`** - Calls `reports_transaction_flow` endpoint. Returns payment/refund transactions with pagination (batch_size=5000). Filters out `balance_transfer` items.
- **`get_gl_account_list()`** - Calls endpoint to fetch GL account codes for sales breakdown column configuration.

---

## 5. Frontend (`frontend/src/pages/Reconciliation.tsx`)

Single monolithic page file following the `Review.tsx` sidebar pattern exactly.

### Sidebar Navigation (MenuGroup pattern)
```
Daily:       Cash Up | History | Multi-Day Report
Floats:      Petty Cash | Change Tin | Safe Cash
Admin:       Settings
```

Routes: `/reconciliation` and `/reconciliation/:subPage` using `useParams`.

### Sub-Page Components (all defined within Reconciliation.tsx)

**CashUpPage** (default) - The core form:
- Date picker with status check (new/draft/final)
- Two denomination counting tables (Float + Takings) with GBP denominations (£50 down to 1p)
- Each row: denomination label, quantity input, auto-calculated total (real-time via state)
- Card machine section: 2 machines (Front Desk, Restaurant/Bar) with Total, Amex, auto-calc Visa/MC
- "Fetch Newbook Data" button -> calls API -> shows categorized payment totals
- Reconciliation table: 6 categories, Banked vs Reported vs Variance with color coding
- Receipt photo upload (multipart) with list + delete
- Notes textarea
- Save Draft / Finalize buttons with dirty-form tracking

**HistoryPage** - Filterable list:
- Filters: status dropdown, date range, user
- Table: Date, Status badge, Cash Total, Card Total, Variance, User, Actions (edit/view/delete)
- Pagination + bulk finalize

**MultiDayReportPage** - Consolidated reporting with Excel-friendly tables:
- Controls: start date, number of days (1-365)
- Table 1: Daily Reconciliation Summary - two side-by-side tables (BANKED green header #e8f5e9, REPORTED orange header #fff3e0) with variance row
- Table 2: Sales Breakdown (GL categories vs days with row/column totals)
- Table 3: Occupancy Stats (rooms, people, rates, REVPAR, occupancy % with averages)
- **Excel copy-paste features** (replicating the WordPress plugin's `enhanceTableSelection()`):
  - Click to select cell, Shift+Click for range selection, drag to extend
  - Tab-separated clipboard copy: on Ctrl+C, selected cells joined with `\t` (columns) and `\n` (rows)
  - Smart number extraction: strips `£` symbols and variance indicators (▼▲) when copying, preserves raw numbers
  - Selection tooltip: floating indicator showing count, sum, and average of selected numeric cells
  - CSS `user-select: text` on report tables, blue highlight on selected cells (`outline: 2px solid #0078d4`)
  - `.toFixed(2)` formatting on all currency values for consistent 2dp display

**PettyCashPage** - Float counting:
- Denomination table (£50 to 5p), receipts add/remove, target comparison, variance

**ChangeTinPage** - Float with per-denomination targets:
- Denomination table with target amounts from settings, top-up suggestions

**SafeCashPage** - Simple denomination count with target comparison

**ReconSettingsPage** - Reconciliation-specific configuration only:
- General: till float, variance threshold, report days
- Float targets: petty cash, change tin breakdown, safe cash
- Sales columns: GL code list with enabled/name/sort, "Refresh from Newbook" button
- Note: Newbook API credentials are NOT shown here - they're managed in the main app Settings page

### Styling
All inline CSS-in-JS using existing theme tokens (`colors`, `spacing`, `typography`, `radius`, `shadows`). Sidebar styles copied from Review.tsx. Reconciliation-specific styles for denomination tables, variance colors, card machine grid layout.

---

## 5b. Staff Cash-Up Page (`frontend/src/pages/StaffCashUp.tsx`)

Separate simplified page for frontline staff who shouldn't access the full app.

### Access Control
- Route: `/staff` and `/staff/:subPage`
- Uses same JWT login (existing Login.tsx), but users with `role='staff'` are redirected here after login instead of Dashboard
- Stripped-down header: shows "Cash Up" logo, user name, and logout button only - no full nav menu
- If a staff user tries to navigate to `/forecasts`, `/settings`, etc., they get redirected to `/staff`
- Admin users CAN access `/staff` route (useful for testing), but staff users CANNOT access admin routes

### App.tsx Routing Changes
```tsx
// After login, check role:
// - role='admin' → navigate to '/' (Dashboard)
// - role='staff' → navigate to '/staff' (StaffCashUp)

// Route protection:
<Route path="/staff" element={token ? <StaffCashUp /> : <Navigate to="/login" />} />
<Route path="/staff/:subPage" element={token ? <StaffCashUp /> : <Navigate to="/login" />} />

// Admin routes get role check:
// element={token && user?.role === 'admin' ? <Component /> : <Navigate to="/staff" />}
```

### Sub-Pages (sidebar nav, same pattern as Reconciliation.tsx)
```
Daily:       Cash Up (default)
Floats:      Petty Cash | Change Tin
```

- **Cash Up**: Same form as admin Reconciliation CashUpPage - date picker, denominations, cards, Newbook fetch, reconciliation, notes, attachments. Staff can save drafts only (no Finalize button).
- **Petty Cash**: Same as admin PettyCashPage
- **Change Tin**: Same as admin ChangeTinPage

### Component Reuse
The sub-page components (CashUpForm, PettyCashForm, ChangeTinForm) will be extracted as shared components that both `Reconciliation.tsx` and `StaffCashUp.tsx` import. This avoids duplicating the denomination table logic, card machine calculations, etc. The shared components accept props for:
- `canFinalize: boolean` (true for admin, false for staff)
- `showHistory: boolean` (true for admin, false for staff)

### auth.py Changes
- Add `role` field to JWT token payload and user response model
- `get_current_user()` returns role in the user dict
- New dependency: `get_admin_user()` that checks `role === 'admin'` (used on admin-only endpoints like settings, bulk-finalize, delete)

### User Management (existing Settings > Users tab)
- Add role dropdown (admin/staff) when creating new users
- Display role in user list

---

## 6. App.tsx Changes

```tsx
// Add imports
import Reconciliation from './pages/Reconciliation'
import StaffCashUp from './pages/StaffCashUp'

// Add routes
<Route path="/reconciliation" element={token && user?.role === 'admin' ? <Reconciliation /> : <Navigate to="/staff" />} />
<Route path="/reconciliation/:subPage" element={token && user?.role === 'admin' ? <Reconciliation /> : <Navigate to="/staff" />} />
<Route path="/staff" element={token ? <StaffCashUp /> : <Navigate to="/login" />} />
<Route path="/staff/:subPage" element={token ? <StaffCashUp /> : <Navigate to="/login" />} />

// Add to remainingNavItems (between Competitors and Settings, admin-only nav)
{ path: '/reconciliation', label: 'Reconciliation' }

// Post-login redirect: role='staff' → '/staff', role='admin' → '/'
```

Active link uses `location.pathname.startsWith('/reconciliation')`.
Admin routes get role guard; staff route accessible to all authenticated users.

---

## 7. Docker Changes (`docker-compose.yml`)

Add volume for receipt photo storage:
```yaml
backend:
  volumes:
    - recon_uploads:/app/uploads/reconciliation

volumes:
  recon_uploads:
```

---

## 8. Implementation Order

| Phase | Tasks |
|-------|-------|
| **1. Foundation** | DB tables + `role` column in `init_clean.sql`, `reconciliation_service.py` with payment categorization, Newbook client extensions, router skeleton in `reconciliation.py`, register in `main.py`, update `auth.py` for role support |
| **2. Frontend Shell** | Create `Reconciliation.tsx` with sidebar nav + empty sub-pages, add route/menu in `App.tsx` with role-based routing |
| **3. Cash Up Core** | Cash up form as shared component (denominations + cards + notes + save/load), Newbook payment fetch, reconciliation variance display, attachments |
| **4. Staff Page** | Create `StaffCashUp.tsx` reusing shared cash-up components, stripped-down header, staff role redirect after login, add role to user creation in Settings |
| **5. History & Reports** | History page with filters/pagination/actions, bulk finalize, multi-day report with 3 Excel-friendly tables (cell selection, tab-separated clipboard copy, selection tooltip) |
| **6. Floats** | Petty Cash, Change Tin (with per-denom targets), Safe Cash - as shared components used by both admin and staff pages |
| **7. Settings & Polish** | Reconciliation settings page (recon-specific only, not Newbook creds), GL account refresh, dirty-form warnings |

---

## 9. Verification

- **Database**: Run `init_clean.sql` against fresh DB, verify all 11 tables + `role` column with `\dt recon_*` and `\d users`
- **Backend**: Hit `/reconciliation/settings` to confirm router registered; test cash-up CRUD cycle
- **Newbook**: Use `/reconciliation/newbook/payments/{date}` to verify payment fetch + categorization (using credentials from main settings)
- **Frontend (admin)**: Login as admin, navigate to Reconciliation menu, verify sidebar nav, test cash-up save/load cycle
- **Frontend (staff)**: Create a staff user, login, verify redirect to `/staff`, verify only Cash Up/Petty Cash/Change Tin visible, verify cannot access admin routes
- **Excel copy-paste**: Open multi-day report, select cells, Ctrl+C, paste into Excel/Sheets, verify tab-separated values with clean numbers
- **Docker**: Rebuild with `docker-compose up --build`, verify uploads volume mounted
- **End-to-end**: Create a cash-up draft -> fetch Newbook data -> review reconciliation -> finalize -> view in history -> generate multi-day report -> copy to Excel
