# CADRAGE — Activation Gate : recâblage fiscal A3/A4 vers `vat_ch`
**Statut : CADRAGE (aucun code). STOP après validation. CH.4 reste STOP.**
Réf. Gate : STRAT-01 §21. Dépend de : CH.1 (Policy Engine), CH.2 (`vat_ch`), CH.3 (Profil fiscal société).

---
## 0. Principe directeur
CH.1 + CH.2 + CH.3 deviennent l'**autorité fiscale réelle** des NOUVELLES transactions A3 (ventes) et A4 (achats), **société par société**, via un **Activation Gate** explicite. Invariants absolus :
- **Aucun recalcul rétroactif** : les transactions existantes gardent leur snapshot fiscal.
- **Aucun big-bang** : bascule par société, réversible tant qu'aucune transaction `vat_ch` n'existe.
- **Aucun second moteur fiscal** : A3/A4 n'hébergent AUCUNE logique TVA CH ; ils construisent un `DecisionContext` et consomment `VATPolicyDecision`.
- **P2 (posting) inchangé** : les `account_roles` sont traduits par les mappings comptables canoniques.

---
## 1. Points d'intégration réels (code existant)
- **A3 ventes** : `core/accounting/ar.py::_compute_lines(...)` → aujourd'hui `tax_engine.compute_line_tax(tax_code, net, on_date)` (legacy, `sales_tax_codes`).
- **A4 achats** : `core/accounting/ap.py` (~L202) → même appel `tax_engine.compute_line_tax(...)`.
- **Autorité cible** : `core/compliance/policy_engine.py::resolve(db, ws, co, domain="vat_ch", context=<DecisionContext>, as_of=<tax_date>)` → `VATPolicyDecision` : `{tax_treatment, tax_code, rate, side, recoverability{mode:full|none|partial|needs_review}, reporting_mapping{200/302/312/342/380/400/...}, account_roles{output_vat_role|input_vat_role|acquisition_vat_role}, vat_fx, legal_basis, vat_status, needs_review}` + snapshot immuable via `policy_engine.snapshot(decision)` et `explain(snap)`.
- **Profil + Gate** : `core/compliance/company_tax_profile.py` (`get_active_profile`, `get_activation`/`set_activation`, `can_manage`), collection `company_fiscal_activation`.
- **Override** : permission `accounting.vat_decision_override` (déjà au catalogue `core/access/permissions_catalog.py`).
- **Registre FX canonique** : `exchange_rates` (déjà utilisé par CH.2 `_vat_fx` et A4.6 closing) — **aucun second registre**.

---
## 2. État d'activation par société (state machine)
Étendre `company_fiscal_activation` d'un booléen vers un **état explicite** (append-only pour l'audit des transitions) :
`legacy` → `shadow` → `ready` → `active` (+ transition retour encadrée, voir §16).
Champs proposés : `{company_id, state, since, by, shadow_started_at, activated_at, activation_effective_at, last_parity_report_id, engine_version}`. Historique des transitions dans `fiscal_activation_audit`.
**Règle de passage à `active`** (toutes obligatoires) :
1. profil fiscal `complete` ; 2. aucun `policy_conflict` ; 3. shadow comparison exécutée sur un échantillon significatif ; 4. écarts classifiés ; 5. **0 anomalie bloquante** ; 6. activation explicitement autorisée (permission dédiée, voir §16).
Isolation stricte : A `active` n'impacte jamais B (`legacy`/`shadow`). Aucune bascule globale.

---
## 3. Shadow mode (observation, zéro impact)
En `shadow`, A3/A4 **continuent d'utiliser le legacy comme autorité opérationnelle** (facture, posting, snapshot legacy inchangés) MAIS appellent aussi `vat_ch.resolve(...)` **en parallèle**, sans effet transactionnel.
Comparaison par ligne/transaction : `legacy result` vs `VATPolicyDecision`. Classement :
- `parity` : mêmes traitement/taux/montant (à l'arrondi canonique près).
- `explained_difference` : écart attendu et justifiable (ex. legacy `EXEMPT` ↔ CH `exempt_without_credit` ; catégorie de taux équivalente ; version de taux datée).
- `blocking_difference` : divergence non expliquée (taux différent non justifié, `needs_review` CH là où legacy produisait un taux, rôle comptable incohérent).
Persistance : `fiscal_shadow_observations` `{company_id, tx_type(A3|A4), tx_id, line_id, legacy, ch_decision(snapshot léger), classification, at}`. **Le shadow ne modifie AUCUNE facture, AUCUN posting, AUCUN snapshot** ; il ne bloque jamais l'activité (sauf incident sécurité/archi indépendant). Coût maîtrisé via le cache `resolve` (clé `ws:co:inputs_hash`).

---
## 4. Rapport de parité (par société, grand public)
Endpoint : `GET /companies/{cid}/tax/activation/parity-report`. UX (aucun hash/policy_id) :
```
TVA — préparation à l'activation
128 transactions analysées
124 identiques ✓
4 différences expliquées
0 anomalie
Prête à être activée
```
Si anomalies : « 2 éléments nécessitent votre attention » + **drill-down jusqu'à la transaction** (et la ligne). Détail d'un écart : libellé métier + « Pourquoi ? » (via `explain(snap)`), jamais d'ID technique en UX normale.

---
## 5. Portée temporelle
À l'activation : définir `activation_effective_at` (date/instant d'effet clair, choisi par l'utilisateur autorisé, ≥ maintenant).
- Transactions **créées après** `activation_effective_at` → `vat_ch`.
- Transactions **existantes** → conservent leur snapshot fiscal historique.
**Jamais** de re-résolution automatique d'anciennes factures du seul fait de l'activation.

---
## 6. Nouvelles factures A3 (ventes) après activation
Dans `ar.py::_compute_lines` (branche `state==active`) : construire le `DecisionContext` par ligne et appeler `resolve(domain="vat_ch", context, as_of=tax_date)`, puis **snapshot** sur la ligne/facture.
`DecisionContext` A3 (clés déjà comprises par `_handle_vat_ch`) : `{side:"output", transaction_kind: domestic|export|..., tax_date, rate_category: standard|reduced|accommodation|exempt|out_of_scope, customer jurisdiction/contexte}`.
Happy Path : vente domestique sans catégorie → proposition `standard` (8,1 %) : « TVA 8,1 % ✓ / Pourquoi ? ». **Aucun choix manuel de tax code** si le contexte suffit. Le champ « tax_code » manuel devient un fallback/override, pas la saisie primaire.

---
## 7. Nouvelles factures A4 (achats) après activation
Même architecture dans `ap.py`. `DecisionContext` A4 : `{side:"input" (ou "both"), transaction_kind: domestic|services_from_abroad|import_goods, tax_date, recoverability_hint: business_taxable|excluded|mixed (+ mixed_rate), fournisseur + juridictions, lignes}`.
`vat_ch` décide (y compris impôt sur les acquisitions + récupérabilité). **A4 ne conserve aucune logique fiscale CH parallèle.**

---
## 8. Profil incomplet / décision impossible (utilisateur autorisé)
Si une opération requiert une donnée fiscale non résolue (profil `needs_attention`, ou `resolve` lève `policy_unavailable`) : **jamais** d'erreur technique. Afficher :
```
Une information TVA doit être confirmée
[Compléter maintenant]
```
« Compléter maintenant » = **deep-link CH.3** ouvrant l'assistant **directement sur le champ manquant précis** (ex. méthode de décompte), en **conservant intégralement le brouillon de facture**. Après correction/publication → **retour automatique à la facture** → **re-resolve** TVA → reprise exacte du workflow.

---
## 9. Utilisateur SANS `tax_profile_manage`
Afficher (lecture seule, cohérent CH.3) :
```
Une information TVA doit être confirmée
Cette configuration doit être complétée par une personne autorisée.
```
**Pas de « Compléter maintenant ».** Action légère « Notifier une personne autorisée » **uniquement si** le système de notification existant est réutilisable sans nouvelle infrastructure (à confirmer en implémentation ; sinon omis).

---
## 10. Conservation du brouillon (critère UX OBLIGATOIRE)
Le parcours Facture → Compléter TVA → Assistant CH.3 → retour facture ne perd **rien** : lignes, montants, document, client/fournisseur, PO, devise, notes, état de saisie. Aucun écran à recommencer.
Mécanisme proposé : persister/auto-sauver le brouillon de facture (déjà `status:"draft"`), naviguer vers CH.3 avec un retour contextuel (`return_to=invoice:<id>#field=<missing>`), puis re-résolution au retour. À valider : brouillon serveur vs état client conservé.

---
## 11. `needs_review`
Si `VATPolicyDecision.needs_review` (ex. usage mixte sans clé, récupérabilité indéterminée) : A3/A4 présentent **uniquement la décision manquante/ambiguë**, jamais un taux/défaut silencieux. Ex. :
```
Traitement TVA à confirmer
Cette dépense pourrait servir à une activité avec droit à déduction et une activité sans droit.
[action autorisée appropriée]
```

---
## 12. Overrides
Réutiliser `accounting.vat_decision_override`, **uniquement** quand la policy déclare la décision `overrideable` (les taux légaux `non_overrideable` restent immuables pour TOUS, y compris manage/admin/platform_admin — aucun bypass).
Override = permission sensible + **motif obligatoire** + `{ancienne_décision, nouvelle_décision, acteur, timestamp, snapshot}` + audit. Le snapshot override remplace la décision figée sur la ligne (append-only, traçable).

---
## 13. VAT FX
A3/A4 consomment le bloc `vat_fx` de `VATPolicyDecision` quand nécessaire (taux **à la date fiscale**). Ne jamais confondre : **transaction FX** (règlement) vs **VAT FX** (base TVA) vs **closing FX** (A4.6). Un seul registre `exchange_rates`.

---
## 14. Notes de crédit
Une note de crédit liée à une facture existante **hérite du snapshot fiscal de la transaction source** lorsque la règle CH.2 le prévoit. **Jamais** de re-résolution d'une note de crédit historique avec les taux/policies actuels. (Point d'intégration : logique notes de crédit A3/A4 existante — hériter `tax` snapshot de la facture source.)

---
## 15. Posting (P2 strictement inchangé)
Les `account_roles` de `VATPolicyDecision` (`output_vat_role`, `input_vat_role`, `acquisition_vat_role`, part non récupérable → `EXPENSE`) sont **traduits via les mappings comptables canoniques** existants. **Aucun** posting direct depuis le Policy Engine ; **aucun** journal fiscal séparé. Le moteur d'écritures P2 (`gl.py`) reste inchangé dans sa structure.

---
## 16. Activation (action explicite, auditée) + rollback
Écran :
```
Activer le moteur TVA
Profil fiscal : prêt ✓
Shadow comparison : 100 % conforme ✓
Aucune anomalie bloquante ✓
[Activer]   Pourquoi ?
```
Permission d'activation dédiée (proposée : `accounting.fiscal_engine_activate`, sensible, distincte de `tax_profile_manage`) — à confirmer lors du cadrage détaillé. Endpoint : `POST /companies/{cid}/tax/activation/activate` (garde fail-closed : profil `complete` + parité OK).
**Rollback** : autorisé UNIQUEMENT tant qu'**aucune transaction `vat_ch` n'a été créée** sous l'activation (retour `active`→`shadow`/`legacy` propre). Dès qu'une transaction `vat_ch` existe, **pas de retour silencieux** au legacy : toute réversion devient une décision explicite documentée (nouvelle stratégie/version), jamais automatique.

---
## 17. Observabilité (post-activation)
Suivre par société : nb décisions `vat_ch`, `needs_review`, overrides, erreurs de policy, différences de posting éventuelles, incidents. Sans exposer de données fiscales sensibles inutiles dans les logs plateforme (métadonnées d'accès uniquement, cf. pattern `security_events`).

---
## 18. Tests obligatoires (matrice de fermeture du Gate)
Société `legacy` inchangée ; `shadow` sans impact transactionnel ; rapport de parité ; `blocking_difference` empêche l'activation ; activation A sans effet B ; nouvelle facture A3 après activation ; nouvelle facture A4 après activation ; transaction historique inchangée ; profil incomplet ; deep-link « Compléter maintenant » ; utilisateur sans permission ; **conservation complète du draft** ; `needs_review` ; override autorisé ; taux légal `non_overrideable` non modifiable ; VAT FX ; note de crédit historique (héritage snapshot) ; posting P2 inchangé ; isolation/no-leak multi-société ; **aucune logique CH introduite dans A3/A4** ; performance resolve/cache ; changement futur de policy sans altérer les snapshots existants.

---
## 19. Gate STRAT-01 §21 — documentation avant code
- **Happy Path** : §6 (A3 8,1 %), §7 (A4), zéro choix manuel si contexte suffisant.
- **Exceptions** : §8 profil incomplet, §11 `needs_review`, §12 override, blocking_difference (§3/§16).
- **Décisions humaines** : compléter profil (CH.3), override (motivé), activation (autorisée).
- **Nombre de clics** : Happy Path = 0 clic fiscal ; exception = 1 clic « Compléter maintenant »/« Confirmer ».
- **UX Pourquoi ?** : `explain(snap)` partout, sans ID technique.
- **Stratégie shadow/activation** : §2, §3, §16 (par société, fail-closed).
- **Rollback** : §16 (sûr avant 1ʳᵉ transaction `vat_ch`, sinon explicite).
- **Impacts exacts A3/A4** : `ar.py::_compute_lines`, `ap.py` (~L202) → branchement conditionnel par `state==active`, sinon legacy.
- **Endpoints/modèles modifiés** : `company_fiscal_activation` (state machine) + `fiscal_activation_audit` + `fiscal_shadow_observations` ; `GET .../tax/activation/status|parity-report`, `POST .../tax/activation/{shadow|activate|rollback}` ; snapshot fiscal étendu sur lignes A3/A4.
- **Migrations** : migrer `fiscal_engine_active` (bool) → `state` (legacy/active) sans rien casser ; aucune donnée fiscale historique touchée.
- **Risques** : perf du double appel en shadow (mitigé par cache) ; cohérence arrondi legacy vs CH (classer en explained) ; UX perte de brouillon (critère bloquant §10) ; confusion FX (§13) ; tentation d'une logique CH résiduelle dans A3/A4 (interdit).

---
## Séquencement proposé (après validation du cadrage)
CH.3B.1 State machine + endpoints activation → CH.3B.2 Shadow mode + observations → CH.3B.3 Rapport de parité (UX) → CH.3B.4 Branchement A3 `active` + snapshot + « Pourquoi ? » → CH.3B.5 Branchement A4 (récupérabilité, acquisitions, VAT FX) → CH.3B.6 Exceptions UX (deep-link brouillon, needs_review, sans-permission) → CH.3B.7 Overrides → CH.3B.8 Notes de crédit (héritage) → CH.3B.9 Observabilité + Gate de fermeture (matrice §18).

**STOP — attendre validation utilisateur avant tout code. CH.4 reste STOP.**
