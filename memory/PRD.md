# PRD — Masse Salariale CCQ (Workforce Budgeting Dashboard)

## Original Problem Statement
French-language, highly fluid single-page workforce budgeting app for a Quebec technical/construction company. Calculates payroll projections (masse salariale) with multi-scenario comparison, strictly separating Standard employees from CCQ union employees (Électriciens & Frigoristes). Left control panel (scenario tabs + category sliders), right real-time canvas (KPI cards + stacked bar chart + employee CRUD table).

## User Choices
- Persistence: Backend + MongoDB for employees; real-time calculations on frontend.
- Employees: full CRUD (add/edit/delete) + pre-seeded mock data.
- Treasury: fixed budget (2,500,000 CAD).
- Design: chosen by agent (Swiss Brutalist / high-density data, IBM Plex Mono + Archivo).

## Architecture
- Backend: FastAPI + MongoDB (motor). Endpoints: GET /api/config, GET/POST/PUT/DELETE /api/employees. Auto-seeds 12 employees on startup. Business constants: EMPLOYER_TAX_RATE=0.1477, TREASURY_BUDGET=2,500,000, CCQ benefit rates per trade.
- Frontend: React SPA. src/lib/calculations.js holds real-time projection engine (useMemo). Components: Dashboard, ScenarioTabs, CategoryControls, KpiCards, SalaryChart (recharts), EmployeeTable.

## Core Requirements (static)
- Scenarios: Budget Initial (40h baseline), Croissance (CCQ overtime x1.5, +3 CCQ hires), Restrictif (35h, hiring frozen).
- CCQ formula: (Hourly*Hours)+(BenefitsRate*Hours)+(Tax*Hourly*Hours). Standard: salary*hoursFactor*(1+tax).
- KPIs: Total Masse Salariale, Total Cotisations CCQ, Solde de Trésorerie Restant.
- Real-time recompute on any slider/scenario change; no page reload.

## Implemented (2026-06)
- [x] Full backend CRUD + config + seed data.
- [x] Real-time projection engine with scenario modifiers + new-hire ramp.
- [x] Left control panel (scenario tabs, category sliders with frozen-hiring lock).
- [x] KPI cards, monthly stacked bar chart, employee CRUD table + dialog.
- [x] French UI, Swiss brutalist design.
- [x] Tested: 100% backend (pytest) + 100% frontend (Playwright E2E).

## Backlog / Next
- P1: Scenario comparison side-by-side view (compare all 3 at once).
- P1: Export projection to CSV/PDF.
- P2: Persist scenario slider adjustments to backend (payroll_projections collection).
- P2: Editable treasury budget & CCQ rates from UI.
