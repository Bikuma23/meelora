# SWISS COUNTRY PACK — CADRAGE P0 (lecture/étude uniquement — AUCUN CODE)
Objectif : rendre Meelora **commercialement exploitable par une PME suisse** tout en
**préservant l'architecture multi-pays (CA / EU / CH)**. Le Country Pack est une **couche
de politique/localisation VERSIONNÉE**, jamais des `if country == CH` dispersés dans les
moteurs métier. Conforme STRAT-01 (§7 Financial Core, §8 Périodes, §11/§12 Country Packs
& fiscalité, §21 Gate). **STOP après présentation pour validation.**

> ⚠️ Étude réglementaire datée de **juin 2026**. Chaque exigence porte source + version +
> `effective_from`. Les normes SPS 2026 (QR-bill 2.4 / camt .08) deviennent applicables le
> **14 novembre 2026** : le versioning par date effective est donc OBLIGATOIRE, pas optionnel.

---
## 1. ANALYSE RÉGLEMENTAIRE SOURCÉE
Chaque ligne = `{domaine, exigence, source officielle, version/date, effective_from, impact Meelora}`.

### 1.1 TVA (AFC / ESTV)
| Exigence | Source | Version/date | effective_from | Impact Meelora |
|---|---|---|---|---|
| Taux **normal 8.1 %** | estv.admin.ch/en/vat-rates-switzerland | en vigueur 2026 | 2024-01-01 (avant : 7.7 % 2018→2023) | Code `VAT_STD` versionné (déjà seedé) |
| Taux **réduit 2.6 %** (biens de première nécessité, aliments, livres, médicaments…) | idem | 2026 | 2024-01-01 (avant : 2.5 %) | Code `VAT_REDUCED` (déjà seedé) |
| Taux **hébergement 3.8 %** | idem | 2026 | 2024-01-01 (avant : 3.7 %) | **MANQUANT** dans le seed actuel → à ajouter `VAT_ACCOMMODATION` |
| **Taux zéro / exonéré / hors champ** (exportations, santé, formation, location immobilière, opérations financières…) | ESTV VAT overview | 2026 | — | `zero_rated` / `exempt` + nouveau `out_of_scope` (hors champ ≠ exonéré pour la déduction) |
| Assujettissement : seuil **CHF 100 000** de CA mondial taxable/an | estv.admin.ch/en/vat-tax-liability + VAT Info entreprises étrangères | 2026 | — | Profil société : statut TVA + date d'assujettissement (jamais un calcul de taux) |
| **Méthode effective** (décompte **trimestriel**, TVA due = collectée − déductible ; champs 200 CA net / 400 impôt préalable) | estv.admin.ch/en/adjust-vat-settlement-methods | 2026 | — | Politique de décompte société ; périodicité TVA trimestrielle |
| **Méthode des taux de la dette fiscale nette (TDFN / Saldosteuersatz)** : décompte **semestriel**, taux forfaitaire sectoriel sur CA TTC, **pas de déduction d'impôt préalable séparée** ; éligibilité CA ≤ **CHF 5 024 000** et TVA ≤ **CHF 108 000**/an | estv.admin.ch (Saldosteuersätze) ; lumabill/tobill guides | 2026 | — | 2ᵉ méthode de décompte ; engage ≥ 1 an ; corrections d'impôt préalable au changement de méthode |
| Décompte **auto-déclaré**, dépôt **≤ 60 jours** après la période, **portail en ligne** exclusif | estv.admin.ch/en/paying-vat | 2026 | — | Meelora **prépare les données** du décompte (mapping des champs), **ne télétransmet pas** en P0 |
| Arrondi TVA au **centime** (0.01 CHF) | pratique ESTV / CO | — | — | Politique d'arrondi par juridiction (au niveau ligne puis total) |
| **Notes de crédit / corrections** : ajustent la TVA de la période de correction, **jamais** de réécriture rétroactive du snapshot d'origine | CO / ESTV | — | — | Déjà respecté par A4 (crédit = écriture propre) ; snapshot fiscal immuable |
| **Prestations / importations / cas transfrontaliers** : acquisition de prestations de l'étranger = **auto-liquidation (reverse charge, Bezugsteuer)** ; TVA import perçue par l'OFDF | ESTV VAT Info | 2026 | — | `transaction_context` (domestic / import_service_reverse_charge / import_goods / export) → détermine collecte/déduction |
| Conservation **10 ans** (26 ans pour docs TVA immobilier) | CO 958f + GeBüV | — | — | Voir §1.4 archivage |

**Règle absolue** : un changement de taux/règle **ne remplace jamais** le snapshot fiscal
d'une facture déjà émise (immutabilité historique — déjà appliqué par `tax_engine`).

### 1.2 QR-facture (SIX)
| Exigence | Source | Version/date | effective_from | Impact Meelora |
|---|---|---|---|---|
| **Implementation Guidelines QR-bill v2.3** (applicable actuellement) | six-group.com IG QR-bill v2.3 | 2.3 | jusqu'au 2026-11-13 | Profil QR versionné |
| **QR-bill v2.4** (SPS 2026) | six-group.com IG QR-bill v2.4 (en) | 2.4 | **2026-11-14** | Le profil actif dépend de la date d'émission → **versioning obligatoire** |
| **QR-IBAN** identifié par QR-IID **30000–31999** ; **QR-IBAN + QR reference réservés au CHF** | IG v2.4 §§ | 2.4 | 2026-11-14 | Validation coordonnées ; EUR interdit avec QR-IBAN |
| **QR reference** : 27 caractères (26 chiffres + 1 clé modulo 10 récursive) ; **uniquement avec QR-IBAN** | IG v2.4 | — | — | Générateur + validateur de référence |
| **Creditor Reference ISO 11649** : `RF` + 2 clés (mod 97-10) + réf. alphanum. (total 5–25) ; utilisé avec **IBAN standard** (CHF **et** EUR) | IG v2.4 | — | — | Générateur/validateur alternatif |
| **Swiss QR Code** (croix suisse), **section paiement + récépissé**, montant/devise, débiteur, informations facture | IG v2.4 | — | — | Génération PDF (section paiement A6, récépissé) |
| Devises autorisées : **CHF et EUR** uniquement | IG v2.4 | — | — | Validation en amont |

**Règle absolue** : **ne pas hardcoder « QR-bill 2.4 »** — le profil est choisi par
`effective_from` selon la date d'émission (2.3 avant le 14.11.2026, 2.4 ensuite).

### 1.3 ISO 20022 / Banque (SIX / PaCoS)
| Exigence | Source | Version/date | effective_from | Impact Meelora |
|---|---|---|---|---|
| **camt.053.001.08** (relevé fin de journée), **camt.052.001.08** (intraday), **camt.054.001.08** (avis débit/crédit) — Maintenance Release 2019 | six-group.com IG Cash Management SPS 2026 ; ZKB | .08 | v04 **retiré le 2026-11-14** | Import bancaire canonique : parser multi-version (.04 et .08) |
| **Batch booking** : résolution interne (détails dans camt.053/052) ou externe (renvoi vers camt.054 via *Additional Information Indicator*) | IG Cash Management | — | — | Normalisation en écritures bancaires atomiques |
| **Entry Reference / QR-Reference / SCOR** = clés de rapprochement | IG Cash Management ; Business Rules SPS 2026 | — | — | Rapprochement encaissements ↔ factures clients / paiements ↔ factures fournisseurs |
| **pain.001** (initiation de paiement) | IG Payments SPS 2026 | — | — | **Hors P0** (émission de paiements = Banking/Treasury Core ultérieur) |

**Frontière architecturale** : le **parsing/normalisation camt** et le **moteur de
rapprochement** relèvent d'un futur **Banking/Treasury Core réutilisable (CA/EU/CH)** ; le
Country Pack CH fournit uniquement le **profil de format** (versions camt admises, règles de
référence QR/SCOR) et les **hints de matching**. **Aucun posting automatique ambigu.**

### 1.4 Archivage (GeBüV / OLico — RS 221.431 ; CO art. 957–958f)
| Exigence | Source | Version/date | effective_from | Impact Meelora |
|---|---|---|---|---|
| Conservation **10 ans** (dès la fin de l'exercice) des livres, pièces, rapports | CO 958f ; fedlex OLico | — | — | Politique de rétention par juridiction + horodatage d'échéance |
| **Intégrité** : les enregistrements ne peuvent être modifiés sans que ce soit **apparent** | GeBüV art. 3 ; kmu.admin.ch | — | — | Sur support **altérable** (cloud/SSD) → **signature/horodatage** + journaux + doc. procédures |
| **Lisibilité** durant toute la durée ; formats d'archive (**PDF/A** recommandé) | kmu.admin.ch | — | — | Génération PDF/A + conservation du moyen de lecture |
| **Traçabilité/accès** : journaliser consultations et migrations de support | GeBüV | — | — | Journal d'accès aux archives |
| Rapports annuels/de révision : **signés, papier** | CO 958f | — | — | Responsabilité **organisationnelle** du client (voir matrice §6) |
| **26 ans** pour pièces TVA liées à l'immobilier | BDO / ESTV | — | — | Règle de rétention spéciale paramétrable |

**Règle absolue** : **Object Storage seul ≠ preuve de conformité**. La conformité exige
intégrité prouvable (hash/signature/horodatage + WORM/versioning verrouillé), journal d'accès,
procédure documentée et durée garantie. Voir §6 (Core vs Country Pack vs client).

### 1.5 Plan comptable & identifiants
| Exigence | Source | Version/date | effective_from | Impact Meelora |
|---|---|---|---|---|
| **Kontenrahmen KMU / Plan comptable suisse PME** (veb.ch, structure Sterchi), 4 chiffres, **9 classes** (1 actif, 2 passif/fonds propres, 3 produits, 4 charges matières, 5 personnel, 6 autres charges, 7 hors exploitation, 8 exceptionnel, 9 clôture) | kmu.admin.ch KMU-Kontenrahmen ; veb.ch | — | — | **Preset de mapping** rôles canoniques → comptes locaux (jamais de numéro suisse dans le Core) |
| TVA due typiquement en série **220x** (2200 TVA due) | kmu.admin.ch | — | — | Mapping rôle `TAX_VAT_PAYABLE` → 2200 (proposé, remappable) |
| **UID/IDE** : `CHE-xxx.xxx.xxx`, suffixe TVA `MWST/TVA/IVA` (ex. `CHE-123.456.789 MWST`) | kmu.admin.ch | — | — | Validation format + affichage sur factures ; **pas** de logique métier dérivée du numéro |

---
## 2. ARCHITECTURE
### 2.1 Principe
Le **Jurisdiction / Accounting Policy Engine** (évolution de `core/compliance/jurisdiction.py`)
devient l'**autorité canonique** qui répond à une **question de politique** et renvoie une
**décision versionnée, explicable et snapshotable**. Les moteurs métier (A2/A3/A4/P2)
**consomment** la décision et **snapshotent** l'ID/version de la politique appliquée — ils ne
contiennent aucune règle CH.

```
Business modules (AR/AP/GL/Tax/Bank)  ──ask──▶  Jurisdiction/Accounting Policy Engine
      │  (contexte de décision)                        │  (résout la règle applicable + version)
      └──────────── snapshot(policy_id, version) ◀──────┘  (décision + « Pourquoi ? »)
                              │
                     Country Pack CH (couche de données versionnée)
        VAT profiles · QR profiles · camt format profiles · retention · CoA preset
```

### 2.2 Contexte de décision (entrée du moteur)
```
DecisionContext = {
  country, canton, effective_date, vat_status (assujetti|non|TDFN),
  vat_method (effective|net_tax_rate), transaction_type (sale|purchase|credit_note|advance),
  transaction_context (domestic|import_service_reverse_charge|import_goods|export|financial|exempt),
  counterparty (domestic|foreign, vat_number?), currency, amount_context
}
```
Sortie : `PolicyDecision = { rule_id, policy_version, result(tax_code/rate/account_role/...),
reason (« Pourquoi ? »), sources:[{authority, version, effective_from}] }` — **déterministe,
reproductible historiquement** (même contexte + même date ⇒ même décision).

### 2.3 Non-négociables
- **Zéro `if country == CH`** dans AR/AP/GL/Tax/Bank : toute spécificité vit dans les données
  du Country Pack + le moteur de politique.
- **Rôles comptables canoniques** partout (P2) ; le plan suisse n'est qu'un **mapping**.
- **Immutabilité** : les décisions sont snapshotées sur la transaction ; une évolution de règle
  crée une **nouvelle version** et ne réécrit jamais l'historique.
- **IA & OANDA restent facultatifs** et **ne sont jamais prérequis** de la conformité comptable CH.

---
## 3. MODÈLE DE DONNÉES (versionné, dérivé, sans duplication)
```
jurisdiction_policies            # catalogue de politiques versionnées (par pays/canton)
  { _id, country, canton?, domain('vat'|'qr_bill'|'bank_format'|'retention'|'coa'),
    policy_version, effective_from, effective_to?, rules:[...],
    sources:[{authority, doc_ref, version, url, retrieved_at}], created_at }

company_jurisdiction_profile     # profil PME (override de compliance_profile existant)
  { workspace_id, company_id, country, canton, vat_status, vat_number(UID),
    vat_method('effective'|'net_tax_rate'), net_tax_rates:[{sector, rate, effective_from}]?,
    vat_period('quarterly'|'semiannual'), coa_preset_id, retention_profile_id,
    policy_bindings:[{domain, policy_id, policy_version}], updated_at }

# TVA — réutilise/étend l'existant sales_tax_codes (déjà versionné) + purchase side
tax_codes (existant)             # + ajout VAT_ACCOMMODATION, out_of_scope, reverse_charge flags
tax_snapshots (sur documents)    # existant — inchangé (immuable)

# QR-facture (AR)
qr_bill_profiles                 # versionné par effective_from (2.3 / 2.4)
qr_bill_instances                # { invoice_id, profile_version, qr_iban|iban, reference_type
                                 #   ('qr_ref'|'scor'|'none'), reference, payload_snapshot, pdf_ref }

# Banque (profil de format seulement — le moteur de rapprochement = Banking Core futur)
bank_format_profiles             # { country, camt_versions:['053.001.08','054.001.08',...], rules }

# Archivage
retention_profiles               # { country, default_years:10, special:[{class:'vat_real_estate', years:26}],
                                 #   integrity:'signature|timestamp|worm', formats:['PDF/A'] }
archive_records                  # { source_document_id, hash, signed_at, integrity_method,
                                 #   retention_until, access_log:[...] }  (dérivé de source_documents)

# Plan comptable
coa_presets                      # { country, name('KMU'), accounts:[{code, name, class}],
                                 #   role_map:[{canonical_role, local_account_code}] }
```
Aucune duplication : `tax_codes`/`tax_snapshots`, `source_documents`, `journal_entries`,
`exchange_rates` (dont `rate_type` A4.6) et l'aging A4 restent **la** vérité. Le Country Pack
ajoute des **profils** et des **mappings**, jamais un second grand livre / solde.

---
## 4. MOTEUR DE RÈGLES & VERSIONING
- **Résolution** : `resolve(domain, DecisionContext)` → sélectionne la `jurisdiction_policy`
  dont `effective_from ≤ date < effective_to` la plus récente pour `(country, canton, domain)`,
  applique ses `rules`, renvoie `PolicyDecision` + `sources` + « Pourquoi ? ».
- **Versioning par date effective** (comme `tax_engine._pick_version`) généralisé à tous les
  domaines (TVA, QR, camt, rétention, CoA). Un nouveau taux/une nouvelle IG = **nouvelle version**.
- **Snapshot** : la transaction stocke `{policy_id, policy_version}` par domaine appliqué →
  **reproductibilité historique** (rejouer une décision passée à sa version d'alors).
- **Explicabilité** : chaque décision porte `reason` + `sources[{authority, version, url}]` pour
  le tiroir « Pourquoi ? ».
- **Gouvernance** : les politiques par défaut sont seedées (versionnées) ; un override société
  est possible mais tracé/audité. **L'IA ne détermine jamais** une décision de politique (§10).

---
## 5. IMPACTS A2 / A3 / A4 / P2
| Module | Impact | Nature |
|---|---|---|
| **A2 (Journal/GL, P2 Core)** | Aucun changement de moteur ; consomme les **rôles** → mapping CoA. Le CoA preset KMU alimente le mapping. | Additif, non-breaking |
| **A3 (FX)** | Réutilisé tel quel. `rate_type` (A4.6) déjà en place. TVA sur devise étrangère : conversion au taux du jour de la facture (règle ESTV) portée par la politique. | Aucun code moteur |
| **A4 (AP)** | Ajout côté **achat** : TVA déductible (impôt préalable), auto-liquidation (reverse charge import de prestations), champ 400 du décompte. Réutilise le tax engine. Rôles TVA déjà mappables. | Additif (évolution approuvée) |
| **AR (ventes)** | TVA collectée (champ 200) + **QR-facture** (émission PDF). C'est le principal chantier neuf CH. | Nouveau (Country Pack + AR) |
| **P2 (Financial Core)** | **Intangible** : rôles canoniques, journal unique, périodes. Le Country Pack ne touche jamais le Core — il ne fait que mapper/paramétrer. | Zéro modification Core |
| **Décompte TVA** | Nouveau : agrégation des `tax_snapshots` par période/champ (200/400/…) pour **préparer** les données du décompte (effective/TDFN). Pas de télétransmission P0. | Nouveau (reporting) |

**Reports du Gate A4 (à traiter au bon endroit, pas maintenant)** :
- **DT1/DT2** → proposer à terme que `balance/amount_paid/credited_total` soient
  **reconstruisibles/vérifiables depuis les événements canoniques** (event-sourcing léger /
  vérificateur de cohérence). **Non corrigé pendant ce cadrage.**
- **R1 Object Storage** → **deployment gate BLOQUANT avant production CH** : test réel
  *upload → stockage → téléchargement → hash/intégrité → permissions → traçabilité*. Le timeout
  du preview **n'est pas** une validation de production.
- **R4** → **déplacer** la politique de **fraîcheur des taux** (seuil A4.6) et la **classification
  monétaire par défaut** dans l'**Accounting Policy** (domaine `fx`/`monetary`) du Country Pack.

---
## 6. MATRICE DES RESPONSABILITÉS — Core vs Country Pack vs Client
| Capacité | Financial Core (CA/EU/CH) | Country Pack CH (données versionnées) | Client (organisationnel) |
|---|---|---|---|
| Journal P2, rôles, périodes, immutabilité | ✅ | — | — |
| Moteur TVA versionné (calcul/snapshot) | ✅ (générique) | Taux/règles CH + contextes | Choix méthode/assujettissement |
| QR-facture (génération/validation) | Générateur générique | Profil QR 2.3/2.4 + règles CHF/EUR | Coordonnées bancaires exactes |
| Import bancaire camt → modèle canonique | ✅ **Banking/Treasury Core (futur)** | Profil format camt CH (.08) | Fourniture des fichiers |
| Rapprochement encaissements/paiements | ✅ **Banking/Treasury Core (futur)** | Hints de référence (QR/SCOR) | Validation des exceptions |
| Archivage : intégrité/hash/horodatage/WORM, journal d'accès, PDF/A | ✅ (mécanisme technique) | Durées (10/26 ans) + méthode d'intégrité | Signature papier des comptes, gouvernance, preuve organisationnelle |
| Plan comptable | Rôles canoniques + mapping | Preset KMU + role_map | Personnalisation des comptes |
| Décompte TVA (préparation données) | Agrégation générique | Mapping champs 200/400/… CH | Télétransmission au portail ESTV |

> **Object Storage seul ≠ conformité GeBüV** : la conformité = mécanisme Core (intégrité prouvable)
> + profil Country Pack (durées) + responsabilité client (signature/gouvernance).

---
## 7. ÉCRANS / UX (la complexité est absorbée par Meelora)
- **Assistant d'installation CH** (progressive disclosure) :
  `Pays : Suisse → Canton : Genève → Assujetti TVA : Oui` → Meelora **propose automatiquement** :
  méthode (effective par défaut), périodicité (trimestrielle), preset CoA KMU, taux TVA en vigueur,
  profil QR/camt applicable — avec **« Pourquoi ? »** sur chaque proposition. L'utilisateur
  n'a **pas** à connaître le Jurisdiction Engine.
- **Réglages avancés** (repliés) : méthode TDFN + taux sectoriels, remap de comptes, profil de
  rétention, override de politique.
- **Facture de vente** : bouton **« QR-facture »** (aperçu section paiement/récépissé) ; validation
  des coordonnées ; « Pourquoi ? » explique QR-ref vs Creditor Reference selon devise.
- **Décompte TVA** : écran **Exceptions First** — « Prêt : N pièces, TVA nette CHF X (champ 200 / 400) »
  ou uniquement les pièces à revoir (contexte manquant, taux ambigu) ; export des données.
- **Archives** : état de conformité par exercice (« Archivé & intégrité vérifiée ✓ » / manques).

---
## 8. PERMISSIONS (réutiliser l'existant + minimum de nouvelles)
| Action | Permission | Type |
|---|---|---|
| Configurer le profil juridiction/TVA société | `accounting.jurisdiction_configure` (NOUVELLE, sensible) | maker-checker léger |
| Changer de méthode TVA (effective ↔ TDFN) | même permission + audit (engagement ≥ 1 an) | sensible |
| Préparer/figer un décompte TVA de période | `accounting.vat_return_prepare` (NOUVELLE) | sensible |
| Émettre une QR-facture | permission AR existante (contribute) | non sensible |
| Remapper le plan comptable | permission comptes existante (P2.3) | existante |
| Gérer les archives / rétention | `accounting.archive_manage` (NOUVELLE) | sensible |
Toutes via `require_sensitive_permission` (aucun bypass manage/admin — cf. Gate A4). Isolation
société stricte.

---
## 9. STRATÉGIE DE MIGRATION DEPUIS LES `tax_code` ACTUELS
- **Base existante** : `sales_tax_codes` est déjà **versionné** avec CH (7.7→8.1 %, 2.5→2.6 %) et
  snapshot sur documents. **On n'écrase rien.**
- **Étapes (non-breaking)** :
  1. Ajouter les codes manquants CH (`VAT_ACCOMMODATION` 3.8 %/3.7 %, `out_of_scope`) comme
     **nouvelles versions**, sans toucher aux snapshots existants.
  2. Introduire `jurisdiction_policies` et **lier** (`policy_bindings`) les tax codes existants
     comme politique `vat` v1 pour la Suisse (wrapper — les documents historiques restent valides).
  3. Étendre le tax engine au **côté achat** (impôt préalable / reverse charge) via le même modèle.
  4. Backfill : les documents existants conservent leur snapshot ; les **nouveaux** documents
     référencent `{policy_id, version}`.
- **Réversibilité** : aucun recalcul rétroactif ; un rollback de politique n'affecte que les
  documents postérieurs.

---
## 10. TESTS RÉGLEMENTAIRES OBLIGATOIRES
- **TVA** : 8.1 / 2.6 / 3.8 % à la bonne date ; bascule de taux au 2024-01-01 sans réécrire
  l'historique ; zéro/exonéré/hors champ (impact déduction) ; reverse charge import de prestations ;
  arrondi au centime ; note de crédit = correction de période, snapshot d'origine intact ;
  méthode effective (trimestriel, champs 200/400) vs TDFN (semestriel, CA TTC, pas de déduction) ;
  éligibilité TDFN (seuils 5 024 000 / 108 000) ; UID `CHE-###.###.### MWST` validé.
- **QR-facture** : QR-ref 27 car. (clé modulo 10) ; Creditor Reference RF/mod97-10 ; QR-IBAN
  CHF uniquement, EUR ⇒ IBAN + Creditor Reference ; profil **2.3 avant 14.11.2026 / 2.4 après**
  (sélection par date) ; validation coordonnées ; génération PDF section paiement + récépissé.
- **camt** : parse `.053/.054/.052 .001.08` ; batch booking interne & externe (camt.054) ;
  extraction Entry Reference / QR-Ref / SCOR ; **aucun posting automatique** (proposition seulement).
- **Archivage** : hash/horodatage sur support altérable ; échéance 10 ans (26 ans TVA immobilier) ;
  journal d'accès ; PDF/A ; intégrité détecte toute altération.
- **Reproductibilité** : rejouer une décision de politique à une date passée ⇒ décision identique.
- **Isolation** : toutes les décisions/écrans scellés `{workspace_id, company_id}`.

---
## 11. RISQUES
- **RQ1 (calendrier SPS 2026)** : QR-bill 2.4 & camt .08 applicables au **14.11.2026** → livrer
  le **versioning par date** et supporter 2.3/.04 **et** 2.4/.08 sur la transition. Élevé si ignoré.
- **RQ2 (Object Storage / GeBüV — R1)** : sans preuve d'intégrité réelle en production, non-conforme.
  **Deployment gate bloquant** requis. Moyen/élevé.
- **RQ3 (TDFN)** : taux sectoriels et corrections d'impôt préalable au changement de méthode =
  complexité ; risque d'erreur si mal cadré. Moyen.
- **RQ4 (portée bancaire)** : tentation de coder le rapprochement dans le Country Pack → dette.
  Le maintenir dans le **Banking/Treasury Core** réutilisable. Moyen.
- **RQ5 (dérive des règles)** : les sources officielles évoluent → sans champ
  `sources/version/effective_from`, l'historique devient irreproductible. Mitigé par §4.
- **RQ6 (multi-canton)** : la TVA est fédérale (pas de taux cantonal), mais d'autres domaines
  futurs (impôts) le seront → garder `canton` dans le contexte dès maintenant. Faible.

---
## 12. ORDRE D'IMPLÉMENTATION PROPOSÉ (tranches CH.1 → CH.n)
- **CH.1 — Jurisdiction/Accounting Policy Engine** (autorité canonique versionnée + contexte +
  snapshot + « Pourquoi ? » + seed politiques CH). *Fondation, sans changement métier visible.*
- **CH.2 — TVA CH complète** (codes manquants 3.8 %/hors champ, côté achat/impôt préalable,
  reverse charge, contextes transfrontaliers, arrondis). *S'appuie sur A4/AR existants.*
- **CH.3 — Profil société & méthodes de décompte** (assujettissement, effective/TDFN, périodicité,
  UID) + **Assistant d'installation CH** (UX progressive disclosure).
- **CH.4 — Préparation du décompte TVA** (agrégation champs 200/400/…, export des données ; pas de
  télétransmission).
- **CH.5 — QR-facture (AR)** (profils 2.3/2.4 versionnés, QR-ref/Creditor Reference, validation,
  PDF section paiement + récépissé).
- **CH.6 — Plan comptable KMU** (preset + role_map + assistant de mapping).
- **CH.7 — Archivage GeBüV/OLico** (intégrité hash/horodatage/WORM, rétention 10/26 ans, PDF/A,
  journal d'accès) + **deployment gate Object Storage (R1)**.
- **CH.8 — Import bancaire camt (Banking/Treasury Core, réutilisable)** : parsing/normalisation
  `.08`, batch booking ; rapprochement AR/AP **proposé** (aucun posting automatique).
- **CH.9 — Reports Gate A4** : R4 (fraîcheur taux + classification monétaire → Accounting Policy) ;
  proposition DT1/DT2 (caches reconstruisibles depuis événements canoniques).
> Chaque tranche passe le **Gate STRAT-01 §21** avant code.

---
## 13. RÉPONSES AU GATE STRAT-01 §21
1. **Tâche** : permettre à une PME suisse de facturer, déclarer la TVA, encaisser (QR) et archiver
   en conformité, sans quitter Meelora ni comprendre la mécanique réglementaire.
2. **Happy Path** : Assistant « Suisse / Canton / Assujetti ? » → configuration proposée en 1 écran ;
   facture → QR en 1 clic ; décompte TVA → « Prêt » en 1 clic ; archivage automatique.
3. **Décisions humaines** : idéalement 1 (valider la config proposée) ; 0 sur les cas nominaux
   ultérieurs (taux/QR/profil déterminés par la politique).
4. **Pré-remplissage** : taux, méthode, périodicité, preset CoA, profil QR/camt, rétention —
   tous dérivés de la politique versionnée. L'utilisateur ne saisit que pays/canton/statut + coordonnées.
5. **Exceptions visibles** : contexte de transaction manquant (import/export), coordonnées QR
   invalides, seuils TDFN dépassés, période de bascule de norme (2.3→2.4), archive dont l'intégrité
   n'est pas prouvée.
6. **Terme comptable requis ?** Non — libellés grand public ; « impôt préalable / reverse charge /
   TDFN » expliqués via « Pourquoi ? ».
7. **Pourquoi ?** Oui — chaque décision porte règle + version + source officielle + effective_from.
8. **Erreur → prochaine action** : « Complétez le contexte (import/national) », « Corrigez l'IBAN »,
   « Choisissez la méthode », « Renouvelez la preuve d'intégrité ».
9. **Drill-down ≤ 3** : Décompte TVA → pièce → snapshot fiscal (règle+version) ; QR → facture →
   coordonnées/référence ; archive → document → preuve d'intégrité/journal.
10. **P1.13 & Financial Core** : nouvelles permissions sensibles sans bypass ; **aucun ledger
    parallèle** ; le Country Pack ne modifie jamais le journal P2 ni l'historique.
11. **Country Packs** : c'est précisément l'objet — politique versionnée, zéro `if country`,
    réutilisable CA/EU. Le Banking Core reste multi-pays.
12. **Duplication ?** Non — réutilise `tax_codes`/snapshots, `source_documents`, journal P2,
    rôles/mapping, permissions/audit, FX. Ajoute des **profils/mappings versionnés**, pas une vérité concurrente.

---
**STOP** — attendre validation (moteur de politique versionné, périmètre TVA/QR/camt/archivage/CoA,
frontière Country Pack ↔ Banking/Treasury Core, matrice de responsabilités, ordre CH.1→CH.9,
reports Gate A4) **avant tout développement**. Aucune ligne de code écrite pendant ce cadrage.
