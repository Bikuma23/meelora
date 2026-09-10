import { useEffect, useMemo, useState } from "react";
import { useNav } from "../context/NavContext";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "../components/ui/popover";
import { Input } from "../components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { Textarea } from "../components/ui/textarea";
import {
  Loader2, ShieldCheck, HelpCircle, Check, ChevronRight, ChevronLeft, AlertCircle,
  CircleDot, Pencil, History, Power, X, Info, ArrowRight, Ban, CalendarClock,
} from "lucide-react";

// Swiss cantons (code -> name). Used to pre-fill / confirm the fiscal context.
const CANTONS = [
  ["ZH", "Zurich"], ["BE", "Berne"], ["LU", "Lucerne"], ["UR", "Uri"], ["SZ", "Schwytz"],
  ["OW", "Obwald"], ["NW", "Nidwald"], ["GL", "Glaris"], ["ZG", "Zoug"], ["FR", "Fribourg"],
  ["SO", "Soleure"], ["BS", "Bâle-Ville"], ["BL", "Bâle-Campagne"], ["SH", "Schaffhouse"],
  ["AR", "Appenzell Rh.-Ext."], ["AI", "Appenzell Rh.-Int."], ["SG", "Saint-Gall"], ["GR", "Grisons"],
  ["AG", "Argovie"], ["TG", "Thurgovie"], ["TI", "Tessin"], ["VD", "Vaud"], ["VS", "Valais"],
  ["NE", "Neuchâtel"], ["GE", "Genève"], ["JU", "Jura"],
];
const cantonName = (c) => (CANTONS.find(([k]) => k === c) || [])[1] || c;
// Friendly errors — never surface raw permission codes/slugs to the user.
const apiError = (e, fallback) => {
  if (e?.response?.status === 403) return "Vous n'avez pas les droits pour modifier la configuration TVA. Contactez votre administrateur.";
  return e?.response?.data?.detail || fallback;
};
// Migration may pre-fill a canton NAME (e.g. "Genève") rather than a code ("GE").
const normalizeCanton = (v) => {
  if (!v) return "";
  const s = String(v).trim();
  if (CANTONS.some(([k]) => k === s.toUpperCase())) return s.toUpperCase();
  const byName = CANTONS.find(([, n]) => n.toLowerCase() === s.toLowerCase());
  return byName ? byName[0] : "";
};

const METHOD_LABEL = { effective: "Méthode effective", net_tax_rate: "Taux de la dette fiscale nette (TDFN)" };
const STATUS_UI = {
  not_configured: { label: "Non configuré", cls: "bg-slate-100 text-slate-500" },
  needs_attention: { label: "À compléter", cls: "bg-[#FBBF24]/15 text-[#B45309]" },
  complete: { label: "Configuré", cls: "bg-[#22C55E]/12 text-[#15803D]" },
};

function Why({ text, testid }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" data-testid={testid}
          className="inline-flex items-center gap-1 text-[11px] font-500 text-slate-400 underline decoration-dotted underline-offset-2 transition-colors hover:text-[#15AF97]">
          <HelpCircle size={12} /> Pourquoi cette information ?
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" sideOffset={6} className="w-72 text-xs leading-relaxed text-slate-600" data-testid={`${testid}-content`}>
        {text}
      </PopoverContent>
    </Popover>
  );
}

function Choice({ label, active, onClick, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={`flex items-center justify-between rounded-xl border px-4 py-3 text-left text-sm transition-colors ${
        active ? "border-[#15AF97] bg-[#15AF97]/8 font-700 text-[#063044]" : "border-slate-200 font-600 text-slate-600 hover:border-slate-300 hover:bg-slate-50"
      }`}>
      <span>{label}</span>
      {active && <Check size={16} className="text-[#15AF97]" />}
    </button>
  );
}

// ---- Onboarding / edit wizard ------------------------------------------------
function Wizard({ cid, prefill, mode, active, onDone, onCancel }) {
  const currentYear = new Date().getFullYear();
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [f, setF] = useState({
    country: (prefill?.country || "CH").toUpperCase(),
    canton: normalizeCanton(prefill?.canton),
    vat_status: prefill?.vat_status && prefill.vat_status !== "unknown" ? prefill.vat_status : "",
    vat_number: prefill?.vat_number || "",
    vat_method: prefill?.vat_method && prefill.vat_method !== "unknown" ? prefill.vat_method : "",
    effective_from: mode === "rectify" ? active?.effective_from
      : mode === "amend" ? new Date().toISOString().slice(0, 10)
      : `${currentYear}-01-01`,
  });
  const set = (k, v) => setF((s) => ({ ...s, [k]: v }));
  const rectify = mode === "rectify";

  // Live local UID validation (mirror of the backend offline rule — never a proof).
  const uidCheck = useMemo(() => {
    const raw = (f.vat_number || "").trim();
    if (!raw) return null;
    const m = raw.replace(/MWST|TVA|IVA/gi, "").trim().match(/^CHE[-\s]?(\d{3})[.\s]?(\d{3})[.\s]?(\d{3})$/i);
    if (!m) return { ok: false, msg: "Format attendu : CHE-123.456.789" };
    const d = m.slice(1).join("");
    const w = [5, 4, 3, 2, 7, 6, 5, 4];
    let t = 0; for (let i = 0; i < 8; i++) t += parseInt(d[i], 10) * w[i];
    let c = 11 - (t % 11); if (c === 11) c = 0;
    const ok = c !== 10 && c === parseInt(d[8], 10);
    return ok
      ? { ok: true, msg: `Numéro valide · CHE-${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}` }
      : { ok: false, msg: "La somme de contrôle ne correspond pas." };
  }, [f.vat_number]);

  const taxable = f.vat_status === "taxable";
  // Ordered steps. A rectification keeps the SAME effective date → no date step.
  const dateStep = rectify ? [] : ["date"];
  const steps = taxable
    ? ["company", "liability", "vat_number", "method", ...dateStep, "review"]
    : ["company", "liability", ...dateStep, "review"];
  const cur = steps[step];
  const last = step === steps.length - 1;

  const canNext = () => {
    if (cur === "company") return !!f.country;
    if (cur === "liability") return !!f.vat_status;
    return true; // number/method/date all allow "Je ne sais pas" / optional
  };

  const submit = async () => {
    setBusy(true);
    try {
      const payload = {
        country: f.country, canton: f.canton || null,
        effective_from: f.effective_from,
        vat_status: f.vat_status || "unknown",
      };
      if (taxable) {
        payload.vat_number = f.vat_number || null;
        payload.vat_method = f.vat_method || "unknown";
        payload.vat_method_start = f.effective_from;
      }
      if (rectify && active?._id) {
        payload.supersedes_version_id = active._id;
        payload.supersession_reason = "Rectification de la période en cours";
      }
      const draft = await api.createTaxDraft(cid, payload);
      await api.publishTaxProfile(cid, draft._id);
      toast.success(rectify ? "Configuration mise à jour" : "Configuration TVA enregistrée");
      onDone();
    } catch (e) {
      toast.error(apiError(e, "Échec de l'enregistrement"));
    } finally { setBusy(false); }
  };

  const unresolvedPreview = [];
  if (f.vat_status === "unknown" || !f.vat_status) unresolvedPreview.push("Assujettissement TVA à confirmer");
  else if (taxable) {
    if (f.vat_method === "unknown" || !f.vat_method) unresolvedPreview.push("Méthode de décompte à confirmer");
    if (!f.vat_number) unresolvedPreview.push("Numéro de TVA à renseigner");
  }

  return (
    <div className="mx-auto max-w-xl" data-testid="tax-wizard">
      {/* Progress */}
      <div className="mb-6 flex items-center gap-1.5" data-testid="tax-wizard-progress">
        {steps.map((s, i) => (
          <span key={s} className={`h-1.5 flex-1 rounded-full transition-colors ${i <= step ? "bg-[#15AF97]" : "bg-slate-200"}`} />
        ))}
      </div>

      <div className="card p-6">
        {cur === "company" && (
          <div className="space-y-5" data-testid="tax-step-company">
            <div>
              <h2 className="font-display text-xl font-700 text-[#063044]">Votre entreprise</h2>
              <p className="mt-1 text-sm text-slate-500">Nous avons pré-rempli ces informations. Confirmez ou ajustez si besoin.</p>
            </div>
            <div>
              <label className="mb-1 block text-xs font-700 uppercase tracking-wide text-slate-500">Pays</label>
              <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-600 text-[#063044]" data-testid="tax-country">
                <span className="text-base">🇨🇭</span> Suisse
              </div>
            </div>
            <div>
              <label className="mb-1 block text-xs font-700 uppercase tracking-wide text-slate-500">Canton</label>
              <select value={f.canton} onChange={(e) => set("canton", e.target.value)} data-testid="tax-canton"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-[#063044] outline-none focus:border-[#15AF97]">
                <option value="">Sélectionner…</option>
                {CANTONS.map(([k, n]) => <option key={k} value={k}>{n}</option>)}
              </select>
              {prefill?.canton && (
                <p className="mt-1.5 flex items-center gap-1 text-[11px] text-slate-400" data-testid="tax-canton-hint">
                  <Info size={11} /> Proposé à partir de l'adresse de l'entreprise
                </p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-xs font-700 uppercase tracking-wide text-slate-500">Devise fonctionnelle</label>
              <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-600 text-[#063044]" data-testid="tax-currency">CHF · Franc suisse</div>
            </div>
          </div>
        )}

        {cur === "liability" && (
          <div className="space-y-4" data-testid="tax-step-liability">
            <div>
              <h2 className="font-display text-xl font-700 text-[#063044]">Êtes-vous assujetti à la TVA ?</h2>
              <p className="mt-1 text-sm text-slate-500">Si vous n'êtes pas certain, choisissez « Je ne sais pas » — vous pourrez le confirmer plus tard.</p>
            </div>
            <div className="grid gap-2.5">
              <Choice label="Oui, mon entreprise est assujettie" active={f.vat_status === "taxable"} onClick={() => set("vat_status", "taxable")} testid="tax-liability-yes" />
              <Choice label="Non, pas assujettie" active={f.vat_status === "not_taxable"} onClick={() => set("vat_status", "not_taxable")} testid="tax-liability-no" />
              <Choice label="Je ne sais pas" active={f.vat_status === "unknown"} onClick={() => set("vat_status", "unknown")} testid="tax-liability-unknown" />
            </div>
            <Why testid="why-liability" text="Cela permet à Meelora d'appliquer automatiquement le traitement TVA approprié à vos factures." />
          </div>
        )}

        {cur === "vat_number" && (
          <div className="space-y-4" data-testid="tax-step-vatnumber">
            <div>
              <h2 className="font-display text-xl font-700 text-[#063044]">Votre numéro de TVA</h2>
              <p className="mt-1 text-sm text-slate-500">Vous le trouverez sur votre décision d'assujettissement de l'AFC. Vous pouvez aussi le renseigner plus tard.</p>
            </div>
            <Input value={f.vat_number} onChange={(e) => set("vat_number", e.target.value)} placeholder="CHE-123.456.789" data-testid="tax-vat-number" className="text-sm" />
            {uidCheck && (
              <p className={`flex items-center gap-1.5 text-xs ${uidCheck.ok ? "text-[#15803D]" : "text-[#B45309]"}`} data-testid="tax-vat-number-feedback">
                {uidCheck.ok ? <Check size={13} /> : <AlertCircle size={13} />} {uidCheck.msg}
              </p>
            )}
            <p className="text-[11px] text-slate-400">La validité du format est vérifiée localement — le statut fiscal n'est pas contrôlé officiellement.</p>
          </div>
        )}

        {cur === "method" && (
          <div className="space-y-4" data-testid="tax-step-method">
            <div>
              <h2 className="font-display text-xl font-700 text-[#063044]">Méthode de décompte</h2>
              <p className="mt-1 text-sm text-slate-500">Choisissez « Je ne sais pas » si vous n'êtes pas certain — Meelora vous le rappellera au bon moment.</p>
            </div>
            <div className="grid gap-2.5">
              <Choice label="Méthode effective" active={f.vat_method === "effective"} onClick={() => set("vat_method", "effective")} testid="tax-method-effective" />
              <Choice label="Taux de la dette fiscale nette (TDFN)" active={f.vat_method === "net_tax_rate"} onClick={() => set("vat_method", "net_tax_rate")} testid="tax-method-tdfn" />
              <Choice label="Je ne sais pas" active={f.vat_method === "unknown"} onClick={() => set("vat_method", "unknown")} testid="tax-method-unknown" />
            </div>
            <Why testid="why-method" text="Votre méthode de décompte détermine la façon dont Meelora prépare vos données TVA." />
          </div>
        )}

        {cur === "date" && (
          <div className="space-y-4" data-testid="tax-step-date">
            <div>
              <h2 className="font-display text-xl font-700 text-[#063044]">À partir de quand ?</h2>
              <p className="mt-1 text-sm text-slate-500">Date à laquelle cette configuration s'applique.</p>
            </div>
            <Input type="date" value={f.effective_from} onChange={(e) => set("effective_from", e.target.value)} data-testid="tax-effective-from" className="text-sm" />
            <Why testid="why-date" text="Elle permet d'appliquer cette configuration uniquement aux opérations concernées, sans modifier votre historique." />
          </div>
        )}

        {cur === "review" && (
          <div className="space-y-5" data-testid="tax-step-review">
            <div>
              <h2 className="font-display text-xl font-700 text-[#063044]">{rectify ? "Compléter la configuration actuelle" : "Configuration proposée"}</h2>
              <p className="mt-1 text-sm text-slate-500">Vérifiez, puis {rectify ? "confirmez" : "activez"} votre configuration.</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-[#063044]" data-testid="tax-review-summary">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-600">
                <span>Suisse</span>
                {f.canton && <><span className="text-slate-300">·</span><span>{cantonName(f.canton)}</span></>}
                <span className="text-slate-300">·</span>
                <span>{f.vat_status === "taxable" ? "Assujetti à la TVA" : f.vat_status === "not_taxable" ? "Non assujetti" : "Assujettissement à confirmer"}</span>
              </div>
              {taxable && (
                <div className="mt-2 space-y-1 text-[13px] text-slate-600">
                  {f.vat_number && <div>N° TVA : <span className="font-600 text-[#063044]">{f.vat_number}</span></div>}
                  <div>Méthode : <span className="font-600 text-[#063044]">{f.vat_method === "unknown" || !f.vat_method ? "À confirmer" : METHOD_LABEL[f.vat_method]}</span></div>
                </div>
              )}
              <div className="mt-2 text-[13px] text-slate-600">À partir du <span className="font-600 text-[#063044]">{f.effective_from}</span></div>
            </div>
            {rectify && (
              <div className="flex items-start gap-2 rounded-xl bg-[#15AF97]/8 p-3 text-xs text-slate-600" data-testid="tax-review-rectify-note">
                <Info size={14} className="mt-0.5 shrink-0 text-[#15AF97]" />
                <span>Cette information sera considérée comme applicable depuis le <span className="font-700 text-[#063044]">{f.effective_from}</span>. La version précédente restera conservée dans l'historique.</span>
              </div>
            )}
            {unresolvedPreview.length > 0 && (
              <div className="flex items-start gap-2 rounded-xl bg-[#FBBF24]/12 p-3 text-xs text-[#B45309]" data-testid="tax-review-unresolved">
                <CircleDot size={14} className="mt-0.5 shrink-0" />
                <div>
                  <p className="font-700">{unresolvedPreview.length} information{unresolvedPreview.length > 1 ? "s" : ""} à confirmer</p>
                  <ul className="mt-1 list-disc pl-4">{unresolvedPreview.map((u, i) => <li key={i}>{u}</li>)}</ul>
                  <p className="mt-1.5 font-500 text-[#92400E]">Vous pouvez {rectify ? "confirmer" : "activer"} maintenant et compléter plus tard. Meelora vous le rappellera au moment utile.</p>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Nav */}
        <div className="mt-7 flex items-center justify-between">
          <button type="button" onClick={() => (step === 0 ? onCancel() : setStep(step - 1))} data-testid="tax-wizard-back"
            className="inline-flex items-center gap-1 text-sm font-600 text-slate-500 transition-colors hover:text-[#063044]">
            <ChevronLeft size={16} /> {step === 0 ? "Annuler" : "Retour"}
          </button>
          {last ? (
            <button type="button" onClick={submit} disabled={busy} data-testid="tax-wizard-submit"
              className="inline-flex items-center gap-2 rounded-xl bg-[#15AF97] px-5 py-2.5 text-sm font-700 text-white transition-colors hover:bg-[#128a78] disabled:opacity-60">
              {busy ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} {rectify ? "Confirmer" : "Activer la configuration"}
            </button>
          ) : (
            <button type="button" onClick={() => canNext() && setStep(step + 1)} disabled={!canNext()} data-testid="tax-wizard-next"
              className="inline-flex items-center gap-1.5 rounded-xl bg-[#063044] px-5 py-2.5 text-sm font-700 text-white transition-colors hover:bg-[#0a4359] disabled:opacity-40">
              Continuer <ChevronRight size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ---- History (secondary, read-only) -----------------------------------------
const VAT_STATUS_LABEL = { taxable: "Assujetti", not_taxable: "Non assujetti", unknown: "À confirmer" };
const readable = (field, val) => {
  if (field === "vat_status") return VAT_STATUS_LABEL[val] || val || "—";
  if (field === "vat_method") return val && val !== "unknown" ? (METHOD_LABEL[val] || val) : "À confirmer";
  if (field === "canton") return val ? cantonName(val) : "—";
  return val || "—";
};
const FIELD_LABEL = { vat_status: "Assujettissement", vat_method: "Méthode", vat_number: "N° TVA", canton: "Canton", country: "Pays" };

function VersionRow({ v, prev, label, idx }) {
  const [open, setOpen] = useState(false);
  const changes = prev
    ? ["vat_status", "vat_method", "vat_number", "canton"].filter((f) => (v[f] || null) !== (prev[f] || null))
    : [];
  const muted = label === "Remplacée" || v.is_cancelled;
  return (
    <li className="py-2.5 text-sm" data-testid={`tax-history-item-${idx}`}>
      <div className="flex items-center justify-between">
        <span className={v.is_cancelled ? "text-slate-400" : "text-[#063044]"}>
          Depuis le <span className={`font-700 ${v.is_cancelled ? "line-through" : ""}`}>{v.effective_from}</span>
          <span className={`ml-2 text-xs ${muted ? "text-slate-400" : "text-[#15AF97]"}`} data-testid={`tax-history-label-${idx}`}>{label}</span>
        </span>
        <div className="flex items-center gap-3">
          {prev && (
            <button type="button" onClick={() => setOpen((o) => !o)} data-testid={`tax-history-changes-${idx}`}
              className="text-xs font-600 text-slate-400 underline decoration-dotted underline-offset-2 hover:text-[#15AF97]">Voir les changements</button>
          )}
          <span className="text-xs text-slate-400">{(v.published_at || "").slice(0, 10)}</span>
        </div>
      </div>
      {v.is_cancelled && v.cancellation_reason && (
        <p className="mt-1 text-xs text-slate-400" data-testid={`tax-history-cancel-reason-${idx}`}>Motif : {v.cancellation_reason}</p>
      )}
      {open && (
        <div className="mt-2 rounded-lg bg-slate-50 p-2.5 text-xs text-slate-600" data-testid={`tax-history-diff-${idx}`}>
          {changes.length === 0 ? "Aucun champ modifié." : changes.map((fld) => (
            <div key={fld} className="flex items-center gap-1.5">
              <span className="font-600 text-[#063044]">{FIELD_LABEL[fld]} :</span>
              <span className="text-slate-400 line-through">{readable(fld, prev[fld])}</span>
              <ArrowRight size={11} /> <span className="font-600 text-[#063044]">{readable(fld, v[fld])}</span>
            </div>
          ))}
        </div>
      )}
    </li>
  );
}

function HistorySection({ versions, activeId }) {
  const [open, setOpen] = useState(false);
  const today = new Date().toISOString().slice(0, 10);
  const published = (versions || []).filter((v) => v.status === "published"); // sorted version desc
  const byId = Object.fromEntries(published.map((v) => [v._id, v]));
  if (published.length === 0) return null;
  const labelFor = (v) => {
    if (v.is_cancelled) return v.effective_from > today ? "Planifiée — annulée" : "Annulée";
    if (v.is_superseded) return "Remplacée";
    if (v._id === activeId) return "Configuration actuelle";
    if (v.effective_from > today) return "Planifiée";
    return "Version précédente";
  };
  return (
    <div className="card p-5" data-testid="tax-history">
      <button type="button" onClick={() => setOpen((o) => !o)} data-testid="tax-history-toggle"
        className="flex w-full items-center justify-between text-left">
        <span className="flex items-center gap-2 text-sm font-700 text-[#063044]"><History size={16} className="text-slate-400" /> Historique des modifications</span>
        <ChevronRight size={16} className={`text-slate-400 transition-transform ${open ? "rotate-90" : ""}`} />
      </button>
      {open && (
        <ul className="mt-3 divide-y divide-slate-100" data-testid="tax-history-list">
          {published.map((v, i) => (
            <VersionRow key={v._id} v={v} prev={v.supersedes_version_id ? byId[v.supersedes_version_id] : null} label={labelFor(v)} idx={i} />
          ))}
        </ul>
      )}
    </div>
  );
}

// ---- Activation gate ---------------------------------------------------------
function ActivationGate({ cid, active, activation, onChange }) {
  const [busy, setBusy] = useState(false);
  const complete = active?.completeness === "complete";
  const engineOn = !!activation?.fiscal_engine_active;
  const missing = (active?.unresolved || []).length;

  const toggle = async () => {
    setBusy(true);
    try {
      await api.activateFiscalEngine(cid, !engineOn);
      toast.success(engineOn ? "Moteur TVA désactivé" : "Moteur TVA activé");
      onChange();
    } catch (e) {
      toast.error(apiError(e, "Action impossible"));
    } finally { setBusy(false); }
  };

  return (
    <div className="card p-5" data-testid="tax-activation-gate">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 text-sm font-700 text-[#063044]"><Power size={16} className="text-slate-400" /> Moteur TVA automatique</h3>
          <p className="mt-1 text-xs text-slate-500">
            {engineOn
              ? "Le traitement TVA automatique est actif pour vos nouvelles opérations."
              : "Une fois activé, Meelora appliquera automatiquement le traitement TVA à vos factures."}
          </p>
          {!complete && !engineOn && (
            <p className="mt-2 flex items-center gap-1.5 text-xs font-600 text-[#B45309]" data-testid="tax-activation-reason">
              <CircleDot size={12} /> {missing} information{missing > 1 ? "s" : ""} à confirmer avant l'activation
            </p>
          )}
        </div>
        <button type="button" onClick={toggle} disabled={busy || (!complete && !engineOn)} data-testid="tax-activation-toggle"
          className={`inline-flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-700 transition-colors ${
            engineOn ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
              : "bg-[#15AF97] text-white hover:bg-[#128a78] disabled:cursor-not-allowed disabled:opacity-40"
          }`}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Power size={15} />}
          {engineOn ? "Désactiver" : "Activer le moteur TVA"}
        </button>
      </div>
    </div>
  );
}

// ---- Cancellation dialog (mandatory reason) ---------------------------------
function CancelDialog({ open, onOpenChange, cid, version, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    if (!reason.trim()) return;
    setBusy(true);
    try {
      await api.cancelTaxVersion(cid, version._id, reason.trim());
      toast.success("Configuration annulée");
      onOpenChange(false); setReason(""); onDone();
    } catch (e) {
      toast.error(apiError(e, "Annulation impossible"));
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="tax-cancel-dialog">
        <DialogHeader>
          <DialogTitle className="text-[#063044]">Annuler cette configuration</DialogTitle>
          <DialogDescription>Indiquez le motif de l'annulation. La configuration restera conservée dans l'historique.</DialogDescription>
        </DialogHeader>
        <p className="text-sm text-slate-500">
          La configuration applicable à partir du <span className="font-700 text-[#063044]">{version?.effective_from}</span> sera rendue inactive.
          Elle restera conservée dans l'historique. Indiquez le motif.
        </p>
        <Textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Motif de l'annulation…"
          data-testid="tax-cancel-reason" className="mt-1 text-sm" rows={3} />
        <DialogFooter>
          <button type="button" onClick={() => onOpenChange(false)} data-testid="tax-cancel-abort"
            className="rounded-xl px-4 py-2 text-sm font-600 text-slate-500 hover:text-[#063044]">Retour</button>
          <button type="button" onClick={confirm} disabled={busy || !reason.trim()} data-testid="tax-cancel-confirm"
            className="inline-flex items-center gap-2 rounded-xl bg-[#DC2626] px-4 py-2 text-sm font-700 text-white transition-colors hover:bg-[#b91c1c] disabled:opacity-40">
            {busy ? <Loader2 size={15} className="animate-spin" /> : <Ban size={15} />} Confirmer l'annulation
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ---- Choice: rectify vs amend -----------------------------------------------
function ChooseMode({ activeDate, onPick, onCancel }) {
  return (
    <div className="mx-auto max-w-xl" data-testid="tax-choose-mode">
      <div className="card p-6">
        <h2 className="font-display text-xl font-700 text-[#063044]">Que souhaitez-vous faire ?</h2>
        <p className="mt-1 text-sm text-slate-500">Choisissez l'option qui décrit le mieux votre situation.</p>
        <div className="mt-5 grid gap-3">
          <button type="button" onClick={() => onPick("rectify")} data-testid="tax-choose-rectify"
            className="rounded-xl border border-slate-200 p-4 text-left transition-colors hover:border-[#15AF97] hover:bg-[#15AF97]/5">
            <div className="flex items-center gap-2 font-700 text-[#063044]"><Pencil size={15} className="text-[#15AF97]" /> Corriger la configuration actuelle</div>
            <p className="mt-1 text-xs text-slate-500">L'information corrigée était déjà valable depuis le {activeDate}.</p>
          </button>
          <button type="button" onClick={() => onPick("amend")} data-testid="tax-choose-amend"
            className="rounded-xl border border-slate-200 p-4 text-left transition-colors hover:border-[#15AF97] hover:bg-[#15AF97]/5">
            <div className="flex items-center gap-2 font-700 text-[#063044]"><CalendarClock size={15} className="text-[#15AF97]" /> Modifier à partir d'une nouvelle date</div>
            <p className="mt-1 text-xs text-slate-500">La situation de votre entreprise change à partir d'une nouvelle date.</p>
          </button>
        </div>
        <button type="button" onClick={onCancel} data-testid="tax-choose-back"
          className="mt-5 inline-flex items-center gap-1 text-sm font-600 text-slate-500 hover:text-[#063044]">
          <ChevronLeft size={16} /> Retour
        </button>
      </div>
    </div>
  );
}


// ---- Main --------------------------------------------------------------------
export default function SwissTaxProfile() {
  const { activeCompanyId } = useNav();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [wiz, setWiz] = useState(null); // null | {mode, prefill, active}
  const [choose, setChoose] = useState(false);
  const [cancelTarget, setCancelTarget] = useState(null);
  const load = () => {
    if (!activeCompanyId) { setLoading(false); return; }
    return api.getTaxProfile(activeCompanyId).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  };
  const refresh = () => { setLoading(true); load(); try { window.dispatchEvent(new Event("meelora:tax-updated")); } catch { /* noop */ } };
  useEffect(() => {
    setLoading(true);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCompanyId]);

  const active = data?.active || null;
  const status = !active ? "not_configured" : (active.completeness === "complete" ? "complete" : "needs_attention");
  const today = new Date().toISOString().slice(0, 10);
  const futureVersions = (data?.versions || [])
    .filter((v) => v.status === "published" && !v.is_superseded && !v.is_cancelled && v.effective_from > today)
    .sort((a, b) => a.effective_from.localeCompare(b.effective_from));

  // kind: "create" (first setup) | "rectify" (same period) | "amend" (new period)
  const startWizard = async (kind) => {
    setChoose(false);
    if (kind === "rectify") { setWiz({ mode: "rectify", prefill: active, active }); return; }
    if (kind === "amend") { setWiz({ mode: "amend", prefill: active, active }); return; }
    let prefill = { country: "CH" };
    try {
      const mig = await api.getTaxMigrationReport(activeCompanyId);
      const canton = (mig.deduced || []).find((d) => d.field === "canton");
      const country = (mig.confirmed || []).find((d) => d.field === "country");
      prefill = { country: country?.value || "CH", canton: canton?.value || "" };
    } catch { /* keep defaults */ }
    setWiz({ mode: "create", prefill, active: null });
  };

  if (loading) return <div className="flex items-center gap-2 p-8 text-slate-500" data-testid="tax-loading"><Loader2 className="animate-spin" size={16} /> Chargement…</div>;

  if (wiz) {
    return (
      <div data-testid="tax-hub">
        <Wizard cid={activeCompanyId} prefill={wiz.prefill} mode={wiz.mode} active={wiz.active}
          onCancel={() => setWiz(null)}
          onDone={() => { setWiz(null); refresh(); }} />
      </div>
    );
  }

  if (choose) {
    return (
      <div data-testid="tax-hub">
        <ChooseMode activeDate={active?.effective_from} onPick={startWizard} onCancel={() => setChoose(false)} />
      </div>
    );
  }

  const s = STATUS_UI[status];
  return (
    <div className="mx-auto max-w-3xl space-y-5" data-testid="tax-hub">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#063044]/6 text-[#063044]"><ShieldCheck size={20} /></span>
          <div>
            <h1 className="font-display text-2xl font-800 text-[#063044]">TVA</h1>
            <p className="text-xs text-slate-400">Configuration fiscale de votre entreprise</p>
          </div>
        </div>
        <span className={`rounded-full px-3 py-1 text-xs font-700 ${s.cls}`} data-testid="tax-status-badge">{s.label}</span>
      </div>

      {/* not_configured — simple call to action */}
      {status === "not_configured" && (
        <div className="card flex flex-col items-center gap-3 py-12 text-center" data-testid="tax-empty">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#15AF97]/10 text-[#15AF97]"><ShieldCheck size={24} /></span>
          <div>
            <p className="text-base font-700 text-[#063044]">Configurez votre TVA</p>
            <p className="mx-auto mt-1 max-w-sm text-sm text-slate-500">Quelques questions simples suffisent — Meelora s'occupe du reste en arrière-plan.</p>
          </div>
          <button type="button" onClick={() => startWizard("create")} data-testid="tax-configure-btn"
            className="mt-1 inline-flex items-center gap-2 rounded-xl bg-[#15AF97] px-5 py-2.5 text-sm font-700 text-white transition-colors hover:bg-[#128a78]">
            Configurer la TVA <ArrowRight size={16} />
          </button>
        </div>
      )}

      {/* Future scheduled configuration (real future versions, not supersessions) */}
      {futureVersions.length > 0 && (
        <div className="card flex items-center gap-3 border-l-4 border-l-[#15AF97] p-4" data-testid="tax-future-banner">
          <Info size={18} className="shrink-0 text-[#15AF97]" />
          <div className="text-sm text-[#063044]">
            <span className="font-700">Une nouvelle configuration est planifiée</span>
            <span className="ml-1 text-slate-500">· Applicable à partir du {futureVersions[0].effective_from}</span>
          </div>
          <button type="button" onClick={() => setCancelTarget(futureVersions[0])} data-testid="tax-future-cancel-btn"
            className="ml-auto inline-flex items-center gap-1 text-xs font-600 text-slate-400 transition-colors hover:text-[#DC2626]">
            <Ban size={13} /> Annuler
          </button>
        </div>
      )}

      {/* needs_attention — summary + complete action */}
      {status === "needs_attention" && (
        <div className="card p-5" data-testid="tax-needs-attention">
          <div className="flex items-start gap-3 rounded-xl bg-[#FBBF24]/10 p-3">
            <CircleDot size={16} className="mt-0.5 shrink-0 text-[#B45309]" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-700 text-[#92400E]">{(active.unresolved || []).length} information{(active.unresolved || []).length > 1 ? "s" : ""} à confirmer</p>
              <ul className="mt-1.5 space-y-1 text-xs text-[#92400E]">
                {(active.unresolved || []).map((u, i) => <li key={i} className="flex items-center gap-1.5" data-testid={`tax-unresolved-${i}`}><X size={11} /> {u.reason}</li>)}
              </ul>
            </div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-slate-600">
            <span className="font-600 text-[#063044]">Suisse{active.canton ? ` · ${cantonName(active.canton)}` : ""}</span>
            <button type="button" onClick={() => startWizard("rectify")} data-testid="tax-complete-btn"
              className="ml-auto inline-flex items-center gap-2 rounded-xl bg-[#15AF97] px-4 py-2 text-sm font-700 text-white transition-colors hover:bg-[#128a78]">
              <Pencil size={14} /> Compléter
            </button>
          </div>
        </div>
      )}

      {/* complete — compact summary */}
      {status === "complete" && (
        <div className="card p-5" data-testid="tax-complete">
          <div className="space-y-1.5 text-sm text-[#063044]">
            <div className="flex items-center gap-2 text-base font-700"><Check size={16} className="text-[#15AF97]" /> Suisse · TVA{active.canton ? ` · ${cantonName(active.canton)}` : ""}</div>
            {active.vat_number && <div className="text-slate-600" data-testid="tax-complete-number">{active.vat_number}</div>}
            {active.vat_method && <div className="text-slate-600" data-testid="tax-complete-method">{METHOD_LABEL[active.vat_method] || active.vat_method}</div>}
            <div className="text-xs text-slate-400">Configuration active depuis le {active.effective_from}</div>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-4 border-t border-slate-100 pt-3">
            <button type="button" onClick={() => setChoose(true)} data-testid="tax-edit-btn"
              className="inline-flex items-center gap-1.5 text-sm font-600 text-[#15AF97] transition-colors hover:text-[#128a78]">
              <Pencil size={14} /> Modifier la configuration
            </button>
            <button type="button" onClick={() => setCancelTarget(active)} data-testid="tax-cancel-current-btn"
              className="ml-auto inline-flex items-center gap-1.5 text-xs font-600 text-slate-400 transition-colors hover:text-[#DC2626]">
              <Ban size={13} /> Annuler cette configuration
            </button>
          </div>
        </div>
      )}

      {/* Cancellation dialog (mandatory reason) */}
      <CancelDialog open={!!cancelTarget} onOpenChange={(o) => !o && setCancelTarget(null)}
        cid={activeCompanyId} version={cancelTarget} onDone={() => { setCancelTarget(null); refresh(); }} />

      {/* Activation gate — only relevant once a profile exists */}
      {active && <ActivationGate cid={activeCompanyId} active={active} activation={data?.activation} onChange={refresh} />}

      {/* History (secondary, read-only) */}
      <HistorySection versions={data?.versions} activeId={active?._id} />
    </div>
  );
}
