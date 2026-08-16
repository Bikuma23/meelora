# Rapport complémentaire — Sign-off P1.13E (sécurité & UX accès)

Date : 2026-06 · Statut : **RAPPORT — aucune migration appliquée** (`--commit` NON exécuté) · P3.x non repris.

Ce document répond aux 4 points du sign-off conditionnel. Aucun moteur financier n'a été
modifié. Les seules modifications de code portent sur la navigation (point 2, autorisée) et
les tests E2E associés.

---

## 1. Domaine REPORTING — mapping documenté (aucun moteur modifié)

REPORTING (module commercial) et le legacy `/api/reports` sont **deux choses distinctes**.
Le middleware de gating l'acte déjà explicitement (`server.py`, `MODULE_ROUTE_MAP`) :
`/api/reports` (rapports **budgétaires** legacy) est gaté par **BUDGETS**, jamais par REPORTING.

### 1.1 BUDGETS — périmètre legacy (inchangé)
Le module **BUDGETS** possède, comme 1er sous-domaine, l'historique masse salariale :
- masse salariale (CCQ / régulier / stagiaire) ;
- employés utilisés pour le budget ;
- hypothèses ;
- départements ;
- budgets (scénarios Budget CA / Revue 1 / Revue 2) ;
- **rapports budgétaires legacy** (`/api/reports`, `/api/reports/*` : synthèse, P&L masse,
  par département, comparatif scénarios, fiches détaillées, exports Excel/PDF).

→ **Confirmation** : `/api/reports` correspondant aujourd'hui **uniquement** aux rapports
budgétaires legacy, il **reste gaté par BUDGETS**. (`MODULE_ROUTE_MAP`:
`("/api/reports", "BUDGETS", "acct")`.)

### 1.2 REPORTING — reporting financier normalisé (déjà construit / prévu)
Le module commercial **REPORTING** couvre les fonctions de reporting financier normalisé,
qui vivent sous les routes `/api/acct/*` et `core/financial/*` (PAS `/api/reports`) :
- Bilan (détaillé + sommaire) ;
- État des résultats (P&L détaillé + sommaire) ;
- Flux de trésorerie (`/api/acct/cashflow`, `core/financial/cash_flow.py`) ;
- `report_runs` (`db.report_runs`) ;
- états financiers ;
- dashboards (indicateurs, KPI, projections) ;
- analyses & variances (analyse d'écarts, variance IA) ;
- diffusion / reporting externe (permission cataloguée `reporting.external_send`).

→ **Décision documentée** : **ne pas assimiler REPORTING au legacy `/api/reports`**. Aucun de
ces moteurs n'a été touché en P1.13E. Le catalogue de permissions REPORTING existe déjà
(`permissions_catalog.py` : `reporting.import`, `mapping_confirm`, `report_generate`,
`report_finalize`, `external_send`, `template_manage`, `settings_manage`).

> Note d'implémentation : ces moteurs financiers normalisés sont aujourd'hui servis par les
> routes `/api/acct/*` (gatées ACCOUNTING) et non par une route « REPORTING » dédiée. Le
> câblage d'un module REPORTING séparé (routes propres + gating REPORTING) est un travail
> futur explicite ; il n'a **pas** été fait ici pour respecter « ne pas modifier ces moteurs ».

---

## 2. Navigation hiérarchique obligatoire — conforme + testée

### 2.1 État après P1.13E
| Élément attendu | État |
|---|---|
| Contexte plateforme : sidebar = Tableau de bord + Sociétés / Clients | ✅ Conforme |
| + « Logs plateforme » dans la sidebar plateforme | ✅ **Ajouté** (choix client 1.b) |
| Page Sociétés / Clients : carte Meelora 1re, fond vert, bouton Accéder | ✅ Conforme (`platform-internal-card`, fond `#15AF97/8`, `platform-internal-access`) |
| Accéder (carte Meelora) → contexte Société Meelora | ✅ Conforme (`enterCompanyContext` → contexte société) |
| Contexte client : libellé « Tous les mandats » | ✅ Conforme (`nav-mandats_list`) |
| Liste Tous les mandats : bouton Accéder par mandat | ✅ Conforme (`mandat-access-<cid>`) |
| Accéder à un mandat → contexte courant + recharge entitlements + recharge droits effectifs + sidebar métier dynamique | ✅ Conforme (`enterMandat` → refetch `GET /api/companies/{cid}/navigation` → `resolve_effective_access`) |

> **Écart assumé vs spec littérale** : la spec dit « sidebar plateforme … rien d'autre ». Sur
> votre choix explicite **1.b (garder Logs)**, « Logs plateforme » a été (r)ajouté comme 3e
> entrée de la sidebar plateforme. Il reste **strictement scopé plateforme** (aucun flux
> agrégé des opérations clients — `GET /api/platform/logs`).

### 2.2 Preuves de test (Playwright — `e2e/nav-hierarchy.spec.js`, 3/3 verts)
1. **Meelora → Sociétés / Clients → Meelora → Accéder** ⇒ bascule en contexte Société Meelora
   (sidebar métier visible, nav plateforme disparue).
2. **Client → Tous les mandats → Société A (Meelora) → Accéder** ⇒ modules de A
   (BUDGETS + ACCOUNTING visibles, CONSOLIDATION absent) ; **retour → Société B (9434) →
   Accéder** ⇒ modules de B (CONSOLIDATION + ACCOUNTING) et **BUDGETS n'apparaît plus**.
   → **Preuve que les accès de A ne persistent pas dans B.**
3. **Isolation renforcée (API)** : `GET /api/companies/A/navigation` expose BUDGETS mais
   `GET /api/companies/B/navigation` ne l'expose pas (et inversement pour CONSOLIDATION).
   L'isolation est **structurelle** (recalcul serveur par société), pas seulement visuelle.

Suite complète : **28/28 tests verts** (`persona-ux`, `platform-context`, `security`,
`access-flows`, `nav-hierarchy`). Le gating par module au niveau API garantit qu'un menu
masqué n'est jamais atteignable par URL/API (`security.spec.js` : routes legacy gatées).

---

## 3. Migration P1.13A — les 7 grants, EXPLICITES (avant validation, SANS `--commit`)

Dry-run relancé : `entitlements à activer = 0` · `user_module_access (read) = 7` ·
`reported = 0`. Toutes les lignes sont **read ACCOUNTING** sur la société **Meelora**
(`965f0770-8cf2-4199-a99f-819ff270436a`, workspace `ws_56c492936ea64c4db53a2f14a0825ef5`).

Justification commune : la société **Meelora UTILISE** le module ACCOUNTING (données
comptables présentes : `acct_periods` / `acct_bv`). Chaque grant dérive d'une
**`company_membership` active** (pont legacy). Dérivation conservatrice = **read**
(equal-or-less, aucune escalade).

| Utilisateur | Société | Accès legacy constaté | Module proposé | Niveau proposé | Justification |
|---|---|---|---|---|---|
| julie@accslegro.com | Meelora (`965f0770…436a`) | `company_membership` rôle **principal** (active) | ACCOUNTING | read | Société Meelora utilise ACCOUNTING (données `acct_periods`/`acct_bv`). Adhésion active → accès dérivé conservateur = read. Aucune escalade. |
| marc@accslegro.com | Meelora (`965f0770…436a`) | `company_membership` rôle **collaborator** (active) | ACCOUNTING | read | Idem : société utilise ACCOUNTING ; collaborateur actif → read only. |
| platform@meelora.com | Meelora (`965f0770…436a`) | `company_membership` rôle **collaborator** (active) — **dérivé de l'adhésion société, PAS du platform_role** | ACCOUNTING | read | Le grant provient de l'adhésion société collaborator, jamais de `platform_role=platform_admin`. read only. |
| persona_clientadmin@accslegro.com | Meelora (`965f0770…436a`) | `company_membership` rôle **admin** (active) | ACCOUNTING | read | Admin société ⇒ read seulement (admin ≠ autorité financière ; aucun manage/sensible auto). |
| persona_reporting@accslegro.com | Meelora (`965f0770…436a`) | `company_membership` rôle **user** (active) | ACCOUNTING | read | Société utilise ACCOUNTING ; membre actif → read only. |
| persona_consol@accslegro.com | Meelora (`965f0770…436a`) | `company_membership` rôle **user** (active) | ACCOUNTING | read | Société utilise ACCOUNTING ; membre actif → read only. |
| persona_budgets@accslegro.com | Meelora (`965f0770…436a`) | `company_membership` rôle **user** (active) | ACCOUNTING | read | Société utilise ACCOUNTING ; membre actif → read only. |

### 3.1 Invariants confirmés (script `scripts/p1_13a_grant_details.py`)
- **0 `manage` automatique** — aucun niveau manage dérivé (aucun signal explicite en legacy).
- **0 permission sensible automatique** — le script n'écrit **jamais** dans
  `user_permission_grants` ; aucune permission comptable n'est accordée.
- **0 grant via `platform_role`** — les 7 grants dérivent **uniquement** de
  `company_membership` actif. Le cas #3 (platform_admin) le prouve : le grant vient de son
  adhésion société `collaborator`, pas de son rôle plateforme.
- **0 cross-workspace** — les 7 grants sont sur la société Meelora du workspace Meelora ;
  aucune fuite inter-workspace.
- **0 grant BUDGETS implicite** — l'ajout du 5e module (BUDGETS) **n'a créé aucun grant** :
  la migration ne dérive un accès QUE sur les modules réellement utilisés par la société
  (ACCOUNTING via `acct_periods/acct_bv`). Aucune donnée BUDGETS « utilisée » détectée →
  0 grant BUDGETS. (Le détecteur `_company_used_modules` ne teste que ACCOUNTING et REPORTING.)

> **Validation demandée** : merci de valider ces 7 lignes. **Aucun `--commit` ne sera lancé
> sans votre feu vert explicite.**

Rejouer les preuves :
```
python backend/scripts/migrate_p1_13a_access.py            # dry-run (n'écrit rien)
python backend/scripts/p1_13a_grant_details.py             # les 7 lignes + invariants
```

---

## 4. Permissions comptables sensibles — sous-phase séparée recommandée (P1.13F)

Le **gating par module** (P1.13E) est en place et validé. Mais les **actions sensibles**
ne vérifient PAS encore de **permission explicite** ; elles reposent sur l'autorisation
Phase 1 (`require_admin`) ou sur un simple contrôle d'accès société + verrou d'exercice.

| Action sensible | Permission cataloguée (existe) | Route actuelle | Garde réelle aujourd'hui |
|---|---|---|---|
| Clôture d'exercice/période | `accounting.period_close` | `PATCH /companies/{cid}/financial-years|periods/{id}` (status→closed/locked) | `require_admin` (pas de permission explicite) |
| Réouverture | `accounting.period_reopen` | idem (status→open) | `require_admin` |
| Comptabilisation (post GL) | `accounting.entry_post` | *(pas de route générique de post GL dans le nouveau module — journal-entries en lecture seule)* | N/A (non encore réellement disponible) |
| Extourne | `accounting.entry_reverse` | `POST /qc9434/invoices/{iid}/reverse` (legacy) | `get_current_user` + accès société + verrou exercice |
| Réconciliation (approbation) | `accounting.reconciliation_approve` / `_manage` | `GET /companies/{cid}/reconciliation/*` | **lecture seule / diagnostic** (aucune écriture, P2.9) |

**Constat** : le catalogue de permissions sensibles existe (`permissions_catalog.py`) et
`resolve_effective_access` sait vérifier une permission (`required_permission`), mais ces
vérifications **ne sont pas encore câblées** sur les routes d'action sensibles. La plupart de
ces opérations (post GL générique, approbation de réconciliation, extourne dans le nouveau
module) **ne sont pas encore réellement disponibles** dans le module Comptabilité refondu.

**Recommandation** : traiter ce câblage comme une **sous-phase dédiée (P1.13F)**, à activer
lorsque ces opérations deviennent réelles dans le nouveau module Comptabilité. Chaque route
sensible devra alors exiger, en plus du gating module, la **permission explicite**
correspondante via `resolve_effective_access(..., required_permission=...)`. **Aucune
modification financière n'a été faite ici.**

---

## Conclusion & STOP
- Points 1, 2, 3, 4 traités. Navigation adaptée (Logs plateforme selon 1.b) + **28/28 E2E verts**.
- Les **7 grants** sont listés explicitement pour votre validation.
- **`--commit` NON exécuté.** En attente de votre validation des 7 lignes.
- **P3.x non repris.**

---

## 5. Parcours UX validés (tour complémentaire — nouvelle spec)

Modifications de code (frontend uniquement, autorisées) + **28/28 E2E verts**.

### 5.1 Employé Meelora SANS rôle plateforme
- Sidebar = **uniquement ses modules métier effectifs** (entrée générique « Tableau de bord » retirée ; le tableau de bord budgétaire est désormais rattaché au module BUDGETS).
- Aucun menu plateforme, aucun « Société Meelora », aucun « Logs plateforme ».
- « Tous les mandats » n'apparaît que pour un utilisateur multi-mandats.
- **Landing** : login → **Comptabilité en priorité si ACCOUNTING attribué**, sinon 1er module.
- Preuves : `persona-ux.spec.js` (personas mono-module, Client Admin), `security.spec.js`.

### 5.2 Employé Meelora AVEC rôle plateforme — EXTENSION (pas bascule)
- Sidebar plateforme = **Tableau de bord · Sociétés / Clients · Société Meelora · Logs plateforme** (appellation « Sociétés / Clients » conservée, choix A).
- **Société Meelora → Accéder** : **ajoute** les modules métier réellement autorisés à la sidebar **en conservant** les 4 menus plateforme (choix B — extension, pas remplacement de contexte).
- `platform_role` n'accorde **aucune** permission financière : pour `platform@` (adhésion « nue »), l'extension est **vide** → preuve visible que platform_role ≠ autorité.
- Preuves : `platform-context.spec.js`, `nav-hierarchy.spec.js`, `security.spec.js`.

### 5.3 Accueil client & « Tous les mandats »
- Multi-mandats : l'utilisateur **atterrit sur « Tous les mandats »** (accueil client), chaque mandat portant un bouton **Accéder**.
- **Accéder** à un mandat : définit le contexte société, recharge les droits effectifs (`resolve_effective_access`), recompose la sidebar, ouvre les modules du mandat. Isolation A↛B prouvée.
- Preuves : `nav-hierarchy.spec.js`, `access-flows.spec.js`.

### 5.4 Formulaire « Créer une société / client » — complet & fiscalité extensible
- Sections : Identification (nom d'affichage, **nom légal**, **nom commercial**, **type d'entité**, code, **n° d'entreprise**), Adresse & coordonnées (adresse, ville, **province/canton/état**, code postal, **pays**, **juridiction**, **téléphone**, **courriel**), **Fiscalité conditionnelle**, Paramètres (**devise**, **langue**, secteur, type, exercice), **Modules souscrits** (5 canoniques), **Administrateur à associer/inviter** (courriel).
- **Modèle fiscal EXTENSIBLE par juridiction** (pas Canada-exclusif) : Canada → **BN**, **TPS/GST**, **TVQ/QST** (si province = QC), **PST** (si BC/SK/MB) ; Suisse → **IDE/UID**, **TVA**. Backend permissif (`tax_profile` dict, nettoyé, ordre modules canonique).
- Preuves : `company-form.spec.js` (champs + bascule QC↔BC↔Suisse) + curl backend (création complète, devise normalisée, QST conservée / PST vide retirée).

> Note d'interprétation « Accueil Client » : l'accueil d'un client multi-mandats **est** la liste « Tous les mandats » (avec un bouton Accéder par mandat). L'infra d'invitation admin existante (P1.13D) reste le canal d'invitation ; le courriel admin saisi au formulaire est stocké sur la société (`admin_email`).
