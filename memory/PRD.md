# PRD — Budget Salaires Pro (Masse salariale CCQ, Québec)

> ⚠️ **CONTRAINTE PERMANENTE — STRAT-01 PRODUCT CHARTER** : voir
> `/app/memory/STRAT-01_PRODUCT_CHARTER.md`. Toute nouvelle tranche doit respecter
> la charte (UX Happy Path/Exceptions First, Time-to-Done, Financial Core sans
> ledger parallèle, périodes closed terminales, P1.13, IA = assistance non-autorité
> + zéro-entraînement, Country Packs, fiscalité versionnée snapshotée, documents
> Object Storage). Passer le **Gate §21** avant de déclarer une fonctionnalité
> terminée. Ne PAS modifier l'existant seulement pour « aligner » la charte sans
> demande explicite ; signaler les contradictions importantes.


## Problème / Objectif
Application web de budgétisation de la masse salariale (Québec, convention CCQ) reconstruite d'après un modèle Excel puis refondue d'après des maquettes fournies. Saisie & extraction faciles, tableaux de bord, hypothèses modifiables, séparation stricte employés CCQ (Électricien/Frigoriste) vs standard.

## Authentification
- JWT email/mot de passe. Admin seed : admin@accslegro.com / admin123.
- Token en cookie httpOnly + body (localStorage + Bearer). Toutes les routes /api protégées.

## Architecture
- Backend FastAPI + MongoDB. Collections : users, employees, departments, hypotheses, journal.
- Moteur `compute_budget` : CCQ (avantages 32.33% + charges normales, sans vacances/assurance/REER, +5% élec. compagnon) vs Régulier/Stagiaire. Vacances = taux × (nouveau salaire + toutes primes, boni inclus). Alloc. sécurité 260$/an. Aucune « prime chef d'équipe ». Cotisations RRQ/AE/RQAP/FSS/CSST avec maximums assurables (plafonds Québec, éditables).
- Import Excel (Employés + Départements) + modèles téléchargeables (openpyxl).
- Journal d'audit : chaque create/update/delete est journalisé (log_action).
- Frontend React : AuthContext + Login, Layout sidebar navy/teal, pages : Dashboard, Employés, Salaires & Budget (fiche éditable), Hypothèses, Départements, Rapports (placeholder), Journal.

## Implémenté (Phase 1 — 2026-07)
- [x] Auth JWT (login/logout/me, admin seed, routes protégées).
- [x] Refonte visuelle complète (sidebar sombre, thème teal/bleu, cartes blanches).
- [x] Types d'emploi élargis (CCQ, Régulier temps plein, Stagiaire).
- [x] Module Départements CRUD (code, description, superviseur, compte GL, groupe P&L, CSST) + import/modèle Excel.
- [x] Journal de logs (historique des modifications).
- [x] Tableau de bord : 4 KPI, budget par département, types d'emploi (donut), ventilation mensuelle (table + barres empilées), décomposition, Top 5.
- [x] Employés : CRUD + recherche + validation obligatoire + âge/ancienneté auto + « Aucune Prime » + import/modèle Excel.
- [x] Fiche Salaires & Budget éditable (preview live, sans chef d'équipe, alloc 260$, vacances sur salaire+primes+boni).
- [x] Hypothèses : jours ouvrables CCQ/standard, charges sociales avec maximums assurables, augmentations, autres paramètres.
- [x] Tests : 18/18 backend + 100% frontend.

## Implémenté (Phase 2 — 2026-07)
- [x] Module Rapports : export **Excel** (Résumé, Détail employés, Par département, Ventilation) et **PDF** (KPI, ventilation, par département), filtrables par département.
- [x] Filtres **Année + Département** sur le tableau de bord (re-calcul en temps réel via /budget?department).
- [x] Validation du code département à la création/modification d'employé **et** à l'import Excel (400 si inexistant).
- [x] Aperçu du rapport (KPI + ventilation + par département) dans la page Rapports.
- [x] Tests : 30/30 backend + 100% frontend.

## Règle primes (2026-07)
- [x] Employés **non-CCQ** : aucune prime. Saisie des primes désactivée dans le formulaire employé ET la fiche ; lignes de primes retirées du calcul automatique. Serveur force primes=0 pour non-CCQ (même si override). BONI / RPDB-REER / Assu. collectives restent (propres aux réguliers). Primes = CCQ uniquement.
- [x] Tests : 33/33 backend + 100% frontend.

## Ajustements primes/gardes (2026-07)
- [x] Prime de garde **hebdomadaire** : coût moyen/an = (52 gardes × 250$) ÷ nb employés admissibles (CCQ). Ex. 25 admissibles → 520$/employé/an.
- [x] Fiche « Calcul automatique » : libellés « Boni » et « Vacances ».
- [x] Boni saisissable en **$ ou en %** (mode au choix ; % = pourcentage du nouveau salaire, inclus dans le calcul des vacances).

## Règles finales primes/garde (2026-07-10)
- [x] **Suppression totale de « Prime électricien compagnon »** : retirée du calcul (compute_budget), de la sortie budget (plus de clé `compagnon`), de la page Hypothèses et de la Fiche Salaires & Budget. Migration `$unset ccq_electricien_compagnon_rate` au démarrage pour nettoyer la DB seedée.
- [x] **Prime de garde** confirmée : 1 seule garde à la fois → coût_unitaire(250$) × nb_paies(52) ÷ nb employés CCQ admissibles (≈ 2 gardes/employé). Paramètres éditables dans Hypothèses. Aucun changement de formule requis.
- [x] **CSST** plafonné au maximum assurable (via `_capped`, déjà en place).
- [x] **Validation garde ↔ type de prime** : si « Prime de garde » cochée mais « Type de prime » = « Aucune Prime », l'enregistrement est bloqué avec erreur — dans le **formulaire Employé** ET la **Fiche Salaires & Budget**.
- [x] Tests : frontend 100 % (iteration_7), backend OK (clé obsolète nettoyée).

## Multi-années + 3 scénarios (2026-07-10)
- [x] **3 scénarios de masse salariale** par année : `actuel` (somme des salaires de base), `ca` (Budget CA = actuel + augmentations/primes), `revue` (Revue Budgétaire, overrides indépendants par employé, sans toucher au Budget CA). Stockage : `employee.years[{year}].{base_salary, ca, revue}`.
- [x] **Multi-années** : sélecteur d'année global (header), création d'année avec **report/rollover** (le Budget CA ou la Revue de l'année source devient le salaire actuel de la nouvelle année). Hypothèses stockées par année (`key=y{year}`), `settings.active_year`.
- [x] **Fiche Salaires & Budget** : bascule scénario (Budget CA / Revue Budgétaire) ; la fiche édite le bucket du scénario actif.
- [x] **Dashboard** : carte comparatif des 3 masses + sélecteurs Année/Scénario/Département.
- [x] **Rapports** : sélecteur de catégorie (3 scénarios) + année ; export Excel/PDF par catégorie.
- [x] Endpoints : GET/POST /api/years, PUT /api/years/active, GET/PUT /api/hypotheses?year=, GET /api/budget?year=&scenario=, GET /api/budget/compare, preview/override ?year=&scenario=, reports ?year=&scenario=.
- [x] Tests : backend 15/15 (pytest), frontend 100 % (iteration_8). Indépendance CA/Revue et rollover confirmés.

## Fiche par employé, 2 revues, verrous & utilisateurs (2026-07-10)
- [x] **Bascule scénario dans la Fiche par employé** (Salaires & Budget) : chaque fiche permet de saisir la Revue Budgétaire sans toucher au Budget CA (salaire de base désactivé/exclu en mode revue).
- [x] **2 Revues Budgétaires par année** : scénarios = Budget CA · Revue Budgétaire 1 · Revue Budgétaire 2 (+ Salaires actuels). Overrides indépendants par employé (`years[{year}].{ca,revue1,revue2}`).
- [x] **Verrouillage par année + scénario** : admin verrouille/déverrouille un budget validé (`db.locks`, key `YYYY:scenario`). Enforcement backend : save_override (par scénario), hypothèses (par année), employés (tout verrou). Admin bypass. Non-admin bloqué (403) + UI lecture seule (badge/bandeau, boutons désactivés).
- [x] **Gestion des utilisateurs (admin)** : page Utilisateurs — créer/modifier/supprimer comptes (rôle Admin/Utilisateur), hash bcrypt, unicité courriel, protection du dernier admin. Nav 'Utilisateurs' visible admin uniquement.
- [x] **Dashboard** : comparatif des 4 masses + graphique d'évolution pluriannuelle (si ≥2 années). **Rapports** : 4 catégories exportables (Excel/PDF).
- [x] Tests : backend 19/19 (pytest, iteration_9), frontend 100 %. Comptes : admin@accslegro.com/admin123, user1@accslegro.com/user123.

## Ajustements UI/UX & garde 2,08 (2026-07-10)
- [x] Titre de la fiche de saisie sans le mot « Fiche » (ex. « Budget CA 2026 — Nom »).
- [x] Prime de garde = **2,08 gardes/an/employé** (montant fixe = 2,08 × 250 $ = 520 $ par employé CCQ admissible, sans division par l'effectif).
- [x] La fiche de saisie **reste ouverte après « Enregistrer »** (refetch en place) ; « Fermer » ferme.
- [x] Titre du formulaire employé = « Nom — #matricule » (sans « Modifier — »).
- [x] **Clic sur une ligne** (Saisie & calcul par employé) ouvre un **détail lecture seule** (BudgetDetailDialog) de tous les éléments de la masse salariale ; le crayon (modification) reste disponible.
- [x] Badge de verrou enrichi : « Verrouillé · courriel le date » (locked_by/locked_at).
- [x] Tests : frontend 100 % (8/8, iteration_10), backend garde=520 $ validé (curl).

## Export PDF fiche employé (2026-07-10)
- [x] Endpoint `GET /api/employees/{eid}/fiche-pdf?year=&scenario=` : génère un PDF détaillé de la masse salariale d'un employé (salaire, primes, cotisations/avantages, total) via reportlab.
- [x] Bouton « Exporter en PDF » (detail-pdf-btn) dans la fenêtre de détail (lecture seule).
- [x] Validé : backend HTTP 200 + application/pdf (curl).

## Exports groupés par département (2026-07-10)
- [x] `GET /api/reports/fiches-pdf` (paysage) & `GET /api/reports/fiches-excel` : fiches détaillées de tous les employés regroupées par département, avec sous-totaux par département + budget total. Filtres année/scénario/département.
- [x] Page Rapports : boutons « Fiches détaillées (Excel) » et « Fiches détaillées (PDF) » en plus des synthèses. Validé backend (curl, PDF %PDF + xlsx 200).

## Import avec matricules définis (2026-07-10)
- [x] Le modèle Excel employés (`GET /api/employees/template`) inclut en 1re colonne « Matricule (# — laisser vide pour auto) ».
- [x] Import (`POST /api/employees/import`) : utilise le matricule fourni (validation entier + unicité dans le fichier), sinon auto-attribution. **Upsert** : si le matricule existe déjà, l'employé est mis à jour (champs de base, sans toucher aux overrides `years`) au lieu d'être rejeté. Retour {inserted, updated, errors}. Validé par curl.

## Alloc. sécurité pour non-CCQ (2026-07-10)
- [x] L'allocation sécurité (montant depuis les hypothèses) est désormais applicable aux employés **non-CCQ** (calcul backend + incluse dans les primes/total), en plus des CCQ. Switch ajouté dans le formulaire Employé et la fiche Salaires & Budget (non-CCQ), affichée dans le détail et le PDF. Validé par curl (260 $).

## Ventilation mensuelle par jours ouvrables (2026-07-10)
- [x] Toutes les ventilations mensuelles (fiche par employé + ventilation globale du tableau de bord/rapports) suivent désormais les **jours ouvrables** définis dans les Hypothèses : `working_days_ccq` pour les employés CCQ, `working_days_std` pour les standards. Chaque mois reçoit une part = jours_ouvrables[mois] × pro-rata / total_jours. La ventilation globale est agrégée à partir des ventilations individuelles pondérées. Validé par curl (CCQ juil.=13j/déc.=14j réduits ; standard juil.=23j).

## Jours ouvrables auto-calculés par année (2026-07-10)
- [x] À la création d'une nouvelle année (et à l'initialisation des hypothèses d'une année), les jours ouvrables sont calculés **automatiquement** : nombre de jours de semaine (lun→ven) par mois, **sans déduire les jours fériés officiels du Québec**.
- [x] Pour les employés **CCQ**, on déduit automatiquement les **vacances de la construction** (convention CCQ) : congé estival (2 sem. se terminant le 1er samedi d'août) + congé hivernal (2 sem. se terminant le 1er samedi de janvier, portion de décembre). Règle validée : 2026 CCQ = [22,20,22,22,21,22,13,21,22,22,21,14] (identique aux valeurs existantes), 2027/2028 recalculés dynamiquement.
- [x] Implémenté dans `server.py` : `compute_working_days(year, ccq)`, `_ccq_vacation_ranges`, `_apply_working_days`, appelés dans `_get_hypo` et `create_year`. Validé end-to-end (curl création d'année).
- Décision utilisateur : pas de grille éditable dans Hypothèses ; notification courriel à la création d'utilisateur reportée (service configuré avant mise en ligne).

## Augmentation globale depuis Salaires & Budget (2026-07-10)
- [x] Nouveau panneau « Augmentation globale » sur la page Salaires & Budget : champs CCQ (%) et Standard (%) pré-remplis depuis les hypothèses de l'année, bouton « Appliquer à tous ». Applique et **sauvegarde** l'augmentation (`years.{year}.{scenario}.augmentation` via `$set` ciblé, sans écraser les autres overrides) pour tous les employés du scénario/année sélectionnés. Ajustement individuel via la fiche toujours possible.
- [x] Endpoint `POST /api/budget/apply-augmentation?year=&scenario=` (body {ccq_pct, std_pct}). Respecte le verrou (admin bypass). Met aussi à jour les défauts d'hypothèses (augmentation_ccq/autres) quand scénario=ca. Validé par curl (CCQ 5%/Std 4% persistés puis restaurés à 3,33/3,5).

## Vacances & avantages CCQ sur salaire + primes (2026-07-10)
- [x] **Vacances CCQ** : désormais calculées (taux vacances de l'employé, ex. 13 %) sur **(nouveau salaire + primes)**, comme les non-CCQ. Auparavant 0 pour les CCQ.
- [x] **Avantages CCQ (32,33 %)** : calculés sur **(nouveau salaire + primes)** au lieu du salaire seul.
- [x] Le champ « Taux vacances (%) » est désormais éditable dans la fiche pour les CCQ. Vérifié par curl (Marie : vac=15 146,25 = 0,13×116 509,60 ; ccq_av=37 667,55 = 0,3233×116 509,60) et écran (colonnes Vacances/Avantages CCQ mises à jour).
- [x] **Salaire brut total** : ligne = nouveau salaire + vacances + primes + boni, affichée dans la fiche éditable, la fenêtre de détail (lecture seule) et le PDF de fiche employé — pour tous les employés (CCQ et non-CCQ). Ancienne ligne « Base de calcul » retirée.
- [x] **Colonne « Salaire brut total »** ajoutée au tableau « Saisie & calculs par employé » et aux exports Excel (feuille Détail employés + Fiches détaillées groupées, avec sous-totaux et budget total). Champ `salaire_brut` exposé dans les lignes de `compute_budget`. Validé par curl (champ + xlsx 200, en-têtes corrects) et capture d'écran (Marie CCQ : 131 656 $).

- [x] **Tri des colonnes** du tableau « Saisie & calculs par employé » : clic sur un en-tête trie (asc/desc) avec indicateur de flèche, sur toutes les colonnes (#, Nom, Type, Nouveau salaire, Vacances, Primes, Salaire brut total, Avantages, Coût total). Tri côté client. Validé par capture d'écran (tri décroissant par salaire brut).

- [x] **Ligne « Total » figée** en bas du tableau « Saisie & calculs par employé » (somme des colonnes affichées + nombre d'employés). Totaux cohérents avec les cartes KPI (validé : 34 employés, budget total 5 227 716 $).
- [x] **Colonne « Dépt »** (numéro de département) ajoutée entre Nom et Type dans le tableau, triable.
- [x] Libellé **« Régulier temps plein » affiché « Rég. Temps Plein »** dans les tableaux Salaires & Budget et Employés (mapping d'affichage, valeur stockée inchangée).

- [x] **Import Excel atomique** (Employés + Départements) : validation complète de toutes les lignes AVANT écriture ; si au moins une erreur est détectée, **rien n'est importé** (aborted). Erreurs structurées {ligne, élément, message}, avec détection des doublons intra-fichier (matricules/codes). Fenêtre modale `ImportErrorsDialog` : tableau « Ligne Excel · Élément · Erreur » + message « Aucune donnée n'a été importée ». Validé par curl (34 employés inchangés après erreurs, insertion OK sans erreur) et capture d'écran.

- [x] Bouton **« Exporter les erreurs (CSV) »** dans la fenêtre d'erreurs d'import : télécharge un CSV (BOM UTF-8, séparateur `;`) avec colonnes Ligne Excel · Élément · Erreur. Validé (téléchargement `erreurs_import_*.csv`).

- [x] **Nouveau type d'emploi « Régulier temps partiel »** : ajouté au modèle backend (Literal `EmployeeBase.employment_type`), à la validation d'import (`valid_types`), au formulaire Employé (liste déroulante) et au mapping d'affichage (« Rég. Temps Partiel »). Validé par curl (création OK) + UI.
- [x] **Confirmation avant suppression d'un employé** : boîte de dialogue `AlertDialog` (« Supprimer cet employé ? » + nom/matricule + avertissement irréversible, boutons Annuler/Supprimer). Remplace la suppression en un clic. Validé par capture d'écran.

## Statut actif/inactif, sexe à la naissance, recherche budget, compteurs dashboard (2026-07-11)
- [x] **Seed employés une seule fois** : indicateur persistant `settings.app.employees_seeded`. Si l'utilisateur vide volontairement la liste, les fiches de démonstration ne réapparaissent plus au redémarrage. Le seed n'écrase jamais de données existantes.
- [x] **Employé actif / inactif** (champ `active`) : bascule dans la fiche Employé ; les inactifs sont **exclus** des calculs de budget/totaux/ventilation/rapports/rollover/augmentation globale et **masqués par défaut** de la liste (bascule « Afficher inactifs » + badge « Inactif »). Filtre backend `_active_q`.
- [x] **Sexe à la naissance** (`sex_at_birth`) : Masculin / Féminin / Autre / Préfère ne pas répondre. Champ facultatif dans la fiche Employé.
- [x] **Barre de recherche** dans « Saisie & calculs par employé » : filtre multi-colonnes (matricule, nom, dépt, titre, type, et montants formatés) — recherche « ce que vous voyez ».
- [x] **Tableau de bord — carte Employés** : total actifs + compteurs CCQ / Non-CCQ / Stagiaire + répartition par sexe à la naissance (Masculin/Féminin/Autre/Non spéc.), police compacte (kpis backend `ccq_count`, `non_ccq_count`, `stagiaire_count`, `sex_counts`).
- Vérifié par curl (exclusion inactifs 122 vs 123, kpis) + captures (dashboard, recherche, formulaire, bascule).

- [x] **Import Excel : colonnes « Sexe à la naissance » et « Statut (Actif/Inactif) »** ajoutées au modèle et au parsing (validation du sexe, statut Inactif reconnu). Validé par curl (modèle 18 colonnes, sexe invalide → erreur ligne, import inactif OK). Champ « Sexe à la naissance » déplacé **en haut du formulaire, avant le nom**.

- [x] **Tableau de bord — Répartition par sexe à la naissance** : nouvelle carte avec camembert (Masculin/Féminin/Autre/Non spécifié) + tableau compact **par département** (M/F/A/N-S/Total). Données backend `sex_by_department` dans `compute_budget`. Polices réduites (10-11px) pour limiter la taille. Validé par curl + capture d'écran.

## Alignement fiche Employé + Date de fin d'emploi (2026-07-11)
- [x] **Bug d'alignement corrigé** dans le formulaire Employé : les cases calculées « Ancienneté » et « Âge » sont désormais des composants Field (avec libellé) et la grille est réordonnée → « Date d'embauche ↔ Ancienneté » et « Date de naissance ↔ Âge » alignées côte à côte. Sexe ↔ Statut en haut.
- [x] **Nouveau champ « Date de fin d'emploi »** (`end_date`, optionnel) : agit comme la date d'embauche (pro-rata au jour). `_proration` gère désormais embauche ET fin d'emploi → impacte le coût total et la ventilation mensuelle (mois après la fin = 0). Libellé de ventilation adapté (embauche / fin / actif de X à Y).
- Validé par testing_agent (iteration_12.json : backend 100%, frontend 100%, fin d'emploi 30/06 → factor 0.5, 6 mois actifs, Juil-Déc à 0).

## Rapports ERP + CNESST + Superviseur auto (2026-06-11)
- [x] **Page Rapports ERP** : 4 onglets (Synthèse, État des résultats P&L par compte GL + graphique, Masse par classe de sécurité + graphique, Constructeur de rapport personnalisé avec choix de colonnes + regroupement). Endpoints `/reports/pnl`, `/reports/by-class`, `/reports/custom`, `/reports/custom-columns` + exports Excel (pnl-excel, by-class-excel, custom-excel). Recharts.
- [x] **Classes de sécurité CNESST** (Hypothèses) remplacent l'augmentation globale : code/description/taux + **max assurable plafonné à 103 000 $ (2026)**. CSST employé = taux_classe × min(salaire_brut, 103 000).
- [x] **Formulaire Employé** : « Titre / Poste », « Superviseur (auto-rempli depuis le département) » en lecture seule, « Classe de sécurité CSST ». Le superviseur est dérivé de la table Départements à la sélection du département et **persisté** (champ `supervisor` ajouté à EmployeeBase).
- [x] **P0 corrigé** : suppression du blocage de sauvegarde dans la Fiche Salaires & Budget quand « Prime de garde » cochée + « Type de prime » = « Aucune Prime ».
- [x] Correctif tester : rétablissement de `def build_budget_excel` (endpoint /reports/excel qui renvoyait 500).
- [x] Tests : backend 12/12 (iteration_13), frontend 100 % (4 onglets, autofill superviseur, P0, exports).

## Modèles de rapport réutilisables (2026-06-11)
- [x] **Constructeur personnalisé — modèles enregistrés** : l'utilisateur configure colonnes + filtres (type, regroupement, département) et **enregistre un modèle** ; les modèles s'affichent en puces cliquables (« un clic » = applique + génère le rapport), avec suppression. Collection `report_templates`. Endpoints `GET/POST /api/report-templates`, `DELETE /api/report-templates/{id}`. Journalisé.
- [x] Vérifié : backend create/list/delete (curl 200), UI carte « Modèles enregistrés » rendue.

## Colonne Classe de sécurité (Employés) + UI responsive (2026-06-11)
- [x] **Employés** : nouvelle colonne « Classe de sécurité » affichant **code + description** (map depuis les hypothèses) ; « — » si non assignée. Table `min-w-[860px]` + scroll horizontal pour lisibilité.
- [x] **UI responsive (desktop / tablette / smartphone)** : sidebar transformée en **drawer coulissant** sur < lg (hamburger dans le header + overlay + bouton fermer, fermeture au clic sur un item) ; visible en fixe sur ≥ lg. Paddings adaptatifs (header `px-4 sm:px-6 lg:px-8`, main `p-4 sm:p-6 lg:p-8`), badge « Budget actif » masqué < sm, titre tronqué. Vérifié à 390px (drawer + overlay OK) et 1920px.

## Vue « cartes » mobile pour les grands tableaux (2026-06-11)
- [x] **Employés** et **Salaires & Budget** : sur < md (smartphone), les tableaux basculent en **vue cartes** (une carte par employé : nom, titre, #, dépt, badge type, montants clés, classe de sécurité, actions modifier/supprimer, ligne cliquable pour le détail dans Budget). Le tableau reste affiché sur ≥ md (`hidden md:block` + `md:hidden` cartes). Vérifié à 390px (cartes visibles et lisibles).

## Départements sans CSST + tri du tableau Employés (2026-06-11)
- [x] **Départements** : colonne « CSST » retirée de la table **et** champ « Taux CSST (%) » retiré du formulaire (CSST géré désormais via les classes CNESST dans Hypothèses). La valeur `csst` existante en base est préservée silencieusement lors des mises à jour.
- [x] **Employés — tri par colonne** : clic sur un en-tête trie asc/desc (indicateurs ChevronUp/Down/UpDown) sur #, Titre, Nom, Dépt, Type, Classe de sécurité, Salaire, Âge, Ancienneté. Tri côté client appliqué au tableau desktop et aux cartes mobiles. Vérifié (tri Salaire décroissant).

## Préférence de tri persistée par utilisateur (2026-06-11)
- [x] **Préférences par compte utilisateur** (backend) : nouveaux endpoints `GET/PUT /api/me/preferences` stockant un objet `preferences` sur le document utilisateur (fusion partielle). Propre à chaque compte, quel que soit l'appareil.
- [x] **Employés** : le tri choisi (colonne + sens) est sauvegardé dans `preferences.employees_sort` et **rechargé automatiquement** à l'ouverture de la page. Vérifié end-to-end (curl PUT/GET, puis rechargement UI qui restaure salaire décroissant).
- [x] **Extension des préférences par utilisateur** : `default_year` (YearContext — l'année sélectionnée est mémorisée par compte et restaurée à la connexion), `budget_scenario` (scénario par défaut de Salaires & Budget) et `budget_sort` (tri de la table Salaires & Budget). Vérifié end-to-end (curl + rechargement UI : Revue Budgétaire 1 + tri Coût total décroissant restaurés).

## Page Mon profil / Préférences + thème + sous-menu utilisateur (2026-06-11)
- [x] **Page « Mon profil »** : apparence (thème Clair/Sombre), résumé des réglages (année par défaut, scénario, tris Employés & Budget, thème) et bouton **Réinitialiser**. Endpoints `GET/PUT /api/me/preferences` (dict fusionné par compte). Validé testing_agent iteration_14 (backend 7/7, frontend 100 %, isolation par utilisateur, persistance du thème après reload).
- [x] **Thème sombre** : overrides CSS `.dark` (cartes, body, utilitaires slate) + variables shadcn ; appliqué à toute l'app via `applyTheme` au montage du Layout. Corrigé le texte « Budget total » et le toggle de scénario invisibles en sombre.
- [x] **Correctif** : `PUT /api/me/preferences` renvoie 400 (au lieu de 500) sur corps JSON invalide.
- [x] **Sidebar — sous-menu utilisateur** : « Mon profil » et « Utilisateurs » (admin) déplacés dans un **sous-menu déroulant sous le bloc utilisateur** (avatar/nom/courriel, chevron), avec la Déconnexion. Retirés de la navigation principale.

## Restriction admin + avatar/badge de rôle (2026-06-11)
- [x] **Sous-menu utilisateur** : « Mon profil » et « Utilisateurs » (admin) regroupés dans un menu déroulant sous le bloc utilisateur (avatar + nom + courriel + chevron), avec Déconnexion. **Badge de rôle** (Admin/Utilisateur) affiché.
- [x] **Avatar personnalisable** : couleur d'avatar (initiale) choisie dans Mon profil, stockée dans `preferences.avatar_color` et appliquée à la sidebar + page profil.
- [x] **Restriction d'écriture aux administrateurs** : middleware backend `admin_write_guard` — tout appel mutant (POST/PUT/DELETE/PATCH) sur `/api` renvoie **403** pour les non-admins, sauf `/api/auth/login`, `/api/auth/logout`, `/api/me/preferences`. Les GET restent accessibles à tous.
- [x] **Frontend lecture seule** pour les non-admins : bannière « Lecture seule », masquage des boutons Ajouter/Importer/Modifier/Supprimer/Enregistrer et des toggles sur Employés, Départements, Hypothèses, Salaires & Budget (canEdit = isAdmin), et modèles de rapport (Rapports).
- [x] Validé testing_agent iteration_15 : backend 21/21 (403 non-admin, 200 admin, prefs autorisées), frontend 25/25. DB intacte (122 employés). Comptes remis aux valeurs par défaut.

## Rôle « éditeur » + Hypothèses admin-only + suppression bannières (2026-06-11)
- [x] **Rôle intermédiaire « éditeur »** : peut modifier employés, départements, lignes de budget (si NON verrouillé), augmentation, modèles de rapport. NE PEUT PAS : hypothèses, verrouiller/déverrouiller, gérer les utilisateurs, gérer les années. Rôle sélectionnable dans la page Utilisateurs (user/editor/admin) ; badge de rôle Admin/Éditeur/Utilisateur (sidebar + profil).
- [x] **Backend** : middleware `write_guard` — chemins admin-only = /api/users*, /api/hypotheses, /api/budget/lock, /api/years* ; autres écritures = admin OU editor ; ouverts = login/logout/me-preferences. `UserCreate/UserUpdate` acceptent `editor`.
- [x] **Hypothèses** : tous les champs désactivés pour les non-admins (`<fieldset disabled>`), bouton Enregistrer masqué.
- [x] **Bannières « Lecture seule » supprimées** partout (Employés, Départements, Hypothèses, Salaires & Budget). L'état verrou reste indiqué par le badge 🔒.
- [x] Validé testing_agent iteration_16 : backend 38/38, frontend 36/36 sur les 3 rôles ; DB intacte ; préférences remises par défaut.

## Journal admin-only + détail employé cliquable (2026-06-12)
- [x] **Menu Journal masqué** pour les non-admins (sidebar) + endpoint `GET /api/journal` restreint aux admins (`require_admin`, 403 pour éditeur/utilisateur).
- [x] **Détail employé** : clic sur une ligne (table desktop) ou une carte (mobile) ouvre `EmployeeDetailDialog` en lecture seule (Informations, Classe de sécurité CNESST, Rémunération, Primes & allocations, Dates & ancienneté) avec bouton « Modifier » (si droits) — même UX que Salaires & Budget. Boutons Modifier/Supprimer avec stopPropagation.
- [x] Vérifié : curl (journal 403 éditeur / 200 admin), captures (détail employé s'ouvre, Journal absent pour éditeur).

## Bouton « Voir le budget » depuis le détail employé (2026-06-12)
- [x] Le dialogue de détail employé propose un bouton **« Voir le budget »** qui charge la fiche budget calculée de l'employé (via `getBudget` pour l'année courante + scénario préféré de l'utilisateur, défaut « Budget CA ») et l'ouvre dans `BudgetDetailDialog` (lecture seule + export PDF). Vérifié (fiche s'ouvre avec masse salariale totale).

## Sélecteur de scénario dans la fiche budget (2026-06-12)
- [x] La fiche budget ouverte depuis un employé (« Voir le budget ») propose un **sélecteur de scénario** (Budget CA / Revue 1 / Revue 2) qui recharge instantanément la fiche calculée du même employé pour comparer le coût sans quitter Employés. Vérifié (bascule Revue 1, recalcul + en-tête mis à jour).

## Écart vs Budget CA dans la fiche budget (2026-06-12)
- [x] Sous le sélecteur de scénario de la fiche budget (ouverte depuis un employé), une ligne **« Écart vs Budget CA »** affiche le montant et le % de différence du coût total de l'employé par rapport au scénario Budget CA (vert si baisse, rouge si hausse). La base CA est chargée une fois et réutilisée. Vérifié.

## Vue « Par département » dans Salaires & Budget (2026-06-12)
- [x] Bascule **Par employé / Par département** dans la table Salaires & calculs. La vue département agrège par département (nb d'employés + nouveau salaire, vacances, primes, salaire brut total, avantages, coût total), triée par numéro de département croissant, avec ligne de totaux — en table (desktop) et cartes (mobile). Vérifié (17 départements, Budget CA 2026).

## Drill-down par département (2026-06-12)
- [x] Dans la vue « Par département », chaque ligne est **dépliable** (chevron) pour afficher la liste des employés qui la composent (sous-lignes indentées avec leurs montants) ; cliquer sur un employé ouvre sa fiche budget détaillée. Fonctionne en table (desktop) et cartes (mobile). Vérifié (dépt 020 → 6 employés).

## Override par scénario : département / type d'emploi / taux d'emploi (2026-06-12)
- [x] **Fiche Salaires & Budget** : nouvelle section « Emploi & imputation » permettant, **par version de budget** (CA/Revue 1/Revue 2), de changer le **département** (n'affecte que l'imputation — GL/regroupement/superviseur ; déductions inchangées, CSST toujours selon la classe de sécurité) et le **type d'emploi** (liste complète CCQ / Rég. temps plein / Rég. temps partiel / Stagiaire). Si « Régulier temps partiel », un champ **Taux d'emploi (%)** apparaît et proratise salaire + primes + allocations.
- [x] Les overrides sont **isolés par scénario** (ne touchent pas les autres versions). Au **verrouillage** d'une version, le département par défaut de la fiche employé prend celui de la version verrouillée.
- [x] Backend : `compute_budget` dérive emp_type/ccq/dept/emp_rate depuis l'override ; `set_lock` propage le département de la version verrouillée vers `employee.department`. Validé testing_agent iteration_17 : backend 8/8, frontend OK, isolation + proratisation + invariance CSST + propagation au verrouillage confirmées. (Note : la base contient 123 employés.)

## Historique des départements par version dans le détail employé (2026-06-12)
- [x] Le détail employé affiche une section **« Département par version »** (Budget CA / Revue 1 / Revue 2) pour l'année courante, lue depuis les overrides `years[year][scenario].department` (défaut = département de la fiche). Une version dont le département diffère de la fiche est mise en évidence (orange). Vérifié.

## Comparatif complet par version dans le détail employé (2026-06-12)
- [x] La section « Par version » du détail employé affiche pour chaque version (CA / Revue 1 / Revue 2) le **coût total**, le **département** (orange si différent de la fiche) et le **type d'emploi** (avec le % si temps partiel). Les données sont chargées à l'ouverture du détail via `getBudget` pour les 3 scénarios. Vérifié.

## Montants avec deux décimales (2026-06-12)
- [x] Tous les montants monétaires s'affichent désormais avec **deux décimales** (via `fmtCAD`, `minimumFractionDigits: 2`) partout dans l'app (tableaux, fiches, dashboard, détails). Vérifié.

## Mise à jour majeure — 8 points (2026-06-14)
- [x] **P1 — Cycle budgétaire verrouillé** : impossible de créer une nouvelle année tant que les 3 scénarios (Budget CA, Revue 1, Revue 2) de l'année source ne sont pas tous verrouillés. Backend `_all_scenarios_locked` + garde dans `POST /api/years` (400 + message FR clair, surfacé en toast dans Layout).
- [x] **P2 — Date de changement de salaire + proratisation** : champ `salary_change_date` par employé ET par scénario (fiche `data-testid=fiche-salary-change-date`). Avant la date = salaire de base actuel (taux plein non proratisé), après = nouveau salaire ; mélange pondéré par jours civils (`_salary_change_weight`). Ligne expose `new_salary` (mélangé) et `new_salary_rate` (taux plein post-changement).
- [x] **P3 — Saisie manuelle** (scénarios Budget CA & Revue 1 uniquement) : bascule `fiche-manual-toggle` rend les lignes de calcul éditables (`manual-new_salary`, `manual-vacation`, `manual-rrq`, `manual-csst`…). Chaque composant peut être écrasé ; le **coût total reste la somme** (non éditable). Stocké dans `override.manual`.
- [x] **P4 — Auto-inactivation sans budget** : bouton `inactivate-noentry-btn` (admin/éditeur) → dialogue `noentry-dialog` listant les employés actifs sans budget saisi pour l'année, confirmation `noentry-confirm`. Endpoints `GET /api/budget/no-entry` + `POST /api/budget/inactivate-no-entry`.
  - **Correctif (2026-06-14)** : « budget saisi » = **override enregistré pour le scénario sélectionné** (le report auto du salaire de base ne compte pas). Détection **par (année, scénario)** via `_has_scenario_entry`. **Déclenchement automatique** du dialogue de confirmation après chaque enregistrement de fiche (`onSaved(scn)` → `afterFicheSave` → check no-entry). Bouton manuel conservé. Vérifié testing_agent iteration_19 (ca≈1-2, revue1=122, aucune inactivation réelle).
- [x] **P5 — Unification du détail employé** : la fiche budget ouverte depuis « Salaires & Budget » (clic ligne) utilise le même `BudgetDetailDialog` que « Employé › Voir le budget », avec sélecteur de scénario + ligne « Écart vs Budget CA » (masquée si scénario = CA).
- [x] **P6 — Primes Tedy & Telus** (non-CCQ uniquement, cachées pour CCQ) : montants fixes $ (`fiche-tedy`, `fiche-telus`) inclus **uniquement** dans les bases RRQ/FSS/RQAP/CSST (exclus de l'AE, des vacances et des avantages CCQ). Ajoutés au coût total et à `primes_total`.
- [x] **P7 — Compte « GL Boni » par département** : champ `dept-gl_boni` + colonne dans le tableau Départements (`Department.gl_boni`).
- [x] **P8 — Ligne GL Boni au P&L** : le boni + ses charges sociales marginales (RRQ+AE+RQAP+FSS+CSST, respectant les plafonds) sont extraits vers le compte GL Boni du département et **déduits** du GL de salaire principal. Totaux P&L inchangés. Ligne expose `boni_gl`.
- [x] Tests : testing_agent iteration_18 — backend 13/13, frontend 8/8. Environnement laissé intact (overrides remis à {}, gl_boni restauré, 123 employés).

## Rapport comparatif des scénarios (2026-06-14)
- [x] **Onglet « Comparatif scénarios »** (Rapports) : tableau par département comparant Budget CA · Revue 1 · Revue 2 avec **écarts $ et %** (R1 vs CA, R2 vs CA), lignes colorées (hausse rouge / baisse verte), ligne TOTAL. Filtrable par année + département.
- [x] **Export Excel** en un clic (`GET /api/reports/scenario-compare-excel`) avec formats monétaires et pourcentages. Endpoint données `GET /api/reports/scenario-compare`.
- [x] Backend `_scenario_compare_data` (réutilise `compute_budget` par scénario, agrège `by_department`). Vérifié testing_agent iteration_20 (frontend 100%, 17 lignes + TOTAL, export OK, filtres OK).

## Édition rapide par double-clic (2026-06-14)
- [x] Composant réutilisable `EditableCell` (double-clic → input, Entrée/blur = enregistrer, Échap = annuler, `stopPropagation` pour ne pas ouvrir le détail).
- [x] **Salaires & Budget** (vue par employé) : colonnes ajoutées **Augm. %** et **Vac. %** ; cellules éditables **Nouveau salaire ($)**, **Augm. (%)**, **Vac. (%)**. Sauvegarde via `saveBudgetOverride` en **fusionnant l'override existant** (`lineToOverride`) pour ne rien écraser. Respecte scénario actif + verrou + rôles (`canEdit = admin || (editor && !locked)`).
- [x] **Employés** : colonne **Vac. %** ajoutée ; cellules éditables **Salaire ($)** et **Vac. (%)** via `updateEmployee` (corps complet `empToBody`). Rôles admin/éditeur (verrou géré côté backend 403). Augmentation N/A ici (donnée de scénario).
- [x] Vérifié testing_agent iteration_21 (admin 100% : édition + recalcul du coût total + non-ouverture du détail + préservation des overrides ; valeurs restaurées, 123 employés intacts). Gating rôles/verrou validé par inspection de code.

## Module Comptabilité — Phase 1 (2026-06-14)
Nouveau module (menu latéral « Comptabilité ») générant Bilan + États des résultats à partir d'une balance de vérification (BV .xlsx). Réutilise auth/rôles existants.
- [x] **Moteur de calcul fiable** (`/app/backend/accounting.py`, `ReportEngine`) : reproduit le graphe de formules du modèle Excel (VLOOKUP par n° de compte + SUM de plages + arithmétique de section + réfs inter-feuilles). **Validé à 100 % des lignes critiques** contre les valeurs Excel en cache (Bilan 473/473 dont équilibre Actif=Passif ; P&L col mois + col à date 493/493). Robuste à l'ordre des comptes (indexé par n° de compte).
- [x] **Navigation** : Comptabilité ▸ Dashboard · Balance de vérification · Bilan · États des résultats · Flux de trésorerie *(à venir)* · Rapports d'audit *(à venir)*.
- [x] **Import du modèle** (admin) : `POST /api/acct/template` extrait le mapping (489 comptes).
- [x] **Upload BV mensuel** : `POST /api/acct/bv?year=&month=` (permis aux utilisateurs standard via WRITE_ALLOW_ALL), parsing (A=n°, B=nom, C=mouvement, I=cumulatif), **validation d'équilibre** (écart bilan ~0), **détection des nouveaux comptes** (dialogue), remplacement complet tant que non verrouillé.
- [x] **Verrouillage mensuel** (admin, `require_admin`, tracé) : bloque tout nouvel upload (403) ; déverrouillage admin.
- [x] **Rapports** : Bilan (cumulatif fin de mois), P&L (mouvement du mois + cumulatif à date), bandeau « Données provisoires » si non verrouillé, négatifs en rouge/parenthèses.
- [x] **Export Excel formaté** (`/api/acct/report/excel`) : en-têtes gras, totaux surlignés, format monétaire, négatifs entre parenthèses.
- [x] **Storage** : collections Mongo `acct_template`, `acct_periods`, `acct_bv`.
- [x] Vérifié testing_agent iteration_22 : backend 9/9, frontend 100 %. Période 2026-06 laissée déverrouillée.

### Améliorations Comptabilité (2026-06-14)
- [x] **Affectation bloquante & mémorisée des nouveaux comptes** : à l'upload, tout compte absent du modèle doit être affecté à un compte existant (regroupement) avant finalisation ; l'affectation est mémorisée (`acct_account_map`) et appliquée aux uploads suivants. Fusion des montants dans le compte-cible (totaux corrects automatiquement). Endpoints `GET /api/acct/accounts`, `POST /api/acct/account-map`. Vérifié via curl (détection → affectation → mémorisation).
- [x] **Bilan sans comptes de résultat** : le rapport Bilan s'arrête à la ligne « Diff » (troncature `stop_after`), excluant les comptes P&L présents plus bas dans la feuille.
- [x] **Masquer les comptes à solde zéro** : bascule dans les rapports (`acct-hidezero-toggle`) qui filtre les lignes de données à solde nul.
- [x] **Colonnes budgets + écarts au P&L** : Réel mois, Budget Rév-2/Écart, Budget Rév-1/Écart, Budget CA/Écart, Réel à date (VLOOKUP idx 3-13, champs BV C-M). Négatifs en rouge/parenthèses.
- [x] Vérifié testing_agent iteration_23 : frontend 100 %.
- [x] **Graphique « Réel vs Budget » (Dashboard)** : barres groupées (Revenus, Dépenses, Bénéfice net) × (Réel, Budget CA, Budget Rév-1) du mois, via `GET /api/acct/summary`. Vérifié testing_agent iteration_24 (backend + frontend 100 %).
- [x] **P&L tronqué** : suppression de l'annexe du bas à partir de « POUR TABLEAU Comité gestion » (r567+) via `stop_at`. Écran + export Excel concernés. Vérifié via curl (s'arrête à r563, Bénéfice net conservé).

### Comptabilité — Flux de trésorerie + nettoyage P&L (2026-06-14)
- [x] **P&L — retrait des lignes de contrôle internes** : suppression des lignes « Bénéfice Net (Perte Nette) - Selon BV détaillée » (r558) et « Contrôle (doit être égal à zéro) » (r559) via nouveau param `exclude` de `build_report` (exclusion ciblée par libellé, sans interrompre le rapport). « BÉNÉFICE NET (PERTE NETTE) » et « Q-P DES RÉSULTATS » conservés. Écran + export Excel. Vérifié (487 lignes vs 489).
- [x] **Flux de trésorerie (méthode indirecte)** : nouveau module `GET /api/acct/cashflow` + `/api/acct/cashflow/excel`. Compare deux périodes chargées (Ouverture → Clôture). Variation = solde de clôture (col. `i`) − solde d'ouverture. 3 sections : Exploitation (Bénéfice net + Amortissement + variation du fonds de roulement), Investissement, Financement ; Variation nette + Encaisse ouverture/clôture. Bénéfice net = Actif−Passif−Avoir(clôture) − idem(ouverture). Classification par section du Bilan (`_bilan_groups`, `_cf_category`), signe par préfixe de compte (1=actif, 2/3=passif/avoir). **Réconciliation garantie** (encaisse clôture = ouverture + variation nette, écart 0,00). Front : `CashflowView` (2 sélecteurs de période, badge « Réconcilié », export Excel). Note : pour un flux « depuis le début de l'exercice », choisir comme ouverture la BV de fin d'exercice précédent. Vérifié testing_agent iteration_25 (frontend 100 %, écart=0,00).
- [ ] **Reporté (phases suivantes)** : export PDF (en-tête pro à définir) ; contenu Rapports d'audit (modèle à venir) ; ligne d'annexe quote-part partenariat (opérateur `%`).

### Comptabilité — UI & graphique cascade (2026-06-14)
- [x] **Badge « Budget actif » masqué** dans l'en-tête pour toutes les pages Comptabilité (`active.startsWith("acct_")` dans Layout.js). Conservé sur la masse salariale.
- [x] **Graphique en cascade (waterfall)** sur la page Flux de trésorerie : Ouverture → Exploitation → Investissement → Financement → Clôture, barres flottantes via `dataKey="range"` ([bas, haut]) + `Cell` (vert=positif, rouge=négatif, gris=ouverture, bleu=clôture). Tooltip affiche le montant réel de chaque étape.
- [x] **Sélecteur mois/année au Tableau de bord Comptabilité** : `PeriodPicker` (« Période affichée ») pilote la carte Statut (verrou/balance/nouveaux comptes) et le graphique Réel vs Budget ; re-fetch `GET /api/acct/summary` par période. KPI globaux (modèle, nb périodes, dernier mois) inchangés. Vérifié visuellement (bascule Juin↔Mai met à jour Statut + graphique).

### Comptabilité — P&L complet (Excel fidèle) + tendance (2026-06-14)
- [x] **P&L : colonnes conformes au modèle Excel** — 16 colonnes en 2 blocs avec en-têtes groupées « Mois » et « Cumulatif (exercice à date) ». Mois : Réel · Bud Rév-2/Écart · Bud Rév-1/Écart · Bud CA/Écart · **Réel an. préc.** (col O, idx BV 7). Cumulatif : Réel à date · **Bud Rév-2/Écart cum.** (R/S) · **Bud Rév-1/Écart cum.** (U/V) · **Bud CA/Écart cum.** (X/Y) · **Cumul. an. préc.** (col AA, idx BV 13). Clés rétro-compatibles (reel, bud_ca, bud_rev1, cumulatif conservées pour `acct_summary`). Séparateur visuel entre les 2 blocs (front + en-têtes groupées). Export Excel = 18 colonnes libellées. `col_groups` renvoyé par `_acct_report`.
- [x] **Graphique de tendance « Évolution du bénéfice net »** (Tableau de bord Comptabilité) : 2 courbes (mensuel + cumulatif) sur tous les mois chargés, via nouvel endpoint `GET /api/acct/trend` (bénéfice net par période). Affiché si ≥2 mois.
- [x] Vérifié testing_agent iteration_26 (frontend 100 %) : en-têtes groupées, colonnes an. préc. non nulles (compte 4004010 : Réel an. préc. 111 527,96 · Cumul. an. préc. 363 507,30), exports Excel OK, tendance + sélecteur période + cascade + badge masqué confirmés.
- [x] **Masquage des colonnes P&L par regroupement** (style Excel) : chips repliables +/− (`acct-colgroup-{id}`) pour masquer/afficher chaque groupe de colonnes — « Budget Rév-2 », « Budget Rév-1 », « Budget CA », « Année précédente » (masque les variantes mois + cumulatif). Réel et Réel à date toujours visibles. En-têtes groupées Mois/Cumulatif et séparateur recalculés dynamiquement. Export Excel reste complet (toutes colonnes). Uniquement pour le P&L (`col_toggle_groups`). Remplace l'ancien sélecteur Mois/Cumulatif (retiré). Vérifié visuellement.

### Refonte design pro + ajustements dashboard/P&L (2026-06-14)
- [x] **Refonte design professionnelle** (inspirée d'un dashboard financier) : polices IBM Plex Sans + Cabinet Grotesk (titres) + JetBrains Mono (données) ; sidebar blanche avec actif teal + barre d'accent ; header glass sticky ; page de connexion split-screen (panneau marque + formulaire) ; cartes KPI premium avec sparklines + flèches de tendance ; `design_guidelines.json` généré par l'agent design.
- [x] **Palette de marque** : prédominant **#063044**, accent **#F8A942** (swap global depuis teal/corail). Graphiques recolorés (Réel=#063044, Budget CA=#F8A942).
- [x] **Dashboard KPI** : cartes Revenus / **COGS** (ligne « TOTAL - COÛT DES MARCHANDISES VENDUES » cumulatif) / **BAIIA** (ligne « BÉNÉFICE AVANT INTÉRÊTS… (BAIIA) » cumulatif) / Bénéfice net — toutes en cumulatif, via `/api/acct/trend` étendu (cogs_cumulatif, baiia_cumulatif).
- [x] **P&L** : suppression de la section GESTION DEMANDE (de « GESTION DEMANDE » à « Marge Brute - GD % ») via nouveau param `exclude_range` de `build_report`.
- [x] **En-têtes figées** (item 8) : header d'app déjà sticky ; en-têtes des tables Bilan/P&L figées (thead sticky dans conteneur `overflow-auto max-h`).
- [x] **Onglets sommaires fusionnés (2026-06-14b)** : « Bilan » et « États des résultats » du sidebar affichent une bascule (`acct-view-toggle`) Détaillé/Sommaire ; entrées sidebar séparées supprimées. Ordre des chips de colonnes P&L : Budget CA, Budget Rév-1, Budget Rév-2, Année précédente. : les feuilles « Bilan Sommaire » et « Resultats sommaires » du fichier fourni ont été fusionnées dans le moteur existant (les feuilles détaillées partageaient déjà la même numérotation de lignes → références inter-feuilles résolues sans ré-import destructif ; `from_template` mis à jour pour les imports futurs). Nouveaux onglets/endpoints : **Bilan sommaire** (`type=bilan_sommaire`, builder 2 panneaux ACTIF|PASSIF via `_bilan_sommaire_data`, rendu 2 colonnes + export Excel `_bilan_sommaire_excel`, validation=0) et **Résultat sommaire** (`type=pnl_sommaire`, `PNL_SOMMAIRE_CFG` sur feuille « Resultats sommaires », colonnes F..X, lignes % sans libellé filtrées, en-têtes groupées + chips). Onglets « Bilan détaillé » et « États des résultats » (détaillés) conservés. Vérifié (ACTIF=PASSIF=19 756 123,01 ; valeurs sommaire = dashboard).

### Comptabilité — Format visuel fidèle au fichier Excel (2026-06-15)
- [x] **Bilan & États des résultats (détaillés + sommaires)** reproduisent désormais le formatage du modèle Excel fourni (« Etats Financiers Juin 2026.xlsx ») : fonds, couleurs de police, gras et bordures extraits de chaque ligne à l'import du modèle.
- [x] Extraction de style dans `accounting.py` (`_cell_style`, `STYLE_LABEL_COL`) capturée par `from_template`, persistée via `to_dict`/`from_dict`, exposée par `build_report` (clé `style` par ligne) et par `_bilan_sommaire_data`.
- [x] Mapping visuel front (`excelRowStyle`/`excelCellColor` dans `Comptabilite.js`) : sous-totaux = fond gris clair + texte **#063044** gras + bordure haut ; grand total Actif/Passif = accent **#F8A942** ; grand total Revenus/Marge = fond navy **#063044** + texte blanc + bordures ; en-têtes de section = gras souligné ; annotations « Réel vs Budget »/« Diff » en rouge **#C00000** ; négatifs en rouge/parenthèses.
- [x] Modèle Excel réimporté (non destructif) pour peupler les styles. Vérifié visuellement (Bilan + P&L, sous-totaux/grands totaux/annotations) + curl (styles présents sur les 4 rapports, Bilan sommaire validation −0,0).

### Ajustements UI Comptabilité — police, gras, palette, M$ (2026-06-15b)
- [x] **Police Calibri** sur toute l'application (`index.css` : body + override des utilitaires `font-sans`/`font-mono`/`font-display`/`font-mono-data`, éléments de formulaire et tables ; fallback Carlito/Segoe UI).
- [x] **Sous-totaux & totaux en gras** dans Bilan/P&L (via `excelRowStyle`, déjà `font-700` sur fonds gris/foncé et lignes total).
- [x] **Titres de catégories/groupes** (Bilan & P&L) en **gras + #063044** (couleur par défaut des lignes `header` dans `excelRowStyle`).
- [x] **Graphiques limités à 4 couleurs** #063044 · #15AF97 · #F8A942 · #808080 (Dashboard masse salariale : constantes NAVY/TEAL/ORANGE/GREY, TYPE_COLORS, SEX_COLORS, séries Salaires actuels/CA/Rév1/Rév2 ; Comptabilité : barres Réel/CA/Rév-1, cascade flux ; Rapports : tableau COLORS).
- [x] **Bilan — bouton « Bilan sommaire (M$) »** : 3e bascule affichant le bilan sommaire avec montants exprimés en **millions** (`moneyM`, `BilanSommaireView millions`). Vérifié visuellement (Total actif = 19,76 M$, balancé).

### Refonte visuelle globale — style accslegroupe.ca (2026-06-15c)
- [x] **Refonte inspirée de www.accslegroupe.ca/emplois** appliquée à toute l'app avec palette stricte #063044 / #15AF97 / #F8A942 / #808080.
- [x] **Typographie** : **Montserrat** (fine/élégante, `.font-display`) pour les grands titres ; **Calibri** conservé pour le corps et tous les tableaux. Ajout des utilitaires de poids `.font-300..900` (Tailwind ne générait pas `font-600/700/800` → ils étaient sans effet ; désormais réels → totaux/sous-titres correctement pondérés).
- [x] **Page de connexion** (split-screen conservé) : panneau héros gauche = image corporate + overlay navy #063044/85, encadré à fine bordure, **overline** « PLATEFORME FINANCIÈRE », grand titre Montserrat fin avec mot **souligné teal** « bien outillé », liste à **lignes verticales teal** ; formulaire droit épuré, overlines de champs, **CTA teal**.
- [x] **Sidebar** : labels de groupe en `.overline` + icônes teal ; item actif = liseré + fond + sous-titre **teal #15AF97**. **En-têtes de page** : overline (Masse salariale / Comptabilité) + titre Montserrat fin navy. Badge « Budget actif » teal.
- [x] **Cartes KPI Comptabilité** : liseré vertical teal, overline, badge d'icône teal, valeur navy. Focus/selection globaux en teal.
- [x] `design_guidelines.json` généré par l'agent design. Vérifié testing_agent iteration_27 : frontend 100 % (login, 13 items de nav, bascule Bilan 3 vues dont M$, chips P&L, dashboards + graphiques), aucune régression. (Warning Recharts sparkline non bloquant — cosmétique.)

### Bilinguisme FR/EN — Phase 1 (2026-06-15d)
- [x] Infrastructure i18n : `context/LanguageContext.js` (provider `useLang` avec `lang`, `setLang`, `t`) + dictionnaire `lib/i18n.js` (clés FR → EN). Langue par défaut **Français**, persistée dans les préférences (`language`) + localStorage. Montée dans `App.js`.
- [x] **Sélecteur de langue dans « Mon profil »** (FR / English US) — carte dédiée, persistance auto.
- [x] Ossature traduite : barre latérale (nav + sous-menus + labels de groupe), en-têtes de pages (PAGES titres/sous-titres), sélecteur d'année + dialogue nouvelle année, menu utilisateur/rôles, page de connexion, page « Mon profil ».
- [x] **Logos** : « Pro » retiré du logo latéral ; connexion → ligne « Pro · Québec » remplacée par **« Terrebonne · Québec »**.
- [x] Format des montants conservé en québécois (10 782 099,30) dans les deux langues (choix utilisateur).
- Vérifié par capture (bascule FR→EN : sidebar/ossature/préférences en anglais).
- [ ] **Phase 2 (à venir)** : traduire les pages métier (Tableau de bord, Employés, Salaires & Budget, Hypothèses, Départements, Rapports, Journal, Utilisateurs) + dialogues. Comptabilité : interface traduisible, mais libellés de lignes Bilan/P&L resteront issus du modèle Excel FR jusqu'à réception d'un **modèle Excel EN** (fourni ultérieurement par l'utilisateur).

- [ ] **Phase 2 (en cours)** :
  - [x] Journal, Utilisateurs, Hypothèses, Départements, Rapports traduits (FR/EN) via dictionnaire `lib/i18n.js`.
  - [ ] Restant : **Tableau de bord (Dashboard)**, **Employés**, **Salaires & Budget**, **Comptabilité** + dialogues (BudgetFiche, BudgetDetail, EmployeeDetail, ImportErrors, EditableCell).
  - Comptabilité : interface à traduire ; libellés de lignes Bilan/P&L resteront issus du modèle Excel FR jusqu'à réception d'un **modèle Excel EN**.

## Implémenté (Comptabilité — Indicateurs & Projections — 2026-07)
- [x] **KPI DSO** : (Comptes clients courants **nets de taxes** hors retenues ÷ Ventes des 12 derniers mois réels) × 365. Solde CC ÷ 1,14975 (TPS 5% + TVQ 9,975%, car le CC inclut les taxes mais pas les ventes). Base glissante 12 mois. Numérateur = (Comptes à recevoir − retenues) / 1,14975 ; dénominateur = ventes 12 mois NON ajustées. Nécessite 12 mois verrouillés. Juin 2026 : 81,0 j.
- [x] **KPI DPO** : (Comptes fournisseurs **nets de taxes** ÷ Achats des 12 derniers mois réels) × 365. Solde CF ÷ 1,14975. **Achats = (COGS 12 mois − main-d'œuvre incluse au COGS 12 mois) + variation d'inventaire 12 mois** — la main-d'œuvre (sous-totaux « TOTAL MAIN D'ŒUVRE » du COGS) est exclue car les salaires ne transitent pas par les fournisseurs. Base glissante 12 mois. Juin 2026 : 35,7 j.
- [x] **DPO — Montant en litige (net de taxes)** : champ éditable persistant par période (symétrique au DSO), soustrait du solde CF net, avec note, report automatique, isolé du champ DSO (mises à jour partielles via `PUT /api/acct/kpi-adjust`).
- [x] **DSO — Taux de taxe configurable** (`/api/acct/settings`, défaut 1,14975) réglable via bouton « Taxe » dans l'en-tête des indicateurs.
- [x] **DSO — Montant en litige (net de taxes)** : champ éditable persistant par période (`/api/acct/kpi-adjust`, collection `acct_kpi_adjust`) directement dans la carte DSO, soustrait du solde CC net utilisé au calcul, avec note optionnelle, montant exclu affiché visiblement, remise à zéro à tout moment. **Report automatique** : le montant se reporte aux mois suivants (indiqué « reporté depuis YYYY-MM ») jusqu'à une remise à 0 explicite (dernier enregistrement ≤ période via tri lexicographique des clés).
- [x] **KPI Fonds de roulement (FDR) & Besoin en fonds de roulement (BFR)** dans une même carte. FDR = (Actif court terme − retenues contractuelles) − Passif court terme + ratio (même exclusion). BFR = Comptes clients courants (hors retenues) + Inventaire − Comptes fournisseurs. Retenues contractuelles = compte « Gestion des retenues - facturation construction » (identifié dans le bilan détaillé), affichées séparément.
- [x] Recalcul auto selon la période (sélecteurs Année/Mois). Bannière « données provisoires » si mois non verrouillé. Message « non calculable » si comptes clients/fournisseurs/totaux introuvables dans le mapping.
- [x] **Drill-down** cliquable sur chaque KPI (dialogue avec détail des composants + formule visible) + boutons « Voir le Bilan / État des résultats » qui naviguent vers le rapport source **synchronisé sur la même période** (event window `acct-navigate` + sessionStorage `acct_focus_period`).
- [x] **Projections 12 mois** : 4 graphiques (Trésorerie, Ventes, Frais hors COGS, COGS) — régression linéaire sur les 12 derniers mois **verrouillés** uniquement ; réel (trait plein) + projeté (pointillé), badge « Projection statistique ». Trésorerie cale les encaissements/décaissements sur le DSO/DPO (décalage en mois). Drill-down « Projection · détail » listant les mois réels de base + liens source par mois.
- Backend : `GET /api/acct/kpis?year&month`, `GET /api/acct/projections` (helpers `_kpi_data`, `_projection_data`, `_pnl_figures`, `_bilan_ct_lines`).
- Tests : backend 4/4 pytest + frontend 100% (iteration_28). Valeurs Juin 2026 : DSO 129,6 j, DPO 18,5 j, FDR 6 488 906,60 (ratio 2.88).

## Implémenté (Comptabilité — UX période — 2026-07)
- [x] Suppression d'une BV non verrouillée (bouton + confirmation ; masqué si verrouillé). `DELETE /api/acct/period` (admin).
- [x] État vide « Aucune période disponible » dans les vues Bilan/P&L/Flux.
- [x] Sélecteurs Année + Mois indépendants (comme la Balance de vérification) dans Tableau de bord, Bilan, P&L, Flux ; masquage du sélecteur d'année global du bandeau sur les pages Comptabilité.
- [x] P&L sommaire : seuls les totaux en gras (aligné sur le P&L détaillé).


## Implémenté (Comptabilité — Phase 3 IA — 2026-07)
- [x] Surcouche IA **lecture seule** sur le module Comptabilité (jamais de modification des données comptables).
- [x] Fournisseur configurable : **Clé universelle Emergent** (défaut, actif), OpenAI, ou Azure OpenAI. Config admin-only (`/api/acct/ai/config`, `/status`, `DELETE /config/key`). Secrets stockés côté serveur, jamais exposés au client.
- [x] **Analyse de variance** (`POST /api/acct/ai/variance`) : commentaire IA des écarts réel vs budget (seuils $/% configurables).
- [x] **Détection d'anomalies** (`POST /api/acct/ai/anomalies`) : z-score sur moyenne 6 mois + résumé IA. Signalements non bloquants.
- [x] **Chat Q&A** (`POST /api/acct/ai/chat`) : assistant factuel basé uniquement sur bilan/P&L/KPI/tendance ; historique en DB.
- [x] **Suggestion de mapping** (`POST /api/acct/ai/suggest-mapping`) : bouton « Suggérer » dans la fenêtre d'affectation des nouveaux comptes.
- [x] Frontend branché dans `Comptabilite.js` : `VarianceCard` + `AiChatPanel` (tableau de bord), bouton `ai-config-btn` (engrenage IA, admin), `AnomaliesCard` (page BV), boutons `acct-suggest-<compte>` (dialogue nouveaux comptes).
- [x] **Dégradation gracieuse** alignée : variance/chat/suggest-mapping renvoient `{available:false, reason}` (au lieu de 503) si IA non configurée OU erreur LLM transitoire → l'UI ne casse jamais.
- [x] Tests : backend 6/6 pytest + frontend 100% (iteration_29). Tous les flux IA validés avec la clé Emergent.

## Refactor (léger & sûr — 2026-07)
- [x] Backend : endpoints IA extraits dans `acct_ai.py` (APIRouter) — helpers partagés injectés via `acct_ai.init(...)` depuis `server.py` (aucun changement de logique). `api.include_router(acct_ai.router)` avant `app.include_router(api)`.
- [x] Frontend : helpers partagés (`MONTHS`, `money`, `moneyM`, `usePeriods`, `PeriodSelect`) dans `pages/comptabilite/shared.js` ; composants IA (`AiConfigDialog`, `VarianceCard`, `AiChatPanel`, `AnomaliesCard`) dans `pages/comptabilite/AiComponents.js`. `Comptabilite.js` réduit de ~1567 → ~1326 lignes.
- [x] Vérifié : backend curl e2e (status/config/variance/suggest-mapping avec vraie IA) + smoke frontend (tous les composants IA rendus sur dashboard & BV). Aucune régression.

## Traduction FR/EN — Phase 2 complétée (2026-07)
- [x] `Employes.js` et `SalairesBudget.js` entièrement bilingues via `useLang()` / `t()` (formulaire employé, tableaux, cartes mobiles, dialogues, toasts, en-têtes, badges).
- [x] ~110 nouvelles clés ajoutées au dictionnaire `lib/i18n.js` (section Employés + Salaires & Budget).
- [x] Valeurs métier (types d'emploi, scénarios, primes) traduites à l'affichage seulement — les valeurs envoyées au backend restent en français.
- [x] Vérifié en anglais (capture) : Employés + Salaires & Budget + formulaire d'ajout d'employé rendus intégralement en anglais. Bascule FR/EN opérationnelle.

## Traduction FR/EN — dialogues partagés (2026-07)
- [x] `BudgetFicheDialog`, `BudgetDetailDialog`, `EmployeeDetailDialog` entièrement bilingues via `useLang()`/`t()` (en-têtes de sections, labels, notes explicatives, ventilation mensuelle, boutons, toasts).
- [x] Valeurs d'enum stockées (sexe, type de prime, scénarios, types d'emploi) traduites à l'affichage (`t(e.sex_at_birth)`, `t(e.prime_type || "Aucune Prime")`).
- [x] Acronymes fiscaux (RRQ, AE, RQAP, FSS, CSST) laissés tels quels (identiques FR/EN).
- [x] Vérifié en anglais (capture EmployeeDetailDialog) : rendu intégral en anglais, compilation propre.
- [x] Couverture i18n désormais complète sur les pages RH/Budget et leurs dialogues.

## Grand livre détaillé — enrichissement IA (2026-07)
- [x] Import mensuel **optionnel** du grand livre détaillé (.xlsx) dans la page Balance de vérification, lié à la même période (mois/année) que la BV. Modèle standard : N° de compte | Date | Description | Débit | Crédit (montant = débit − crédit).
- [x] Endpoints : `POST /acct/ledger` (upload + agrégats par compte), `GET /acct/ledger/status`, `DELETE /acct/ledger` (bloqué si mois verrouillé), `GET /acct/ledger/template`. Collection `acct_ledger`. N'affecte **aucun** calcul existant (Bilan, P&L, KPI, budget vs réel).
- [x] Remplaçable/supprimable tant que le mois n'est pas verrouillé (même logique que la BV). Non bloquant : rapports et variance fonctionnent normalement sans grand livre.
- [x] **Filtrage déterministe (code, sans IA)** avant tout appel modèle : (1) agrégation par compte à l'import ; (2) détection d'aberrations par IQR sur les comptes en écart ; (3) transmission ciblée à l'IA des seules transactions des comptes en écart majeur (top 3 postes, ≤25 txns/poste, aberrantes priorisées) ; (4) résumé par description si >200 transactions pertinentes.
- [x] `_ai_variance_ctx` inchangé côté logique ; l'endpoint variance injecte les transactions ciblées et renvoie `ledger_used`. Anomalies/chat/suggestion non modifiés.
- [x] **Testé** (iteration_30, 100% backend+frontend) : CRUD, verrouillage (403), fichier invalide (400), non-régression Bilan/P&L, nettoyage. Vérifié manuellement : l'IA cite la transaction aberrante ciblée (« GÉANT -145000$ »).
- [x] **Format réel pris en charge** (fichier fourni par l'utilisateur) : détection des colonnes par en-tête, compatible export complet `Type | Période | Date | Numéro | Description | Compte | Description | Débit | Crédit` (écritures en double partie) ET modèle simple. Compte = colonne « Compte », description = tiers/payeur, montant = débit − crédit. Rapport **annuel complet accepté** — seules les transactions du mois/année sélectionné sont conservées (filtrage par date). Template régénéré à ce format.
- [x] Validé sur le fichier réel (janvier 2026 : 5242 écritures, 157 comptes) : `ledger_used: True`, résumé auto pour un poste > 200 txns (« Revenus - Projets contrôles »), détail + aberrations IQR sinon, l'IA cite la transaction ponctuelle exacte (177 491 $). Nettoyage effectué.
- [x] **Aperçu des transactions cliquable** : le badge « Grand livre » ouvre un dialogue (`LedgerPreviewDialog`) listant les transactions du mois (date, compte, description, montant), avec **recherche** par compte/description (`GET /acct/ledger/transactions`, paginé 100/page). Vérifié : janvier 2026 (5242 txns, 53 pages), recherche « bell » → 15 résultats.
- [x] **Colonne « Grand livre »** dans le tableau des Périodes : badge vert ✓ cliquable + nombre de transactions par mois (ou « — » si absent), alimenté par `ledger_count`.
- [x] **Import global « toutes les périodes »** (`POST /acct/ledger/import-all`) : un seul upload du rapport annuel répartit les transactions par mois selon la date. Importe uniquement les mois **non verrouillés** (seuil ≥10 txns pour écarter le bruit) ; renvoie un récap `imported / skipped_locked / skipped_small`. Bouton frontend dédié avec toasts de synthèse. Validé sur le fichier réel : 2026-01 (5242) + 2026-02 (4820) importés. Nettoyage effectué.

## Analyse de variance IA — sélection du scénario budgétaire (2026-07)
- [x] `VarianceCard` : 3 boutons de scénario **Budget CA / Budget Rév-1 / Budget Rév-2** (libellés cohérents avec le reste du module), sélection exclusive.
- [x] Aucun scénario généré par défaut (l'utilisateur choisit un scénario puis clique « Générer », bouton distinct). Sélection mémorisée via `localStorage` (`acct.ai.variance.scenario`).
- [x] **Changer de scénario régénère l'analyse** (nouvel appel IA) si une analyse est déjà affichée.
- [x] Bouton **désactivé** si le scénario n'a pas de données pour la période (pas d'appel/erreur). Nouvel endpoint `GET /acct/ai/variance/scenarios?year&month` → `{ca,rev1,rev2: bool}`.
- [x] Backend : `POST /acct/ai/variance` accepte `scenario` (`ca|rev1|rev2`) ; mappe vers les bons champs P&L (`bud_ca/ecart_ca`, `bud_rev1/ecart_rev1`, `bud_rev2/ecart_rev2` + cumulatifs). Aucune modification de la logique budget vs réel du Bilan/P&L.
- [x] **Vérifié** (curl + Playwright) : scénarios juin 2026 → `{ca:true, rev1:true, rev2:false}` ; CA et Rév-1 produisent des budgets/écarts distincts ; Rév-2 bouton désactivé ; Générer activé après sélection ; bascule CA→Rév-1 régénère et cite les écarts Rév-1 exacts.

## Comparaison multi-scénarios IA (2026-07)
- [x] Bouton **Comparaison** dans `VarianceCard` (à côté des 3 scénarios) : l'IA commente en un seul rapport le réel vs tous les scénarios disponibles (CA/Rév-1/Rév-2) et la **dérive budgétaire** entre révisions.
- [x] Backend : `POST /acct/ai/variance?scenario=compare` — contexte `_ai_variance_compare_ctx` (écarts par poste × scénario actif), réutilise le grand livre ciblé. Désactivé si < 2 scénarios avec données (`reason_empty`).
- [x] Frontend : bouton désactivé si moins de 2 scénarios ; sélection mémorisée (localStorage) ; régénère si analyse déjà affichée.
- [x] **Vérifié** (curl + Playwright) : juin 2026 compare `['ca','rev1']`, Rév-2 exclu ; l'IA cite la dérive -45,4 %→-60,9 % sur MARGE BRUTE - PROJETS.

## Usage de l'agent IA accessible à tous les rôles (2026-07)
- [x] Cause : le middleware `write_guard` (server.py) bloquait les POST pour le rôle « user » (lecture seule) ; les endpoints d'usage IA étant des POST, ils étaient inaccessibles aux utilisateurs.
- [x] Correctif : ajout de `/api/acct/ai/variance`, `/api/acct/ai/anomalies`, `/api/acct/ai/chat`, `/api/acct/ai/suggest-mapping` à `WRITE_ALLOW_ALL`. La **configuration** (`/api/acct/ai/config`, `.../config/key`) reste admin-only (dépendance `_get_admin`).
- [x] Frontend déjà conforme : bouton « Assistant IA » (config) gaté `isAdmin` ; cartes IA (variance, chat, anomalies) visibles à tous.
- [x] **Vérifié** (curl rôles + Playwright) : editor.test & user.test → variance/anomalies/chat POST = 200 ; config GET/PUT = 403 ; en tant que « user » l'UI génère l'analyse et le bouton config est masqué.

## Débogage chat IA — contexte financier incomplet (2026-07)
- [x] Symptôme : le chat répondait « information non disponible » pour créances/encaisse/fournisseurs/flux, alors que les totaux (ventes, actif CT, bénéfice net) fonctionnaient.
- [x] Cause racine (PAS un fallback ni une erreur API) : `_ai_chat_ctx` ne gardait que les lignes `total`/`header` des rapports **sommaires** (lignes `data` détaillées exclues) et n'incluait **pas le flux de trésorerie**. Le modèle répondait donc correctement « absent » car la donnée n'était pas dans le prompt.
- [x] Correctif : contexte enrichi avec bilan détaillé complet (actif/passif toutes lignes), P&L avec budget_ca, et flux de trésorerie (mois précédent → courant, via `_cashflow_data` injecté dans `init`). Prompt système invite au rapprochement des libellés équivalents. Message d'erreur IA reflète la vraie cause (« Erreur de connexion au service IA … »).
- [x] **Vérifié** : réponses confrontées au Bilan réel juin 2026 — Comptes à recevoir 7 656 359,73 ; Encaisse 574 427,81 ; Fournisseurs 874 454,86 ; Flux exploitation -615 997,09 ; Actif CT 9 936 986,74. Toutes exactes.

## Chat IA — affichage des sources (2026-07)
- [x] Le modèle retourne désormais, en fin de réponse, un bloc `###SOURCES###` + JSON des postes/valeurs du contexte réellement utilisés ; le backend le sépare (`_split_answer_sources`) et renvoie `sources: [{poste, valeur}]` (nettoie le texte affiché). Persisté dans `acct_ai_chat` et exposé dans l'historique.
- [x] Frontend (`AiChatPanel`) : chips « Sources » sous chaque réponse IA (libellé + montant formaté), testid `ai-chat-source-{i}-{j}`.
- [x] **Vérifié** (curl + Playwright) : « créances clients et encaisse » → chips « Comptes à recevoir 7 656 359,73 » et « Encaisse 574 427,81 » (concordent avec le Bilan).

## Grand livre — détail de l'écriture au clic (2026-07)
- [x] Chaque ligne de `LedgerPreviewDialog` est cliquable : elle déploie l'écriture complète (toutes les lignes débit/crédit), avec en-tête (N°/Type/Date), ligne cliquée surlignée, totaux débit/crédit et indicateur d'équilibre.
- [x] Backend : parser (`_parse_ledger_xlsx`) capture désormais `numero` et `type` (imports futurs) ; endpoint `GET /acct/ledger/entry?year&month&index` regroupe par **numéro** si présent, sinon par **plage contiguë date+description** (fallback pour les données déjà importées sans numéro). `/transactions` renvoie un `idx` stable.
- [x] **Vérifié** (curl + Playwright) : Fév. 2026 — clic « Ministre des finances » → 2 lignes (1001020 crédit / 2002100 débit) équilibrées 15 474,52 ; badge « groupé par date + description » affiché (numéro absent des données actuelles).

## Variance IA → lien vers l'écriture du grand livre (2026-07)
- [x] Chaque transaction ciblée de l'analyse de variance (mode détail) affiche un lien « Voir » qui ouvre l'écriture complète (dialogue `EntryDialog`) via `/acct/ledger/entry`, ligne source surlignée, totaux + équilibre.
- [x] Backend : `_variance_txns` attache l'`idx` (index original du grand livre) à chaque transaction détaillée.
- [x] **Vérifié** (curl + Playwright) : fév. 2026 — clic « Voir » sur « Consommation matériel projet février 2026 » → écriture à 3 lignes (5005000 débit / 5505000 + 1001200 crédit) équilibrée à 136 722,34.

## Grand livre — filtre « Inhabituelles » (2026-07)
- [x] Toggle « Inhabituelles (N) » dans `LedgerPreviewDialog` : affiche uniquement les transactions atypiques (aberrations IQR **par compte**, déterministe) ; chaque ligne inhabituelle porte un triangle ambre. Param backend `unusual_only` + `unusual_total` dans `/acct/ledger/transactions` (helper `_ledger_unusual_idx`).
- [x] **Vérifié** (Playwright) : fév. 2026 → 708 transactions inhabituelles sur 4820, filtrage OK.

## Refonte visuelle dashboard Comptabilité (2026-07)
- [x] Layout dense 2 colonnes (grille xl:grid-cols-12) inspiré du modèle Cryptobase, **sans changer les KPI ni la palette** : colonne principale (col-span-8/9) = 4 KPI + 3 tuiles statut + Projection 12 mois (4 mini-graphiques) + Réel vs Budget & Évolution côte à côte ; sidebar (col-span-4/3) = Indicateurs (DSO/DPO/FDR-BFR) + Variance IA + Chat IA.
- [x] Densification : paddings/gaps réduits (p-3/gap-3), hauteurs de graphiques réduites (ProjChart 250→150, graphiques principaux 320/300→230), en-têtes de section compacts. Passage d'environ 5-6 écrans verticaux à ~1,3.
- [x] Fiabilité : `acctProjections` déplacé dans l'effet lié à la période (évite la course à l'auth au montage). Blueprint dans `/app/design_guidelines.json`.
- [x] **Vérifié** (Playwright, 1920px) : toutes les sections rendent (KPI, indicateurs, 4 projections, 2 graphiques, IA).

## Ajustements dashboard + mode présentation (2026-07)
- [x] Cartes KPI : valeurs non tronquées (text-3xl→text-2xl + truncate/title, paddings réduits) ; suppression du soulignement « overline » sur les titres (collision classe Tailwind `.overline` → `text-decoration:none` dans index.css).
- [x] Suppression des tuiles « Verrouillé » et « Balancé » du dashboard ; carte « N nouveau(x) compte(s) non affecté(s) » déplacée dans **Balance de vérification**, à droite sur la ligne de l'en-tête « Périodes ».
- [x] Suppression des compteurs d'en-tête du dashboard (« X comptes », « Y périodes »).
- [x] **Mode Présentation / plein écran** : bouton « Présentation » (dashboard) → `requestFullscreen` + masque la barre latérale et l'en-tête (event `acct-presentation` écouté par Layout), bouton flottant « Quitter » (+ sortie via Échap synchronisée sur `fullscreenchange`).
- [x] **Vérifié** (Playwright) : valeurs KPI complètes, titres propres, tuiles retirées, carte nouveaux comptes dans BV, compteurs retirés, présentation masque sidebar/header.

## Commentaires sur les lignes P&L / Bilan + bouton Présentation généralisé (2026-07)
- [x] **Commentaires par ligne** (P&L & Bilan) : fil horodaté avec auteur, **par période** mais affichant aussi les commentaires des autres mois (période courante surlignée). Uniquement sur les lignes de données (compte). Écriture réservée aux **éditeurs/admins** (middleware `write_guard`), lecture pour tous ; modification/suppression par l'auteur ou un admin.
- [x] Backend : collection `acct_line_comments` (clé report+compte) ; endpoints `GET /acct/line-comments`, `GET /acct/line-comments/counts`, `POST`, `PUT /{id}`, `DELETE /{id}`.
- [x] Frontend : icône commentaire + badge de compteur sur chaque ligne de données du `ReportView` ; `LineCommentDialog` (fil + ajout/édition/suppression). Comptes rechargés à l'ouverture du rapport.
- [x] **Bouton Présentation** ajouté aux tables Comptabilité : Bilan (détaillé + sommaire), États des résultats (détaillé + sommaire), Flux de trésorerie — **exclu de Balance de vérification** (composant partagé `PresentationButton`). Ajouté aussi au dashboard Masse salariale.
- [x] **Vérifié** (curl + Playwright) : add/list/counts/edit/delete OK ; user POST=403, GET=200 ; UI P&L : dialogue s'ouvre (compte 4504035, Juin 2026), commentaire affiché avec auteur + badge période, badge compteur sur la ligne, bouton Présentation présent.

## Ajustements KPI + responsive (compléments 2026-07)
- [x] Cartes KPI passées en pleine largeur (ruban) au-dessus de la grille 2 colonnes → valeurs jamais tronquées ; police réduite (text-xl). Breakpoints `lg` pour adaptation écran. Correctif overflow Masse salariale (`min-w-0` sur cellule graphique Comparatif). Axe X des mini-graphiques Projection corrigé (angle -35°, preserveStartEnd).

## Ajustements P&L/Bilan : persistance, couleur, survol (2026-07)
- [x] **Persistance affichage P&L** : la bascule État détaillé / Résultat sommaire est mémorisée (`localStorage acct.pnl.view`) ; hideZero et groupes masqués persistés par type de rapport.
- [x] **Bouton commentaire** en vert de la palette (#0E9488) ; affiché uniquement au survol de la ligne (opacity 0 → group-hover:opacity-100) ou en permanence si la ligne possède déjà un ou plusieurs commentaires.
- [x] **Surlignement de ligne au survol** (fond #F1F5F9, transition douce, dark #1E293B) sur tous les tableaux du module via classe `.acct-hover-rows` (Balance de vérification, Bilan, États des résultats, Flux de trésorerie, P&L budget vs réel). Rapports d'audit = placeholder sans tableau.
- [x] **Vérifié** (Playwright) : opacité bouton 0→1 au survol, couleur rgb(14,148,136), fond ligne rgb(241,245,249) au survol, bascule P&L conservée après reload.

## Finition mise en forme P&L + mémorisation page (2026-07-18)
- [x] **Bas de l'État des résultats** : 2 lignes vides insérées avant le bloc « Q-P DES RÉSULTATS » (2× spacer `<tr>` h-6). Les lignes Q-P s'affichent en texte plus petit (0.72rem), non gras (fontWeight 400), encadrées d'un fin bord vert/teal (#0E9488) englobant tout le bloc. Appliqué dans `ReportView` de `Comptabilite.js`.
- [x] **Mémorisation de la dernière page visitée** : `Layout.js` initialise `active` depuis `localStorage acct:lastPage` (validé contre PAGES) et le persiste à chaque changement de page. Restauration confirmée après rechargement.
- [x] **Vérifié** (Playwright) : bloc Q-P encadré vert + espace 2 lignes visible ; navigation Flux de trésorerie → reload → page restaurée.

## Espace bord Q-P + Export PDF (2026-07-18)
- [x] **Q-P encadrement** : espace de 1px ajouté à gauche du cadre vert des lignes « Q-P DES RÉSULTATS » (`pl-px` sur le conteneur scrollable de `ReportView`) pour symétrie gauche/droite.
- [x] **Export PDF** des rapports comptables : nouveaux boutons « PDF » (à côté de « Excel ») sur Bilan, États des résultats (détaillé + sommaire), Bilan sommaire et Flux de trésorerie.
  - Backend : `_pdf_money`, `_acct_pdf`, `_bilan_sommaire_pdf`, `_cashflow_pdf` (reportlab, paysage A4 pour les tableaux larges, portrait pour le flux). Négatifs entre parenthèses en rouge, totaux/en-têtes gras, lignes « dark » sur fond navy.
  - Endpoints : `GET /api/acct/report/pdf` (type=bilan|pnl|pnl_sommaire|bilan_sommaire), `GET /api/acct/cashflow/pdf`.
  - Frontend : `api.acctReportPdf`, `api.acctCashflowPdf` ; handlers `exportPdf` dans les 3 vues.
- [x] **Vérifié** : les 5 PDF renvoient HTTP 200 / application/pdf (%PDF-1.4), contenu correct (titres, sections, montants, parenthèses négatives), boutons présents en DOM.

## Export PDF/Excel fidèle à l'écran (2026-07-18)
- [x] **Colonnes & filtres respectés** : les exports PDF et Excel du Bilan / États des résultats (détaillé + sommaire) reçoivent désormais `cols` (colonnes visibles selon les bascules de groupes) et `hide_zero` (masquage des comptes à solde zéro). Backend : `_filter_rep_view(rep, cols, hide_zero)`.
- [x] **Formatage visuel reproduit** : ligne d'en-tête de groupe (MOIS / CUMULATIF) fusionnée, colonnes d'écart en italique gris (rouge si négatif), lignes « dark » sur fond navy + texte blanc, lignes « grey »/totaux sur fond gris, en-têtes/totaux en gras, négatifs entre parenthèses en rouge. Appliqué à `_acct_excel` et `_acct_pdf`.
- [x] **Vérifié** : PDF filtré (2 colonnes + hide_zero) = 26 Ko vs 105 Ko complet ; extraction confirme 2 colonnes valeur, en-tête de groupe MOIS/CUMULATIF présent, lignes zéro masquées ; Excel filtré valide. Aucune erreur console front.

## Fidélité export sommaire + bouton Exporter unifié (2026-07-18b)
- [x] **Formatage sommaire fidèle** : nouveau helper backend `_row_view_style(ln, bold_totals)` répliquant `excelRowStyle` du front. Le P&L sommaire utilise `bold_totals=False` (les totaux ne sont gras que si le style Excel le prévoit), fonds « dark » navy/« grey », couleur de police par ligne, bordures haut/bas (t/u), colonnes d'écart en italique gris/rouge. Appliqué à `_acct_excel` et `_acct_pdf`. Titre Excel « RÉSULTAT SOMMAIRE » pour le sommaire.
- [x] **Bouton « Exporter » unifié** : composant `ExportMenu` (DropdownMenu) remplaçant les 2 boutons PDF/Excel séparés sur les 3 vues (États des résultats, Bilan sommaire, Flux de trésorerie). Sous-menu PDF / Excel au clic.
- [x] **Vérifié** : exports sommaire PDF (7,6 Ko) et Excel (8,3 Ko) valides ; dropdown s'ouvre avec items PDF/Excel ; téléchargement déclenché depuis la vue sommaire (`resultats_2026-06.xlsx`).

## P&L détaillé — ratios en % + nettoyage (2026-07-18c)
- [x] **Lignes « Réel vs Budget » supprimées** du P&L détaillé uniquement (type `pnl`, filtre sur label).
- [x] **Lignes de ratio en pourcentage** (Matériels/Sous-traitance/Main d'œuvre/FGF Projets, Marge Brute Projet %, Marge très brute Projets, ratios Services, Marge Brute Service %, Marge Brute Globale %) + **la ligne sous BAIIA** : affichées en % (val×100), police non-gras, italique, couleur verte palette #0E9488. Implémenté côté frontend `ReportView` (scopé à `type === "pnl"`).
- [x] **Vérifié** (Playwright) : 0 ligne « Réel vs Budget », ratios et ligne post-BAIIA en vert italique « x,x % ».
- Note : exports PDF/Excel inchangés pour ces lignes (affichage écran seulement).

## Exports P&L détaillé alignés (2026-07-18d)
- [x] Les exports **PDF et Excel** du P&L détaillé appliquent désormais les mêmes ajustements que l'écran : lignes « Réel vs Budget » retirées ; lignes de ratio + ligne sous BAIIA affichées en pourcentage (Excel format `0.0%`, PDF « x,x % »), police non-grasse, italique, verte (#0E9488). Backend : `_pnl_detail_adjust` + marqueur `_pct` géré dans `_acct_excel`/`_acct_pdf` (appliqué uniquement pour `type == "pnl"`).
- [x] **Vérifié** : xlsx (0 ligne « Réel vs Budget » ; ratios `0.0%`, italique, couleur 0E9488, non gras) ; pdf (aucune ligne « Réel vs Budget », ratios en « x,x % »).

## 4 fonctionnalités : cartes IA, taux QC auto, présentation budget, inactivation par scénario (2026-07-22)
- [x] **#1 Cartes IA déplacées** : « Analyse de variance (IA) » et « Questions sur les données (IA) » passent dans la colonne principale (gauche), sous les graphiques du tableau de bord Comptabilité (`Comptabilite.js`).
- [x] **#2 Taux Revenu Québec auto** : à la création d'une nouvelle année, `_apply_qc_rates` tente une récupération en ligne (`_fetch_qc_rates` via httpx, best-effort sur RQAP ; repli sur report de l'année précédente si échec réseau/parsing) et met à jour toutes les charges **sauf CSST** (taux + max assurable). Drapeau `rates_changed` + `rates_note` → bannière rouge dans Hypothèses ; l'enregistrement efface la bannière et applique les taux (`update_hypotheses` force `rates_changed=False`). NOTE : le scraping live est best-effort (à vérifier par l'utilisateur).
- [x] **#3 Bouton Présentation** ajouté dans l'en-tête de Salaires & Budget (`PresentationButton`).
- [x] **#4 Inactivation par scénario** : « Inactiver sans budget » n'affecte plus que l'année+scénario courant via `inactive_scenarios: ["{year}:{scenario}"]` (plus de `active:false` global). `compute_budget` filtre par scénario ; `save_override` réactive (`$pull`) l'employé pour le scénario lors d'une saisie. Historique conservé dans les autres scénarios/années.
- [x] **Vérifié** : filtrage scénario (ca=122, revue2 avec 1 inactif=121, ca conserve 122, employé reste actif global) ; bannière rouge Hypothèses ; cartes IA à gauche ; bouton Présentation budget (captures).

## Journal avant→après + aperçu taux (2026-07-22b)
- [x] **Journal — valeurs avant/après** : `log_action` accepte un tableau `changes`. `update_hypotheses` (`_diff_hypotheses`) et `update_employee` (`_diff_employee`) calculent le diff (taux, max assurable, exemptions, classes de sécurité, paramètres scalaires ; nom, département, salaire, vacances, actif, etc.). Affichage dans `Journal.js` : ancienne valeur barrée (rouge) → nouvelle (vert).
- [x] **Bannière taux — aperçu ancien→nouveau** : `_apply_qc_rates` stocke `rates_diff` ; la bannière rouge d'Hypothèses liste chaque taux modifié (ancien → nouveau). Effacé à l'enregistrement.
- [x] **Vérifié** : roundtrip Hypothèses (RRQ Taux 6,4%→6,5%, max 74 600$→75 600$, REER 5%→5,5%) enregistré et affiché dans le Journal ; `_diff_employee` testé en isolation.

## Variance multi-scénarios + filtres Journal (2026-07-22c)
- [x] **Analyse de variance (IA) — sélection individuelle** : les chips de scénarios (CA, Rév-1, Rév-2) sont désormais multi-sélectionnables (coche). 1 sélectionné = analyse simple ; ≥2 = comparaison (badge « Comparaison (n) »). Backend `acct_ai_variance` accepte `scenarios=` (liste) et restreint la comparaison aux scénarios choisis ayant des données. Persisté en localStorage.
- [x] **Journal — filtres + export** : filtres par entité et par utilisateur, bouton « Exporter » (CSV avec BOM, séparateur `;`, incluant le détail avant→après). `Journal.js`.
- [x] **Vérifié** : backend compare `ca,rev1` → `compared:['ca','rev1']` (25 lignes) ; rev2 sans données correctement exclu ; UI multi-select + badge ; filtre Journal Hypothèses = 3/300.

## Bouton IA dans États des résultats + seuil affiché (2026-07-22d)
- [x] **Bouton « IA »** ajouté dans la barre d'outils des États des résultats (après « Exporter »), visible uniquement pour le P&L (détaillé + sommaire). Ouvre une popup « Analyse IA — {titre} » contenant la carte **Analyse de variance (IA)** (multi-sélection de scénarios) et **Questions sur les données (IA)** — identiques au Tableau de bord, câblées sur la période courante.
- [x] **Seuil de déclenchement affiché** dans chaque carte de variance : « écart ≥ {montant} $ ou ≥ {pct} % (configurable dans les réglages IA) ». Le backend `acct_ai_variance_scenarios` renvoie désormais `thresholds`.
- [x] **Vérifié** : bouton IA présent ; popup avec les deux cartes ; endpoint thresholds (2 000 $ / 5 %) affiché dans la carte.

## Nettoyage import GL + boutons compacts + responsive (2026-07-30)
- [x] **#1** Bouton « Importer le grand livre (.xlsx) » (mensuel) supprimé de la carte Grand livre détaillé ; « Importer toutes les périodes » conservé.
- [x] **#2** Texte « Colonnes : Type | Période | Date | Numéro | Description | Compte | Débit | Crédit » retiré de la description de la carte Grand livre.
- [x] **#4** Boutons **Présentation, Exporter, IA** passés en icône seule (sans texte) pour réduire leur taille (`PresentationButton`, `ExportMenu`, bouton IA).
- [x] **#3** Adaptation portrait : barre d'outils des rapports en `flex-wrap` (plus de débordement horizontal), boutons compacts. La structure reste responsive (menu latéral en tiroir + hamburger sous `lg`, grilles `grid-cols-1` qui s'empilent). NOTE : rendu vérifié en desktop ; l'outil de capture force une largeur desktop, le vrai portrait mobile n'a pas pu être capturé.

## Correctif portrait P&L (2026-07-30b)
- [x] Le conteneur de table du P&L/Bilan (ReportView) passe de `overflow-auto max-h-[calc(100vh-230px)]` (scroll interne + en-têtes sticky) à `overflow-x-auto` naturel en mobile, et conserve le comportement sticky/scroll desktop via `lg:`. Les en-têtes de groupe/colonnes deviennent non-sticky sous `lg`. Le P&L s'affiche désormais comme les autres tables (BV, Flux) en portrait. Vérifié desktop OK.

## Hub « Rapports » — Phase 1 (2026-07-30c)
Transformation de l'ancien menu « Rapports d'audit » (placeholder) en **hub central « Rapports »** (menu latéral Comptabilité, sous-titre « Génération centralisée »).
- [x] **Barre de types** (`AcctReports`, data-testid `acct-reports-type-<value>`) : Bilan · État des résultats · Flux de trésorerie · **Résultats mensuels (colonnes)** · **Par responsable budgétaire**. Type mémorisé dans `localStorage` (`acct.reports.type`).
- [x] **Résultats mensuels** (`PnlMonthlyView`, `GET /api/acct/report/pnl-monthly?year=`) : P&L réutilisé par mois → 12 colonnes (JAN..DÉC) + colonne **Total**, styles Excel repris, colonnes des mois non verrouillés marquées « * » + bannière provisoire. Lignes d'en-tête sans montants.
- [x] **Par responsable budgétaire** (`ByManagerView`, `GET /api/acct/report/by-manager?manager_id=&year=&month=`) : P&L limité aux comptes mappés à un responsable, mêmes colonnes budget/écart que le P&L. **CRUD responsables** (`acct_budget_managers` : name/email/accounts/active) via `ManagersDialog` — endpoints `GET/POST/PUT/DELETE /api/acct/budget-managers` **admin-only** (403 editor/user).
- [x] Correctif : import `Settings2` (lucide-react) manquant dans `Comptabilite.js` (crash ByManagerView).
- [x] Vérifié testing_agent iteration_31 : backend 3/3 + frontend 100 % (hub 5 types, P&L mensuel 12 mois+Total, CRUD responsables admin-only, filtrage par comptes, régression Bilan/P&L/Flux OK). Collection `acct_budget_managers` laissée vide.
- [ ] **Phase 2 (à venir)** : modèle Excel « État de résultat par responsable » (mise en page finale, à fournir par l'utilisateur) ; **synchro OneDrive/SharePoint via Microsoft Graph** (nécessite enregistrement d'app Azure AD — à confirmer avec l'utilisateur avant de démarrer).

## Hub « Rapports » — Phase 2 (2026-07-30d)
Refonte du hub selon nouvelles demandes + modèle Excel « par responsable » fourni.
- [x] **Onglets réordonnés** : Bilan · État des résultats · **Résultats mensuels** · Flux de trésorerie · Par responsable budgétaire. Renommé « Résultats mensuels (colonnes) » → « Résultats mensuels ».
- [x] **Résultats mensuels** : bascule **État détaillé / Résultat sommaire** (`variant` sur `/acct/report/pnl-monthly`, pnl vs pnl_sommaire) + case **Masquer les comptes à solde zéro**. Mise en page fidèle au P&L (styles Excel, en-têtes navy, totaux surlignés, négatifs rouge, ligne « Réel vs Budget » filtrée en détaillé). 12 colonnes mois + Total.
- [x] **Sidebar Comptabilité nettoyée** : items **Bilan, États de résultats, Flux de trésorerie retirés** de `NAV_ACCT` (accessibles uniquement via le hub Rapports). Restent : Tableau de bord, Balance de vérification, Rapports, Journal.
- [x] **Par responsable budgétaire — modèle Excel exact** (fichiers RH/TI/MKT/FGF fournis) : titre « Suivi Budget frais d'exploitation - <responsable> », colonnes **No GL | Désignation | Réel <mois> <an> (Cumulatif) | Budget REV-1 <an> (<mois> <an>) | Budget REV-1 <an> (Annuel) | Écart Budget Mois vs Annuel | Notes et commentaires**, ligne **TOTAL - <RESPONSABLE>**. Réel cum = P&L `cumulatif` ; Budget à date = `bud_<rev>_cum` ; **Annuel = budget mensuel `bud_<rev>` × 12** ; Écart = Annuel − Réel. Sélecteur budget Rév-1 (défaut) / CA / Rév-2. *(NB : « Annuel » reconstitué depuis le budget mensuel BV arrondi → écart d'arrondi ~4 $ vs l'annuel exact du fichier source, seul l'annuel exact n'étant pas importé.)*
- [x] **Exports PDF + Excel** du rapport par responsable (`/acct/report/by-manager/excel` et `/pdf`) respectant la même mise en page (titre, en-têtes navy, TOTAL surligné, négatifs rouge/parenthèses).
- [x] Vérifié testing_agent iteration_32 : backend 5/5 + frontend 100 % (valeurs RH conformes au fichier, ordre onglets, sidebar, bascule détail/sommaire, masquer zéro, exports, sécurité CRUD admin-only). Collection `acct_budget_managers` laissée vide.
- [ ] **Phase 3 (à venir)** : colonne « Notes et commentaires » éditable par les responsables ; **synchro/envoi OneDrive-SharePoint via Microsoft Graph** (nécessite app Azure AD — à confirmer avec l'utilisateur).

## Rapports par responsable — Notes éditables + seed des responsables (2026-07-30e)
- [x] **Responsables budgétaires pré-remplis** (seed unique, flag `budget_managers_seeded`) selon les fichiers Excel fournis : **RH** (11 cptes), **TI** (19), **MARKETING** (28), **FGF** (27). Chaque groupe mappe ses numéros de compte exacts.
- [x] **Colonne « Notes et commentaires » éditable** dans le rapport par responsable : clic sur une cellule → zone de texte (Ctrl/Cmd+Entrée ou blur = enregistrer, Échap = annuler), placeholder « Ajouter une note… ». Notes **enregistrées par compte + période** (collection `acct_manager_notes`, clé `YYYY-MM-<compte>`) → réapparaissent au rechargement du même mois. Note vide = suppression.
- [x] **Éditables par tous les utilisateurs connectés** (admin/éditeur/utilisateur) : endpoint `PUT /api/acct/report/by-manager/note` ajouté à `WRITE_ALLOW_ALL`. Vérifié : un compte « user » peut enregistrer une note.
- [x] **Notes incluses dans les exports** PDF (colonne alignée à gauche) et Excel (colonne J, retour à la ligne).
- [x] Vérifié : seed (4 responsables), note enregistrée par user + attachée au rapport + exports 200 + suppression, UI d'édition inline avec toast « Note enregistrée » (curl + captures).
- [ ] **Reporté (phase ultérieure, confirmé utilisateur)** : bouton « Envoyer par courriel » (PDF du suivi au responsable) — nécessite un fournisseur d'email (Resend/SendGrid) + clé API.

## Envoi des rapports par courriel aux responsables (2026-07-30f)
- [x] **Au verrouillage d'un mois** (Balance de vérification, admin) : un dialogue « Mois verrouillé — envoyer les rapports ? » propose l'**envoi automatique du PDF « Suivi budgétaire »** à tous les responsables ayant un courriel (`acct-sendreports-dialog`, boutons « Plus tard » / « Envoyer à tous les responsables »). Récap toast (envoyés / échecs / sans courriel).
- [x] **Envoi individuel** : bouton **« Envoyer »** dans « Rapports › Par responsable budgétaire » (`acct-bymanager-email`) → envoie le PDF au responsable sélectionné pour la période/budget affichés.
- [x] **Intégration Resend** (playbook) : `resend>=2.0.0`, envoi non-bloquant (`asyncio.to_thread`), PDF joint (contenu en octets). Endpoints `POST /acct/report/by-manager/email`, `/email-all`, `GET /acct/email/status`. Courriel HTML standard FR (objet « Suivi budgétaire <nom> — <mois> <année> » + PDF joint).
- [x] **Dégradation gracieuse** : si `RESEND_API_KEY` absent → boutons désactivés + note « service non configuré » ; endpoints renvoient 400 clair. Vérifié (curl status `configured:false`, envoi → 400 ; captures dialogue verrouillage + bouton Envoyer).
- [x] Les 4 responsables (RH/TI/MARKETING/FGF) pré-remplis avec le courriel `bbindanda@accslegroupe.ca` (modifiable via « Gérer les responsables »).
- [ ] **À FAIRE pour activer l'envoi réel** : renseigner `RESEND_API_KEY` (clé re_… du compte Resend) et `SENDER_EMAIL` (domaine expéditeur vérifié) dans `backend/.env`, puis `sudo supervisorctl restart backend`. En mode test Resend, seuls les destinataires vérifiés reçoivent les courriels.

## Historique d'envoi + choix du budget à l'envoi (2026-07-30g)
- [x] **Historique / dernier envoi par responsable** : chaque envoi réussi est journalisé (`acct_email_log`) + dernier envoi mémorisé par (responsable, période) (`acct_email_last`, avec date, courriel, expéditeur `sent_by`, budget). Endpoint `GET /acct/email/log?manager_id=&limit=`.
  - Affiché dans l'**en-tête du rapport par responsable** : « Dernier envoi : <date/heure> à <courriel> · par <utilisateur> (budget <rev>) » (`acct-bymanager-lastsent`) ; sinon « Jamais envoyé pour cette période ». Rafraîchi après un envoi individuel.
  - Affiché aussi dans **« Gérer les responsables »** sous chaque responsable (dernier envoi tous mois confondus, `acct-manager-lastsent-<id>`).
- [x] **Choix du budget à l'envoi** dans le **dialogue de verrouillage** : sélecteur Budget Rév-1 (défaut) / CA / Rév-2 (`acct-sendreports-rev`) → transmis à `email-all`. L'envoi individuel utilise déjà le budget affiché.
- [x] Vérifié : endpoints log/last_sent (curl + enregistrement simulé), affichage en-tête + dialogue « Gérer » + sélecteur budget au verrouillage (captures). État nettoyé (simulation supprimée, courriels responsables = `bbindanda@accslegroupe.ca`).

## Correctif « État détaillé » du mensuel = copie exacte du P&L détaillé (2026-07-30h)
- [x] **Bug de correction majeur** : le mensuel alignait les lignes par **index** `i`, or le nombre/ordre de lignes varie selon le mois → décalage (ex. « Marge Brute - Projet - % » affichait 171 584 au lieu de 13 %). Corrigé : alignement par la **clé stable `row`** (`GET /acct/report/pnl-monthly` construit un `row_maps` par mois). Chaque compte reflète désormais exactement les bons montants (vérifié vs P&L simple : Formation-RH juin 200,87 / total 23 760,04, etc.).
- [x] **Lignes de ratio (%)** : détectées côté backend (`is_pct`, mêmes `PNL_PCT_LABELS` + BAIIA+1 que le front). Par mois = ratio du mois ; **Total = ratio annuel** (cumulatif du dernier mois avec données) au lieu d'une somme erronée de ratios.
- [x] **Mise en forme identique au P&L détaillé** (`ReportView`) : nombres via `money()` (négatifs rouges entre parenthèses), ratios en **vert `#0E9488` italique %** (`pctFmt`), en-têtes de section navy, sous-totaux gris, ligne totale navy, regroupement **Q-P DES** (bordures teal + police réduite + 2 lignes d'espacement), couleurs de cellule via `excelCellColor`, police et classes reprises à l'identique.
- [x] Vérifié par curl (alignement + is_pct + totaux) et captures (comparaison visuelle mensuel vs P&L détaillé : identiques).

## Correctif : pas de % dans le sommaire mensuel (2026-07-30i)
- [x] Le formatage en pourcentage ne s'applique qu'à l'**État détaillé** (comme `ReportView` où `isDetailedPnl = type === "pnl"`). Dans le mensuel, `is_pct` est désormais gâté par `variant == "detail"` → la ligne **FRAIS FINANCIERS** (et toute autre) du **Résultat sommaire** s'affiche en montants, plus jamais en %. Vérifié (curl : sommaire `is_pct=[]`, détaillé conserve 13 lignes % ; capture sommaire OK).

## Onglet « Envoi Externe » + rapports présentation + Margination Desjardins (2026-07-30j)
- [x] **Nouvel onglet « Envoi Externe »** dans le hub Rapports (après « Par responsable budgétaire »), même logique que celui-ci mais liste intitulée **« Contact Externe »** (`ExternalSendView`).
- [x] **Contacts externes multiples** (`acct_external_contacts`) : CRUD **admin-only** (`GET/POST/PUT/DELETE /api/acct/external-contacts`), dialogue « Gérer les contacts » (`ExternalContactsDialog`) avec sélection des **types de rapports** depuis un catalogue (`GET /api/acct/external/catalog` : pnl_presentation, bilan_presentation, margination, pnl, pnl_sommaire, bilan).
- [x] **Contact « Banque Desjardins » seedé** (report_types = présentation P&L + présentation Bilan + Margination ; courriel vide à remplir).
- [x] **Rapports PDF « présentation » ACCS** (`presentation_reports.py`, fidèles aux images fournies) : États de Résultats (bandeaux marine BÉNÉFICE BRUT/BAIIA/BÉNÉFICE NET, colonnes Réel/Budget CA/Écart mois + cumulatif + Budget CA annuel, cellules Réel surlignées sarcelle, % sarcelle italique, colonne annuelle vert clair, mention CONFIDENTIEL) et Bilan (Actif/Passif, surlignage sarcelle, bandeau marine TOTAL, équilibré 19 756 123,01). *Sans logo (à ajouter en phase de finalisation).*
- [x] **Rapport de Margination Desjardins — téléversement mensuel** (approche (a) validée) : `POST /api/acct/margination/upload` (multipart, **admin-only**), `GET /acct/margination/status`, stockage base64 (`acct_margination` par période). Le fichier est **joint tel quel** (formules/onglets/mise en page 100 % préservés). Fichier juin 2026 déjà téléversé.
- [x] **Package + envoi** : `GET /acct/external/report` (téléchargement individuel PDF/Excel), `POST /acct/external/email` (joint tous les rapports du contact via Resend). Bouton « Envoyer le package » désactivé tant que Resend non configuré (dégradation gracieuse, 400 clair).
- [x] Vérifié testing_agent iteration_33 : backend 13/13 + frontend 100 % (catalogue, seed Desjardins, package Juin 2026, PDF présentation, Margination upload/status/download, sécurité admin-only, email guard). PDF présentation inspectés visuellement (conformes aux modèles).
- [ ] **Limitation connue** : colonne « Budget CA ANNUEL » du P&L présentation = budget cumulatif annualisé linéairement (`bud_ca_cum / mois × 12`) car le budget annuel exact n'est pas importé → léger écart vs budget saisonnier réel. À corriger en important la source du budget annuel.
- [ ] **À venir** : logo ACCS sur tous les rapports (phase de finalisation) ; activation envoi Resend (clé + expéditeur).

## Envoi Externe — finitions présentation + aperçu + flux (2026-07-30k)
- [x] **Mise en page présentation fidèle aux images** : P&L — colonnes **Budget CA en texte sarcelle**, colonnes Réel surlignées sarcelle (blanc), bandeaux marine complets (BÉNÉFICE BRUT/BAIIA/BÉNÉFICE NET incl. colonne annuelle), % sarcelle italique, en-têtes propres (REEL sombre / BUDGET CA sarcelle), colonne annuelle vert clair, CONFIDENTIEL. Bilan — titres **ACTIF/PASSIF** sarcelle, libellés exacts, lignes ajoutées (Marge de crédit / Crédit Rotatif séparés, Dépôts Inter-co, Comptes à payer 9379), **libellés Capital Actions corrigés** (montants réels 8 932 980 / 4 810 065 / 1), bilan équilibré 19 756 123,01. `_find` robuste (exact puis contains).
- [x] **Flux de trésorerie ajouté au catalogue** des rapports envoyables (`GET /acct/external/report?key=cashflow` : période précédente → sélectionnée, `_cashflow_pdf`).
- [x] **Aperçu au clic** : cliquer une ligne de rapport (ou bouton « Aperçu ») ouvre un dialogue avec le PDF intégré (iframe) + boutons Fermer/Télécharger. Pour la Margination (Excel), message + téléchargement (aperçu en ligne non supporté). data-testid `acct-external-preview-<key>`, `acct-preview-frame`.
- [x] **Bug corrigé** : décorateur `@api.get("/acct/external/catalog")` accidentellement supprimé lors de l'ajout du cashflow → catalogue 404 (cases vides). Rétabli.
- [x] Vérifié : PDF présentation inspectés visuellement (conformes), catalogue 7 types, aperçu iframe OK (curl + captures).
- [ ] **Budget CA ANNUEL exact (à faire)** : toujours annualisé linéairement — nécessite l'import de la **source du budget annuel** (fichier de budget CA annuel non présent dans les données actuelles). En attente d'un fichier/source de la part de l'utilisateur.

## Aperçu web du fichier Margination (2026-07-30l)
- [x] **Aperçu tableau multi-onglets** du fichier Excel de Margination (au lieu d'un simple téléchargement) : endpoint `GET /acct/margination/preview` lit le fichier stocké (openpyxl `data_only` → valeurs de formules mises en cache par Excel), renvoie chaque feuille (nom + lignes, plafonné 300×20). Frontend : onglets par feuille + tableau HTML défilable, nombres formatés/alignés à droite, en-tête marine. Vérifié : 6 onglets (Calcul du Montant Disponible, Ventilation cpt assurés, Engagements financiers, CAP, Sheet1, CAR) avec montants calculés corrects (capture). Bouton « Télécharger l'Excel » conservé.

## Aperçu Margination — en-têtes figés (2026-07-30m)
- [x] Dans l'aperçu tableau du fichier Margination, la **première ligne** (`sticky top-0`) et la **première colonne des comptes** (`sticky left-0`, fond blanc) restent figées lors du défilement vertical/horizontal, pour lire les grandes feuilles (ex. CAR ~260 lignes). Gestion des z-index (coin en z-30). Vérifié par capture (défilement CAR : comptes ancrés à gauche).

## Envoi Externe — Mise en page PDF présentation (2026-06)
- [x] **Bilan de présentation en PORTRAIT sur 1 page** : `build_presentation_bilan_pdf` (`presentation_reports.py`) passé de `landscape(A4)` à `A4` (portrait). Colonnes ACTIF/PASSIF côte à côte (2 colonnes, `92mm` chacune, tables internes `60mm+30mm`), polices réduites (labels 6,8 / titres 9 / bandeau 8) et paddings resserrés pour tenir sur une seule page portrait. Bandeau TOTAL ACTIF / TOTAL PASSIF ET CAPITAUX réajusté (`38/54/54/38 mm`).
- [x] **États de résultats de présentation** : conservé en **paysage** (nombreuses colonnes Mois + Cumulatif + Annuel), déjà sur 1 page — inchangé (choix utilisateur).
- [x] Vérifié via `pdfinfo` + rendu image : Bilan = 1 page, `595 × 841` (portrait), Actif = Passif = 19 756 123,01, aucune donnée coupée ; P&L = 1 page paysage inchangé.
- [x] **Sous-titre Bilan corrigé** : « En millions $ dollars canadiens (CAD) » → « En dollars canadiens (CAD) » (les montants sont en dollars pleins). Vérifié via `pdftotext`.
- [x] **Recherche dans l'aperçu Margination** (`ExternalSendView`, `Comptabilite.js`) : champ de recherche (`acct-marg-search`) au-dessus du tableau multi-onglets qui filtre les lignes de la feuille active sur toutes les colonnes (compte/client/description), conserve la ligne d'en-tête, affiche un compteur de résultats (`acct-marg-search-count`) et un état vide (`acct-marg-search-empty`). En-têtes/1re colonne figés conservés.
- [x] **Recherche Margination mémorisée par onglet** : `margSearch` est un objet `{index_onglet: requête}` — chaque onglet conserve sa propre recherche (pas de réinitialisation au changement d'onglet). Indicateur visuel `·` + anneau orange sur les onglets ayant une recherche active. Réinitialisation uniquement à l'ouverture d'un nouveau fichier / fermeture. Vérifié (console : onglet CAR vide à l'entrée, onglet 0 conserve « credit » au retour).

## Envoi Externe — Historique & dernier envoi (2026-06)
- [x] **Journal des envois externes** : chaque envoi de package (`POST /acct/external/email`) est journalisé dans `acct_external_email_log` (contact, courriel, période, liste des documents, doc_count, manquants, sent_at, sent_by) et le dernier envoi est mémorisé sur le document contact (`last_sent`).
- [x] Endpoint `GET /acct/external/email/log?contact_id=` (trié desc). `GET /acct/external-contacts` renvoie désormais `last_sent`.
- [x] **Frontend** : badge « Dernier envoi : … · période · N doc(s) » (ou « Aucun envoi enregistré ») dans l'en-tête du package ; bouton **Historique (N)** (`acct-external-history-btn`) ouvrant un dialogue (`acct-external-history-dialog`) listant chaque envoi (période, date, destinataire, expéditeur, puces des documents transmis, manquants). Rafraîchi après un envoi réussi.
- [x] Vérifié par capture (enregistrement de test injecté puis nettoyé) : badge dernier envoi vert, compteur Historique (1), dialogue détaillé avec 3 documents.

## Entité comptable indépendante « 9434-3977 QC inc. » — Phase 1 (2026-06)
Nouvelle entité juridique distincte, sous-menu du module Comptabilité, avec **saisie comptable directe** (journal général) — il n'y a pas de système comptable externe en amont. **Données 100 % isolées** de l'entité principale (collections dédiées `qc9434_*`, aucun partage de plan de comptes/écritures).
- [x] **Sous-menu** « 9434-3977 QC inc. » dans la nav Comptabilité (`Layout.js` : `PAGES.acct_qc9434` + `NAV_ACCT`, préfixe `acct_` → en-tête « Comptabilité », contrôles d'année globaux masqués). Page : `pages/QcEntity.js`.
- [x] **Structure par onglets** (boutons reproduisant les onglets du futur modèle Excel) : Écritures · Balance de vérification (générés maintenant) · Bilan · État des résultats (**placeholders « bientôt »** en attente du modèle Excel) · Envoi externe.
- [x] **Onglet Écritures** (journal général multi-lignes) : dialogue de saisie (date, référence, description, N lignes compte/nom/débit/crédit), **indicateur d'équilibre en direct**, bouton Enregistrer **désactivé tant que débits ≠ crédits** ou total nul. CRUD complet ; édition/suppression bloquées si l'exercice est verrouillé. Suggestions de comptes déjà utilisés (datalist) + auto-remplissage du nom. Saisie libre du n°/nom de compte (le plan de comptes structuré viendra avec le modèle Excel).
- [x] **Balance de vérification** générée automatiquement à partir des écritures (`_qc_trial_balance` : agrégation par compte débit/crédit/solde, total, `balanced`), export **Excel** (`_qc_tb_xlsx`). Négatifs en rouge/parenthèses.
- [x] **Gestion par exercice (année)** : sélecteur d'exercice, création (admin), exercice actif mémorisé (`qc9434_settings`). **Cycle verrouillé** : impossible de créer un nouvel exercice tant que le plus récent n'est pas verrouillé (400 + message FR clair). **Verrouillage réservé aux admin** (`require_admin`) ; écritures bloquées (403) sur un exercice verrouillé. Les rôles admin **et** éditeur peuvent saisir des écritures (via `write_guard`), un rôle « user » est bloqué (403 confirmé).
- [x] **Bouton « Envoi externe »** réutilisant le même mécanisme (contacts + email Resend + historique + dernier envoi), avec une **liste de contacts propre** à cette entité (`qc9434_external_contacts`). Catalogue actuel = **Balance de vérification (Excel)** uniquement ; Bilan/Résultats seront branchés à la réception du modèle Excel. Endpoints : `GET/POST/PUT/DELETE /api/qc9434/external-contacts`, `/external/catalog`, `/external/report`, `/external/email`, `/external/email/log`.
- [x] **Endpoints** (`server.py`, bloc dédié) : `/api/qc9434/years` (GET/POST/`years/active`/`years/lock`), `/qc9434/entries` (GET/POST/PUT/DELETE), `/qc9434/trial-balance` (+`/excel`), `/qc9434/external-*`. Helpers `_qc_validate_lines`, `_qc_trial_balance`, `_qc_tb_xlsx`, `_qc_generate_external`.
- [x] **Vérifié** testing_agent iteration_34 : backend 21/21 (pytest), frontend 100 % (création exercice, saisie multi-lignes + validation d'équilibre + désactivation du bouton, CRUD, balance + Excel, contacts externes, gating rôles). Cycle verrouillage validé (création bloquée tant que non verrouillé → verrouillage admin → écritures 403 → exercice suivant OK). **Isolation confirmée** (entité principale intacte, 18 périodes). Collections `qc9434_*` laissées vides.
- [ ] **En attente du modèle Excel** (à finaliser ensuite) : structure exacte des onglets Bilan / État des résultats / autres, plan de comptes structuré (dropdown au lieu de saisie libre), branchement de ces rapports dans l'Envoi externe.



## Backlog restant
- Rapports personnalisés avancés (choix de colonnes, comparaison multi-scénarios).
- Édition rapide (double-clic) des taux ; gestion multi-utilisateurs & rôles.
- Gestion multi-années / duplication du budget actif.
- **Refactor complet (P2)** : découper le reste de `server.py` (endpoints Comptabilité/budget) et les dialogues restants de `Comptabilite.js` si souhaité.
- **Traduction FR/EN** (Phase 2) à compléter sur `Employes.js`, `SalairesBudget.js`.
- Rétention/TTL sur `acct_ai_chat` (historique chat non borné).

## Backlog Phase 2 (obsolète — livré)
- Rapports prédéfinis & personnalisés (export PDF/Excel).
- Filtres Année + Département sur le tableau de bord (backend /budget?department déjà prêt).
- Validation du code département à la création d'un employé.
- Édition rapide (double-clic) des taux ; gestion d'utilisateurs multiples.
- Gestion multi-années / budget actif.


## « 9434-3977 QC inc. » (Commandité) — Phase 2 : modèle Excel intégré (2026-06)
Construite à partir du fichier fourni « Commandité ACCS EF 2026 (non-audités).xlsx ».
- [x] **Renommage** : sous-titre du sous-menu « Entité distincte » → **« Commandité »** (`Layout.js`).
- [x] **Plan comptable structuré** (nouvel onglet) : GL · Description · Type (auto-déduit du préfixe 1/2/3/4/5, modifiable) · **Section de rapport** (10 sections). CRUD complet ; suppression bloquée si le compte est utilisé dans une écriture. **Seed automatique des 23 comptes** du modèle avec sections pré-mappées (`_qc_seed_accounts`, `QC_ACCOUNTS_SEED`, `QC_SECTIONS`). Collection `qc9434_accounts`.
- [x] **Écritures** : le champ Compte devient une **liste déroulante** alimentée par le plan comptable (auto-remplit le nom) ; ajout du champ **Fournisseur/Client** (`tiers`) par ligne (comme l'Excel). Validation d'équilibre inchangée.
- [x] **Écritures modèles (récurrentes)** : enregistrer une écriture comme modèle réutilisable (`qc9434_templates`) et l'appliquer en un clic dans le dialogue de saisie. CRUD `/api/qc9434/templates`.
- [x] **Journal général PDF** : export imprimable paysage de toutes les écritures de l'exercice (date, réf, compte, libellé/description, tiers, débit, crédit, totaux). `/api/qc9434/journal/pdf` (reportlab).
- [x] **Onglet Bilan détaillé** (`_qc_bilan`) : sections ACTIF (court terme / placement / immobilisations) et PASSIF (court terme / long terme) / CAPITAUX, ligne calculée **« Bénéfices non répartis » = bénéfice net** (impact équité), TOTAL DE L'ACTIF / TOTAL PASSIF ET CAPITAUX, ligne **Diff** de contrôle. **3 colonnes** : Exercice (mouvement) / Antérieur (cumul des exercices précédents) / Cumulatif. Équilibré (Diff=0) validé inter-exercices. Export Excel `/api/qc9434/bilan/excel`.
- [x] **Onglet États des résultats** (`_qc_pnl`) : REVENUS → TOTAL, CHARGES → TOTAL, **BAIIA**, Quote-part des bénéfices, Bénéfice avant impôt, IMPÔTS, **Bénéfice net**, puis **Q-P des résultats calculées auto : HILO 65 % / 9379-5599 QC inc. 35 %** du bénéfice net. **2 colonnes** : exercice courant / année précédente (comparatif). Export Excel `/api/qc9434/pnl/excel`.
- [x] **Balances par exercice** (`_qc_report_balances`) : convention débit-positif ; movement (année) / opening (cumul années < N) / cumulative. Bénéfice net = -(somme des comptes de résultat) → garantit l'équilibre du bilan.
- [x] **Envoi externe** : catalogue de l'entité étendu à **Balance de vérification + Bilan + État des résultats** (xlsx). `QC_EXTERNAL_CATALOG`.
- [x] **Vérifié** testing_agent iteration_35 : backend 16/16 nouveaux + 21/21 existants, frontend 100 %. Exactitude comptable validée (bilan balancé, BNR = bénéfice net, comparatif N-1, Q-P 65/35 = 100 % du net), gating de rôles (user bloqué 403), isolation de l'entité principale confirmée. Collections de test vidées (plan comptable conservé/re-seed auto).
- [ ] **Backlog** : index sur `qc9434_entries.year` si la base grossit (perf) ; onglets additionnels du modèle Excel si nécessaires (Auxiliaires, Transactions) ; logo/en-tête sur les exports.


## « Commandité » (9434-3977 QC inc.) — Phase 3 : facturation, auxiliaires, fermeture, import (2026-06)
Basée sur « Facturation - Frais de gestion 2021 Commandité.xlsx » + import du fichier « Commandité ACCS EF 2026 ».
- [x] **Numéros séquentiels d'écriture** par exercice (`AAAA-000N`) via `_qc_post_entry` (`seq`+`num`), affichés au journal, PDF et badge de source (manuel/facture/fourn./encaiss./paiem./fermeture).
- [x] **Factures clients (auxiliaire recevable)** — onglet « Factures clients » : création (client, att, adresse, date, échéance, description, montant HT → **TPS 5 % + TVQ 9,975 %** auto, total), **numéro séquentiel `AAAA-001`**, **PDF de facture** conforme au modèle. Comptabilisation auto (Dr 130118 / Cr 400310 + Cr 215310 + Cr 215301, source=invoice). Statut Ouvert/Encaissée + action **Encaisser** (Dr 100110 / Cr 130118, source=receipt). Endpoints `/qc9434/invoices(+/receive,/pdf)`.
- [x] **Factures fournisseurs (auxiliaire payable)** — onglet « Factures fournisseurs » : **téléversement du fichier** (PDF/image, stockage objet Emergent) + saisie (fournisseur, réf, date, compte de charge, montant HT). Compta auto (Dr charge + Dr 145110 + Dr 145101 / Cr 211010, source=bill). Statut + action **Payer** (Dr 211010 / Cr 100110, source=payment) + visualisation du fichier. Endpoints `/qc9434/bills(+/pay,/file multipart)`.
- [x] **Compta auto = suggestion éditable** : les écritures générées (facture/fournisseur/encaissement/paiement) restent modifiables dans l'onglet Écritures.
- [x] **Écriture de fermeture au verrouillage** (`_qc_post_closing`) : transfère le bénéfice net → BNR (330010), datée à la dernière date de l'exercice, `source=closing`. **Exclue des rapports** (bilan/pnl/tb) pour ne pas remettre le résultat à zéro. **Supprimée au déverrouillage**.
- [x] **Bilan & États des résultats en PDF présentation** (`_qc_report_pdf`) : `/qc9434/bilan/pdf`, `/qc9434/pnl/pdf`. Catalogue Envoi externe étendu : `bilan_pdf, pnl_pdf, trial_balance, bilan, pnl`.
- [x] **Import du modèle Excel** (`POST /qc9434/import-model`, admin, non idempotent) : crée l'exercice **2025** (facture #2025-001 « Société en commandite ACCS » 10 000 $ HT → 11 497,50 $, encaissée + fermeture + verrouillage) puis **2026** avec les **9 écritures** du modèle (frais bancaires mensuels, encaissement facture, intérêts, dividendes, paiement d'impôts). Résultat conforme : **net 2026 = −18,11 $**, bilan équilibré. Bouton « Importer le modèle Excel » dans l'état vide.
- [x] **Stockage objet** : `_qc_init_storage/_qc_put_object/_qc_get_object` (clé Emergent), init au démarrage. Fichiers fournisseurs servis via `/qc9434/bills/{id}/file?auth=TOKEN`.
- [x] **Vérifié** testing_agent iteration_36 : backend 25/25 (Phase 3) + 21/21 régression, frontend 100 %. Exactitude comptable (bilan toujours équilibré après factures/paiements, net = −18,11), gating de rôles, isolation entité principale. **État actuel : modèle réimporté proprement (2025 verrouillé + 2026).**
- [ ] **Backlog** : déplacer le bloc qc9434 (~1200 lignes) dans `backend/qc9434.py` ; contrôle type de token sur `/bills/{id}/file` ; index `qc9434_entries.year` ; en-tête/logo ACCS sur exports.

## Commandité — Phase 4 finalisée (frontend) + Rapports + Aperçu externe (2026-07-31)
- [x] **Factures clients (`InvoicesView`)** : colonnes Échéance + Solde, statut Encaissée/**Partielle**/Ouverte (`InvoiceStatus`), bannière rouge `qc-ar-overdue-banner` + badge RETARD si échéance dépassée, bouton **courriel** (`qc-invoice-email-*`, visible si courriel client), encaissement **partiel** via prompt (montant < solde → statut Partielle). Champ **Courriel du client** ajouté au dialogue de création (`qc-invoice-email-input`).
- [x] **Factures fournisseurs (`BillsView`)** : parité complète — colonnes Échéance + Solde, statut (`BillStatus`), bannière `qc-ap-overdue-banner`, **paiement partiel** via prompt (`qc-bill-pay-*`). Champ **Échéance** ajouté au dialogue (`qc-bill-due`).
- [x] **États Financiers** (`EtatsFinanciersView`, nouvel onglet `ef`) : État des résultats + BNR (courant vs précédent) + Bilan condensé, badge d'équilibre, exports **PDF** (`qc-ef-pdf`) et **Excel** (`qc-ef-excel`). API `qcEfPdf`/`qcEfExcel` ajoutées.
- [x] **Menu déroulant « Rapports »** : onglets principaux = Écritures · Factures clients · Factures fournisseurs ; le reste (Balance de vérification, Bilan détaillé, États des résultats, États Financiers, Plan comptable, Envoi externe) regroupé sous un dropdown `qc-tab-rapports`.
- [x] **Envoi externe — aperçu cliquable** : chaque ligne de rapport est cliquable + bouton « Aperçu » (`qc-external-preview-*`) ouvrant `QcExtPreviewDialog` qui affiche les données réelles du document (BV / Bilan / Résultats / États Financiers) avant envoi ; extension de téléchargement corrigée (pdf vs xlsx).
- [x] **Vérifié** testing_agent iteration_37 : backend 16/16 nouveaux + 25/25 régression Phase 3 (100 %), frontend ~100 % après correctifs (champ courriel + échéance). Bilan toujours équilibré (total_actif = total_pc). Données de test nettoyées (`scripts/qc_cleanup_testdata.py`).

## Commandité — Phase 5 : journal paiements, relances, États Financiers conformes + flux de trésorerie (2026-07-31)
- [x] **Journal des paiements** : dialogue `PaymentHistoryDialog` (boutons horloge `qc-invoice-history-*` / `qc-bill-history-*`) listant chaque encaissement/paiement partiel (n° écriture, date, montant) + en-tête Total/Réglé/Solde/statut. Endpoints `GET /qc9434/invoices/{id}/payments` et `GET /qc9434/bills/{id}/payments`.
- [x] **Relance courriel** : bouton `qc-ar-remind-btn` dans la bannière des retards → `POST /qc9434/invoices/send-reminders?year=` envoie un rappel à chaque facture cliente échue avec courriel (Resend). Erreur claire si Resend non configuré (comportement attendu).
- [x] **États Financiers conformes au modèle Excel** ("Commandité ACCS EF 2026") : libellés exacts (Honoraires de gestion, Services juridiques, Services d'expertise comptable et financière, etc.), colonnes **2026 vs 2025**, **chiffres 2025 FIGÉS** en dur (`QC_EF_PREV`), bilan 2026 **toujours équilibré** (BNR = solde équilibrant), colonne comparative 2025 au bilan (`prev_bilan`).
- [x] **États des flux de trésorerie** (méthode indirecte) ajouté à la vue, au PDF et à l'Excel — réconcilié (trésorerie fin = début + variation nette). Détail « Informations supplémentaires » (variation FDR).
- [x] **Signataires du Conseil d'administration** : bloc « Au nom du Conseil d'administration » (Marco Vézina / Simon Chevalier-Fournier — Administrateur) au bas du Bilan (vue + PDF + Excel), **éditables** via dialogue `qc-ef-sig-dialog` (admin). Endpoints `GET/PUT /qc9434/ef-settings` (collection `qc9434_settings`, clé `ef_admins`).
- [~] **Bug rapporté « téléversement + comptabilisation factures fournisseurs »** : NON REPRODUIT — testé via curl (fichiers jusqu'à 12 Mo) et UI ; création + comptabilisation auto + upload + récupération du fichier fonctionnent. En attente de précisions utilisateur (message d'erreur, taille/type de fichier).
- [x] **Vérifié** : iteration_38 (journal/relances = 100 %) + curl EF (2025 figé, bilan équilibré 11194,58=11194,58, PDF/Excel 200, PUT signataires) + captures (résultats/bilan 2 colonnes, signatures, flux de trésorerie, dialogue signataires).

## Commandité — Correctif soldes d'ouverture 2026 (2026-07-31)
- [x] **Cause** : l'import du modèle ne créait que la facture 2025, donc l'ouverture 2026 (soldes antérieurs) était incomplète → colonne « Antérieur » du Bilan détaillé vide, cumulatif non représentatif, flux de trésorerie sans trésorerie d'ouverture.
- [x] **Fix** : écriture d'à-nouveaux `Solde d'ouverture au 1er janvier 2026` (année 2025, source="opening", num "OUV-2026") calculée par deltas pour amener l'ouverture 2026 au bilan de clôture 2025 (`QC_OPENING_2026`, base débit, aligné sur la créance réelle 11 497,50 $ → aucun résidu). Helper `_qc_seed_opening_balances`, intégré à `POST /qc9434/import-model` + endpoint admin `POST /qc9434/seed-opening` (idempotent).
- [x] **Résultat vérifié** : Bilan détaillé — Antérieur 19 950,50 = équilibré ; Caisse 6 735 → 17 979,58 ; créance 11 497,50 → 0 (soldée). Flux de trésorerie : trésorerie début 6 735 + variation 11 244,58 = fin 17 979,58 (reconciled). Aucune modification de la structure des autres rapports de l'outil.

## Commandité — Colonne comparative 2025 au flux de trésorerie (2026-07-31)
- [x] Ajout des chiffres 2025 FIGÉS (`QC_CF_PREV`, modèle) au flux de trésorerie : net 411, quote-part -95, variation FDR 0, flux exploitation 316, distribution/placement 350, variation nette 666, trésorerie début 8 545 → fin 9 211, détail FDR (clients 1). Exposé via `cf.prev`.
- [x] Colonne 2025 rendue dans la vue (`qc-ef-cashflow-table` + détail), le PDF et l'Excel. Structure des autres rapports inchangée.
- [x] Vérifié : API renvoie `cashflow.prev`, PDF/Excel 200, capture confirme les 2 colonnes (2026 réconcilié : 6 735 + 11 232,68 = 17 967,68 ; 2025 : 8 545 + 666 = 9 211).

## Commandité — Saisie des soldes d'ouverture par exercice (2026-08-01)
- [x] Fonction backend générique `_qc_post_opening(year, targets, actor)` (à-nouveaux par deltas, entrée source="opening", opening_year=Y, année Y-1). `_qc_seed_opening_balances` = wrapper 2026.
- [x] Endpoints `GET /qc9434/opening/{year}` (trial balance d'ouverture des comptes de bilan) + `PUT /qc9434/opening/{year}` (valide Débit=Crédit puis pose l'à-nouveaux).
- [x] UI : bouton admin « Soldes d'ouverture » (`qc-opening-btn`) → dialogue `qc-opening-dialog` groupé par section, inputs débit/crédit, indicateur d'équilibre, enregistrement (`qc-opening-save`). Vérifié (2026 = 19 950,50 équilibré).

## Backlog demandé (2026-08-01) — à implémenter
- [ ] **Extraction IA à l'upload d'une facture fournisseur** : lire le fichier (PDF/image) et pré-remplir fournisseur/date/échéance/montant/taxes + suggérer un compte GL. (Intégration LLM vision requise.)
- [ ] **Factures multi-lignes** (fournisseurs ET clients) : plusieurs lignes (description + compte GL + montant) par facture, taxes calculées sur le total.

## Commandité — Phase 6 : Carnet clients, Notes de crédit, Extourne, Modification de factures (2026-08-10)
- [x] **Frontend complété** (backend déjà livré/testé iter 39) dans `QcEntity.js` :
  - **Onglet « Clients »** (`ClientsView`, tab `qc-tab-clients`) : carnet CRUD admin — nom, à l'attention, courriel, adresse, **compte de comptes-clients (AR) dédié** (sélecteur des comptes de type actif), actif/inactif. Écriture réservée aux admins (backend `require_admin`).
  - **Facture client — sélection d'un client** (`qc-invoice-client-select`) : pré-remplit nom/att/courriel/adresse et applique automatiquement le compte AR du client (saisie libre toujours possible).
  - **Actions par facture** : Modifier (`qc-invoice-edit-*`, visible seulement si `paid_amount==0 && credited_amount==0`), Note de crédit (`qc-invoice-credit-*`), Extourner (`qc-invoice-reverse-*`, visible seulement si `paid_amount==0`). Helpers `canEditInvoice/canReverseInvoice/canCreditInvoice`.
  - **`CreditNoteDialog`** : notes de crédit **liées** (client verrouillé, plafonnées au solde de la facture) ou **autonomes** (bouton `qc-add-credit-note`, sélecteur de client). Écriture inverse Dr Ventes/taxes / Cr Comptes clients.
  - **Extourne** : `AlertDialog` de confirmation (`qc-reverse-dialog`), marque la facture « Extournée » et annule le solde.
  - **`InvoiceStatus`** enrichi : statuts `reversed` (Extournée), `credit` (Note de crédit), `applied` (NC appliquée) + rendu des NC (montant négatif, flèche vers la facture liée).
- [x] `api.js` : ajout `qcClients/qcCreateClient/qcUpdateClient/qcDeleteClient`, `qcUpdateInvoice`, `qcReverseInvoice`, `qcCreateCreditNote`.
- [x] Correctif cosmétique : libellés d'`<option>` en concaténation de chaîne (silence l'avertissement React « <span> in <option> »).
- [x] **Vérifié** : testing_agent iteration_40 = **100 % (10/10 flux)** — CRUD clients, création/modification de factures, notes de crédit liées + autonomes, extourne, application de la règle `paid_amount` (Modifier/Extourner masqués après tout encaissement, Note de crédit conservée), aucune régression (Écritures/BV/Bilan/Résultats). Exercice 2026 laissé ouvert.
- Note tests : données de démonstration `TEST_*` créées via l'UI (1 client, ~4 factures, 3 notes de crédit) — à purger avant démo.


## Multi-sociétés — Validation P0 + Gap fix `company_id` (2026-08-14)
- [x] **Validation P0 (testing_agent iteration_42, 100%)** — (A) **Extourne** conserve l'écriture originale (`source='invoice'`) ET poste une écriture inverse (`source='reversal'`), sans jamais modifier/supprimer l'originale ; seuls `status/credited_amount/reversed_at` de la facture sont mis à jour. (B) **AccountDetailModal** (drill-down Bilan/Résultats) : barre de recherche (`qc-detail-search`) filtrant les lignes + bascule de portée (`qc-detail-scope-toggle`) Exercice {year} (movement) / Cumulatif (cumulative). Backend 7/7 pytest + frontend 100%.
  - Observation non bloquante (pré-existante) : la facture héritée **2026-001** a une écriture d'extourne orpheline (aucune écriture `source='invoice'` correspondante) — artefact d'un ancien code path, pas un bug du code actuel.
- [x] **Gap fix `company_id` (volet écriture — étape « pont » avant refonte multi-mandat complète)** : constat = aucune route POST n'écrivait `company_id` (seul le backfill du 14/08 l'avait ajouté aux 130 docs existants). Ajout d'un helper `_company_id(legacy_prefix)` (`server.py`, après `db=`) qui résout `'acct'→Meelora` / `'qc9434'→9434-3977 QC inc.` depuis `db.companies` (cache mémoire, RuntimeError explicite si société absente — pas de doc orphelin).
  - `company_id` injecté à **tous les sites de création** : **acct** (line-comments, budget-managers, email-log, external-contacts + seeds insert_many) ; **qc9434** (`_qc_post_entry` = factures/NC/factures fournisseurs/écritures manuelles/extournes, `_qc_post_opening`, création d'année, external-contacts, external-email-log, `_qc_seed_accounts`, accounts, templates, invoices, clients, credit_notes, bills, seeds startup 2025/2026).
  - **Vérifié** (curl + inspection DB) : nouvelle facture 9434 → `company_id`=9434 ✔, son écriture (`qc9434_entries`) → 9434 ✔, commentaire de ligne acct → Meelora ✔. Données de test purgées.
  - Reste à faire (Étape 4) : volet **lecture** (filtrer `find/find_one`/agrégations par `company_id`) + **sélecteur de société** dans l'UI. Ne pas activer le filtrage lecture sans avoir déployé ce volet écriture (déjà fait).

## Sélecteur de société + réparation écriture orpheline (2026-08-14)
- [x] **Sélecteur de société (en-tête)** : composant `CompanySelector` (`Layout.js`) affiché **uniquement** sur les pages Comptabilité (`active.startsWith('acct_')`). Deux mandats chargés via `GET /api/companies` : **Meelora** (`legacy_prefix='acct'`) et **9434-3977 QC inc.** (`legacy_prefix='qc9434'`). Bascule : Meelora → `acct_dashboard`, 9434 → `acct_qc9434` (page Commandité dédiée). Valeur active déduite de la page courante. Sur les pages Masse salariale, le sélecteur est absent (sélecteur d'année + badge « Budget actif » conservés). Endpoint backend `GET /api/companies` (auth, lecture seule) ; `api.getCompanies()` côté front. Testids : `company-selector`, `company-select`, `company-option-acct`, `company-option-qc9434`.
  - **Vérifié** : testing_agent iteration_43 = **100% (5/5)** — présence/absence conditionnelle + bascule aller-retour entre les 2 mandats.
- [x] **Réparation écriture orpheline (facture 2026-001)** : la facture héritée 2026-001 (Bikuma Bindanda, extournée) avait son écriture originale supprimée (`entry_id` pointait vers un doc inexistant) ; seule subsistait l'écriture d'extourne (`source='reversal'`), faussant le grand livre. Écriture originale reconstruite (inverse de l'extourne : Dr Comptes clients 11 497,50 / Cr Ventes 400310 + TPS 215310 + TVQ 215301), datée du 2026-08-07 (avant l'extourne du 2026-08-10), `source='invoice'`, `reference='2026-001'`, `company_id=qc9434` ; `entry_id` de la facture reconnecté. **Vérifié** : les 2 écritures nettent à 0,00 sur tous les comptes (400310/215310/215301/130118) et apparaissent dans le drill-down `account-detail` (originale avant extourne). Réparation ponctuelle en base (non liée au code, qui produit déjà des extournes correctes depuis).


## Étape 4 — Filtrage lecture par company_id (défensif ciblé) (2026-08-14)
- [x] Filtre `company_id` ajouté aux requêtes de LISTE/rapport principales de chaque module via le helper `_company_id(prefix)` : **qc9434** (années, écritures journal + rapports/balances + drill-down account-detail, factures, factures fournisseurs, clients, comptes, recherche tiers, relevé client, clôture) et **acct** (périodes : liste, dashboard, verrouillées, agrégat responsables). Approche (a) « défensif ciblé » retenue par l'utilisateur (les collections `acct_*`/`qc9434_*` sont déjà 1:1 avec une société ; ce filtrage est future-proof). Vérifié préalablement : 0 document sans `company_id` → aucune perte de données. Endpoints re-testés (curl) : années 2026/2025, 20 périodes, 23 comptes, 13 écritures — OK.

## Rebranding « Meelora » — refonte visuelle globale (2026-08-14)
- [x] **Migration couleurs globale** (sed sur tout `frontend/src`, ~514 occurrences) : `#063044→#0F172A` (Deep Navy), `#0E9488`+`#15AF97→#22C55E` (Meelora Green), `#F8A942→#FBBF24` (Amber), `#F4F6F8→#F3F4F6` (Light Gray). Palette Meelora : Deep Navy #0F172A · Green #22C55E · Mint #A7F3DD · Amber #FBBF24 · Light Gray #F3F4F6.
- [x] **Typographie Satoshi** (`index.css`, Fontshare) en remplacement de Montserrat+Calibri (body, `.font-display`, `.font-mono-data`, `.font-sans/.font-mono`, form/table).
- [x] **Sidebar refondue navy→BLANC/CLAIR** (`Layout.js`) : logo `MeeloraLogo` (SVG M vert + point ambre + wordmark 'meelora'), item actif = fond Mint + icône/label vert, groupes en overline ; bloc bas tagline « Votre entreprise, clairement. » + profil utilisateur. NavItem/NavSubItem/NavParent recolorés en thème clair.
- [x] **Header** : fil d'Ariane (`breadcrumb`), titre Satoshi gras, + 3 boutons ronds (`header-help-btn`, `header-notif-btn`, `header-settings-btn`→Mon profil). **Footer global** (`app-footer`) : « © 2026 Meelora inc. » + liens.
- [x] **Login** rebrandé (logo meelora blanc sur navy / navy sur mobile, footer Meelora). Titre onglet `index.html` = « Meelora — Votre entreprise, clairement. ».
- [x] **Vérifié** : testing_agent iteration_44 = **100% frontend**, aucune régression (11 items de nav, sélecteur société, cartes KPI, tableaux, format québécois, graphiques recolorés).
- [ ] **En attente utilisateur** : PNG officiel du logo Meelora à intégrer (logo SVG provisoire fidèle à la charte en place, `data-testid='brand-logo'`).


## Finalisation Meelora — Logo officiel + PDF + Thème sombre (2026-08-14)
- [x] **Logo officiel PNG intégré** : fichier fourni par l'utilisateur (webp transparent 2000×667) traité via Pillow → variantes générées dans `frontend/public/` : `meelora-logo.png` (mark+wordmark sans tagline), `meelora-mark.png` (icône M), `meelora-logo-full.png` (avec tagline), `favicon.png` (64px), `logo192.png`. Copies aplaties blanc dans `backend/assets/` pour les PDF. Composant `MeeloraLogo` bascule sur `<img>`. Login (carte blanche + logo full / mobile), sidebar, footer (mark), favicon + apple-touch-icon dans `index.html`. Vérifié : images chargées (naturalWidth>0).
- [x] **Rapports PDF — logo + palette Meelora** : `presentation_reports.py` palette mise à jour (NAVY #0F172A, TEAL→GREEN #22C55E, ORANGE→AMBER #FBBF24, GREY #F3F4F6, LIGHTGREEN→MINT #A7F3DD) + helper `_logo()`. `server.py` : recolor backend (#0E1526/#14B8A6/#0E9488/#F59E0B/#063044 → palette Meelora) + helper module `_pdf_logo()` inséré dans TOUS les générateurs PDF : budget, fiche employé, fiches, gestionnaire, acct (résultats/bilan/cashflow), qc (journal, bilan/pnl, relevé client, facture, états financiers). Vérifié curl : qc bilan (270KB), qc journal, acct bilan (280KB) = PDF valides avec logo.
- [x] **Thème sombre adapté Meelora** (`index.css`) : fond navy #0F172A, cartes #16233A / bordures #243B5A, accents Mint→vert translucide, focus-ring + `--ring` (clair & sombre) passés en vert `142 71% 45%`. Boutons/accents restent verts #22C55E. Vérifié : bascule `.dark`, aucun texte illisible.
- [x] **Vérifié** : testing_agent iteration_45 = **100% frontend** (6/6 critères), aucune régression.


## Menu utilisateur (header) + photo de profil + ajustements login (2026-08-14)
- [x] **Profil déplacé en haut à droite** : nouveau composant `UserMenu` (`Layout.js`) — avatar circulaire (data-testid='user-menu-toggle') dans le header, à droite des icônes aide/notifications.
- [x] **Photo de profil** : upload via input fichier (data-testid='avatar-file-input') → backend `POST /api/me/avatar` (stockage objet Emergent, réutilise `_qc_put_object`), `DELETE /api/me/avatar`, `GET /api/users/{uid}/avatar` (public, sert l'image). `/auth/me` renvoie `has_avatar`. `/api/me/avatar` ajouté à `WRITE_ALLOW_ALL` (tout utilisateur connecté). Frontend : `api.uploadAvatar/deleteAvatar`, avatar = `Avatar` shadcn (AvatarImage `${BACKEND}/api/users/{id}/avatar?v=ts`, fallback initiales). Validé curl : upload 200 → serve 200 → delete → 404.
- [x] **Initiales** : `getInitials(name)` = 1ʳᵉ lettre du 1ᵉʳ mot + 1ʳᵉ lettre du dernier mot (ex. 'Bikuma B.' → 'BB'), fond coloré selon le rôle.
- [x] **Menu flottant** : `DropdownMenu` shadcn (data-testid='user-menu') avec nom+email+badge rôle, 'Changer la photo', 'Retirer la photo', 'Mon profil', 'Utilisateurs' (admin), 'Déconnexion' — remplace l'ancienne expansion inline dans la sidebar.
- [x] **Login** : logo blanc `meelora-logo-white.png` (wordmark recoloré en blanc, mark vert + tagline verte) directement sur le panneau navy — carte blanche supprimée.
- [x] **Sidebar** : bloc profil + tagline 'Votre entreprise, clairement.' supprimés.
- [x] **Vérifié** : testing_agent iteration_46 = **100% frontend** (5/5 + upload photo), aucune régression.


## Avatars Users/Journal + cloche active + logo Excel + crayon photo (2026-08-14)
- [x] **Composant réutilisable `UserAvatar`** (`components/UserAvatar.jsx`) : photo via `${BACKEND}/api/users/{id}/avatar` sinon initiales (2 lettres) colorées par rôle + `getInitials`.
- [x] **Avatars affichés** : page Utilisateurs (photo par `u.id`) et Journal d'audit (initiales, pas d'id dans les logs) — data-testid='user-avatar'.
- [x] **Cloche header vivante** : `NotificationsBell` (`Layout.js`) — fetch `GET /api/notifications` (polling 60s), badge compteur (data-testid='notif-badge') + dropdown flottant (data-testid='notif-menu') listant les factures ÉCHUES/à échoir (entité 9434), items cliquables (nav vers acct_qc9434), état vide (data-testid='notif-empty'). Endpoint backend calcule overdue (due<aujourd'hui) et soon (≤7j) sur `qc9434_invoices` ouvertes avec solde>0.
- [x] **Logo dans les exports Excel** : helper `_xlsx_logo(ws)` (réserve la 1re ligne + insère `assets/meelora-logo.png`) appliqué aux 6 exports budget/masse salariale (comparatif scénarios, P&L, rapport budgétaire, fiches détaillées, masse par classe, rapport personnalisé) ; styles de titre décalés A1→A2. Vérifié : `xl/media/image1.png` présent dans les xlsx.
- [x] **Menu utilisateur (tâche crayon)** : item 'Retirer la photo' supprimé du menu. Au survol de la photo (en-tête du dropdown) : bouton CRAYON (data-testid='avatar-change') → ouvre l'input fichier ; bouton CROIX (data-testid='avatar-remove') visible au survol quand une photo existe → retire la photo.
- [x] **Vérifié** : testing_agent iteration_47 = **100% frontend** (import `UserAvatar` repositionné dans Users.js par l'agent). Excel vérifié via curl.


# ============================================================
# MEELORA V2 — MIGRATION STRANGLER (7 phases)
# ============================================================
## PHASE 1 — FONDATION (2026-08-14) ✅ TERMINÉE
Modèle de tenancy : WORKSPACE > COMPANY > données financières. Non destructif, backend-first.
- **Collections nouvelles** : `workspaces` {id,name,organization_type(company|group|fiduciary),primary_jurisdiction(CH|CA),jurisdictions[],onboarding_complete,created_at} · `company_access` {id,workspace_id,company_id,user_id,role(principal|collaborator)} (= AUTORITÉ de sécurité) · `mandates` {id,workspace_id,company_id,code,principal_user,collaborators[],status}.
- **Champs ajoutés** : companies(workspace_id,company_type,industry ; jurisdiction préexistait 'CA-QC') · users(workspace_id) · journal(workspace_id).
- **Backend** (`server.py`) : helpers `_ws_id`, `_accessible_company_ids` (admin=toutes sociétés du workspace ; user=sociétés assignées), `require_company_access` (404 si hors périmètre). Endpoints : `/auth/me` (workspace+org type), `/workspace`, `/onboarding` (POST, verrouillé si onboarding_complete), `/logs` (admin-only, scopé workspace), `/company-access` (GET/POST/DELETE), `/mandates` (GET/POST). `/companies` scopé workspace+accès. `log_action` stampe workspace_id.
- **Frontend** : 'Journal d'audit' → **'Logs'** (admin-only, nav-journal). Écran `Onboarding.jsx` (affiché si admin && onboarding_complete===false). `api.completeOnboarding/getWorkspace`.
- **Migration** : `scripts/phase1_foundation.py` (DRY-RUN → COMMIT, idempotente) — workspace 'Meelora' (company, CA, CH+CA) créé ; 2 sociétés + admin rattachés ; company_access admin=principal ×2 ; 1026 logs stampés. Re-run = 0 changement.
- **Tests** : testing_agent iteration_48 — backend 9/9 critiques, frontend 100%, aucune régression du core existant.
- **⚠️ Warnings / dépendances legacy restantes** :
  1. `require_company_access` câblé sur `/companies` + endpoints V2 UNIQUEMENT ; les routes legacy `acct_*`/`qc9434_*` filtrent par company_id mais NE vérifient PAS encore l'assignation user (à durcir).
  2. Rôle legacy `editor` conservé (non normalisé vers `user`) — rapporté seulement.
  3. Un seul utilisateur admin existe → scoping `user` non testé end-to-end (pas de compte user de test).
  4. Collections legacy `acct_*`/`qc9434_*` intactes (nettoyage = Phase 7).
- **Prochaine étape recommandée** : soit (A) durcir l'enforcement `company_access` sur les routes legacy + gestion des utilisateurs/assignations (UI admin) ; soit (B) démarrer PHASE 2 — Financial Core (financial_years/periods, accounts, imports, trial balance & journal normalisés). **EN ATTENTE D'APPROBATION.**


## PHASE 1 — RÉIMPLÉMENTATION MODULAIRE P1.10 (2026-08-14) ✅ INTÉGRÉE & VALIDÉE — SUPERSEDES la section ci-dessus
Le client a fourni `meelora_phase1_p1_10.zip` : réimplémentation modulaire, propre et testée de la Phase 1 (P1.1→P1.10), construite AU-DESSUS du travail de session (avatars/notifications/logo intacts). Elle REMPLACE l'approche ad-hoc `phase1_foundation.py` + `Onboarding.jsx`.

### Architecture intégrée
- **`backend/core/`** (nouveau, modulaire) : `workspaces.py`, `auth_context.py`, `permissions.py`, `company_access.py`, `companies.py`, `mandates.py`, `logs.py`, `access_management.py`, `company_imports.py`.
- **`server.py`** : importe `core/*`; `get_current_user` charge le workspace (fail-closed 403 si workspace manquant/inactif) ; routes fondation déléguées aux services core.
- **Scripts migration séparés (dry-run→commit)** : `migrate_phase1_workspace.py`, `migrate_phase1_company_access.py`, `migrate_phase1_logs.py`, `migrate_phase1_mandates.py`.
- **Frontend** : nouvelles pages `Companies.js` (label Sociétés/Mandats selon org_type) + `Logs.js` ; `Layout.js` NAV_FOUNDATION ; suppression de `Onboarding.jsx`/`Journal.js`. Pages financières + P1.10 role-compat (Employes/Departements/SalairesBudget/Comptabilite/Rapports/Preferences/Users) mises à jour.

### Modèle de données (schéma P1.10 — DIFFÉRENT de l'ancien)
- `workspaces` : `_id="ws_<hex>"` (STRING, = identifiant tenant), `name`, `organization_type`(company|group|fiduciary), `jurisdiction`, `primary_admin_user_id`, `status`, `onboarding_completed`.
- `companies` : `id`(uuid/`cmp_`), `workspace_id`(→ws _id), `name`, `company_code`, `jurisdiction`, `status`, `active`, `legacy_prefix`(pont acct/qc9434).
- `company_access` (AUTORITÉ sécurité) : `_id="cacc_"`, `workspace_id`, `company_id`, `user_id`, `access_role`(principal|collaborator), `active`. Index unique partiel : 1 principal actif/société.
- `mandates` (fiduciaire only) : `_id="mnd_"`, `workspace_id`, `company_id`, `mandate_code`, `principal_user_id`, `collaborator_user_ids[]`, `status`. Index uniques partiels (1 mandat actif/société, code unique).
- `users` : `workspace_id`, `status`. `logs` : collection immuable admin-only scopée workspace (dual-write journal conservé).

### Réconciliation DB (approuvée par le client)
L'ancienne migration avait laissé un schéma incompatible (workspace `_id`=ObjectId+`id`uuid, `role` au lieu de `access_role`, `primary_jurisdiction`). Reset des 3 collections fondation (workspaces/company_access/mandates) + retrait workspace_id/status sur users/companies → état legacy. **Données financières `acct_*`/`qc9434_*` + `journal` JAMAIS touchées** (comptes vérifiés identiques avant/après).

### Migrations exécutées (dry-run → commit)
- Workspace : **Meelora / fiduciary / CA** (`ws_56c492936ea64c4db53a2f14a0825ef5`), admin@accslegro.com rattaché + 2 sociétés (Meelora/acct, 9434/qc9434).
- company_access : indexes créés (0 accès inféré du legacy — pas d'invention de principal).
- logs : 1027 lignes journal → logs (idempotent, journal conservé). Remap workspace_id périmé→nouveau ws (les lignes journal legacy portaient l'ancien uuid).
- mandates : indexes. **BUG CORRIGÉ** : `partialFilterExpression {status:{$ne:"inactive"}}` invalide sous MongoDB → remplacé par `{status:"active"}` (égalité supportée).
- **Fix core** : `_load_workspace_user`/`_workspace_user` rendus robustes (ObjectId `_id` en prod + fallback `id` string) — corrige 5 tests unitaires bson-env.

### Validation (2026-08-14)
- **Tests unitaires Phase 1** : 44/44 PASS (`tests/test_phase1_*.py`, pytest-asyncio installé). Ancien `test_phase1_foundation.py` supprimé (endpoints disparus).
- **Matrice sécurité (curl)** : admin→2 sociétés ; Julie→[Meelora] ; Marc→[Meelora,9434] ; Julie GET company B=403, company A=200, inconnu=404 (pas d'énumération) ; Julie /logs=403 (admin-only).
- **Mandats** : création→sync company_access ; doublon actif/société=409 ; PATCH inactive→révocation accès. Import Excel PREVIEW : lignes valides/erreurs bloquantes (juridiction, doublon code)/warnings détectés, 0 société créée (non destructif).
- **P1.10 régression** : Julie (role user) PEUT écrire (POST/DELETE départements=200) mais bloquée sur routes admin (users, hypotheses=403). NON read-only.
- **Régression financière** : tous endpoints acct_*/qc9434_* (dashboard, kpis, cashflow, trial-balance, bilan, pnl, entries, invoices, bills) = 200 avec params ; export Excel = fichier xlsx valide. Aucune régression.
- **STEP 14** : 0 user/company sans workspace_id ; 0 accès cross-workspace ; 0 doublon principal/mandat actif ; collections financières + journal intacts. **PASS**.

### Comptes de test (voir /app/memory/test_credentials.md)
admin@accslegro.com/admin123 · julie@accslegro.com/julie123 (Meelora only) · marc@accslegro.com/marc123 (Meelora+9434).

### ⚠️ Dépendances legacy restantes (à traiter en Phase 2+)
1. Routes legacy `acct_*`/`qc9434_*` filtrent par company_id mais N'appliquent PAS encore `require_company_access` (durcissement Financial Core).
2. Rôle legacy `editor` exposé comme `user` (normalisation DB à finaliser).
3. `legacy_prefix` maintenu comme pont (retiré à la migration Financial Core).

### STATUT : Phase 1 production-ready. **STOP — EN ATTENTE D'APPROBATION EXPLICITE AVANT PHASE 2 (Financial Core).**

## PHASE 1+ — DURCISSEMENT ACCÈS LEGACY (2026-08-14) ✅ FAIT & VALIDÉ
À la demande explicite du client : chaque route financière legacy applique désormais `company_access`.
- **Middleware `write_guard` (server.py)** étendu : pour tout `/api/acct/*` (société `acct`) et `/api/qc9434/*` (société `qc9434`), TOUTES méthodes → résolution `_company_id(prefix)` puis vérification d'une affectation `company_access` active (workspace_id+company_id+user_id+active). **Admin bypass** (toutes sociétés du workspace). User sans affectation active → 403 « Accès à cette société non autorisé » ; user sans workspace → 403 « Contexte workspace requis ». Optimisé : lookup user seulement si route financière OU écriture.
- **Helper** `_legacy_prefix_for_path(path)` ; réutilise `_normalized_role` (editor→user).
- **Validé (curl)** : matrice READ+WRITE — admin=200 partout ; Julie (acct only) acct=200 / qc9434=403 (GET et POST) ; Marc (acct+qc9434)=200 partout ; routes NON-financières (employees/departments) inchangées ; scoping `/api/companies` intact ; 44/44 tests unitaires Phase 1 OK.
- **Nettoyage** : suppression de l'artefact `tests/test_phase1_e2e_review.py` (test d'intégration généré par le testing agent, frappait le backend live et polluait la DB à chaque `pytest` — créait des mandats/désactivait des accès). DB remise propre : 3 users (admin/julie/marc), 2 sociétés, 0 mandat, 3 accès actifs, logs préservés.
- **Reste (Phase 2 Financial Core)** : les routes legacy ciblent encore UNE société fixe par préfixe (`_company_id`) ; le vrai multi-société par route (sélecteur/param company_id) viendra avec la normalisation Financial Core.

## P1.11 — LEGACY FINANCIAL ACCESS HARDENING + Sign-off Phase 1 (2026-08-14) ✅ VALIDÉ (testing_agent iteration_50)
Durcissement finalisé via le **helper centralisé** `require_company_access` (et non plus une requête inline).
- **Middleware `write_guard`** (server.py) : pour `/api/acct/*` et `/api/qc9434/*` (toutes méthodes), `_company_id(legacy_prefix)` sert UNIQUEMENT de pont pour résoudre la société, puis `build_auth_user(user_doc, workspace_doc)` + `await require_company_access(db, company_id, auth_user)` ; `HTTPException`→`JSONResponse`. Admin bypass ; user non affecté→403 ; cross-workspace/inexistant→404 (via `require_same_workspace`, pas de fuite d'existence). Aucun moteur/collection/formule financière modifié.
- **Fix log P1.9** : `POST /api/companies/import/commit` journalise désormais `company.created` par société importée, en plus de `mandate.created` (créé par le service) et `company.bulk_imported` (batch).
- **Validation testing_agent (iteration_50, backend 87% — 5 mineurs hors périmètre)** :
  - P1.11 : admin=200 ; Julie (acct only) acct=200/qc9434=403 (READ+WRITE) ; Marc=200 les deux ; **user non affecté=403 partout**. ✅
  - Smoke financier admin (dashboard/kpis/pnl-monthly/cashflow ; qc9434 trial-balance/bilan/pnl/entries/invoices) = 200 non vides → **formules inchangées**. ✅
  - P1.9 E2E COMMIT (code société unique) : preview valid=1 → commit created=1 → company + mandate actif (principal Julie, collab Marc) + company_access synchronisé + logs → **nettoyage ciblé** → baseline restaurée. Aucune donnée historique touchée. ✅
- **Points mineurs relevés (informational, hors P1.11)** : pas d'endpoints DELETE companies/mandates (enhancement) ; DELETE user = soft-deactivate P1.7 (comportement voulu) ; `GET /users/{id}/company-access` [] = artefact transitoire du test (vérifié OK ensuite) ; `company.created` manquant à l'import = **corrigé**.
- **Nettoyage post-tests** : dérive de données restaurée (société acct→"Meelora"/CA, users julie→"Julie Test", marc→"Marc Test") ; script one-off dans `/app/test_reports/scratch/` (PAS dans tests/, non collecté par pytest). Baseline finale : users=3, companies=2, mandates=0, active company_access=3, 44/44 tests unitaires.

### ✅ PHASE 1 — FINAL SECURITY SIGN-OFF : APPROUVÉ. **STOP — Phase 2 en attente d'approbation explicite du client.**

## PHASE 2 — P2.1 FINANCIAL YEARS (2026-08-14) ✅ IMPLÉMENTÉ & VALIDÉ (testing_agent iteration_51) — P2.2 NON DÉMARRÉ
Première brique du Financial Core normalisé, en parallèle du legacy (aucune donnée legacy migrée).
- **Module dédié** : `backend/core/financial/` (package extensible : years → plus tard periods/accounts/data_imports/trial_balance/journal/ingestion). `years.py` = modèles + services purs (list/get/create/update) réutilisant l'autorisation Phase 1 (`require_company_access`/`require_company_admin`).
- **Collection** `financial_years` : `{_id:"fy_<uuid>", workspace_id, company_id, label, start_date, end_date, status(open|closed), created_at/by, updated_at}`.
- **Routes fines (server.py)** : GET/POST `/api/companies/{company_id}/financial-years`, GET/PATCH `/api/companies/{company_id}/financial-years/{id}`. Pas de DELETE physique (405). Création admin-only (`require_admin`), lecture pour user affecté.
- **Règles métier** : 1 exercice = 1 workspace + 1 société ; NON calendaire (jamais dérivé de date.year) ; start<=end (422) ; pas de chevauchement par société (409, `[s1<=e2 AND s2<=e1]`) ; label unique par société (409) ; même label OK sur sociétés différentes ; pas de suppression physique.
- **Index** : unique `(workspace_id, company_id, label)` + `(workspace_id, company_id, start_date, end_date)` (créés au startup).
- **Sécurité** (réutilise Phase 1, PAS de 2e système) : admin same-workspace=OK ; user affecté=lecture ; user non affecté=403 ; cross-workspace/inexistant=404 (no-leak).
- **Logs** : `financial_year.created/updated/closed/reopened` (close/reopen distingués via previous_status) avec workspace_id/company_id/entity_id/acteur.
- **Tests permanents** : `tests/test_p2_financial_years.py` (16, in-memory, SANS effet de bord). Le test API live du testing_agent est rangé dans `/app/test_reports/scratch/` (non collecté par pytest par défaut, anti-pollution).
- **Validation testing_agent iteration_51** : 23/23 API + 16/16 unit P2.1 + 44/44 régression Phase 1 ; smoke financier legacy 200 (formules inchangées) ; P1.11 intact ; baseline restaurée (users=3, companies=2, mandates=0, active_access=3, financial_years=0).
- **Sécurité legacy** : acct_*/qc9434_*, formules BV/P&L/Bilan/Cashflow, acct_periods/qc9434_years, legacy_prefix, comportement P1.11 → **inchangés**.
- **Dépendances legacy restantes** : `acct_periods`/`qc9434_years` non migrés (P2.x ultérieur) ; financial_years non peuplé depuis le legacy (attendra instruction explicite).
- **Reco P2.2** : `financial_periods` (rattachés à un financial_year, avec verrouillage introduit à ce moment-là).

### 🛑 P2.1 TERMINÉ. STOP — NE PAS DÉMARRER P2.2 avant approbation explicite du client.

## PHASE 2 — P2.2 FINANCIAL PERIODS (2026-08-14) ✅ IMPLÉMENTÉ & VALIDÉ (testing_agent iteration_52) — P2.3 NON DÉMARRÉ
Périodes normalisées rattachées aux exercices (financial_years), en parallèle du legacy.
- **Module** : `backend/core/financial/periods.py` (services purs, réutilise l'autorisation Phase 1/P2.1). Routes fines dans server.py.
- **Collection** `financial_periods` : `{_id:"fp_<uuid>", workspace_id, company_id, financial_year_id, period_code, label, start_date, end_date, period_type(month|quarter|adjustment), sequence, status(open|locked|closed), created_at/by, updated_at}`.
- **Endpoints** : GET/POST `/api/companies/{cid}/financial-years/{fyid}/periods` ; POST `.../periods/generate-monthly` ; GET/PATCH `/api/companies/{cid}/financial-periods/{pid}`. Pas de DELETE physique (405).
- **Règles** : 1 période=1 exercice ; workspace/company doivent matcher l'exercice parent (404 sinon) ; période entièrement dans l'exercice (422) ; pas de chevauchement/exercice (409) ; period_code unique/société (409) ; sequence unique/exercice (409) ; sequence NON basée sur janvier (position fiscale) ; exercices non calendaires first-class ; pas de suppression physique.
- **Génération mensuelle** : admin, mois calendaires contigus couvrant l'exercice, sequence dès 1 (= 1er mois fiscal), idempotente (skip period_codes existants), rejette exercice non aligné mois entiers (422, message clair — pas de règle inventée). Pas de 4-4-5.
- **Machine à états (verrou/clôture)** explicite : open↔locked, open↔closed, locked→closed, closed→open ; transition invalide (ex. closed→locked)=409. **Non propagé** aux écritures acct_*/qc9434_* (phase compat ultérieure).
- **Index** : unique `(ws,company,fy,sequence)`, unique `(ws,company,period_code)`, `(ws,company,fy,start,end)`.
- **Sécurité** : admin same-workspace read+admin ; user affecté=lecture ; non affecté=403 ; cross-workspace/inexistant=404 (no-leak) ; parent FY d'une autre société=404.
- **Logs** : financial_periods.generated, financial_period.created/updated/locked/unlocked/closed/reopened (workspace/company/entity/acteur).
- **Tests permanents** : `tests/test_p2_financial_periods.py` (22 in-memory, sans effet de bord). Test API live rangé dans `/app/test_reports/scratch/` (non collecté).
- **Validation testing_agent iteration_52** : 31/31 API + 22/22 unit P2.2 + 16/16 P2.1 + régression Phase 1 ; smoke financier legacy 200 (formules inchangées) ; P1.11 intact ; baseline restaurée (financial_years=0, financial_periods=0).
- **Sécurité legacy** : acct_periods/qc9434_years, formules BV/P&L/Bilan/Cashflow, P1.11 → inchangés. Aucune donnée legacy migrée.
- **Reco P2.3** : Unified Accounts (plan de comptes normalisé) réutilisant `core/financial/`.

### 🛑 P2.2 TERMINÉ. STOP — NE PAS DÉMARRER P2.3 avant approbation explicite du client.

## PHASE 2 — P2.3 UNIFIED ACCOUNTS (2026-08-14) ✅ IMPLÉMENTÉ & VALIDÉ (testing_agent iteration_53) — P2.4 NON DÉMARRÉ
Plan de comptes normalisé canonique par société, en parallèle du legacy (aucun compte legacy migré).
- **Module** : `backend/core/financial/accounts.py` (services purs, réutilise l'autorisation Phase 1). Routes fines dans server.py.
- **Collection** `accounts` : `{_id:"acc_<uuid>", workspace_id, company_id, account_code, account_name, account_type, normal_balance, currency, active, source_system, external_id, created_at/by, updated_at}`.
- **Endpoints** : GET (filtres active/account_type/search)/POST `/api/companies/{cid}/accounts` ; GET/PATCH `/api/companies/{cid}/accounts/{aid}`. Pas de DELETE physique (405).
- **Règles** : account_code = STRING opaque (zéros de tête et ponctuation préservés, jamais casté en int) ; unique/société (409) ; même code OK sur sociétés différentes ; account_name requis ; account_type ∈ {asset,liability,equity,revenue,expense,other} ; normal_balance ∈ {debit,credit} (stocké explicitement, non déduit) ; currency par défaut = company.functional_currency (validée 3 lettres ISO, uppercased, ne modifie JAMAIS la devise société) ; active défaut true ; pas de suppression physique (deactivate/reactivate via PATCH) ; source_system métadonnée ; external_id optionnel (prep connecteur).
- **Index** : unique `(ws,company,account_code)` ; lookups `(ws,company,active)`, `(ws,company,account_type)` ; unique PARTIEL `(ws,company,source_system,external_id)` seulement si external_id présent (`$type:string`, pas de collision sur null).
- **Sécurité** : admin same-workspace read+admin ; user affecté=lecture ; non affecté=403 ; cross-workspace/inexistant=404 (no-leak) ; compte d'une autre société=404.
- **Logs** : account.created/updated/deactivated/reactivated (workspace/company/entity/account_code/acteur ; log 'updated' non émis sur PATCH vide).
- **Tests permanents** : `tests/test_p2_accounts.py` (23 in-memory). Test API live dans `/app/test_reports/scratch/`.
- **Validation testing_agent iteration_53** : 27/27 API + 23/23 unit + régression P2.2/P2.1/Phase 1 ; smoke financier legacy 200 ; P1.11 intact ; baseline restaurée (accounts=0).
- **Sécurité legacy** : acct_account_map/qc9434_accounts, formules, P1.11 → inchangés. Aucun compte legacy migré.
- **Reco P2.4** : Data Imports (ingestion normalisée alimentant accounts + trial balance), utilisant source_system/external_id pour l'idempotence connecteur.

### 🛑 P2.3 TERMINÉ. STOP — NE PAS DÉMARRER P2.4 avant approbation explicite du client.

## PHASE 1 — P1.12 MULTI-LEVEL IDENTITY & MEMBERSHIP (2026-08-14) ✅ IMPLÉMENTÉ & VALIDÉ (testing_agent iteration_54) — P2.3 EN PAUSE
Sépare l'identité globale (users) de l'appartenance workspace et société.
- **Modules** : `backend/core/memberships.py` (services + validate_combo + index) ; `core/permissions.py` refactoré ; `core/auth_context.py` (+platform_role). Routes fines dans server.py. Migration `scripts/migrate_p1_12_identity.py`.
- **Collections ajoutées** : `workspace_memberships` {_id:wsm_, workspace_id, user_id, role(admin|user), status} ; `company_memberships` {_id:cpm_, workspace_id, company_id, user_id, membership_type(workspace_staff|company_user), role, status}. `users` +`platform_role`(null|support|platform_admin).
- **Index** : unique partiel actif `(ws,user)` [wsm] ; unique partiel actif `(ws,company,user,membership_type)` [cpm] ; lookups user/company.
- **Combinaisons rôle** : workspace_staff∈{principal,collaborator} ; company_user∈{admin,user} (validées, 422 sinon).
- **Auth** : platform_role séparé, N'accorde AUCUN accès client auto (platform_admin sans workspace → 403 fail-closed). users.workspace_id conservé comme contexte workspace actif transitionnel.
- **Helpers** : require_workspace_admin, require_workspace_membership, require_company_local_admin (workspace admin OU company_user+admin de CETTE société), require_company_access **dual-read** (company_memberships + company_access legacy), require_company_admin reste workspace-admin-only (financier), list_accessible_company_ids union.
- **APIs** : GET/POST/PATCH `/api/workspace/members` (workspace-admin) ; GET/POST/PATCH `/api/companies/{cid}/members` (workspace-admin ou admin local ; admin local limité aux company_user de sa société, ne peut affecter le personnel fiduciaire ni voir autres sociétés/Logs).
- **Logs** : workspace_member.created/updated/deactivated, company_member.created/updated/deactivated, company_admin.user_created/user_updated. Logs restent workspace-admin only.
- **Migration (dry-run→commit)** : users.workspace_id→workspace_memberships (admin/user) ; company_access→company_memberships (workspace_staff principal/collaborator). company_access **préservé** (pont). platform_role=null posé. Aucun user local inventé, aucun platform_role inféré. Résultat : 3 wsm + 3 cpm.
- **Tests permanents** : `tests/test_p1_12_memberships.py` (14 in-memory). Suite globale 119/119.
- **Validation testing_agent iteration_54** : 15/15 live (dual-read, workspace-admin CRUD, admin local scoping, company_user lecture seule, platform_admin fail-closed, combos 422, cross-workspace 404, logs admin-only, smoke financier inchangé). Baseline restaurée.
- **Frontend** : inchangé en P1.12 (pas de redesign ; l'UI Membres par contexte est un enhancement recommandé, non implémenté).
- **users.workspace_id encore utilisé ?** OUI (contexte workspace actif transitionnel + auth_context + pont helpers). **company_access encore utilisé ?** OUI (pont legacy dual-read, non supprimé).
- **Reco avant reprise P2.3** : marquer company_access legacy une fois l'UI Membres migrée ; ajouter le sélecteur de workspace uniquement pour utilisateurs multi-organisations.

### 🛑 P1.12 TERMINÉ. STOP — NE PAS REPRENDRE P2.3 avant approbation explicite du client.

## P2.3 — Comptes unifiés (Financial Core) — FINALISÉ sous P1.12 (2026-08-14)
- [x] **Module** `core/financial/accounts.py` validé/finalisé : CRUD, `account_code` opaque STRING (zéros de tête / ponctuation / alphanumérique préservés, jamais casté), devise héritée de `company.functional_currency` si omise (jamais mutée, validée 3 lettres ISO), pas de suppression physique (drapeau `active`), unicité `account_code` par société + unicité partielle `external_id` par (société, source) uniquement si présent.
- [x] **Routes** `server.py` : `GET/POST /api/companies/{id}/accounts`, `GET/PATCH .../{account_id}`. POST/PATCH gardés par `require_admin` (workspace admin) ; module appelle `require_company_admin` (workspace-admin-only, conforme P1.12). Logs `account.created/updated/deactivated/reactivated` avec workspace_id, company_id, entity_id, account_code, acteur.
- [x] **Index** créés au démarrage : UNIQUE (ws+company+code), lookup (ws+company+active), lookup (ws+company+type), UNIQUE partiel (ws+company+source+external_id) si external_id string.
- [x] **Autorisation P1.12** : lecture via `require_company_access` (dual-read `company_memberships`→legacy `company_access`) ; admin structurel = workspace admin uniquement (admin local société = users locaux seulement). `platform_role` n'accorde AUCUN accès client automatique.
- [x] **Tests** : `test_p2_accounts.py` porté à **32 cas** (+8 matrice de sécurité P1.12 : principal/collaborator via memberships, company_user admin/user lecture OK + admin structurel refusé, platform_admin sans membership refusé, isolation par société, parité membership vs legacy). Suite in-memory permanente **128/128 verte** (Phase 1 + P1.11 + P1.12 + P2.1 + P2.2 + P2.3).
- [x] **Smoke live** : create (code `SMOKE-0010` préservé, devise CAD héritée) + list/search OK ; legacy `acct` summary HTTP 200 ; comptes de test supprimés (baseline propre, 0 compte normalisé, chart legacy intact).
- [x] **Dépendances legacy P2.3** : `users.workspace_id` utilisé uniquement via helper centralisé `require_tenant_context` (contexte de session, pas comme vérité d'appartenance) ; `company_access` utilisé uniquement comme pont dual-read en lecture. Aucune nouvelle dépendance introduite. Aucune collection `acct_*`/`qc9434_*` touchée.

### 🛑 P2.3 FINALISÉ. STOP — NE PAS DÉMARRER P2.4 (Imports de données) avant approbation explicite du client.

## P2.4 — Registre des imports de données & cycle de vie (Financial Core) — 2026-08-14
- [x] **Module** `core/financial/data_imports.py` : registre canonique d'ingestion (`data_imports`) conçu pour accounts / trial_balance / transactions / journal / api. Seul **accounts** est pleinement connecté en P2.4 (preview + commit → `accounts` P2.3). Statuts : pending/validating/valid/importing/completed/completed_with_warnings/failed.
- [x] **APIs** : `POST /api/companies/{id}/imports/accounts/preview` (upload Excel/CSV, crée le record, parse, valide, **n'écrit jamais** dans accounts), `POST .../imports/accounts/commit` (applique l'import validé, upserts idempotents, compteurs, statut), `GET .../imports` (filtres data_type/source_type/status), `GET .../imports/{import_id}`.
- [x] **Cycle de vie** : preview → valid|failed ; commit refuse failed (409), no-op si déjà committé (`already_committed`), no-op sûr si même source (checksum) déjà importée. Compteurs `records_received/created/updated/rejected`.
- [x] **Validation** : erreurs bloquantes (code/nom manquant, type/solde invalide, doublon de code en conflit dans le fichier) vs warnings (compte existant → mise à jour, devise omise → héritée, external_id absent, doublon identique ignoré). `account_code` préservé en STRING (zéros de tête / ponctuation).
- [x] **Idempotence** : checksum SHA-256 + `idempotency_key = ws:company:accounts:checksum` ; index NON unique (ré-imports de données modifiées autorisés) ; commit protégé contre double soumission.
- [x] **Upsert comptes** : priorité (source_system+external_id) puis (company+account_code) → aucun doublon normalisé. Devise héritée de `company.functional_currency` si omise. Aucune collection legacy touchée.
- [x] **Autorisation P1.12** : preview/commit = workspace admin uniquement (aligné P2.3 structural admin) ; historique = tout membre société autorisé (`require_company_access`, dual-read). `platform_role` sans membership → aucun accès. Cross-workspace 404.
- [x] **Index** `data_imports` : (ws+company+created_at desc), (ws+company+status), (ws+company+data_type), (idempotency_key).
- [x] **Logs** : `data_import.previewed/validated/completed/completed_with_warnings/failed` (workspace_id, company_id, import_id, data_type, source_type, acteur).
- [x] **Tests** : `test_p2_4_data_imports.py` **32/32** (parsing, preview sans écriture, validation, idempotence, upsert, historique + filtres, matrice de sécurité P1.12). Suite in-memory permanente **160/160 verte** (Phase 1 + P1.11 + P1.12 + P2.1 + P2.2 + P2.3 + P2.4).
- [x] **Smoke live** : preview (codes `0090`/`7777` préservés, devise héritée CAD) → commit (2 créés, completed_with_warnings) → re-commit idempotent (`already_committed`) → historique 1 → accounts vérifiés ; imports/accounts de test supprimés (baseline propre : 0 account, 0 data_import).

### 🛑 P2.4 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P2.5 (Balance de vérification normalisée) avant approbation explicite du client.

## P2.5 — Balance de vérification normalisée (trial_balance_lines) — 2026-08-14
- [x] **Module** `core/financial/trial_balance.py` : couche normalisée `trial_balance_lines` bâtie sur le cycle de vie P2.4 (`data_imports`, data_type=`trial_balance`). Chaque import référence un exercice + une période et résout chaque `account_code` source contre le plan comptable normalisé P2.3 (jamais de création silencieuse).
- [x] **Convention nette (jamais inversée par type de compte)** : `period_net = period_debit − period_credit` ; `ytd_net = ytd_debit − ytd_credit`. La présentation/solde normal reste au reporting futur.
- [x] **Sources** : account_code (requis), account_name (opt.), period_debit/credit, period_net (opt., cohérence validée à ±0,01), ytd_debit/credit, ytd_net (opt., cohérence validée). YTD source préservé quand fourni ; net calculé si omis.
- [x] **Contexte financier validé** : exercice appartient à la société, période appartient à l'exercice ET à la société (mismatch → 422 ; introuvable/cross-workspace → 404). Import lié à company/workspace.
- [x] **Contrôles de balance** (bloquants par défaut) : period_total_debit/credit + period_difference ; ytd_total_debit/credit + ytd_difference ; tolérance 0,01. Une balance déséquilibrée n'est jamais importée silencieusement.
- [x] **Doublons dans le fichier** : exact → warning + déduplication ; en conflit → erreur bloquante (préférence rejet vs agrégation cachée).
- [x] **APIs** : `POST /api/companies/{id}/imports/trial-balance/preview` (multipart : file + financial_year_id + financial_period_id ; n'écrit **jamais** de lignes), `POST .../imports/trial-balance/commit`, `GET .../trial-balance?financial_period_id&import_id&account_id` (+ totaux de contrôle), `GET .../imports/{import_id}/trial-balance`.
- [x] **Idempotence / versioning** : commit lié à `import_id` ; retry sur le même import → no-op (`already_committed`) ; **plusieurs versions par période autorisées** (chaque import commit crée son propre jeu de lignes ; lignée jamais écrasée). Pas de suppression physique.
- [x] **Index** `trial_balance_lines` : (ws+company+period+import), UNIQUE (ws+company+import+account) — empêche les doublons intra-import sans bloquer les versions multiples —, (ws+company+period+account).
- [x] **Sécurité P1.12** : preview/commit = workspace admin uniquement (aligné P2.4) ; lecture = membre société autorisé (dual-read) ; company-local admin ≠ import structurel ; platform_role sans membership → aucun accès ; cross-workspace 404. Pas de conversion FX.
- [x] **Logs** : `trial_balance.previewed/validated/completed/failed` (workspace_id, company_id, financial_year_id, financial_period_id, import_id, acteur, totaux de contrôle).
- [x] **Tests** : `test_p2_5_trial_balance.py` **34/34**. Suite in-memory permanente **194/194 verte** (Phase 1 + P1.11 + P1.12 + P2.1..P2.5).
- [x] **Smoke live** : FY→périodes→comptes→preview (équilibré, contrôles OK)→commit (2 lignes)→re-commit idempotent→lecture avec totaux ; toutes les données de test supprimées (baseline propre). Legacy `acct` summary HTTP 200 ; aucune collection `acct_*`/`qc9434_*` touchée.

### 🛑 P2.5 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P2.6 (Journal / Transactions normalisés) avant approbation explicite du client.

## P2.6 — Journal comptable normalisé (journal_entries + journal_entry_lines) — 2026-08-14
- [x] **Module** `core/financial/journal.py` : couche journal normalisée sur le cycle de vie P2.4 (`data_imports`, data_type=`journal`). Regroupe les lignes source par `entry_id` (jamais par ordre de ligne), résout chaque `account_code` contre le plan comptable P2.3, valide l'équilibre par écriture (Σdébit=Σcrédit, tolérance 0,01), la date dans la période, et les règles de montant.
- [x] **Convention nette** : `net = debit − credit` (jamais inversée par type de compte).
- [x] **Règles de ligne** : debit≥0, credit≥0, pas les deux positifs, au moins un montant non nul ; négatif → bloquant ; `line_number` unique et contigu par écriture.
- [x] **Statut de période (P2.2)** : écritures normalisées autorisées uniquement si la période est `open` ; `locked`/`closed` → import refusé (409) au preview ET au commit ; réouverture admin rétablit l'import. **N'affecte pas** le comportement legacy acct/qc9434.
- [x] **APIs** : `POST .../imports/journal/preview` (multipart file + fy + fp ; n'écrit rien), `POST .../imports/journal/commit`, `GET .../journal-entries` (filtres period/import/account/date_from/date_to/reference, lignes aplaties + totaux), `GET .../journal-entries/{entry_id}`, `GET .../journal-entries/aggregate` (réconciliation lecture seule).
- [x] **Doublons** : dans une écriture, ligne dupliquée en conflit (même identifiant, données ≠) → bloquant ; doublon exact → dédupliqué (warning) déterministe (jamais de double comptabilisation).
- [x] **Idempotence / versioning** : commit lié à `import_id`, retry = no-op (`already_committed`) ; plusieurs versions par période autorisées ; lignée jamais écrasée ; pas de suppression physique. `external_entry_id`/`external_line_id` préservés pour l'idempotence connecteur future.
- [x] **Réconciliation (préparation P2.9)** : `aggregate_journal` renvoie total_debit/credit + net par compte pour une période/import — **lecture seule**, n'écrit PAS `trial_balance_lines`, n'exige PAS l'égalité avec la BV pour le commit.
- [x] **Index** — journal_entries : (ws+company+period), (ws+company+import), (ws+company+entry_date), UNIQUE partiel (ws+company+source_system+external_id) si présent. journal_entry_lines : UNIQUE (ws+company+entry+line_number), (ws+company+account), (ws+company+entry).
- [x] **Sécurité P1.12** : import structurel = workspace admin uniquement ; lecture = membre société autorisé (principal/collaborator/company_user admin+user) ; company-local admin ≠ import ; platform_role sans membership → aucun accès ; cross-workspace 404.
- [x] **Logs** : `journal.previewed/validated/completed/failed` (+ totaux, entry/line count, fy/fp, import_id, acteur).
- [x] **Tests** : `test_p2_6_journal.py` **37/37**. Suite in-memory permanente **231/231 verte** (Phase 1 + P1.11 + P1.12 + P2.1..P2.6).
- [x] **Smoke live** : FY→périodes→comptes→preview (écriture équilibrée)→commit (1 écriture / 2 lignes)→re-commit idempotent→liste (lignes+totaux)→aggregate (net 9001=+100 / 9002=−100) ; données de test supprimées (baseline propre). Legacy `acct` HTTP 200, aucune collection legacy touchée.

### 🛑 P2.6 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P2.7 (Abstraction d'ingestion) avant approbation explicite du client.

## P2.7 — Abstraction d'ingestion (refactor architectural) — 2026-08-14
- [x] **Nouveau package** `core/financial/ingestion/` : `readers.py` (ExcelReader/CSVReader = `read_tabular`, transport uniquement, `_cell_str`), `base.py` (contrat `ImportAdapter`, états de cycle de vie + `assert_transition`, catégories d'erreurs), `registry.py` (fabrique data_type→adapter, échec explicite si inconnu), `orchestrator.py` (unique implémentation du cycle de vie : création data_import, transitions, compteurs, idempotence), `adapters/{accounts,trial_balance,journal}.py` (règles de domaine déléguées aux services existants), `connectors/base.py` (BaseConnector + MockConnector, AUCUN fournisseur réel).
- [x] **Duplication supprimée** : la lecture Excel/CSV (≈3×55 lignes) est centralisée dans `read_tabular` ; le cycle de vie data_import (création doc, gardes de statut, transition importing, compteurs, no-op idempotent) est centralisé dans l'orchestrateur. Les 6 fonctions `preview_*/commit_*` sont devenues de **fins délégateurs** (import local de l'orchestrateur + registry → aucun cycle d'import).
- [x] **Comportement inchangé** : APIs publiques `/imports/{accounts,trial-balance,journal}/{preview,commit}` identiques ; logs conservés au niveau des routes ; règles de domaine (code opaque, devise héritée, net=debit−credit, comptes manquants bloquants, équilibre par écriture, verrou de période journal, versions multiples, lignée d'import, external IDs) préservées.
- [x] **Connecteurs (préparation P2.7)** : interface `BaseConnector` (connect/test_connection/fetch_accounts/fetch_trial_balance/fetch_transactions) + `MockConnector` (payloads simulés / échec `ConnectorError`). `source_type=api` passe par le MÊME cycle de vie data_import (accounts adapter accepte `api`). Aucun fournisseur réel, aucun secret.
- [x] **Modèle d'erreurs** : catégories normalisées (`source_format_error`, `validation_error`, `account_resolution_error`, `financial_consistency_error`, `duplicate_error`, `period_error`, `connector_error`) sans remplacer les messages utilisateur spécifiques.
- [x] **Sécurité inchangée** (P1.12) : import structurel = workspace admin ; lecture = membre autorisé ; company-local admin / platform_role sans membership refusés ; cross-workspace 404.
- [x] **Tests** : `test_p2_7_ingestion.py` **18/18** (registry, readers, transitions, connecteurs mock, source_type=api). **Parité prouvée** : P2.4 (32), P2.5 (34), P2.6 (37) restent verts via la nouvelle abstraction. Suite in-memory permanente **249/249 verte**.
- [x] **Smoke live parité** : accounts (preview valid → commit completed_with_warnings, 2 créés), trial_balance (valid → completed, 2 lignes), journal (valid → completed, 1 écriture / 2 lignes) via les mêmes routes publiques ; legacy `acct` HTTP 200 ; données de test supprimées (baseline propre).

### 🛑 P2.7 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P2.8 (Pont de compatibilité legacy) avant approbation explicite du client.

## P2.8 — Pont de compatibilité legacy (LECTURE SEULE) — 2026-08-14
- [x] **Module** `core/financial/compatibility.py` : couche d'adaptation en lecture exposant les données normalisées V2 (accounts / trial_balance / journal) dans des formes compatibles legacy, SANS écrire dans acct_*/qc9434_* et SANS changer les formules. La seule collection écrite est `financial_config` (drapeau de source, scoped société).
- [x] **Sélection de source** : drapeau `financial_data_source: legacy|normalized` **scoped société**, appliqué au backend, **défaut legacy**, réversible, changement **admin uniquement**, journalisé. Aucun switch global, aucune contamination inter-sociétés.
- [x] **Adaptateurs** : `NormalizedAccountsCompatibilityAdapter` (code opaque préservé, name, active, type), `NormalizedTrialBalanceCompatibilityAdapter` (débit/crédit/net période + cumul, convention P2.5 non inversée, totaux de contrôle), `NormalizedJournalCompatibilityAdapter` (date/référence/description, lignes ordonnées par line_number, totaux).
- [x] **Règle de version (déterministe)** : dernier import **complété** (completed/completed_with_warnings) pour société+période, trié par (completed_at, _id) ; les imports échoués/incomplets ne sont jamais sélectionnés ; `import_id` exposé dans la réponse/status.
- [x] **Normalisé indisponible** : en mode normalized sans données requises → **erreur contrôlée 409** (aucun repli silencieux vers legacy). En mode legacy → marqueur explicite `use_legacy_endpoint` (les endpoints legacy restent la source, inchangés).
- [x] **APIs** : `GET /api/companies/{id}/financial-source/status` (métadonnées P2.9), `PUT /api/companies/{id}/financial-source` (admin), `GET /api/companies/{id}/compat/{accounts,trial-balance,journal}`. Routes publiques existantes inchangées.
- [x] **Sécurité P1.12** : lecture via `require_company_access` ; changement de source via workspace admin ; platform_role sans membership refusé ; cross-workspace 404 ; P1.11 legacy intacte.
- [x] **Logs** : `financial_source.changed` (workspace_id, company_id, old_source, new_source, acteur). Pas d'inondation de logs sur les lectures normales.
- [x] **Preuve zéro écriture legacy** : test dédié espionnant acct_bv/acct_ledger/acct_account_map/qc9434_accounts/qc9434_entries → 0 écriture pendant les lectures compat.
- [x] **P&L / Bilan / Flux de trésorerie** : INCHANGÉS, restent sur legacy (migration = phases ultérieures ; réconciliation = P2.9).
- [x] **Tests** : `test_p2_8_compatibility.py` **23/23**. Suite in-memory permanente **272/272 verte** (Phase 1 + P1.11 + P1.12 + P2.1..P2.8).
- [x] **Smoke live (switch)** : défaut legacy → set normalized (accounts `0091/0092` + TB via normalisé, contrôles équilibrés) → 2e société reste legacy → status expose import_id/compteurs → retour legacy → legacy `acct` HTTP 200 ; données de test supprimées (baseline propre, financial_config vidé).

### 🛑 P2.8 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P2.9 (Réconciliation des données) avant approbation explicite du client.

## P2.9 — Réconciliation des données (LECTURE SEULE, diagnostic) — 2026-08-14
- [x] **Module** `core/financial/reconciliation.py` : moteur de réconciliation en lecture seule. Ne mute JAMAIS les données financières (aucun write-back legacy/normalisé, aucune écriture d'équilibrage, aucune auto-correction). Données manquantes = `not_available`/`incomplete`, jamais traitées comme zéro (pas de faux positif).
- [x] **3 niveaux** : (1) plan comptable legacy vs normalisé (matched/missing_in_normalized[critical]/missing_in_legacy/name_difference + sévérité), (2) BV legacy vs BV normalisée (par compte + totaux de contrôle sur les 6 mesures, tolérance 0,01, convention net non inversée), (3) journal normalisé (agrégat P2.6) vs BV normalisée période (matched/journal_only/tb_only/difference).
- [x] **Interprétation legacy EXPLICITE** : la BV legacy (`acct_bv`, clé "YYYY-MM", colonnes opaques) n'est lue que si l'appelant fournit `legacy_period_key` + mapping de colonnes (period_debit/credit, ytd_debit/credit) → **jamais de supposition** ; sinon `not_available`.
- [x] **Sélection de version normalisée** : règle déterministe P2.8 (dernier import complété société+période) + override explicite `normalized_import_id` ; imports échoués exclus ; `normalized_import_id` toujours rapporté.
- [x] **Couverture journal / YTD** : basée sur `financial_period.sequence` (jamais le calendrier). Mensuel = 1 période ; YTD = séquences 1..sélectionnée ; couverture insuffisante → `incomplete` (aucune valeur cumulée inventée).
- [x] **Verdict global + cutover_ready** : `cutover_ready` exige BV normalisée + BV legacy disponibles, réconciliation BV = reconciled, et 0 écart critique de mapping de comptes. Le journal est rapporté séparément. **Aucun switch automatique** de `financial_data_source` (flag P2.8 inchangé).
- [x] **APIs (GET, lecture seule)** : `/reconciliation/{status,accounts,trial-balance,journal-vs-trial-balance}` (params financial_period_id, normalized_import_id, tolerance, legacy_period_key + colonnes, ytd).
- [x] **Sécurité P1.12** : lecture = membre société autorisé (principal/collaborator/company_user admin+user + admin) ; non autorisé 403 ; platform_role sans membership 403 ; cross-workspace 404. Aucun nouveau modèle de permission.
- [x] **Preuve zéro écriture** : test espion → 0 écriture sur acct_*/qc9434_* ET sur les collections normalisées pendant toutes les réconciliations.
- [x] **P&L / Bilan / Flux de trésorerie** : INCHANGÉS, restent legacy (migration = phase moteur de reporting, après validation du Financial Core).
- [x] **Tests** : `test_p2_9_reconciliation.py` **31/31**. Suite in-memory permanente **303/303 verte** (Phase 1 + P1.11 + P1.12 + P2.1..P2.9).
- [x] **Smoke live** : match parfait → `reconciled` + `cutover_ready=true` ; différence injectée (compte 10 : legacy 120 vs normalisé 100) → `difference` écart −20 détecté ; journal absent → `incomplete` (pas de faux zéro) ; legacy `acct` HTTP 200 ; données de test (dont 2 BV legacy) supprimées (baseline restaurée).

### 🛑 P2.9 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P2.10 (Validation/Sign-off Phase 2) avant approbation explicite du client.

## P2.10 — Sign-off / Validation Phase 2 (couche d'évidence, gel d'audit) — 2026-06 (APPROUVÉ par le client)
- [x] **Module** `core/financial/phase2_signoff.py` + collection `phase2_signoffs` (`_id=p2so_<uuid>`). AUCUN calcul financier nouveau : la préparation est dérivée EXCLUSIVEMENT de la sortie réelle de `reconciliation_status` (P2.9) + `reconcile_journal_vs_tb`. Ne mute JAMAIS `financial_data_source` (pas de cutover — préparation seulement) ni les collections legacy (acct_*/qc9434_*). Seule `phase2_signoffs` est écrite.
- [x] **Décisions** : `approved` | `approved_with_conditions` | `blocked`. Règles : `approved` REFUSÉ (422) si TB ≠ reconciled OU cutover_ready=false OU écarts critiques de comptes > 0 ; `approved` simple aussi refusé si journal ≠ reconciled (→ utiliser approved_with_conditions). `approved_with_conditions` exige conditions non vides ET les portes dures TB/cutover (le journal seul ne bloque pas si documenté). `blocked` toujours permis, conserve `reconciliation_reasons`.
- [x] **validation_snapshot** (évidence immuable, PAS de duplication des datasets) : reconciliation generated_at, normalized_import_id, legacy_period_key, tolérance, résumé comptes, totaux de contrôle TB, compteurs de différences, nb d'écarts critiques, statut+couverture journal, overall_status, cutover_ready.
- [x] **Supersession** (jamais d'écrasement/suppression) : un nouveau sign-off société/période marque le précédent `superseded=true` (+ superseded_at/superseded_by) et pointe via `supersedes_signoff_id`. Le dernier finalisé (non superseded) est identifiable de façon déterministe.
- [x] **APIs** : `POST /api/companies/{id}/phase2-signoffs` (workspace admin), `GET /api/companies/{id}/phase2-signoffs` (liste, filtre période), `GET /api/companies/{id}/phase2-signoffs/{signoff_id}`, `GET /api/companies/{id}/phase2-signoff-status?financial_period_id=...`. **Cutover NON implémenté** (choix client — sécurité > convenance ; le flag P2.8 reste inchangé).
- [x] **Sécurité P1.12** : création/finalisation = workspace admin uniquement (`require_company_admin`) ; lecture = membre société autorisé ; admin company-local = lecture seule ; platform_role sans membership refusé ; cross-workspace 404.
- [x] **Logs** : `phase2_signoff.{approved|approved_with_conditions|blocked}` (workspace_id, company_id, financial_period_id, signoff_id, normalized_import_id, decision, acteur). Aucun log sur les lectures.
- [x] **Tests** : `test_p2_10_signoff.py` **19/19** ; suite in-memory permanente **322/322 verte** (Phase 1 + P1.11 + P1.12 + P2.1..P2.10).
- [x] **Smoke live (pilote Meelora, période fictive 2099)** : status → `reconciled` + `cutover_ready=true` ; POST approved → OK (snapshot 15 clés) ; scénario en échec (sans mapping legacy) → 422 ; blocked supersède l'approved ; status latest=blocked count=2 ; Julie (principal) lit (200) mais ne peut créer (403) ; société sans accès 403 ; sign-off inexistant 404 ; logs `phase2_signoff.approved/.blocked` présents ; legacy `acct`/`companies` HTTP 200 ; **baseline restaurée** (acct_bv 2099-01 supprimé, 0 phase2_signoffs résiduels).

## 🏁 RAPPORT DE COMPLÉTION PHASE 2 — FINANCIAL CORE (2026-06)
1. **Composants livrés** : P2.1 Exercices, P2.2 Périodes, P2.3 Comptes unifiés, P2.4 Cycle de vie des imports, P2.5 Balance normalisée, P2.6 Journal normalisé, P2.7 Abstraction d'ingestion, P2.8 Pont de compatibilité legacy, P2.9 Réconciliation, P2.10 Sign-off.
2. **Collections introduites** : `financial_years`, `financial_periods`, `accounts`, `data_imports`, `trial_balance_lines`, `journal_entries`, `journal_entry_lines`, `financial_config`, `phase2_signoffs`.
3. **APIs introduites** : imports (accounts/TB/journal preview+commit), lectures TB/journal, financial-source (status/set), compat (accounts/TB/journal), reconciliation (accounts/TB/journal-vs-TB/status), phase2-signoffs (create/list/get/status).
4. **Modèle de sécurité** : P1.12 partout — import/structurel/sign-off = workspace admin ; lecture = membre autorisé ; company-local admin borné ; platform_role sans accès client automatique ; cross-workspace 404.
5. **Ingestion** : abstraction unifiée (readers/adapters/orchestrator/registry) ; connecteurs (BaseConnector + MockConnector, **aucun fournisseur réel — MOCKÉ**).
6. **Comptes normalisés** : opaques (code string préservé), devise, normal_balance ; réconciliés vs legacy.
7. **Balance de vérification** : normalisée, contrôles d'équilibre, convention net=debit−credit ; réconciliée vs BV legacy (tolérance 0,01).
8. **Journal** : normalisé, équilibre par écriture, agrégat de réconciliation vs TB (couverture par sequence, mensuel/YTD).
9. **Pont de compatibilité** : lecture normalisée en formes legacy, flag société réversible, défaut legacy, aucune écriture legacy.
10. **Réconciliation** : diagnostic lecture seule 3 niveaux + `cutover_ready`.
11. **Résultat sign-off pilote** : APPROVED prouvé sur données réconciliées + cutover_ready ; approbation refusée (422) sur scénario en échec ; supersession prouvée.
12. **Tests permanents** : **322/322 verts** (< 2 s, in-memory). (Les tests d'intégration HTTP legacy `test_admin_write_guard`/`test_preferences`/`test_fiche_overrides` échouent en pré-existant : identifiants legacy non semés dans cet environnement — hors périmètre Phase 2.)
13. **Smoke legacy** : endpoints `acct`/`companies`/`employees` HTTP 200 après P2.10 ; aucune collection legacy modifiée destructivement.
14. **Limitations connues** : connecteurs API réels non implémentés (mockés) ; cutover non implémenté (préparation seulement, par choix de sécurité).
15. **Dépendances legacy restantes** : P&L / Bilan / Flux de trésorerie / KPI / Dashboards restent sur legacy (`acct_bv` clé "YYYY-MM", colonnes opaques).
16. **Dépendances pont d'identité** : P1.12 (workspace_memberships / company_memberships + pont company_access) — stable.
17. **Société réellement basculée en normalisé ?** : **NON** — aucune (défaut legacy conservé partout ; aucun cutover exécuté).
18. **Phase 2 prête à la clôture ?** : **OUI** — Financial Core complet, testé, réversible, non destructif.
19. **Préconditions Phase 3 (Reporting Engine)** : (a) sign-off approuvé par société/période cible ; (b) interprétation legacy explicite (clé + mapping colonnes) validée ; (c) couverture journal si le reporting le requiert ; (d) décision de bascule `financial_data_source` par société (action séparée, à concevoir).
20. **Prochaine étape recommandée** : **ATTENDRE l'approbation explicite du client** avant de démarrer la Phase 3 (moteur de reporting P&L/Bilan/Flux sur données normalisées). NE PAS démarrer Concepts financiers / Templates de reporting.

### 🛑 P2.10 IMPLÉMENTÉ — PHASE 2 PRÊTE À LA CLÔTURE. STOP — NE PAS DÉMARRER LA PHASE 3 (Reporting Engine) avant approbation explicite du client.

## P3.1 — Couche sémantique de reporting (concepts / mappings / templates skeleton) — 2026-06 (APPROUVÉ)
> Design P3.1 approuvé (voir `/app/memory/P3.1_design_proposal.md`) avec ajustements. Implémentation P3.1 = schémas + gouvernance + validations + indexes + sécurité + APIs référentiel/mapping/template skeleton. **AUCUN seed réel** de concepts/templates standards (→ P3.2). **AUCUN moteur de calcul** (→ P3.4). **`report_runs` conçu mais NON créé** (→ P3.4). Aucune modification P2 / `acct_*` / `qc9434_*`.
- [x] **`financial_concepts`** (`core/financial/concepts.py`) : référentiel canonique **system-managed, global**. `concept_code` **sémantiquement immuable** (dépréciation/remplacement `replaced_by_concept_id`, jamais de mutation sémantique sous nouveau `version` ; seuls sort_order/tags mutables → version cosmétique). Concepts contra dédiés (`contra_asset|contra_liability`). Écriture = **platform_admin uniquement** ; lecture = utilisateur tenant. Pas de suppression (deprecate only).
- [x] **`financial_i18n_labels`** (`core/financial/i18n.py`) : **table i18n dédiée** pour concepts/templates système (codes langue-neutres) ; résolution déterministe (demandée → défaut profil → `en`). Labels embarqués tolérés pour le custom. Écriture platform_admin, lecture tenant.
- [x] **`account_mappings`** (`core/financial/mappings.py`) : compte P2.3 → concept canonique. **Cardinalité** : au plus **un** mapping `confirmed` non-superseded par compte (index unique partiel) ; fenêtre effective par **`financial_period_id`** (+ `sequence` dénormalisée), cohérente avec le Financial Core ; antidatage refusé (409). **`unmapped` DÉRIVÉ** (jamais stocké : statuts stockés = suggested/confirmed/rejected). Splits préparés (`weight=1.0`) non activés. Supersession sans suppression. Gouvernance : create/confirm/reject + `mapping-coverage` (dérive mapped/suggested_only/unmapped, ratio, fully_mapped). Écriture = workspace admin ; lecture = membre autorisé.
- [x] **`reporting_templates` + `reporting_template_lines`** (`core/financial/reporting_templates.py`) : SKELETON de présentation (sections/concept/subtotal/formula/spacer, `display_sign`, `measure` period|ytd, arbre `parent_line_id`). Système = platform_admin ; custom = workspace/company scoped (workspace admin). Versioning immuable (draft→published→archived ; `new-version` clone en draft). **`semantic_bypass` (compte→ligne) autorisé UNIQUEMENT en custom** (warning explicite sur ses limites), **interdit en système**. Publication exige ≥1 ligne. **Aucun moteur de calcul.**
- [x] **`jurisdiction_profiles`** : system-managed (frameworks, locales, templates par défaut, concepts requis/optionnels, conventions d'affichage). Écriture platform_admin, lecture tenant. (Référentiels cibles CA_PRIVATE_ENTERPRISE_STANDARD / CH_CO_SME_STANDARD seedés en P3.2.)
- [x] **Sécurité** : nouveau garde `require_platform_manager` (permissions.py) = seul endroit honorant `platform_role='platform_admin'`, et **jamais** d'accès aux données client. Client-scoped réutilise P1.12 (`require_company_admin`/`require_company_access`) ; platform_role sans membership refusé ; cross-workspace 404.
- [x] **APIs** : référentiel (`GET/POST/PATCH /api/financial-concepts`, `.../deprecate`, `GET/POST /api/financial-i18n/labels`, `GET/POST /api/jurisdiction-profiles`), mappings (`GET/POST /api/companies/{id}/account-mappings`, `.../{mid}/confirm|reject`, `GET .../mapping-coverage`), templates (`GET/POST /api/reporting-templates`, `.../lines`, `.../publish|archive|new-version`, `GET /api/companies/{id}/reporting-templates`). Logs d'audit : `financial_concept.created/.deprecated`, `account_mapping.{suggested|confirmed|rejected}`, `reporting_template.created/.published`.
- [x] **Tests** : `test_p3_1_reporting_semantics.py` **27/27** ; suite permanente in-memory **349/349 verte** (Phase 1 + P1.11/12 + P2.1..P2.10 + P3.1).
- [x] **Smoke live** : GET concepts (tenant) ; admin sans platform_role → concept 403 & template système 403 ; mapping suggested→confirmed ; concept agrégat non mappable 422 ; Julie mapping 403 ; coverage dérivé ; template custom create→ligne concept→ligne semantic_bypass (warning)→publish→get (2 lignes) ; jurisdiction profiles 200 ; legacy `companies` 200 ; **baseline nettoyée** (0 concept/mapping/template résiduel).

### 🛑 P3.1 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P3.2 (seed concepts/profils/templates standards) avant approbation explicite du client.

## P3.2 — Seed système (concepts canoniques + i18n + profils CA/CH + templates standards) — 2026-06 (APPROUVÉ)
> Seed système **déterministe, idempotent, versionné, system-managed**. Aucune donnée client (pas d'account_mappings, pas de template custom, pas de report_runs). Aucun moteur de calcul. Zéro modification P2 / `acct_*` / `qc9434_*`.
- [x] **Module** `core/financial/system_seed.py` + script `scripts/seed_reporting_system.py` + endpoint `POST /api/system/reporting-seed` (chemin de gestion plateforme, `require_platform_manager`). `run_system_seed(db)` = contexte système ; `run_system_seed_as(db, user)` = contexte plateforme (platform_admin). Rapport : created/existing/updated/skipped/errors + counts. **Jamais d'écrasement sémantique** (drift bloqué → `errors`, template publié jamais muté). SEED_VERSION `2026.06.0`.
- [x] **59 concepts canoniques** (codes anglais langue-neutres, sémantiquement immuables) : 9 agrégats (ASSETS/CURRENT_ASSETS/NON_CURRENT_ASSETS/LIABILITIES/CURRENT_LIABILITIES/NON_CURRENT_LIABILITIES/EQUITY/INCOME/EXPENSES) + concepts contra dédiés (ACCUMULATED_DEPRECIATION/AMORTIZATION) + concepts structurants (RELATED_PARTY_RECEIVABLES/PAYABLES, RIGHT_OF_USE_ASSETS, LEASE_LIABILITIES_CURRENT/NON_CURRENT, PROVISIONS, FOREIGN_EXCHANGE_GAIN/LOSS, NON_RECURRING_ITEMS, LEGAL_RESERVES, DEFERRED_TAX_ASSET/LIABILITY). `cash_flow_category` renseigné uniquement où sûr (operating/investing/financing), `none` sinon (FX, financier, impôts différés, résultat). Agrégats non mappables (règle P3.1).
- [x] **236 labels i18n** (table dédiée P3.1) : en/fr/de/it pour les 59 concepts. Résolution à fallback déterministe.
- [x] **2 profils de juridiction** : `CA` (framework `CA_PRIVATE_ENTERPRISE`, « Meelora Canada Private Enterprise Standard — aligned with… conventions », locales en/fr, CAD) et `CH` (framework `CH_CO_SME`, « Meelora Swiss CO SME Standard — aligned with Swiss Code of Obligations presentation (not exhaustive) », locales fr/de/it/en, CHF). `default_template_codes` valides. **Aucun calcul fiscal.**
- [x] **4 templates système publiés (v1, immuables)** : `CA_PRIVATE_ENTERPRISE_STANDARD_BS` (47 lignes), `CA_PRIVATE_ENTERPRISE_STANDARD_PL` (21 lignes), `CH_CO_SME_STANDARD_BS`, `CH_CO_SME_STANDARD_PL`. **Concepts canoniques identiques CA/CH** ; terminologie via labels de ligne (en/fr pour CA ; en/fr/de/it pour CH). BS avec sous-totaux (courants/non-courants, total actifs, total passifs+CP) ; P&L avec Gross Profit/EBITDA/EBIT/PBT/Net income en formules (grammaire skeleton, **non exécutées**). **Aucun `semantic_bypass`, aucun account_ref** ; toutes les concept_refs valides, line_codes uniques, parents et références de formule validés au seed.
- [x] **Sécurité** : écriture seed = platform_admin uniquement (`run_system_seed_as` → 403 pour workspace admin) ; lecture référentiel = utilisateur tenant. platform_role n'ouvre aucun accès client. P1.12 inchangé.
- [x] **Tests** : `test_p3_2_system_seed.py` **18/18** (idempotence, unicité codes, intégrité parents, agrégats/contra, concepts structurants requis + support KPI, blocage drift sémantique, i18n en/fr/de/it + fallback, 4 templates publiés/versionnés, no-bypass + refs valides, validation formules, profils + templates par défaut valides, sécurité, no client data). Suite permanente **367/367 verte** (Phase 1 → P3.2).
- [x] **Validation live** : seed exécuté 2×. Run 1 = 301 créés (59+236+2+4) ; Run 2 = 0 créé, 59 existing + 242 skipped, **compteurs identiques** (59/236/2/4). Lecture API : 59 concepts, 2 profils, 4 templates publiés v1, CA_BS 47 lignes sans bypass (label fr « Trésorerie »), CH_PL 21 lignes avec labels de/it. Legacy `companies`/`employees` HTTP 200. **Données de référence conservées** (production-grade, persistantes).

### 🛑 P3.2 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P3.3 (Gouvernance du mapping de comptes) avant approbation explicite du client.

## P3.3 — Gouvernance du mapping compte→concept — 2026-06 (APPROUVÉ)
> Extension de `mappings.py` + nouveau `mapping_import.py`. Fenêtres effectives **INCLUSIVES** par `financial_period_id`. `unmapped` DÉRIVÉ. Aucune donnée financière normalisée modifiée, aucun moteur de calcul, zéro écriture P2/legacy.
- [x] **Fichiers ajoutés** : `core/financial/mapping_import.py`, `scripts/…` (seed inchangé), `tests/test_p3_3_mapping_governance.py`, seeds live `memory/p3_3_smoke_seed.py`. **Modifiés** : `core/financial/mappings.py` (réécrit P3.3), `server.py` (routes étendues), `tests/test_p3_1_reporting_semantics.py` (2 assertions alignées sur convention inclusive + forme coverage), `memory/PRD.md`.
- [x] **Fenêtres effectives inclusives** : `effective_from_period_id` (requis) + `effective_to_period_id` (optionnel, dernier période couvert ; open si null). Validations : périodes appartiennent à la société, `from_seq <= to_seq`. Résolution `_effective_at`: from ≤ seq ≤ to.
- [x] **Cardinalité** : chevauchement de mappings CONFIRMÉS pour un même compte **interdit** (409) ; fenêtres confirmées **non-chevauchantes acceptées** ; suggestions peuvent se chevaucher. Index unique partiel P3.1 **retiré** (drop_index) — cardinalité gérée applicativement (`_plan_confirm`).
- [x] **Supersession explicite** (jamais d'écrasement silencieux) : confirmer un mapping OPEN démarrant après un mapping OPEN existant ferme le précédent au **prédécesseur** (superseded=true, superseded_by, effective_to = prédécesseur) — historique préservé. Tout autre chevauchement = conflit 409.
- [x] **États** : suggested/confirmed/rejected. Manuel (workspace admin) peut créer un confirmed directement (règles conflit/fenêtre appliquées). Rejet préserve l'historique ; rejet d'un confirmed interdit (409, utiliser supersession).
- [x] **Résolution déterministe** `resolve_confirmed_mapping(account_id, period_id)` : renvoie **exactement un** confirmé effectif (y compris supersédé pour l'historique) ou None ; **≥2 effectifs = erreur d'intégrité 500** (jamais de choix arbitraire).
- [x] **Coverage** (dénominateur = comptes actifs normalisés ; inactifs exclus) : total_active_accounts, confirmed_accounts, unmapped_accounts, suggested_only_accounts, rejected_only_accounts, coverage_percentage, fully_mapped, détails unmapped (id/code/name). **Matérialité optionnelle** via TB (mapped/unmapped_balance_abs, materiality_coverage_percentage, critical_unmapped_count) — n'empêche jamais la coverage de base si TB absente.
- [x] **Bulk-confirm** : items par mapping_id ou paire compte/concept ; validation par item, `dry_run` (preview sans écriture), conflits DB + intra-lot détectés, résultat déterministe par item (confirmed/error+raison) — **pas de succès partiel caché**.
- [x] **Import Excel/CSV** : `preview → commit`. Preview **n'écrit rien** (valide compte/concept/agrégat/périodes/doublons/conflits/confirmés existants → valid/warnings/errors/existing_affected). Commit **suggested par défaut** (source=excel), **idempotent** (dédoublonnage), confirmed possible seulement en action explicite workspace-admin avec toutes les lignes valides ; bloque si erreurs de preview (422).
- [x] **Readiness P3.4** : `mapping-readiness` → `reporting_mapping_ready` (0 unmapped) + coverage + couverture de concepts vs template standard (couverts/manquants). **Aucun calcul d'état, aucune formule exécutée.**
- [x] **Sécurité** : écriture/confirm/reject/bulk/import = workspace admin ; lecture coverage/mappings = membre autorisé (principal/collaborator/company-admin/company-user) ; admin company-local = **lecture seule** (write 403) ; platform_role sans membership refusé ; cross-workspace 404.
- [x] **Logs** : `account_mapping.{suggested|confirmed|rejected|superseded|bulk_confirmed|imported}` (workspace/company/account/mapping/concept/fenêtre/acteur). Aucun log sur lecture.
- [x] **Tests** : `test_p3_3_mapping_governance.py` **34/34** (manuel, cardinalité, périodes, gouvernance, coverage+matérialité, bulk, import, résolution+intégrité, sécurité). Suite permanente **401/401 verte** (Phase 1 → P3.3).
- [x] **Validation live** (3 comptes + 2 périodes temporaires, société A) : coverage 0%→33.33%→100% ; suggestion n'améliore PAS le confirmé ; confirmation améliore ; readiness True à 100% ; supersession FP1→FP2 (historique 2 lignes) ; import preview valid=2/errors=2 **sans écriture** ; commit suggested created=2 puis **idempotent** (skipped=2) ; legacy `companies` 200, **0 écriture TB**, 59 concepts intacts ; **baseline nettoyée**.

### 🛑 P3.3 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P3.4 (Moteur de reporting P&L/Bilan) avant approbation explicite du client.

## P3.4 — Moteur de reporting (P&L + Bilan) + report_runs immuables — 2026-06 (APPROUVÉ)
> `core/financial/reporting_engine.py` + collection `report_runs`. **Jurisdiction-neutre** (CA/CH via templates, aucune branche de calcul). Source numérique = TB normalisée P2.5 ; seuls les mappings **confirmés** P3.3 alimentent. Signes de présentation dans la couche reporting uniquement. Aucun eval(). Aucune écriture P2/legacy (seul `report_runs` écrit) ; aucun cutover.
- [x] **Fichiers ajoutés** : `core/financial/reporting_engine.py`, `tests/test_p3_4_reporting_engine.py`, `memory/p3_4_smoke_seed.py`. **Modifiés** : `server.py` (routes reports + index startup), `memory/PRD.md`.
- [x] **Sélection TB** : dernier import `completed`/`completed_with_warnings` (échec exclu), override `normalized_import_id`, exposé dans les métadonnées ; TB absente → 422 contrôlé.
- [x] **Résolution mapping** : `resolve_confirmed_mapping` par compte effectif à la période ; suggested/rejected ignorés ; ≥2 confirmés = intégrité 500 ; compte renseigné non mappé bloque la génération (preview tolère via `allow_incomplete`).
- [x] **Agrégation concepts** : somme TB→concept confirmé ; agrégat référencé résolu récursivement à ses feuilles descendantes **dédupliquées** (jamais de double comptage). `net = debit-credit` préservé.
- [x] **Signes de présentation** : `value` (magnitude arithmétique, base_mult par concept_type) vs `presented_value` (display_sign natural/positive/negative/inverted) vs `raw_value` (net brut) — TB jamais mutée. Revenu crédit -500 → présenté +500 ; charge +60000 → +60000 ; contra en négatif.
- [x] **Exécution template** : section/concept/subtotal/formula/spacer ; **évaluateur de formules sûr** (descente récursive, grammaire `+ - ( )` + refs de line_code) ; fail-closed sur référence inconnue / auto-référence / cycle / syntaxe invalide / codes dupliqués.
- [x] **P&L** : measure period|ytd (override requête, sinon ligne) ; Gross Profit/EBITDA/EBIT/PBT/Net income via formules. **Bilan** : valeurs cumulées (ytd) ; **contrôle d'équation** assets/liabilities/equity/balance_difference/is_balanced (tolérance 0,01), aucune écriture d'équilibrage.
- [x] **Résultat de l'exercice** : Bilan rapporté **exactement** depuis la TB mappée (pas d'injection auto du Net Income) ; diagnostic croisé `pnl_net_income` vs `mapped_current_year_result` + différence (informatif, aucune auto-correction).
- [x] **report_runs** : snapshot immuable (workspace/company/statement/FY/période/template_id+code+version/tb_import_id/mapping_snapshot/concepts_version/locale/measure/computed_lines+labels/control_totals/diagnostics/generated_by/at/status=final). **Immuable** (pas de PATCH), régénération = nouveau run, GET renvoie le stocké **sans recalcul**.
- [x] **Multilingue** : labels résolus (locale → défaut juridiction → en → line_code) et **figés** dans le run.
- [x] **Sécurité** : preview/lecture = membre autorisé ; generate/finalize = workspace admin ; company-local admin = preview/lecture seule ; platform_role sans membership refusé ; cross-workspace 404. **Logs** : `report.generated` / `report.generation_failed`.
- [x] **Tests** : `test_p3_4_reporting_engine.py` **21/21** (formules, sélection TB, signes, P&L period/ytd, bilan équilibré/déséquilibré, agrégat parent sans double comptage, unmapped bloquant, suggested ignoré, intégrité multi-confirmés, immuabilité/reproductibilité, sécurité, no-write). Suite permanente **422/422 verte** (Phase 1 → P3.4).
- [x] **Validation live** (société A, données temporaires balancées) : CA P&L NET=200 (label fr « Chiffre d'affaires »), CA Bilan A700=L200+E500 équilibré, diagnostic croisé pnl=cyr=200 (diff 0) ; **CH** mêmes données → NET=200 (label de « Betrieblicher Ertrag ») = **neutralité prouvée** ; génération finalisée (tb_import + version + 21 lignes) ; **immuabilité** (mapping muté → run stocké NET toujours 200) ; **blocage** compte renseigné non mappé → 422 ; legacy `companies` 200 ; **baseline nettoyée** (0 report_run, 59 concepts intacts).

### 🛑 P3.4 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P3.5 (Templates custom) avant approbation explicite du client.

## P3.5 — Templates de reporting custom (P&L + Bilan) — 2026-06 (APPROUVÉ & IMPLÉMENTÉ)
> `core/financial/custom_templates.py` (nouveau) + collection `reporting_template_defaults`. **Réutilise strictement** le schéma P3.1 (`reporting_templates`/`reporting_template_lines`), la grammaire de formules sûre P3.4 (importée, jamais réécrite) et le moteur générique P3.4 (aucun « moteur custom »). Aucune écriture P2/legacy ; mappings en lecture seule ; templates système inviolables.
- [x] **Fichiers ajoutés** : `core/financial/custom_templates.py`, `tests/test_p3_5_custom_templates.py`. **Modifiés** : `core/financial/reporting_engine.py` (exécution `semantic_bypass` via `account_refs` + résolution template par défaut, additif et gardé), `server.py` (endpoints P3.5 + import + index startup), `memory/PRD.md`.
- [x] **Cycle de vie** : draft (éditable) → published (immuable) → archived (lecture historique, non sélectionnable par défaut). Évolution d'un publié = **nouvelle version** (v+1), l'ancienne version jamais mutée.
- [x] **Portées** : `workspace` (toutes sociétés du workspace) / `company` (société unique). Système = référence globale lecture seule. Cross-workspace = 404 (no-leak).
- [x] **Dérivation** : draft depuis template système / workspace / company (accès permis) ; copie la structure ; stocke `based_on_template_id` + `based_on_template_version` ; modifications du parent **n'affectent pas** le dérivé.
- [x] **Sémantique-first** : ligne → concept(s). `semantic_bypass=true` (custom uniquement) → `account_refs` requis, concepts exclus sur la ligne, avertissement stocké/exposé, compatibilité sémantique réduite/none. Système : bypass interdit. Comptes bypass validés par appartenance société.
- [x] **Upload Excel/CSV** : `preview → validation → commit en DRAFT` (jamais de publication auto). Colonnes : line_code, parent_line_code, line_type, label_fr/en/de/it, concept_codes, formula, display_sign, measure, account_codes, semantic_bypass. Preview **n'écrit rien** ; commit **idempotent** sur retry (draft existant renvoyé).
- [x] **Édition draft** : add/update/reorder/remove ; mutation d'un publié rejetée (409).
- [x] **Validation de publication (fail-closed)** : line_code requis/unique, parents valides, line_type valide, concepts valides/actifs & état cohérent, formules (grammaire + refs connues + pas d'auto-ref + pas de cycle), display_sign/measure valides, règles bypass, comptes existants & société correcte, template financier non vide, statement_type valide. Diagnostics : template_valid/publishable, concept_coverage, semantic_bypass_count, semantic_compatibility, formula_errors, hierarchy_errors.
- [x] **Templates par défaut** (`reporting_template_defaults`) : défaut société **> ** défaut workspace **> ** fallback juridiction système. Présentation uniquement — `financial_data_source` inchangé.
- [x] **Intégration P3.4** : templates custom publiés (P&L & Bilan) exécutés par le moteur générique (preview + generate). `report_run` fige la version du template ; un ancien run reste inchangé après publication d'une nouvelle version. Lignes bypass exécutées déterministiquement (agrégation directe des comptes, sans bloquer la génération).
- [x] **Multilingue** : labels fr/en/de/it embarqués, fallback locale→…→line_code, figés dans le report_run.
- [x] **Sécurité** : workspace admin = create/derive/edit/publish/archive/defaults/upload ; membres autorisés = lecture des templates publiés ; **admin local société = lecture seule** ; platform_role sans membership refusé ; cross-workspace 404 ; écriture template système via P3.5 interdite (403).
- [x] **Logs** : `reporting_template.{created|derived|updated|uploaded|published|archived|default_changed}` (workspace/company/template/code/version/statement/acteur). Aucun log sur lecture.
- [x] **Tests** : `test_p3_5_custom_templates.py` **32/32** (création/dérivation/portée/draft/validation/bypass/upload CSV+Excel/publish+versioning/defaults/i18n/sécurité/intégration P3.4 + reproductibilité inter-versions/no-write). Suite permanente en mémoire **454/454 verte** (Phase 1 → P3.5).
- [x] **Validation live** (société A) : liste templates système (CA/CH) ; dérivation CA standard (21 lignes, 15 concepts, compat « full ») ; validate publishable ; publish v1 ; défaut société posé ; new-version v2 (draft) ; immuabilité publiée (add line → 409) ; **artefacts de test nettoyés** (0 template custom résiduel).

### 🛑 P3.5 IMPLÉMENTÉ. STOP — NE PAS DÉMARRER P3.6 (Moteur Cash Flow) avant approbation explicite du client.

## P3.5.b — Refonte page de connexion + Google Auth + réinitialisation mot de passe — 2026-06 (IMPLÉMENTÉ & TESTÉ)
> Refonte fidèle au design fourni. Backend : nouveaux endpoints d'auth (coexistent avec email/mot de passe). Frontend : SPA à rendu conditionnel (pas de react-router) — callback Google géré dans `AuthContext`, page `/reset-password` gérée dans `Shell`.
- [x] **Fichiers ajoutés** : `frontend/src/lib/token.js`, `frontend/src/components/ResetPassword.js`, `frontend/public/login-hero-wave.jpg` (généré). **Modifiés** : `server.py` (auth: remember, Google session, forgot/reset password), `frontend/src/components/Login.js` (refonte complète), `frontend/src/App.js`, `frontend/src/context/AuthContext.js`, `frontend/src/context/LanguageContext.js`, `frontend/src/lib/api.js`.
- [x] **Design** : panneau sombre à vague verte (logo, « En toute clarté. », grille 3 features Données protégées/Accès sécurisé/Journal d'audit, encart confidentialité, copyright) + panneau blanc (sélecteur FR/EN/DE/IT, « Bon retour. », courriel/mot de passe avec icônes + œil, « Se souvenir de moi » + « Mot de passe oublié ? », bouton vert, séparateur, Google + Microsoft, footer conditions).
- [x] **Google Auth (Emergent)** : `POST /api/auth/session` échange le `session_id` côté serveur (`/auth/v1/env/oauth/session-data`), crée/lie l'utilisateur (`auth_provider=google`, sans password_hash), émet le JWT maison + cookie. Redirect frontend dérivé de `window.location.origin` (jamais hardcodé).
- [x] **Réinitialisation mot de passe** : `forgot-password` (réponse générique anti-énumération, email Resend, lien `<FRONTEND_URL>/reset-password?token=`), `reset-password` (JWT type=reset 1h, **usage unique** via `reset_token_jti`, min 6 car.). Comptes Google (sans mot de passe) exclus.
- [x] **Se souvenir de moi** : persistance réelle — token en `localStorage` (coché) ou `sessionStorage` (décoché) ; cookie `max_age` conditionnel.
- [x] **Langues** : FR/EN/DE/IT sélectionnables ; seules FR/EN traduisent l'UI (DE/IT → FR).
- [x] **Microsoft** : bouton présent, non implémenté (« bientôt disponible »).
- [x] **Tests** : backend validé par curl (login remember, Google 401 sur id invalide, forgot générique, reset valide/usage unique/invalide 400) ; frontend **11/11 scénarios** (testing agent `iteration_55.json`) — login, erreur, œil, langues, forgot inline, Google redirect, Microsoft notice, remember local/session, reset avec/sans token + validations. Design conforme (capture).

- [x] **Passe fidélité (spec EMERGENT_PROMPT_FR_ONLY)** : split 64/36, fond navy CSS `#001a35` (radial+linéaire), **ruban SVG** en « V/vague » (dégradé #00344d→#27c98c, glow), **graphique décoratif SVG** bas-droite (aria-hidden), tokens couleurs exacts (green #00b978, yellow #ffb900), logo compact icône + « meelora » (sans slogan), bouton pill dégradé vert, champs 60px bord #d8e0ea, callout confidentialité en cercle, langue FR verte + chevron / EN/DE/IT navy. Rendu 1920×1080 conforme à `meelora login page.png` (capture). Logique/handlers/testids inchangés.

- [x] **Logo officiel exact** : à partir de « Meelora logo dark mode (FR).webp », le slogan a été retiré (effacement région droite-bas + recadrage `getbbox`) → `frontend/public/meelora-wordmark-white.png` (icône M dégradée + point jaune + mot-symbole « meelora » minuscule dans la police de marque exacte). Affiché à `w-[212px] self-start` dans le panneau navy — fidèle à `meelora login page.png`.

- [x] **Fond officiel + split 60/40** : image de fond fournie appliquée telle quelle (`frontend/public/login-bg.png` — navy + ruban « V » vert + graphique décoratif) via `bg-cover bg-center` ; split passé à `lg:grid-cols-[60%_40%]`. SVG ruban/graphique reconstruits retirés. Fidèle au design fourni.

- [x] **Spec finale approuvée** : split ramené à **64/36** (`lg:grid-cols-[64%_36%]`), logo officiel agrandi à `w-[320px]` (~330px @1920), fond dédié fourni conservé (`login-bg.png` — navy + ruban V vert + graphique), tokens/typo conformes. Rendu 1920×1080 fidèle à la référence approuvée. Auth inchangée.

## P3.6 — Moteur de flux de trésorerie (méthode INDIRECTE) — 2026-06 (APPROUVÉ, IMPLÉMENTÉ & TESTÉ)
> `core/financial/cash_flow.py` (nouveau). Moteur jurisdiction-neutre réutilisant TB P2.5, concepts P3.2 (`cash_flow_category`), mappings confirmés P3.3, primitives P3.4 (`_aggregate`, `select_tb_import`, `_eval_formula`). Aucun moteur séparé, aucune écriture financial-core/legacy (seuls templates CF système + report_runs + logs).
- [x] **Méthode indirecte** : Résultat net (flux période) + réintégrations non-cash (DEPRECIATION/AMORTIZATION) + variations du BFR = exploitation ; + investissement + financement = variation nette de trésorerie ; + trésorerie d'ouverture = trésorerie de clôture.
- [x] **Périodes** : mouvement période courante vs période précédente via `financial_period.sequence` ; séquence 1 → dernière période de l'exercice précédent ; sinon diagnostic `not_available` contrôlé (jamais de solde d'ouverture inventé).
- [x] **Trésorerie** : CASH_AND_CASH_EQUIVALENTS ; réconciliation exposée (opening/net_change/expected_ending/actual_ending/difference/reconciled, tolérance 0.01), aucun ajustement d'équilibrage.
- [x] **BFR** : signe unifié `cash_effect = prior_net − cur_net` (actif↑=sortie, passif↑=entrée) ; trésorerie exclue. Signes testés.
- [x] **Investissement / financement** : mouvements de solde indicatifs → `manual_required=true` (pas de CAPEX ni de flux de dette fabriqués) ; statut `incomplete` si présents ou réconciliation non équilibrée.
- [x] **Règles CF** : couche système jurisdiction-neutre (constantes Python, jamais sur les mappings).
- [x] **Templates CF système** : `CA_PRIVATE_ENTERPRISE_STANDARD_CF` + `CH_CO_SME_STANDARD_CF` (présentation multilingue uniquement, même noyau de calcul). Templates CF custom différés (hors scope P3.6).
- [x] **report_runs** : `statement_type=cash_flow`, immuables (période, comparaison, template/version, TB courant+comparaison, mapping snapshot, cash_flow_rules, computed_lines, opening/ending cash, réconciliation, diagnostics, labels). Reproductibilité historique prouvée.
- [x] **preview / generate** : preview sans run ; generate = run immuable. Sécurité : membre=preview/read, workspace admin=generate, admin local=read-only, platform_role seul=refus, cross-workspace=404.
- [x] **Endpoints** : `POST /api/companies/{id}/reports/cash-flow/preview` & `/generate`. Seed CF branché dans `/api/system/reporting-seed` (plateforme).
- [x] **NO CUTOVER / NO WRITE** : `financial_data_source` inchangé ; accounts/TB/journal/mappings/périodes/legacy `acct_*`/`qc9434_*` intacts (prouvé en tests).
- [x] **Tests** : `test_p3_6_cash_flow.py` **23/23** ; régression P3.1→P3.6 **155/155** (testing agent `iteration_56.json`, backend 100%, aucun défaut). Endpoints live auth-gated, 4xx contrôlés (pas de 500), cross-workspace 404.
- [x] **Validation live** : la DB preview n'a pas ≥2 périodes de TB normalisée → chemin diagnostic validé en mémoire (données déterministes) ; endpoints live confirmés opérationnels et sécurisés.
- [x] **Limites** : investissement/financement = mouvements nets (manual_required) ; méthode directe hors scope ; gouvernance de templates CF custom différée.

### 🛑 P3.6 IMPLÉMENTÉ & TESTÉ. STOP — NE PAS DÉMARRER P3.7 avant approbation explicite du client.

## P3.7 — Comparatifs & Reporting de gestion — 2026-06 (APPROUVÉ, IMPLÉMENTÉ & TESTÉ)
> `core/financial/comparatives.py` (nouveau). Construit AU-DESSUS des moteurs approuvés : P&L/BS recalculés via P3.4 (`preview_report`) pour chaque période avec le MÊME template courant (comparabilité structurelle) ; CF via P3.6 (`preview_cash_flow`). Variances objectives (aucune interprétation favorable/défavorable). Aucune écriture financial-core/legacy ; runs immuables à la finalisation.
- [x] **Modes** : `prior_period` (période précédente), `prior_year` (même séquence fiscale de l'exercice précédent — non-calendaire), `ytd` (YTD vs YTD année précédente). Résolution par `financial_years/periods.sequence` ; absence → `not_available` (jamais deviné).
- [x] **Variance** : `amount = cur − comp` ; `percent = amount/abs(comp)*100` ou **null** si dénominateur 0 (jamais Infinity/NaN), avec `variance_status`.
- [x] **P&L** : mois vs mois précédent, mois vs année précédente, YTD vs YTD ; même structure de lignes, même template pour les deux périodes.
- [x] **Bilan** : période courante vs précédente / année précédente ; équation du bilan validée indépendamment par période (`current_balanced`/`comparison_balanced`).
- [x] **Cash Flow** : comparatif via P3.6 ; qualité incomplète/`manual_required` remontée honnêtement (jamais masquée).
- [x] **Diagnostics de comparabilité** : `mapping_changes_detected`, `template_change_detected`, `source_incomplete`, `fully_comparable` ; contextes de mapping courant/comparaison exposés (mappings résolus par période, jamais forcés).
- [x] **Reporting de gestion** : composition en sections (executive_summary, pl_comparative, balance_sheet_comparative, cash_flow_summary, notes) — pas de nouvelle source financière, pas de narration IA. Point d'attache notes/commentaires réservé (compatibilité seulement).
- [x] **report_run** : `report_kind` ∈ {comparative_pl, comparative_bs, comparative_cf, management}, snapshot immuable (périodes, imports TB, template/version, mapping evidence, valeurs courant+comparaison, variances, labels, diagnostics). Reproductibilité prouvée.
- [x] **Multilingue** : labels résolus via i18n P3.4/P3.5 (fr/en/de/it + fallback), figés dans le run.
- [x] **Endpoints** : `POST /api/companies/{id}/reports/comparative/{preview,generate}` & `/management/{preview,generate}`. Logs via `report.generated` (report_kind, périodes, template/version, acteur).
- [x] **Sécurité** : membre=preview/read, workspace admin=generate, admin local=read-only, platform_role seul=refus, cross-workspace=404.
- [x] **NO CUTOVER / NO WRITE** : `financial_data_source` inchangé ; financial-core & legacy intacts (prouvé).
- [x] **Tests** : `test_p3_7_comparatives.py` **16/16** ; régression P3.1→P3.7 **171/171** ; smoke API live **8/8** (testing agent `iteration_57.json`, backend **100%**, 0 défaut). Fichier live ajouté : `tests/test_p3_7_live_api.py`.
- [x] **Limites** : Budget/Prévision non implémentés (extension future) ; méthode directe CF hors scope ; commentaires legacy non migrés (compat seulement) ; variances numériques live non exerçables (DB preview sans ≥2 périodes TB) → validées en mémoire.

### 🛑 P3.7 IMPLÉMENTÉ & TESTÉ. STOP — NE PAS DÉMARRER P3.8 (KPI Engine) avant approbation explicite.

## P1.13A — ACCESS & IDENTITY FOUNDATION V2 (2026-06)
Infrastructure d'accès backend uniquement. AUCUNE modification financière, AUCUNE refonte UI, P1.13B NON démarré. Modèle en couches : Identité → Membership → Entitlement → Accès Module → Permission → Scope → Assignation → Accès Effectif. Deny-by-default (fail-closed). Le backend reste l'autorité de sécurité.

**Principe clé** : IDENTITÉ ≠ AUTORISATION. Un compte auto-inscrit ne reçoit AUCUN workspace/société/rôle/module automatiquement. Email/domaine ne donnent jamais d'accès. ADMINISTRATEUR ≠ AUTORITÉ FINANCIÈRE (un admin gère les accès mais n'obtient aucune autorité de saisie/clôture/finalisation sans permission explicite). PLATEFORME ≠ SOCIÉTÉ (`platform_role` ne donne jamais d'accès client).

**Fichiers ajoutés** :
- `core/access/__init__.py`, `modules.py` (registre REPORTING/ACCOUNTING/FIXED_ASSETS/CONSOLIDATION + échelle none/read/contribute/manage), `permissions_catalog.py` (~37 permissions sensibles stables), `entitlements.py` (workspace_module_entitlements + company_module_enablement + seed Meelora), `module_access.py` (user_module_access + user_permissions), `scopes.py` (consolidation_group_scopes + workflow_assignments + politiques PO/SoD), `activation.py` (jetons activation/remplacement Client Admin à usage unique), `log_scope.py` (platform_logs séparés + scopes workspace/company), `effective_access.py` (résolveur central `resolve_effective_access`), `indexes.py`.
- `scripts/migrate_p1_13a_access.py` (dry-run-first, conservateur, sans escalade).
- `tests/_fake_access_db.py`, `tests/test_p1_13a_access_model.py`, `tests/test_p1_13a_effective_access.py`, `tests/test_p1_13a_activation_logs.py`.

**Fichiers modifiés** : `server.py` (imports P1.13A ; routes : GET /api/access/modules, GET /api/access/permissions, GET/PATCH /api/workspace/module-entitlements, GET/PUT /api/companies/{cid}/module-enablement, GET/PUT /api/companies/{cid}/users/{uid}/module-access, PUT .../permissions/{code}, GET .../effective-access ; startup : ensure_indexes accès + seed entitlements Meelora idempotent).

**Nouvelles collections** : workspace_module_entitlements, company_module_enablement, user_module_access, user_permissions, consolidation_group_scopes, workflow_assignments, client_admin_activations, platform_logs.

**Autorités** : entitlements PATCH = `require_platform_manager` (plateforme/commercial) ; enablement société = admin workspace ; module-access/permissions utilisateur = `require_company_local_admin` (admin workspace OU admin local company_user). Client Admin ne peut jamais accorder un module non souscrit (409) ni un platform_role.

**Compatibilité P1.12** : `company_access` et `users.workspace_id` PRÉSERVÉS (non destructif). Résolveur lit company_memberships avec pont legacy company_access. `permissions.py` legacy intact.

**Seed Meelora** : les 4 modules entitled (active) pour le workspace Meelora — DISPONIBILITÉ seulement, aucun octroi utilisateur automatique.

**Migration** : dry-run exécuté (rapport : 0 entitlement à activer [déjà seedés], 2 user_module_access read dérivés sur ACCOUNTING pour la société Meelora utilisée, 0 rapporté, 0 permission sensible, 0 'manage'). NON appliqué (dry-run only, décision utilisateur).

**Tests** : 44 tests P1.13A permanents (100%). Régression in-memory : phase1 + P1.12 + P2 + P3.1→P3.7 = 189/189. Validation live via curl : identité sans accès → refus ; membership sans module → contexte OK mais module indisponible ; read accordé → effectif ; permission entry_post requise et accordée → effective ; 4 entitlements Meelora confirmés. Enregistrements de test nettoyés.

**Dépendances legacy identité restantes** : `company_access` (pont lecture), `users.workspace_id` (contexte tenant), `require_company_access` admin-bypass legacy (pour routes financières existantes uniquement — le nouveau résolveur ne fait PAS de bypass admin). À retirer en phase ultérieure.

### 🛑 P1.13A IMPLÉMENTÉ & TESTÉ. STOP — NE PAS DÉMARRER P1.13B (User Lifecycle & Admin Replacement) ni refonte UI avant approbation explicite.

## P1.13B — USER LIFECYCLE & ADMIN REPLACEMENT (2026-06)
Cycle de vie utilisateur backend uniquement (aucune refonte UI, P1.13C/D NON démarrés). Aucune donnée/formule financière touchée. Aucun accès financier automatique (l'activation ne crée qu'une relation organisationnelle).

**Fichiers ajoutés** : `core/access/lifecycle.py` (invitation → activation → provisioning de membership) ; `tests/test_p1_13b_lifecycle.py`.
**Fichiers modifiés** :
- `core/access/activation.py` : `intent` sur les jetons, `peek_activation_token` (validation sans consommation), `revoke_user_sessions`, purposes `workspace_invitation`/`company_invitation`, `replace_client_admin` (désactive l'ancien membership, révoque ses sessions, réutilise/prépare l'identité, intent = admin société).
- `core/access/log_scope.py` : écriture de log plateforme = action serveur interne (gate `platform_role` seulement en lecture).
- `server.py` : `create_token` ajoute `iat` ; `get_current_user` **révoque effectivement** tout JWT émis avant `session_revoked_at` ; helpers email (`_send_invitation_email`, `_send_admin_notice_email`, `_activation_link`) ; routes.

**Nouvelles routes** :
- `GET /api/auth/activation/{token}` (public, aperçu sans consommation)
- `POST /api/auth/activate` (public — l'utilisateur choisit son propre mot de passe, auto-login)
- `POST /api/workspace/invitations` + `GET /api/workspace/invitations` (admin workspace)
- `POST /api/companies/{cid}/client-admin/replace` (admin workspace OU platform_admin)

**Sécurité** : jeton à usage unique + expiration (48 h) ; aucun mot de passe permanent défini/visible par un admin ; réutilisation d'identité existante par email (clé d'identité) ; révocation JWT effective de l'ancien admin (401 immédiat) ; notifications email au nouvel admin + aux admins workspace ; logs plateforme (`client_admin.replaced`) et client (`company_admin.replaced`) séparés par contexte.

**Tests** : 9 tests P1.13B in-memory (100%) ; régression in-memory (phase1 + P1.12 + P3.5→P3.7 + P1.13A/B) = 150/150. Validation live e2e via curl : invitation société → aperçu → activation (mot de passe choisi) → login OK → remplacement admin → **ancien token révoqué (401)** → logs plateforme + client enregistrés. Tous les artefacts de test nettoyés (5 users, 0 `session_revoked_at` résiduel).

**Reporté (hors périmètre P1.13B, ne pas démarrer sans approbation)** : page frontend `/activate` (appartient au travail UI) ; P1.13C/D ; refonte UI.

### 🛑 P1.13B IMPLÉMENTÉ & TESTÉ. STOP — page UI d'activation et P1.13C/D en attente d'approbation explicite.

## P1.13C — ACCESS ADMINISTRATION & LIFECYCLE GOVERNANCE (2026-06)
Gouvernance backend/API uniquement pour la future UI de gestion des accès. AUCUNE refonte UI, migration P1.13A conservée en dry-run (non commit), aucun changement financier.

**Fichiers ajoutés** : `core/access/admin_governance.py` ; `tests/test_p1_13c_governance.py`.
**Fichiers modifiés** : `core/memberships.py` (statut `suspended` sur workspace/company memberships) ; `tests/_fake_access_db.py` (matcher notation pointée `metadata.company_id`) ; `server.py` (routes P1.13C + import gouvernance).

**Sécurité (rappel P1.13B)** : `identity_is_verified()` — un email normalisé ne suffit JAMAIS à accorder un accès. La réutilisation d'identité ne provisionne un membership actif qu'après preuve de contrôle via le jeton d'activation (fail-closed). Une identité existante NON vérifiée ne gagne aucun membership actif par simple correspondance d'email (testé).

**Cycle de vie invitation** : statuts pending / accepted / expired / revoked. Services : list (+filtre), view, resend (révoque l'ancien jeton → inutilisable, émet un jeton frais), revoke. **Aucun token brut exposé** dans les API admin (testé).

**Cycle de vie identité/membership** : identité (pending_verification/active/suspended/disabled) distincte du membership (active/suspended/inactive). Suspendre/désactiver une identité pose `status=inactive` + révoque les JWT (401/403 immédiat). Retirer l'accès d'une société n'affecte pas l'identité globale ni les autres sociétés (isolation testée). Réactivation supportée. Aucune suppression physique.

**Administration accès module** : `module_access_matrix` → par module : entitled, company_enabled, assigned_level, effective_level (dérivé UNIQUEMENT via `resolve_effective_access`), sensitive_permissions. Aucune duplication de logique d'accès.

**Explication d'accès effectif** : `explain_effective_access` (admin) → allowed + reason_code + reason FR + facteurs (checks du résolveur). Diagnostic uniquement, aucune fuite d'info tenant non liée.

**Visibilité remplacement admin** : `company_admin_history` → admins actuels, précédents/désactivés, date/acteur du remplacement, statut d'activation du nouvel admin (aucun secret/token/mot de passe).

**Nouvelles routes** :
- `GET /api/workspace/invitations?status=` · `GET /api/workspace/invitations/{id}` · `POST .../resend` · `POST .../revoke`
- `GET /api/workspace/users` · `GET /api/workspace/users/{uid}` · `POST /api/workspace/users/{uid}/identity-status`
- `GET /api/companies/{cid}/users/{uid}/module-matrix` · `GET .../effective-access/explain` · `GET /api/companies/{cid}/admin-history`

**Logs** : événements `user.invited`/`invitation.resent`/`invitation.revoked`/`identity.suspended`/`identity.reactivated`/`module_access.updated`/`user_permission.updated` en logs tenant (contexte workspace/company) ; `client_admin.replaced` en `platform_logs`. Aucun GET journalisé. Pas de flux global d'évènements clients en plateforme.

**Séparation Meelora plateforme/société** : `platform_role` toujours ignoré par le résolveur ; l'administration plateforme d'un employé Meelora reste indépendante de son accès aux modules de la société Meelora.

**Tests** : 13 tests P1.13C (100%). Régression in-memory 168/168 (phase1 + P1.12 + P3.5→P3.7 + P1.13A/B/C). Validation live curl : invitation→list(sans token)→resend(ancien invalidé)→revoke ; users list/detail ; module-matrix ; explain (denied) ; suspend identité→**JWT 403**→réactivation→login OK ; admin-history. Artefacts nettoyés (Julie restaurée, 5 users, 0 activation résiduelle).

**Dépendances legacy restantes** : `company_access` (pont lecture), `users.workspace_id`, route legacy `create_cmp_member`/`create_ws_member` P1.12 (ajout direct par admin avec mot de passe — action explicite, hors flux invitation).

### 🛑 P1.13C IMPLÉMENTÉ & TESTÉ. STOP — NE PAS DÉMARRER P1.13D (UX & Navigation) avant approbation explicite.

## P1.13D — UX & NAVIGATION (ACCESS MANAGEMENT) (2026-06) — PARTIEL
Frontend au-dessus des API P1.13A/B/C. Aucun changement backend d'autorisation, migration P1.13A toujours en dry-run, aucun changement financier.

**Fichiers ajoutés** : `frontend/src/components/Activate.js` (page publique `/activate`), `frontend/src/pages/AccessManagement.js` (console Utilisateurs et accès).
**Fichiers modifiés** : `frontend/src/App.js` (route publique `/activate`), `frontend/src/lib/api.js` (méthodes activation/gouvernance), `frontend/src/components/Layout.js` (nav admin `access` + PAGES).

**Livré & validé** :
- **Page d'activation `/activate`** : états valid/invalid(expiré/utilisé/révoqué)/succès, carte contexte (organisation + objet + email), choix du mot de passe + confirmation, message identité existante, auto-login au succès. Rendu vérifié par capture ; endpoint `/api/auth/activate` validé par curl (token+user+membership).
- **Console « Utilisateurs et accès »** (admin, nav bas) : compteurs (actifs/en attente/expirées), onglets Utilisateurs/Invitations, recherche, assistant d'invitation 3 étapes (personne → société+rôle → revue), fiche utilisateur (cartes module par société, niveaux Lecture/Saisie|Contribution/Gestion, autorisations sensibles groupées en langage métier, suspendre/rétablir), journal d'invitations (renvoyer/révoquer), états vides, libellés FR. Compile proprement, branchée aux API P1.13C testées.

**Reporté (P1.13D restant, non démarré)** : switch de contexte plateforme/société Meelora + navigation par contexte, carte client Meelora (Mandats→Client: Aperçu/Admins/Utilisateurs/Modules/Logs), séparation visuelle des logs plateforme/client, profils préréglés (Comptable, Responsable financier…), assistant d'invitation avec étapes modules/niveaux/permissions complètes, explication « Pourquoi cet accès ? » en UI, wizard de remplacement d'admin en UI, suite de tests frontend dédiée. Le harness de login du screenshot n'a pas progressé (souci de timing) — validation e2e UI complète à refaire.

### 🛑 P1.13D PARTIEL (activation + console de base). STOP — reste de l'UX en attente d'approbation.

## P1.13D — UX ACCESS MANAGEMENT (SUITE, 2026-06)
Tranche 2 : wizard complet + presets + explication + remplacement admin + activation. Backend inchangé sauf ajouts additifs (invite_user_full, application de l'accès planifié à l'activation uniquement si présent ; membership_id dans admin-history). Migration P1.13A toujours en dry-run. Aucun changement financier.

**Livré & validé E2E (testing_agent iter 58 & 59, aucun bug bloquant, retest_needed=False)** :
- Console « Utilisateurs et accès » (nav admin) : stats, onglets Utilisateurs/Invitations/Administrateurs, recherche.
- **Wizard d'invitation complet 4 étapes** : Personne → Société(s) multi → Accès (cartes module, niveaux Lecture/Saisie|Contribution/Gestion, autorisations sensibles groupées en langage métier, **profils préréglés** Lecture seule/Junior/Comptable/Responsable financier/Responsable reporting/Responsable consolidation/Personnalisé) → Résumé → Envoyer. Modules non souscrits non sélectionnables ; « Gestion » n'implique aucune permission sensible. L'accès planifié est appliqué à l'activation (preuve de contrôle via jeton).
- **Sous-filtres d'invitations** (En attente/Acceptées/Expirées/Révoquées/Toutes) + renvoyer/révoquer (aucun token exposé).
- **Fiche utilisateur** : cartes module par société, changement de niveau, attribution/révocation de permission sensible, **« Pourquoi cet accès ? »** (API explain), suspendre/rétablir (avec confirmation), multi-société isolée.
- **Onglet Administrateurs + wizard de remplacement** : conséquences affichées, ancien admin désactivé + sessions révoquées, nouvel admin invité, jamais de mot de passe affiché (backend P1.13B).
- **Page publique `/activate`** : états valid/expiré/utilisé/révoqué/invalide, choix du mot de passe, auto-login (validée iter 58).

**Fichiers** : ajoutés `frontend/src/components/Activate.js`, `frontend/src/pages/AccessManagement.js`, `backend/tests/test_p1_13d_full_invite.py` ; modifiés `frontend/src/App.js`, `frontend/src/lib/api.js`, `frontend/src/components/Layout.js`, `backend/core/access/lifecycle.py` (invite_user_full + application accès planifié), `backend/core/access/admin_governance.py` (membership_id), `backend/server.py` (route invitation full-wizard).

**Tests** : backend in-memory P1.13A/B/C/D = 172/172 verts (dont 4 nouveaux P1.13D). Frontend : testing_agent 2 passes, 100% des assertions fonctionnelles.

**NON livré (reporté, hors tranche)** : contexte plateforme Meelora + switch de contexte, carte client « Mandats → Client » (Aperçu/Admins/Utilisateurs/Modules/Logs/Support), écran Logs plateforme + séparation visuelle complète des logs plateforme/client dans l'UI, suite de tests frontend permanente (Playwright committée), audit a11y complet (warnings Radix DialogTitle/description restants). Ces éléments requièrent une persona platform_admin absente du déploiement mono-workspace actuel.

### 🛑 P1.13D — TRANCHE CLIENT ADMIN + ACTIVATION + REMPLACEMENT LIVRÉE & VALIDÉE. Contexte plateforme/carte client/logs UI reportés. STOP — en attente d'approbation.

## P1.13D.2 — Contexte plateforme Meelora & clôture UX (2026-06 — LIVRÉ & VALIDÉ)
Contexte plateforme STRICTEMENT séparé du contexte société/financier. `platform_role` (platform_admin|support) n'accorde JAMAIS d'autorité financière automatique.
- [x] **Backend — service `core/access/platform_console.py`** (agrégation lecture seule) + endpoints `/api/platform/*` fail-closed (`require_platform_staff`) : `summary`, `clients`, `clients/{ws}` (+ `administrators`, `users`, `modules`, `logs`, `support`), `logs`. La seule action mutante joignable = remplacement d'admin client (endpoint gouverné existant, platform_admin only).
- [x] **Séparation stricte des logs** : `GET /api/platform/logs` = scope plateforme uniquement (types `platform.`/`client.`/`client_admin.`/`support.`) ; `GET /api/platform/clients/{ws}/logs` = logs opérationnels tenant d'UN client (défense en profondeur : les évènements plateforme n'y apparaissent jamais). Aucun flux agrégé « tous clients ».
- [x] **Frontend** — `pages/Platform.js` : `PlatformHome` (bannière + 4 stats + clients récents), `PlatformClients` (recherche + liste → fiche), `ClientCard` (6 onglets : Aperçu, Administrateurs avec assistant de remplacement, Utilisateurs, Modules, Logs tenant, Support), `PlatformLogs`. Onglets/Modules/Utilisateurs en lecture seule (aucune autorité financière depuis la plateforme).
- [x] **Bascule de contexte** dans `Layout.js` (`ContextSwitcher`, visible si `platform_role`) : « Administration plateforme » ⇄ « Société Meelora ». Nav plateforme (Accueil/Mandats-Clients/Logs plateforme) vs nav financière ; en-tête masque année/badge budget/sélecteur société en contexte plateforme. Persistance `localStorage meelora:ctx`.
- [x] **Correctif** `/auth/login` renvoie désormais le payload complet (`auth_me_payload`, avec `platform_role`) → la bascule apparaît immédiatement après connexion.
- [x] **Seed** identités de test : `platform@meelora.com/platform123` (platform_admin + adhésion distincte société Meelora) et `support@meelora.com/support123` (support, plateforme seule). Idempotent au démarrage.
- [x] **a11y** : `aria-describedby={undefined}` sur les DialogContent sans description (AccessManagement) ; nouveaux dialogues plateforme avec `DialogDescription`.
- [x] **Suite Playwright E2E permanente** `/app/frontend/e2e/` (14 tests verts) : bascule de contexte, nav plateforme, fiche client 6 onglets, séparation des logs, assistant d'invitation, round-trip d'activation, multi-société, sécurité fail-closed (403). Lancer : `cd /app/frontend && npx playwright test --config=e2e/playwright.config.js`.
- [x] **Validation** : `testing_agent` iteration_60 → 100 % (backend 18/18, frontend 8/8), aucun défaut. `platform_role` refusé sur `/api/logs` (workspace-admin only) = confirmation qu'il n'ouvre aucune autorité financière.
- **Règle inchangée** : migration P1.13A reste en `--dry-run` (NE PAS committer sans autorisation) ; aucun calcul financier modifié.


## P1.13E — Persona & UX Security Sign-off (2026-06 — TERMINÉ, aucune fonctionnalité métier)
Audit de bout en bout de l'identité/accès/UX avec 8 personas + tests négatifs + revue du dry-run P1.13A. Aucun code financier modifié.
- [x] **Personas A–H** seedés (idempotent, `scripts/seed_p1_13e_personas.py`) et validés via 3 canaux : matrice résolveur sur DB réelle (`scripts/p1_13e_signoff.py`), pytest permanent `tests/test_p1_13e_persona_matrix.py` (12/12), Playwright `e2e/persona-ux.spec.js`.
- [x] **Invariants prouvés** : platform_role ≠ autorité financière (A) ; admin ≠ autorité financière (C) ; `manage` n'implique jamais une permission sensible (E period_reopen refusé) ; permissions granulaires (D ne peut ni poster ni clôturer) ; isolation par société (G posting seulement sur 9434) ; scope groupe consolidation (H group_beta refusé) ; suspension révoque tout ; cross-workspace = no-leak (404, aucune énumération).
- [x] **Tests négatifs HTTP fail-closed** : `/api/platform/*` = 403 pour non-plateforme ; `/api/logs` = 403 pour platform_admin (aucune autorité financière/log) ; société sans accès = 403 ; société inexistante = 404 ; Client Admin limité aux membres de SA société.
- [x] **Séparation Meelora** : Administration plateforme ≠ Société Meelora — bascule claire, aucune fuite de navigation/données/logs. **Logs** : `/api/platform/logs` (scope plateforme) et `/api/platform/clients/{ws}/logs` (tenant) distincts ; aucun flux agrégé cross-client.
- [x] **Dry-run P1.13A** (NON committé) : 0 entitlement à activer (déjà seedés) ; 6 accès `read` conservateurs dérivés d'adhésions actives sur une société en usage (julie, marc + 4 personas) ; **0 manage**, **0 permission sensible**, **0 accès dérivé de platform_role**, **0 cross-workspace**, **0 entitlement implicite** ; legacy company_access/users.workspace_id préservés.
- [x] **testing_agent iteration_61 : 100 %** (backend 12/12 + négatifs HTTP + matrice A–H ; frontend UX A–H). 0 BLOCKER, 0 HIGH.
- [x] **Correctif mineur** : réalignement des tests legacy périmés `test_ccq_rules.py` (garde 2,08×250=520 $, valeur PRD 2026-07-10) — aucun code/formule financière modifié.
- **Anomalie MEDIUM (différée, non bloquante)** : routes financières legacy (/api/budget*, /api/acct*, /api/employees*) pas encore câblées à `resolve_effective_access` (modèle de rôle P1.10 conservé) → gating par module non appliqué côté legacy. Travail futur explicite ; sans impact sur le nouveau modèle ni la migration.
- **GATE** : **P1.13 ACCESS FOUNDATION: READY** — **P1.13A MIGRATION RECOMMENDATION: SAFE TO COMMIT** (attendre l'autorisation explicite ; NE PAS exécuter `--commit`).


## P1.13E (finalisation) — Sidebar dynamique + gating modules + registre 5 modules (2026-06 — LIVRÉ & VALIDÉ)
Refonte navigation/gating/sécurité, AUCUNE fonctionnalité métier, AUCUN calcul financier modifié.
- [x] **Registre canonique 5 modules** : REPORTING, BUDGETS, ACCOUNTING, FIXED_ASSETS, CONSOLIDATION (`core/access/modules.py`). PAYROLL NON créé (masse salariale = 1er sous-domaine de BUDGETS). Entitlement BUDGETS auto-seedé (workspace Meelora).
- [x] **Sidebar dynamique** (`Layout.js` `DynamicCompanyNav`) pilotée par `GET /api/companies/{cid}/navigation` (`core/access/navigation.build_company_navigation`). Plus aucun menu métier basé sur `user.role`. Module visible = entitlement ∩ enablement ∩ user_access. Recalcul immédiat au changement de société (`GET /api/me/company-context`, tri par pertinence).
- [x] **Vue de gestion Admin** (option B.a) : admin workspace/société voit les modules souscrits+activés (`admin_view`) ; overlay n'accorde JAMAIS de permission sensible → ADMIN ≠ AUTORITÉ FINANCIÈRE.
- [x] **Gating routes legacy** (middleware + `authorize_module`) : /api/acct,/api/qc9434→ACCOUNTING ; /api/budget,/api/employees,/api/hypotheses,/api/departments,/api/reports→BUDGETS ; GET=read, écriture=contribute ; cross-workspace=404. Correctif de la faille P1.13E (reporting-only→/api/budget désormais 403).
- [x] **Placeholders** REPORTING/FIXED_ASSETS/CONSOLIDATION (`ModulePlaceholder.js`). Dashboard tolère 403 (dégradation gracieuse).
- [x] **Décision documentée** : `/api/reports` (rapports budgétaires) classé BUDGETS (respect exigence O). REPORTING commercial = module dédié à page placeholder (à mapper sur une UI concrète quand son domaine de données sera tranché).
- [x] **Utilisateurs existants NON seedés** (décision H) : sidebar minimale si aucun grant (comportement conservateur voulu).
- [x] **Tests** : pytest 149 (dont `test_p1_13e_navigation.py` 16, `test_p1_13e_persona_matrix.py` 12) ; Playwright 24/24 ; `scripts/p1_13e_signoff.py` (nav+gating live) vert ; `testing_agent` iteration_62 = 100 % (28/28 backend, 7 personas + placeholders + multi-société), 0 BLOCKER/HIGH.
- **Dry-run P1.13A (5 modules, NON committé)** : 5 entitlements présents ; 7 accès `read` ACCOUNTING conservateurs (membres d'une société en usage) ; 0 manage, 0 permission sensible, 0 accès via platform_role, 0 cross-workspace, 0 entitlement implicite. Legacy préservé.
- **GATE** : **P1.13 ACCESS FOUNDATION: READY** — **P1.13A MIGRATION: SAFE TO COMMIT** (attendre autorisation ; `--commit` NON exécuté).
- **Pré-existant (LOW, hors périmètre)** : 5 tests financiers périmés dans `test_backend.py` (échouent aussi sur le code d'origine, vérifié par git stash) — code financier NON modifié.


## P1.13E (nav V2) — Distinction Meelora/Client/Mandat (2026-06 — LIVRÉ & VALIDÉ)
Modèle : **Client → Tous les mandats → Mandat → Modules**. Vocabulaire distinct par contexte. Aucune fonctionnalité métier / calcul financier modifié.
- [x] **Sidebar plateforme** = Tableau de bord + **Sociétés / Clients** uniquement (Logs plateforme retiré du menu ; renommage local au contexte plateforme).
- [x] **Page Sociétés / Clients** : carte **Meelora interne** en 1er (fond vert, badge « Société interne », bouton « Accéder » → bascule contexte Société Meelora) ; clients externes → fiche admin/support (ClientCard).
- [x] **Contexte client** : vocabulaire « Tous les mandats ». Accueil (Dashboard) conservé + bannière « Espace client » avec bouton principal **Accéder** (`client-home-access`) → `mandats_list`. Entrée sidebar « Tous les mandats » → même écran (2 chemins).
- [x] **Page `MandatsList`** (`mandats_list`) : cartes des sociétés accessibles (`mandat-card-<id>`) + bouton **Accéder** (`mandat-access-<id>`). « Accéder » = définit le mandat actif, recalcule la sidebar métier via accès effectif, ouvre le tableau de bord du mandat. Indicateur « Mandat actif » dans la sidebar.
- [x] **Mono-mandat** conserve l'architecture (mandat auto-sélectionné mais « Tous les mandats » toujours accessible pour le retour).
- [x] **NavContext** (`context/NavContext.js`) : `go`, `enterMandat`, `enterCompanyContext`, `activeCompanyId`, `companies`.
- [x] **Durcissement `GET /api/companies/{cid}/navigation`** : 404 si société inexistante/cross-workspace ; 403 si le caller (non-admin) n'a ni membership ni company_access ; aucune fuite de modules sur refus. `GET /api/me/company-context` trie par pertinence (has_modules).
- [x] **Validation** : Playwright **25/25** ; `testing_agent` iteration_63 (frontend 100 %, 2 HIGH backend nav guard) → corrigés → iteration_64 **backend 100 %, retest_needed False**. 0 BLOCKER/HIGH ouvert.
- **Rappels** : migration P1.13A reste `--dry-run` (NON committée) ; ClientCard (fiche client externe) non E2E-testée ici faute de client externe dans l'environnement (attendu).


## Nav V3 — Employé Meelano entrée directe (2026-06 — #1 LIVRÉ & TESTÉ)
- [x] #1 Employé Meelora sans platform_role: aucun menu plateforme; "Tous les mandats" masqué en mono-mandat (companies.length<=1); entrée directe sur le 1er module (ACCOUNTING->Comptabilite, REPORTING->reporting_home...) au lieu d un dashboard budget vide. Playwright 25/25.
- [ ] #2 Formulaire creation societe/client COMPLET (identification, coordonnees, fiscalite conditionnelle par juridiction/province [Canada: BN/TPS/TVQ; autres provinces sans TVQ], operationnel). Architecture extensible multi-juridictions. Aucun champ fiscal ne confere de droit. -> A FAIRE (prochaine iteration).
- [ ] #3 Fiche "Societe Meelora" (Apercu/Admins/Users/Modules/Logs/Parametres) + bouton Acceder en mode EXTENSION (conserver menus plateforme + AJOUTER modules metier, ne pas remplacer la nav). -> A FAIRE (refonte du modele context-switch vers extension).
- Rappels: migration P1.13A reste --dry-run (NON committee); aucun calcul financier modifie.



## P1.13E — Sign-off complémentaire sécurité & UX (2026-06)
Rapport complet : `/app/RAPPORT_P1_13E.md`. **Aucune migration appliquée** (`--commit` NON exécuté), P3.x non repris.
- **REPORTING vs legacy /api/reports (doc seule)** : `/api/reports` = rapports budgétaires legacy → gaté **BUDGETS** (inchangé). REPORTING (module commercial) = reporting financier normalisé (Bilan, P&L, Flux, report_runs, états financiers, dashboards, analyses/variances, diffusion externe) servi via `/api/acct/*` + `core/financial/*` — moteurs **non modifiés**. Décision : ne pas assimiler REPORTING au legacy /api/reports.
- **Navigation hiérarchique** : conforme (plateforme = Tableau de bord + Sociétés/Clients ; carte Meelora 1re/verte/Accéder → contexte Société ; client = « Tous les mandats » + Accéder par mandat → recharge entitlements + droits effectifs → sidebar métier). **Ajout « Logs plateforme » à la sidebar plateforme (choix client 1.b)**, strictement scopé plateforme. `Layout.js` `NAV_PLATFORM` (3 items).
- **Preuves E2E** : nouvelle spec `e2e/nav-hierarchy.spec.js` (3 tests : flux Meelora, flux A→B avec **preuve isolation A↛B**, isolation API). 2 tests `platform-context.spec.js` adaptés (Logs = menu scopé). **Suite complète : 28/28 verts.**
- **Migration P1.13A — 7 grants explicites (à valider AVANT commit)** : 7× read ACCOUNTING sur Meelora, dérivés de `company_membership` actifs. Script `scripts/p1_13a_grant_details.py` (lecture seule). Invariants confirmés : 0 manage auto · 0 permission sensible auto · 0 via platform_role (cas platform@ dérive de son adhésion société) · 0 cross-workspace · 0 BUDGETS implicite (ajout du 5e module ne crée aucun grant).
- **Permissions sensibles (P1.13F recommandé)** : catalogue existant (`permissions_catalog.py`) mais **pas encore câblé** sur les routes d'action sensibles (clôture/réouverture = `require_admin` ; extourne legacy = accès société + verrou ; réconciliation = lecture seule/diagnostic ; post GL générique = non disponible). Sous-phase dédiée à activer quand ces opérations seront réelles dans le nouveau module Comptabilité.

### En attente / prochaines étapes
- **Validation utilisateur** des 7 lignes P1.13A, puis autorisation explicite pour `--commit`.
- P1.13F (câblage permissions sensibles) — sur décision.
- P3.x — non repris (sur demande).


## P1.13E — Refonte navigation (extension) + formulaire société complet (2026-06)
Rapport : `/app/RAPPORT_P1_13E.md` (§5 + tableau 7 grants). `--commit` NON exécuté, P3.x non repris. Suite E2E **28/28 verte**.
- **Employé SANS platform_role** : sidebar = uniquement ses modules métier (entrée générique « Tableau de bord » retirée ; dashboard budgétaire rattaché à BUDGETS via `MODULE_PAGES`/`ModulesNav`). Landing = **Comptabilité prioritaire si ACCOUNTING**, sinon 1er module ; multi-mandats → « Tous les mandats ».
- **Employé AVEC platform_role — modèle EXTENSION** (remplace la bascule de contexte). Sidebar plateforme = Tableau de bord · Sociétés / Clients · **Société Meelora** · Logs plateforme. « Société Meelora → Accéder » (`enterMeelora`) **ajoute** les modules réellement autorisés SANS retirer les menus plateforme. `platform_role` = 0 module (extension vide pour platform@). `ContextSwitcher` supprimé.
- **Formulaire « Créer une société / client »** (`Companies.js`) : sections Identification / Adresse / **Fiscalité conditionnelle** / Paramètres / Modules souscrits / Administrateur. Modèle fiscal **extensible par juridiction** (`TAX_FIELDS`) : CA → BN/TPS/TVQ(QC)/PST(BC,SK,MB) ; CH → UID/TVA. Backend `core/companies.py` : `CompanyCreate/Update` étendus (trade_name, entity_type, business_number, adresse complète, country, phone/email, language, subscribed_modules, admin_email, `tax_profile` permissif) + `public_company`.
- Fichiers E2E : `nav-hierarchy.spec.js`, `platform-context.spec.js` (réécrit extension), `persona-ux.spec.js`, `security.spec.js`, `company-form.spec.js` (nouveau). `helpers.js` nettoie `meelora:accessed`/`activeCompany`.
- Scripts (lecture seule) : `scripts/p1_13a_grant_details.py` (7 grants + invariants).

### En attente
- **Validation explicite des 7 grants P1.13A** avant `--commit`.
- P1.13F (câblage permissions sensibles) ; P3.x — sur décision.

## P1.13E — Ajustements finaux (vocabulaire + admin identity) (2026-06)
- **Sidebar plateforme** : « Sociétés / Clients » renommé **« Tous les mandats »** (vue des sociétés clientes). Sidebar plateforme = Tableau de bord · Tous les mandats · Société Meelora · Logs plateforme.
- **Admin création société** : endpoint `GET /api/access/admin-candidate?email=` (classe verified/absent/unverified via `admin_governance.identity_is_verified`). Formulaire propose Associer (vérifié) / Inviter (absent) / Activation requise (non vérifié). L'action réutilise `POST /workspace/invitations` ou `POST /companies/{id}/members` — jamais d'accès auto sur simple email. Aucun 2e mécanisme d'identité.
- Tests : `company-form.spec.js` étendu (lookup identité). Suite 28/28 verte. `--commit` P1.13A toujours NON exécuté.

## P1.13E — Interface plateforme finale (3 menus + audit logs) (2026-06)
- Sidebar plateforme = EXACTEMENT 3 menus : Tableau de bord · Sociétés / Clients · Logs plateforme (ancré en bas via mt-auto + séparateur). Société Meelora RETIRÉE comme menu ; gérée depuis Sociétés/Clients (carte 1re, verte, badge Société interne, Accéder). Aucun module financier en sidebar plateforme. (`Layout.js` NAV_PLATFORM 2 + NAV_PLATFORM_LOGS)
- Société Meelora → Accéder → page `platform_meelora_manage` = console `AccessManagement` (users/invitations/module levels/sensitive/effective). N'ajoute aucun module, aucune autorité financière. Client externe → Accéder → ClientCard (fiche admin). (`Platform.js` PlatformMeeloraManage)
- Logs plateforme = outil d'audit : recherche texte + filtres (type/résultat/acteur/dates/catégorie) + contenu enrichi (acteur+rôle, ressource, résultat, before/after, IP, user-agent, request_id, motif) + REDACTION serveur des secrets. Isolation plateforme/client préservée. (`core/access/log_scope.py`, `/platform/logs`, `PlatformLogs`)
- Tests : `platform-context.spec.js` (réécrit), `platform-logs.spec.js` (nouveau). Suite 33/33 verte. Seed : 4 logs plateforme + client externe démo (`ws_demo_clientabc`).
- P1.13A `--commit` toujours NON exécuté. Aucun calcul financier modifié.

## P1.13E — Création société (plateforme) + changement d'email de connexion (2026-06)
- **Création société/client plateforme** : bouton « + Nouvelle société / client » (visible platform_admin) dans Sociétés/Clients ouvrant le formulaire complet. Gating backend `require_company_creator` sur POST /companies (workspace admin OU platform_admin) ; support/client user → 403. (`server.py`, `Platform.js`, `Companies.js` export CompanyForm + createCompanyWithAdmin)
- **Changement d'email de connexion** (opération sensible, non hardcodé) : `POST /me/email-change/request` + `/confirm` (token JWT email_change + jti, vérification de la nouvelle adresse via Resend/fallback, unicité, ancienne active jusqu'à validation). Rôles/memberships/permissions inchangés. Journalisé (platform.config before/after). UI : Préférences → carte « Courriel de connexion » [Modifier]. (`server.py`, `Preferences.js` EmailChangeCard, guard platform autorise `preferences`)
- Tests : `platform-context.spec.js` (bouton + gating), `email-change.spec.js` (round-trip A↔B, ancienne refusée, rôle inchangé). Seed : compte jetable `emailchange_demo@accslegro.com`. **Suite 36/36 verte.**
- P1.13A `--commit` toujours NON exécuté. Aucun calcul financier modifié.

## P1.13E — Cycle de vie société : Modifier / Rendre inactive / Réactiver (2026-06)
- **Feature** : gestion du cycle de vie d'une société directement dans « Sociétés / Clients » (aucune suppression physique — données conservées). Boutons par carte : Modifier, « Rendre inactive » (confirmation explicite via `deactivate-dialog`/`deactivate-confirm`), « Réactiver ». Filtre statut Toutes/Actives/Inactives (`company-status-filter`). La société interne Meelora (`legacy_prefix == "acct"`) ne peut PAS être désactivée via l'UI. Une société inactive bloque l'accès opérationnel (`isActive` désactive le bouton « Accéder »).
- **Bug corrigé (P0)** : la réactivation renvoyait **404** — `update_company_for_admin` (chemin admin workspace) passait par `require_company_admin` → `require_same_workspace` qui filtre les sociétés actives (`_active_company_filter`), rendant une société inactive introuvable. Correctif ciblé dans `core/companies.py` : lookup scoping workspace SANS filtre actif/inactif pour le cycle de vie (garde `role==admin` + isolation cross-tenant conservées). Chemin `platform_admin` inchangé. Aucun autre endpoint impacté (garde opérationnelle 404 sur société inactive intacte ailleurs).
- Tests : `company-lifecycle.spec.js` (filtre + désactivation avec confirmation + réactivation) vert. **Suite E2E complète 37/37 verte.** Vérifié aussi via curl (deactivate 200 → reactivate status=active). P1.13A `--commit` toujours NON exécuté ; aucun calcul financier modifié.

## P1.13E — Motif de désactivation obligatoire + historique de statut (2026-06)
- **Motif obligatoire** à la désactivation : `POST/PATCH /companies/{id}` renvoie **400** si `status→inactive` sans `status_reason` non vide. Réactivation : motif optionnel. Champ `status_reason` ajouté à `CompanyUpdate` (max 500). UI : dialogue de statut avec textarea `status-reason` (bouton confirmer désactivé tant que vide pour la désactivation). Motif affiché sur la carte de la société inactive (`company-reason-<id>`).
- **Historique de statut** (`status_history` sur le doc société, `$push`) : chaque transition (désactivation ET réactivation) trace `at` (horodatage), `from`, `to`, `by_id`, `by` (email acteur), `reason`. Exposé via `public_company`. UI : bouton `company-history-<id>` ouvrant `status-history-dialog` (liste anti-chronologique : statut→statut, date, acteur, motif). Journalisé aussi dans `log_action` (détail + motif) et Logs plateforme (metadata `reason`) pour comptes plateforme.
- Tests : `company-lifecycle.spec.js` étendu (motif obligatoire → bouton désactivé, désactivation+motif, réactivation via dialogue, historique 2 entrées). Vérifié curl (400 sans motif, historique from→to+acteur+motif). **Suite E2E 37/37 verte.** P1.13A `--commit` toujours NON exécuté ; aucun calcul financier modifié. STOP sur ce périmètre.

## P1.13A — Règle de migration corrigée : preuve d'accès métier legacy (2026-06)
- **Décision utilisateur** : la migration ne doit JAMAIS déduire un accès module d'un `company_membership` actif + société utilisant le module. **Membership ≠ Module Access.** Un grant exige une **preuve d'accès métier legacy réel** (P1.10 `company_access`) + module réellement utilisé. Cas ambigus → `none`. Comptes `persona_*` (fixtures P1.13E) → aucun grant. `platform@` (platform_role) → aucun module métier automatique (attribution explicite via gestion des accès si besoin).
- **Correctif** (`scripts/migrate_p1_13a_access.py`, `p1_13a_grant_details.py`) : l'étape 2 itère désormais le `company_access` legacy (au lieu de `company_memberships`), exclut tout utilisateur `platform_role`, exige un module réellement utilisé par la société ; sinon reporté en `none`. Aucune écriture (dry-run only).
- **Dry-run corrigé** : `user_module_access (read) = 2` — **Julie (ACCOUNTING/read)** + **Marc (ACCOUNTING/read)** sur Meelora. Exclus : Marc@9434 (aucun module), platform@ (platform_role), persona_clientadmin@9434 (aucun module) ; persona_reporting/consol/budgets = aucun `company_access` → aucun grant. Invariants : 0 manage · 0 permission sensible · 0 via platform_role · 0 par membership seul · 0 cross-workspace · 0 BUDGETS implicite.
- **`--commit` NON exécuté.** En attente de validation ligne par ligne. **P1.13F non démarré.** Sociétés de test « ZZ » nettoyées.

## P1.13A — MIGRATION APPLIQUÉE (--commit) — 2026-06
- **Autorisation utilisateur** : 2 grants validés explicitement (Julie + Marc → ACCOUNTING/read). Commit exécuté avec sauvegarde préalable, journalisation Platform Logs, garde de sécurité (allowlist stricte), confirmation invariants, smoke sécurité et vérification d'invariance financière.
- **Scripts** : `backup_p1_13a.py` (dump JSON des collections d'accès/identité + snapshot compteurs financiers), `migrate_p1_13a_access.py --commit --actor-email` (garde allowlist Julie/Marc ACCOUNTING/Meelora → abort si divergence ; écrit platform log `platform.migration`), `smoke_p1_13a.py` (accès effectif via API réelle).
- **Résultat** : `user_module_access` 11 → 13 (+2). Seule collection modifiée. Grants : Julie ACCOUNTING/read + Marc ACCOUNTING/read sur Meelora (created_by=migration_p1_13a).
- **Invariants confirmés post-commit** : 0 manage · 0 permission sensible (collection user_permission_grants absente) · 0 via platform_role · 0 par membership seul · 0 cross-workspace · 0 BUDGETS implicite.
- **Smoke sécurité (API réelle)** : AVANT → tous AUCUN ACCOUNTING ; APRÈS → Julie=read(user_access), Marc=read(user_access), platform@=AUCUN, persona_reporting/consol/budgets=AUCUN. No-leak intact (société inconnue 404, Julie→9434 403).
- **Invariance financière** : snapshots before/after IDENTIQUES (acct_periods 20, acct_bv 19, acct_ledger 19, journal 1953, employees 123, departments 26, hypotheses 1). Aucune donnée/formule financière modifiée.
- **Audit** : platform log `platform.migration` (timestamp, acteur platform@meelora.com, script+version v2-legacy-company_access, grants_applied, invariants). Backups : `/app/backend/backups/p1_13a_*_before|after/`.
- **P1.13F non démarré** (attente validation du rapport post-migration).

## P1.13E — Sociétés / Clients (portefeuille plateforme) : 3 correctifs (2026-06)
- **#1 Modifier une société** : chaque carte du portefeuille plateforme affiche Accéder + **Modifier** ; la fiche société détaillée propose aussi Modifier. Modifier ouvre le `CompanyForm` en mode édition (préremplи) → `PATCH /api/companies/{id}`. Autorité backend inchangée : `require_company_creator` (platform_admin OK ; support/client user → 403) + journalisation before/after via `log_action`. Bouton Modifier masqué si non platform_admin.
- **#2 9434 visible** : cause = `Companies.js`/vue plateforme filtrait par `company_memberships` de l'utilisateur (platform@ n'a de membership que sur Meelora → 9434 masquée). Correctif : la vue plateforme « Sociétés / Clients » (`PlatformClients`) liste désormais le **registre complet des sociétés** via nouveau `GET /api/platform/companies` (indépendant des memberships du caller ; platform staff only). Société interne Meelora en 1re position, puis clients (9434…), filtre Toutes/Actives/Inactives. Utilise la société 9434 existante (aucun seed/doublon).
- **#3 Utilisateurs de la fiche** : nouvel onglet Utilisateurs de la fiche société via `GET /api/platform/companies/{cid}/members` : source = `company_memberships` de CETTE société (priorité) + pont legacy `company_access` en transition ; identité depuis `users` global. Affiche nom, email, statut identité, type/rôle de membership, statut de membership, modules attribués + niveau. Sections Administrateurs / Actifs / Suspendus. Scoping strict company_id → aucun utilisateur d'une autre société ne fuit. Cross-workspace/no-leak inchangé.
- Backend : `platform_console.list_platform_companies` + `company_members` (réutilisent `_user_by_id`/`_identity_view`). Routes `/api/platform/companies` et `/api/platform/companies/{cid}/members` (require_platform_staff). Code mort workspace (`ClientCard` + onglets) retiré de Platform.js.
- Tests : nouveau `e2e/platform-companies.spec.js` (5) + `platform-context.spec.js` adapté. **Suite E2E complète 42/42 verte.** Vérifié curl : portefeuille = Meelora+9434, membres 9434=17 (dont modules), Meelora=11 sans fuite, PATCH platform_admin 200 / support 403.

## P1.13F — Sensitive Financial Permissions Hardening (2026-06)
- **Objectif** : câbler les actions financières sensibles RÉELLES sur `resolve_effective_access` + permissions explicites, sans toucher aux calculs. Chaque action vérifie : module access + permission sensible explicite + company scope + membership + société active. `manage`/admin seul ne suffit JAMAIS.
- **Garde réutilisable** : `core/access/sensitive.py::require_sensitive_permission` (fail-closed ; cross_workspace/inconnu → 404 no-leak ; autres refus → 403).
- **Routes câblées (réelles)** :
  - `PATCH /companies/{cid}/financial-periods/{id}` : statut→closed/locked ⇒ `accounting.period_close` ; réouverture/déverrouillage ⇒ `accounting.period_reopen` ; édition métadonnées (sans statut) conserve le contrôle admin. `require_company_admin` interne retiré de `update_financial_period` (autorité déplacée au garde route).
  - `POST /companies/{cid}/imports/journal/commit` ⇒ `accounting.entry_post`.
  - `POST /qc9434/invoices` ⇒ `accounting.customer_invoice_post`.
  - `POST /qc9434/invoices/{iid}/reverse` (extourne) ⇒ `accounting.entry_reverse`.
- **Non câblé (routes pas encore réelles)** : réconciliation (routes GET diagnostiques en lecture seule uniquement), `accounting.po_approve` (aucune route PO), `accounting.supplier_invoice_post` (aucune route fournisseur générique). Documenté, non fabriqué.
- **Tests** : `backend/tests/test_p1_13f_sensitive.py` — matrice positive/négative pour les 5 permissions + manage-insuffisant + cross-workspace + no-membership + société inactive (18/18 PASS). Curls HTTP réels : julie (read, sans perm) journal commit → 403 (permission_not_granted) ; société inconnue → 404 ; création facture 9434 → 403. **Suite E2E complète 42/42 verte.** Aucune formule financière modifiée.
- STOP après rapport. P3.x non repris.

## P1.13F — Vérification UI accès + audit + événements de refus (2026-06)
- **Règle architecturale définitive** : niveau module ≠ permission sensible. `manage`/company admin/platform admin ne suffisent JAMAIS. `require_sensitive_permission` = garde central pour toute future opération sensible.
- **UI P1.13D vérifiée** : la gestion des accès utilise le vrai catalogue P1.13F (`GET /access/permissions`) et octroie/révoque **par société** via `PUT /companies/{cid}/users/{uid}/permissions/{code}`. Aucun second système d'autorité : `PERM_GROUPS` (frontend) = libellés UX uniquement ; 0 code hors catalogue (vérifié). `accounting.entry_reverse` (câblé P1.13F) ajouté à l'UI (était manquant) → les 5 permissions câblées sont octroyables.
- **Audit grant/revoke** (`user_permission.granted`/`revoked`) : acteur, utilisateur cible, société, permission, avant/après, horodatage (changes + metadata). Vérifié via curl.
- **Événement de sécurité sur refus** : `security.sensitive_denied` dans `security_events` — structuré (actor, company, permission, reason), **coalescé sur fenêtre 60s** (anti-bruit : 3 refus → 1 doc count=3), **aucune donnée financière**. Émis par `require_sensitive_permission`, fail-safe (n'interrompt jamais la requête).
- **Routes futures non créées artificiellement** : réconciliation (reconciliation_manage/approve), po_approve, supplier_invoice_post devront utiliser le même garde lors de leur implémentation réelle.
- Tests rejoués : backend matrice 18/18 PASS + **E2E 42/42 verte**. Aucune logique/formule financière modifiée.

## ACCOUNTING A1 + A2 (2026-06)
### A1 — Accounting Shell & Navigation
- Sidebar société : Comptabilité rendue en **accordéon** (NavParent) avec 15 sous-menus : Aperçu, Ventes & Clients, Achats & Fournisseurs, Bons de commande, Banque & Trésorerie, Écritures comptables, Grand livre, Balance de vérification, Plan comptable, Analytique & Projets, Taxes, Actifs & amortissements, Clôture & Réconciliation, Imports & Migration, Rapports & Analyses. Écrans non développés = placeholders propres (`AcctPlaceholder`). Visibilité pilotée par le manifest P1.13 (gating module).
- Menu avatar : Profil / Administration (admin) / Sécurité / Langue (bascule FR/EN).
- Fichiers : `pages/AccountingA1.js`, `components/Layout.js` (MODULE_NAV.ACCOUNTING type "accordion", NAV_ACCT_A1, PAGES/MODULE_PAGES).
### A2 — Core GL & Posting Workflow (module ISOLÉ)
- Collections dédiées `gl_periods` / `gl_entries` — zéro impact legacy (acct_*/qc9434_* inchangés).
- Écriture : draft → submitted → approved → posted → reversed. Écritures équilibrées (débits=crédits), source traçable, pièces jointes, audit complet par transition.
- Permissions : draft/submitted = ACCOUNTING contribute ; approved = **accounting.entry_approve** (NOUVELLE permission sensible) + **maker-checker** (créateur ≠ approbateur, jamais contourné par manage/admin/platform_admin) ; posted = accounting.entry_post ; reversed = accounting.entry_reverse. Tout via `require_sensitive_permission`.
- Périodes : open → locked → closed (+ déverrouillage locked→open). `closed` TERMINAL : réouverture **définitivement interdite** pour tous. `accounting.period_reopen` **déprécié** (retiré du catalogue exposé + UI ; route legacy financial-periods renvoie 410 sur réouverture). Locked bloque la comptabilisation. Comptabilisation séquentielle : impossible de poster dans une période si une période antérieure n'est pas clôturée. Correction post-clôture = écriture dans une période ultérieure.
- Routes : `/api/companies/{cid}/gl/periods` (+transition), `/gl/entries` (+submit/approve/post/reverse). Fichiers : `core/accounting/gl.py`, routes dans `server.py`, `core/access/sensitive.py::require_module_level`.
- Architecture : module isolé, aucune dépendance obligatoire inter-module, pas de duplication ; AR/AP/PO/banque = placeholders (non fonctionnels dans cette tranche).
- Tests : `backend/tests/test_a2_gl.py` (19/19 : lifecycle, équilibre, maker-checker, verrouillage, clôture terminale, séquentiel, extourne, audit) ; gating HTTP (contribute/approve/post/reverse + cross-workspace 404) ; `test_p1_13f_sensitive.py` MAJ (period_reopen retiré). E2E `accounting-a1.spec.js` (4) — **suite complète 46/46 verte**. Aucune régression P1.13. Aucun calcul financier legacy modifié.

## Alignement A2 ↔ Cœur financier P2 (2026-06) — avant A3
Refonte de persistance de l'Accounting A2 pour consommer le Cœur financier normalisé (P2) au lieu de systèmes modernes parallèles. AUCUN legacy (acct_*/qc9434_*) touché ; aucune migration.
- **Périodes** : suppression totale de `gl_periods`. Le workflow Accounting consomme directement `financial_periods` (P2.2) comme **source canonique** (référence `financial_period_id`). `gl.list_periods` lit `financial_periods` (alias `code` ← `period_code`) ; création de période autonome supprimée (route `POST /gl/periods` → **410**, l'UI sélectionne une période existante générée via l'exercice + périodes mensuelles du Cœur financier).
- **Règles de période portées sur la source canonique** : `_ALLOWED_TRANSITIONS` de `periods.py` rendu **closed = terminal** (`closed → {closed}`) — réouverture historique P2.2 (closed→open) supprimée pour tous. Transitions : open↔locked, open→closed, locked→closed. Un seul état-machine partagé par le Cœur financier ET l'Accounting.
- **Écritures** : `gl_entries` renommé `accounting_entries` (document/workflow pré-posting : draft/submitted/approved + provenance/pièces/approbations, maker-checker inchangé). Au **POST** → création d'**exactement UNE** écriture canonique `journal_entries` + `journal_entry_lines` (P2.6, `source_system="accounting"`, `net=debit-credit`), liée par `journal_entry_id` immuable. **POST idempotent** (idempotence garantie par l'index unique `(source_system, external_id)` + court-circuit si déjà posté). Comptes résolus best-effort contre `accounts` (P2.3) sans bloquer le posting.
- **Extourne** : crée une NOUVELLE `accounting_entry` (posted) + un NOUVEAU `journal_entries` lié à l'original (`reverses_journal_entry_id`) ; l'écriture comptabilisée d'origine n'est **jamais mutée** (seul un back-reference non financier `reversed_by_journal_entry_id` est ajouté). Traçabilité bidirectionnelle workflow ⇄ journal.
- **Helpers** ajoutés dans `core/financial/journal.py` : `create_workflow_journal_entry(...)` (idempotent, période OPEN requise), `link_reversal(...)`. `public_entry` journal expose désormais `reverses_journal_entry_id` / `reversed_by_journal_entry_id`.
- Données A2 de dev `gl_*` supprimées (repartir propre).
- **Tests** : `test_a2_gl.py` réécrit (33 checks : pas de duplication de périodes, `financial_period_id` canonique partout, draft/submit/approve n'écrit pas au journal, POST = 1 écriture canonique, retry idempotent, extourne liée + original intact, traçabilité 2 sens, locked/closed bloquent le posting, période suivante bloquée si précédente non closed, acct_*/qc9434_* inchangés) — **ALL PASS**. Régressions vertes : P2.2 périodes 22/22 (closed terminal), P2.6 journal 37/37, P1.13F sensitive ALL PASS, E2E `accounting-a1.spec.js` 4/4. Routes live vérifiées (GET /gl/periods → 200 lit financial_periods ; POST /gl/periods → 410).
- **STOP** — A3 non démarré (en attente de validation utilisateur).

## Correction navigation/UX société — panneau flottant & console Plateforme (2026-06)
Correction de navigation/UX pure (aucun moteur financier ni droit backend modifié ; composition côté frontend à partir du manifest/effective access P1.13).
- **Section ADMINISTRATION retirée de la sidebar société** : « Sociétés/Clients », « Utilisateurs et accès », « Logs » ne sont plus dans la sidebar. Les fonctions admin autorisées (« Utilisateurs et accès » → `access`, « Logs » → `logs`) passent dans le **menu avatar → Administration**, piloté par `manifest.admin_view` (jamais par `user.role`).
- **Sociétés/Clients = console Plateforme uniquement** : le cycle de vie société (désactiver/réactiver + **motif obligatoire** + **historique de statut**) a été **migré** de l'env société (`CompaniesPage`, désormais hors navigation) vers la console Plateforme (`PlatformClients`) — testids `company-deactivate/reactivate/history-{id}`, `deactivate-dialog`, `reactivate-dialog`, `status-history-dialog`, `company-reason-{id}`. `platform_admin` uniquement.
- **Sélecteur de mandat compact** : affiché **uniquement une fois entré** dans un mandat (jamais sur « Tous les mandats »). En-tête sidebar « MANDAT ACTIF <nom> ▾ » (`mandat-switcher`/`active-mandat-name`) → liste des mandats accessibles + « Tous les mandats » en dernier. Mono-mandat = libellé statique. **Fail-closed** au changement : le manifest précédent est vidé (aucun module résiduel pendant le chargement).
- **Navigation par panneau flottant (popover) — remplace les accordéons** : la sidebar reste compacte (modules racines seulement). Clic sur un module → **panneau flottant à droite** (Radix Popover, `side=right`, scroll interne `max-h-85vh`) ; re-clic/clic ailleurs/Échap ferme ; sélection d'un sous-menu navigue + ferme ; un seul panneau ouvert à la fois ; module + sous-menu actifs mis en évidence. Composant réutilisable `ModuleFlyout` (`nav-module-{CODE}` trigger, `flyout-{CODE}` contenu, `nav-{key}` sous-items). Comptabilité groupée en **Opérations / Comptabilité / Contrôle & analyse** (15 sous-menus A1). Immobilisations, Consolidation, Budgets, Reporting adoptent le même composant (Budgets : « Tableau de bord » → enfant **« Aperçu »**, fonctionnalités inchangées ; placeholders ajoutés pour FA/Consolidation/Reporting).
- **Composition Reporting/Accounting** (règle de navigation, codes canoniques distincts) : ACCOUNTING présent ⇒ REPORTING masqué comme module racine (capacités dans Comptabilité → Rapports & Analyses) ; REPORTING seul ⇒ module autonome ; les deux ⇒ seul Comptabilité affiché. Aucune permission sensible inférée, backend reste l'autorité.
- **Teardown E2E** : `scripts/cleanup_e2e_companies.py` + `e2e/global-teardown.js` (wired dans `playwright.config.js`) suppriment les sociétés « ZZ * » après la suite. 4 sociétés « ZZ Lifecycle Test » résiduelles nettoyées.
- **E2E** : specs mis à jour (accounting-a1 popover, nav-hierarchy, persona-ux, access-flows via avatar, company-form + company-lifecycle migrés Plateforme). **Suite complète 46/46 verte**, teardown confirmé.

## ACCOUNTING A3 — Ventes & Clients (Accounts Receivable) (2026-06)
Module AR isolé, branché sur le Cœur financier P2 (périodes P2.2, journal P2.6, comptes P2.3) et sur deux primitives partagées nouvelles (FX + moteur fiscal). Aucun legacy (acct_*/qc9434_*) touché ; aucune migration. **Aucun second grand livre** : chaque comptabilisation crée UNE écriture canonique via le helper A2.
- **Primitive FX partagée** `core/financial/fx.py` : collection `exchange_rates` (taux + date + source), `get_rate`/`convert`, snapshot immuable par transaction (aucun taux courant ne réécrit l'historique). Le journal canonique est TOUJOURS équilibré en devise fonctionnelle ; les montants en devise de transaction voyagent en métadonnées (`txn_debit`/`txn_credit`/`txn_currency` sur les lignes, `transaction_currency`/`fx` sur l'en-tête).
- **Moteur fiscal réutilisable versionné** `core/financial/tax_engine.py` : `sales_tax_codes` avec `tax_kind` (taxable/zero_rated/exempt) et **versions par date d'effet** ; taux jamais codés en dur ; défauts par juridiction extensibles (CA-QC GST 5%+QST 9,975%, CA-ON HST, CA-BC GST+PST, CH TVA 7,7%→8,1% versionnée) ; snapshot fiscal figé sur chaque facture. Moteur déterminé par juridiction+config, réutilisable par Achats plus tard.
- **Modèle de données** (`sales_*`) : `sales_customers` (devise + code taxe par défaut + `credit_balance`), `sales_invoices`, `sales_payments`, `sales_credit_notes`, `sales_customer_credits`, `sales_gl_mapping`, `sales_sequences`. Multidevise par conception (devise transaction + snapshot FX ; montants txn ET fonctionnels).
- **Facture** : draft→submitted→approved→posted→(partially_paid)→paid ; **maker-checker** (créateur ≠ approbateur) ; POST (`customer_invoice_post`) → 1 écriture **Dr AR / Cr Produits (par ligne) / Cr Taxes (par composant)** en devise fonctionnelle, lien `journal_entry_id` immuable, **POST idempotent**, numérotation INV-AAAA-####.
- **Encaissement** (`customer_payment_post`) → **Dr Banque / Cr AR** (AR soldé au taux d'origine) + **écart de change réalisé** (Gain FX PL_FXGAIN / Perte FX PL_FXLOSS) quand le taux de paiement diffère.
- **3 concepts distincts** (jamais confondus) : **VOID** (extourne complète d'une facture posted NON payée, écriture miroir liée, `entry_reverse`) ; **note de crédit** commerciale totale/**partielle** (document AR autonome, propre numéro CN-AAAA-####, workflow draft→submitted→approved→posted, maker-checker, `customer_credit_note_approve`/`customer_credit_note_post`, réutilise le snapshot fiscal+FX d'origine, garde-fou anti-sur-crédit par ligne, si facture déjà payée → **crédit client disponible**) ; **remboursement** monétaire modélisé (crédit client), workflow cash-out différé.
- **Permissions sensibles** ajoutées au catalogue P1.13F : `customer_invoice_approve`, `customer_payment_post`, `customer_credit_note_approve`, `customer_credit_note_post` (+ `customer_invoice_post` déjà présent). Gating via `require_sensitive_permission` (aucune autorité implicite admin/manage). ACCOUNTING = 14 permissions.
- **Routes** `/companies/{cid}/ar/*` (tax-codes, mapping, fx-rates, customers, invoices + submit/approve/post/void, payments, credit-notes + submit/approve/post, aging).
- **UI** : page `SalesAR.js` (remplace le placeholder `acct_sales`) — onglets Factures / Notes de crédit / Clients / Configuration ; workflow complet + encaissement + note de crédit ; data-testids complets.
- **Correctif** : lookups société par `id` OU `_id` dans `journal.py`/`ar.py`/route seed (les sociétés réelles portent l'UUID dans `id`, `_id`=ObjectId).
- **Tests** : `tests/test_a3_ar.py` **ALL PASS** (moteur fiscal GST+QST & TVA CH versionnée, cycle facture + maker-checker, écriture canonique équilibrée, idempotence, VOID vs note de crédit partielle, anti-sur-crédit, crédit client, **multidevise CAD↔USD gain +50 & CHF↔EUR perte −25**, aging, isolation legacy). E2E frontend (testing_agent) **9/9**. Live e2e curl : facture INV-2026-0001 (1081 CHF), paiement→payée, note de crédit CN-2026-0001 approuvée/comptabilisée avec gating 403 junior. Régressions vertes : A2, P2.6+P2.2 59/59, P1.13F.
- Seed test : `persona_junior` = MAKER AR (contribute) ; `persona_finance` = CHECKER/POSTER (permissions AR sensibles) sur Meelora (CHF/CH, période 2026-01 seedée). **A4 non démarré.**

## A3 — Complétion (PDF figé + Document Service + Relances + Référentiel client + UX) — 2026-06-16
Suite à la validation du cœur A3, les 4 écarts restants de la spécification ont été livrés :
- **Document Service générique immuable** (`core/financial/documents.py`) sur Emergent Object Storage : `store_document` (SHA-256, versioning, jamais d'écrasement, métadonnées Mongo `source_documents`, binaire privé), `download_document` (vérif. hash + accès scopé workspace/société/ACCOUNTING), `link_journal` (gel + lien bidirectionnel). Réutilisable AP/PO/immobilisations plus tard.
- **PDF de facture figé à l'approbation** (`core/accounting/ar_pdf.py`, reportlab) : généré dans `approve_invoice`, stocké (v1), `source_document_id/version/sha256` portés par la facture. Numéro attribué à l'approbation ; posting réutilise ce numéro et lie le document à l'écriture (`journal_entries.source_document_id`).
- **Traçabilité bidirectionnelle** : Facture → PDF → écriture ; et `resolve_journal_source` (route `GET /companies/{cid}/journal-source/{je_id}`) : journal → source AR → facture → PDF. Panneau « Traçabilité » dans l'UI.
- **Relances / Dunning** (`core/accounting/dunning.py`) : `overdue_invoices`, `create_reminder` (PDF de relance stocké comme document source + envoi courriel via Resend + historique niveau/acteur/date/statut). ⚠️ **`RESEND_API_KEY` VIDE** dans l'environnement → l'envoi retombe en `status=failed` (dégradation gracieuse : relance + PDF + historique conservés). Fournir la clé Resend pour activer l'envoi réel.
- **Référentiel client enrichi (Section 2)** : adresses facturation/livraison, contacts, courriel de facturation, téléphone, juridiction/pays, langue, conditions de paiement, limite de crédit, numéros fiscaux, exemptions, dimensions, notes internes, pièces jointes, audit.
- **UX complète** (`SalesAR.js`) : onglets **Aperçu AR | Factures | Paiements | Notes de crédit | Clients | Aging | Relances | Configuration** ; drill-down facture → PDF → journal.
- **Nouvelles routes** : `ar/overview`, `ar/invoices/{id}/documents`, `documents/{doc_id}/download`, `journal-source/{je}`, `ar/overdue`, `ar/reminders` (GET/POST).
- **Tests** : `tests/test_a3_ar.py` **ALL PASS** (non-régression, PDF généré à l'approbation via Object Storage réel) ; `tests/test_a3_documents_dunning.py` **ALL PASS** (référentiel enrichi, immutabilité/versioning/hash, traçabilité bidirectionnelle, isolation cross-workspace, relances, aperçu). Frontend testing_agent **100 %** (8 onglets, aucun bug). Isolation legacy `acct_*/qc9434_*` confirmée.
- **A4 (Achats & Fournisseurs) NON démarré** — en attente d'approbation utilisateur.

## Tranche UX transverse (Accueil société, navigation, profil, fiche client) — 2026-06-16 (A3 en pause)
Correction/évolution UX transverse, aucun moteur A3 ajouté, design Meelora strictement conservé.
- **Header** : sélecteur société supprimé (`CompanySelector` retiré de `Layout.js`). Le changement de mandat reste géré par le switcher sidebar « MANDAT ACTIF ». Plus de double sélecteur.
- **Accueil société** (`pages/CompanyHome.js`, route `company_home`) : affiché systématiquement après « Accéder »/entrée dans un mandat (`enterMandat` → `company_home`), avant tout module. « Bienvenue chez <NOM> » + identité société (adresse/ville/région/pays/tél/courriel/site) + 4 KPI (CA du mois, CA exercice, factures ouvertes, encaissements du mois) **conditionnés aux modules accessibles** (KPI uniquement si ACCOUNTING accessible ; sinon état vide propre). Endpoint `GET /companies/{id}/home` (identité + `ar_service.home_kpis`, filtré par manifeste d'accès).
- **Menu Avatar** : Mon profil · Administration (si `admin_view`) → Utilisateurs et accès / Logs société · **Langue** (sous-menu compact `DropdownMenuSub`, 4 langues) · Déconnexion. Item « Sécurité » redondant **supprimé**.
- **Mon profil** (`Preferences.js`) : changement de courriel existant conservé + **changement de mot de passe self-service** (`POST /me/password-change`) : mot de passe actuel requis, politique (≥8 + lettre + chiffre), nouveau ≠ actuel, rotation du token de session courante, audit sans secret (`auth.password_changed`). Un admin ne peut jamais connaître/fixer le mot de passe d'un tiers.
- **Langues** : DE/EN/FR/IT affichées par ordre alphabétique ; **DE et IT désactivées (grisées)** tant que les dictionnaires n'existent pas (FR/EN complets). Préférence persistée via i18n existant.
- **Fiche client (préparation A3, sans workflow facture)** (`SalesAR.js` CustomersTab) : pays → province/territoire (CA) ou canton (CH) → **proposition fiscale automatique** via moteur central (`GET /tax/jurisdiction-config`, `tax_engine.jurisdiction_config` / `resolve_jurisdiction`), aucun taux en dur côté frontend, codes versionnés (pas de recalcul rétroactif). Champs ajoutés : `region`, `due_days`, `tax_regime`, `customer_po` (modèle `_CUSTOMER_FIELDS` + `ARCustomerIn`). Placeholder OANDA « Récupérer le taux » (désactivé) préparé sur la facture.
- **Tests** : frontend testing_agent **100 %** (`iteration_67.json`) — absence sélecteur header, atterrissage accueil, identité+KPI conditionnés, menu avatar, langue DE/IT désactivées, changement courriel/mot de passe (revert OK), pays+province/canton → proposition fiscale, isolation. Endpoints backend curl-vérifiés (password-change 401/422/succès/revert, home, jurisdiction-config CA-QC & CH). Aucune régression navigation ; aucun moteur legacy modifié. **A3 reste en pause.**

## Logo société canonique (Accueil priorité utilisateur + référentiel unique) — 2026-06-16 (A3 en pause)
- **4A Accueil** (`CompanyHome.js`) : priorité visuelle à l'utilisateur connecté — « Bonjour » + **NOM UTILISATEUR en grand** (`company-home-user`), puis **logo + nom de société en plus petit** (pastille `company-home-company`), puis coordonnées et KPI. Composant `CompanyLogo` (fetch blob authentifié → objectURL, fallback initiales).
- **4B Référentiel logo** : le logo est un champ canonique de la société. Upload/remplacement/suppression depuis le formulaire de création/édition (`Companies.js` `CompanyForm`, section « Logo & identité visuelle ») dans Plateforme → Sociétés/Clients et fiche société. Validation type (PNG/JPG/SVG/WEBP) + taille (≤2 Mo), aperçu, ratio conservé, fallback initiales.
- **4C Canonique & réutilisable** : binaire stocké **une seule fois** en Object Storage via le Document Service (`source_type=company_logo`, immuable/versionné, SHA-256) ; seule la référence (`company.branding.logo_document_id`, mime, hash, version, updated_at/by) vit sur la société. Endpoints `POST/DELETE/GET /companies/{id}/logo` (upload/suppression réservés à `require_company_creator` ; GET affichage pour tout membre ayant accès). `branding.has_logo` exposé dans `public_company` et `GET /companies/{id}/home`. Les moteurs de rapports pourront consommer cette identité sans re-téléversement (modèle `branding` extensible pour couleurs/mise en page futures) — moteurs de rapports NON modifiés dans cette tranche.
- **Tests** : frontend testing_agent **100 %** (`iteration_68.json`) — création avec/sans logo, remplacement, suppression, validation type, isolation inter-sociétés, bon logo après bascule de mandat, fallback initiales. Backend curl-vérifié (upload/get/delete, 422 mauvais type, 403 non-admin, 200 GET non-admin, branding). Aucune régression ; A3 reste en pause.

## Correction UX — Landing déterministe + route canonique + logo adaptatif — 2026-06-16 (A3 en pause)
**Cause racine (bug première connexion)** : dans `Layout.js`, l'état `active` était initialisé depuis `localStorage("acct:lastPage")` et persisté à chaque navigation → la page d'atterrissage suivait la dernière route mémorisée (ou une route résiduelle d'une session précédente) au lieu d'être recalculée depuis les mandats. Résultat non déterministe (atterrissage sur un module au lieu de l'Accueil société).
**Correctif** :
- Suppression totale de la dépendance à `acct:lastPage` (lecture ET écriture). `active` initialisé à une sentinelle `__boot__` ; la landing est **recalculée depuis les mandats** : 1 mandat → sélection auto + `company_home` ; plusieurs → `mandats_list` puis Accéder → `company_home` ; aucun mandat → `NoMandateScreen` (état vide propre) ; société inactive → pas d'accès.
- **Route canonique** `/company/:companyId/home` (via `history.replaceState`) : reflétée quand on est sur l'Accueil, supportée au refresh direct (parse du path au boot, `activeCompanyId` résolu fail-closed depuis le contexte).
- **Fail-closed** : pendant la résolution / le changement de mandat (`navManifest` null), un `BootScreen` s'affiche — aucun module/donnée de l'ancien mandat n'est jamais rendu.
- Mention « Point d'entrée du mandat » ajoutée sur l'Accueil.
**Logo adaptatif** (`components/CompanyLogo.js`) : analyse canvas (same-origin blob → non tainté) de la transparence et de la luminance moyenne → fond du conteneur adapté : logo sombre (avgLum ≤ 110) → fond clair `#FFFFFF` ; logo clair/blanc (avgLum ≥ 150) → fond foncé `#0F172A` ; intermédiaire → neutre `#F1F5F9` ; transparent + contraste faible → `#E2E8F0` ; échec/vide → fallback neutre. Proportions conservées (`object-contain`), marge interne, pas de déformation, responsive. Composant réutilisable (Accueil aujourd'hui, rapports/factures plus tard).
**Sidebar** : inchangée et conforme — uniquement « MANDAT ACTIF » + modules accessibles ; aucune fonction d'admin (Sociétés/Clients, Utilisateurs, Logs, Préférences) dans la sidebar (restent dans l'Avatar).
**Tests** : frontend testing_agent **100 % (7/7)** (`iteration_69.json`) — landing 1 mandat (URL canonique + refresh), landing multi (chooser), déterminisme prouvé (logout/login → chooser, pas le dernier module), bascule de mandat sans fuite, logo adaptatif sombre→fond clair, fallback initiales, aucune page plateforme en contexte client. Vérif visuelle main agent : logo BLANC → fond `rgb(15,23,42)` (foncé), logo sombre → fond blanc. Aucun backend/permission/calcul modifié ; A3 reste en pause.

## Registre KPI dynamique & extensible de l'Accueil — 2026-06-16 (A3 en pause)
- **Registre central** (`core/home/registry.py`) : chaque module DÉCLARE ses contributions (`kpis`, `quick_actions`, `recent_activity`, `informational_items`) via `@register("<MODULE>")`. L'Accueil n'importe aucun module directement — l'ajout futur d'un module expose ses KPI automatiquement après entitlement + activation + accès.
- **API d'agrégation unique** : `GET /companies/{id}/home` renvoie `company` + `home_kpis` + `quick_actions` + `recent_activity` + `informational_items` (contrat normalisé). Chaque contribution est gated par `resolve_effective_access` (module accessible + niveau/permission). **Aucune fuite** : un KPI d'un module non accessible n'est jamais calculé ni renvoyé (vérifié : admin_view liste les modules mais n'obtient AUCUN KPI opérationnel). KPI plafonnés à 5 (tri par `priority`), quick actions à 6, activités à 6 (tri date desc). Jamais de carte vide (grille reflow).
- **Contributeur ACCOUNTING** (données AR réelles) : CA du mois (avec comparaison mois précédent + mini-tendance 6 mois), CA cumulé (vs année précédente), Factures ouvertes (+ montant), Encaissements du mois, Clients actifs ; quick actions « Nouvelle facture » / « Paiements reçus » (gated `contribute`), « Clients », « Rapports » → `acct_sales` ; activités récentes (paiements/factures/notes de crédit) ; infos (devise, taxes auto, conditions). **REPORTING défère à ACCOUNTING** (pas de KPI en double).
- **Frontend** (`CompanyHome.js`) : layout du mockup validé conservé — KPI (comparaison ↑/↓ + sparkline SVG), Accès rapides, Activités récentes, À savoir, hint « KPI affichés selon vos modules et permissions ». Cartes KPI et quick actions cliquables → destination.
- **Tests** : testing_agent (`iteration_70.json`) rendu/gating/état vide/bascule OK ; un bug de destination (`acct_sales_ar`→`acct_sales`) corrigé et re-vérifié (clic KPI + Accès rapide → Ventes & Clients). Aucun backend financier/permission modifié ; A3 reste en pause.

## Accueil société — CORRECTION FINALE fidèle au mockup (2026-08-17)
Correction UX/navigation UNIQUEMENT (aucun moteur financier, calcul, entitlement ou permission backend modifié).
- [x] **En-tête Accueil reproduit fidèlement le mockup** (`CompanyHome.js`) : passage d'un layout centré à un layout **aligné à gauche** — grande vignette carrée du logo société (124px, ratio préservé, fond adaptatif conservé) à gauche ; à droite « Bonjour » (petit) → **Nom utilisateur** (dominant) → **Nom société + pastille verte de statut** (CheckCircle si `status=active`, point neutre sinon) → coordonnées (adresse, tél., courriel, site) alignées à gauche.
- [x] **« Point d'entrée du mandat » supprimé entièrement** : de la page Accueil ET du sous-titre de l'item sidebar (sous-titre `NavItem` rendu conditionnellement).
- [x] **Capsule/pilule retirée** autour de l'identité société.
- [x] **Filigrane Meelora très discret** : image `/meelora-mark.png` à opacité ~5 %, coin sup. droit, `pointer-events-none` — le fond du dashboard reste quasi-blanc (pas de fond bleu foncé).
- [x] **Item « Accueil » persistant** ajouté dans la sidebar (`nav-company_home`, icône maison) sous « MANDAT ACTIF », au-dessus des modules. Sous-menus modules toujours en **popovers flottants** (inchangés).
- [x] **Backend** : ajout du champ `identity.status` dans `GET /api/companies/{cid}/home` (non financier, pour la pastille). Aucune autre modification backend.
- [x] **Landing déterministe (cause racine confirmée résolue)** : la landing est calculée uniquement depuis les mandats accessibles (jamais depuis une route sauvegardée ni via un module). 1 mandat → Accueil auto ; multi → « Tous les mandats » puis Accéder → Accueil ; aucun mandat → empty state ; société inactive → exclue du sélecteur / 403 sur `/home` ; jamais de page `/platform/*` en contexte client ; refresh sur `/company/:id/home` → même Accueil. `moduleEntry` (ancien saut vers Comptabilité) devenu code mort non utilisé.
- [x] **Bloc « Budget actif » + sélecteur d'année + bouton « + Année » retiré de l'en-tête** sur tous les écrans (demande utilisateur). `YearControls` conservé mais non monté.
- [x] Tests : testing_agent iteration_71 — frontend **100 % (10/10)**, aucun problème. Landing mono/multi, refresh, changement de mandat, popover modules, logo, absence de « Point d'entrée » et de capsule, pastille de statut, fidélité au mockup : tous validés.


## Accueil raffiné + REPRISE A3 (2026-08-17)
### Accueil (raffinements)
- [x] Filigrane Meelora **global** (`login-bg.png`, opacité ~3,5 %, `fixed inset-0 z-0`) sur toutes les pages de l'outil ; contenu en `z-10`, sidebar opaque.
- [x] Logo Accueil **sans cadre ni fond** (mode `bare` de CompanyLogo, contrainte par la hauteur pour les logos larges), aligné en haut avec « Bonjour », légèrement plus grand que le nom utilisateur (nom réduit à text-3xl/4xl).
- [x] Activités récentes **cliquables** → onglet source (Factures/Paiements/Notes de crédit) + surbrillance de la ligne (sessionStorage `ar_focus`). « À savoir » **contextuel** (factures échues/à échéance, ton avertissement).
### A3 — Ventes & Clients (reprise)
- [x] **§7 Logo canonique + couleur d'accent société dans les PDF** (facture & relance) — `documents.company_branding_assets()` + `ar_pdf` (logo_bytes/accent). Aucun upload par module.
- [x] **§2 Échéance auto** depuis les conditions du client (Net N / due_days) à la création de facture ; `due_date_source` (customer_terms|manual) ; override auditée ; jamais d'écrasement rétroactif.
- [x] **§5 Référence / PO client** sur la facture (auto-proposé depuis la fiche client) + affiché sur le PDF ; champs `customer_po`/`reference` sur ARInvoiceIn/Update et public_invoice.
- [x] **§9 OANDA** : service serveur `core/financial/oanda.py` (API v20 REST, candles midpoint, pas de scraping) + endpoint `GET /companies/{cid}/ar/fx-oanda`. Clés env `OANDA_BASE_URL/OANDA_API_TOKEN/OANDA_ACCOUNT_ID` (VIDES → **dégradation gracieuse** `{available:false}` ; même devise → rate 1). Bouton « Récupérer le taux » fonctionnel. **⚠️ Clé OANDA à fournir par l'utilisateur pour activer l'appel réel.**
- [x] **§12 Écart de change réalisé** : déjà géré à l'encaissement (gain/perte vs taux facture) — confirmé.
- [x] **Couleur d'accent société** : champ `branding.accent_color` (modèle + update `branding.accent_color` + expose) ; sélecteur couleur dans la fiche société (Companies.js) ; accès admin via Avatar → « Sociétés / Mandats » (`menu-companies`).
- [x] **Fiche client 6 sections** (Général | Adresses & contacts | Facturation | Fiscalité | Documents | Historique) : contacts multiples + contact principal, exemptions fiscales, statut actif/inactif, dénomination légale, adresse légale (`_CUSTOMER_FIELDS` + ARCustomerIn étendus).
- [x] Tests : backend **100 % (8/8)** iteration_72 ; frontend **100 % (4/4)** iteration_73 (après correctifs : toast d'erreur sûr `errMsg()`, primary_contact dict, tax_exemptions List[dict], accès admin Sociétés). Non-régression workflow facture/paiement/note de crédit/aging confirmée.
- [ ] Restant A3 : brancher la clé OANDA réelle (tester CAD/USD, CHF/EUR) ; warning React dev-only `<span> in <option>` (cosmétique) ; UI Documents/Historique de la fiche client (placeholders pour l'instant). **STOP A3 — ne pas démarrer A4 sans approbation.**



## Relances — proposition programmée (2026-08-17)
Conforme A3 §16 (pas d'automatisation agressive) — mode **proposition + confirmation manuelle** validé par l'utilisateur.
- [x] **Politique de relance par société** : `dunning_policy = {enabled, levels:[7,15,30]}` (défauts modifiables, seuils positifs et strictement croissants). Endpoints `GET/PUT /companies/{cid}/ar/reminders/policy` (lecture = _ar_read_scope, écriture = _ar_write_scope, auditée).
- [x] **Suggestions** : `GET /companies/{cid}/ar/reminders/suggestions` — propose pour chaque facture échue le prochain niveau non encore envoyé dont le seuil (jours de retard) est franchi. Un envoi échoué ne compte pas comme relance envoyée. Aucun envoi automatique en arrière-plan.
- [x] **UI onglet Relances** (`SalesAR.js` RemindersTab) : panneau « Politique de relance » (toggle + 3 seuils + Enregistrer) et « Relances suggérées » (facture, retard, niveau suggéré) avec bouton « Envoyer niveau N » (réutilise `create_reminder` avec `level`).
- [x] **Accueil « À savoir »** : item contextuel « N relance(s) suggérée(s) » (registre, si politique activée).
- [x] Vérifié : endpoints (policy défaut/valide/invalide, suggestions=2) par curl + rendu UI. ⚠️ L'envoi réel reste dégradé (statut "failed") tant que `RESEND_API_KEY` est absent.

## A4 — Achats & Fournisseurs : GATE validé + A4.1 livré (2026-08-17)
- **GATE A4** : plan complet dans `/app/memory/A4_PLAN.md` (inventaire, modèle de données, workflow, permissions, ingestion PDF/email/IA, PO/matching, découpage A4.1→A4.8, risques). Décisions validées : 4 statuts séparés ; PO minimal en A4.5 ; courriel entrant reporté (A4.7) ; IA = GPT vision **sous gouvernance stricte** (non-entraînement, `DocumentAIProvider`, minimisation, rétention, audit, l'IA propose sans jamais poster) — **GATE de vérification avant A4.4**.
- **A4.1 — Référentiel fournisseurs (livré, testé 100 %)** : `core/accounting/ap.py` (CRUD `ap_suppliers` + masquage bancaire), endpoints `GET/POST/PATCH /companies/{cid}/ap/suppliers`, permissions AP ajoutées au catalogue, écran `PurchasesAP.js` (7 onglets, fiche fournisseur 7 sections, contacts multiples, proposition fiscale par juridiction, PO obligatoire par fournisseur), nav `acct_purchases` branché. Isolation société + refus d'accès validés. **STOP après A4.1** — tranche suivante A4.2 sur validation.


## A4.2 — Factures fournisseurs & workflow AP (2026-08-17)
- Facture fournisseur canonique `ap_invoices` à **4 statuts séparés** (document/approval/posting/payment) ; workflow draft→verified→submitted→approved/rejected ; posting séparé approved→posted.
- Réutilise le Cœur financier : moteur fiscal versionné (snapshot), FX/OANDA (bouton « Récupérer le taux », jamais fallback 1), posting canonique P2 `create_workflow_journal_entry` (Dr charge/actif · Dr taxes récupérables · Cr fournisseurs — atomique/équilibré/idempotent, périodes locked/closed).
- Échéance auto depuis conditions fournisseur (snapshot, override audité). Doublon (company+supplier+n°) bloquant. Règle PO obligatoire (statut `po_missing`, submit/approve bloqués). Upload PDF source en Object Storage (`source_document_id`+sha256, jamais base64) + lien au journal.
- Permissions sensibles `accounting.supplier_invoice_approve` / `supplier_invoice_post` via `require_sensitive_permission` + maker-checker (aucun bypass manage/Client Admin/platform_role). Immutabilité après posting.
- UI `PurchasesAP.js` : onglets **Factures** + **Factures à traiter** activés (formulaire création, actions workflow, upload PDF, badges).
- **Testé : backend 100 % (13/13), frontend 100 %** (iteration_75). Reste : warning React dev-only `<span> in <option>` (cosmétique). **STOP après A4.2 — A4.3+ sur validation.**


---

## A4.3 — Paiements fournisseurs · Crédits · Aging AP (LIVRÉ — 2026-06)
Module Achats & Fournisseurs (AP) uniquement. Aucun ledger parallèle : réutilise le Cœur P2/A2, le moteur FX/OANDA et l'Object Storage. **STOP strict après A4.3** (A4.4 IA, A4.5 PO, A4.7 courriel entrant NON démarrés — attente validation).

### Implémenté
- **Paiements fournisseurs (`ap_payments`)** — cycle de vie à 5 états : `draft → prepared → authorized → executed → posted` (+ cancelled). Invariants clés :
  - draft/prepared/authorized NE modifient PAS `invoice.payment_status` et NE créent AUCUN journal.
  - `execute` (SENSIBLE `accounting.supplier_payment_post`) = décaissement confirmé (acteur/date/méthode/référence/audit) → SEUL déclencheur de `invoice.payment_status` (unpaid→partially_paid→paid), dérivé des allocations exécutées.
  - `post` (SENSIBLE) = écriture canonique P2 `Dr Fournisseurs / Cr Banque (+ Gain/Perte FX réalisé)`, équilibrée, atomique, idempotente (external_id).
  - Partiel/total/multiples/multi-factures ; allocations = registre traçable (flag `active`) ; avance/non affecté (`unapplied_amount`) + affectation ultérieure (`allocate`, aucun 2e décaissement/journal).
  - **Paiement AVANT posting facture** démontré : les 2 journaux (paiement + facture) s'annulent nets sur le compte AP, aucune double comptabilisation.
  - Points d'extension prévus (prepare/approve/execute séparés) pour le futur module Banque & Trésorerie qui CONSOMMERA le même `ap_payment` (idempotency_key/external_ref).
- **Notes de crédit fournisseurs (`ap_credit_notes`)** — workflow propre `draft→submitted→approved→posted`, maker-checker, journal inverse proportionnel (`Dr Fournisseurs / Cr Charge(s) / Cr Taxes récupérables`) au taux/snapshot fiscal d'origine, crédit partiel par ligne, **sur-crédit cumulatif interdit** (posted + pending), crédit non affecté → crédit fournisseur disponible (`ap_supplier_credits`). Permissions `supplier_credit_note_approve/post`.
- **Aging AP** — buckets Courant/1-30/31-60/61-90/90+ par date d'échéance, dérivés des transactions, date d'analyse (`as_of`) paramétrable. Sépare **Solde comptable** (factures posted) de **Approuvé à comptabiliser** (approved non posted) + **Crédits disponibles** ; consolidation devise fonctionnelle ; tableau par fournisseur.
- **Vue synthétique fournisseur** (`GET /ap/suppliers/{id}/summary`) : solde, buckets, échu, plus ancienne facture échue, crédits dispo, derniers paiements.
- **Lots de paiement (`ap_payment_batches`)** — objet de PRÉPARATION seulement (jamais preuve de paiement, jamais GL) : `propose_batch_candidates`, snapshot au `prepare`, lifecycle draft→prepared→authorized→processing→completed(+cancelled/partially_completed), `revalidate` (exceptions sans mutation silencieuse). **Aucune émission bancaire** (réservée à Banque & Trésorerie).

### Endpoints (préfixe `/api/companies/{cid}/ap`)
`POST/GET/PATCH /payments` · `/payments/{id}/{prepare|authorize|cancel|execute|post|allocate}` · `GET/POST /credit-notes` · `/credit-notes/{id}/{submit|approve|post}` · `GET /aging?as_of=` · `GET /suppliers/{sid}/summary` · `GET /batch-candidates` · `GET/POST /batches` · `/batches/{id}/{prepare|authorize|cancel}` · `GET /batches/{id}/revalidate`.

### Fichiers
- Backend : `core/accounting/ap.py` (paiements/crédits/aging/lots), `server.py` (routes + modèles Pydantic), `scripts/seed_p1_13e_personas.py` (grants supplier_payment/credit).
- Frontend : `pages/PurchasesAP.js` (PaymentsTab/CreditsTab/AgingTab), `lib/api.js`.
- Tests : `backend/tests/test_a4_3_ap_payments.py` (15/15) — rapport `test_reports/iteration_76.json` (backend 100%, frontend 100%, 0 bug).

### Roadmap AP restante (NON démarrée — validation requale)
- **A4.4 (P0)** — Analyse documentaire IA (OCR factures). ⚠️ Gouvernance stricte `A4_PLAN.md` (abstraction DocumentAIProvider, zéro entraînement, isolation, audit).
- **A4.5 (P0)** — Bons de commande (PO) minimaux + matching 2-way.
- **A4.6 (P1)** — Réévaluation FX non réalisée + réconciliation Aging↔GL avancée.
- **A4.7 (P1)** — Boîte de réception courriel AP dédiée.
- **Banque & Trésorerie (futur)** — exécution/rapprochement bancaire consommant `ap_payments` + `ap_payment_batches`.
- OANDA_API_KEY (P2) et RESEND_API_KEY (P2) : en attente des clés utilisateur.

### A4.3 finition — onglet Aperçu AP (LIVRÉ — 2026-06)
Vue de pilotage compacte et actionnable dans Achats & Fournisseurs → **Aperçu** (onglet par défaut), dérivée exclusivement des données A4.1–A4.3 (aucun solde stocké, aucun ledger parallèle).
- **5 KPI cliquables** : À traiter (nombre) · À payer · Échu · Échéance 7 j · Crédits disponibles → drill-down direct (inbox / payments to_pay / aging / aging / credits).
- **Priorités** triées par urgence (factures : approbation requise/PO manquant/échue depuis X j ; paiements : à autoriser / exécuté à comptabiliser) — clic → vue concernée.
- **Trésorerie fournisseurs** : Échu | 7 j | 30 j | >30 j, ventilation PAR DEVISE (jamais additionnées silencieusement ; contre-valeur fonctionnelle indicative).
- **Top fournisseurs à payer** (max 5, solde ouvert + prochaine échéance) → clic vers Aging.
- Skeleton loading + cache/revalidation (`_ovCache`), chargement parallèle. Respecte prepared/authorized ≠ payé, executed ≠ posted.
- Backend : `ap.py::overview()` + `GET /api/companies/{cid}/ap/overview`. Frontend : `PurchasesAP.js::OverviewTab`, `api.js::apOverview`. Tests : `test_reports/iteration_77.json` (frontend 100%, 0 bug).

### A4.3 finition — Aperçu AP quasi temps réel (LIVRÉ — 2026-06)
Rafraîchissement léger des KPI et Priorités de l'Aperçu AP, sans WebSocket/SSE (aucune infra temps réel disproportionnée).
- **Polling ~25s + revalidation au focus** (`visibilitychange`) sur `GET /ap/overview` (scopé société active + droits effectifs côté serveur). Aucune donnée financière sensible en optimistic UI (serveur confirmé uniquement).
- **Badge compteur `+N`** discret sur la carte KPI « À traiter » (nouvelles factures à actionner) ; **badge « Nouveau »** + animation `ap-fade-in` (420ms, une seule fois, neutralisée sous `prefers-reduced-motion`) sur les nouvelles priorités. Aucun clignotement, aucun son.
- **Acquittement** : le badge disparaît au clic (KPI ou priorité) via `seenRef`/`acknowledge()` ; baseline établie au premier rendu (rien n'est « nouveau » à l'ouverture).
- **Boost de récence backend** : les factures reçues/soumises ≤ 2 j (`urgency 40→70`) remontent dans le top-8 des priorités (jamais au-dessus d'une facture réellement échue).
- Fichiers : `PurchasesAP.js::OverviewTab` (refs seenRef/baseRef/firstRef, états newIds/toProcessDelta), `index.css` (@keyframes apFadeIn), `ap.py::overview()`. Tests : `test_reports/iteration_78.json` (frontend 90% — KPI +N badge, fade-in, acquittement, revalidation focus vérifiés ; logique newIds confirmée par revue ; boost de récence ajouté ensuite pour surfacer les nouveautés).

### A4.3 finition — Badge de navigation AP (registre extensible) (LIVRÉ — 2026-06)
Indicateur discret « éléments non vus » sur l'entrée de nav Achats & Fournisseurs, sans infra temps réel dédiée.
- **Registre extensible** `context/NavBadgeContext.js` (`NAV_BADGE_SOURCES` : par module, `fetchItems(cid)`) — pas de code AP en dur ; d'autres modules pourront s'y enregistrer. `NavBadgeProvider` : polling unique 30 s + revalidation `visibilitychange`, scopé société active + modules accessibles ; « vus » persistés en localStorage par (clé, société). Réutilise `GET /ap/overview` (champ `actionable_ids` = factures à traiter + paiements authorized/executed + crédits dispo).
- **UI** (`Layout.js` `NavCount`) : badge compteur discret plafonné **« 9+ »** sur le module racine `Comptabilité` (`nav-module-badge-ACCOUNTING`) et la sous-entrée `Achats & Fournisseurs` (`nav-item-badge-acct_purchases`). Pas de clignotement, pas de son, `ap-fade-in` neutralisé sous `prefers-reduced-motion`. Aucune donnée financière dans le badge (nombre seul).
- **Acquittement** : ouvrir l'Aperçu AP (`OverviewTab` → `acknowledgeWith`) efface le badge (persisté) ; réapparaît uniquement à l'arrivée d'un nouvel élément non vu. Scope société strict.
- Tests : `test_reports/iteration_79.json` (frontend 100% — 7/7 : présence, sous-item, acquittement+persistance, réapparition, no-blink/no-son, scope société, contenu numérique plafonné).

**PROCHAINE ÉTAPE : A4.4 — Analyse IA des factures** (OCR/extraction). ⚠️ Ne PAS activer réellement sans le GATE de gouvernance IA de `A4_PLAN.md` (abstraction DocumentAIProvider, zéro entraînement, minimisation, zéro-rétention, isolation, audit) — validation utilisateur requise avant activation réelle.

### A4.4 — Analyse automatique des documents (architecture, DORMANT/fail-closed) (LIVRÉ — 2026-06)
Extraction IA de factures fournisseurs comme couche d'ASSISTANCE (STRAT-01 §10). GATE approuvé sous conditions. **Aucun appel IA réel** : registre de providers VIDE → fail-closed → fallback manuel intégral.
- **Abstraction `DocumentAIProvider`** (`core/accounting/ap_extraction.py`) : ABC + `ProviderAttestation` **versionnée** (`A4.4-2026-06`) + registre extensible ; scaffold `ByoVisionProvider` (clé lue depuis `os.environ[api_key_env]` — jamais DB/logs/audit/frontend ; `extract_invoice` lève `ProviderNotConfigured` = pas d'appel réel).
- **Gate fail-closed** (`extraction_gate`) : rejette si version d'attestation ≠ politique, non-entraînement absent, **clé Emergent universelle interdite**, chiffrement insuffisant, région non autorisée, ou provider indisponible. Vérifié (6/6 règles) + isolation.
- **Politique de juridiction** (`core/compliance/jurisdiction.py`) : `document_ai_policy` porte `region_required` (Meelora=CH → ['CH','EU']) + `allow_emergent_universal_key=false`. **Non hardcodé dans AP** (seed Jurisdiction Engine, STRAT-01 §11).
- **`ap_extractions`** (schéma approuvé, `Field<T>` = value/confidence/provenance/needs_review) : confiance & provenance stockées mais **jamais exposées en UX normale** (réservées à « Pourquoi ? »). **Corrections humaines `excluded_from_training=true`**, journalisées, aucun chemin d'entraînement.
- **Audit IA** (`ap_ai_audit`) sans secrets ni prompt brut ; status (unavailable/error/ok), attestation_snapshot.
- **No-authority prouvé** (revue code) : le module n'appelle jamais posting/approve/pay ; toutes les actions sensibles restent derrière `require_sensitive_permission` (humain P1.13). Maker-checker intact.
- **UX** : panneau `DocumentAIPanel` (« Analyse automatique des documents », jamais « IA »/« GPT » au centre) dans l'onglet Factures à traiter → « Indisponible — saisie manuelle » actuellement. **Fallback manuel A4.2 pleinement fonctionnel.**
- Endpoints : `GET /ap/document-ai/status`, `POST /ap/document-ai/analyze` (fail-closed), `GET /ap/extractions(+/{xid})`, `POST /ap/extractions/{xid}/corrections`.
- Doc de gouvernance : `memory/A4_4_GOVERNANCE_SCOPING.md`. Tests : `test_reports/iteration_80.json` (backend 5/5, frontend 100%, 0 bug).

**Prérequis d'ACTIVATION réelle (non faits)** : provider BYO conforme configuré + **attestation écrite** (non-entraînement, rétention, DPA/sous-traitants, région UE/CH, chiffrement, suppression) → puis câblage du vrai appel vision dans une tranche ultérieure. **STOP après A4.4 — A4.5 non démarré.**

### A4.5 — Bons de commande (PO) + Matching 2-way (LIVRÉ — 2026-06)
Contrôle financier AP (pas de procurement/ERP). Construit sur A4.1–A4.4 + P2. Aucun ledger PO.
- **Objet PO** (`ap_purchase_orders`) : numéro PO-YYYY-#### (à l'approbation), lignes avec `line_id` stable + taxes (moteur fiscal), FX snapshot, pièces jointes, approbateurs, factures liées, invoiced/remaining dérivés. **`po_status` ⟂ `invoicing_status`** (indépendants). `closed` **explicite** (jamais auto). **Annulation interdite si facture liée**.
- **Matrice d'approbation + tolérance** : `company_ap_settings` **versionnée** (matrix_version / policy_version). Tolérance presets **Strict/Standard/Personnalisé**, Standard=CHF 1.00 abs. `required_levels` par montant (contre-valeur fonctionnelle), extensible multi-niveaux.
- **Matching 2-way déterministe** : fournisseur/devise/total + cumul facturé ; statut ∈ matched/within_tolerance/exception(over_invoicing|tolerance|mismatch)/partial. **Anti sur-facturation** (Σ ≤ total PO). Auto-association PO (société active, unique+fiable). A4.4 = hint, jamais décideur.
- **Override** `accounting.po_match_override` (sensible) : accepte exception tolérance/mismatch + motif + audit ; **REFUSE la sur-facturation** (→ amendement/ré-approbation PO).
- **P1.13** : approbation PO = `accounting.po_approve` (sensible, maker-checker, aucun bypass). Hook `assert_invoice_matchable` bloque l'approbation facture si matching non validé / PO obligatoire manquant. **Posting facture inchangé (A4.2/P2)**.
- **UX** : page Bons de commande (Aperçu | À approuver | Bons de commande) + KPIs + sélecteur de tolérance (avancé replié). Happy Path 1 décision, Exceptions First.
- Endpoints : `/ap/settings`, `/ap/purchase-orders(+/{id}/{submit|approve|reject|send|cancel|close})`, `/ap/invoices/{id}/{match|auto-match|match-override}`. Fichiers : `core/accounting/po.py`, `pages/PurchaseOrders.js`. Tests : `test_reports/iteration_81.json` (backend 11/11, frontend 100%, 0 bug).

**STOP après A4.5 — A4.6 et Swiss Country Pack NON démarrés.**

### A4.6 — Réévaluation FX non réalisée + Réconciliation Aging AP ↔ GL (CADRAGE LIVRÉ — 2026-06, EN ATTENTE VALIDATION)
Cadrage document uniquement (`memory/A4_6_SCOPING.md`), **AUCUN code**. Gate STRAT-01 §21 complet. Décisions validées client (ask_human) :
- **Taux** : `exchange_rates` étendu `rate_type = current|closing` ; priorité `closing`, fallback `current` tracé dans « Pourquoi ? » (jamais silencieux) ; fraîcheur douteuse → exception `rate_stale` ; snapshot immuable par run.
- **Comptabilisation** : toujours calculable sans GL ; posting = action humaine sensible `accounting.fx_revaluation_post` (P2 atomique/idempotent) ; extourne auto-préparée période suivante, liée bidirectionnellement ; périodes open/locked/closed respectées, aucun bypass.
- **Soldes** : classification canonique `monetary_classification = monetary|non_monetary` + `classification_reason` (déterministe, explicable, auditée, jamais l'IA) ; factures/crédits/soldes partiels postés ouverts = monétaires ; avances biens/services = non monétaires ; avances remboursables = monétaires. Réévalue seulement le solde ouvert.
- **Comptes** (rôles canoniques, mapping société) : `FX_UNREAL_GAIN`/`FX_UNREAL_LOSS` (P&L) + `AP_FX_REVAL` (bilan) — DISTINCTS du réalisé A4.3 (`FX_GAIN`/`FX_LOSS`). Compte de contrôle fournisseurs historique jamais touché. Équation réconciliation : `Aging(hist.) +/− AP_FX_REVAL = AP GL clôture`.
- **Réconciliation** : rapport dérivé Aging(hist.) ↔ solde GL compte(s) fournisseurs ; taxonomie temporelle / légitime / anomalie ; « Réconcilié ✓ » si concordance, sinon Exceptions First ; drill-down ≤3.
- **Permission** : NOUVELLE `accounting.fx_revaluation_post` (sensible, maker-checker, aucun bypass) ; pas de réutilisation `supplier_invoice_post`, pas de couplage clôture période.
- **Preuve zéro ledger parallèle** : sous-registre Aging dérivé au taux historique (inchangé) ; positions du run = photo d'audit non autoritative ; seule écriture GL via journal canonique P2. Nouvelles collections : `ap_fx_revaluations`, `ap_reconciliations` (runs/rapports, jamais des soldes).

**STOP après cadrage A4.6 — attendre validation avant tout développement. Swiss Country Pack toujours NON démarré.**

### A4.6 — Réévaluation FX non réalisée + Réconciliation Aging AP ↔ GL (LIVRÉ & TESTÉ — 2026-06)
Gate approuvé, développement autorisé & livré. Backend 9/9 pytest PASS + frontend 100% (`test_reports/iteration_82.json`).
- **Extension FX** (`core/financial/fx.py`) : `exchange_rates.rate_type = current|closing` (non-breaking) + `get_rate_typed`. `record_rate(rate_type)`. Route `ar/fx-rates` accepte `rate_type`.
- **Module `core/accounting/fx_revaluation.py`** : `calculate_revaluation` (aucun GL, idempotent — remplace tout brouillon du même périmètre, renvoie `already_posted` si run posté existe), `post_revaluation` (sensible, maker-checker préparateur≠posteur, période postable, écriture P2 idempotente via `external_id={id}:reval`, extourne auto-préparée/postée période suivante liée bidirectionnellement), `post_reversal`, `reconcile`.
- **Résolution de taux** : priorité `closing`, fallback `current` **tracé** (`is_fallback`+reason dans « Pourquoi ? »), fraîcheur douteuse (>7j) → exception `rate_stale`, taux absent → `rate_unavailable` ; posting bloqué tant qu'exception. Snapshot immuable par run.
- **Classification** `classify_ap_position` déterministe (monetary|non_monetary), jamais l'IA. Réévalue seulement le solde ouvert des factures postées en devise ≠ fonctionnelle.
- **Comptes** (mapping société, rôles) : `FX_UNREAL_GAIN`/`FX_UNREAL_LOSS` (P&L) + `AP_FX_REVAL` (bilan). **Le compte de contrôle fournisseurs (`AP`) n'est jamais mouvementé** (vérifié en test). Écriture équilibrée/atomique ; extourne = mêmes comptes inversés + `reverses_journal_entry_id`/`link_reversal`.
- **Réconciliation** (`GET /ap/reconciliation`) : Aging(historique) ± AP_FX_REVAL = AP présenté au taux de clôture ; taxonomie anomaly/legitimate/temporal ; ponts (avances postées, relief exécuté-non-posté **plafonné par facture**, crédits dispo, paiements postés sur factures non postées, approuvé-non-posté). « Réconcilié ✓ » si résiduel ~0, sinon Exceptions First (anomalies en tête). Données seed réparées (2 factures dont le cache credited_total était périmé).
- **Permission** NOUVELLE `accounting.fx_revaluation_post` (catalogue) — sensible, aucun bypass ; octroyée à persona_finance.
- **UI** (`pages/PurchasesAP.js`) : onglets « Réévaluation FX » (Calculer → vérifier exceptions → Comptabiliser, panneau « Pourquoi ? », historique) et « Réconciliation » (Réconcilié ✓ / écarts catégorisés). `api.js` : apReconciliation/apRevaluations/apCalculate/apPost/apPostReversal.
- **Preuve zéro ledger parallèle** : sous-registre Aging inchangé (dérivé, taux historique) ; positions du run = photo d'audit ; seule écriture GL via journal canonique P2. Collection `ap_fx_revaluations`. Doc : `memory/A4_6_SCOPING.md`.

**STOP après A4.6 — Swiss Country Pack NON démarré.**

### Swiss Country Pack — CADRAGE GLOBAL (VALIDÉ — 2026-06) → `memory/SWISS_COUNTRY_PACK_SCOPING.md`
Étude réglementaire sourcée (ESTV, SIX, GeBüV/OLico, veb.ch). Ordre validé CH.1→CH.9. Policy Engine canonique versionné, zéro `if country==CH`, Banking/Treasury = Core réutilisable, migration non-breaking `sales_tax_codes`.

### CH.1 — Jurisdiction / Accounting Policy Engine (LIVRÉ & TESTÉ — 2026-06)
Fondation transverse (CH/CA/EU). Doc : `memory/CH1_POLICY_ENGINE_SCOPING.md`. Tests : **30/30 PASS** (`backend/tests/test_ch1_policy_engine.py`, exécution directe).
- **Module** `core/compliance/policy_engine.py` : `resolve(domain, context, as_of) → PolicyDecision`, `explain(snapshot)`, `list_effective`, `create_draft/update_draft/publish_draft`, `check_overlaps`, `assert_overridable`, `snapshot`, `ensure_seed/ensure_indexes`.
- **Collections** : `jurisdiction_policies` (append-only, draft|published, versions immuables), `policy_audit`.
- **Domaines câblés** : `vat` (wrapper `sales_tax_codes` — **parité 100%**), `fx_freshness` (R4, défaut 7j), `monetary_classification` (R4), `rounding` (fallback Core 2 déc.), `document_ai` (absorbe `jurisdiction.document_ai_policy`). **Aucune règle métier neuve** (3.8%/QR/camc = CH.2+).
- **Hiérarchie juridictionnelle générique** (spécificité par profondeur : `CH-GE>CH>*`, `CA-QC>CA>*`), jamais le mot « canton » codé.
- **Résolution déterministe** : spécificité → scope(company>system) → priorité → effective_from ; **égalité parfaite → `policy_conflict` fail-closed** (aucun tie-break arbitraire) ; détection d'overlap **à la publication** + garde runtime.
- **Stratégie par domaine** : `required` (vat/monetary → fail-closed, jamais 0 implicite), `fallback_allowed` (rounding/fx → fallback Core explicite), `optional` (document_ai).
- **Reproductibilité démontrée** : facture 2023 @7.7% ; publication future v2 @8.1% ne touche pas la v1 ; `explain(snapshot)` rejoue 7.7% **sans re-résolution**.
- **Cache** invalidé depuis `effective_from` d'une nouvelle policy (corrections rétroactives), snapshots jamais invalidés.
- **Overridability** déclarée (`configurable|overrideable|non_overrideable`) ; `assert_overridable` bloque l'override d'une règle réglementaire même pour admin/manage.
- **sources[]** objet structuré (authority, title, doc_ref, url, published_version/date, effective_from, verified_at, archived_hash).
- **Routes lecture** : `GET /companies/{cid}/policy/effective`, `POST /companies/{cid}/policy/resolve`. Seed système au démarrage. **Non-régression** A4/A4.6 confirmée (réconciliation 0, isolation 404).
- **Reports** : A4.6 **non modifié** (interface d'autorité disponible, câblage R4 ultérieur) ; DT1/DT2 → CH.9 ; R1 production-only ; OANDA/IA facultatifs.

**STOP après CH.1 — ne pas démarrer CH.2 automatiquement.**

### CH.2 — TVA Suisse (LIVRÉ & TESTÉ — 2026-06)
Doc : `memory/SWISS_CH2_VAT_SCOPING.md`. Domaine **`vat_ch`** ajouté au Policy Engine CH.1 (aucun second moteur fiscal ; A3/A4 consommeront la décision). Tests : **46/46 PASS** (`backend/tests/test_ch1_policy_engine.py`).
- **`VATPolicyDecision`** structurée : `tax_treatment` (standard/reduced/accommodation/zero_rated_export/exempt_without_credit/out_of_scope/reverse_charge_acquisition/import_goods), `rate`, `recoverability{full|none|partial|needs_review}`, `reporting_mapping` (200/302/312/342/380/400 pour CH.4), `account_roles` canoniques, `vat_fx`, `rounding` snapshot, `legal_basis`, `sources`, `needs_review`.
- **Seed** `vat_ch/CH` v1 (2018 : 7.7/2.5/3.7 %) + v2 (2024 : 8.1/2.6/3.8 %), versionné, reproductible.
- **Ajustement 1 (acquisition tax)** : assujetti CH → imposable **sans** seuil ; non-assujetti → seuil CHF 10 000 (statut + `acquisition_ytd`). Testé (CHF 1000 assujetti = imposable ; non-assujetti <10k non ; >10k oui).
- **Ajustement 2 (recoverability)** : `full` = résultat du Happy Path, **jamais** fallback ; info insuffisante → `needs_review` fail-closed (aucun droit à déduction inventé).
- **Ajustement 3 (VAT FX)** : bloc `vat_fx` = taux **à la date fiscale** (registre `exchange_rates` canonique, non dupliqué), distinct du FX transaction et du closing/revaluation A4.6. Testé (fiscal 0.95 ≠ closing 0.90).
- Nouveaux rôles : `TAX_VAT_ACQUISITION`, part non récupérable → `EXPENSE`. Taux légaux `non_overrideable` ; override sensible réservé aux décisions réellement overrideable (`accounting.vat_decision_override`, à câbler côté A3/A4 lors de la consommation).
- **Migration** : taux en parité `sales_tax_codes` ; **A3/A4 non encore recâblés** (CH.2 = autorité + API prêtes) → posting P2 et historique **inchangés** (non-régression réconciliation 0 confirmée). Shadow/parité std/reduced validés dans les tests.
- Routes CH.1 `POST /policy/resolve` servent `vat_ch`. Notes de crédit : héritage du snapshot fiscal d'origine (règle définie, appliquée lors du câblage A4).

**STOP après CH.2 — ne pas démarrer CH.3 automatiquement.**
