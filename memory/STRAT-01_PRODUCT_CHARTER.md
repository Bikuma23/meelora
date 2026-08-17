# STRAT-01 — PRODUCT CHARTER MEELORA (contrainte permanente)

> Ce document est une **contrainte de développement permanente**. Toute nouvelle
> tranche/spécification doit le respecter, même si un prompt individuel ne répète
> pas ces règles. NE PAS modifier une fonctionnalité existante uniquement pour
> « aligner » la charte sans demande explicite. Utiliser la charte comme règle
> pour les NOUVELLES tranches et **signaler les contradictions importantes**
> lorsqu'elles apparaissent.
>
> **A4.4 (Analyse IA des factures) reste STOP jusqu'à approbation explicite.**

## 1. Vision produit
Puissance d'un système financier professionnel + simplicité grand public. La
complexité vit dans le moteur, jamais imposée inutilement à l'utilisateur. Chaque
fonctionnalité est évaluée sur DEUX critères simultanés : rigueur financière/
réglementaire ET simplicité d'usage / Time-to-Done. Une fonctionnalité qui marche
mais reste compliquée n'est PAS terminée.

## 2. Positionnement
N'est PAS : comptable low-cost, ERP généraliste, outil « AI-first », assemblage de
modules indépendants. EST : le système financier des PME qui veulent les contrôles
d'un vrai département finance sans la complexité d'un ERP.
Marché initial : Suisse, architecture internationale dès l'origine. Expansion :
Canada/Québec → Canada → France → Allemagne → Italie → autres.

## 3. Principes UX fondamentaux
- Happy Path First (cas normal ultra-court)
- Exceptions First (montrer d'abord l'unique élément incorrect)
- Progressive Disclosure (détails comptables/techniques à la demande)
- Smart Defaults (proposer ce qui est déjà connu)
- Zero Duplicate Entry (ne jamais redemander une info connue)
- One Human Decision (automatiser jusqu'à la vraie décision humaine)
- Explain Everything (toute automatisation répond à « Pourquoi ? »)
- Every Error Has a Next Action (prochaine action légalement/comptablement admissible)
- Financial Drill-down ≤ 3 niveaux (chiffre → transaction/document source)
- No Accounting Knowledge Required for Routine Work

## 4. Time-to-Done (métrique produit principale)
Cibles à intégrer progressivement aux critères d'acceptation :
- facture client existant → ≤ 60 s
- facture fournisseur conforme → idéalement 1 décision humaine
- paiement fournisseurs → gérer surtout les exceptions
- rapprochement bancaire → examiner uniquement le non-rapproché
- comprendre un chiffre → ≤ 3 niveaux
- invitation utilisateur standard → ≤ 60 s
- ajout d'un module → aucune ressaisie de données existantes

## 5. Architecture modulaire
Modules autonomes MAIS indépendance ≠ duplication de données. Modules canoniques :
REPORTING, ACCOUNTING, FIXED_ASSETS, CONSOLIDATION, BUDGETS, INVENTORY.
À l'ajout d'un module : réutiliser automatiquement société, utilisateurs, données,
documents, périodes, devises, dimensions, configurations ; ne jamais réimporter ;
proposer uniquement les paramètres manquants ; préserver l'historique. Un nouveau
module « débloque une capacité du même système ».

## 6. ACCOUNTING et REPORTING
REPORTING = module commercial autonome (clients gardant leur compta ailleurs).
ACCOUNTING inclut fonctionnellement Reporting. Si ACCOUNTING présent : NE PAS
afficher REPORTING comme module racine séparé ; Reporting via
**Comptabilité → Rapports & Analyses**. Ne jamais dupliquer moteurs ni données.

## 7. Financial Core
Une seule vérité comptable. `financial_periods` = périodes canoniques.
`accounting_entries` = workflow pré-posting. `journal_entries`/
`journal_entry_lines` = journal canonique. AUCUN ledger parallèle. Objets
comptabilisés immuables. Correction = nouvelle transaction liée (extourne, note de
crédit, ajustement). Posting idempotent. Audit complet.

## 8. Périodes
`open ↔ locked → closed`. **closed est terminal** — jamais de réouverture, aucun
rôle. Correction post-clôture → période ultérieure avec traçabilité. La période
suivante peut exister mais aucun posting tant que la précédente n'est pas fermée.

## 9. Autorisations (P1.13)
identité ≠ membership ≠ module ≠ niveau ≠ permission sensible. `manage`,
`Client Admin`, `platform_role` ne confèrent JAMAIS implicitement une autorité
financière sensible. Actions sensibles = permissions explicites. Maker-checker si
pertinent. Navigation masquée ≠ sécurité. Backend = autorité. Cross-workspace/
no-leak obligatoire.

## 10. IA
Couche d'ASSISTANCE, jamais autorité financière. PEUT : extraire, classifier,
suggérer, matcher, expliquer, détecter anomalie. NE PEUT PAS : approuver, poster,
payer, clôturer, contourner les permissions.
**Règle absolue** : les données client transmises à un fournisseur IA ne doivent
PAS servir à entraîner/améliorer un modèle partagé. Exiger : minimisation,
non-entraînement, rétention maîtrisée, isolation tenant, chiffrement, audit,
abstraction `DocumentAIProvider`, possibilité de remplacer le fournisseur. L'UI
n'expose pas confidence scores / prompts / OCR raw ; l'utilisateur voit le résultat
métier + peut ouvrir « Pourquoi ? ».

## 11. International Core / Country Packs
Financial Core → Jurisdiction Engine → Country Packs (CHCountryPack, CACountryPack,
EUCommon + FrancePack/GermanyPack/ItalyPack). Ne JAMAIS disperser `if country ==`
dans les modules métier. Country Packs : fiscalité, obligations documentaires,
reporting réglementaire, paiements, e-invoicing, conservation, validations locales.
Country Pack ≠ module facturé séparément.

## 12. Fiscalité
Ne jamais déterminer une taxe uniquement via pays/province/canton. Contexte :
vendeur, acheteur, localisation, nature bien/service, date, statuts/enregistrements
fiscaux, exemptions, type de transaction. Décision fiscale versionnée + explicable.
**Snapshot fiscal immuable** par transaction ; un changement de taux futur ne
modifie jamais une transaction historique.

## 13. Swiss Country Pack — P0 (avant commercialisation sérieuse CH)
TVA suisse complète ; taux légal + méthodes de décompte ; historique/versioning
fiscal ; QR-bill 2.4 + validation QR ; ISO 20022 ; camt.052/.053/.054 ;
rapprochement bancaire ; CHF/EUR/multidevise ; archivage 10 ans ; gate GeBüV/Olico ;
FR/DE/IT/EN ; documents dans la langue du destinataire ; migration simple.
eBill + eTVA = priorités élevées post-noyau. Fiduciaire multi-mandats = différenciateur.

## 14. Standards externes
QR-bill, ISO 20022, eBill, Peppol… jamais hardcodés. Composants versionnés :
`standard`, `version`, `effective_from`, `effective_to`, `validation_rules`.
L'utilisateur ne connaît pas la version ; Meelora absorbe les changements.

## 15. Documents
Document approuvé/posté = document source traçable. Object Storage (pas base64
Mongo). Conserver : document_id, storage reference, SHA-256, version, source,
société, acteur, timestamps, audit. Jamais écrasés. Logo société canonique réutilisé
automatiquement.

## 16. Navigation
Sidebar = travail ; Avatar = identité + administration. Sidebar : mandat actif,
Accueil, modules accessibles. Sous-menus en panneaux flottants/popovers. Impression
d'app native : shell persistant, nav rapide, préchargement ciblé, cache/revalidation,
skeletons, pas de gros reload, conservation filtres/scroll/onglets, animations très
courtes, aucune fuite de contexte au changement de mandat.

## 17. Accueil société
Layout validé = référence. Accueil = landing du mandat. Registre extensible :
`company_identity`, `user_identity`, `kpis`, `quick_actions`, `recent_activity`,
`informational_items`. ≈ 5 KPI prioritaires max, selon modules + permissions
effectives. Aucun KPI inaccessible calculé/retourné.

## 18. Fiduciaires
Préparer l'expérience native PME ↔ fiduciaire : voir les mandats nécessitant
attention, traiter les exceptions, passer vite au suivant. Mesure : mandats traités
par heure.

## 19. Migration
Migration = fonctionnalité produit. Assistant depuis Bexio, KLARA, Abacus, Excel,
etc. : détecter, importer, rapprocher, demander uniquement les exceptions. Changer
pour Meelora sans reconstruire l'entreprise.

## 20. Ce que Meelora ne doit PAS devenir
Pas de : CRM commercial complet, RH généraliste, POS, e-commerce, MRP/manufacturing,
ERP généraliste, procurement enterprise complexe, fonctions « parce qu'un concurrent
les a ». Chaque fonction future doit satisfaire ≥ 1 : exigence réglementaire ;
réduction majeure du Time-to-Done ; contrôle financier nécessaire ; différenciation
stratégique mesurable ; continuité naturelle d'un module financier existant.

## 21. Gate obligatoire par tranche (répondre AVANT de valider)
1. Quelle tâche utilisateur résout-elle ?
2. Quelle est la Happy Path ?
3. Combien de décisions humaines réellement nécessaires ?
4. Peut-on préremplir davantage ?
5. Quelles exceptions doivent être visibles ?
6. L'utilisateur doit-il connaître un terme comptable pour réussir ?
7. Peut-il comprendre « Pourquoi ? »
8. En cas d'erreur, la prochaine action est-elle claire ?
9. Peut-on remonter au document/journal en ≤ 3 niveaux ?
10. Respecte-t-elle P1.13 et le Financial Core ?
11. Compatible Country Packs ?
12. Ajoute-t-elle une duplication de données/moteur ?
Échec significatif → redesign avant « terminé ».

---
### Conformité A4.1–A4.3 (déjà livré) vis-à-vis de la charte
- §7/§8 Financial Core & périodes : respectés (posting canonique P2, idempotent,
  périodes locked/closed, closed terminal, corrections par transaction liée).
- §9 P1.13 : respecté (permissions sensibles explicites supplier_payment_post /
  supplier_credit_note_*, maker-checker, backend autorité, isolation société).
- §12 Fiscalité : snapshot fiscal d'origine réutilisé pour notes de crédit (immuable).
- §15 Documents : Object Storage + SHA-256 (A4.2).
- §16/§17 Navigation & Accueil : shell persistant, lazy-loading, skeletons, registre
  KPI Accueil, badge de nav extensible (A4.3 finition).
- §10 IA : A4.4 NON démarré — gate de gouvernance requis (voir A4_PLAN.md).

### Contradictions/points de vigilance signalés (à trancher, PAS corrigés)
- **§6 REPORTING vs ACCOUNTING** : ✅ DÉJÀ conforme — `Layout.js` (l.538-544) masque
  REPORTING comme module racine quand ACCOUNTING est accessible ; Reporting vit sous
  Comptabilité → Rapports & Analyses (`acct_reports2`). Rien à changer.
- **§11 Country Packs / §12 moteur fiscal versionné** : l'architecture actuelle des
  taxes (tax_code type EXEMPT/…) devra migrer vers un Jurisdiction Engine + décision
  fiscale versionnée + contexte complet (vendeur/acheteur/nature/date/exemptions)
  avant le Swiss Country Pack (§13). À cadrer comme tranche dédiée.
- **§14 Standards versionnés** (QR-bill 2.4 / ISO 20022 camt / eBill / Peppol) : non
  encore implémentés — prérequis P0 pour la commercialisation Suisse (§13). À planifier.
- **§13 Swiss Pack** : archivage 10 ans / gate GeBüV/Olico, décompte TVA, documents
  dans la langue du destinataire : à évaluer par rapport à l'existant avant go-to-market CH.
