import { useState, useEffect, useCallback } from "react";
import { useNav } from "../context/NavContext";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Construction, BookOpen, Loader2, Plus, Lock, Unlock, CheckCircle2, Ban, Send,
  Stamp, RotateCcw, ThumbsUp, ChevronLeft,
} from "lucide-react";

const STATUS_META = {
  draft: { label: "Brouillon", cls: "bg-slate-100 text-slate-600" },
  submitted: { label: "Soumise", cls: "bg-blue-100 text-blue-700" },
  approved: { label: "Approuvée", cls: "bg-amber-100 text-amber-700" },
  posted: { label: "Comptabilisée", cls: "bg-emerald-100 text-emerald-700" },
  reversed: { label: "Extournée", cls: "bg-rose-100 text-rose-700" },
};
const PERIOD_META = {
  open: { label: "Ouverte", cls: "text-emerald-600", icon: Unlock },
  locked: { label: "Verrouillée", cls: "text-amber-600", icon: Lock },
  closed: { label: "Clôturée", cls: "text-slate-500", icon: Ban },
};

// Generic clean placeholder for screens not yet developed in this slice.
export function AcctPlaceholder({ title, note }) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center" data-testid="acct-placeholder">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-[#063044]/8 text-[#063044]">
        <Construction size={28} />
      </div>
      <h2 className="text-lg font-semibold text-[#063044]" data-testid="acct-placeholder-title">{title}</h2>
      <p className="mt-2 max-w-md text-sm text-slate-500">{note || "Cet écran sera développé dans une tranche ultérieure. La navigation et le gating par module sont déjà en place."}</p>
    </div>
  );
}
export const makePlaceholder = (title, note) => () => <AcctPlaceholder title={title} note={note} />;

function useCid() {
  const { activeCompanyId } = useNav();
  return activeCompanyId;
}

// ------------------------------------------------------------------ Clôture & Réconciliation (périodes)
export function AcctPeriods() {
  const cid = useCid();
  const [periods, setPeriods] = useState(null);
  const [code, setCode] = useState("");
  const reload = useCallback(() => {
    if (!cid) return;
    api.glPeriods(cid).then((d) => setPeriods(d.periods || [])).catch((e) => { setPeriods([]); });
  }, [cid]);
  useEffect(() => { reload(); }, [reload]);
  const create = async () => {
    try { await api.glCreatePeriod(cid, { code }); toast.success("Période créée"); setCode(""); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || "Création impossible"); }
  };
  const transition = async (pid, status) => {
    try { await api.glTransitionPeriod(cid, pid, status); toast.success(`Période → ${PERIOD_META[status].label}`); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || "Transition refusée"); }
  };
  if (!cid) return <AcctPlaceholder title="Clôture & Réconciliation" note="Sélectionnez un mandat." />;
  if (periods === null) return <div className="flex items-center gap-2 text-slate-500"><Loader2 className="animate-spin" size={16}/> Chargement…</div>;
  return (
    <div className="space-y-5" data-testid="acct-periods-page">
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label className="text-[11px] uppercase text-slate-500">Nouvelle période (code)</label>
          <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="2026-01" className="mt-1 h-10 w-40 font-mono-data" data-testid="period-code-input" />
        </div>
        <Button onClick={create} disabled={!code.trim()} className="h-10 gap-1.5 bg-[#063044] text-white" data-testid="period-create-btn"><Plus size={15}/> Créer</Button>
      </div>
      <p className="text-xs text-slate-400">Transitions permises : ouverte → verrouillée → clôturée (déverrouillage possible tant que non clôturée). La réouverture d'une période clôturée est définitivement interdite.</p>
      <div className="space-y-2">
        {periods.length === 0 && <p className="text-sm text-slate-400" data-testid="periods-empty">Aucune période. Créez la première.</p>}
        {periods.map((p) => {
          const M = PERIOD_META[p.status]; const Icon = M.icon;
          return (
            <div key={p.id} data-testid={`period-row-${p.code}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-center gap-3">
                <span className="font-mono-data text-sm font-600 text-[#0F172A]">{p.code}</span>
                <span className={`inline-flex items-center gap-1 text-xs font-600 ${M.cls}`} data-testid={`period-status-${p.code}`}><Icon size={13}/>{M.label}</span>
              </div>
              <div className="flex gap-1.5">
                {p.status === "open" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`period-lock-${p.code}`} onClick={() => transition(p.id, "locked")}><Lock size={13}/>Verrouiller</Button>}
                {p.status === "locked" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`period-unlock-${p.code}`} onClick={() => transition(p.id, "open")}><Unlock size={13}/>Déverrouiller</Button>}
                {p.status !== "closed" && <Button size="sm" variant="outline" className="h-8 gap-1 text-slate-700" data-testid={`period-close-${p.code}`} onClick={() => transition(p.id, "closed")}><Ban size={13}/>Clôturer</Button>}
                {p.status === "closed" && <span className="text-[11px] text-slate-400">Terminale — correction via période ultérieure</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Écritures comptables (GL)
export function AcctEntries() {
  const cid = useCid();
  const [entries, setEntries] = useState(null);
  const [periods, setPeriods] = useState([]);
  const [form, setForm] = useState(null);
  const reload = useCallback(() => {
    if (!cid) return;
    api.glEntries(cid).then((d) => setEntries(d.entries || [])).catch(() => setEntries([]));
    api.glPeriods(cid).then((d) => setPeriods(d.periods || [])).catch(() => {});
  }, [cid]);
  useEffect(() => { reload(); }, [reload]);
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); reload(); } catch (e) { toast.error(e.response?.data?.detail || "Action refusée"); } };
  if (!cid) return <AcctPlaceholder title="Écritures comptables" note="Sélectionnez un mandat." />;
  if (entries === null) return <div className="flex items-center gap-2 text-slate-500"><Loader2 className="animate-spin" size={16}/> Chargement…</div>;
  if (form) return <EntryForm cid={cid} periods={periods} onDone={() => { setForm(null); reload(); }} onCancel={() => setForm(null)} />;
  return (
    <div className="space-y-4" data-testid="acct-entries-page">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">Écritures du grand livre — cycle brouillon → soumise → approuvée → comptabilisée → extournée.</p>
        <Button className="gap-1.5 bg-[#063044] text-white" data-testid="entry-new-btn" onClick={() => setForm({})}><Plus size={15}/> Nouvelle écriture</Button>
      </div>
      <div className="space-y-2">
        {entries.length === 0 && <p className="text-sm text-slate-400" data-testid="entries-empty">Aucune écriture.</p>}
        {entries.map((e) => {
          const M = STATUS_META[e.status];
          return (
            <div key={e.id} data-testid={`entry-row-${e.id}`} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-white p-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-600 text-[#0F172A]">{e.reference || e.id.slice(0, 10)}</span>
                  <span className={`rounded px-1.5 py-0.5 text-[11px] font-600 ${M.cls}`} data-testid={`entry-status-${e.id}`}>{M.label}</span>
                  {e.source === "reversal" && <span className="rounded bg-rose-50 px-1.5 py-0.5 text-[10px] text-rose-600">extourne</span>}
                </div>
                <div className="text-xs text-slate-400">{e.memo} · {e.date} · {e.total_debit?.toFixed(2)} DR / {e.total_credit?.toFixed(2)} CR</div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {e.status === "draft" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`entry-submit-${e.id}`} onClick={() => act(() => api.glSubmitEntry(cid, e.id), "Soumise")}><Send size={13}/>Soumettre</Button>}
                {e.status === "submitted" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`entry-approve-${e.id}`} onClick={() => act(() => api.glApproveEntry(cid, e.id), "Approuvée")}><ThumbsUp size={13}/>Approuver</Button>}
                {e.status === "approved" && <Button size="sm" variant="outline" className="h-8 gap-1 text-emerald-700" data-testid={`entry-post-${e.id}`} onClick={() => act(() => api.glPostEntry(cid, e.id), "Comptabilisée")}><Stamp size={13}/>Comptabiliser</Button>}
                {e.status === "posted" && <Button size="sm" variant="outline" className="h-8 gap-1 text-rose-600" data-testid={`entry-reverse-${e.id}`} onClick={() => act(() => api.glReverseEntry(cid, e.id, {}), "Extournée")}><RotateCcw size={13}/>Extourner</Button>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function EntryForm({ cid, periods, onDone, onCancel }) {
  const openPeriods = periods.filter((p) => p.status !== "closed");
  const [pid, setPid] = useState(openPeriods[0]?.id || "");
  const [memo, setMemo] = useState("");
  const [ref, setRef] = useState("");
  const [lines, setLines] = useState([{ account: "", debit: "", credit: "" }, { account: "", debit: "", credit: "" }]);
  const td = lines.reduce((s, l) => s + (parseFloat(l.debit) || 0), 0);
  const tc = lines.reduce((s, l) => s + (parseFloat(l.credit) || 0), 0);
  const balanced = td > 0 && Math.round(td * 100) === Math.round(tc * 100);
  const setLine = (i, k, v) => setLines((ls) => ls.map((l, j) => j === i ? { ...l, [k]: v } : l));
  const save = async () => {
    try {
      await api.glCreateEntry(cid, { period_id: pid, memo, reference: ref,
        lines: lines.filter((l) => l.account).map((l) => ({ account: l.account, debit: parseFloat(l.debit) || 0, credit: parseFloat(l.credit) || 0 })) });
      toast.success("Écriture créée (brouillon)"); onDone();
    } catch (e) { toast.error(e.response?.data?.detail || "Création impossible"); }
  };
  return (
    <div className="space-y-4" data-testid="entry-form">
      <button onClick={onCancel} className="flex items-center gap-1 text-sm text-slate-500" data-testid="entry-form-back"><ChevronLeft size={16}/> Écritures</button>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div><label className="text-[11px] uppercase text-slate-500">Période</label>
          <select value={pid} onChange={(e) => setPid(e.target.value)} className="mt-1 h-10 w-full rounded-lg border border-slate-200 px-2 text-sm" data-testid="entry-period-select">
            {openPeriods.length === 0 && <option value="">Aucune période ouverte</option>}
            {openPeriods.map((p) => <option key={p.id} value={p.id}>{p.code} ({p.status})</option>)}
          </select></div>
        <div><label className="text-[11px] uppercase text-slate-500">Référence</label><Input value={ref} onChange={(e) => setRef(e.target.value)} className="mt-1 h-10" data-testid="entry-ref-input" /></div>
        <div><label className="text-[11px] uppercase text-slate-500">Libellé</label><Input value={memo} onChange={(e) => setMemo(e.target.value)} className="mt-1 h-10" data-testid="entry-memo-input" /></div>
      </div>
      <div className="space-y-2">
        {lines.map((l, i) => (
          <div key={i} className="grid grid-cols-12 gap-2" data-testid={`entry-line-${i}`}>
            <Input placeholder="Compte" value={l.account} onChange={(e) => setLine(i, "account", e.target.value)} className="col-span-6 h-10 font-mono-data" data-testid={`line-account-${i}`} />
            <Input placeholder="Débit" type="number" value={l.debit} onChange={(e) => setLine(i, "debit", e.target.value)} className="col-span-3 h-10 font-mono-data" data-testid={`line-debit-${i}`} />
            <Input placeholder="Crédit" type="number" value={l.credit} onChange={(e) => setLine(i, "credit", e.target.value)} className="col-span-3 h-10 font-mono-data" data-testid={`line-credit-${i}`} />
          </div>
        ))}
        <Button size="sm" variant="outline" onClick={() => setLines((ls) => [...ls, { account: "", debit: "", credit: "" }])} data-testid="entry-add-line"><Plus size={13}/> Ligne</Button>
      </div>
      <div className={`text-sm font-600 ${balanced ? "text-emerald-600" : "text-rose-600"}`} data-testid="entry-balance">
        Débits {td.toFixed(2)} / Crédits {tc.toFixed(2)} — {balanced ? "équilibrée ✓" : "déséquilibrée"}
      </div>
      <div className="flex gap-2">
        <Button variant="outline" onClick={onCancel}>Annuler</Button>
        <Button className="bg-[#063044] text-white" disabled={!balanced || !pid} onClick={save} data-testid="entry-save-btn"><BookOpen size={15} className="mr-1.5"/> Enregistrer le brouillon</Button>
      </div>
    </div>
  );
}
