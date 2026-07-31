import { useState, useEffect, useMemo, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { money } from "./comptabilite/shared";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../components/ui/alert-dialog";
import {
  Plus, Lock, Unlock, Trash2, Pencil, Send, Settings2, Download, Clock, CheckCircle2, AlertTriangle, BookOpen, Scale, FileText, X, Eye,
} from "lucide-react";

const ENTITY = "9434-3977 QC inc.";
const TODAY = new Date().toISOString().slice(0, 10);

// Onglets : Écritures + Balance de vérification (générés maintenant), autres en attente du modèle Excel.
const TABS = [
  { key: "entries", label: "Écritures", icon: BookOpen, ready: true },
  { key: "tb", label: "Balance de vérification", icon: Scale, ready: true },
  { key: "bilan", label: "Bilan", icon: FileText, ready: false },
  { key: "pnl", label: "État des résultats", icon: FileText, ready: false },
  { key: "external", label: "Envoi externe", icon: Send, ready: true },
];

function fmtSent(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString("fr-CA", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

export default function QcEntity() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canEdit = user?.role === "admin" || user?.role === "editor";
  const [tab, setTab] = useState("entries");
  const [years, setYears] = useState([]);
  const [activeYear, setActiveYear] = useState(null);
  const [yearDlg, setYearDlg] = useState(false);
  const [newYear, setNewYear] = useState("");

  const loadYears = useCallback(() => api.qcYears().then((r) => {
    setYears(r.years || []);
    setActiveYear((prev) => prev || r.active_year || (r.years?.[0]?.year ?? null));
  }).catch(() => {}), []);
  useEffect(() => { loadYears(); }, [loadYears]);

  const curYear = years.find((y) => y.year === activeYear);
  const locked = !!curYear?.locked;

  const createYear = async () => {
    try {
      const r = await api.qcCreateYear(newYear ? { year: Number(newYear) } : {});
      toast.success(`Exercice ${r.year} créé`);
      setActiveYear(r.year); setYearDlg(false); setNewYear(""); loadYears();
    } catch (e) { toast.error(e.response?.data?.detail || "Création impossible"); }
  };
  const toggleLock = async () => {
    try {
      await api.qcLockYear({ year: activeYear, locked: !locked });
      toast.success(!locked ? `Exercice ${activeYear} verrouillé` : `Exercice ${activeYear} déverrouillé`);
      loadYears();
    } catch (e) { toast.error(e.response?.data?.detail || "Action impossible"); }
  };
  const changeYear = (v) => { const n = Number(v); setActiveYear(n); api.qcSetActiveYear({ year: n }).catch(() => {}); };

  return (
    <div className="space-y-4" data-testid="qc-entity-page">
      {/* Barre exercice + verrou */}
      <div className="card p-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <label className="mb-1 block text-[11px] font-600 uppercase tracking-wider text-slate-400">Exercice</label>
            {years.length === 0
              ? <span className="text-sm text-slate-400">Aucun exercice</span>
              : <Select value={activeYear ? String(activeYear) : ""} onValueChange={changeYear}>
                  <SelectTrigger className="h-9 w-[130px]" data-testid="qc-year-select"><SelectValue /></SelectTrigger>
                  <SelectContent>{years.map((y) => <SelectItem key={y.year} value={String(y.year)}>{y.year}{y.locked ? " 🔒" : ""}</SelectItem>)}</SelectContent>
                </Select>}
          </div>
          {curYear && (locked
            ? <span data-testid="qc-lock-badge" className="inline-flex items-center gap-1.5 rounded-full bg-slate-800 px-2.5 py-1 text-xs font-600 text-white"><Lock size={12} /> Verrouillé{curYear.locked_at ? ` · ${fmtSent(curYear.locked_at)}` : ""}</span>
            : <span data-testid="qc-lock-badge" className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-600 text-amber-700"><Unlock size={12} /> Ouvert · saisie autorisée</span>)}
        </div>
        <div className="flex items-center gap-2">
          {isAdmin && curYear && (
            <Button size="sm" variant="outline" onClick={toggleLock} data-testid="qc-lock-btn" className="gap-2">
              {locked ? <><Unlock size={14} /> Déverrouiller</> : <><Lock size={14} /> Verrouiller l'exercice</>}
            </Button>
          )}
          {isAdmin && <Button size="sm" onClick={() => setYearDlg(true)} data-testid="qc-new-year-btn" className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><Plus size={14} /> Nouvel exercice</Button>}
        </div>
      </div>

      {/* Onglets (reproduisent les onglets du fichier Excel — à compléter au modèle) */}
      <div className="flex flex-wrap gap-2" data-testid="qc-tabbar">
        {TABS.map((tp) => {
          const Icon = tp.icon; const on = tab === tp.key;
          return (
            <button key={tp.key} onClick={() => setTab(tp.key)} data-testid={`qc-tab-${tp.key}`}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-600 transition-colors ${on ? "border-[#063044] bg-[#063044] text-white" : "border-slate-300 bg-white text-slate-600 hover:border-[#0E9488] hover:text-[#0E9488]"}`}>
              <Icon size={14} /> {tp.label}{!tp.ready && <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] font-700 text-amber-700">bientôt</span>}
            </button>
          );
        })}
      </div>

      {!activeYear && tab !== "external"
        ? <div className="card p-10 text-center" data-testid="qc-no-year">
            <p className="text-sm text-slate-500">Aucun exercice comptable pour {ENTITY}.</p>
            {isAdmin && <Button onClick={() => setYearDlg(true)} className="mt-3 gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><Plus size={14} /> Créer le premier exercice</Button>}
          </div>
        : tab === "entries" ? <EntriesView year={activeYear} locked={locked} canEdit={canEdit} />
        : tab === "tb" ? <TrialBalanceView year={activeYear} />
        : tab === "external" ? <QcExternalView years={years} isAdmin={isAdmin} />
        : <PlaceholderView label={TABS.find((t) => t.key === tab)?.label} />}

      {/* Dialogue nouvel exercice */}
      <Dialog open={yearDlg} onOpenChange={setYearDlg}>
        <DialogContent data-testid="qc-year-dialog" className="max-w-md">
          <DialogHeader>
            <DialogTitle>Nouvel exercice — {ENTITY}</DialogTitle>
            <DialogDescription className="text-xs">L'exercice précédent doit être verrouillé avant d'en créer un nouveau.</DialogDescription>
          </DialogHeader>
          <div>
            <label className="mb-1 block text-xs font-600 text-slate-500">Année (laisser vide = année suivante automatique)</label>
            <Input value={newYear} onChange={(e) => setNewYear(e.target.value.replace(/\D/g, ""))} placeholder="ex. 2026" data-testid="qc-year-input" className="h-9" />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setYearDlg(false)}>Annuler</Button>
            <Button onClick={createYear} data-testid="qc-year-create" className="bg-[#0E9488] hover:bg-[#0E9488]/90">Créer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function PlaceholderView({ label }) {
  return (
    <div className="card p-10 text-center" data-testid="qc-placeholder">
      <FileText size={36} className="mx-auto text-slate-300" />
      <h3 className="mt-3 font-display text-base font-700 text-[#063044]">{label}</h3>
      <p className="mt-1 text-sm text-slate-500">Cet écran sera construit à partir du <strong>modèle Excel</strong> de la structure comptable à venir.</p>
      <p className="mt-0.5 text-xs text-slate-400">Les écritures saisies alimenteront automatiquement ce rapport une fois la structure connue.</p>
    </div>
  );
}

// ===================== Écritures =====================
const emptyLine = () => ({ account: "", account_name: "", debit: "", credit: "" });

function EntriesView({ year, locked, canEdit }) {
  const [entries, setEntries] = useState([]);
  const [dlg, setDlg] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ date: TODAY, description: "", reference: "", lines: [emptyLine(), emptyLine()] });
  const [saving, setSaving] = useState(false);
  const [delTarget, setDelTarget] = useState(null);

  const load = useCallback(() => { if (year) api.qcEntries({ year }).then(setEntries).catch(() => setEntries([])); }, [year]);
  useEffect(() => { load(); }, [load]);

  // suggestions de comptes déjà utilisés
  const accountOptions = useMemo(() => {
    const m = {};
    entries.forEach((e) => (e.lines || []).forEach((l) => { if (l.account) m[l.account] = l.account_name || m[l.account] || ""; }));
    return Object.entries(m).map(([account, name]) => ({ account, name }));
  }, [entries]);

  const totalDebit = form.lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const totalCredit = form.lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
  const balanced = Math.abs(totalDebit - totalCredit) < 0.005 && totalDebit > 0;

  const openNew = () => { setEditing(null); setForm({ date: TODAY, description: "", reference: "", lines: [emptyLine(), emptyLine()] }); setDlg(true); };
  const openEdit = (e) => {
    setEditing(e);
    setForm({ date: e.date, description: e.description || "", reference: e.reference || "",
      lines: (e.lines || []).map((l) => ({ account: l.account, account_name: l.account_name || "", debit: l.debit || "", credit: l.credit || "" })) });
    setDlg(true);
  };
  const setLine = (i, k, v) => setForm((f) => ({ ...f, lines: f.lines.map((l, j) => j === i ? { ...l, [k]: v } : l) }));
  const onAccountBlur = (i) => {
    const acc = form.lines[i].account;
    const found = accountOptions.find((o) => o.account === acc);
    if (found && found.name && !form.lines[i].account_name) setLine(i, "account_name", found.name);
  };
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, emptyLine()] }));
  const removeLine = (i) => setForm((f) => ({ ...f, lines: f.lines.length > 2 ? f.lines.filter((_, j) => j !== i) : f.lines }));

  const save = async () => {
    const body = {
      date: form.date, description: form.description, reference: form.reference,
      lines: form.lines.filter((l) => l.account || l.debit || l.credit).map((l) => ({
        account: String(l.account).trim(), account_name: l.account_name || "",
        debit: Number(l.debit) || 0, credit: Number(l.credit) || 0 })),
    };
    setSaving(true);
    try {
      if (editing) { await api.qcUpdateEntry(editing.id, body); toast.success("Écriture modifiée"); }
      else { await api.qcCreateEntry(body, { year }); toast.success("Écriture enregistrée"); }
      setDlg(false); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Enregistrement impossible"); }
    finally { setSaving(false); }
  };
  const del = async () => {
    try { await api.qcDeleteEntry(delTarget.id); toast.success("Écriture supprimée"); setDelTarget(null); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Suppression impossible"); }
  };

  return (
    <div className="space-y-3" data-testid="qc-entries-view">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">{entries.length} écriture(s) · Exercice {year}</p>
        {canEdit && !locked && <Button size="sm" onClick={openNew} data-testid="qc-add-entry" className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><Plus size={14} /> Nouvelle écriture</Button>}
      </div>

      {entries.length === 0
        ? <div className="card p-10 text-center text-sm text-slate-400" data-testid="qc-entries-empty">Aucune écriture pour cet exercice.{canEdit && !locked ? " Cliquez « Nouvelle écriture » pour commencer." : ""}</div>
        : <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="qc-entries-table">
                <thead>
                  <tr className="bg-[#063044] text-left text-xs uppercase tracking-wide text-white">
                    <th className="px-3 py-2">Date</th><th className="px-3 py-2">Réf.</th><th className="px-3 py-2">Description</th>
                    <th className="px-3 py-2">Comptes</th><th className="px-3 py-2 text-right">Montant</th><th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {entries.map((e) => (
                    <tr key={e.id} className="hover:bg-slate-50" data-testid={`qc-entry-row-${e.id}`}>
                      <td className="whitespace-nowrap px-3 py-2 font-mono-data text-xs">{e.date}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{e.reference || "—"}</td>
                      <td className="px-3 py-2">{e.description || "—"}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">
                        {(e.lines || []).map((l, i) => (
                          <div key={i}>{l.account}{l.account_name ? ` · ${l.account_name}` : ""} <span className={l.debit ? "text-[#063044]" : "text-[#0E9488]"}>{l.debit ? `Dt ${money(l.debit)}` : `Ct ${money(l.credit)}`}</span></div>
                        ))}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-right font-mono-data">{money(e.total)}</td>
                      <td className="px-3 py-2">
                        {canEdit && !locked && (
                          <div className="flex justify-end gap-1">
                            <button onClick={() => openEdit(e)} data-testid={`qc-edit-${e.id}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100"><Pencil size={14} /></button>
                            <button onClick={() => setDelTarget(e)} data-testid={`qc-del-${e.id}`} className="rounded p-1.5 text-red-500 hover:bg-red-50"><Trash2 size={14} /></button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>}

      {/* Dialogue saisie */}
      <Dialog open={dlg} onOpenChange={setDlg}>
        <DialogContent data-testid="qc-entry-dialog" className="max-w-3xl">
          <DialogHeader>
            <DialogTitle>{editing ? "Modifier l'écriture" : "Nouvelle écriture"} — Exercice {year}</DialogTitle>
            <DialogDescription className="text-xs">Journal général : ajoutez les lignes de débit et de crédit. Le total des débits doit égaler le total des crédits.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Date</label><Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="qc-entry-date" className="h-9" /></div>
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Référence</label><Input value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} placeholder="ex. F-001" data-testid="qc-entry-ref" className="h-9" /></div>
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Description</label><Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Libellé de l'écriture" data-testid="qc-entry-desc" className="h-9" /></div>
            </div>

            <datalist id="qc-accounts">{accountOptions.map((o) => <option key={o.account} value={o.account}>{o.name}</option>)}</datalist>
            <div className="rounded-lg border border-slate-200">
              <table className="w-full text-sm">
                <thead><tr className="bg-slate-50 text-left text-[11px] uppercase text-slate-500">
                  <th className="px-2 py-1.5">Compte</th><th className="px-2 py-1.5">Nom du compte</th><th className="px-2 py-1.5 text-right">Débit</th><th className="px-2 py-1.5 text-right">Crédit</th><th></th>
                </tr></thead>
                <tbody>
                  {form.lines.map((l, i) => (
                    <tr key={i} data-testid={`qc-line-${i}`}>
                      <td className="px-2 py-1"><Input list="qc-accounts" value={l.account} onChange={(e) => setLine(i, "account", e.target.value)} onBlur={() => onAccountBlur(i)} placeholder="N°" data-testid={`qc-line-account-${i}`} className="h-8 w-24" /></td>
                      <td className="px-2 py-1"><Input value={l.account_name} onChange={(e) => setLine(i, "account_name", e.target.value)} placeholder="Nom" data-testid={`qc-line-name-${i}`} className="h-8" /></td>
                      <td className="px-2 py-1"><Input type="number" step="0.01" value={l.debit} onChange={(e) => setLine(i, "debit", e.target.value)} onFocus={() => l.credit && setLine(i, "credit", "")} data-testid={`qc-line-debit-${i}`} className="h-8 w-28 text-right" /></td>
                      <td className="px-2 py-1"><Input type="number" step="0.01" value={l.credit} onChange={(e) => setLine(i, "credit", e.target.value)} onFocus={() => l.debit && setLine(i, "debit", "")} data-testid={`qc-line-credit-${i}`} className="h-8 w-28 text-right" /></td>
                      <td className="px-1"><button onClick={() => removeLine(i)} disabled={form.lines.length <= 2} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500 disabled:opacity-30"><X size={14} /></button></td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-slate-200 font-600">
                    <td className="px-2 py-1.5" colSpan={2}>
                      <button onClick={addLine} data-testid="qc-add-line" className="inline-flex items-center gap-1 text-xs text-[#0E9488] hover:underline"><Plus size={13} /> Ajouter une ligne</button>
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono-data" data-testid="qc-total-debit">{money(totalDebit)}</td>
                    <td className="px-2 py-1.5 text-right font-mono-data" data-testid="qc-total-credit">{money(totalCredit)}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <div data-testid="qc-balance-indicator" className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-600 ${balanced ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
              {balanced ? <><CheckCircle2 size={15} /> Écriture équilibrée</> : <><AlertTriangle size={15} /> Déséquilibre : {money(Math.abs(totalDebit - totalCredit))} $ (débits {money(totalDebit)} vs crédits {money(totalCredit)})</>}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDlg(false)}>Annuler</Button>
            <Button onClick={save} disabled={!balanced || saving} data-testid="qc-entry-save" className="bg-[#0E9488] hover:bg-[#0E9488]/90">{saving ? "…" : "Enregistrer"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!delTarget} onOpenChange={(v) => !v && setDelTarget(null)}>
        <AlertDialogContent data-testid="qc-del-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer cette écriture ?</AlertDialogTitle>
            <AlertDialogDescription>{delTarget?.date} · {delTarget?.description} ({money(delTarget?.total)} $). Cette action est irréversible.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction onClick={del} data-testid="qc-del-confirm" className="bg-red-600 hover:bg-red-700">Supprimer</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ===================== Balance de vérification =====================
function TrialBalanceView({ year }) {
  const [tb, setTb] = useState(null);
  useEffect(() => { if (year) api.qcTrialBalance({ year }).then(setTb).catch(() => setTb(null)); }, [year]);
  const dl = async () => {
    try { const b = await api.qcTrialBalanceExcel({ year }); const url = URL.createObjectURL(b); const a = document.createElement("a"); a.href = url; a.download = `balance_verification_9434_${year}.xlsx`; a.click(); URL.revokeObjectURL(url); }
    catch { toast.error("Export impossible"); }
  };
  if (!tb) return <div className="card p-8 text-center text-sm text-slate-400">Chargement…</div>;
  return (
    <div className="space-y-3" data-testid="qc-tb-view">
      <div className="flex items-center justify-between">
        <span data-testid="qc-tb-balanced" className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-600 ${tb.balanced ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
          {tb.balanced ? <><CheckCircle2 size={13} /> Balancée</> : <><AlertTriangle size={13} /> Non balancée</>}
        </span>
        <Button size="sm" variant="outline" onClick={dl} data-testid="qc-tb-excel" className="gap-2"><Download size={14} /> Excel</Button>
      </div>
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="qc-tb-table">
            <thead><tr className="bg-[#063044] text-left text-xs uppercase tracking-wide text-white">
              <th className="px-3 py-2">Compte</th><th className="px-3 py-2">Nom du compte</th>
              <th className="px-3 py-2 text-right">Débit</th><th className="px-3 py-2 text-right">Crédit</th><th className="px-3 py-2 text-right">Solde</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {tb.rows.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-400">Aucun compte (saisissez des écritures).</td></tr>}
              {tb.rows.map((r) => (
                <tr key={r.account} className="hover:bg-slate-50">
                  <td className="px-3 py-1.5 font-mono-data text-xs">{r.account}</td>
                  <td className="px-3 py-1.5">{r.account_name || "—"}</td>
                  <td className="px-3 py-1.5 text-right font-mono-data">{r.debit ? money(r.debit) : "—"}</td>
                  <td className="px-3 py-1.5 text-right font-mono-data">{r.credit ? money(r.credit) : "—"}</td>
                  <td className={`px-3 py-1.5 text-right font-mono-data ${r.balance < 0 ? "text-red-600" : ""}`}>{money(r.balance)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr className="border-t-2 border-[#063044] bg-slate-50 font-700">
              <td className="px-3 py-2" colSpan={2}>TOTAL</td>
              <td className="px-3 py-2 text-right font-mono-data">{money(tb.total_debit)}</td>
              <td className="px-3 py-2 text-right font-mono-data">{money(tb.total_credit)}</td>
              <td className="px-3 py-2 text-right font-mono-data">{money(tb.total_debit - tb.total_credit)}</td>
            </tr></tfoot>
          </table>
        </div>
      </div>
    </div>
  );
}

// ===================== Envoi externe (contacts propres) =====================
function QcExternalView({ years, isAdmin }) {
  const [contacts, setContacts] = useState([]);
  const [catalog, setCatalog] = useState([]);
  const [cid, setCid] = useState("");
  const [year, setYear] = useState(years[0]?.year || null);
  const [emailCfg, setEmailCfg] = useState({ configured: false });
  const [busy, setBusy] = useState(false);
  const [manageOpen, setManageOpen] = useState(false);
  const [history, setHistory] = useState([]);
  const [histOpen, setHistOpen] = useState(false);

  const load = useCallback(() => api.qcExternalContacts().then((r) => setContacts(r || [])), []);
  const loadHistory = useCallback(() => { if (cid) api.qcExternalEmailLog({ contact_id: cid }).then((r) => setHistory(r || [])).catch(() => setHistory([])); else setHistory([]); }, [cid]);
  useEffect(() => { load(); api.qcExternalCatalog().then(setCatalog).catch(() => {}); api.acctEmailStatus().then(setEmailCfg).catch(() => {}); }, [load]);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  useEffect(() => { if (!year && years.length) setYear(years[0].year); }, [years, year]);

  const contact = contacts.find((c) => c.id === cid);
  const labelOf = (k) => (catalog.find((c) => c.key === k) || {}).label || k;
  const ls = contact?.last_sent;
  const fmt = (iso) => fmtSent(iso);

  const download = async (key) => {
    try { const b = await api.qcExternalReport({ key, year }); const url = URL.createObjectURL(b); const a = document.createElement("a"); a.href = url; a.download = `${key}_9434_${year}.xlsx`; a.click(); URL.revokeObjectURL(url); toast.success("Téléchargé"); }
    catch (e) { toast.error(e.response?.data?.detail || "Indisponible"); }
  };
  const sendAll = async () => {
    setBusy(true);
    try { const r = await api.qcExternalEmail({ contact_id: cid, year }); toast.success(r.message || "Envoyé"); load(); loadHistory(); }
    catch (e) { toast.error(e.response?.data?.detail || "Envoi impossible"); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-4" data-testid="qc-external-view">
      <div className="card p-3 flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-[11px] font-600 uppercase tracking-wider text-slate-400">Contact externe</label>
            <select value={cid} onChange={(e) => setCid(e.target.value)} data-testid="qc-external-select"
              className="h-9 min-w-[220px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 focus:border-[#0E9488] focus:outline-none">
              <option value="">— Choisir —</option>
              {contacts.map((c) => <option key={c.id} value={c.id}>{c.name}{c.report_types?.length ? ` (${c.report_types.length})` : ""}</option>)}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-[11px] font-600 uppercase tracking-wider text-slate-400">Exercice</label>
            <Select value={year ? String(year) : ""} onValueChange={(v) => setYear(Number(v))}>
              <SelectTrigger className="h-9 w-[120px]" data-testid="qc-external-year"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{years.map((y) => <SelectItem key={y.year} value={String(y.year)}>{y.year}</SelectItem>)}</SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {cid && contact && <Button size="sm" onClick={sendAll} disabled={busy || !emailCfg.configured} title={emailCfg.configured ? `Envoyer à ${contact.email || "(aucun courriel)"}` : "Service d'email non configuré"} data-testid="qc-external-email" className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><Send size={15} /> {busy ? "…" : "Envoyer le package"}</Button>}
          {cid && <Button size="sm" variant="outline" onClick={() => setHistOpen(true)} data-testid="qc-external-history-btn" className="gap-2"><Clock size={15} /> Historique{history.length ? ` (${history.length})` : ""}</Button>}
          {isAdmin && <Button size="sm" variant="outline" onClick={() => setManageOpen(true)} data-testid="qc-external-manage" className="gap-2"><Settings2 size={15} /> Gérer les contacts</Button>}
        </div>
      </div>

      <p className="text-xs text-slate-400">Note : seule la <strong>Balance de vérification</strong> est disponible pour l'instant. Le Bilan et l'État des résultats seront ajoutés une fois le modèle Excel reçu.</p>

      {!cid ? <p className="p-6 text-center text-sm text-slate-400">Sélectionnez un contact externe pour préparer son package.</p>
        : (
          <div className="card overflow-hidden" data-testid="qc-external-package">
            <div className="border-b border-slate-100 px-5 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-display text-base font-700 text-[#063044]">Package — {contact.name}</h3>
                {ls
                  ? <span data-testid="qc-external-last-sent" className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-600 text-emerald-700"><CheckCircle2 size={13} /> Dernier envoi : {fmt(ls.sent_at)} · {ls.year} · {ls.doc_count || 0} doc(s)</span>
                  : <span data-testid="qc-external-last-sent" className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-600 text-slate-500"><Clock size={13} /> Aucun envoi enregistré</span>}
              </div>
              <p className="mt-0.5 text-xs text-slate-400">Exercice {year || "—"} · {contact.email || "aucun courriel"} · {contact.report_types?.length || 0} document(s)</p>
            </div>
            <div className="divide-y divide-slate-50">
              {(contact.report_types || []).map((key) => (
                <div key={key} className="flex items-center justify-between gap-3 px-5 py-3" data-testid={`qc-external-report-${key}`}>
                  <p className="text-sm font-600 text-slate-700">{labelOf(key)}</p>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" onClick={() => download(key)} data-testid={`qc-external-download-${key}`} className="gap-1.5"><Download size={14} /> Excel</Button>
                    <span className="text-xs font-600 text-emerald-600">Prêt</span>
                  </div>
                </div>
              ))}
              {(contact.report_types || []).length === 0 && <p className="p-6 text-center text-sm text-slate-400">Aucun document sélectionné pour ce contact (voir « Gérer les contacts »).</p>}
            </div>
          </div>
        )}

      {isAdmin && <QcContactsDialog open={manageOpen} onOpenChange={setManageOpen} contacts={contacts} catalog={catalog} onChanged={load} />}

      <Dialog open={histOpen} onOpenChange={setHistOpen}>
        <DialogContent data-testid="qc-external-history-dialog" className="max-h-[85vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Clock size={16} className="text-[#0E9488]" /> Historique des envois — {contact?.name || ""}</DialogTitle>
            <DialogDescription className="text-xs">Journal des documents financiers transmis à ce contact.</DialogDescription>
          </DialogHeader>
          {history.length === 0
            ? <p className="py-8 text-center text-sm text-slate-400">Aucun envoi enregistré pour ce contact.</p>
            : <div className="space-y-2">
                {history.map((h, i) => (
                  <div key={i} className="rounded-lg border border-slate-200 px-3 py-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-600 text-[#063044]">Exercice {h.year}</span>
                      <span className="text-xs text-slate-500">{fmt(h.sent_at)}</span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500">Vers {h.email} · par {h.sent_by} · {h.doc_count || 0} document(s)</p>
                    {(h.documents || []).length > 0 && <div className="mt-1.5 flex flex-wrap gap-1">{h.documents.map((d, j) => <span key={j} className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-600 text-emerald-700">{d}</span>)}</div>}
                  </div>
                ))}
              </div>}
          <DialogFooter><Button variant="outline" onClick={() => setHistOpen(false)}>Fermer</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function QcContactsDialog({ open, onOpenChange, contacts, catalog, onChanged }) {
  const [form, setForm] = useState({ name: "", email: "", report_types: [], active: true });
  const [editId, setEditId] = useState(null);
  const reset = () => { setForm({ name: "", email: "", report_types: [], active: true }); setEditId(null); };
  const startEdit = (c) => { setEditId(c.id); setForm({ name: c.name, email: c.email || "", report_types: c.report_types || [], active: c.active !== false }); };
  const toggleType = (k) => setForm((f) => ({ ...f, report_types: f.report_types.includes(k) ? f.report_types.filter((x) => x !== k) : [...f.report_types, k] }));
  const save = async () => {
    if (!form.name.trim()) { toast.error("Nom requis"); return; }
    try {
      if (editId) await api.qcUpdateExternalContact(editId, form);
      else await api.qcCreateExternalContact(form);
      toast.success("Enregistré"); reset(); onChanged();
    } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); }
  };
  const del = async (c) => { try { await api.qcDeleteExternalContact(c.id); toast.success("Supprimé"); onChanged(); } catch { toast.error("Impossible"); } };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) reset(); onOpenChange(v); }}>
      <DialogContent data-testid="qc-contacts-dialog" className="max-h-[85vh] max-w-2xl overflow-y-auto">
        <DialogHeader><DialogTitle>Contacts externes — 9434-3977 QC inc.</DialogTitle>
          <DialogDescription className="text-xs">Liste propre à cette entité, indépendante des contacts de l'entité principale.</DialogDescription></DialogHeader>
        <div className="space-y-2">
          {contacts.map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2" data-testid={`qc-contact-row-${c.id}`}>
              <div><p className="text-sm font-600 text-slate-700">{c.name}</p><p className="text-xs text-slate-400">{c.email || "aucun courriel"} · {c.report_types?.length || 0} doc(s)</p></div>
              <div className="flex gap-1">
                <button onClick={() => startEdit(c)} data-testid={`qc-contact-edit-${c.id}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100"><Pencil size={15} /></button>
                <button onClick={() => del(c)} data-testid={`qc-contact-del-${c.id}`} className="rounded p-1.5 text-red-500 hover:bg-red-50"><Trash2 size={15} /></button>
              </div>
            </div>
          ))}
        </div>
        <div className="space-y-3 rounded-lg border border-[#0E9488]/30 bg-[#0E9488]/5 p-3" data-testid="qc-contact-form">
          <p className="text-xs font-700 text-[#063044]">{editId ? "Modifier le contact" : "Nouveau contact"}</p>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Nom du contact" data-testid="qc-contact-name" className="h-9" />
          <Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Courriel" data-testid="qc-contact-email" className="h-9" />
          <div>
            <p className="mb-1 text-xs font-600 text-slate-500">Documents à envoyer</p>
            <div className="flex flex-wrap gap-2">
              {catalog.map((c) => (
                <label key={c.key} className="flex cursor-pointer items-center gap-2 rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 hover:border-[#0E9488]" data-testid={`qc-contact-type-${c.key}`}>
                  <input type="checkbox" checked={form.report_types.includes(c.key)} onChange={() => toggleType(c.key)} /> {c.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={save} data-testid="qc-contact-save" className="bg-[#0E9488] hover:bg-[#0E9488]/90">Enregistrer</Button>
            {editId && <Button size="sm" variant="outline" onClick={reset}>Annuler</Button>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
