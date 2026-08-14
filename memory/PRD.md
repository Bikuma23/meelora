# PRD — Budget Salaires Pro (Masse salariale CCQ, Québec)

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
