# GATE A4 COMPLETE — Rapport (lecture/tests uniquement) — 2026-06
Périmètre : A4.1→A4.6 de bout en bout + non-régression A2/A3/P1.13/P2. **Aucune
correction ni développement effectué.** Méthode : revue statique du code + contrôles
runtime lecture seule (curl) + preuve de tests (test_reports iter. 76→82).

## VERDICT : ✅ PASS (vert)
Aucun écart bloquant. La prochaine phase (Country Pack Suisse P0) peut démarrer.
Quelques éléments de dette technique / risques (non bloquants) listés plus bas.

---
## 1. Vérifications des invariants (PASS)
| # | Invariant | Verdict | Preuve |
|---|---|---|---|
| 1 | Une seule vérité financière P2 | ✅ | Seul `core/financial/journal.py` écrit `journal_entries`/`journal_entry_lines` (via `create_workflow_journal_entry`). Index UNIQUE `(ws, co, source_system, external_id)` → idempotence au niveau DB. Gate `_check_period_open`. |
| 2 | Aucun ledger AP/PO/FX parallèle | ✅ | AP/aging = dérivés des transactions (`ap.py:1166`), PO ne poste jamais (`po.py:13`), réévaluation FX porte l'ajustement par `AP_FX_REVAL` sans 2ᵉ solde (`fx_revaluation.py`). Aucun `insert` journal hors journal.py. |
| 3 | Quatre statuts facture cohérents | ✅ | 4 dimensions : `document_status` (draft/verified/submitted/po_missing/discrepancy/approved/rejected), `approval_status`, `posting_status`, `payment_status`. Transitions gardées (`_transition` 409). `payment_status` DÉRIVÉ. |
| 4 | Lifecycle paiement (5 états) | ✅ | `draft→prepared→authorized→executed→posted (+cancelled)` (`ap.py:444`). Seul EXECUTED alimente l'aging ; POSTED crée l'écriture. |
| 5 | PO / matching sans duplication | ✅ | `compute_matching` déterministe + tolérances versionnées ; PO ne poste pas ; `po_status ⟂ invoicing_status` ; annulation interdite si facture liée ; close explicite. |
| 6 | Paiement avant posting sans double comptabilisation | ✅ | `mark_executed` (économique) ≠ `post_payment` (GL). `post_payment` idempotent (`journal_entry_id` guard + external_id=pid). Écriture unique équilibrée. |
| 7 | Crédits & affectations sans double journal | ✅ | `post_credit_note` idempotent (external_id=cid), 1 écriture reversal-style au taux d'origine ; `allocate_advance` ne re-décaisse jamais (avance déjà en AP). |
| 8 | Aging dérivé & réconciliable | ✅ | `aging()` calculé à la volée, jamais stocké ; sépare postées vs approuvées-non-postées. Réconciliation runtime : `status=reconciled, residual=0.0`. |
| 9 | FX réalisé ≠ FX non réalisé | ✅ | Réalisé : `FX_GAIN`/`FX_LOSS` au posting paiement (`ap.py:716-719`). Non réalisé : `FX_UNREAL_GAIN`/`FX_UNREAL_LOSS`+`AP_FX_REVAL`. Comptes/écritures disjoints ; extourne A4.6 neutralise avant réalisation. |
| 10 | Aging historique ± AP_FX_REVAL = présentation GL | ✅ | `reconcile()` : équation implémentée + taxonomie anomaly/legitimate/temporal ; ponts plafonnés par facture. Vérifié residual 0. |
| 11 | Maker-checker & permissions sensibles sans bypass | ✅ | `require_sensitive_permission` : `manage`/admin n'impliquent JAMAIS une permission sensible (grant explicite, fail-closed). Maker-checker : PO (demandeur≠approbateur), réévaluation FX (préparateur≠posteur). Testé 403 (iter.82). |
| 12 | Documents/Object Storage + traçabilité au journal | ✅ (code) | `link_journal` gèle le document à l'écriture postée (lien bidirectionnel `source_document_id` ↔ `journal_entry_id`). ⚠️ voir Risque R1 (backend stockage injoignable en preview). |
| 13 | Fonctionnement intégral sans provider IA | ✅ | `extraction_gate` fail-closed : registre vide → `available:false` (runtime confirmé, `region_required:[CH,EU]`). Emergent Universal Key interdite ; clé BYO env-only ; corrections exclues de l'entraînement. Saisie manuelle 100% opérationnelle. |
| 14 | Isolation multi-société / no-leak | ✅ | Toutes les requêtes scellées `{workspace_id, company_id}`. Runtime : société inexistante → 404 (aging + réconciliation), cross_workspace → 404, sans token → 401. |
| 15 | STRAT-01 §21 (Happy Path, Exceptions First, Pourquoi ?, drill-down ≤3) | ✅ | AP Overview + Réconciliation « Réconcilié ✓ »/écarts, réévaluation Calculer→exceptions→Comptabiliser + « Pourquoi ? », drill-down ≤3 (écart→doc→journal). |
| 16 | Non-régression A2/A3/P1.13/P2 | ✅ | Endpoints A2/A3/P2 (journal, périodes, FX) réutilisés sans modification de signature ; extension FX `rate_type` non-breaking (legacy=`current`). Suites iter.76→82 vertes ; runtime AP/GL sains. |

---
## 2. Écarts (gaps) bloquants
**Aucun.**

---
## 3. Dette technique (non bloquante)
- **DT1 — Caches dérivés facture** : `ap_invoices.balance / amount_paid / credited_total`
  sont des caches recalculés par `_recompute_invoice_payment`. Ils peuvent se désynchroniser
  si des données sont écrites en contournant cette fonction (constaté sur 2 factures de seed
  dont `credited_total` était périmé — réparé pendant A4.6 via la fonction canonique).
  → Recommandation (hors Gate) : ajouter une vérification de cohérence périodique (aging vs
  transactions) OU calculer l'aging strictement à partir des sous-objets. Impact : faible.
- **DT2 — `available_credits`/ponts de réconciliation** : logique correcte mais dépendante de
  la fraîcheur des caches (DT1). Couverte par la réconciliation elle-même (détecte l'écart).
- **DT3 — Pré-câblage IA** : `ByoVisionProvider.extract_invoice` lève `ProviderNotConfigured`
  (fail-closed voulu). Le vrai appel vision reste à câbler (tranche ultérieure, sur attestation BYO).

---
## 4. Risques
- **R1 (infra, moyen)** : Object Storage — l'init échoue en preview
  (`integrations.emergentagent.com:443` timeout). Le CODE de traçabilité est correct, mais
  l'upload/download de documents (PDF factures/PO) est INDISPONIBLE dans cet environnement de
  preview. À revalider en déploiement où le backend de stockage est joignable.
- **R2 (données, faible)** : intégrité des caches dérivés (cf. DT1) — un import/seed direct peut
  fausser aging/réconciliation jusqu'au recalcul.
- **R3 (dépendances externes, faible)** : OANDA (taux `closing`) et Resend (emails) non câblés —
  en attente de clés. Sans impact sur A4 (taux saisis manuellement, fallback tracé).
- **R4 (juridiction, à cadrer)** : A4.6 utilise un seuil de fraîcheur de taux par défaut (7 j) et
  une classification monétaire par défaut ; devront être gouvernés par l'Accounting Policy /
  Country Pack (déjà prévu, non hardcodé par pays).

---
## Conclusion
Gate **VERT**. Cœur financier P2 unique et sain, aucune duplication de ledger, séparations
réalisé/non-réalisé et exécuté/posté respectées, permissions sensibles sans bypass, isolation
multi-tenant no-leak, IA fail-closed, STRAT-01 §21 respecté. Prochaine phase autorisée :
**Country Pack Suisse (P0)** — à démarrer par un cadrage soumis au Gate STRAT-01 §21.
