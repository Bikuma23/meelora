# CH.3 — CADRAGE : Profil société suisse + Assistant d'installation (AUCUN CODE)
Transforme CH.1 (Policy Engine) + CH.2 (`vat_ch`) en **configuration initiale ultra-simple** pour
une PME suisse. Principe : Meelora pose des **questions métier**, construit le profil fiscal/
comptable **en arrière-plan** ; l'utilisateur ne touche jamais `jurisdiction_policies`,
`VATPolicyDecision`, rôles ni mappings. Conforme STRAT-01 (§7 Core intact, §11/§12, §21).
**STOP après ce cadrage — aucun recâblage A3/A4.**

---
## 1. SÉPARATION identité société / profils versionnés
Trois objets distincts (ne pas surcharger la fiche société) :
- **`company_identity`** (existant `companies`, inchangé) : raison sociale, logo, adresse, pays,
  canton/subdivision, devise fonctionnelle, coordonnées, **UID**. Modifier logo/adresse **ne crée
  jamais** de version fiscale.
- **`company_tax_profile`** (NOUVEAU, versionné) : choix TVA susceptibles d'évoluer.
- **`accounting_policy_profile`** (NOUVEAU, versionné) : liaisons de politiques comptables (arrondi,
  fraîcheur FX, futur preset CoA CH.5) — pré-câblé, minimal en CH.3.
> Les profils versionnés étendent le `company_jurisdiction_profile` posé en CH.1 (bindings), sans le
> dupliquer : `company_tax_profile` EST la source des `vat_status/vat_method/vat_number/périodicité`.

### Modèle proposé
```
company_tax_profile (append-only versions)
{
  _id, workspace_id, company_id, profile_version, status: draft|published,
  effective_from, effective_to?,                # versioning temporel (§5)
  country, canton,                              # copiés/confirmés (contexte de résolution)
  vat_status: 'taxable' | 'not_taxable' | 'unknown',
  vat_number,                                   # UID + suffixe (nullable si non assujetti)
  vat_number_validation: { format_ok, checksum_ok, online_checked?, online_status? },
  vat_method: 'effective' | 'net_tax_rate' | 'unknown',
  vat_method_start,                             # date de début de méthode
  vat_period: 'quarterly' | 'semiannual' | null,
  net_tax_rates?: [ {sector, rate, effective_from} ],   # TDFN (profil seulement; calcul CH.4)
  completeness: 'complete' | 'needs_attention' | 'not_configured',   # §11
  unresolved: [ {field, reason, blocks:[domains]} ],    # « À confirmer » (§3)
  created_by, created_at, published_at, source_entry: 'onboarding'|'edit'|'fiduciary'|'migration'
}
accounting_policy_profile (append-only versions)  # bindings arrondi/FX/(CoA futur)
{ _id, ws, co, profile_version, status, effective_from, policy_bindings:[{domain, policy_id}],
  created_by, created_at, published_at }
```

## 2. ÉTATS DU PROFIL (§11)
`not_configured` (aucune version publiée) · `needs_attention` (publié mais `unresolved` non vide, ex.
`vat_status=unknown`) · `complete` (aucun champ bloquant manquant). L'entreprise **utilise librement**
tout ce qui ne dépend pas des champs manquants ; une opération exigeant une décision fiscale
impossible est **fail-closed** avec action claire (§11), jamais une erreur technique.

## 3. ASSISTANT INITIAL — 5 à 7 questions max
Écran par écran (Progressive Disclosure ; les paramètres avancés restent masqués) :
1. **Votre entreprise** : Pays (défaut Suisse si `company.country=CH`), Canton (auto-proposé depuis
   l'adresse si identifiable).
2. **Devise fonctionnelle** : pré-remplie (CHF), confirmable.
3. **TVA — assujettie ?** : Oui / Non / **Je ne sais pas**.
4. *(si Oui)* **N° TVA** : `CHE-123.456.789 TVA` (validation format/checksum locale).
5. *(si Oui)* **Méthode de décompte** : Effective / TDFN / **Je ne sais pas**.
6. *(si Oui)* **Date de début**.
7. **Aperçu & activation** (§6).
Fin possible pour une PME standard en ~5–7 questions ; le reste est déduit/proposé.

## 4. « JE NE SAIS PAS » — vrai parcours (jamais bloquant)
Aucune notion fiscale n'est imposée pour terminer l'installation. Toute réponse à conséquence
réglementaire → `unknown` produit **« À confirmer »** dans `unresolved` (jamais une config inventée).
Meelora affiche **« Pourquoi cette information ? »** (langage grand public) et laisse continuer
**tant que c'est comptablement sûr**. La décision manquante déclenche un **fail-closed au bon
moment** (ex. émettre une facture TVA nécessite `vat_status/vat_method` → sinon « Configuration TVA
à compléter → Compléter maintenant »).

## 5. VERSIONING TEMPOREL
Toute modification fiscale porte une **date d'effet** (« À partir de quand ? » ex. 01.01.2027) →
**nouvelle version** `company_tax_profile` (append-only, comme CH.1). Les transactions antérieures
restent rattachées à leurs snapshots/décisions historiques. **Mutations silencieuses interdites**
sur une version publiée (draft éditable, published immuable).

## 6. PREVIEW avant activation
Résumé compréhensible (**pas de JSON/codes/vocabulaire moteur**) :
```
Configuration proposée
Suisse · Genève · Assujetti TVA ✓ · Méthode effective · CHF · À partir du 01.01.2027
[Activer]   [Pourquoi ces paramètres ?]
```
« Activer » publie la version ; « Pourquoi ? » explique chaque choix (source, effet).

## 7. MODIFICATIONS ULTÉRIEURES — même modèle canonique
L'onboarding **crée la première version** des vrais profils. L'édition future consomme le **même**
modèle (pas d'`onboarding settings` séparés). Un seul écran de configuration réutilisé.

## 8. CAS FIDUCIAIRE (préparé, non développé)
Le modèle prévoit `source_entry='fiduciary'` : un fiduciaire autorisé peut configurer le profil d'un
mandat via les **mêmes permissions/audit** que le client (aucun chemin privilégié). **Workflow
fiduciaire complet = hors CH.3** (tranche ultérieure) ; on garantit seulement que l'architecture ne
le bloque pas.

## 9. PERMISSIONS
- **Lecture** du profil : selon droits ACCOUNTING view (large).
- **Publier/modifier** le profil fiscal : NOUVELLE permission sensible **`accounting.tax_profile_manage`**
  via `require_sensitive_permission` — **aucun bypass** manage / Client Admin / platform_admin
  (Client Admin n'est PAS automatiquement autorité fiscale).
- **Maker-checker** : **non imposé** aux TPE par défaut ; prévu comme **option future** activable par
  politique société pour les modifications sensibles (changement de méthode, d'assujettissement).
- Audit complet (§ ci-dessous) quel que soit le point d'entrée (onboarding/edit/fiduciary/migration).

## 10. AUDIT
Événement immuable à chaque publication de version : `{company_id, profile_version, effective_from,
changed_fields (old→new pour champs non sensibles ; pour champs sensibles : marqueur + acteur),
vat_status, vat_method, by, source_entry, at}`. Aucune donnée secrète. Isolation `{ws,co}`.

## 11. PROFIL INCOMPLET — comportement
`completeness` pilote l'accès **par dépendance**, pas globalement : les fonctions sans dépendance
fiscale marchent ; une facture TVA sans `vat_status` → blocage ciblé « Configuration TVA à compléter
→ Compléter maintenant » (fail-closed **au moment de l'action**, cf. domaines `required` de CH.2).

## 12. MIGRATION des sociétés existantes (non destructive)
Rapport **par société** en 3 colonnes : **Confirmées** (ex. pays depuis `companies`), **Déduites**
(ex. canton depuis l'adresse, `vat_status` supposé) , **À confirmer**. **Aucun champ fiscal sensible
ne passe de « supposé » à « confirmé » silencieusement** : les déductions restent `unresolved`
jusqu'à validation humaine. Migration crée une **version `draft` pré-remplie** (source
`migration`), publiée seulement après revue → non destructive, réversible.

## 13. ACTIVATION GATE FISCAL (A3/A4) — futur, défini ici
Séquence stricte avant que `vat_ch` devienne autoritatif :
```
CH.1 moteur + CH.2 règles + CH.3 profil société (complete)
  → shadow comparison (vat_ch vs sales_tax_codes, parité exigée)
  → Activation Gate (par société)
  → A3/A4 basculent sur vat_ch pour les NOUVELLES transactions
```
Tant que le `company_tax_profile` requis n'existe pas (ou `needs_attention` sur un champ bloquant),
**aucune nouvelle transaction ne bascule** ; A3/A4 restent sur le chemin actuel (`sales_tax_codes`).
**CH.3 ne recâble PAS A3/A4** — il ne fait que rendre l'activation possible et sûre.

---
## TESTS UX / PERSONAS (Gate CH.3)
Même architecture, Progressive Disclosure :
- **Entrepreneur sans compta** : termine le parcours normal (5–7 questions) **sans connaître aucun
  code TVA** ; « Je ne sais pas » possible partout → profil `needs_attention`, app utilisable.
- **Comptable PME** : accède aux paramètres avancés (méthode, périodicité, dates d'effet), contrôle
  et corrige.
- **Fiduciaire** : comprend en un écran la config d'un mandat (aperçu §6), mêmes permissions/audit.
Autres tests : validation UID offline (format/checksum) + enrichissement online **non bloquant** ;
« Je ne sais pas » ne fabrique jamais de config ; blocage fail-closed ciblé au moment d'une facture
TVA sans profil ; versioning (nouvelle version à date d'effet, historique intact) ; migration 3
colonnes sans promotion silencieuse ; permission `tax_profile_manage` sans bypass admin/manage ;
isolation `{ws,co}`.

## IMPACTS CH.1 / CH.2
- CH.1 : `company_tax_profile` **alimente** le `DecisionContext` (vat_status, canton, méthode) déjà
  attendu par `resolve()`. Interface canonique déjà prête — **CH.1 non modifié**.
- CH.2 : `vat_ch` consommera `vat_status`/méthode du profil (déjà pris en compte : cf. acquisition
  tax par statut). **CH.2 non modifié** ; seul le profil devient la source officielle du contexte.
- **A3/A4 : aucun changement en CH.3** (recâblage = Activation Gate ultérieur).

## RÉPONSES STRAT-01 §21
1. **Tâche** : configurer une PME suisse en quelques questions métier, sans jargon fiscal.
2. **Happy Path** : 5–7 questions → aperçu → Activer.
3. **Décisions humaines** : ~5–7 réponses simples ; 0 concept technique.
4. **Pré-remplissage** : pays/canton/devise/UID déduits ; l'utilisateur confirme.
5. **Exceptions visibles** : « Je ne sais pas » → À confirmer ; UID invalide ; profil `needs_attention`.
6. **Terme comptable requis ?** Non ; « effective/TDFN/assujetti » expliqués via « Pourquoi ? ».
7. **Pourquoi ?** Sur chaque proposition (source, effet, base légale).
8. **Erreur → prochaine action** : « Configuration TVA à compléter → Compléter maintenant ».
9. **Drill-down ≤ 3** : Décision fiscale d'une facture → version de profil active → champ/source.
10. **P1.13 & Core** : `accounting.tax_profile_manage` sensible sans bypass ; profils append-only ;
    aucun ledger parallèle ; Core P2 & historique intacts.
11. **Country Packs** : profil = données société ; l'assistant est piloté par le pack CH ; CA/EU
    réutiliseront le même modèle avec leurs questions.
12. **Duplication ?** Non — onboarding et édition partagent le même modèle canonique ; le profil
    étend `company_jurisdiction_profile` (CH.1) sans dupliquer identité ni règles.

---
**STOP** — attendre validation (modèle `company_tax_profile`/`accounting_policy_profile`, états,
parcours onboarding + « Je ne sais pas », auto-proposition vs confirmation, preview/activation,
permission `accounting.tax_profile_manage`, migration 3 colonnes, stratégie fiduciaire, Activation
Gate A3/A4, personas) **avant tout développement**. Aucun recâblage A3/A4.
