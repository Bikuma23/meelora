# CH.2 — CADRAGE : TVA Suisse (AUCUN CODE)
Transforme le Policy Engine CH.1 en **moteur TVA suisse exploitable par A3/A4**, **sans second
moteur fiscal** : A3 (ventes) et A4 (achats) **posent une question** (`resolve(domain="vat_ch", …)`)
et reçoivent une **VATPolicyDecision** snapshotée sur la transaction. Conforme STRAT-01 (§7 Core
intact, §11/§12 fiscalité/Country Pack, §21). **STOP après ce cadrage.**

> Rappels validés : CH.1 non modifié (sauf interface démontrée ici) ; rôles canoniques → mapping
> local ; migration non-breaking `sales_tax_codes` ; snapshot immuable ; « Pourquoi ? » ; overrides
> encadrés sans bypass admin/manage.

---
## 1. SOURCES OFFICIELLES (revalidées — cadrage juin 2026)
Chaque règle du moteur portera un objet `sources[]` structuré (déjà supporté par CH.1) :
`{authority, doc_ref, url, published_version, published_date, effective_from, effective_to, verified_at, evidence_hash?}`.
| Domaine | Autorité | Référence / doc_ref | Version/date | effective_from | verified_at |
|---|---|---|---|---|---|
| Taux TVA 8.1 / 2.6 / 3.8 % | AFC/ESTV | vat-rates-switzerland | en vigueur 2026 | 2024-01-01 | 2026-06 |
| Taux antérieurs 7.7 / 2.5 / 3.7 % | AFC/ESTV | historique | 2018–2023 | 2018-01-01 (→2023-12-31) | 2026-06 |
| Assujettissement (seuil CHF 100 000) | ESTV | vat-tax-liability | 2026 | — | 2026-06 |
| Méthodes effective / TDFN | ESTV | adjust-vat-settlement-methods | 2026 | — | 2026-06 |
| **Impôt sur les acquisitions (Bezugsteuer, reverse charge)** | ESTV / MWSTG art. 45–49 ; MI 14 | steuerpflicht-bezugsteuer-mwst | 2026 (émissions dès 2025) | — | 2026-06 |
| **Déduction impôt préalable / usage mixte** | ESTV / MWSTG **art. 28–30** ; vat-adjustment-statement | 2026 | — | 2026-06 |
| Prestations exclues/exonérées (art. 21/23 MWSTG) | ESTV / MWSTG | vat-act | 2026 | — | 2026-06 |
| **UID / n° TVA** (CHE-###.###.### + MWST/TVA/IVA ; « VAT » interdit) | OFS UID-Register ; ESTV | uid-general ; ValidateVatNumber (Webservice V3.0) | 2026 | — | 2026-06 |
| Décompte : dépôt ≤ 60 j, portail en ligne, champs 200/302/312/380/400/… | ESTV | paying-vat ; formulaire décompte | 2026 | — | 2026-06 |

**Règle** : aucune règle codée uniquement à partir de notre cadrage — chaque règle publiée cite sa
source officielle et sa date d'effet. Revérification à l'implémentation (« ne pas coder une norme
comme une constante éternelle »).

---
## 2. MATRICE DES CAS TVA — PÉRIMÈTRE P0 (PME suisse)
| # | Cas | Côté | tax_treatment | Taux | recoverability | Champs décompte (mapping) |
|---|---|---|---|---|---|---|
| 1 | Vente domestique biens/services | Output | `standard_rated` / `reduced_rated` / `accommodation_rated` | 8.1 / 2.6 / 3.8 % | — | 200 (CA) + 302/312/342 (TVA due) |
| 2 | Vente exonérée **avec** droit (exportation, prestations à l'étranger) | Output | `zero_rated_export` | 0 % | — | 200 + 220/221 (déductions CA) |
| 3 | Vente exclue **sans** droit (santé, formation, location immobilière, finance — art. 21) | Output | `exempt_without_credit` | 0 % | (réduit le droit à déduction amont) | 200 + 230 |
| 4 | Hors champ (subventions, dons, indemnités) | Output | `out_of_scope` | — | — | 200 + 910/…(non-CA) |
| 5 | Achat domestique | Input | `standard_rated` (préalable) | 8.1 / 2.6 / 3.8 % | `full` / `none` / `partial` | 400 (matériel/services) / 405 (investissements) |
| 6 | **Acquisition de prestations de l'étranger (Bezugsteuer / reverse charge)** | Input+Output | `reverse_charge_acquisition` | 8.1 % (en général) | `full`/`partial` (comme domestique) | 380 (impôt acquisition dû) + 400 (déduction) |
| 7 | Importation de biens (TVA perçue par l'OFDF) | Input | `import_goods` | 8.1 / 2.6 % | `full`/`partial` | 400/405 (sur justificatif OFDF) |
| 8 | Note de crédit / correction (héritée de l'origine) | Output/Input | = décision d'origine | = origine | = origine | 200/305/…(corrections) |

**Explicitement HORS P0 (future / conseil fiscal)** : méthode TDFN complète (taux sectoriels —
profil seulement en P0, calcul CH.4), option pour l'imposition (art. 22), prestations immobilières
avec option, décompte de groupe, taux de la dette fiscale forfaitaire (collectivités), marge
(art. 24a), prestations mixtes/combinées complexes, dégrèvement ultérieur/prestation à soi-même
(art. 31–32), correction pour double affectation détaillée par clés multiples. Marqués `future` ou
`needs_tax_advice` dans le moteur (jamais un taux inventé).

---
## 3. MODÈLE `VATPolicyDecision` (proposé — au-delà de `tax_rate`)
Domaine CH.1 : **`vat_ch`** (le domaine générique `vat` de CH.1 reste le wrapper de parité ; `vat_ch`
est la décision structurée complète). Résultat :
```
VATPolicyDecision.result = {
  tax_treatment,            # enum §2 (standard_rated | reduced_rated | accommodation_rated |
                            #          zero_rated_export | exempt_without_credit | out_of_scope |
                            #          reverse_charge_acquisition | import_goods)
  tax_code,                 # code canonique lisible (ex. 'CH_VAT_STD')
  rate,                     # taux effectif (0 si zero/exempt/out_of_scope)
  components: [ {name, rate, tax_type} ],   # (parité tax_engine)
  rate_version_effective_date,
  side,                     # 'output' | 'input' | 'both' (acquisition)
  recoverability: {         # côté input uniquement
     mode,                  # 'full' | 'none' | 'partial' | 'deferred_correction'
     rate?,                 # si partial (0..1)
     reason
  },
  reporting_mapping: {      # champs du futur décompte CH.4 (préparés MAINTENANT)
     base_field,            # ex. '200'
     tax_field,             # ex. '302' (8.1% output) / '380' (acquisition) / '400' (input)
     correction_field?      # ex. '415' (usage mixte)
  },
  account_roles: {          # rôles CANONIQUES (mappés au plan local — jamais un n° suisse ici)
     output_vat_role?,      # 'TAX_VAT_PAYABLE'
     input_vat_role?,       # 'TAX_RECOVERABLE'  (part récupérable)
     non_recoverable_target? # 'EXPENSE' (part non récupérable → charge)
  },
  rounding: { decimals, mode },   # snapshot du domaine 'rounding' CH.1
  legal_basis: [ art. MWSTG… ],
  sources: [ …structuré… ],
  reason                    # « Pourquoi ? » grand public
}
```
Plus les champs CH.1 standard : `policy_id, policy_version, jurisdiction, effective_from/to,
decision_id, inputs_hash, engine_version, resolved_at`. **Snapshoté intégralement** sur la
transaction (A3/A4) — jamais recalculé pour l'historique.

---
## 4. POLITIQUES / VERSIONS / DATES D'EFFET (via CH.1, append-only)
- `vat_ch / CH` **v1** `effective_from=2018-01-01` : 7.7 / 2.5 / 3.7 % + treatments.
- `vat_ch / CH` **v2** `effective_from=2024-01-01` : 8.1 / 2.6 / 3.8 %.
- **Reproductibilité** : une facture 2023 résout v1 (7.7 %) ; publier v2 ne touche jamais v1
  (démontré en CH.1). Aucune valeur par défaut implicite : absence ⇒ `policy_unavailable`
  (fail-closed, domaine `required`).
- Les **taux** restent dérivés du référentiel versionné (`sales_tax_codes`, parité) ; `vat_ch`
  ajoute treatment/recoverability/mapping/roles autour.

---
## 5. MAPPINGS COMPTABLES CANONIQUES
- Output : `TAX_VAT_PAYABLE` (existant). Input récupérable : `TAX_RECOVERABLE` (existant A4).
- **Nouveaux rôles** : `TAX_VAT_ACQUISITION` (dette reverse charge, art. 45), part **non
  récupérable** → `default_expense_account_code` (la TVA non déductible devient une charge).
- Tous **mappés** au plan KMU en CH.5 (ex. 2200 TVA due, 1170 impôt préalable) — **jamais** de n°
  suisse codé dans le moteur.

---
## 6. MAPPINGS FUTURS CH.4 (préparés maintenant)
`reporting_mapping` par décision (champ base + champ TVA + champ correction) → CH.4 **agrège** les
`tax_snapshots` par période/champ sans reconstruire la logique fiscale. Champs P0 couverts :
200 (CA), 220/221/230 (déductions/exclues), 302/312/342 (TVA due par taux), **380 (impôt
acquisition)**, 400/405 (impôt préalable), 415 (corrections usage mixte). TDFN : champ 200 TTC +
taux sectoriel (profil), calcul en CH.4.

---
## 7. DONNÉES SOCIÉTÉ / CLIENT / FOURNISSEUR REQUISES
- **Société** (`company_jurisdiction_profile`, CH.1/CH.3) : pays/canton, `vat_status`
  (assujetti/non), `vat_number` (UID), `vat_method` (effective/TDFN + dates d'effet), périodicité.
- **Client/Fournisseur** : pays, adresse fiscale, `vat_number` éventuel, indicateur
  domestique/étranger. **Contexte seulement** — la décision appartient au Policy Engine.
- **Transaction** : type (vente/achat/avoir), date, produit/service (catégorie de taux si dispo),
  contexte (domestique/export/import/acquisition).
> **UX/architecture clé** : le taux **n'est plus « posé » dans la fiche client**. La fiche fournit
> du contexte ; la décision est résolue à la date de la transaction et **snapshotée**. **Modifier le
> client plus tard ne change jamais une facture historique.**

---
## 8. UID / NUMÉRO TVA
- **Stockage** : `vat_number` sur la société et les tiers, **distinct** de l'`_id` Meelora.
- **Format** : `CHE` + 9 chiffres (clé de contrôle modulo 11), formes `CHE-123.456.789` /
  `CHE123456789` ; suffixe `MWST|TVA|IVA` (jamais « VAT »), non partie de l'UID.
- **Validation** : **contrôle de format + checksum HORS LIGNE** (déterministe, jamais dépendant d'un
  service). Vérification en ligne (OFS `ValidateVatNumber` / `ValidateUID`, uid.admin.ch) =
  **enrichissement optionnel non bloquant** ; **la comptabilité ne dépend jamais** de sa
  disponibilité (fail-open sur l'enrichissement, jamais fail-closed comptable).

---
## 9. MÉTHODES DE DÉCOMPTE
- **Effective** (défaut, trimestriel) et **TDFN/Saldosteuersatz** (semestriel, taux sectoriel ;
  éligibilité CA ≤ 5 024 000 / TVA ≤ 108 000) portées par le **profil fiscal versionné société**
  avec **dates d'effet**. En P0, `vat_ch` expose la méthode dans la décision ; le **calcul TDFN**
  (taux forfaitaire, corrections d'impôt préalable au changement) est **CH.4**.
- **Changement de méthode** = nouvelle version du profil avec `effective_from` → **ne réécrit jamais
  les périodes antérieures** (décisions passées gardent leur méthode snapshotée).

---
## 10. DÉDUCTIBILITÉ (input VAT) — pas de 100 % implicite
- `recoverability.mode` ∈ `full | none | partial | deferred_correction` (art. 28–30 MWSTG).
- **full** : achat professionnel taxable (défaut du Happy Path domestique). **none** : achat lié à
  une activité exclue (art. 21) → TVA en **charge** (`non_recoverable_target=EXPENSE`). **partial** :
  usage mixte → `rate` (clé de répartition) ; TVA éclatée récupérable/charge. **deferred_correction**
  : déduction pleine puis correction en fin de période (art. 30) — préparé, exécuté en CH.4.
- **Impact posting** : la part non récupérable augmente la charge (rôle `EXPENSE`), la part
  récupérable va à `TAX_RECOVERABLE`. Aucune écriture nouvelle hors A4 (A4 consomme la décision).
- **UX** : cas normal = `full` automatique ; usage mixte/non récupérable = **exception explicite**
  (1 information à confirmer), jamais une liste technique.

---
## 11. VENTES (A3) vs ACHATS (A4) — même moteur
- **A3 (output)** : `resolve(domain="vat_ch", context={side:'output', treatment_hint, product_cat,
  counterparty, date})` → treatment + rate + reporting (200/302/…). A3 **n'implémente aucune règle
  CH** ; il applique la décision et la snapshote sur la facture.
- **A4 (input)** : idem avec `side:'input'` → treatment + recoverability + roles + reporting
  (380/400/405). Acquisition de prestations étrangères (`reverse_charge_acquisition`) : A4 génère la
  **dette (380)** ET la **déduction (400)** selon recoverability — via le tax engine existant, pas
  un moteur parallèle.

---
## 12. NOTES DE CRÉDIT & CORRECTIONS — héritage de snapshot
- Une note de crédit **hérite** de la `VATPolicyDecision` **snapshotée** sur la facture d'origine
  (treatment, rate version, mapping, roles) — c'est la règle par défaut (juridiquement correct :
  la correction suit le fait générateur d'origine).
- Une **policy publiée aujourd'hui ne transforme JAMAIS** la TVA d'un avoir lié à une facture
  historique (le snapshot d'origine fait foi). Déjà garanti par A4 (crédit = écriture propre) + CH.1
  (immutabilité). Exception : correction volontaire **explicite** (override sensible §14).

---
## 13. UX — simplicité grand public
- **Happy Path** : client suisse + transaction domestique + contexte connu → Meelora **propose
  automatiquement** « **TVA 8,1 % ✓** » ; bouton **« Pourquoi ? »** (taux, treatment, base légale,
  source, date d'effet).
- **Ambiguïté** : « **1 information fiscale à confirmer** » (ex. export ? usage mixte ?) — **pas**
  une erreur technique ni une liste de 40 codes. Progressive disclosure pour les cas avancés.
- **Achat** : cas normal `full` silencieux ; non récupérable/mixte = 1 confirmation explicite.

---
## 14. OVERRIDES
- Distinguer **correction fiscale d'une décision configurable** (ex. treatment ambigu confirmé par
  l'utilisateur) d'un **override d'une règle réglementaire** (`non_overrideable` — ex. le taux légal).
- `overridability` déjà porté par CH.1 : taux légal = `non_overrideable` (bloqué même admin/manage,
  via `assert_overridable`) ; treatment/récupérabilité ambigus = `overrideable` **avec permission
  explicite + motif + acteur + old/new + audit + snapshot**. Aucun bypass admin/manage.
- **Permission** : `accounting.vat_decision_override` (NOUVELLE, sensible).

---
## 15. MIGRATION A3/A4 (non-breaking)
- **Nouvelles transactions** : A3/A4 appellent `resolve(vat_ch)` et snapshotent la décision. Les
  **taux** viennent toujours de `sales_tax_codes` (parité) → aucun changement de montant.
- **Documents/avoirs historiques** : **inchangés** (leur `tax_snapshot` d'origine fait foi) ;
  aucun recalcul ; posting P2 et rapports existants intacts.
- **Shadow mode** (recommandé, comme CH.1) : comparer, pour un lot, l'ancien chemin
  (`tax_engine.compute_line_tax`) vs `vat_ch.result.components` → **parité 100 %** exigée avant
  d'activer `vat_ch` comme autorité pour les nouvelles transactions.
- **A3/A4 n'implémentent jamais de règle CH** : ils ne connaissent que l'API canonique.

---
## TESTS (temporels & réglementaires)
Taux 8.1/2.6/3.8 à la bonne date ; bascule 2024-01-01 sans réécrire l'historique ; zero_rated_export
vs exempt_without_credit (impact déduction) ; out_of_scope ; reverse charge acquisition (380 dette +
400 déduction, seuil 10 000 hors P0-calcul) ; import biens (400/405 sur justificatif) ;
recoverability full/none/partial → posting (part non récup. en charge) ; note de crédit hérite la
décision d'origine ; policy publiée après coup ne change ni facture ni avoir historique ; UID
CHE-###.###.### + suffixe MWST validé **hors ligne** (checksum), enrichissement en ligne non
bloquant ; méthode effective vs TDFN dans la décision ; changement de méthode ne réécrit pas les
périodes passées ; arrondi via domaine `rounding` **identique A3/A4** ; **parité shadow** avec
`sales_tax_codes` ; `explain(snapshot)` sans re-résolution ; override réglementaire bloqué
(admin/manage) ; correction ambiguë overrideable avec audit ; isolation `{ws,co}`.

## HORS PÉRIMÈTRE CH.2 (rappel)
Calcul du décompte (CH.4), TDFN détaillé, option d'imposition (art. 22), immobilier avec option,
décompte de groupe, marge, prestation à soi-même/dégrèvement (art. 31–32), clés d'usage mixte
multiples, QR-facture (CH.6), import bancaire (CH.8).

## RÉPONSES STRAT-01 §21
1. **Tâche** : appliquer automatiquement le bon traitement TVA CH (vente/achat) et préparer les
   données du décompte, sans que l'utilisateur gère des codes.
2. **Happy Path** : « TVA 8,1 % ✓ » proposé, 0 saisie fiscale dans le cas nominal.
3. **Décisions humaines** : 0 en nominal ; 1 confirmation en cas d'ambiguïté.
4. **Pré-remplissage** : treatment/taux/récupérabilité/mapping dérivés de la policy + contexte.
5. **Exceptions visibles** : export ?, usage mixte ?, reverse charge ?, TVA non récupérable, UID invalide.
6. **Terme comptable requis ?** Non ; « impôt préalable / acquisition / exclu » expliqués via « Pourquoi ? ».
7. **Pourquoi ?** Taux + treatment + base légale (art. MWSTG) + source + date d'effet.
8. **Erreur → prochaine action** : « Confirmez la nature (domestique/export) », « Précisez la part professionnelle ».
9. **Drill-down ≤ 3** : montant TVA → décision snapshotée (treatment/version) → source/article de loi.
10. **P1.13 & Core** : override réglementaire sensible sans bypass ; aucun ledger parallèle ; Core P2 & historique intacts.
11. **Country Packs** : `vat_ch` est un domaine du pack CH ; A3/A4 restent agnostiques ; CA/EU ajouteront leurs domaines sans toucher les moteurs.
12. **Duplication ?** Non — réutilise `sales_tax_codes` (parité), le tax engine, les rôles/mappings, CH.1 ; aucun second moteur fiscal.

---
**STOP** — attendre validation (matrice P0, modèle `VATPolicyDecision`, versions/dates, mappings
comptables & CH.4, récupérabilité, notes de crédit, UX, permissions, migration shadow) **avant tout
développement**. Aucune ligne de code écrite pendant ce cadrage.
