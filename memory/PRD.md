# PRD — Budget Masse Salariale CCQ (rebuild du modèle Excel)

## Problème / Objectif
Refaire entièrement le fichier Excel de budget salarial (Québec CCQ) en application web fluide : dashboards, saisie et extraction faciles, formulaires de saisie + recherche, tables d'employés, hypothèses facilement modifiables, en conservant la philosophie de calcul de l'Excel.

## Choix utilisateur
- Remplace l'ancien simulateur de scénarios.
- 4 onglets : Tableau de bord · Employés · Budget Salaires · Hypothèses.
- Comparatif des 3 sections (Salaire Actuel / Budget CA / Budget Revue) — important.
- Fiche Employé : # auto-incrémenté, âge auto (date naissance), ancienneté auto (date embauche), tous champs obligatoires + messages d'erreur.
- Hypothèses persistées en MongoDB, éditables. Champ "augmentation" retiré des hypothèses → piloté dans l'onglet Budget.
- Respect des conditions du fichier Template App Budget.

## Conditions Excel implémentées
- CCQ : avantages sociaux 32.33% + RRQ/AE/RQAP/FSS normaux ; pas de vacances, assurance, REER (RPDB/BONI/Assu. masqués) ; prime électricien compagnon +5%.
- Prime de garde = (365 × 250$) / nb employés admissibles (coût moyen).
- Primes 8/11/12% calculées automatiquement sur le nouveau salaire.
- Charges sociales avec plafonds/exemptions ; CSST par département.

## Architecture
- Backend FastAPI + MongoDB. Collections: employees, hypotheses (doc key="current"). Endpoints: /api/employees (CRUD + ?q recherche, employee_number auto), /api/hypotheses (GET/PUT), /api/budget (3 sections + agrégats dashboard). Moteur de calcul compute_section().
- Frontend React SPA, nav par état (4 onglets). Recharts, framer-motion, shadcn/ui. Design Swiss brutalist (Archivo + IBM Plex Mono/Sans).

## Implémenté (2026-06)
- [x] CRUD employés + recherche, # auto, âge/ancienneté auto, validation champs obligatoires.
- [x] Onglet Hypothèses éditable (taux RRQ/AE/RQAP/FSS, CCQ, primes, CSST par département) persisté.
- [x] Budget Salaires : 3 sections comparatives + contrôles d'augmentation temps réel + détail par employé.
- [x] Tableau de bord : KPI + graphiques (comparatif scénarios, camembert CCQ/Régulier, coût par département).
- [x] Tests : 100% backend (pytest) + 100% frontend (Playwright E2E).

## Backlog / Next
- P1: Export Excel/PDF du budget et de l'effectif.
- P1: Modèle Pydantic pour PUT /api/hypotheses (validation d'entrée).
- P2: Compteur atomique MongoDB pour employee_number (concurrence).
- P2: Historique multi-années et duplication d'année budgétaire.
- P2: Champ BONI éditable pour employés Réguliers.
