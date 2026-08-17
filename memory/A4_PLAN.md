# GATE A4 — Achats & Fournisseurs / Accounts Payable — PLAN (2026-08-17)

> Statut : **PLAN uniquement — aucune fonction métier développée.** En attente de validation (GATE).
> Principe cardinal : A4 ⊂ ACCOUNTING. **Réutiliser le Cœur financier canonique P2 + A2.** Aucun ledger, période ou moteur comptable parallèle. A4 reflète l'architecture d'A3 (AR) transposée aux fournisseurs.

---

## 1. INVENTAIRE TECHNIQUE (canonique / réutilisable / manquant)

### ✅ Canonique & réutilisable tel quel
| Brique | Emplacement | Réutilisation A4 |
|---|---|---|
| Posting canonique P2/A2 | `core/financial/journal.py` → `create_workflow_journal_entry(...)`, `link_reversal` | Toute facture/paiement AP poste **1** journal_entry équilibré, atomique, idempotent |
| Périodes | `core/accounting/gl.py` → `_get_period`, `_assert_postable_period` | Interdit posting en période locked/closed, séquence respectée |
| Moteur fiscal versionné | `core/financial/tax_engine.py` → `default_tax_codes(jurisdiction)`, `list_tax_codes`, versions par `effective_date` | TPS/TVQ/GST/HST/PST/TVA ; snapshot fiscal par date de transaction ; pas de recalcul rétroactif |
| FX + OANDA | `core/financial/fx.py`, `core/financial/oanda.py` | Devise txn/fonctionnelle, taux/date/source, override audité, bouton « Récupérer le taux » |
| Object Storage + traçabilité | `core/financial/documents.py` → `store_document`, `download_document`, `company_branding_assets` ; `resolve_journal_source` (server) | PDF source figé + SHA-256 ; lien bidirectionnel doc↔(source_type,source_id)↔journal_entry_id |
| Accès effectif (deny-by-default) | `core/access/effective_access.py` → `resolve_effective_access` ; `core/access/sensitive.py` → `require_sensitive_permission` | Gating modules souscrits ∩ activés ∩ accès ∩ permissions |
| Catalogue permissions | `core/access/permissions_catalog.py` | Contient déjà `accounting.supplier_invoice_post`, `accounting.po_approve` |
| Patron AR complet (template AP) | `core/accounting/ar.py`, `ar_pdf.py`, `dunning.py` | Mapping GL, public model, workflow, post, paiements, notes de crédit, aging, relances → à transposer |
| Nav frontend | `Layout.js` : `acct_purchases` (« Achats & Fournisseurs ») et `acct_po` (« Bons de commande ») **déjà présents en placeholders** | Brancher les vrais écrans |
| IA / LLM | `emergentintegrations` installé + Emergent LLM key | Extraction documentaire (vision) §4 |

### ⚠️ Manquant / à créer
- **Aucun module fournisseur (AP)** : `core/accounting/` = seulement `ar.py`, `ar_pdf.py`, `dunning.py`, `gl.py`.
- **Aucun moteur Bons de commande (PO)** ni **réception** : `purchase_order` n'apparaît que dans des noms de comptes/permission `po_approve`. → **GATE §8 : le moteur PO est ABSENT.**
- **Aucune ingestion documentaire IA** : `core/financial/ingestion/readers.py` ne lit que Excel/CSV (imports comptables), pas de PDF/OCR/vision.
- **Aucune infrastructure de courriel entrant** : seul Resend **sortant** existe → l'adresse AP dédiée (§3) nécessite un fournisseur *inbound* (décision d'intégration).
- **Permissions AP incomplètes** : manquent `accounting.supplier_invoice_approve`, `accounting.supplier_payment_post`, `accounting.supplier_credit_note_approve`, `accounting.supplier_credit_note_post`.

### 🔸 Divergence d'architecture à trancher (A3 vs spec A4)
A3 (AR) utilise **un seul champ `status`** (draft→submitted→approved→posted→partially_paid→paid). La spec A4 §10 impose **4 statuts séparés** : `document_status`, `approval_status`, `posting_status`, `payment_status`. → A4 adoptera le **modèle multi-statuts explicite** (plus riche, requis par la spec). A3 n'est pas modifié.

---

## 2. MODÈLE DE DONNÉES PROPOSÉ (collections Mongo, préfixe `ap_` / `purchase_`)

Toutes les collections portent `workspace_id` + `company_id` (isolation stricte, déjà standard).

### `ap_suppliers` — fiche fournisseur (§1)
```
_id, workspace_id, company_id, code (n° fournisseur),
name (raison sociale), trade_name (nom commercial), status: active|inactive,
legal_address, remit_to_address (adresse de paiement),
contacts: [{name,email,phone,role}], primary_contact: {name},
email, phone, website, country, region, language,
default_currency, payment_terms, due_days,
tax_ids: {TPS,TVQ,PST,TVA,...}, tax_regime, tax_exemptions: [{code}],
bank_info: {iban/transit/account, ...} (chiffré/masqué), preferred_payment_method,
default_expense_account_code, default_ap_account_code,
default_dimensions: {project, department},
requires_po: bool (politique PO par fournisseur), notes,
attachments: [], credit_balance, audit(created/updated/by)
```

### `ap_invoices` — facture fournisseur (§10)
```
_id, workspace_id, company_id, number (n° fournisseur), supplier_id,
issue_date, due_date, due_date_source, currency, fx{rate,date,source,override_by},
customer_po / po_id, po_required: bool, reference,
lines: [{description, qty, unit_price, tax_code, expense_account_code, dimensions,
         is_fixed_asset_candidate: bool}],
subtotal, tax_total, total, amount_paid, balance,
tax_snapshot: [...versions figées...],
# 4 statuts séparés (§10)
document_status: received|analyzing|to_verify|po_missing|discrepancy|verified|submitted|approved|rejected
approval_status: pending|approved|rejected
posting_status: not_posted|posted
payment_status: unpaid|partial|paid|unapplied_credit
match_result: none|match|match_tolerance|discrepancy|blocked,
source_document_id, journal_entry_id, reversal_journal_entry_id,
period_id, financial_period_id, financial_year_id,
extraction: {raw, proposed, confidence_by_field, corrected_by, model, at},
duplicate_of, audit
```

### `ap_inbox_items` — boîte de réception (§2)
```
_id, ws, company_id, channel: upload|drag_drop|import|email|api,
received_at, from_email, original_document_id, filename, mime, sha256,
status (miroir document_status), extracted_invoice_id (une fois promue),
assignee_id, error, dedupe_key
```

### `ap_payments` — paiements fournisseurs (§17)
```
_id, ws, company_id, supplier_id, date (valeur), amount, currency, fx,
method, bank_reference, allocations: [{invoice_id, amount}],
unapplied_amount, realized_fx: {...}, journal_entry_id, posting_status, audit
```

### `ap_credit_notes` — crédits fournisseurs (§19)
```
_id, ws, company_id, supplier_id, source_invoice_id, lines, subtotal, tax_total, total,
tax_snapshot, document_status, approval_status, posting_status, journal_entry_id, audit
```

### `ap_gl_mapping` — mapping GL AP (miroir `sales_gl_mapping`)
```
default_ap_account_code (Fournisseurs / créditeurs), default_expense_account_code,
recoverable_tax_account_code, rounding_account_code, fx_gain_loss_account_code
```

### `ap_dunning`/notify → **`ap_po_notifications`** (§6 « Notifier le responsable du PO »)
```
_id, ws, company_id, invoice_id, requested_by, sent_to (po_owner), message,
sent_at, status: sent|acknowledged|resolved
```

### `purchase_orders` (sous-module PO — §8, à valider — voir §6 du plan)
```
_id, ws, company_id, number, supplier_id, owner_id (responsable),
status: draft|approved|received|closed|cancelled, currency,
lines: [{description, qty, unit_price, tax_code, received_qty}],
subtotal, tax_total, total, approval_status, audit
```
> **A4 lit/recherche/matche un PO** ; il ne construit PAS tout le moteur Procurement. Voir §6.

### `ap_match_config` — tolérances de matching par société (§7)
```
amount_abs_tolerance, amount_pct_tolerance, qty_tolerance, misc_charges_tolerance
```

### `ap_approval_matrix` — matrice d'approbation par société (§9, data-driven, PAS de `if`)
```
rules: [{seq, min_amount, max_amount, department, project, entity, category,
         supplier_id, purchase_type, level, approver_id, backup_approver_id}]
```

---

## 3. WORKFLOW COMPLET

```
INGESTION            TRAITEMENT                         COMPTABILISATION      PAIEMENT
upload/email/import → received → analyzing (IA) →       (séparé, permission)  (indépendant)
                      to_verify → [dedupe] →            posting_status:       payment_status:
                      [PO required? →                     not_posted→posted    unpaid→partial→paid
                        po_missing (notifier)|           via                   allocations
                        matching 2-way →                 create_workflow_
                        match|tolerance|discrepancy] →   journal_entry
                      verified → submitted →
                      approved (matrice + maker-checker) → REJETÉ possible à toute étape
```
- **Approuvée & payée sans être posted** = autorisé (§10/§17). `posting_status` et `payment_status` indépendants.
- Posting AP canonique (§15) : `Dr Charge/Actif · Dr Taxes récupérables · Cr Fournisseurs` → 1 journal_entry P2 équilibré/atomique/idempotent, lié à `financial_periods`.
- Paiement avant posting : à la comptabilisation ultérieure, ne jamais double-compter le paiement (miroir de la mécanique A3).
- Immobilisation détectée (§16) : ligne flaguée `is_fixed_asset_candidate` → si `FIXED_ASSETS` acquis, proposer lien/transfert ; sinon reste comptabilisable dans ACCOUNTING, infos conservées pour transition future.

---

## 4. MATRICE PERMISSIONS (§11)

| Action | Permission (catalogue) | Statut |
|---|---|---|
| Créer/soumettre facture fournisseur | ACCOUNTING contribute | existe (module level) |
| Approuver facture fournisseur | `accounting.supplier_invoice_approve` | **À AJOUTER** |
| Comptabiliser (post) facture fournisseur | `accounting.supplier_invoice_post` | existe |
| Approuver PO | `accounting.po_approve` | existe |
| Comptabiliser paiement fournisseur | `accounting.supplier_payment_post` | **À AJOUTER** |
| Approuver/poster crédit fournisseur | `accounting.supplier_credit_note_approve` / `_post` | **À AJOUTER** |

- **Maker-checker** : le créateur ne peut jamais approuver sa propre facture.
- `manage`, `Client Admin`, `platform_role` **ne confèrent aucune** permission financière sensible → tout passe par `require_sensitive_permission`.
- Matrice d'approbation = data-driven (`ap_approval_matrix`), évaluée par un moteur de règles générique (montant/dept/projet/entité/catégorie/fournisseur/type), séquence + suppléant.

---

## 5. ARCHITECTURE INGESTION PDF / EMAIL / IA (§2, §3, §4)

- **Upload / drag&drop / import** : endpoint `POST /companies/{cid}/ap/inbox` (chunked pour contourner les limites proxy) → `store_document(source_type="ap_inbox")` → item `ap_inbox_items(status=received)`.
- **Courriel dédié (§3)** : alias `factures+<company-alias>@<domaine>` → nécessite un **fournisseur inbound** (Resend Inbound / Postmark / SendGrid Inbound Parse / Mailgun Routes) via webhook `POST /webhooks/ap-email`. Sécurité : SPF/DKIM/DMARC (anti-spoofing), whitelist types MIME (PDF/PNG/JPG), antivirus/refus exécutables, dédup par SHA-256, **résolution société par alias** (jamais par adresse perso). → **DÉCISION D'INTÉGRATION requise** (choix du fournisseur + domaine).
- **Extraction IA (§4)** : service `core/accounting/ap_extraction.py` utilisant `emergentintegrations` (LLM key) avec modèle **vision** (GPT ou Gemini) → JSON structuré {fournisseur, n°, dates, devise, PO, lignes, taxes, totaux, coordonnées fiscales} + **confidence par champ**. L'IA **ne comptabilise jamais** ; champs à faible confiance signalés ; conservation document original + extraction + corrections + audit.

---

## 6. ARCHITECTURE PO / MATCHING (§7, §8)

- **GATE §8 — moteur PO ABSENT.** A4 a besoin de : lire un PO, rechercher, afficher le responsable, matcher, connaître le statut, utiliser lignes/montants.
- **Option retenue proposée** : construire un **sous-module PO minimal** (`purchase_orders`) suffisant pour le matching AP (création/approbation/lecture/lignes/statut/responsable), **sans** moteur Procurement complet (pas de sourcing, contrats, réceptions avancées). Le **3-way matching** (PO↔Réception↔Facture) est **préparé architecturalement** (champ `received_qty`, collection `ap_receptions` prévue) mais **différé** (réception = A4.x ultérieur).
- **2-way matching** (PO↔Facture) : comparer fournisseur, articles, quantités, prix, devise, taxes, frais, total avec **tolérances configurables** (`ap_match_config`, jamais hardcodé). Résultat : `match | match_tolerance | discrepancy | blocked`.
- **Règle PO obligatoire (§6)** : si `po_required` et aucun PO → `document_status=po_missing`, reste dans la boîte, aucun posting, bouton **Notifier le responsable** (`ap_po_notifications`). À l'arrivée du PO, retour automatique au matching. Exemptions par catégorie/fournisseur si la politique société l'autorise (`requires_po=false`).

---

## 7. DÉCOUPAGE D'IMPLÉMENTATION

- **A4.1 — Référentiel fournisseurs** : `ap_suppliers` + fiche 7 sections (Général | Adresses & contacts | Facturation & paiement | Fiscalité | Comptabilité | Documents | Historique) + proposition fiscale par juridiction (réutilise tax_engine). *Livrable testable autonome.*
- **A4.2 — Facture fournisseur (saisie manuelle) + posting canonique** : `ap_invoices` (4 statuts), mapping `ap_gl_mapping`, workflow received→approved, posting P2 (`create_workflow_journal_entry`), maker-checker, permissions `supplier_invoice_approve/post`, PDF source figé, traçabilité doc↔journal, multidevise + OANDA, snapshot fiscal.
- **A4.3 — Paiements fournisseurs + Aging** : `ap_payments` (partiel/multiple, avant posting, FX réalisé), `ap_credit_notes`, aging (Courant/1-30/31-60/61-90/90+), drill-down.
- **A4.4 — Boîte de réception + ingestion + IA** : `ap_inbox_items`, upload/drag&drop/import, extraction IA + confiance, dédup (§5).
- **A4.5 — PO minimal + matching 2-way + règle PO obligatoire + notifier responsable** (§6/§7/§8).
- **A4.6 — Matrice d'approbation data-driven** (§9) + moteur de règles.
- **A4.7 — Courriel AP dédié entrant** (§3, dépend de la décision fournisseur inbound).
- **A4.8 (préparé, différé)** : réception + 3-way matching ; hooks Immobilisations/Stock (§16/§20).
- **UX (transverse)** : nav `acct_purchases` → onglets **Aperçu | Factures à traiter | Fournisseurs | Factures | Paiements | Crédits | Aging** (langage Meelora, drill-down, peu d'actions simultanées).

---

## 8. RISQUES / MIGRATIONS / DÉCISIONS À VALIDER

1. **Statuts multiples (§10)** : A4 adopte 4 statuts séparés alors qu'A3 a un statut unique → cohérence conceptuelle à assumer (pas de migration A3, modèles distincts). **[à valider]**
2. **Moteur PO absent (§8)** : construire un PO minimal dans A4.5 (option proposée) vs attendre un futur module Procurement. **[à valider]**
3. **Courriel AP entrant (§3)** : choix du fournisseur inbound (Resend Inbound / Postmark / SendGrid / Mailgun) + domaine + clés. Sans cela, A4.7 reste désactivé (upload/import fonctionnent). **[décision + clés requises]**
4. **Modèle IA (§4)** : choix du modèle vision (GPT vs Gemini via Emergent LLM key). Coût par page. **[à valider]**
5. **Infos bancaires fournisseur (§1)** : stockage sensible (chiffrement/masquage) — décision de conformité. **[à valider]**
6. **Permissions à ajouter** : `supplier_invoice_approve`, `supplier_payment_post`, `supplier_credit_note_approve/post` (non sensible = aucun bypass admin). Aucune migration destructive.
7. **Aucune modification** d'A3/A2/P2/P1.13 : A4 est purement additif.

---
**STOP — fin du plan A4. En attente de validation avant tout développement métier.**

---

## DÉCISIONS DE VALIDATION (GATE A4 — 2026-08-17)
1. **Statuts** : A4 adopte **4 statuts séparés** (document/approval/posting/payment). A3 inchangé. ✅
2. **Moteur PO** : construire un **PO minimal en A4.5** (créer/approuver/lire/rechercher/lignes/statut/responsable + matching 2-way) ; 3-way (réception) préparé mais différé. ✅
3. **Courriel AP entrant (§3)** : **reporté (A4.7)** ; livrer d'abord upload / drag&drop / import. ✅
4. **IA extraction (§4)** : **GPT vision** via clé Emergent — SOUS RÉSERVE de la politique de gouvernance ci-dessous.
5. **Ordre** : A4.1 → A4.2 → … (chaque tranche testée). ✅

## POLITIQUE DE GOUVERNANCE IA MEELORA (obligatoire — s'applique à TOUTE fonctionnalité IA)
> **GATE avant A4.4** : vérifier que la configuration Emergent/GPT réellement utilisée satisfait ces exigences. Ne PAS supposer que « GPT » les garantit. Si non établissable → **STOP et signaler**.
- **Non-entraînement** : les données/documents/images/factures/prompts/résultats Meelora ne doivent jamais servir à entraîner, fine-tuner, améliorer un modèle partagé, constituer un dataset externe, à l'apprentissage croisé entre tenants, ni à une réutilisation commerciale par le fournisseur. Aucun apprentissage implicite inter-tenants.
- **Corrections humaines** : conservées dans les données/audits de la société, jamais transformées automatiquement en données d'entraînement.
- **Minimisation** : n'envoyer au modèle que le document + infos strictement nécessaires ; jamais mots de passe/tokens/credentials/données d'autres sociétés/contexte global. Isolation workspace/company préservée avant/pendant/après.
- **Abstraction fournisseur** : créer `DocumentAIProvider` (ne pas coupler A4 à GPT). Le provider expose sa gouvernance : politique d'usage des données, rétention, région (si dispo), capacités de suppression. Un fournisseur ne garantissant pas le non-entraînement **n'est pas activable**.
- **Rétention** : le document original reste dans l'Object Storage canonique Meelora (jamais le fournisseur IA comme archive). Privilégier zero/minimal retention côté fournisseur.
- **Audit** (par analyse, sans secrets) : provider | modèle/version | timestamp | document_id | company_id | request_id | résultat/statut | confidence | corrections humaines.
- **Autorité** : l'IA propose (extraire/classifier/rapprocher/suggérer une écriture) ; elle n'approuve/poste/paie jamais et ne contourne aucune permission sensible.

## AVANCEMENT A4
- [x] **A4.1 — Référentiel fournisseurs** (2026-08-17) : `core/accounting/ap.py` (CRUD `ap_suppliers`, masquage bancaire `_mask_bank`), endpoints `GET/POST/PATCH /companies/{cid}/ap/suppliers` (scopes ACCOUNTING read/write), permissions AP additionnées au catalogue, écran `PurchasesAP.js` (onglets Aperçu | Factures à traiter | Fournisseurs | Factures | Paiements | Crédits | Aging ; fiche 7 sections ; contacts multiples + principal ; proposition fiscale par juridiction ; PO obligatoire par fournisseur), nav `acct_purchases` branché. **Testé : backend 100 % (6/6), frontend 100 %** (iteration_74). Isolation + refus d'accès validés.
- [x] **A4.2 — Facture fournisseur + workflow + posting canonique** (2026-08-17) : `ap.py` (facture `ap_invoices` à **4 statuts séparés** document/approval/posting/payment ; workflow draft→verified→submitted→approved/rejected ; posting séparé) + `ap_gl_mapping` (codes logiques AP/EXPENSE/TAX_RECOVERABLE) + `check_duplicate` + règle PO obligatoire + upload PDF source (Object Storage, `source_document_id`+sha256) + snapshot fiscal + FX/OANDA (jamais fallback 1) + échéance auto depuis conditions fournisseur. Posting canonique P2 (`create_workflow_journal_entry`) : Dr charge/actif · Dr taxes récupérables · Cr fournisseurs — atomique, équilibré, idempotent, périodes locked/closed respectées. Permissions `supplier_invoice_approve`/`supplier_invoice_post` via `require_sensitive_permission` + maker-checker (aucun bypass). UI `PurchasesAP.js` : onglets **Factures** et **Factures à traiter** activés (formulaire création, actions workflow, upload PDF, badges statut/PO/PDF). **Testé : backend 100 % (13/13), frontend 100 %** (iteration_75) — doublon bloquant, PO manquant, maker-checker, permission denied, posting équilibré/idempotent, immutabilité, isolation, FX requis. Warning React dev-only `<span> in <option>` (cosmétique, non bloquant). **STOP après A4.2.**
- [ ] A4.3 Paiements + Aging · A4.4 Boîte de réception + IA (GATE gouvernance) · A4.5 PO minimal + matching 2-way + règle PO · A4.6 Matrice d'approbation · A4.7 Courriel AP entrant · A4.8 Réception + 3-way (différé).

