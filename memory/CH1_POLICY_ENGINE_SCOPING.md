# CH.1 — CADRAGE : Jurisdiction / Accounting Policy Engine (AUCUN CODE)
Première tranche du Swiss Country Pack. **Fondation transverse** (CH/CA/EU) : une autorité
canonique de décision **versionnée, explicable, snapshotée, reproductible**. Conforme STRAT-01
(§7 Financial Core intact, §11/§12 Country Packs & fiscalité, §21 Gate). **STOP après ce cadrage.**

> Cadre validé (message précédent) : Policy Engine canonique versionné ; zéro `if country == CH` ;
> décisions explicables/snapshotées ; **Core P2 inchangé** ; rôles canoniques → mappings locaux ;
> Banking/Treasury = Core réutilisable ; migration **non-breaking** des `sales_tax_codes` ;
> normes externes = jamais des constantes éternelles (version + source + dates d'effet + fenêtre de
> compatibilité) ; **R4** (fraîcheur FX + classification monétaire) trouve son **autorité** ici
> **sans modifier A4.6** (sauf interface canonique explicitement nécessaire) ; **DT1/DT2** = dette
> jusqu'au CH.9 ; **R1** = bloquant production, pas dev ; **OANDA/IA** facultatifs.

---
## 0. OBJECTIF & NON-OBJECTIFS
**Objectif CH.1** : livrer le moteur de décision (API, modèle de policy versionné, résolution/
priorité/conflits, snapshot, « Pourquoi ? », cache/invalidation, audit, tests temporels) + le seed
des politiques par défaut existantes **enveloppées** (wrapping) — **sans changer aucun résultat
métier actuel**.
**Non-objectifs CH.1** : aucune règle métier neuve (pas de taux 3.8 %, pas de QR, pas de camt —
ce sont CH.2+). CH.1 est une **fondation invisible** : mêmes résultats qu'aujourd'hui, mais désormais
résolus/expliqués/snapshotés par l'autorité canonique.

---
## 1. FRONTIÈRE Core / Country Pack (invariant architectural)
```
A2/A3/A4/P2 (moteurs métier, multi-pays)
   │  posent une QUESTION DE POLITIQUE (DecisionContext) — jamais une règle CH/CA/EU
   ▼
Accounting Policy Engine  (CH.1 — CANONIQUE, agnostique du pays)
   │  résout la politique applicable par (domain, jurisdiction, effective_date)
   ▼
Policy Packs versionnés (données)  : ch.* , ca.* , eu.* …  (ajout sans toucher aux moteurs)
```
- Les moteurs **ne connaissent que l'API canonique** ; ils ignorent qu'un pack CH/CA/EU existe.
- Ajouter un pack (CH, CA, puis EU) = **insérer des documents `jurisdiction_policies`** + un
  `PolicyPack` déclaratif ; **zéro modification** de A2/A3/A4/P2 (démontré §11).
- **Core P2 intangible** : le moteur ne poste rien, ne stocke aucun solde, ne touche pas le journal.

---
## 2. API CANONIQUE DE DÉCISION
### 2.1 Signature (contrat stable, agnostique)
```
resolve(db, ws, co, *, domain, context, as_of) -> PolicyDecision
explain(decision_ref) -> Explanation           # « Pourquoi ? » à partir d'un snapshot
list_effective(domain, jurisdiction, as_of)     # introspection/preview (lecture)
```
- **`domain`** (extensible) : `vat` | `fx_freshness` | `monetary_classification` | `rounding` |
  `qr_bill` | `bank_format` | `retention` | `coa_mapping` | … (CH.1 câble `vat`, `fx_freshness`,
  `monetary_classification`, `rounding` ; les autres domaines sont déclarés mais alimentés en CH.2+).
- **`context` (DecisionContext)** — entrée normalisée, sérialisable, hashable :
  `{ country, canton?, vat_status?, vat_method?, transaction_type?, transaction_context?,
     counterparty?, currency?, amount_context?, extra:{} }`. Champs inconnus d'un domaine sont
  ignorés par ce domaine (tolérance ascendante).
- **`as_of`** : date d'effet de la décision (= date comptable de la transaction). **Obligatoire** :
  interdit de résoudre « maintenant » pour un fait daté.

### 2.2 Sortie (`PolicyDecision`) — déterministe & snapshotable
```
PolicyDecision = {
  domain, jurisdiction,                 # ex. 'vat', 'CH' (ou 'CH-GE')
  policy_id, policy_version,            # version IMMUABLE retenue
  rule_id,                              # règle précise appliquée
  result: { … },                       # ex. {tax_code, rate, account_role} ; opaque au moteur métier
  reason: "phrase grand public",        # « Pourquoi ? »
  sources: [ { authority, doc_ref, version, url, effective_from, retrieved_at } ],
  engine_version,                       # version de l'algorithme de résolution
  inputs_hash,                          # hash canonique du (domain, context, as_of)
  resolved_at
}
```
> `result` est **opaque** pour le moteur métier appelant : AP/AR reçoit un `tax_code`/`rate`/
> `account_role` et l'applique via ses propres mécanismes existants (aucune règle CH chez eux).

---
## 3. MODÈLE DE POLICY / VERSION / DATES D'EFFET
### 3.1 Document `jurisdiction_policies` (APPEND-ONLY, immuable par version)
```
{
  _id,                                  # policy_id logique (stable par domaine+juridiction+clé)
  domain, jurisdiction,                 # 'vat', 'CH'  (jurisdiction = country[-canton])
  policy_version: int,                  # incrément monotone ; une version n'est JAMAIS mutée
  effective_from: 'YYYY-MM-DD',         # début d'applicabilité
  effective_to:   'YYYY-MM-DD' | null,  # fin (null = ouvert) — fenêtre de compatibilité
  priority: int,                        # départage les chevauchements (défaut 100)
  status: 'active' | 'superseded' | 'draft',
  rules: [ { rule_id, match:{…}, result:{…} } ],   # règles internes ordonnées
  sources: [ { authority, doc_ref, version, url, effective_from, retrieved_at } ],
  supersedes_version: int | null,       # traçabilité de la chaîne de versions
  created_by, created_at, published_at
}
```
**Règles d'or** :
- Une version publiée est **immuable** (WORM logique). Corriger = **publier une nouvelle version**
  (`policy_version+1`, nouvel `effective_from`), jamais éditer l'ancienne.
- « Normes = jamais des constantes éternelles » : chaque version porte **source + version officielle
  + `effective_from` (+ `effective_to`)**. Aucune valeur codée en dur dans le moteur.
- **QR-facture** (préparé CH.6) : modélisé comme **plusieurs versions coexistantes** (2.3 avec
  `effective_to=2026-11-13`, 2.4 avec `effective_from=2026-11-14`) — **pas un flag `v2.4`**. Le même
  mécanisme sert à camt (.04 / .08) et à la TVA (7.7→8.1 %).

### 3.2 Liaison société (`company_jurisdiction_profile`)
Reprend le §3 du cadrage global : `policy_bindings:[{domain, policy_id}]` permet un **override
société** tracé, sinon la politique par défaut de la juridiction s'applique. Le binding fige le
`policy_id` mais **pas** la version (la version est résolue par `as_of` → reproductibilité §5).

---
## 4. RÉSOLUTION — PRIORITÉS & CONFLITS (déterministe)
Algorithme `resolve(domain, context, as_of)` :
1. **Filtrer** les politiques `{domain}` dont la `jurisdiction` correspond au contexte, en
   remontant du plus spécifique au plus général : `country-canton` → `country` → `default`.
2. **Fenêtre temporelle** : ne garder que celles avec `effective_from ≤ as_of < effective_to|∞`.
3. **Départage déterministe** (ordre strict, sans ambiguïté) :
   a. spécificité de juridiction (canton > pays > défaut) ;
   b. `priority` décroissante ;
   c. `effective_from` la plus récente ;
   d. `policy_version` la plus élevée.
   → si **égalité parfaite persiste** = **erreur de configuration** `policy_conflict` (fail-closed,
   jamais un choix arbitraire) remontée comme **exception nécessitant action** (pas un plantage silencieux).
4. **Règles internes** : dans la politique retenue, la première `rule` dont `match` satisfait le
   contexte gagne (ordre déclaré). Aucun `match` ⇒ `no_matching_rule` (exception explicable).
5. **Aucune politique** ⇒ `policy_unavailable` (fail-closed) → le moteur métier applique son
   comportement neutre existant (ex. code de taxe « à configurer ») — **jamais** un taux inventé.
> Déterminisme total : même `(context, as_of, état des politiques publiées)` ⇒ même décision.

---
## 5. SNAPSHOT & REPRODUCTIBILITÉ (démonstration exigée)
### 5.1 Ce qui est snapshoté sur la transaction (par le moteur métier appelant)
```
transaction.policy_snapshots[domain] = {
  policy_id, policy_version, rule_id, engine_version, inputs_hash,
  result, reason, sources, resolved_at
}
```
### 5.2 Invariant démontré — « même explication & même résultat après une future modification »
**Scénario** : facture émise le **2023-06-30** au taux normal **7.7 %** (politique `vat/CH` v1,
`effective_from=2018-01-01`). Le **2024-01-01** une **nouvelle version v2** (8.1 %) est publiée.
- **Immutabilité des versions** : v1 n'est jamais modifiée ; v2 est une **ligne distincte**
  (`effective_from=2024-01-01`, `supersedes_version=1`).
- **Ré-explication de la facture historique** : `explain()` lit **le snapshot** figé sur la facture
  (v1, 7.7 %, reason, sources d'alors) → **identique**, sans re-résolution.
- **Ré-résolution de contrôle** : `resolve(vat, CH, as_of=2023-06-30)` applique la fenêtre
  temporelle → sélectionne **v1** (car `2023-06-30 < 2024-01-01`) → **7.7 %**, même `reason`.
- **Conclusion** : le résultat **et** l'explication d'un fait passé restent **exactement identiques**
  après toute évolution réglementaire future — garanti par (a) versions append-only immuables,
  (b) résolution bornée par `as_of`, (c) snapshot sur la transaction. `engine_version` +
  `inputs_hash` permettent de prouver qu'aucune dérive d'algorithme n'a eu lieu.

---
## 6. « POURQUOI ? »
`explain(snapshot|decision)` renvoie une `Explanation` grand public :
`{ statement, rule_id, policy_version, effective_from, sources:[{authority, version, url}],
   inputs (contexte lisible), engine_version }`. Alimente le tiroir « Pourquoi ? » partout
(TVA, arrondi, fraîcheur FX, classification monétaire, plus tard QR/camt/rétention). Aucun jargon
imposé ; les termes techniques sont expliqués.

---
## 7. MIGRATION DEPUIS L'EXISTANT (non-breaking)
- **`sales_tax_codes`** (déjà versionné par `effective_date`, snapshot sur documents) devient la
  **source de vérité enveloppée** : CH.1 crée une politique `vat/<juridiction>` v1 qui **référence**
  les tax codes existants (wrapper), sans les dupliquer ni les modifier.
- **`jurisdiction.py`** (profil de conformité + `document_ai_policy`) est **absorbé** comme domaine
  `document_ai` du même moteur (l'API AP fail-closed reste inchangée : elle continue d'appeler la
  même fonction, désormais servie par le moteur canonique).
- **R4 (A4.6)** : la **fraîcheur des taux FX** (seuil 7 j) et la **classification monétaire par
  défaut** deviennent des domaines `fx_freshness` / `monetary_classification` du moteur. **A4.6
  n'est PAS modifié pendant CH.1**, sauf ajout d'une **interface d'appel canonique** si strictement
  nécessaire (sinon, câblage reporté à la tranche qui consomme réellement — valeurs par défaut
  identiques garanties).
- **Backfill** : documents historiques inchangés (leur snapshot fait foi) ; seuls les **nouveaux**
  documents portent `policy_snapshots`. Aucun recalcul rétroactif.
- **Réversibilité** : publier/retirer une version n'affecte que les faits **postérieurs**.

---
## 8. CACHE & INVALIDATION
- **Cache lecture** clé = `(ws, co, domain, jurisdiction, as_of_bucket, inputs_hash)` → décision.
  Comme les versions publiées sont **immuables**, le cache est sûr par construction.
- **Invalidation** : à la **publication** d'une nouvelle version (ou override société), invalider
  les entrées `(domain, jurisdiction)` **dont l'`as_of` ≥ `effective_from`** de la nouvelle version.
  Les buckets `as_of` **antérieurs** ne sont jamais invalidés (reproductibilité).
- **Sécurité** : le cache ne stocke jamais de secret ; il est optionnel (le moteur reste correct
  sans cache). TTL borné pour éviter une dérive en cas de bug d'invalidation.

---
## 9. AUDIT
- **Publication de politique** : événement immuable `{policy_id, version, effective_from, sources,
  by, at, supersedes_version}` — traçable, jamais supprimé.
- **Override société** : événement sensible audité (qui, quand, quelle politique/binding, raison).
- **Décisions** : non journalisées individuellement (volume) ; la **preuve** est le **snapshot** sur
  la transaction + la table de politiques immuable. `resolve` en anomalie (`policy_conflict`,
  `policy_unavailable`) émet un événement structuré (comme `security.sensitive_denied`).
- Aucune donnée secrète ; isolation `{workspace_id, company_id}` stricte.

---
## 10. TESTS (obligatoires — accent TEMPOREL)
- **Temporel/reproductibilité** : facture 2023 → 7.7 % ; publier v2 (8.1 %, 2024-01-01) ; ré-`explain`
  historique inchangé ; `resolve(as_of=2023-…)` = v1 ; `resolve(as_of=2024-…)` = v2 (démo §5).
- **Fenêtres** : `effective_from` inclusif, `effective_to` exclusif ; bascule exacte au jour pivot.
- **Priorité/conflit** : canton > pays > défaut ; `priority` ; version ; **égalité parfaite ⇒
  `policy_conflict`** (jamais de choix arbitraire).
- **Absence** : `policy_unavailable`/`no_matching_rule` ⇒ comportement neutre du moteur métier
  (aucun taux inventé).
- **Immutabilité** : impossible de muter une version publiée (nouvelle version obligatoire).
- **Cache** : hit/miss ; invalidation ciblée par `effective_from` ; buckets antérieurs préservés ;
  correction identique avec et sans cache.
- **Migration** : les résultats TVA post-wrapping sont **identiques** à l'existant (non-régression
  A2/A3/A4/P2).
- **Extensibilité** : ajouter un pack fictif `xx` ne casse aucun moteur (test §11).
- **Isolation** : décisions/politiques scellées `{ws, co}` ; override d'une société n'affecte pas une autre.

---
## 11. EXTENSIBILITÉ CH / CA / EU (démonstration sans toucher les moteurs)
- Un **PolicyPack** est un ensemble déclaratif de `jurisdiction_policies` (données) + un seed.
  Enregistrer `ch.*`, puis `ca.*`, puis `eu.*` = **insertion de documents**.
- Les moteurs A2/A3/A4/P2 appellent toujours **`resolve(domain, context, as_of)`** ; ils ne
  référencent jamais un pays. Ajouter l'Europe (ex. TVA intracommunautaire, e-invoicing) =
  nouveau domaine/versions dans le pack `eu`, **zéro diff** dans les moteurs.
- **Test d'architecture** : un pack de démonstration `xx` (juridiction fictive) doit être résolu de
  bout en bout via l'API canonique **sans modifier une seule ligne des moteurs métier**.

---
## 12. RÉPONSES AU GATE STRAT-01 §21
1. **Tâche** : fournir une autorité unique, versionnée et explicable pour toute décision de politique
   comptable/réglementaire, réutilisable multi-pays.
2. **Happy Path** : les moteurs posent une question, reçoivent une décision pré-résolue + « Pourquoi ? » ;
   l'utilisateur final ne voit rien de CH.1 (fondation invisible).
3. **Décisions humaines** : 0 en usage nominal ; publication de politique = acte d'administration tracé.
4. **Pré-remplissage** : tout est dérivé des politiques versionnées + du profil société ; aucune saisie
   de règle par l'utilisateur.
5. **Exceptions visibles** : `policy_conflict`, `policy_unavailable`, `no_matching_rule` (fail-closed,
   avec prochaine action), tentative de mutation d'une version publiée.
6. **Terme comptable requis ?** Non — explications grand public ; termes expliqués via « Pourquoi ? ».
7. **Pourquoi ?** Cœur du design : règle + version + source officielle + dates d'effet sur chaque décision.
8. **Erreur → prochaine action** : « Configurez la politique pour cette juridiction/date »,
   « Résolvez le conflit de politiques (priorités/dates) ».
9. **Drill-down ≤ 3** : Résultat sur transaction → snapshot (policy_version/rule) → source officielle.
10. **P1.13 & Core** : nouvelles permissions sensibles (publier/override politique) sans bypass ;
    **aucun ledger parallèle** ; Core P2 et historique jamais modifiés ; décisions immuables.
11. **Country Packs** : c'est l'objet même — packs additifs, moteurs inchangés (démo §11).
12. **Duplication ?** Non — enveloppe `sales_tax_codes` et `jurisdiction.py` existants ; snapshots
    déjà en place ; aucune vérité concurrente créée.

---
**STOP** — attendre validation (API `resolve/explain`, modèle append-only versionné, algorithme de
priorité/conflit, invariant de reproductibilité §5, stratégie cache/invalidation, migration wrapping
non-breaking, périmètre des domaines câblés en CH.1) **avant tout développement**. Aucune ligne de
code écrite pendant ce cadrage. Rappel : **R1** production-only, **DT1/DT2** → CH.9, **A4.6 non
modifié** hors interface canonique strictement nécessaire, **OANDA/IA** facultatifs.
