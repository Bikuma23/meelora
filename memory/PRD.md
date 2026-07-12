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

## Backlog restant
- Rapports personnalisés avancés (choix de colonnes, comparaison multi-scénarios).
- Édition rapide (double-clic) des taux ; gestion multi-utilisateurs & rôles.
- Gestion multi-années / duplication du budget actif.

## Backlog Phase 2 (obsolète — livré)
- Rapports prédéfinis & personnalisés (export PDF/Excel).
- Filtres Année + Département sur le tableau de bord (backend /budget?department déjà prêt).
- Validation du code département à la création d'un employé.
- Édition rapide (double-clic) des taux ; gestion d'utilisateurs multiples.
- Gestion multi-années / budget actif.
