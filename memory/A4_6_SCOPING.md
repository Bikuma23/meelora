# A4.6 — CADRAGE : Réévaluation FX non réalisée + Réconciliation Aging AP ↔ Grand Livre
Statut : **CADRAGE POUR VALIDATION — AUCUN CODE**. Construit sur A4.1–A4.5 + Financial
Core P2. Conforme STRAT-01 (Gate §21, §7 Financial Core, §8 Périodes, §9 P1.13, §10 IA,
§11/§12 Country Packs & fiscalité). **STOP après ce cadrage — attendre validation avant tout dev.**

> Décisions de politique validées par le client (ask_human) :
> 1. **Taux** : « Les deux » — priorité au taux `closing`, fallback traçable au dernier taux ≤ date, jamais silencieux ; snapshot immuable par run ; fraîcheur douteuse → exception.
> 2. **Comptabilisation** : toujours calculable/affichable sans impact GL ; posting = action humaine sensible (`accounting.fx_revaluation_post`) ; extourne auto-préparée pour la période suivante, liée bidirectionnellement ; jamais de contournement.
> 3. **Soldes** : classification canonique `monetary | non_monetary` (déterministe, explicable, auditée, jamais l'IA) — pas de `if document_type == advance`.
> 4. **Comptes** : `FX_UNREAL_GAIN` / `FX_UNREAL_LOSS` (P&L) + `AP_FX_REVAL` (bilan) distincts du réalisé A4.3 ; le compte de contrôle fournisseurs historique n'est jamais touché.
> 5. **Permission** : NOUVELLE `accounting.fx_revaluation_post` (sensible, maker-checker), pas de réutilisation de `supplier_invoice_post`, pas de couplage à une permission de clôture.

---
## A. Gate STRAT-01 §21 — réponses
1. **Tâche** : présenter les dettes fournisseurs en devise étrangère à leur juste valeur à une
   date de reporting (réévaluation FX non réalisée) ET prouver en un coup d'œil que le
   sous-registre AP (Aging) concorde avec le Grand Livre. Deux tâches sœurs, une seule vérité.
2. **Happy Path** :
   - Réévaluation : ouvrir « Réévaluation FX » → **Calculer** → si tout est net « Rien à signaler,
     N positions » → **1 clic Comptabiliser** (posting P2 + extourne préparée pour le mois suivant).
   - Réconciliation : ouvrir « Réconciliation AP » → si tout concorde afficher **« Réconcilié ✓ »**
     (aucune action). Sinon n'afficher QUE les écarts nécessitant une action.
3. **Décisions humaines** : idéalement **1** par exécution (Comptabiliser la réévaluation). La
   réconciliation est **0 décision** quand tout concorde (état « Réconcilié ✓ »).
4. **Pré-remplissage** : positions AP ouvertes, taux de clôture, montants historiques/clôture,
   écart calculé, comptes de réévaluation — tout dérivé des transactions canoniques + du mapping
   société. L'utilisateur ne saisit rien manuellement dans le cas normal (Smart Defaults, Zero Duplicate).
5. **Exceptions visibles** : taux manquant/périmé pour la date, taux `closing` absent (fallback
   utilisé), position dont la classification monétaire est ambiguë, écart Aging↔GL non expliqué
   par une cause légitime connue, réévaluation déjà postée pour la période (double bloqué),
   période locked/closed empêchant le posting.
6. **Terme comptable requis ?** Non — libellés grand public (« Différence de change non encore
   réalisée », « Concordance avec la comptabilité »). Le mot « réévaluation » est expliqué via « Pourquoi ? ».
7. **Pourquoi ?** Oui — chaque montant explique : « Solde ouvert 10 000 EUR · taux d'origine 0.95 =
   9 500 CHF · taux de clôture 0.92 = 9 200 CHF · différence non réalisée −300 CHF (perte) · taux
   source : BCE clôture 2026-06-30 ». Fallback de taux explicitement mentionné s'il a lieu.
8. **Erreur → prochaine action** : taux périmé → « Mettre à jour le taux de clôture » ; période
   locked → « Demander l'ouverture / choisir la période ultérieure » ; classification ambiguë →
   « Confirmer la nature (monétaire / non monétaire) ». Every Error Has a Next Action.
9. **Drill-down ≤ 3** :
   - Réévaluation : Écart FX (chiffre) → position AP source (facture/crédit) → taux & calcul.
   - Réconciliation : Solde GL compte fournisseurs → ligne d'écart (catégorie) → facture/paiement/
     journal source. **≤ 3 niveaux garantis.**
10. **P1.13 & Financial Core** : posting réévaluation = permission sensible explicite
    `accounting.fx_revaluation_post` (aucun bypass) ; **aucun ledger AP parallèle** (§O) ; posting
    canonique P2 idempotent ; périodes locked/closed respectées ; corrections par transaction liée.
11. **Country Packs** : la **méthode** de réévaluation et la **classification monétaire** sont
    gouvernables par l'Accounting Policy / Country layer (§11/§12) — jamais de `if canton/pays`
    dans A4.6. Les comptes sont des **rôles canoniques** mappés par société, jamais des numéros hardcodés.
12. **Duplication ?** Non — réutilise l'aging existant (A4.3), le moteur FX (A3), les périodes/
    journaux P2, le mapping AP, les permissions/audit, les registres UI. **Une seule vérité** ; le
    calcul de réévaluation est **dérivé** (jamais un solde AP stocké en double).

---
## B. Principe directeur — la double vérité qui reste UNE vérité
- Le **sous-registre AP (Aging)** reste valorisé **au taux historique** de chaque transaction
  (comme aujourd'hui, A4.3 l. 943-980). On n'y touche pas.
- La **réévaluation FX non réalisée** est portée **séparément** par `AP_FX_REVAL` (bilan) — elle
  n'écrase JAMAIS le solde du compte de contrôle fournisseurs historique.
- **Équation de présentation** (cœur de la réconciliation) :

  ```
  Aging AP (taux historique)  +/−  Solde AP_FX_REVAL  =  Position AP GL au taux de clôture
  ```

  Un écart expliqué exclusivement par `AP_FX_REVAL` est une **différence légitime**, pas une anomalie.

---
## C. Source & snapshot du taux (décision 1 — « Les deux »)
### C.1 Extension `exchange_rates` (extensible, non-breaking)
Ajouter un champ **`rate_type ∈ { current, closing }`** (défaut `current`) au document existant
`exchange_rates` (fx.py l. 30-33). Aucune migration destructive : les taux existants restent `current`.
```
exchange_rates: { ..., rate_type: 'current'|'closing', reference?: str, version?: int }
```
OANDA (clé en attente) alimentera plus tard cette même table en `current` et/ou `closing` **sans
modifier A4.6**.

### C.2 Résolution du taux de réévaluation (déterministe, traçable)
Pour `(from_currency → functional, as_of)` :
1. Chercher le meilleur taux **`rate_type='closing'`** avec `rate_date <= as_of` (le plus proche).
2. Sinon → **fallback** : dernier taux `current` `rate_date <= as_of` (logique `get_rate` existante).
3. Le fallback est **toujours** exposé dans « Pourquoi ? » (« taux de clôture indisponible — dernier
   taux courant du 2026-06-28 utilisé ») — **jamais silencieux**.
4. **Fraîcheur douteuse** (aucun taux ≤ as_of, ou écart de fraîcheur > seuil configurable société) →
   **EXCEPTION** `rate_stale` nécessitant validation humaine. On n'invente ni n'accepte
   automatiquement un taux.

### C.3 Snapshot immuable par run (jamais recalculé après coup)
Chaque exécution fige, par devise et par position :
```
rate_snapshot: {
  requested_date,          # date de réévaluation demandée (as_of)
  effective_rate_date,     # rate_date réellement retenu
  rate,                    # taux appliqué
  source,                  # 'BCE' | 'OANDA' | 'manual' | ...
  rate_type,               # 'closing' | 'current' (si fallback)
  is_fallback: bool,       # true si fallback current
  reference, version       # traçabilité du taux
}
```
Un changement de taux futur ne modifie JAMAIS une réévaluation historique (STRAT-01 §12, immutabilité).

---
## D. Classification monétaire canonique (décision 3 — « Something else »)
Introduire une classification **explicite, déterministe, auditée** portée par chaque position AP
ouverte — **jamais** un `if document_type == advance`, **jamais** l'IA (§10).
```
monetary_classification: 'monetary' | 'non_monetary'
classification_reason:   str      # explicable via « Pourquoi ? »
classified_by:           'policy' | 'human_override'
policy_version:          int      # gouvernable par Country/Accounting Policy layer plus tard
```
Règles par défaut (gouvernables ultérieurement, non hardcodées par type) :
| Position AP ouverte | Nature | Réévaluée ? |
|---|---|---|
| Facture fournisseur **postée** encore ouverte (solde > 0) | monétaire | **Oui** (solde ouvert seulement) |
| Note de crédit fournisseur **postée** ouverte | monétaire | **Oui** |
| Solde résiduel après paiement partiel | monétaire | **Oui** (uniquement le solde ouvert) |
| Avance/acompte = droit à **recevoir un bien/service** | non monétaire | **Non** |
| Avance **remboursable** / droit à un montant fixe de monnaie | monétaire | **Oui** |
- Position **ambiguë** → EXCEPTION `classification_ambiguous` → l'humain confirme (override audité).
- La classification est explicable (« Pourquoi ? ») et versionnée ; elle n'affecte jamais le montant
  historique déjà réglé.

---
## E. Méthode de calcul du FX non réalisé à une date donnée
Pour chaque position AP **monétaire, postée, en devise ≠ fonctionnelle, à solde ouvert > 0** au `as_of` :
```
open_balance_ccy      = solde ouvert en devise de transaction (dérivé des transactions canoniques)
historical_value_func = open_balance_ccy × taux_historique_de_la_position      # déjà au GL
closing_value_func    = open_balance_ccy × taux_de_clôture (§C.2)
unrealized_delta_func  = closing_value_func − historical_value_func
```
- `unrealized_delta_func > 0` sur une **dette** (AP) ⇒ la dette « coûte plus cher » ⇒ **perte** non
  réalisée (et inversement, gain). Le signe est explicité dans « Pourquoi ? ».
- **Seuls les soldes OUVERTS** sont réévalués ; la portion déjà réglée a produit du **FX réalisé A4.3**
  et n'est jamais recyclée (§H séparation stricte).
- Positions en devise fonctionnelle → `unrealized_delta = 0` (identité, ignorées).
- Résultat agrégé par compte de contrôle fournisseurs, par devise, avec la liste des positions
  sources (pour drill-down §M).

### E.1 Traitement facture / crédit / avance / paiement partiel multidevise (décision 2 requirement)
- **Facture** : solde ouvert = total − crédits postés alloués − allocations de paiement exécutées
  (réutilise `_invoice_open_balance` A4.3, l. 498-533). Réévalué au solde ouvert.
- **Note de crédit** ouverte : réévaluée en sens opposé (réduit la dette nette).
- **Paiement partiel** : seul le **reste** ouvert est réévalué ; la part payée a déjà généré le FX
  réalisé au posting du paiement (A4.3 `post_payment`, l. 667-724).
- **Avance/acompte** : selon `monetary_classification` (§D) — non monétaire ⇒ exclue ; monétaire
  remboursable ⇒ incluse.

---
## F. Modèle de données (dérivé — AUCUN solde AP dupliqué)
### F.1 `ap_fx_revaluations` (en-tête de run, une par (société, période, as_of))
```
{
  _id: "fxrev_...", workspace_id, company_id,
  as_of,                          # date de réévaluation
  financial_year_id, financial_period_id,
  functional_currency,
  status,                         # cf. lifecycle §G
  rate_snapshots: [ { currency, ...§C.3 } ],   # 1 par devise réévaluée
  totals: { by_currency:[{currency, historical_func, closing_func, delta_func}], net_delta_func },
  positions: [ {                  # DÉRIVÉ — photo des soldes ouverts au calcul (jamais LA source)
      position_type:'invoice'|'credit_note', source_id, source_number, supplier_id,
      currency, open_balance_ccy, historical_rate, historical_func,
      closing_rate, closing_func, delta_func,
      monetary_classification, classification_reason,
      journal_entry_id_source,    # ancre drill-down vers l'écriture d'origine
  } ],
  exceptions: [ { code:'rate_stale'|'classification_ambiguous'|'period_locked'|..., ref, message } ],
  revaluation_journal_entry_id: null,   # posting P2 (rempli à Comptabiliser)
  reversal_journal_entry_id: null,      # extourne P2 (période suivante)
  reversal_prepared_for_period_id: null,
  prepared_by, calculated_at,
  posted_by, posted_at,
  created_at, audit: [...]
}
```
Règles : les `positions` sont une **photo dérivée** au moment du calcul (traçabilité), **jamais** une
source de solde concurrente — la vérité reste les transactions canoniques + le journal P2.

### F.2 `ap_reconciliations` (rapport de réconciliation — dérivé, jamais un solde stocké)
```
{
  _id: "aprec_...", workspace_id, company_id, as_of,
  ap_control_accounts: [ acct_code... ],   # comptes de contrôle fournisseurs (mapping société)
  gl_balance_func,                          # solde GL agrégé des comptes de contrôle
  subledger_aging_func,                     # total Aging au taux historique (A4.3)
  ap_fx_reval_balance_func,                 # solde AP_FX_REVAL
  expected_gl = subledger_aging_func + ap_fx_reval_balance_func,
  differences: [ { category, amount_func, items:[{ref, drill}] } ],
  status: 'reconciled' | 'differences',
  computed_at
}
```

### F.3 Mapping comptable (rôles canoniques — extension `company_ap_mapping`)
Réutiliser le mapping AP existant (ap.py l. 133-159) et ajouter les **rôles** (pas des numéros) :
```
company_ap_mapping: { ...,
  fx_unrealized_gain_account_code,   # rôle FX_UNREAL_GAIN
  fx_unrealized_loss_account_code,   # rôle FX_UNREAL_LOSS
  ap_fx_reval_account_code           # rôle AP_FX_REVAL (bilan)
}
```
Distincts des rôles réalisés existants `fx_gain_account_code=FX_GAIN` / `fx_loss_account_code=FX_LOSS`.

---
## G. Lifecycle de la réévaluation
```
draft(calculated) ──post(sensible)──▶ posted ──(période suivante)──▶ reversed
        │                                 │
        │ (recalcul autorisé tant que      └─ reversal_journal_entry lié bidirectionnellement
        │  non postée : remplace le draft)
        ▼
   cancelled (terminal, si non postée)
```
- **calculated** : run calculé, non posté, aucune écriture GL. Peut être recalculé/annulé librement.
- **posted** : écriture P2 de réévaluation créée (§I) ; extourne **préparée** pour la période suivante.
- **reversed** : extourne postée (automatiquement selon politique société, sinon manuellement),
  liée à la réévaluation d'origine.
- Un seul run **posté** par (société, compte de contrôle, as_of, période) — cf. idempotence §K.

---
## H. Séparation stricte FX réalisé (A4.3) / FX non réalisé (A4.6)
- **Réalisé (A4.3)** : constaté au **posting d'un paiement** (extinction réelle), comptes
  `FX_GAIN`/`FX_LOSS`, sur la portion **réglée**.
- **Non réalisé (A4.6)** : estimation sur soldes **ouverts** à une date, comptes
  `FX_UNREAL_GAIN`/`FX_UNREAL_LOSS` + `AP_FX_REVAL`, **extournée** à la période suivante.
- **Règle absolue** : une réalisation ultérieure (paiement) **ne recycle jamais**
  `FX_UNREAL_GAIN/LOSS` en gain/perte réalisé. Les deux flux ne partagent aucun compte et aucune
  écriture. L'extourne A4.6 neutralise le non réalisé avant que le réalisé A4.3 ne s'applique.

---
## I. Écritures P2 — réévaluation & extourne
> Toutes via `journal_service.create_workflow_journal_entry` (journal.py l. 387+), balancées en
> devise fonctionnelle, statut `posted`, période **open** requise. **Le compte de contrôle
> fournisseurs historique n'est jamais mouvementé.**

**Réévaluation (perte non réalisée nette, `net_delta > 0` = dette plus chère)** :
```
Dr  FX_UNREAL_LOSS         net_delta_func
    Cr  AP_FX_REVAL             net_delta_func
source_type = "ap_fx_revaluation", source_system = "purchases"
```
**Réévaluation (gain non réalisé net)** :
```
Dr  AP_FX_REVAL            net_delta_func
    Cr  FX_UNREAL_GAIN         net_delta_func
```
**Extourne (période suivante)** : **exactement les mêmes comptes en sens inverse**, via
`create_workflow_journal_entry(..., reverses_journal_entry_id=<reval_je>)` + `link_reversal`
(journal.py l. 449-457) pour le lien **bidirectionnel** (`reverses_journal_entry_id` /
`reversed_by_journal_entry_id`).
- Aucune écriture ne modifie les factures/paiements/écritures historiques (immutabilité §7).
- Écritures **atomiques** : le posting réévaluation + la préparation de l'extourne réussissent
  ensemble ou échouent ensemble.

---
## J. Comportement aux périodes open / locked / closed (décision 6)
Réutilise `_assert_postable_period` (gl.py) + la machine d'état des périodes (periods.py, `closed`
terminal) — **aucun contournement** :
- **Calcul** (status `calculated`) : autorisé quelle que soit la période (aucun GL) — utile pour
  consulter un run passé/verrouillé.
- **Posting réévaluation** : période cible **open** obligatoire. Locked/closed → EXCEPTION
  `period_not_postable` + prochaine action.
- **Extourne** : période suivante **open** requise. Si la période suivante n'existe pas encore ou
  n'est pas ouverte → l'extourne reste **préparée** (`reversal_prepared_for_period_id`) et sera
  postée dès son ouverture, selon la politique société. Aucune écriture forcée dans une période fermée.
- **Correction post-clôture** : jamais de réouverture (§8) ; corriger via un nouveau run daté sur
  une période ultérieure, tracé.

---
## K. Idempotence & prévention des doubles réévaluations (décision 7)
- **Clé d'unicité** : au plus **une** réévaluation en statut `posted` par
  `(workspace_id, company_id, ap_control_account, as_of, financial_period_id)`. Toute tentative de
  double posting → refus `already_revalued` (exception visible, prochaine action « Voir le run existant »).
- Poster deux fois le **même** run est **no-op** (retourne l'écriture existante) — même pattern que
  `post_invoice`/`post_payment` (idempotents, l. 384-388 / 672-676).
- L'extourne est idempotente (une seule par réévaluation, protégée par `reversal_journal_entry_id`).
- Le **recalcul** avant posting remplace le draft (aucune écriture) — pas de multiplication de runs postés.

---
## L. Réconciliation Aging AP ↔ compte(s) fournisseurs GL (décision 9 & 10)
### L.1 Méthode
```
1. subledger_aging_func   = total Aging AP au taux historique (A4.3 aging(), postées uniquement)
2. gl_balance_func        = Σ soldes des comptes de contrôle fournisseurs au GL (P2) au as_of
3. ap_fx_reval_balance    = solde du compte AP_FX_REVAL au as_of
4. expected_gl            = subledger_aging_func + ap_fx_reval_balance
5. residual               = gl_balance_func − expected_gl
```
Si `residual ≈ 0` (tolérance d'arrondi) ⇒ **« Réconcilié ✓ »**.

### L.2 Taxonomie des écarts (différences temporelles / légitimes / anomalies)
| Catégorie | Nature | Exemple | Traitement UX |
|---|---|---|---|
| **Différence temporelle** | En attente, se résorbe seule | Facture **approuvée non postée** (dans le GL nulle part), paiement **exécuté non posté** | Informative, « en attente de comptabilisation » — pas une anomalie |
| **Différence légitime** | Expliquée par une écriture connue | Solde `AP_FX_REVAL` (réévaluation non extournée), ajustement manuel tracé | Expliquée + drill-down, pas d'action requise |
| **Anomalie** | Écart **inexpliqué** | Écriture directe au compte de contrôle hors sous-registre, écart d'arrondi anormal, écriture orpheline | **Exception** nécessitant action, en tête de liste |
- L'aging A4.3 distingue déjà `accounting` (postées) vs `approved_unposted` (l. 969-974) → la
  différence temporelle « approuvée non postée » est déjà calculable, réutilisée telle quelle.

### L.3 UX Exceptions First (décision 12)
- **Tout concorde** → carte unique **« Réconcilié ✓ · N fournisseurs · CHF X au TT.MM.AAAA »**,
  détails repliés (Progressive Disclosure).
- **Écarts** → n'afficher QUE les lignes d'écart, **anomalies en premier**, chacune avec « Pourquoi ? »
  et sa prochaine action. Les différences temporelles/légitimes sont listées en second, en lecture seule.

---
## M. Drill-down ≤ 3 niveaux (décision 11)
- **Réévaluation** : `Écart FX non réalisé (chiffre)` → `position AP source (facture/crédit + solde
  ouvert)` → `taux & calcul (snapshot §C.3)`. (3 niveaux)
- **Réconciliation** : `Solde GL compte fournisseurs` → `ligne d'écart (catégorie L.2)` →
  `facture / paiement / écriture journal source (journal_entry_id)`. (3 niveaux)
- Chaque ligne de réévaluation conserve `journal_entry_id_source` et `source_id` comme ancres.

---
## N. Permissions (décision 5) — réutiliser l'existant + 1 seule nouvelle
| Action | Permission | Maker-checker |
|---|---|---|
| Calculer / recalculer une réévaluation | ACCOUNTING contribute | préparateur |
| **Comptabiliser une réévaluation** | **`accounting.fx_revaluation_post`** (sensible, NOUVELLE) | ≠ préparateur du run |
| Poster l'extourne | **`accounting.fx_revaluation_post`** (hérite provenance du run, contrôlé par période + politique) | pas de 2ᵉ approbation inventée |
| Consulter la réconciliation (rapport) | ACCOUNTING view | — |
| Confirmer une classification monétaire ambiguë (override) | ACCOUNTING contribute (audité) | — |
- `require_sensitive_permission('accounting.fx_revaluation_post')` — **aucun bypass** manage /
  Client Admin / platform_admin. Isolation société stricte. Audit complet. Backend = autorité.
- **Ne pas** réutiliser `accounting.supplier_invoice_post` ; **ne pas** coupler à une permission de
  clôture de période.
- Ajout au catalogue de permissions (`core/access/permissions_catalog.py`) — 1 seule nouvelle entrée.

---
## O. Preuve : AUCUN ledger / solde AP parallèle introduit (décision 15)
- Le sous-registre AP (Aging) reste **dérivé** des transactions canoniques au taux historique
  (A4.3, inchangé) — A4.6 **lit** ces soldes, n'en crée aucun.
- `ap_fx_revaluations.positions` est une **photo d'audit** au moment du calcul, **explicitement non
  autoritative** — la vérité des soldes reste les factures/paiements/crédits + le journal P2.
- La seule écriture au GL passe par le journal **canonique P2** (`create_workflow_journal_entry`),
  via `AP_FX_REVAL` / `FX_UNREAL_*`, **sans jamais** toucher le compte de contrôle fournisseurs
  historique ni créer une seconde table de soldes fournisseurs.
- La réconciliation (§L) est un **rapport dérivé** recalculé à la demande, jamais un solde stocké.
- ⇒ Une seule vérité comptable (STRAT-01 §7), zéro duplication de moteur/donnée (§21.12).

---
## P. Impacts exacts sur l'existant
- **`exchange_rates` (fx.py)** : AJOUT champ `rate_type` (défaut `current`) + `record_rate`/résolveur
  `closing`. Non-breaking, taux existants inchangés.
- **`company_ap_mapping` (ap.py l. 133-159)** : AJOUT des 3 rôles `fx_unrealized_gain/loss`,
  `ap_fx_reval`. Défauts canoniques proposés, non hardcodés.
- **Aging A4.3 (ap.py l. 943-980)** : **réutilisé tel quel** (source du sous-registre au taux
  historique). Aucun changement fonctionnel.
- **Positions AP (factures/crédits)** : AJOUT (dérivé/à la demande, non stocké de façon
  autoritative) de `monetary_classification` + `classification_reason` lors du calcul ; override
  humain audité si ambigu.
- **Journal P2** : **inchangé** — réutilise `create_workflow_journal_entry` + `link_reversal`.
- **Périodes** : **inchangé** — réutilise `_assert_postable_period` + machine d'état.
- **Permissions** : **1 seule** nouvelle `accounting.fx_revaluation_post`.
- **Nouvelles collections** : `ap_fx_revaluations`, `ap_reconciliations` (rapports/runs, jamais des soldes).

---
## Q. Écrans proposés (UX Exceptions First, langage grand public)
1. **Comptabilité → Réévaluation des devises** : sélection période/date → **Calculer** → carte
   « Rien à signaler / N exceptions » → **Comptabiliser** (1 clic) → confirmation + « Extourne
   préparée pour <mois suivant> ». Panneau « Pourquoi ? » (calcul, taux, fallback éventuel).
2. **Comptabilité → Réconciliation fournisseurs** (peut vivre sous Aperçu AP A4.3) :
   - Concordance → **« Réconcilié ✓ »** compact.
   - Écarts → liste Exceptions First (anomalies d'abord) + drill-down ≤ 3.
3. **Fiche run de réévaluation** : en-tête métier (date, devises, écart net), liste des positions
   (facturé/crédit, solde ouvert, taux hist./clôture, delta), état (calculé/posté/extourné), liens
   écritures P2. Détails techniques en Progressive Disclosure.

---
## R. Non-objectifs (STRAT-01 §20/§21)
Pas de : réévaluation AR (hors périmètre A4, tranche AR dédiée), couverture/hedging, comptabilité de
couverture (IFRS 9), réévaluation de postes non monétaires, taux intraday/temps réel de marché,
FX automatique OANDA (tant que clé absente), politique fiscale de change (reste au moteur fiscal /
Country Pack). Multi-comptes de contrôle avancé au-delà du mapping société : ultérieur si besoin.

---
## S. Tests obligatoires (≥ STRAT-01 §22)
Réévaluation : devise = fonctionnelle → delta 0 · perte non réalisée (dette plus chère) · gain non
réalisé · facture partiellement payée → seul le solde ouvert réévalué · note de crédit ouverte
réévaluée en sens opposé · avance non monétaire exclue · avance remboursable monétaire incluse ·
classification ambiguë → exception + override audité · taux `closing` présent prioritaire · fallback
`current` tracé dans « Pourquoi ? » · taux périmé → exception `rate_stale` (jamais inventé) · snapshot
immuable (un taux futur ne modifie pas un run passé). Posting : permission
`accounting.fx_revaluation_post` requise (aucun bypass manage/admin) · maker-checker (préparateur ≠
posteur) · période locked/closed → refus · double posting même (compte, as_of, période) → refus
`already_revalued` · re-post du même run → no-op idempotent · extourne préparée pour période suivante
+ lien bidirectionnel · extourne comptes inversés identiques · extourne bloquée si période suivante
fermée (reste préparée). Séparation : `FX_UNREAL_*` jamais recyclés en réalisé lors d'un paiement
ultérieur · compte de contrôle fournisseurs historique jamais mouvementé. Réconciliation : tout
concorde → « Réconcilié ✓ » · facture approuvée non postée → différence temporelle (pas anomalie) ·
paiement exécuté non posté → différence temporelle · solde `AP_FX_REVAL` → différence légitime
expliquée · écriture directe hors sous-registre → anomalie en tête · drill-down ≤ 3 (écart → doc →
journal). Isolation société stricte sur tous les cas. Aucun solde AP parallèle (preuve §O).

---
**STOP** — attendre validation (extension `rate_type`, classification monétaire canonique, rôles
comptables `FX_UNREAL_GAIN/LOSS`+`AP_FX_REVAL`, lifecycle réévaluation, permission sensible
`accounting.fx_revaluation_post`, méthode de réconciliation & taxonomie d'écarts, écrans) avant
d'implémenter A4.6.
