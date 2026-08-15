# Meelora — Suite E2E Playwright (permanente)

Couvre P1.13D / P1.13D.2 : contexte plateforme, fiche client, séparation des logs,
assistant d'invitation, activation à usage unique, multi-société et sécurité
(fail-closed).

## Prérequis
- Navigateur déjà installé : `npx playwright install chromium`
- L'app tourne (frontend + backend via supervisor). L'URL de base est lue depuis
  `frontend/.env` (`REACT_APP_BACKEND_URL`), surchargeable via `E2E_BASE_URL`.

## Lancer
```bash
cd /app/frontend
npx playwright test --config=e2e/playwright.config.js            # toute la suite
npx playwright test --config=e2e/playwright.config.js e2e/platform-context.spec.js  # un fichier
npx playwright show-report e2e/playwright-report                 # rapport HTML
```

## Fichiers
- `helpers.js` — identifiants de test + connexion.
- `platform-context.spec.js` — bascule de contexte, nav plateforme, fiche client (6 onglets), séparation des logs.
- `access-flows.spec.js` — assistant d'invitation, round-trip d'activation, multi-société.
- `security.spec.js` — un user simple ne voit pas la plateforme ; API plateforme fail-closed (403) ; logs plateforme scoping.

## Identifiants
Voir `/app/memory/test_credentials.md`.
