# A4.4 — CADRAGE DE GOUVERNANCE IA (Analyse documentaire des factures)
Statut : **CADRAGE POUR VALIDATION — AUCUN APPEL IA RÉEL**. Conforme STRAT-01 §10
(IA = assistance, jamais autorité) et à la Politique de gouvernance IA de
`A4_PLAN.md`. A4.4 reste **STOP** jusqu'à approbation explicite.

---
## 0. Résumé du GATE (à trancher AVANT toute activation)
- **Fournisseur pressenti** : modèle *vision* via l'**Emergent Universal LLM key**
  (`emergentintegrations`), option par défaut = OpenAI GPT vision.
- ⚠️ **BLOQUANT** : les garanties de gouvernance de la clé universelle Emergent
  (non-entraînement, rétention, sous-traitants/DPA, région, chiffrement) **NE SONT
  PAS documentées** (confirmé par le support Emergent, ce jour). Le gate STRAT-01
  interdit d'activer un fournisseur sans ces garanties écrites.
- **Deux voies d'activation possibles (au choix du client) :**
  1. **Emergent LLM key** — activable UNIQUEMENT après réception d'une attestation
     écrite d'Emergent (via support@emergent.sh) : non-entraînement, rétention
     (idéalement zéro/minimale), DPA + sous-traitants, région, chiffrement.
  2. **BYO provider key** (OpenAI / Anthropic / futur OCR UE-CH) — clé fournie par
     le client avec son propre DPA + zéro-rétention direct.
- Tant qu'aucune voie n'est confirmée : **l'IA reste désactivée**. A4.4 fonctionne en
  **mode manuel (fallback sans IA)** sans aucune perte de capacité comptable.

---
## 1. Périmètre & tâche utilisateur (STRAT-01 §21)
- **Tâche** : réduire la saisie d'une facture fournisseur à **une seule décision
  humaine** (Happy Path §3/§4). L'IA pré-remplit ; l'humain vérifie/corrige/approuve.
- **Ce que l'IA fait** : extraire, classifier (fournisseur probable), suggérer un
  rapprochement (PO/fournisseur), détecter une anomalie, **expliquer**.
- **Ce que l'IA ne fait JAMAIS** : approuver, comptabiliser (post), payer, clôturer,
  décider la fiscalité, contourner P1.13. (Preuve : §16 ci-dessous.)

## 2. Fournisseur IA envisagé
- **Abstraction obligatoire `DocumentAIProvider`** (§3) — A4 n'est jamais couplé à un
  fournisseur précis.
- Implémentation initiale envisagée : `EmergentVisionProvider` (GPT vision via clé
  universelle) **OU** `OpenAIVisionProvider` (BYO key). Architecture prête pour un
  futur `SwissOCRProvider` (région UE/CH) sans changer les appelants.
- Un fournisseur qui **ne peut pas attester le non-entraînement n'est pas activable**
  (drapeau `attestation.non_training = false` ⇒ provider refusé au démarrage).

## 3. Abstraction `DocumentAIProvider`
Interface (contrat), aucune logique métier fiscale/comptable dedans :
```
class DocumentAIProvider(ABC):
    name: str; model: str; model_version: str
    # Attestation de gouvernance déclarée par le provider (vérifiée au boot)
    def attestation(self) -> ProviderAttestation:
        # { non_training: bool, retention: 'zero'|'minimal'|'<days>',
        #   subprocessors: [...], region: str|None, encryption_in_transit: bool,
        #   encryption_at_rest: bool, deletion_supported: bool, dpa_ref: str|None }
        ...
    async def extract_invoice(self, *, document_bytes|storage_ref, company_id,
                              workspace_id, request_id, hints) -> ExtractionResult:
        ...  # renvoie un ExtractionResult structuré (§18), JAMAIS une écriture
    def health(self) -> ProviderHealth: ...   # dispo / quota / latence
```
- **Registre de providers** extensible (comme le nav-badge registry) ; sélection par
  configuration société/workspace ; **jamais** de `if provider == 'gpt'` dans les
  modules métier.
- Au démarrage : si `attestation.non_training` n'est pas `True`, le provider est
  chargé en **mode inactif** (extraction indisponible → fallback manuel).

## 4. Données transmises (minimisation — STRAT-01 §10)
- **Transmis** : le strict nécessaire pour lire la facture — image/PDF de la facture
  fournisseur (ou pages pertinentes), + éventuels *hints* non sensibles (devise
  attendue, liste de noms de fournisseurs connus pour l'appariement — **sans**
  IBAN/numéros fiscaux internes).
- **Exclus explicitement** : plan comptable, journaux, autres factures, données
  d'autres sociétés, coordonnées bancaires internes Meelora, secrets/API keys,
  identités utilisateurs, historique de paiements, permissions, tout PII non présent
  sur le document lui-même. Aucune donnée d'un autre tenant.
- **Redaction optionnelle** (roadmap) : masquer des zones sensibles avant envoi si le
  client l'exige.

## 5. Garanties de non-entraînement (exigence absolue)
- Les documents, images, texte extrait, prompts et résultats Meelora **ne doivent
  jamais** servir à entraîner / fine-tuner / améliorer un modèle partagé, ni à un
  apprentissage croisé entre tenants, ni à une réutilisation commerciale.
- Les **corrections humaines** restent dans les données/audit de la société ; elles
  ne sont **jamais** transformées automatiquement en données d'entraînement.
- Exigé par écrit du fournisseur retenu (voir §0). Stocké dans `attestation`.

## 6. Politique de rétention
- **Document original** : conservé UNIQUEMENT dans l'Object Storage canonique Meelora
  (SHA-256, versionné, immuable) — jamais le fournisseur IA comme archive.
- **Côté fournisseur IA** : viser **zéro-rétention** ; à défaut, rétention minimale
  documentée (ex. purge ≤ 30 j) et contractualisée.
- **Côté Meelora** : `ap_extractions` conservé pour audit/traçabilité (résultat +
  confiance + provenance + corrections), soumis aux règles d'archivage
  réglementaire (GeBüV/Olico) du Country Pack.

## 7. Sous-traitants (subprocessors)
- À documenter selon la voie retenue : Emergent (proxy) → OpenAI/Anthropic/Google ;
  ou fournisseur direct BYO. Liste conservée dans `attestation.subprocessors` et
  présentée au client. Tout changement de sous-traitant = revalidation.

## 8. Région / localisation
- À confirmer (US par défaut probable côté clé universelle). Si conformité CH/UE
  requise : privilégier un provider/région UE-CH (voie BYO ou futur `SwissOCRProvider`).
- `attestation.region` exposé ; si `None`/US et exigence de résidence → provider non
  activable pour ce mandat.

## 9. Chiffrement
- **En transit** : TLS obligatoire (déclaré `encryption_in_transit`).
- **Au repos** : documents dans Object Storage chiffré ; `ap_extractions` en base
  Meelora. Attestation `encryption_at_rest` du fournisseur requise.

## 10. Suppression
- Capacité de suppression sur demande (droit à l'effacement) : document original
  (selon rétention légale), extraction, et — si le fournisseur retient des données —
  déclenchement d'une purge côté fournisseur (`deletion_supported`).

## 11. Isolation société / workspace
- Chaque appel porte `company_id` + `workspace_id` + `request_id` ; aucun contexte
  d'une autre société n'est jamais transmis ni mélangé. Les *hints* (ex. liste
  fournisseurs) sont filtrés à la société active. Résultats stockés scoppés société.
- Aucun cache/état partagé inter-tenant côté Meelora.

## 12. Protection prompt injection / document malveillant
- Le contenu du document est traité comme **donnée non fiable** : le prompt système
  isole les instructions ; toute « instruction » présente dans le document est
  ignorée (l'IA n'exécute jamais d'action, elle ne fait que remplir un schéma §18).
- Validation stricte de la sortie : **schéma JSON contraint** ; tout champ hors
  schéma est rejeté. L'IA ne peut produire que des valeurs de données, jamais des
  ordres (pas de function-calling vers des actions sensibles).
- Contrôles fichier : type/MIME, taille max, nb de pages max, anti-« zip bomb »/PDF
  malveillant, antivirus (roadmap), rendu en image sécurisé. Rejet → exception visible
  avec prochaine action (§15).
- Aucune donnée extraite n'entraîne d'action automatique (pas de post/paiement).

## 13. Séparation stricte : extraction IA ≠ décisions fiscales/comptables
- L'IA renvoie les montants/taxes **tels que lus** sur le document (hints bruts).
- La **détermination fiscale** reste au moteur fiscal versionné (STRAT-01 §12), avec
  contexte complet + **snapshot fiscal immuable** ; la **comptabilisation** reste au
  Financial Core P2 (§7). L'extraction ne pré-décide jamais le compte, le taux ni le
  traitement — elle propose des valeurs à confirmer.
- Aucune écriture n'est jamais créée par le provider ; le flux A4.2 (verify → submit
  → approve → post, permissions sensibles) reste l'unique voie de comptabilisation.

## 14. Journal d'audit IA (`ap_ai_audit`)
Par analyse, **sans secrets ni prompt brut sensible** :
`provider | model | model_version | timestamp | company_id | workspace_id |
document_id | request_id | status (ok/partial/error/rejected) | latency_ms |
page_count | overall_confidence | fields_low_confidence[] | human_corrections[] |
attestation_snapshot (non_training/retention/region au moment de l'appel)`.
Immuable, consultable pour « Pourquoi ? » (§17) et conformité.

## 15. Gestion des erreurs / provider indisponible + fallback sans IA
- `health()` + timeouts + retry borné ; **circuit breaker** : si le provider est
  indisponible/quota dépassé/attestation invalide → passage transparent en
  **mode manuel**.
- **Fallback sans IA (obligatoire)** : l'utilisateur peut toujours saisir/valider la
  facture manuellement (flux A4.2 intact). Aucune fonctionnalité comptable ne dépend
  de l'IA. Message clair : « Extraction indisponible — saisie manuelle » + prochaine
  action (Every Error Has a Next Action, STRAT-01 §3).
- Aucune valeur inventée : un champ non extrait = vide/à saisir, jamais un défaut
  fiscal implicite.

## 16. Preuve qu'aucune IA ne peut approuver / poster / payer / contourner P1.13
- Le provider ne dispose d'**aucune** route d'écriture : `extract_invoice` renvoie un
  DTO `ExtractionResult`, jamais un appel à `create_workflow_journal_entry`,
  `post_invoice`, `mark_executed`, `post_payment`, etc.
- Les actions sensibles restent derrière `require_sensitive_permission`
  (supplier_invoice_approve/post, supplier_payment_post, …) — exécutées par un
  **humain authentifié**, jamais par un token/service IA.
- Aucune identité machine « IA » n'existe dans le modèle d'autorisation P1.13 ; l'IA
  n'est ni membership, ni rôle, ni permission. Backend = autorité.
- Maker-checker préservé : l'extraction ne peut pas jouer le rôle de créateur ET
  d'approbateur.
- Tests d'acceptation A4.4 (futurs) incluront : « un résultat d'extraction, même à
  100 % de confiance, ne crée aucune écriture et n'avance aucun statut sans action
  humaine autorisée ».

## 17. UX (STRAT-01 §3)
- **Happy Path First** : facture entrante → champs pré-remplis → l'utilisateur voit
  un récapitulatif propre → **1 clic** « Vérifier & soumettre » si tout est cohérent.
- **Exceptions First** : n'afficher en évidence que les champs à faible confiance /
  incohérents / manquants (ex. « Fournisseur non reconnu », « Total ne correspond pas
  aux lignes », « PO manquant ») ; le reste est replié.
- **Progressive Disclosure** : confidence, provenance (page/zone), texte brut OCR,
  modèle/version → **cachés** dans l'UX normale ; accessibles via un panneau
  « Pourquoi ? » destiné aux professionnels.
- **Pourquoi ?** : pour chaque valeur pré-remplie, expliquer la source (« lu page 1 »,
  « fournisseur apparié par n° TVA », « défaut société ») et permettre le drill-down
  ≤ 3 niveaux jusqu'au document source.

## 18. Schéma de données du résultat d'extraction
> Confiance + provenance **par champ**, mais **jamais exposés dans l'UX normale**
> (uniquement via « Pourquoi ? »). Aucune écriture n'en découle automatiquement.

Collection `ap_extractions` :
```
{
  id, company_id, workspace_id, document_id, inbox_item_id,
  provider, model, model_version, request_id,
  status: 'ok'|'partial'|'error'|'rejected',
  created_at, latency_ms, page_count, overall_confidence: 0..1,
  attestation_snapshot: { non_training, retention, region },
  fields: {
    supplier:            Field<{ name:str, matched_supplier_id:str|null, match_basis:'vat'|'name'|'iban'|null }>,
    supplier_invoice_number: Field<str>,
    invoice_date:        Field<date>,
    due_date:            Field<date>,
    currency:            Field<str>,
    po_number:           Field<str|null>,
    subtotal:            Field<number>,
    tax_total:           Field<number>,   # LU sur le document (hint), non décisionnel
    total:               Field<number>,
    vat_number_seller:   Field<str|null>,
    payment_reference:   Field<str|null>, # ex. QR-ref CH (validé plus tard par Country Pack)
    iban:                Field<str|null>,
    lines: [ LineField<{ description, qty, unit_price, line_net, tax_hint }> ]
  },
  consistency: { total_matches_lines: bool, tax_plausible: bool, duplicate_suspected: bool },
  corrections: [ { field_path, old_value, new_value, by_user_id, at } ],  # tenant-only, jamais training
  needs_review_fields: [ 'field_path', ... ]
}
```
Type générique `Field<T>` :
```
Field<T> = {
  value: T | null,
  confidence: 0..1,                 # interne — non affiché en UX normale
  provenance: {
    source: 'ai'|'human'|'default'|'lookup',
    page: int|null, bbox: [x,y,w,h]|null,   # zone d'origine si dispo
    raw_snippet_ref: str|null        # référence (pas le texte brut) — jamais exposé UX normale
  },
  needs_review: bool                 # dérive un affichage "Exceptions First"
}
```
Règles :
- `source:'ai'` sur des champs pré-remplis, `source:'human'` après correction,
  `source:'default'|'lookup'` pour smart defaults / apparn fournisseur.
- **Aucun** champ `confidence`/`bbox`/`raw_snippet_ref` n'est rendu dans l'écran
  normal ; ils alimentent seulement « Pourquoi ? » et l'ordre d'affichage des
  exceptions (needs_review d'abord).
- `tax_total`/`tax_hint` sont des **indices de lecture**, remplacés par la décision du
  moteur fiscal versionné + snapshot au moment de la soumission/comptabilisation.

## 19. Gate STRAT-01 §21 — réponses
1. Tâche : saisir une facture fournisseur en ~1 décision humaine. 2. Happy Path :
entrée → pré-rempli → 1 clic soumettre. 3. Décisions humaines : 1 (vérif/approbation).
4. Pré-remplissage : maximal (extraction + smart defaults + apparn fournisseur).
5. Exceptions visibles : faible confiance / incohérence total-lignes / fournisseur
non reconnu / PO manquant / doublon. 6. Terme comptable requis : non (mécanique
cachée). 7. « Pourquoi ? » : oui (provenance par champ). 8. Erreur → prochaine action :
oui (fallback manuel). 9. Drill-down ≤ 3 : oui (champ → extraction → document source).
10. P1.13 & Financial Core : respectés (IA sans autorité). 11. Country Packs :
compatible (fiscalité/QR/validation restent hors extraction). 12. Duplication de
données/moteur : non (une seule vérité ; original en Object Storage).

## 20. Prérequis d'activation (bloquants) & décisions attendues
- [ ] **Choix de la voie fournisseur** : (a) Emergent LLM key **avec attestation
  écrite** obtenue via support@emergent.sh, ou (b) BYO key (OpenAI/Anthropic/OCR UE)
  avec DPA/zéro-rétention.
- [ ] Réception & archivage de l'attestation (non-entraînement, rétention, DPA,
  région, chiffrement, suppression).
- [ ] Exigence de résidence des données (US acceptable ? ou UE/CH imposée ?).
- [ ] Budget/coût par page acceptable.
- [ ] Validation de ce cadrage par le client.
Tant que ces cases ne sont pas cochées : **IA désactivée, A4.4 en mode manuel**.

---
**STOP** — Aucun appel IA réel, aucune implémentation, tant que ce cadrage n'est pas
approuvé et qu'une voie fournisseur conforme (§0/§20) n'est pas confirmée.
