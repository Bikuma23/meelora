# A4.5 — CADRAGE : Bons de commande (PO) + Matching 2-way
Statut : **CADRAGE POUR VALIDATION — AUCUN CODE**. Construit sur A4.1–A4.4 + Financial
Core P2. Conforme STRAT-01 (Gate §21). **STOP après ce cadrage.**

## A. Gate STRAT-01 §21 — réponses
1. **Tâche** : sécuriser le cycle besoin→PO→approbation→envoi→facture→matching→
   approbation→posting, et permettre qu'une facture conforme se traite en **1 décision** (Approuver).
2. **Happy Path** : facture avec n° PO → association auto → matching vert → « Tout
   correspond » → **1 clic Approuver** (puis posting canonique A4.2/P2).
3. **Décisions humaines** : idéalement **1** (approuver la facture). L'approbation du PO
   en amont est une décision distincte, faite une fois par PO.
4. **Pré-remplissage** : association PO auto (société/fournisseur/devise/statut), taxes
   via moteur fiscal existant, montants facturés/solde dérivés. A4.4 (si dispo) fournit
   des hints (n° PO, lignes) mais ne décide jamais.
5. **Exceptions visibles** : PO introuvable/en attente, fournisseur/devise incohérents,
   dépassement de tolérance, sur-facturation, lignes non rapprochées « À vérifier ».
6. **Terme comptable requis ?** Non — libellés métier (« Facturé/Restant/Tout correspond »).
7. **Pourquoi ?** Oui — « Référence PO identique · Fournisseur identique · Devise
   identique · Total dans la tolérance · 3/3 lignes rapprochées ».
8. **Erreur → prochaine action** : PO introuvable → « Notifier le responsable » +
   facture reste « En attente du PO » (aucune ressaisie).
9. **Drill-down ≤ 3** : Facture → PO → ligne PO → (facture source / journal A4.2).
10. **P1.13 & Financial Core** : approbation PO = permission sensible explicite ;
    aucun ledger PO ; posting inchangé (A4.2/P2). Maker-checker.
11. **Country Packs** : A4.5 compare taxes PO vs taxes facture (affichées) ; la
    **décision fiscale reste au Jurisdiction Engine** (séparation stricte).
12. **Duplication ?** Non — réutilise fournisseurs (A4.1), facture AP (A4.2, on ajoute
    seulement des champs de lien), moteur fiscal, périodes, devises/FX, Object Storage,
    permissions, audit, registres UI. Un seul objet facture.

## B. Objet PO canonique — modèle de données (`ap_purchase_orders`)
```
{
  _id: "po_...", workspace_id, company_id,
  number,                       # unique/société (séquence PO-YYYY-####)
  supplier_id, supplier_name_snapshot,
  po_date, requested_by, po_owner_id,         # demandeur + responsable
  currency, fx (snapshot à l'approbation, réutilise moteur FX A3/A4),
  status,                       # cf. lifecycle §C
  lines: [{
    line_id: "pol_...",         # IDENTITÉ LIGNE STABLE (matching ligne)
    description, quantity, unit_price, line_net,
    tax: { components:[...], tax_total },     # via moteur fiscal existant (snapshot)
    dimensions: { project?, department?, cost_center? },
    invoiced_qty, invoiced_net,               # dérivés (cumul factures liées)
  }],
  subtotal, tax_total, total,
  note, attachments: [document_id...],        # Object Storage (réutilise A4.2/§15)
  approvers: [{ user_id, level, decided:'approved'|'rejected', at, reason }],
  approval_snapshot: { matrix_version, required_levels:[...] },
  linked_invoice_ids: [inv_...],
  invoiced_total, remaining_amount,           # dérivés des factures EXÉCUTÉES du matching
  reference,                                  # projet/interne
  created_by, created_at, audit:[...]
}
```
Règles : **aucun ledger GL** ; création/approbation d'un PO ne poste jamais au journal
(A4.5). Montants `invoiced_*`/`remaining_*` **dérivés** des factures liées (jamais un
champ éditable indépendant). Ligne PO **immuable après première facture liée** (toute
modif significative → ré-approbation + audit).

## C. Lifecycle final
```
draft ──submit──▶ submitted ──approve──▶ approved ──send──▶ sent
  │                   │                                        │
  │                   └──reject──▶ rejected (terminal)         ▼
  cancel (draft/submitted/approved non facturé)         partially_invoiced ⇄ (factures)
  ▼                                                            │
cancelled (terminal, si aucune facture liée)                  ▼
                                                        fully_invoiced ──close──▶ closed (terminal)
```
Transitions autorisées (garde) :
- draft→submitted (créateur/demandeur) ; submitted→approved|rejected (approbateur ≠
  créateur, permission) ; approved→sent ; sent→partially_invoiced (1ère facture liée) ;
  partially_invoiced→fully_invoiced (solde=0) ; fully_invoiced→closed ; * →cancelled
  UNIQUEMENT si `linked_invoice_ids` vide. Un PO avec facture liée n'est **jamais**
  réécrit destructivement — modif = nouvelle version auditée + ré-approbation si hors règles.

## D. Matrice d'approbation (fiche Société → Société/Clients)
Config par société : `company_ap_settings.po_approval_matrix` (versionnée) :
```
{ matrix_version, currency_basis:'functional',
  rules: [ { max_amount: 5000,  levels:['manager'] },
           { max_amount: 25000, levels:['finance'] },
           { max_amount: null,  levels:['cfo'] } ] }   # seuils NON hardcodés
```
- Détermine les niveaux requis selon **montant** (contre-valeur fonctionnelle si devise ≠
  fonctionnelle), extensible **département/projet/dimension**.
- Architecture multi-niveaux dès le départ (liste `levels`) ; A4.5 livre 1 niveau effectif
  minimum, la structure supporte N niveaux sans refonte.
- P1.13 : `require_sensitive_permission('accounting.po_approve')` ; **aucun bypass**
  manage/Client Admin/platform_admin. Maker-checker : le créateur/demandeur ne peut pas
  approuver un PO relevant de son propre périmètre.

## E. Politique de tolérance (config société, non hardcodée)
`company_ap_settings.match_tolerance` :
```
{ preset:'standard'|'strict'|'custom',
  amount_abs, amount_pct, price_pct, qty_abs }   # ex. standard: pct 2% & abs 50
```
UX : sélecteur « Tolérance de rapprochement : Standard ▾ » ; options avancées repliées.
Tout dépassement = **exception** (jamais accepté silencieusement) ; dérogation =
permission `accounting.po_match_override` + motif + audit.

## F. Matching 2-way (déterministe, autorité)
Comparaison PO ↔ facture A4.2 : fournisseur, devise, (lignes/qté/PU si dispo), sous-total,
taxes affichées, total, **cumul déjà facturé sur le PO**. Résultat :
`matching_status ∈ { matched, within_tolerance, exception, partial, unmatched, to_verify }`
`matching_result = { checks:[{name, ok, po_value, invoice_value}], line_map:[{invoice_line, po_line_id, status}], variance }`
- Association auto si correspondance **unique et fiable** (société active, fournisseur
  cohérent, statut approved/sent/partially_invoiced, devise compatible, solde disponible).
- Matching **au niveau ligne** via `line_id` PO stable ; mapping incertain → `to_verify`
  (jamais inventé). A4.4 propose invoice_line→po_line en hint ; le moteur déterministe tranche.
- **Anti sur-facturation** : `Σ factures liées ≤ total PO` (par ligne si possible) ;
  dépassement bloqué sauf dérogation permissionnée + audit.

## G. Diagramme PO → facture → matching → approval → posting
```
[Besoin] → PO draft → submit → approve(P1.13, matrix) → sent → (envoi fournisseur)
                                                              │
Facture AP (A4.2, saisie manuelle OU hint A4.4) ─ n° PO ─────┤
                                                              ▼
                              Association auto (société/fournisseur/devise/statut/solde)
                                                              ▼
                              MATCHING 2-way déterministe (tolérance société)
                        ┌───────────────┴────────────────┐
                   matched/within_tol                 exception/to_verify
                        │                                   │ (Exceptions First + Pourquoi?)
                        ▼                                   ▼
             Approuver facture (1 clic)          Résoudre / dérogation permissionnée
                        │                                   │
                        └───────────────┬───────────────────┘
                                        ▼
                    POSTING FACTURE = CANONIQUE A4.2/P2 (inchangé, idempotent)
        (le PO met à jour invoiced/remaining → partially/fully_invoiced ; PO ne poste JAMAIS)
```

## H. Écrans proposés (UX Exceptions First, langage grand public)
1. **Comptabilité → Bons de commande** (active le sous-menu existant) : onglets
   **Aperçu | À approuver | Bons de commande**. Aperçu = PO à approuver · PO bloquant des
   factures · PO partiellement facturés · exceptions (registre KPI compact, drill-down).
2. **Fiche PO** : entête métier (`PO 8742 · Swisscom · CHF 10'000 · Approuvé`) →
   `Facturé CHF 4'000 · Restant CHF 6'000` → Factures liées (`INV-8821 · CHF 4'000 ✓`) ;
   lignes/détails techniques secondaires (progressive disclosure).
3. **Traitement facture (dans Factures à traiter)** :
   - Conforme → carte verte « Tout correspond · PO 8742 ✓ · Approuver · Voir le détail ».
   - Exception → « 1 élément nécessite votre attention · dépasse le PO de CHF 120 » +
     actions autorisées seulement ; détail via « Voir le détail » ; « Pourquoi ? ».
   - PO introuvable → « PO 8742 pas encore disponible · Notifier le responsable » ;
     facture reste « En attente du PO » (aucune ressaisie).

## I. Impacts exacts sur l'existant
- **A4.1 (fournisseurs)** : consommer réellement `requires_po` (déjà présent). Ajout config
  société `company_ap_settings` (matrice + tolérance) — nouvelle collection, pas de refonte.
- **A4.2 (factures AP)** : AJOUTER seulement des champs sur `ap_invoices` :
  `purchase_order_id` (déjà présent, devient FK vers `ap_purchase_orders`),
  `matching_status`, `matching_result`, `po_reference_text` (n° lu). `verify` renforcé :
  si `po_required` → exiger un **PO valide existant** (plus juste une chaîne) sinon
  `po_missing`/`En attente du PO`. **Posting inchangé** (A4.2/P2).
- **A4.4 (extraction)** : fournit hints (fournisseur, n° PO, lignes, montants, taxes
  affichées) ; **ne décide jamais** le lien. A4.5 fonctionne intégralement sans A4.4.
- **P2/Financial Core** : **AUCUN changement** — le PO ne poste pas ; seul le posting
  facture A4.2 crée des écritures. Périodes/immutabilité/idempotence inchangées.
- **Permissions** : réutiliser `accounting.po_approve` (déjà au catalogue) ; **1 seule**
  nouvelle : `accounting.po_match_override` (dérogation tolérance/sur-facturation).

## J. Réutilisé (PAS dupliqué)
Fournisseurs A4.1 · objet facture A4.2 (étendu, pas recréé) · moteur fiscal (snapshot) ·
moteur FX A3/A4 · périodes/journaux P2 · Object Storage + SHA-256 (pièces jointes) ·
`require_sensitive_permission`/P1.13 · maker-checker · pattern audit (`_audit`) ·
registres UI (onglets, KPI Aperçu, badge nav, « Pourquoi ? ») · notifications existantes
(bouton « Notifier le responsable »).

## K. Permissions — matrice proposée (à valider)
| Action | Permission | Maker-checker |
|---|---|---|
| Créer/soumettre PO | ACCOUNTING contribute | créateur |
| Approuver/rejeter PO | **accounting.po_approve** (sensible) | ≠ créateur, selon matrice |
| Envoyer PO | ACCOUNTING contribute | — |
| Associer/modifier PO d'une facture | ACCOUNTING contribute (audité) | — |
| Dérogation tolérance / sur-facturation | **accounting.po_match_override** (sensible, NOUVELLE) | ≠ créateur |
| Approuver facture | accounting.supplier_invoice_approve (A4.2) | ≠ créateur |
| Poster facture | accounting.supplier_invoice_post (A4.2) | — |

## L. Non-objectifs (STRAT-01 §21)
Pas de : RFQ/sourcing, catalogues, contrats, vendor scoring, réception physique/3-way,
warehouse, MRP, engagements GL, procurement enterprise. (Décision produit ultérieure.)

## M. Tests obligatoires (au moins §22)
draft→approve→sent · maker-checker · permission approve · isolation société ·
fournisseur PO-required · PO manquant bloque facture · notifier responsable · association
auto · modif manuelle auditée · match parfait · dans tolérance · dépassement · multi-
factures · partial/full invoiced · anti sur-facturation · multidevise · A4.4 indispo →
manuel complet · aucun posting PO · posting facture canonique P2 · idempotence ·
Exceptions First · Pourquoi ?.

---
**STOP** — attendre validation (modèle, lifecycle, matrice permissions dont la nouvelle
`accounting.po_match_override`, tolérance, écrans) avant d'implémenter A4.5.
