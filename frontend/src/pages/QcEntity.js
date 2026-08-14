import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import { money } from "./comptabilite/shared";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../components/ui/alert-dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "../components/ui/dropdown-menu";
import {
  Plus, Lock, Unlock, Trash2, Pencil, Send, Settings2, Download, Clock, CheckCircle2, AlertTriangle, BookOpen, Scale, FileText, X, Eye, FileDown, Save, Copy, Upload, Wallet, ChevronDown, LayoutList, Mail, Users, RotateCcw, FileMinus,
} from "lucide-react";

const ENTITY = "9434-3977 QC inc.";
const TODAY = new Date().toISOString().slice(0, 10);

// Onglets reproduisant le modèle Excel.
const MAIN_TABS = [
  { key: "entries", label: "Écritures", icon: BookOpen },
  { key: "ar", label: "Factures clients", icon: FileText },
  { key: "ap", label: "Factures fournisseurs", icon: FileText },
  { key: "clients", label: "Clients", icon: Users },
];
const REPORT_TABS = [
  { key: "tb", label: "Balance de vérification", icon: Scale },
  { key: "bilan", label: "Bilan détaillé", icon: FileText },
  { key: "pnl", label: "États des résultats", icon: Scale },
  { key: "ef", label: "États Financiers", icon: FileText },
  { key: "accounts", label: "Plan comptable", icon: BookOpen },
  { key: "external", label: "Envoi externe", icon: Send },
];
const ALL_TABS = [...MAIN_TABS, ...REPORT_TABS];

function fmtSent(iso) {
  if (!iso) return "";
  try { return new Date(iso).toLocaleString("fr-CA", { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return iso; }
}

function OpeningBalancesDialog({ open, onOpenChange, year, locked, canEdit }) {
  const [rows, setRows] = useState([]);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!open || !year) return;
    setLoading(true);
    api.qcGetOpening(year).then((d) => setRows(d.rows || [])).catch(() => setRows([])).finally(() => setLoading(false));
  }, [open, year]);
  const setVal = (gl, field, v) => setRows((rs) => rs.map((r) => r.gl === gl ? { ...r, [field]: v, [field === "debit" ? "credit" : "debit"]: v ? 0 : r[field === "debit" ? "credit" : "debit"] } : r));
  const num = (v) => { const n = Number(v); return isNaN(n) ? 0 : n; };
  const totalD = rows.reduce((s, r) => s + num(r.debit), 0);
  const totalC = rows.reduce((s, r) => s + num(r.credit), 0);
  const balanced = Math.abs(totalD - totalC) < 0.01;
  const SECTIONS = { actif_court: "Actif à court terme", actif_placement: "Placement et immobilisations", passif_court: "Passif à court terme", passif_long: "Passif à long terme", capitaux: "Capitaux propres" };
  const grouped = Object.keys(SECTIONS).map((sec) => ({ sec, label: SECTIONS[sec], items: rows.filter((r) => r.section === sec) })).filter((g) => g.items.length);
  const other = rows.filter((r) => !Object.keys(SECTIONS).includes(r.section));
  if (other.length) grouped.push({ sec: "autre", label: "Autres comptes", items: other });
  const save = async () => {
    if (!balanced) { toast.error("Les débits et crédits doivent être égaux."); return; }
    setSaving(true);
    try {
      await api.qcPutOpening(year, { rows: rows.map((r) => ({ gl: r.gl, debit: num(r.debit), credit: num(r.credit) })) });
      toast.success(`Soldes d'ouverture ${year} enregistrés`);
      onOpenChange(false);
    } catch (e) { toast.error(e.response?.data?.detail || "Enregistrement impossible"); } finally { setSaving(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="qc-opening-dialog" className="max-h-[88vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Scale size={16} className="text-[#22C55E]" /> Soldes d'ouverture — exercice {year}</DialogTitle>
          <DialogDescription className="text-xs">Saisissez le bilan de clôture de l'exercice précédent (report « à-nouveaux »). Les débits doivent égaler les crédits.</DialogDescription>
        </DialogHeader>
        {loading ? <p className="py-6 text-center text-sm text-slate-400">Chargement…</p>
          : <div className="space-y-4">
              {grouped.map((g) => (
                <div key={g.sec}>
                  <p className="mb-1 text-xs font-700 uppercase tracking-wide text-[#22C55E]">{g.label}</p>
                  <table className="w-full text-sm">
                    <thead><tr className="text-left text-[11px] uppercase text-slate-400"><th className="py-1">Compte</th><th className="py-1 text-right w-32">Débit</th><th className="py-1 text-right w-32">Crédit</th></tr></thead>
                    <tbody>
                      {g.items.map((r) => (
                        <tr key={r.gl} data-testid={`qc-opening-row-${r.gl}`}>
                          <td className="py-0.5"><span className="font-mono-data text-xs text-slate-400">{r.gl}</span> {r.description}</td>
                          <td className="py-0.5"><Input type="number" step="0.01" value={r.debit || ""} disabled={!canEdit} onChange={(e) => setVal(r.gl, "debit", e.target.value)} data-testid={`qc-opening-debit-${r.gl}`} className="h-8 text-right font-mono-data" /></td>
                          <td className="py-0.5"><Input type="number" step="0.01" value={r.credit || ""} disabled={!canEdit} onChange={(e) => setVal(r.gl, "credit", e.target.value)} data-testid={`qc-opening-credit-${r.gl}`} className="h-8 text-right font-mono-data" /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
              <div className={`flex items-center justify-between rounded-lg px-3 py-2 text-sm font-700 ${balanced ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`} data-testid="qc-opening-totals">
                <span className="flex items-center gap-1.5">{balanced ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />} {balanced ? "Équilibré" : `Écart : ${money(totalD - totalC)} $`}</span>
                <span className="font-mono-data">Débit {money(totalD)} · Crédit {money(totalC)}</span>
              </div>
            </div>}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Fermer</Button>
          {canEdit && <Button onClick={save} disabled={saving || !balanced} data-testid="qc-opening-save" className="bg-[#22C55E] hover:bg-[#22C55E]/90">{saving ? "…" : "Enregistrer les à-nouveaux"}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function QcEntity() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const canEdit = user?.role === "admin" || user?.role === "editor";
  const [tab, setTab] = useState("entries");
  const [years, setYears] = useState([]);
  const [activeYear, setActiveYear] = useState(null);
  const [yearDlg, setYearDlg] = useState(false);
  const [openingDlg, setOpeningDlg] = useState(false);
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
  const importModel = async () => {
    try { const r = await api.qcImportModel(); toast.success(r.message || "Modèle importé"); setActiveYear(2026); loadYears(); }
    catch (e) { toast.error(e.response?.data?.detail || "Import impossible"); }
  };

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
          {isAdmin && curYear && (
            <Button size="sm" variant="outline" onClick={() => setOpeningDlg(true)} data-testid="qc-opening-btn" className="gap-2">
              <Scale size={14} /> Soldes d'ouverture
            </Button>
          )}
          {isAdmin && <Button size="sm" onClick={() => setYearDlg(true)} data-testid="qc-new-year-btn" className="gap-2 bg-[#22C55E] hover:bg-[#22C55E]/90"><Plus size={14} /> Nouvel exercice</Button>}
        </div>
      </div>

      {curYear && <OpeningBalancesDialog open={openingDlg} onOpenChange={setOpeningDlg} year={activeYear} locked={locked} canEdit={isAdmin} />}

      {/* Onglets : principaux + menu déroulant Rapports */}
      <div className="flex flex-wrap items-center gap-2" data-testid="qc-tabbar">
        {MAIN_TABS.map((tp) => {
          const Icon = tp.icon; const on = tab === tp.key;
          return (
            <button key={tp.key} onClick={() => setTab(tp.key)} data-testid={`qc-tab-${tp.key}`}
              className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-600 transition-colors ${on ? "border-[#0F172A] bg-[#0F172A] text-white" : "border-slate-300 bg-white text-slate-600 hover:border-[#22C55E] hover:text-[#22C55E]"}`}>
              <Icon size={14} /> {tp.label}
            </button>
          );
        })}
        {(() => {
          const reportOn = REPORT_TABS.some((t) => t.key === tab);
          const active = REPORT_TABS.find((t) => t.key === tab);
          return (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button data-testid="qc-tab-rapports"
                  className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-600 transition-colors ${reportOn ? "border-[#0F172A] bg-[#0F172A] text-white" : "border-slate-300 bg-white text-slate-600 hover:border-[#22C55E] hover:text-[#22C55E]"}`}>
                  <LayoutList size={14} /> Rapports{active ? ` · ${active.label}` : ""} <ChevronDown size={14} />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-56" data-testid="qc-rapports-menu">
                {REPORT_TABS.map((tp) => {
                  const Icon = tp.icon;
                  return (
                    <DropdownMenuItem key={tp.key} onClick={() => setTab(tp.key)} data-testid={`qc-tab-${tp.key}`}
                      className={`gap-2 ${tab === tp.key ? "bg-[#22C55E]/10 font-600 text-[#22C55E]" : ""}`}>
                      <Icon size={14} /> {tp.label}
                    </DropdownMenuItem>
                  );
                })}
              </DropdownMenuContent>
            </DropdownMenu>
          );
        })()}
      </div>

      {!activeYear && tab !== "external"
        ? <div className="card p-10 text-center" data-testid="qc-no-year">
            <p className="text-sm text-slate-500">Aucun exercice comptable pour {ENTITY}.</p>
            {isAdmin && <div className="mt-3 flex flex-wrap justify-center gap-2">
              <Button onClick={() => setYearDlg(true)} className="gap-2 bg-[#22C55E] hover:bg-[#22C55E]/90"><Plus size={14} /> Créer le premier exercice</Button>
              <Button variant="outline" onClick={importModel} data-testid="qc-import-model" className="gap-2"><Download size={14} /> Importer le modèle Excel (2025-2026)</Button>
            </div>}
          </div>
        : tab === "entries" ? <EntriesView year={activeYear} locked={locked} canEdit={canEdit} />
        : tab === "ar" ? <InvoicesView year={activeYear} locked={locked} canEdit={canEdit} accounts={[]} />
        : tab === "ap" ? <BillsView year={activeYear} locked={locked} canEdit={canEdit} />
        : tab === "clients" ? <ClientsView isAdmin={isAdmin} year={activeYear} />
        : tab === "tb" ? <TrialBalanceView year={activeYear} />
        : tab === "bilan" ? <StatementView year={activeYear} kind="bilan" />
        : tab === "pnl" ? <StatementView year={activeYear} kind="pnl" />
        : tab === "ef" ? <EtatsFinanciersView year={activeYear} />
        : tab === "accounts" ? <PlanComptableView canEdit={canEdit} />
        : tab === "external" ? <QcExternalView years={years} isAdmin={isAdmin} />
        : <PlaceholderView label={ALL_TABS.find((t) => t.key === tab)?.label} />}

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
            <Button onClick={createYear} data-testid="qc-year-create" className="bg-[#22C55E] hover:bg-[#22C55E]/90">Créer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AccountDetailModal({ year, account, scope, onClose }) {
  const [d, setD] = useState(null);
  const [curScope, setCurScope] = useState(scope || "movement");
  const [query, setQuery] = useState("");
  useEffect(() => { setCurScope(scope || "movement"); setQuery(""); }, [account, scope]);
  useEffect(() => { if (account) { setD(null); api.qcAccountDetail({ year, account, scope: curScope }).then(setD).catch(() => setD(null)); } }, [year, account, curScope]);
  const q = query.trim().toLowerCase();
  const rows = (d?.rows || []).filter((r) => {
    if (!q) return true;
    const hay = [r.num, r.date, r.description, r.tiers, money(r.debit), money(r.credit), money(r.balance)].join(" ").toLowerCase();
    return hay.includes(q);
  });
  const fDebit = rows.reduce((s, r) => s + (r.debit || 0), 0);
  const fCredit = rows.reduce((s, r) => s + (r.credit || 0), 0);
  return (
    <Dialog open={!!account} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="qc-account-detail-modal" className="max-h-[88vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><FileText size={16} className="text-[#22C55E]" /> Détail du compte {account} {d?.name ? `— ${d.name}` : ""}</DialogTitle>
          <DialogDescription className="text-xs">{curScope === "cumulative" ? "Écritures cumulatives jusqu'à la fin de l'exercice" : `Écritures de l'exercice ${year}`} · Solde : {d ? money(d.balance) : "…"} $</DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-center gap-2">
          <div className="inline-flex overflow-hidden rounded-lg border border-slate-200" data-testid="qc-detail-scope-toggle">
            <button onClick={() => setCurScope("movement")} data-testid="qc-detail-scope-movement" className={`px-3 py-1.5 text-xs font-600 ${curScope === "movement" ? "bg-[#22C55E] text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>Exercice {year}</button>
            <button onClick={() => setCurScope("cumulative")} data-testid="qc-detail-scope-cumulative" className={`px-3 py-1.5 text-xs font-600 ${curScope === "cumulative" ? "bg-[#22C55E] text-white" : "bg-white text-slate-600 hover:bg-slate-50"}`}>Cumulatif</button>
          </div>
          <div className="relative flex-1 min-w-[180px]">
            <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Rechercher (n°, date, description, tiers, montant)…" data-testid="qc-detail-search" className="h-8 pl-3 text-sm" />
          </div>
        </div>
        {!d ? <p className="py-6 text-center text-sm text-slate-400">Chargement…</p>
          : (d.rows || []).length === 0 ? <p className="py-6 text-center text-sm text-slate-400" data-testid="qc-detail-empty">Aucune écriture pour ce compte.</p>
          : <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-detail-table">
              <thead><tr className="bg-[#0F172A] text-left text-xs uppercase text-white">
                <th className="px-3 py-2">N°</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Description</th><th className="px-3 py-2">Tiers</th><th className="px-3 py-2 text-right">Débit</th><th className="px-3 py-2 text-right">Crédit</th><th className="px-3 py-2 text-right">Solde</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {rows.length === 0 ? <tr data-testid="qc-detail-no-match"><td colSpan={7} className="py-6 text-center text-sm text-slate-400">Aucun résultat pour « {query} ».</td></tr>
                  : rows.map((r, i) => (
                  <tr key={i} className="hover:bg-slate-50" data-testid={`qc-detail-row-${i}`}>
                    <td className="px-3 py-1.5 font-mono-data text-xs text-[#22C55E]">{r.num}</td>
                    <td className="px-3 py-1.5 text-xs">{r.date}</td>
                    <td className="px-3 py-1.5">{r.description}</td>
                    <td className="px-3 py-1.5 text-xs text-slate-500">{r.tiers || "—"}</td>
                    <td className="px-3 py-1.5 text-right font-mono-data">{r.debit ? money(r.debit) : "—"}</td>
                    <td className="px-3 py-1.5 text-right font-mono-data">{r.credit ? money(r.credit) : "—"}</td>
                    <td className="px-3 py-1.5 text-right font-mono-data">{money(r.balance)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr className="border-t-2 border-[#0F172A] bg-slate-50 font-700">
                <td className="px-3 py-2" colSpan={4}>{q ? `TOTAL FILTRÉ (${rows.length})` : "TOTAL"}</td>
                <td className="px-3 py-2 text-right font-mono-data">{money(q ? fDebit : d.total_debit)}</td>
                <td className="px-3 py-2 text-right font-mono-data">{money(q ? fCredit : d.total_credit)}</td>
                <td className="px-3 py-2 text-right font-mono-data">{money(d.balance)}</td>
              </tr></tfoot>
            </table></div>}
        <DialogFooter><Button variant="outline" onClick={onClose}>Fermer</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function PlaceholderView({ label }) {
  return (
    <div className="card p-10 text-center" data-testid="qc-placeholder">
      <FileText size={36} className="mx-auto text-slate-300" />
      <h3 className="mt-3 font-display text-base font-700 text-[#0F172A]">{label}</h3>
      <p className="mt-1 text-sm text-slate-500">Cet écran sera construit à partir du <strong>modèle Excel</strong> de la structure comptable à venir.</p>
      <p className="mt-0.5 text-xs text-slate-400">Les écritures saisies alimenteront automatiquement ce rapport une fois la structure connue.</p>
    </div>
  );
}

// ===================== Écritures =====================
const emptyLine = () => ({ account: "", account_name: "", tiers: "", debit: "", credit: "" });

function EntriesView({ year, locked, canEdit }) {
  const [entries, setEntries] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [dlg, setDlg] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ date: TODAY, description: "", reference: "", lines: [emptyLine(), emptyLine()] });
  const [saving, setSaving] = useState(false);
  const [delTarget, setDelTarget] = useState(null);
  const [tplName, setTplName] = useState("");

  const load = useCallback(() => { if (year) api.qcEntries({ year }).then(setEntries).catch(() => setEntries([])); }, [year]);
  const loadTpl = useCallback(() => api.qcTemplates().then(setTemplates).catch(() => setTemplates([])), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.qcAccounts().then((r) => setAccounts(r.accounts || [])).catch(() => {}); loadTpl(); }, [loadTpl]);

  const accountOptions = accounts.map((a) => ({ account: a.gl, name: a.description }));

  const totalDebit = form.lines.reduce((s, l) => s + (Number(l.debit) || 0), 0);
  const totalCredit = form.lines.reduce((s, l) => s + (Number(l.credit) || 0), 0);
  const balanced = Math.abs(totalDebit - totalCredit) < 0.005 && totalDebit > 0;

  const openNew = () => { setEditing(null); setForm({ date: TODAY, description: "", reference: "", lines: [emptyLine(), emptyLine()] }); setTplName(""); setDlg(true); };
  const openEdit = (e) => {
    setEditing(e);
    setForm({ date: e.date, description: e.description || "", reference: e.reference || "",
      lines: (e.lines || []).map((l) => ({ account: l.account, account_name: l.account_name || "", tiers: l.tiers || "", debit: l.debit || "", credit: l.credit || "" })) });
    setTplName(""); setDlg(true);
  };
  const setLine = (i, k, v) => setForm((f) => ({ ...f, lines: f.lines.map((l, j) => j === i ? { ...l, [k]: v } : l) }));
  const onAccountChange = (i, acc) => {
    const found = accountOptions.find((o) => o.account === acc);
    setForm((f) => ({ ...f, lines: f.lines.map((l, j) => j === i ? { ...l, account: acc, account_name: found ? found.name : l.account_name } : l) }));
  };
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, emptyLine()] }));
  const removeLine = (i) => setForm((f) => ({ ...f, lines: f.lines.length > 2 ? f.lines.filter((_, j) => j !== i) : f.lines }));
  const applyTemplate = (t) => {
    if (!t) return;
    setForm((f) => ({ ...f, description: t.description || f.description,
      lines: (t.lines || []).map((l) => ({ account: l.account, account_name: l.account_name || "", tiers: l.tiers || "", debit: l.debit || "", credit: l.credit || "" })) }));
  };
  const saveTemplate = async () => {
    if (!tplName.trim()) { toast.error("Nommez le modèle"); return; }
    try {
      await api.qcCreateTemplate({ name: tplName, description: form.description,
        lines: form.lines.filter((l) => l.account).map((l) => ({ account: String(l.account).trim(), account_name: l.account_name || "", tiers: l.tiers || "", debit: Number(l.debit) || 0, credit: Number(l.credit) || 0 })) });
      toast.success("Modèle enregistré"); setTplName(""); loadTpl();
    } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); }
  };
  const delTemplate = async (t) => { try { await api.qcDeleteTemplate(t.id); toast.success("Modèle supprimé"); loadTpl(); } catch { toast.error("Impossible"); } };
  const journalPdf = async () => {
    try { const b = await api.qcJournalPdf({ year }); const url = URL.createObjectURL(b); const a = document.createElement("a"); a.href = url; a.download = `journal_9434_${year}.pdf`; a.click(); URL.revokeObjectURL(url); }
    catch { toast.error("Export impossible"); }
  };

  const save = async () => {
    const body = {
      date: form.date, description: form.description, reference: form.reference,
      lines: form.lines.filter((l) => l.account || l.debit || l.credit).map((l) => ({
        account: String(l.account).trim(), account_name: l.account_name || "", tiers: l.tiers || "",
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
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" onClick={journalPdf} data-testid="qc-journal-pdf" className="gap-2"><FileDown size={14} /> Journal PDF</Button>
          {canEdit && !locked && <Button size="sm" onClick={openNew} data-testid="qc-add-entry" className="gap-2 bg-[#22C55E] hover:bg-[#22C55E]/90"><Plus size={14} /> Nouvelle écriture</Button>}
        </div>
      </div>

      {entries.length === 0
        ? <div className="card p-10 text-center text-sm text-slate-400" data-testid="qc-entries-empty">Aucune écriture pour cet exercice.{canEdit && !locked ? " Cliquez « Nouvelle écriture » pour commencer." : ""}</div>
        : <div className="card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" data-testid="qc-entries-table">
                <thead>
                  <tr className="bg-[#0F172A] text-left text-xs uppercase tracking-wide text-white">
                    <th className="px-3 py-2">N°</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Réf.</th><th className="px-3 py-2">Description</th>
                    <th className="px-3 py-2">Comptes</th><th className="px-3 py-2 text-right">Montant</th><th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {entries.map((e) => (
                    <tr key={e.id} className="hover:bg-slate-50" data-testid={`qc-entry-row-${e.id}`}>
                      <td className="whitespace-nowrap px-3 py-2 font-mono-data text-xs font-600 text-[#22C55E]">{e.num}{e.source && e.source !== "manual" ? <span className="ml-1 rounded bg-slate-100 px-1 text-[9px] uppercase text-slate-500">{e.source === "closing" ? "fermeture" : e.source === "invoice" ? "fact." : e.source === "bill" ? "fourn." : e.source === "receipt" ? "encaiss." : e.source === "payment" ? "paiem." : e.source}</span> : null}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono-data text-xs">{e.date}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">{e.reference || "—"}</td>
                      <td className="px-3 py-2">{e.description || "—"}</td>
                      <td className="px-3 py-2 text-xs text-slate-500">
                        {(e.lines || []).map((l, i) => (
                          <div key={i}>{l.account}{l.account_name ? ` · ${l.account_name}` : ""}{l.tiers ? ` · ${l.tiers}` : ""} <span className={l.debit ? "text-[#0F172A]" : "text-[#22C55E]"}>{l.debit ? `Dt ${money(l.debit)}` : `Ct ${money(l.credit)}`}</span></div>
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

            {templates.length > 0 && (
              <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2" data-testid="qc-template-apply">
                <span className="text-xs font-600 text-slate-500"><Copy size={13} className="mr-1 inline" />Modèles :</span>
                {templates.map((t) => (
                  <span key={t.id} className="inline-flex items-center gap-1 rounded-full border border-slate-300 bg-white pl-2.5 pr-1 py-0.5 text-xs">
                    <button onClick={() => applyTemplate(t)} data-testid={`qc-tpl-apply-${t.id}`} className="font-600 text-[#22C55E] hover:underline">{t.name}</button>
                    <button onClick={() => delTemplate(t)} className="text-slate-300 hover:text-red-500"><X size={12} /></button>
                  </span>
                ))}
              </div>
            )}
            <div className="rounded-lg border border-slate-200">
              <table className="w-full text-sm">
                <thead><tr className="bg-slate-50 text-left text-[11px] uppercase text-slate-500">
                  <th className="px-2 py-1.5">Compte</th><th className="px-2 py-1.5">Nom du compte</th><th className="px-2 py-1.5">Fournisseur / Client</th><th className="px-2 py-1.5 text-right">Débit</th><th className="px-2 py-1.5 text-right">Crédit</th><th></th>
                </tr></thead>
                <tbody>
                  {form.lines.map((l, i) => (
                    <tr key={i} data-testid={`qc-line-${i}`}>
                      <td className="px-2 py-1">
                        <select value={l.account} onChange={(e) => onAccountChange(i, e.target.value)} data-testid={`qc-line-account-${i}`}
                          className="h-8 w-32 rounded-md border border-slate-300 bg-white px-1.5 text-sm focus:border-[#22C55E] focus:outline-none">
                          <option value="">—</option>
                          {accountOptions.map((o) => <option key={o.account} value={o.account}>{o.account}</option>)}
                        </select>
                      </td>
                      <td className="px-2 py-1"><Input value={l.account_name} onChange={(e) => setLine(i, "account_name", e.target.value)} placeholder="Nom" data-testid={`qc-line-name-${i}`} className="h-8" /></td>
                      <td className="px-2 py-1"><Input value={l.tiers} onChange={(e) => setLine(i, "tiers", e.target.value)} placeholder="(optionnel)" data-testid={`qc-line-tiers-${i}`} className="h-8 w-40" /></td>
                      <td className="px-2 py-1"><Input type="number" step="0.01" value={l.debit} onChange={(e) => setLine(i, "debit", e.target.value)} onFocus={() => l.credit && setLine(i, "credit", "")} data-testid={`qc-line-debit-${i}`} className="h-8 w-28 text-right" /></td>
                      <td className="px-2 py-1"><Input type="number" step="0.01" value={l.credit} onChange={(e) => setLine(i, "credit", e.target.value)} onFocus={() => l.debit && setLine(i, "debit", "")} data-testid={`qc-line-credit-${i}`} className="h-8 w-28 text-right" /></td>
                      <td className="px-1"><button onClick={() => removeLine(i)} disabled={form.lines.length <= 2} className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500 disabled:opacity-30"><X size={14} /></button></td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-slate-200 font-600">
                    <td className="px-2 py-1.5" colSpan={3}>
                      <button onClick={addLine} data-testid="qc-add-line" className="inline-flex items-center gap-1 text-xs text-[#22C55E] hover:underline"><Plus size={13} /> Ajouter une ligne</button>
                    </td>
                    <td className="px-2 py-1.5 text-right font-mono-data" data-testid="qc-total-debit">{money(totalDebit)}</td>
                    <td className="px-2 py-1.5 text-right font-mono-data" data-testid="qc-total-credit">{money(totalCredit)}</td>
                    <td></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-slate-300 px-3 py-2" data-testid="qc-template-save">
              <Save size={14} className="text-slate-400" />
              <Input value={tplName} onChange={(e) => setTplName(e.target.value)} placeholder="Nom du modèle (ex. Frais bancaires)" data-testid="qc-tpl-name" className="h-8 max-w-xs" />
              <Button size="sm" variant="outline" onClick={saveTemplate} data-testid="qc-tpl-save">Enregistrer comme modèle</Button>
            </div>
            <div data-testid="qc-balance-indicator" className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-600 ${balanced ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
              {balanced ? <><CheckCircle2 size={15} /> Écriture équilibrée</> : <><AlertTriangle size={15} /> Déséquilibre : {money(Math.abs(totalDebit - totalCredit))} $ (débits {money(totalDebit)} vs crédits {money(totalCredit)})</>}
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDlg(false)}>Annuler</Button>
            <Button onClick={save} disabled={!balanced || saving} data-testid="qc-entry-save" className="bg-[#22C55E] hover:bg-[#22C55E]/90">{saving ? "…" : "Enregistrer"}</Button>
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
  const [drill, setDrill] = useState(null);
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
            <thead><tr className="bg-[#0F172A] text-left text-xs uppercase tracking-wide text-white">
              <th className="px-3 py-2">Compte</th><th className="px-3 py-2">Nom du compte</th>
              <th className="px-3 py-2 text-right">Débit</th><th className="px-3 py-2 text-right">Crédit</th><th className="px-3 py-2 text-right">Solde</th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {tb.rows.length === 0 && <tr><td colSpan={5} className="px-3 py-6 text-center text-slate-400">Aucun compte (saisissez des écritures).</td></tr>}
              {tb.rows.map((r) => (
                <tr key={r.account} className="cursor-pointer hover:bg-[#22C55E]/5" onClick={() => setDrill(r.account)} data-testid={`qc-tb-row-${r.account}`} title="Voir le détail des écritures">
                  <td className="px-3 py-1.5 font-mono-data text-xs text-[#22C55E] underline decoration-dotted">{r.account}</td>
                  <td className="px-3 py-1.5">{r.account_name || "—"}</td>
                  <td className="px-3 py-1.5 text-right font-mono-data">{r.debit ? money(r.debit) : "—"}</td>
                  <td className="px-3 py-1.5 text-right font-mono-data">{r.credit ? money(r.credit) : "—"}</td>
                  <td className={`px-3 py-1.5 text-right font-mono-data ${r.balance < 0 ? "text-red-600" : ""}`}>{money(r.balance)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot><tr className="border-t-2 border-[#0F172A] bg-slate-50 font-700">
              <td className="px-3 py-2" colSpan={2}>TOTAL</td>
              <td className="px-3 py-2 text-right font-mono-data">{money(tb.total_debit)}</td>
              <td className="px-3 py-2 text-right font-mono-data">{money(tb.total_credit)}</td>
              <td className="px-3 py-2 text-right font-mono-data">{money(tb.total_debit - tb.total_credit)}</td>
            </tr></tfoot>
          </table>
        </div>
      </div>
      {drill && <AccountDetailModal year={year} account={drill} scope="movement" onClose={() => setDrill(null)} />}
    </div>
  );
}


// ===================== Factures clients (auxiliaire recevable) =====================
function InvoiceStatus({ status }) {
  if (status === "reversed") return <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs font-600 text-slate-600" data-testid="qc-status-reversed">Extournée</span>;
  if (status === "credit") return <span className="rounded-full bg-violet-50 px-2 py-0.5 text-xs font-600 text-violet-700" data-testid="qc-status-credit">Note de crédit</span>;
  if (status === "applied") return <span className="rounded-full bg-violet-50 px-2 py-0.5 text-xs font-600 text-violet-700" data-testid="qc-status-applied">NC appliquée</span>;
  if (status === "paid") return <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-600 text-emerald-700" data-testid="qc-status-paid">Encaissée</span>;
  if (status === "partial") return <span className="rounded-full bg-sky-50 px-2 py-0.5 text-xs font-600 text-sky-700" data-testid="qc-status-partial">Partielle</span>;
  return <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-600 text-amber-700" data-testid="qc-status-open">Ouverte</span>;
}

function BillStatus({ status }) {
  if (status === "paid") return <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-600 text-emerald-700" data-testid="qc-bill-status-paid">Payée</span>;
  if (status === "partial") return <span className="rounded-full bg-sky-50 px-2 py-0.5 text-xs font-600 text-sky-700" data-testid="qc-bill-status-partial">Partielle</span>;
  return <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs font-600 text-amber-700" data-testid="qc-bill-status-open">Ouverte</span>;
}

function PaymentHistoryDialog({ open, onOpenChange, kind, id, label }) {
  const [data, setData] = useState(null);
  useEffect(() => {
    if (!open || !id) { setData(null); return; }
    (kind === "bill" ? api.qcBillPayments(id) : api.qcInvoicePayments(id)).then(setData).catch(() => setData(null));
  }, [open, id, kind]);
  const doc = data ? (kind === "bill" ? data.bill : data.invoice) : null;
  const payments = data?.payments || [];
  const verb = kind === "bill" ? "Paiement" : "Encaissement";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="qc-payment-history-dialog" className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Clock size={16} className="text-[#22C55E]" /> Historique des {verb.toLowerCase()}s — {label}</DialogTitle>
          <DialogDescription className="text-xs">{doc ? <>Total {money(doc.total)} $ · Réglé {money(doc.paid_amount)} $ · Solde {money(doc.balance)} $ · <InvoiceStatus status={doc.status} /></> : "Chargement…"}</DialogDescription>
        </DialogHeader>
        {!data ? <p className="py-6 text-center text-sm text-slate-400">Chargement…</p>
          : payments.length === 0 ? <p className="py-6 text-center text-sm text-slate-400" data-testid="qc-payment-empty">Aucun {verb.toLowerCase()} enregistré pour l'instant.</p>
          : <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-payment-table">
              <thead><tr className="bg-[#0F172A] text-left text-xs uppercase text-white"><th className="px-3 py-2">Écriture</th><th className="px-3 py-2">Date</th><th className="px-3 py-2 text-right">Montant</th></tr></thead>
              <tbody className="divide-y divide-slate-100">
                {payments.map((p, i) => (
                  <tr key={i} data-testid={`qc-payment-row-${i}`}><td className="px-3 py-1.5 font-mono-data text-xs text-[#22C55E]">{p.num}</td><td className="px-3 py-1.5 text-xs">{p.date}</td><td className="px-3 py-1.5 text-right font-mono-data">{money(p.amount)}</td></tr>
                ))}
              </tbody>
              <tfoot><tr className="border-t-2 border-[#0F172A] bg-slate-50 font-700"><td className="px-3 py-2" colSpan={2}>Total réglé</td><td className="px-3 py-2 text-right font-mono-data">{money(payments.reduce((s, p) => s + (p.amount || 0), 0))}</td></tr></tfoot>
            </table></div>}
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Fermer</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const emptyItem = () => ({ description: "", account: "", amount: "" });

function LineItemsEditor({ items, setItems, accounts, testid, defaultAccount = "" }) {
  const upd = (i, k, v) => setItems(items.map((it, idx) => (idx === i ? { ...it, [k]: v } : it)));
  const add = () => setItems([...items, { ...emptyItem(), account: defaultAccount }]);
  const rm = (i) => setItems(items.length > 1 ? items.filter((_, idx) => idx !== i) : items);
  const subtotal = items.reduce((s, it) => s + (Number(it.amount) || 0), 0);
  return (
    <div data-testid={testid}>
      <div className="mb-1 flex items-center justify-between">
        <label className="text-xs font-600 text-slate-500">Lignes de la facture</label>
        <Button size="sm" variant="ghost" onClick={add} data-testid={`${testid}-add`} className="h-7 gap-1 text-[#22C55E] hover:bg-[#22C55E]/10"><Plus size={12} /> Ajouter</Button>
      </div>
      <div className="space-y-2">
        {items.map((it, i) => (
          <div key={i} className="flex items-center gap-2" data-testid={`${testid}-row-${i}`}>
            <Input value={it.description} onChange={(e) => upd(i, "description", e.target.value)} placeholder="Description" data-testid={`${testid}-desc-${i}`} className="h-8 flex-1" />
            <select value={it.account} onChange={(e) => upd(i, "account", e.target.value)} data-testid={`${testid}-account-${i}`} className="h-8 w-40 shrink-0 rounded-lg border border-slate-300 bg-white px-2 text-xs focus:border-[#22C55E] focus:outline-none">
              <option value="">Compte…</option>
              {accounts.map((a) => <option key={a.gl} value={a.gl}>{`${a.gl} · ${a.description}`}</option>)}
            </select>
            <Input type="number" step="0.01" value={it.amount} onChange={(e) => upd(i, "amount", e.target.value)} placeholder="0.00" data-testid={`${testid}-amount-${i}`} className="h-8 w-24 shrink-0 text-right font-mono-data" />
            <button onClick={() => rm(i)} data-testid={`${testid}-remove-${i}`} className="shrink-0 rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500" title="Supprimer"><Trash2 size={14} /></button>
          </div>
        ))}
      </div>
      <p className="mt-1 text-right text-xs text-slate-400">Sous-total : <span className="font-mono-data">{money(subtotal)} $</span></p>
    </div>
  );
}

const canEditInvoice = (r) => r.type !== "credit_note" && r.status !== "reversed" && (r.paid_amount || 0) === 0 && (r.credited_amount || 0) === 0;
const canReverseInvoice = (r) => r.type !== "credit_note" && r.status !== "reversed" && (r.paid_amount || 0) === 0;
const canCreditInvoice = (r) => r.type !== "credit_note" && r.status !== "reversed";

function InvoicesView({ year, locked, canEdit }) {
  const [rows, setRows] = useState([]);
  const [dlg, setDlg] = useState(false);
  const [saving, setSaving] = useState(false);
  const emptyForm = { date: TODAY, due_date: "", client_id: "", ar_account: "", client_name: "", client_att: "", client_address: "", client_email: "", items: [{ ...emptyItem(), account: "400310" }] };
  const [form, setForm] = useState(emptyForm);
  const [editing, setEditing] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [clients, setClients] = useState([]);
  const [history, setHistory] = useState(null);
  const [reminding, setReminding] = useState(false);
  const [creditTarget, setCreditTarget] = useState(undefined); // undefined = closed, null = standalone, obj = linked
  const [reverseTarget, setReverseTarget] = useState(null);
  const [receiveTarget, setReceiveTarget] = useState(null);
  const load = useCallback(() => { if (year) api.qcInvoices({ year }).then(setRows).catch(() => setRows([])); }, [year]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.qcAccounts().then((r) => setAccounts((r.accounts || []).filter((a) => a.type === "produit"))).catch(() => {}); api.qcClients().then(setClients).catch(() => {}); }, []);
  const amt = form.items.reduce((s, it) => s + (Number(it.amount) || 0), 0);
  const tps = Math.round(amt * 0.05 * 100) / 100, tvq = Math.round(amt * 0.09975 * 100) / 100, total = Math.round((amt + tps + tvq) * 100) / 100;
  const overdue = (r) => r.type !== "credit_note" && r.status !== "paid" && r.status !== "reversed" && r.due_date && r.due_date < TODAY;
  const onPickClient = (cid) => {
    if (!cid) { setForm((f) => ({ ...f, client_id: "" })); return; }
    const c = clients.find((x) => x.id === cid);
    if (!c) return;
    setForm((f) => ({ ...f, client_id: c.id, ar_account: c.ar_account || "", client_name: c.name || "", client_att: c.att || "", client_address: c.address || "", client_email: c.email || "" }));
  };
  const openNew = () => { setEditing(null); setForm(emptyForm); setDlg(true); };
  const openEdit = (inv) => {
    setEditing(inv);
    setForm({ date: inv.date || TODAY, due_date: inv.due_date || "", client_id: inv.client_id || "", ar_account: inv.ar_account || "",
      client_name: inv.client_name || "", client_att: inv.client_att || "", client_address: inv.client_address || "", client_email: inv.client_email || "",
      items: (inv.items && inv.items.length ? inv.items : [{ description: inv.description || "", account: inv.sales_account || "400310", amount: inv.amount || 0 }]).map((it) => ({ description: it.description || "", account: it.account || "400310", amount: it.amount })) });
    setDlg(true);
  };
  const save = async () => {
    const items = form.items.filter((it) => (Number(it.amount) || 0) > 0).map((it) => ({ description: it.description, account: it.account || "400310", amount: Number(it.amount) }));
    if (!form.client_name.trim() || items.length === 0) { toast.error("Client et au moins une ligne avec montant requis"); return; }
    setSaving(true);
    const body = { date: form.date, due_date: form.due_date, client_id: form.client_id || null, ar_account: form.ar_account || null, client_name: form.client_name, client_att: form.client_att, client_address: form.client_address, client_email: form.client_email, items };
    try {
      if (editing) { await api.qcUpdateInvoice(editing.id, body); toast.success("Facture modifiée"); }
      else { await api.qcCreateInvoice(body, { year }); toast.success("Facture créée et comptabilisée"); }
      setDlg(false); setEditing(null); setForm(emptyForm); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } finally { setSaving(false); }
  };
  const receive = (inv) => setReceiveTarget(inv);
  const doReceive = async (inv, amount) => {
    try { await api.qcReceiveInvoice(inv.id, { date: TODAY, amount }); toast.success("Encaissement comptabilisé"); setReceiveTarget(null); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Impossible"); }
  };
  const reverse = async () => {
    if (!reverseTarget) return;
    try { const r = await api.qcReverseInvoice(reverseTarget.id, { date: TODAY }); toast.success(r.message || "Facture extournée"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } finally { setReverseTarget(null); }
  };
  const emailInvoice = async (inv) => { try { const r = await api.qcEmailInvoice(inv.id); toast.success(r.message || "Envoyée"); } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } };
  const sendReminders = async () => {
    setReminding(true);
    try { const r = await api.qcInvoiceSendReminders({ year }); toast.success(r.message || "Rappels envoyés"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Envoi impossible"); } finally { setReminding(false); }
  };
  const pdf = async (inv) => { try { const b = await api.qcInvoicePdf(inv.id); const url = URL.createObjectURL(b); const a = document.createElement("a"); a.href = url; a.download = `facture_${inv.number}.pdf`; a.click(); URL.revokeObjectURL(url); } catch { toast.error("PDF indisponible"); } };
  const openTotal = rows.filter((r) => r.status !== "paid" && r.status !== "reversed").reduce((s, r) => s + (r.balance || 0), 0);
  const overdueCount = rows.filter(overdue).length;

  return (
    <div className="space-y-3" data-testid="qc-ar-view">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500">{rows.length} facture(s) · Solde à recevoir : <strong>{money(openTotal)} $</strong></p>
        {canEdit && !locked && <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setCreditTarget(null)} data-testid="qc-add-credit-note" className="gap-2"><FileMinus size={14} /> Note de crédit</Button>
          <Button size="sm" onClick={openNew} data-testid="qc-add-invoice" className="gap-2 bg-[#22C55E] hover:bg-[#22C55E]/90"><Plus size={14} /> Nouvelle facture</Button>
        </div>}
      </div>
      {overdueCount > 0 && <div data-testid="qc-ar-overdue-banner" className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-600 text-red-700"><span className="flex items-center gap-2"><AlertTriangle size={16} /> {overdueCount} facture(s) en retard (échéance dépassée).</span>{canEdit && <Button size="sm" onClick={sendReminders} disabled={reminding} data-testid="qc-ar-remind-btn" className="gap-1.5 bg-red-600 hover:bg-red-700"><Mail size={14} /> {reminding ? "Envoi…" : "Relancer les retards"}</Button>}</div>}
      {rows.length === 0
        ? <div className="card p-10 text-center text-sm text-slate-400" data-testid="qc-ar-empty">Aucune facture client pour cet exercice.</div>
        : <div className="card overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-invoices-table">
            <thead><tr className="bg-[#0F172A] text-left text-xs uppercase tracking-wide text-white">
              <th className="px-3 py-2">N°</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Échéance</th><th className="px-3 py-2">Client</th><th className="px-3 py-2 text-right">Total</th><th className="px-3 py-2 text-right">Solde</th><th className="px-3 py-2">Statut</th><th className="px-3 py-2"></th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => {
                const od = overdue(r);
                const isCN = r.type === "credit_note";
                return (
                <tr key={r.id} className={`hover:bg-slate-50 ${r.status === "reversed" ? "text-slate-400" : ""}`} data-testid={`qc-invoice-row-${r.id}`}>
                  <td className="px-3 py-2 font-mono-data text-xs">{r.number}{isCN && r.linked_number ? <span className="ml-1 text-[10px] text-violet-600">↩ {r.linked_number}</span> : null}</td>
                  <td className="px-3 py-2 text-xs">{r.date}</td>
                  <td className={`px-3 py-2 text-xs ${od ? "font-700 text-red-600" : "text-slate-500"}`}>{isCN ? "—" : (r.due_date || "—")}{od && <span className="ml-1 rounded bg-red-100 px-1 text-[10px] font-700 text-red-700">RETARD</span>}</td>
                  <td className={`px-3 py-2 ${r.status === "reversed" ? "line-through" : ""}`}>{r.client_name}</td>
                  <td className="px-3 py-2 text-right font-mono-data">{money(r.total)}</td>
                  <td className="px-3 py-2 text-right font-mono-data">{money(r.balance)}</td>
                  <td className="px-3 py-2"><InvoiceStatus status={r.status} /></td>
                  <td className="px-3 py-2"><div className="flex justify-end gap-1">
                    <button onClick={() => setHistory({ id: r.id, label: r.number })} data-testid={`qc-invoice-history-${r.id}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" title="Historique des encaissements"><Clock size={14} /></button>
                    {!isCN && <button onClick={() => pdf(r)} data-testid={`qc-invoice-pdf-${r.id}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" title="PDF"><FileDown size={14} /></button>}
                    {!isCN && r.client_email && <button onClick={() => emailInvoice(r)} data-testid={`qc-invoice-email-${r.id}`} className="rounded p-1.5 text-[#22C55E] hover:bg-[#22C55E]/10" title={`Envoyer à ${r.client_email}`}><Mail size={14} /></button>}
                    {canEdit && !locked && !isCN && r.status !== "paid" && r.status !== "reversed" && <button onClick={() => receive(r)} data-testid={`qc-invoice-receive-${r.id}`} className="rounded p-1.5 text-emerald-600 hover:bg-emerald-50" title="Encaisser"><Wallet size={14} /></button>}
                    {canEdit && !locked && canEditInvoice(r) && <button onClick={() => openEdit(r)} data-testid={`qc-invoice-edit-${r.id}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" title="Modifier"><Pencil size={14} /></button>}
                    {canEdit && !locked && canCreditInvoice(r) && <button onClick={() => setCreditTarget(r)} data-testid={`qc-invoice-credit-${r.id}`} className="rounded p-1.5 text-violet-600 hover:bg-violet-50" title="Note de crédit"><FileMinus size={14} /></button>}
                    {canEdit && !locked && canReverseInvoice(r) && <button onClick={() => setReverseTarget(r)} data-testid={`qc-invoice-reverse-${r.id}`} className="rounded p-1.5 text-orange-600 hover:bg-orange-50" title="Extourner"><RotateCcw size={14} /></button>}
                  </div></td>
                </tr>
              );})}
            </tbody>
          </table></div></div>}

      <PaymentHistoryDialog open={!!history} onOpenChange={(v) => !v && setHistory(null)} kind="invoice" id={history?.id} label={history?.label} />

      <CreditNoteDialog open={creditTarget !== undefined} invoice={creditTarget} year={year} accounts={accounts} clients={clients}
        onClose={() => setCreditTarget(undefined)} onDone={() => { setCreditTarget(undefined); load(); }} />

      <ReceivePaymentDialog invoice={receiveTarget} onClose={() => setReceiveTarget(null)} onConfirm={doReceive} />

      <AlertDialog open={!!reverseTarget} onOpenChange={(v) => !v && setReverseTarget(null)}>
        <AlertDialogContent data-testid="qc-reverse-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Extourner la facture {reverseTarget?.number} ?</AlertDialogTitle>
            <AlertDialogDescription>L'écriture inverse sera comptabilisée : le solde sera annulé et la facture marquée « Extournée ». Action réservée aux factures sans encaissement.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="qc-reverse-cancel">Annuler</AlertDialogCancel>
            <AlertDialogAction onClick={reverse} data-testid="qc-reverse-confirm" className="bg-orange-600 hover:bg-orange-700">Extourner</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={dlg} onOpenChange={(v) => { setDlg(v); if (!v) setEditing(null); }}>
        <DialogContent data-testid="qc-invoice-dialog" className="max-w-lg">
          <DialogHeader><DialogTitle>{editing ? `Modifier la facture ${editing.number}` : "Nouvelle facture client"} — Exercice {year}</DialogTitle>
            <DialogDescription className="text-xs">La comptabilisation (Dr Comptes à recevoir / Cr Ventes + taxes) est automatique et reste modifiable dans les Écritures.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs font-600 text-slate-500">Client du carnet (optionnel — applique son compte AR)</label>
              <select value={form.client_id} onChange={(e) => onPickClient(e.target.value)} data-testid="qc-invoice-client-select" className="h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-sm focus:border-[#22C55E] focus:outline-none">
                <option value="">— Saisie libre —</option>
                {clients.filter((c) => c.active !== false).map((c) => <option key={c.id} value={c.id}>{`${c.name} · CR ${c.ar_account}`}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Date</label><Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="qc-invoice-date" className="h-9" /></div>
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Échéance</label><Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} data-testid="qc-invoice-due" className="h-9" /></div>
            </div>
            <Input value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} placeholder="Nom du client" data-testid="qc-invoice-client" className="h-9" />
            <Input value={form.client_att} onChange={(e) => setForm({ ...form, client_att: e.target.value })} placeholder="À l'attention de (optionnel)" data-testid="qc-invoice-att" className="h-9" />
            <Input type="email" value={form.client_email} onChange={(e) => setForm({ ...form, client_email: e.target.value })} placeholder="Courriel du client (pour l'envoi par courriel)" data-testid="qc-invoice-email-input" className="h-9" />
            <Input value={form.client_address} onChange={(e) => setForm({ ...form, client_address: e.target.value })} placeholder="Adresse (optionnel)" className="h-9" />
            <LineItemsEditor items={form.items} setItems={(items) => setForm({ ...form, items })} accounts={accounts} defaultAccount="400310" testid="qc-invoice-items" />
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm" data-testid="qc-invoice-totals">
              <div className="flex justify-between"><span>Total des ventes</span><span className="font-mono-data">{money(amt)} $</span></div>
              <div className="flex justify-between text-slate-500"><span>T.P.S. (5,0 %)</span><span className="font-mono-data">{money(tps)} $</span></div>
              <div className="flex justify-between text-slate-500"><span>T.V.Q. (9,975 %)</span><span className="font-mono-data">{money(tvq)} $</span></div>
              <div className="mt-1 flex justify-between border-t border-slate-200 pt-1 font-700 text-[#0F172A]"><span>TOTAL</span><span className="font-mono-data">{money(total)} $</span></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDlg(false); setEditing(null); }}>Annuler</Button>
            <Button onClick={save} disabled={saving || amt <= 0 || !form.client_name.trim()} data-testid="qc-invoice-save" className="bg-[#22C55E] hover:bg-[#22C55E]/90">{saving ? "…" : editing ? "Enregistrer les modifications" : "Créer & comptabiliser"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ===================== Encaissement d'une facture =====================
function ReceivePaymentDialog({ invoice, onClose, onConfirm }) {
  const [amount, setAmount] = useState("");
  const [full, setFull] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (invoice) { setFull(true); setAmount(String(invoice.balance ?? "")); } }, [invoice]);
  const bal = invoice ? Number(invoice.balance || 0) : 0;
  const amt = full ? bal : Number(amount || 0);
  const invalid = !full && (amt <= 0 || amt > bal + 0.005);
  const submit = async () => { if (invalid || !invoice) return; setSaving(true); try { await onConfirm(invoice, full ? 0 : amt); } finally { setSaving(false); } };
  return (
    <Dialog open={!!invoice} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="qc-receive-dialog" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Wallet size={16} className="text-emerald-600" /> Encaisser la facture {invoice?.number}</DialogTitle>
          <DialogDescription className="text-xs">Solde restant : <strong>{money(bal)} $</strong>. L'écriture (Dr Encaisse / Cr Comptes clients) est comptabilisée automatiquement.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={full} onChange={(e) => setFull(e.target.checked)} data-testid="qc-receive-full" /> Encaisser le solde complet</label>
          {!full && <div>
            <label className="mb-1 block text-xs font-600 text-slate-500">Montant à encaisser ($)</label>
            <Input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="qc-receive-amount" className="h-9 text-right font-mono-data" autoFocus />
            {invalid && <p className="mt-1 text-xs font-600 text-red-600">Le montant doit être supérieur à 0 et ne pas dépasser le solde ({money(bal)} $).</p>}
          </div>}
          <div className="rounded-lg bg-emerald-50 px-3 py-2 text-sm" data-testid="qc-receive-preview">
            <div className="flex justify-between font-700 text-emerald-700"><span>À encaisser</span><span className="font-mono-data">{money(amt)} $</span></div>
            <div className="flex justify-between text-slate-500"><span>Solde après encaissement</span><span className="font-mono-data">{money(Math.max(0, bal - amt))} $</span></div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annuler</Button>
          <Button onClick={submit} disabled={saving || invalid} data-testid="qc-receive-confirm" className="bg-emerald-600 hover:bg-emerald-700">{saving ? "…" : "Comptabiliser l'encaissement"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ===================== Note de crédit (liée ou autonome) =====================
function CreditNoteDialog({ open, invoice, year, accounts, clients, onClose, onDone }) {
  const linked = invoice || null; // objet facture si liée, sinon null (autonome)
  const [saving, setSaving] = useState(false);
  const empty = { date: TODAY, client_id: "", ar_account: "", client_name: "", client_att: "", client_address: "", client_email: "", items: [{ ...emptyItem(), account: "400310" }] };
  const [form, setForm] = useState(empty);
  useEffect(() => {
    if (!open) return;
    if (linked) setForm({ date: TODAY, client_id: linked.client_id || "", ar_account: linked.ar_account || "", client_name: linked.client_name || "", client_att: linked.client_att || "", client_address: linked.client_address || "", client_email: linked.client_email || "", items: [{ ...emptyItem(), account: linked.sales_account || "400310" }] });
    else setForm(empty);
  }, [open, invoice]); // eslint-disable-line
  const onPickClient = (cid) => {
    if (!cid) { setForm((f) => ({ ...f, client_id: "" })); return; }
    const c = clients.find((x) => x.id === cid);
    if (!c) return;
    setForm((f) => ({ ...f, client_id: c.id, ar_account: c.ar_account || "", client_name: c.name || "", client_att: c.att || "", client_address: c.address || "", client_email: c.email || "" }));
  };
  const amt = form.items.reduce((s, it) => s + (Number(it.amount) || 0), 0);
  const tps = Math.round(amt * 0.05 * 100) / 100, tvq = Math.round(amt * 0.09975 * 100) / 100, total = Math.round((amt + tps + tvq) * 100) / 100;
  const remaining = linked ? (linked.balance || 0) : null;
  const save = async () => {
    const items = form.items.filter((it) => (Number(it.amount) || 0) > 0).map((it) => ({ description: it.description, account: it.account || "400310", amount: Number(it.amount) }));
    if (!form.client_name.trim() || items.length === 0) { toast.error("Client et au moins une ligne avec montant requis"); return; }
    setSaving(true);
    const body = { date: form.date, client_name: form.client_name, client_att: form.client_att, client_address: form.client_address, client_email: form.client_email, client_id: form.client_id || null, ar_account: form.ar_account || null, items, invoice_id: linked ? linked.id : null };
    try { await api.qcCreateCreditNote(body, { year }); toast.success("Note de crédit comptabilisée"); onDone(); }
    catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } finally { setSaving(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="qc-credit-note-dialog" className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{linked ? `Note de crédit — facture ${linked.number}` : "Nouvelle note de crédit"}</DialogTitle>
          <DialogDescription className="text-xs">{linked ? `Solde de la facture liée : ${money(remaining)} $. L'écriture inverse (Dr Ventes/taxes, Cr Comptes clients) réduit le solde de la facture.` : "Note de crédit autonome (non liée à une facture)."}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          {!linked && <div>
            <label className="mb-1 block text-xs font-600 text-slate-500">Client du carnet (optionnel)</label>
            <select value={form.client_id} onChange={(e) => onPickClient(e.target.value)} data-testid="qc-cn-client-select" className="h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-sm focus:border-[#22C55E] focus:outline-none">
              <option value="">— Saisie libre —</option>
              {clients.filter((c) => c.active !== false).map((c) => <option key={c.id} value={c.id}>{`${c.name} · CR ${c.ar_account}`}</option>)}
            </select>
          </div>}
          <div className="grid grid-cols-2 gap-3">
            <div><label className="mb-1 block text-xs font-600 text-slate-500">Date</label><Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="qc-cn-date" className="h-9" /></div>
            <div><label className="mb-1 block text-xs font-600 text-slate-500">Client</label><Input value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} disabled={!!linked} placeholder="Nom du client" data-testid="qc-cn-client" className="h-9" /></div>
          </div>
          <LineItemsEditor items={form.items} setItems={(items) => setForm({ ...form, items })} accounts={accounts} defaultAccount="400310" testid="qc-cn-items" />
          <div className="rounded-lg bg-violet-50 px-3 py-2 text-sm" data-testid="qc-cn-totals">
            <div className="flex justify-between"><span>Total des crédits</span><span className="font-mono-data">{money(amt)} $</span></div>
            <div className="flex justify-between text-slate-500"><span>T.P.S. (5,0 %)</span><span className="font-mono-data">{money(tps)} $</span></div>
            <div className="flex justify-between text-slate-500"><span>T.V.Q. (9,975 %)</span><span className="font-mono-data">{money(tvq)} $</span></div>
            <div className="mt-1 flex justify-between border-t border-violet-200 pt-1 font-700 text-violet-700"><span>TOTAL À CRÉDITER</span><span className="font-mono-data">{money(total)} $</span></div>
            {linked && total > remaining + 0.005 && <p className="mt-1 text-xs font-600 text-red-600">Le total dépasse le solde de la facture ({money(remaining)} $).</p>}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Annuler</Button>
          <Button onClick={save} disabled={saving || amt <= 0 || !form.client_name.trim() || (linked && total > remaining + 0.005)} data-testid="qc-cn-save" className="bg-violet-600 hover:bg-violet-700">{saving ? "…" : "Créer la note de crédit"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ===================== Carnet de clients =====================
function ClientsView({ isAdmin, year }) {
  const [rows, setRows] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [dlg, setDlg] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [delTarget, setDelTarget] = useState(null);
  const [stmtClient, setStmtClient] = useState(null);
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [purging, setPurging] = useState(false);
  const empty = { name: "", att: "", address: "", email: "", ar_account: "", active: true };
  const [form, setForm] = useState(empty);
  const load = useCallback(() => api.qcClients().then(setRows).catch(() => setRows([])), []);
  useEffect(() => { load(); api.qcAccounts().then((r) => setAccounts((r.accounts || []).filter((a) => a.type === "actif"))).catch(() => {}); }, [load]);
  const openNew = () => { setEditing(null); setForm(empty); setDlg(true); };
  const openEdit = (c) => { setEditing(c); setForm({ name: c.name || "", att: c.att || "", address: c.address || "", email: c.email || "", ar_account: c.ar_account || "", active: c.active !== false }); setDlg(true); };
  const save = async () => {
    if (!form.name.trim()) { toast.error("Le nom du client est requis"); return; }
    setSaving(true);
    try {
      if (editing) { await api.qcUpdateClient(editing.id, form); toast.success("Client modifié"); }
      else { await api.qcCreateClient(form); toast.success("Client créé"); }
      setDlg(false); setEditing(null); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } finally { setSaving(false); }
  };
  const del = async () => { if (!delTarget) return; try { await api.qcDeleteClient(delTarget.id); toast.success("Client supprimé"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } finally { setDelTarget(null); } };
  const purge = async () => {
    setPurging(true);
    try { const r = await api.qcPurgeTestData(); toast.success(r.message || "Données de test purgées"); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } finally { setPurging(false); setPurgeOpen(false); }
  };
  const accName = (gl) => { const a = accounts.find((x) => x.gl === gl); return a ? `${a.gl} · ${a.description}` : gl; };
  return (
    <div className="space-y-3" data-testid="qc-clients-view">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500">{rows.length} client(s) au carnet.</p>
        {isAdmin && <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={() => setPurgeOpen(true)} data-testid="qc-purge-test-btn" className="gap-2 text-red-600 hover:bg-red-50"><Trash2 size={14} /> Purger données test</Button>
          <Button size="sm" onClick={openNew} data-testid="qc-add-client" className="gap-2 bg-[#22C55E] hover:bg-[#22C55E]/90"><Plus size={14} /> Nouveau client</Button>
        </div>}
      </div>
      {rows.length === 0
        ? <div className="card p-10 text-center text-sm text-slate-400" data-testid="qc-clients-empty">Aucun client. {isAdmin ? "Ajoutez-en un pour attribuer un compte de comptes-clients dédié." : ""}</div>
        : <div className="card overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-clients-table">
            <thead><tr className="bg-[#0F172A] text-left text-xs uppercase tracking-wide text-white">
              <th className="px-3 py-2">Nom</th><th className="px-3 py-2">À l'attention</th><th className="px-3 py-2">Courriel</th><th className="px-3 py-2">Compte clients (AR)</th><th className="px-3 py-2">Statut</th><th className="px-3 py-2"></th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((c) => (
                <tr key={c.id} className="hover:bg-slate-50" data-testid={`qc-client-row-${c.id}`}>
                  <td className="px-3 py-2 font-600">{c.name}</td>
                  <td className="px-3 py-2 text-slate-500">{c.att || "—"}</td>
                  <td className="px-3 py-2 text-slate-500">{c.email || "—"}</td>
                  <td className="px-3 py-2 font-mono-data text-xs">{accName(c.ar_account)}</td>
                  <td className="px-3 py-2">{c.active !== false ? <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-600 text-emerald-700">Actif</span> : <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-600 text-slate-500">Inactif</span>}</td>
                  <td className="px-3 py-2"><div className="flex justify-end gap-1">
                    <button onClick={() => setStmtClient(c)} data-testid={`qc-client-statement-${c.id}`} className="rounded p-1.5 text-[#22C55E] hover:bg-[#22C55E]/10" title="Relevé de compte"><FileText size={14} /></button>
                    {isAdmin && <button onClick={() => openEdit(c)} data-testid={`qc-client-edit-${c.id}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" title="Modifier"><Pencil size={14} /></button>}
                    {isAdmin && <button onClick={() => setDelTarget(c)} data-testid={`qc-client-delete-${c.id}`} className="rounded p-1.5 text-red-500 hover:bg-red-50" title="Supprimer"><Trash2 size={14} /></button>}
                  </div></td>
                </tr>
              ))}
            </tbody>
          </table></div></div>}

      <Dialog open={dlg} onOpenChange={(v) => { setDlg(v); if (!v) setEditing(null); }}>
        <DialogContent data-testid="qc-client-dialog" className="max-w-md">
          <DialogHeader><DialogTitle>{editing ? "Modifier le client" : "Nouveau client"}</DialogTitle>
            <DialogDescription className="text-xs">Le compte de comptes-clients (AR) sélectionné est utilisé automatiquement à la facturation de ce client.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Nom du client" data-testid="qc-client-name" className="h-9" />
            <Input value={form.att} onChange={(e) => setForm({ ...form, att: e.target.value })} placeholder="À l'attention de (optionnel)" data-testid="qc-client-att" className="h-9" />
            <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Courriel (optionnel)" data-testid="qc-client-email" className="h-9" />
            <Input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} placeholder="Adresse (optionnel)" data-testid="qc-client-address" className="h-9" />
            <div>
              <label className="mb-1 block text-xs font-600 text-slate-500">Compte de comptes-clients (AR)</label>
              <select value={form.ar_account} onChange={(e) => setForm({ ...form, ar_account: e.target.value })} data-testid="qc-client-ar" className="h-9 w-full rounded-lg border border-slate-300 bg-white px-2 text-sm focus:border-[#22C55E] focus:outline-none">
                <option value="">— Compte par défaut —</option>
                {accounts.map((a) => <option key={a.gl} value={a.gl}>{`${a.gl} · ${a.description}`}</option>)}
              </select>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} data-testid="qc-client-active" /> Client actif</label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDlg(false); setEditing(null); }}>Annuler</Button>
            <Button onClick={save} disabled={saving || !form.name.trim()} data-testid="qc-client-save" className="bg-[#22C55E] hover:bg-[#22C55E]/90">{saving ? "…" : editing ? "Enregistrer" : "Créer"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!delTarget} onOpenChange={(v) => !v && setDelTarget(null)}>
        <AlertDialogContent data-testid="qc-client-delete-dialog">
          <AlertDialogHeader><AlertDialogTitle>Supprimer ce client ?</AlertDialogTitle>
            <AlertDialogDescription>{delTarget?.name} sera retiré du carnet. Les factures déjà émises ne sont pas affectées.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction onClick={del} data-testid="qc-client-delete-confirm" className="bg-red-600 hover:bg-red-700">Supprimer</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <ClientStatementDialog client={stmtClient} year={year} onClose={() => setStmtClient(null)} />

      <AlertDialog open={purgeOpen} onOpenChange={(v) => !v && setPurgeOpen(false)}>
        <AlertDialogContent data-testid="qc-purge-dialog">
          <AlertDialogHeader><AlertDialogTitle>Purger les données de démonstration ?</AlertDialogTitle>
            <AlertDialogDescription>Tous les clients, factures clients et factures fournisseurs dont le nom commence par « TEST_ » seront supprimés définitivement, ainsi que leurs écritures comptables. Les vraies données ne sont pas touchées.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction onClick={purge} disabled={purging} data-testid="qc-purge-confirm" className="bg-red-600 hover:bg-red-700">{purging ? "…" : "Purger"}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

// ===================== Relevé de compte client =====================
function ClientStatementDialog({ client, year, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!client) { setData(null); return; }
    setLoading(true);
    api.qcClientStatement(client.id, year ? { year } : {}).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [client, year]);
  const pdf = async () => {
    try { const b = await api.qcClientStatementPdf(client.id, year ? { year } : {}); const url = URL.createObjectURL(b); const a = document.createElement("a"); a.href = url; a.download = `releve_${client.name}.pdf`; a.click(); URL.revokeObjectURL(url); }
    catch { toast.error("PDF indisponible"); }
  };
  const t = data?.totals;
  return (
    <Dialog open={!!client} onOpenChange={(v) => !v && onClose()}>
      <DialogContent data-testid="qc-statement-dialog" className="max-h-[88vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><FileText size={16} className="text-[#22C55E]" /> Relevé de compte — {client?.name}</DialogTitle>
          <DialogDescription className="text-xs">{year ? `Exercice ${year}` : "Tous les exercices"} · Compte clients {client?.ar_account}</DialogDescription>
        </DialogHeader>
        {loading ? <p className="py-6 text-center text-sm text-slate-400">Chargement…</p>
          : !data || data.rows.length === 0 ? <p className="py-6 text-center text-sm text-slate-400" data-testid="qc-statement-empty">Aucune facture ni note de crédit pour ce client.</p>
          : <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-statement-table">
              <thead><tr className="bg-[#0F172A] text-left text-xs uppercase text-white">
                <th className="px-3 py-2">N°</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Type</th><th className="px-3 py-2 text-right">Total</th><th className="px-3 py-2 text-right">Réglé</th><th className="px-3 py-2 text-right">Crédité</th><th className="px-3 py-2 text-right">Solde</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {data.rows.map((r, i) => (
                  <tr key={i} className={`hover:bg-slate-50 ${r.status === "reversed" ? "text-slate-400 line-through" : ""}`} data-testid={`qc-statement-row-${i}`}>
                    <td className="px-3 py-1.5 font-mono-data text-xs">{r.number}{r.linked_number ? <span className="ml-1 text-[10px] text-violet-600">↩ {r.linked_number}</span> : null}</td>
                    <td className="px-3 py-1.5 text-xs">{r.date}</td>
                    <td className={`px-3 py-1.5 text-xs ${r.is_credit_note ? "text-violet-700" : ""}`}>{r.type}{r.status === "reversed" ? " (Extournée)" : ""}</td>
                    <td className="px-3 py-1.5 text-right font-mono-data">{money(r.total)}</td>
                    <td className="px-3 py-1.5 text-right font-mono-data">{money(r.paid_amount)}</td>
                    <td className="px-3 py-1.5 text-right font-mono-data">{money(r.credited_amount)}</td>
                    <td className="px-3 py-1.5 text-right font-mono-data">{money(r.balance)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr className="border-t-2 border-[#0F172A] bg-slate-50 font-700 text-[#0F172A]" data-testid="qc-statement-totals">
                <td className="px-3 py-2" colSpan={3}>TOTAUX</td>
                <td className="px-3 py-2 text-right font-mono-data">{money(t?.billed)}</td>
                <td className="px-3 py-2 text-right font-mono-data">{money(t?.paid)}</td>
                <td className="px-3 py-2 text-right font-mono-data">{money(t?.credited)}</td>
                <td className="px-3 py-2 text-right font-mono-data">{money(t?.balance)}</td>
              </tr></tfoot>
            </table>
            <p className="mt-3 rounded-lg bg-[#22C55E]/10 px-3 py-2 text-right text-sm font-700 text-[#0F172A]" data-testid="qc-statement-balance">Solde dû : {money(t?.balance)} $</p>
          </div>}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Fermer</Button>
          {data && data.rows.length > 0 && <Button onClick={pdf} data-testid="qc-statement-pdf" className="gap-2 bg-[#22C55E] hover:bg-[#22C55E]/90"><FileDown size={14} /> Télécharger le relevé (PDF)</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
function BillsView({ year, locked, canEdit }) {
  const [rows, setRows] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [dlg, setDlg] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ supplier: "", date: TODAY, due_date: "", reference: "", items: [{ ...emptyItem(), account: "540210" }] });
  const [file, setFile] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const load = useCallback(() => { if (year) api.qcBills({ year }).then(setRows).catch(() => setRows([])); }, [year]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.qcAccounts().then((r) => setAccounts((r.accounts || []).filter((a) => a.type === "charge"))).catch(() => {}); }, []);
  const amt = form.items.reduce((s, it) => s + (Number(it.amount) || 0), 0);
  const tps = Math.round(amt * 0.05 * 100) / 100, tvq = Math.round(amt * 0.09975 * 100) / 100, total = Math.round((amt + tps + tvq) * 100) / 100;
  const resetForm = () => { setForm({ supplier: "", date: TODAY, due_date: "", reference: "", items: [{ ...emptyItem(), account: "540210" }] }); setFile(null); };
  const analyze = async (f) => {
    if (!f) return;
    setAnalyzing(true);
    try {
      const d = await api.qcBillExtract(f);
      const items = (d.items || []).map((it) => ({ description: it.description || "", account: it.account || "540210", amount: it.amount || "" }));
      setForm((prev) => ({ ...prev, supplier: d.supplier || prev.supplier, date: d.date || prev.date, due_date: d.due_date || prev.due_date, reference: d.reference || prev.reference, items: items.length ? items : prev.items }));
      toast.success(`Facture analysée (confiance ${Math.round((d.confidence || 0) * 100)}%) — vérifiez les champs`);
    } catch (e) { toast.error(e.response?.data?.detail || "Analyse impossible"); } finally { setAnalyzing(false); }
  };
  const onFile = (f) => { setFile(f); if (f) analyze(f); };
  const save = async () => {
    const items = form.items.filter((it) => (Number(it.amount) || 0) > 0 && it.account).map((it) => ({ description: it.description, account: it.account, amount: Number(it.amount) }));
    if (!form.supplier.trim() || items.length === 0) { toast.error("Fournisseur et au moins une ligne (compte + montant) requis"); return; }
    const fd = new FormData();
    fd.append("year", year); fd.append("supplier", form.supplier); fd.append("date", form.date);
    fd.append("due_date", form.due_date); fd.append("reference", form.reference); fd.append("items_json", JSON.stringify(items));
    if (file) fd.append("file", file);
    setSaving(true);
    try { await api.qcCreateBill(fd); toast.success("Facture fournisseur comptabilisée"); setDlg(false); resetForm(); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } finally { setSaving(false); }
  };
  const pay = async (b) => {
    const input = window.prompt(`Montant à payer (solde ${money(b.balance)} $) — laisser vide pour le solde complet :`, "");
    if (input === null) return;
    const a = input.trim() === "" ? 0 : Number(input);
    try { await api.qcPayBill(b.id, { date: TODAY, amount: a }); toast.success("Paiement comptabilisé"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); }
  };
  const overdue = (r) => r.status !== "paid" && r.due_date && r.due_date < TODAY;
  const overdueCount = rows.filter(overdue).length;
  const openTotal = rows.filter((r) => r.status !== "paid").reduce((s, r) => s + (r.balance || 0), 0);
  const API = process.env.REACT_APP_BACKEND_URL;
  const token = localStorage.getItem("token");
  const viewFile = (b) => window.open(`${API}/api/qc9434/bills/${b.id}/file?auth=${token}`, "_blank");
  const [history, setHistory] = useState(null);

  return (
    <div className="space-y-3" data-testid="qc-ap-view">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-500">{rows.length} facture(s) · Solde à payer : <strong>{money(openTotal)} $</strong></p>
        {canEdit && !locked && <Button size="sm" onClick={() => setDlg(true)} data-testid="qc-add-bill" className="gap-2 bg-[#22C55E] hover:bg-[#22C55E]/90"><Upload size={14} /> Téléverser une facture</Button>}
      </div>
      {overdueCount > 0 && <div data-testid="qc-ap-overdue-banner" className="flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm font-600 text-red-700"><AlertTriangle size={16} /> {overdueCount} facture(s) fournisseur en retard (échéance dépassée).</div>}
      {rows.length === 0
        ? <div className="card p-10 text-center text-sm text-slate-400" data-testid="qc-ap-empty">Aucune facture fournisseur pour cet exercice.</div>
        : <div className="card overflow-hidden"><div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-bills-table">
            <thead><tr className="bg-[#0F172A] text-left text-xs uppercase tracking-wide text-white">
              <th className="px-3 py-2">Réf.</th><th className="px-3 py-2">Fournisseur</th><th className="px-3 py-2">Date</th><th className="px-3 py-2">Échéance</th><th className="px-3 py-2 text-right">Total</th><th className="px-3 py-2 text-right">Solde</th><th className="px-3 py-2">Statut</th><th className="px-3 py-2"></th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {rows.map((r) => {
                const od = overdue(r);
                return (
                <tr key={r.id} className="hover:bg-slate-50" data-testid={`qc-bill-row-${r.id}`}>
                  <td className="px-3 py-2 font-mono-data text-xs">{r.number}</td>
                  <td className="px-3 py-2">{r.supplier}</td>
                  <td className="px-3 py-2 text-xs">{r.date}</td>
                  <td className={`px-3 py-2 text-xs ${od ? "font-700 text-red-600" : "text-slate-500"}`}>{r.due_date || "—"}{od && <span className="ml-1 rounded bg-red-100 px-1 text-[10px] font-700 text-red-700">RETARD</span>}</td>
                  <td className="px-3 py-2 text-right font-mono-data">{money(r.total)}</td>
                  <td className="px-3 py-2 text-right font-mono-data">{money(r.balance)}</td>
                  <td className="px-3 py-2"><BillStatus status={r.status} /></td>
                  <td className="px-3 py-2"><div className="flex justify-end gap-1">
                    <button onClick={() => setHistory({ id: r.id, label: r.number })} data-testid={`qc-bill-history-${r.id}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" title="Historique des paiements"><Clock size={14} /></button>
                    {r.file_id && <button onClick={() => viewFile(r)} data-testid={`qc-bill-file-${r.id}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100" title="Voir le fichier"><Eye size={14} /></button>}
                    {canEdit && !locked && r.status !== "paid" && <button onClick={() => pay(r)} data-testid={`qc-bill-pay-${r.id}`} className="rounded p-1.5 text-emerald-600 hover:bg-emerald-50" title="Payer"><Wallet size={14} /></button>}
                  </div></td>
                </tr>
              );})}
            </tbody>
          </table></div></div>}

      <PaymentHistoryDialog open={!!history} onOpenChange={(v) => !v && setHistory(null)} kind="bill" id={history?.id} label={history?.label} />

      <Dialog open={dlg} onOpenChange={setDlg}>
        <DialogContent data-testid="qc-bill-dialog" className="max-w-lg">
          <DialogHeader><DialogTitle>Facture fournisseur — Exercice {year}</DialogTitle>
            <DialogDescription className="text-xs">Comptabilisation auto : Dr Charge + Dr TPS/TVQ à recevoir / Cr Comptes à payer. Modifiable dans les Écritures.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <div className="rounded-lg border border-dashed border-[#22C55E]/40 bg-[#22C55E]/5 px-3 py-2.5">
              <label className="mb-1 flex items-center gap-1.5 text-xs font-600 text-[#22C55E]"><Upload size={13} /> Fichier de la facture (PDF/image) — analyse automatique</label>
              <input type="file" accept=".pdf,.png,.jpg,.jpeg,.webp" onChange={(e) => onFile(e.target.files[0])} data-testid="qc-bill-file-input" className="text-sm" />
              {analyzing && <p className="mt-1 flex items-center gap-1.5 text-xs font-600 text-[#22C55E]" data-testid="qc-bill-analyzing"><span className="h-3 w-3 animate-spin rounded-full border-2 border-[#22C55E] border-t-transparent" /> Lecture du document par l'IA…</p>}
              {file && !analyzing && <p className="mt-1 text-xs text-slate-500">📎 {file.name} — champs pré-remplis, vérifiez-les avant de comptabiliser.</p>}
            </div>
            <Input value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })} placeholder="Nom du fournisseur" data-testid="qc-bill-supplier" className="h-9" />
            <div className="grid grid-cols-2 gap-3">
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Date</label><Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="qc-bill-date" className="h-9" /></div>
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Échéance</label><Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} data-testid="qc-bill-due" className="h-9" /></div>
            </div>
            <div><label className="mb-1 block text-xs font-600 text-slate-500">N° facture (réf.)</label><Input value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} data-testid="qc-bill-ref" className="h-9" /></div>
            <LineItemsEditor items={form.items} setItems={(items) => setForm({ ...form, items })} accounts={accounts} defaultAccount="540210" testid="qc-bill-items" />
            <div className="rounded-lg bg-slate-50 px-3 py-2 text-sm" data-testid="qc-bill-totals">
              <div className="flex justify-between"><span>Montant HT</span><span className="font-mono-data">{money(amt)} $</span></div>
              <div className="flex justify-between text-slate-500"><span>T.P.S. + T.V.Q.</span><span className="font-mono-data">{money(tps + tvq)} $</span></div>
              <div className="mt-1 flex justify-between border-t border-slate-200 pt-1 font-700 text-[#0F172A]"><span>TOTAL</span><span className="font-mono-data">{money(total)} $</span></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDlg(false)}>Annuler</Button>
            <Button onClick={save} disabled={saving || amt <= 0 || !form.supplier.trim()} data-testid="qc-bill-save" className="bg-[#22C55E] hover:bg-[#22C55E]/90">{saving ? "…" : "Comptabiliser"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ===================== Bilan / États des résultats =====================
function StatementView({ year, kind }) {
  const [rep, setRep] = useState(null);
  const [drill, setDrill] = useState(null);
  const isBilan = kind === "bilan";
  useEffect(() => {
    if (!year) return;
    (isBilan ? api.qcBilan({ year }) : api.qcPnl({ year })).then(setRep).catch(() => setRep(null));
  }, [year, isBilan]);
  const dl = async () => {
    try {
      const b = await (isBilan ? api.qcBilanExcel({ year }) : api.qcPnlExcel({ year }));
      const url = URL.createObjectURL(b); const a = document.createElement("a");
      a.href = url; a.download = `${isBilan ? "bilan" : "resultats"}_9434_${year}.xlsx`; a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Export impossible"); }
  };
  if (!rep) return <div className="card p-8 text-center text-sm text-slate-400">Chargement…</div>;
  const cols = isBilan
    ? [["movement", "Exercice"], ["opening", "Antérieur"], ["cumulative", "Cumulatif"]]
    : [["cur", String(year)], ["prev", String(year - 1)]];
  const rowCls = (k) => {
    if (k === "title") return "bg-[#0F172A] text-white font-700";
    if (k === "total") return "border-t-2 border-[#0F172A] bg-slate-100 font-700";
    if (k === "subtotal") return "border-t border-slate-300 font-600";
    if (k === "header") return "font-600 text-[#22C55E]";
    if (k === "diff") return "text-xs text-slate-400";
    if (k === "qp") return "text-xs italic text-slate-500";
    return "";
  };
  return (
    <div className="space-y-3" data-testid={`qc-${kind}-view`}>
      <div className="flex items-center justify-between">
        {isBilan
          ? <span data-testid="qc-bilan-balanced" className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-600 ${rep.balanced ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>{rep.balanced ? <><CheckCircle2 size={13} /> Bilan équilibré</> : <><AlertTriangle size={13} /> Écart de bilan</>}</span>
          : <span className="text-sm font-600 text-[#0F172A]">Bénéfice net : {money(rep.net?.cur)} $</span>}
        <Button size="sm" variant="outline" onClick={dl} data-testid={`qc-${kind}-excel`} className="gap-2"><Download size={14} /> Excel</Button>
      </div>
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid={`qc-${kind}-table`}>
            <thead><tr className="bg-[#0F172A] text-left text-xs uppercase tracking-wide text-white">
              <th className="px-3 py-2 w-20">Compte</th><th className="px-3 py-2">Libellé</th>
              {cols.map(([k, lbl]) => <th key={k} className="px-3 py-2 text-right">{lbl}</th>)}
            </tr></thead>
            <tbody>
              {rep.lines.map((ln, i) => {
                const isText = ln.kind === "title" || ln.kind === "header";
                const clickable = ln.kind === "data" && ln.gl;
                return (
                  <tr key={i} className={`${rowCls(ln.kind)} ${clickable ? "cursor-pointer hover:bg-[#22C55E]/5" : ""}`} onClick={clickable ? () => setDrill(ln.gl) : undefined} data-testid={`qc-${kind}-line-${i}`} title={clickable ? "Voir le détail des écritures" : undefined}>
                    <td className={`px-3 py-1.5 font-mono-data text-xs ${clickable ? "text-[#22C55E] underline decoration-dotted" : ""}`}>{ln.gl || ""}</td>
                    <td className="px-3 py-1.5">{ln.label}</td>
                    {isText ? cols.map(([k]) => <td key={k}></td>)
                      : cols.map(([k]) => <td key={k} className={`px-3 py-1.5 text-right font-mono-data ${(ln[k] || 0) < 0 ? "text-red-600" : ""}`}>{ln[k] === undefined || ln[k] === null ? "" : money(ln[k])}</td>)}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
      {drill && <AccountDetailModal year={year} account={drill} scope={isBilan ? "cumulative" : "movement"} onClose={() => setDrill(null)} />}
    </div>
  );
}

// ===================== États Financiers (modèle Excel) =====================
function EtatsFinanciersView({ year }) {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [ef, setEf] = useState(null);
  const [sigDlg, setSigDlg] = useState(false);
  const [admins, setAdmins] = useState({ a1_name: "", a1_title: "Administrateur", a2_name: "", a2_title: "Administrateur" });
  const [savingSig, setSavingSig] = useState(false);
  const loadEf = useCallback(() => { if (year) api.qcEtatsFinanciers({ year }).then((d) => { setEf(d); if (d.admins) setAdmins(d.admins); }).catch(() => setEf(null)); }, [year]);
  useEffect(() => { loadEf(); }, [loadEf]);
  const saveSig = async () => {
    setSavingSig(true);
    try { await api.qcEfSettingsUpdate(admins); toast.success("Signataires mis à jour"); setSigDlg(false); loadEf(); }
    catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } finally { setSavingSig(false); }
  };
  const dl = async (fmt) => {
    try {
      const b = await (fmt === "pdf" ? api.qcEfPdf({ year }) : api.qcEfExcel({ year }));
      const url = URL.createObjectURL(b); const a = document.createElement("a");
      a.href = url; a.download = `etats_financiers_9434_${year}.${fmt === "pdf" ? "pdf" : "xlsx"}`; a.click(); URL.revokeObjectURL(url);
    } catch { toast.error("Export impossible"); }
  };
  if (!ef) return <div className="card p-8 text-center text-sm text-slate-400" data-testid="qc-ef-loading">Chargement…</div>;
  const balanced = Math.abs((ef.bilan.total_actif || 0) - (ef.bilan.total_pc || 0)) < 1;
  const R = ({ label, cur, prev, kind }) => {
    const cls = kind === "total" ? "border-t-2 border-[#0F172A] bg-slate-100 font-700"
      : kind === "subtotal" ? "border-t border-slate-300 font-600"
      : kind === "header" ? "font-600 text-[#22C55E]" : "";
    return (
      <tr className={cls}>
        <td className={`px-3 py-1.5 ${kind === "indent" ? "pl-6 text-slate-600" : ""}`}>{label}</td>
        <td className={`px-3 py-1.5 text-right font-mono-data ${(cur || 0) < 0 ? "text-red-600" : ""}`}>{cur === undefined ? "" : money(cur)}</td>
        {prev !== "none" && <td className={`px-3 py-1.5 text-right font-mono-data ${(prev || 0) < 0 ? "text-red-600" : ""}`}>{prev === undefined ? "" : money(prev)}</td>}
      </tr>
    );
  };
  const c = ef.cur, p = ef.prev, bn = ef.bnr, bl = ef.bilan, pb = ef.prev_bilan || {}, py = ef.prev_year || (year - 1);
  return (
    <div className="space-y-4" data-testid="qc-ef-view">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span data-testid="qc-ef-balanced" className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-600 ${balanced ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>{balanced ? <><CheckCircle2 size={13} /> Bilan équilibré</> : <><AlertTriangle size={13} /> Écart de bilan</>}</span>
        <div className="flex gap-2">
          {isAdmin && <Button size="sm" variant="outline" onClick={() => setSigDlg(true)} data-testid="qc-ef-sig-btn" className="gap-2"><Pencil size={14} /> Signataires</Button>}
          <Button size="sm" variant="outline" onClick={() => dl("pdf")} data-testid="qc-ef-pdf" className="gap-2"><FileDown size={14} /> PDF</Button>
          <Button size="sm" variant="outline" onClick={() => dl("xlsx")} data-testid="qc-ef-excel" className="gap-2"><Download size={14} /> Excel</Button>
        </div>
      </div>

      {/* État des résultats */}
      <div className="card overflow-hidden">
        <div className="border-b border-slate-100 bg-[#0F172A] px-4 py-2.5"><h3 className="font-display text-sm font-700 text-white">État des résultats et des bénéfices non répartis</h3><p className="text-[11px] text-slate-300">9434-3977 Québec Inc. · Exercice terminé le 31 décembre {year} · Non-audités · En dollars canadiens</p></div>
        <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-ef-resultats">
          <thead><tr className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-3 py-2">Poste</th><th className="px-3 py-2 text-right">{year}</th><th className="px-3 py-2 text-right">{py}</th>
          </tr></thead>
          <tbody className="divide-y divide-slate-50">
            <R label="Produits" kind="header" cur={undefined} prev={undefined} />
            <R label="Honoraires de gestion" kind="indent" cur={c.rev} prev={p.rev} />
            <R label="Charges" kind="header" cur={undefined} prev={undefined} />
            <R label="Services juridiques" kind="indent" cur={c.juridique} prev={p.juridique} />
            <R label="Services d'expertise comptable et financière" kind="indent" cur={c.expertise} prev={p.expertise} />
            <R label="Frais financiers" kind="indent" cur={c.financiers} prev={p.financiers} />
            <R label="" kind="subtotal" cur={c.charges} prev={p.charges} />
            <R label="Bénéfice (perte) avant quote-part et impôts sur les bénéfices" kind="subtotal" cur={c.avant_qp} prev={p.avant_qp} />
            <R label="Quote-part des résultats de la société en commandite" kind="indent" cur={c.qp} prev={p.qp} />
            <R label="Bénéfice (perte) avant impôts sur les bénéfices" kind="subtotal" cur={c.avant_impot} prev={p.avant_impot} />
            <R label="Impôts sur les bénéfices exigibles" kind="indent" cur={c.impots} prev={p.impots} />
            <R label="Bénéfice (perte) net(te) de l'exercice" kind="total" cur={c.net} prev={p.net} />
            <R label="Bénéfices non répartis au début de l'exercice" kind="indent" cur={bn.debut_cur} prev={bn.debut_prev} />
            <R label="Bénéfices non répartis à la fin de l'exercice" kind="total" cur={bn.fin_cur} prev={bn.fin_prev} />
          </tbody>
        </table></div>
      </div>

      {/* Bilan */}
      <div className="card overflow-hidden">
        <div className="border-b border-slate-100 bg-[#0F172A] px-4 py-2.5"><h3 className="font-display text-sm font-700 text-white">Bilan</h3><p className="text-[11px] text-slate-300">9434-3977 Québec Inc. · au 31 décembre {year} · Non-audités · En dollars canadiens</p></div>
        <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-ef-bilan">
          <thead><tr className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="px-3 py-2">Poste</th><th className="px-3 py-2 text-right">{year}</th><th className="px-3 py-2 text-right">{py}</th>
          </tr></thead>
          <tbody className="divide-y divide-slate-50">
            <R label="ACTIF" kind="header" />
            <R label="Actif à court terme" kind="header" cur={undefined} prev={undefined} />
            <R label="Trésorerie" kind="indent" cur={bl.treso} prev={pb.treso} />
            <R label="Clients - Société en commandite ACCS" kind="indent" cur={bl.clients} prev={pb.clients} />
            <R label="Sommes à recevoir de l'état - Taxes de ventes" kind="indent" cur={bl.taxes_rec} prev={pb.taxes_rec} />
            <R label="" kind="subtotal" cur={bl.total_ct} prev={pb.total_ct} />
            <R label="Placement – Société en commandite ACCS" kind="indent" cur={bl.placement} prev={pb.placement} />
            <R label="TOTAL DE L'ACTIF" kind="total" cur={bl.total_actif} prev={pb.total_actif} />
            <R label="PASSIF" kind="header" />
            <R label="Passif à court terme" kind="header" cur={undefined} prev={undefined} />
            <R label="Créditeurs et charges à payer aux apparentés" kind="indent" cur={bl.crediteurs} prev={pb.crediteurs} />
            <R label="Taxes de ventes à remettre" kind="indent" cur={bl.taxes_rem} prev={pb.taxes_rem} />
            <R label="Impôt à payer" kind="indent" cur={bl.impot_pay} prev={pb.impot_pay} />
            <R label="" kind="subtotal" cur={bl.total_passif} prev={pb.total_passif} />
            <R label="CAPITAUX PROPRES" kind="header" cur={undefined} prev={undefined} />
            <R label="Capital-actions" kind="indent" cur={bl.capital} prev={pb.capital} />
            <R label="Bénéfices non répartis" kind="indent" cur={bl.bnr} prev={pb.bnr} />
            <R label="TOTAL DU PASSIF ET DES CAPITAUX PROPRES" kind="total" cur={bl.total_pc} prev={pb.total_pc} />
          </tbody>
        </table></div>
        <div className="border-t border-slate-100 px-4 py-3">
          <p className="text-xs font-600 text-slate-500">Au nom du Conseil d'administration</p>
          <div className="mt-2 flex flex-wrap gap-8" data-testid="qc-ef-signatures">
            <div><p className="border-t border-slate-400 pt-1 text-sm font-700 text-[#0F172A]">{ef.admins?.a1_name || "—"}</p><p className="text-xs text-slate-400">{ef.admins?.a1_title || "Administrateur"}</p></div>
            <div><p className="border-t border-slate-400 pt-1 text-sm font-700 text-[#0F172A]">{ef.admins?.a2_name || "—"}</p><p className="text-xs text-slate-400">{ef.admins?.a2_title || "Administrateur"}</p></div>
          </div>
        </div>
      </div>

      <Dialog open={sigDlg} onOpenChange={setSigDlg}>
        <DialogContent data-testid="qc-ef-sig-dialog" className="max-w-md">
          <DialogHeader><DialogTitle>Signataires — Conseil d'administration</DialogTitle>
            <DialogDescription className="text-xs">Ces noms apparaissent au bas du Bilan (PDF et Excel). Modifiables avant l'envoi.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Administrateur 1</label><Input value={admins.a1_name} onChange={(e) => setAdmins({ ...admins, a1_name: e.target.value })} data-testid="qc-ef-a1-name" className="h-9" /></div>
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Titre</label><Input value={admins.a1_title} onChange={(e) => setAdmins({ ...admins, a1_title: e.target.value })} data-testid="qc-ef-a1-title" className="h-9" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Administrateur 2</label><Input value={admins.a2_name} onChange={(e) => setAdmins({ ...admins, a2_name: e.target.value })} data-testid="qc-ef-a2-name" className="h-9" /></div>
              <div><label className="mb-1 block text-xs font-600 text-slate-500">Titre</label><Input value={admins.a2_title} onChange={(e) => setAdmins({ ...admins, a2_title: e.target.value })} data-testid="qc-ef-a2-title" className="h-9" /></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSigDlg(false)}>Annuler</Button>
            <Button onClick={saveSig} disabled={savingSig} data-testid="qc-ef-sig-save" className="bg-[#22C55E] hover:bg-[#22C55E]/90">{savingSig ? "…" : "Enregistrer"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* États des flux de trésorerie */}
      {ef.cashflow && (() => {
        const cf = ef.cashflow; const cpf = cf.prev || {}; const cpd = cpf.wc_detail || {};
        return (
          <div className="card overflow-hidden" data-testid="qc-ef-cashflow">
            <div className="border-b border-slate-100 bg-[#0F172A] px-4 py-2.5"><h3 className="font-display text-sm font-700 text-white">États des flux de trésorerie</h3><p className="text-[11px] text-slate-300">9434-3977 Québec Inc. · Exercice terminé le 31 décembre {year} · Non-audités · En dollars canadiens · méthode indirecte</p></div>
            {!cf.reconciled && <div className="border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-xs font-600 text-amber-700">Note : léger écart de réconciliation (trésorerie au bilan {money(cf.bilan_cash)} $).</div>}
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-ef-cashflow-table">
              <thead><tr className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500"><th className="px-3 py-2">Poste</th><th className="px-3 py-2 text-right">{year}</th><th className="px-3 py-2 text-right">{py}</th></tr></thead>
              <tbody className="divide-y divide-slate-50">
                <R label="Activités d'exploitation" kind="header" cur={undefined} prev={undefined} />
                <R label="Bénéfice (perte) net(te) de l'exercice" kind="indent" cur={cf.net} prev={cpf.net} />
                <R label="Élément sans effet sur la trésorerie :" kind="indent" cur={undefined} prev={undefined} />
                <R label="Quote-part des résultats de la Société en commandite" kind="indent" cur={cf.qp_noncash} prev={cpf.qp_noncash} />
                <R label="Variation des éléments hors caisse du fonds de roulement" kind="indent" cur={cf.wc} prev={cpf.wc} />
                <R label="Flux liés aux activités d'exploitation" kind="subtotal" cur={cf.op_sub} prev={cpf.op_sub} />
                <R label="Activités de financement" kind="header" cur={undefined} prev={undefined} />
                <R label="Émission d'actions ordinaires" kind="indent" cur={cf.capital} prev={cpf.capital} />
                <R label="Activités d'investissement" kind="header" cur={undefined} prev={undefined} />
                <R label="Variation du placement – Société en commandite ACCS" kind="indent" cur={cf.placement} prev={cpf.placement} />
                <R label="Variation nette de la trésorerie au cours de l'exercice" kind="subtotal" cur={cf.net_var} prev={cpf.net_var} />
                <R label="Trésorerie au début de l'exercice" kind="indent" cur={cf.cash_open} prev={cpf.cash_open} />
                <R label="Trésorerie à la fin de l'exercice" kind="total" cur={cf.cash_close} prev={cpf.cash_close} />
              </tbody>
            </table></div>
            <div className="border-t border-slate-100 px-4 py-2"><p className="text-xs font-700 uppercase text-[#22C55E]">Informations supplémentaires — Variation des éléments hors caisse</p></div>
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-ef-cashflow-detail">
              <tbody className="divide-y divide-slate-50">
                <R label="Clients – Société en commandite ACCS" kind="indent" cur={cf.wc_detail.clients} prev={cpd.clients} />
                <R label="Sommes à recevoir de l'état - Taxes de ventes" kind="indent" cur={cf.wc_detail.taxes_rec} prev={cpd.taxes_rec} />
                <R label="Créditeurs et charges à payer aux apparentés" kind="indent" cur={cf.wc_detail.crediteurs} prev={cpd.crediteurs} />
                <R label="Taxes de ventes à remettre" kind="indent" cur={cf.wc_detail.taxes_rem} prev={cpd.taxes_rem} />
                <R label="Impôt à payer" kind="indent" cur={cf.wc_detail.impot} prev={cpd.impot} />
                <R label="Total" kind="subtotal" cur={cf.wc_detail.total} prev={cpd.total} />
              </tbody>
            </table></div>
          </div>
        );
      })()}
    </div>
  );
}

// ===================== Plan comptable =====================
function PlanComptableView({ canEdit }) {
  const [data, setData] = useState({ accounts: [], sections: {} });
  const [form, setForm] = useState({ gl: "", description: "", type: "actif", section: "actif_court" });
  const [editGl, setEditGl] = useState(null);
  const load = useCallback(() => api.qcAccounts().then(setData).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const sections = data.sections || {};
  const TYPES = [["actif", "Actif"], ["passif", "Passif"], ["capitaux", "Capitaux"], ["produit", "Produit"], ["charge", "Charge"]];
  const reset = () => { setForm({ gl: "", description: "", type: "actif", section: "actif_court" }); setEditGl(null); };
  const startEdit = (a) => { setEditGl(a.gl); setForm({ gl: a.gl, description: a.description, type: a.type, section: a.section }); };
  const save = async () => {
    if (!form.gl.trim()) { toast.error("N° de compte requis"); return; }
    try {
      if (editGl) await api.qcUpdateAccount(editGl, form);
      else await api.qcCreateAccount(form);
      toast.success("Enregistré"); reset(); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); }
  };
  const del = async (a) => { try { await api.qcDeleteAccount(a.gl); toast.success("Supprimé"); load(); } catch (e) { toast.error(e.response?.data?.detail || "Impossible"); } };

  return (
    <div className="space-y-3" data-testid="qc-accounts-view">
      <p className="text-sm text-slate-500">{data.accounts.length} compte(s) · plan comptable propre à cette entité</p>
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="qc-accounts-table">
            <thead><tr className="bg-[#0F172A] text-left text-xs uppercase tracking-wide text-white">
              <th className="px-3 py-2">GL</th><th className="px-3 py-2">Description</th><th className="px-3 py-2">Type</th><th className="px-3 py-2">Section de rapport</th><th className="px-3 py-2"></th>
            </tr></thead>
            <tbody className="divide-y divide-slate-100">
              {data.accounts.map((a) => (
                <tr key={a.gl} className="hover:bg-slate-50" data-testid={`qc-account-row-${a.gl}`}>
                  <td className="px-3 py-1.5 font-mono-data text-xs">{a.gl}</td>
                  <td className="px-3 py-1.5">{a.description}</td>
                  <td className="px-3 py-1.5 text-xs capitalize">{a.type}</td>
                  <td className="px-3 py-1.5 text-xs text-slate-500">{sections[a.section] || a.section}</td>
                  <td className="px-3 py-1.5">
                    {canEdit && (
                      <div className="flex justify-end gap-1">
                        <button onClick={() => startEdit(a)} data-testid={`qc-account-edit-${a.gl}`} className="rounded p-1.5 text-slate-500 hover:bg-slate-100"><Pencil size={14} /></button>
                        <button onClick={() => del(a)} data-testid={`qc-account-del-${a.gl}`} className="rounded p-1.5 text-red-500 hover:bg-red-50"><Trash2 size={14} /></button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {canEdit && (
        <div className="card space-y-3 p-4" data-testid="qc-account-form">
          <p className="text-xs font-700 text-[#0F172A]">{editGl ? `Modifier le compte ${editGl}` : "Nouveau compte"}</p>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <Input value={form.gl} disabled={!!editGl} onChange={(e) => setForm({ ...form, gl: e.target.value.replace(/\D/g, "") })} placeholder="N° GL" data-testid="qc-account-gl" className="h-9" />
            <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description" data-testid="qc-account-desc" className="h-9 sm:col-span-3" />
          </div>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs font-600 text-slate-500">Type</label>
              <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} data-testid="qc-account-type" className="h-9 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm focus:border-[#22C55E] focus:outline-none">
                {TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-600 text-slate-500">Section de rapport</label>
              <select value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} data-testid="qc-account-section" className="h-9 w-full rounded-lg border border-slate-300 bg-white px-3 text-sm focus:border-[#22C55E] focus:outline-none">
                {Object.entries(sections).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={save} data-testid="qc-account-save" className="bg-[#22C55E] hover:bg-[#22C55E]/90">Enregistrer</Button>
            {editGl && <Button size="sm" variant="outline" onClick={reset}>Annuler</Button>}
          </div>
        </div>
      )}
    </div>
  );
}


// ===================== Envoi externe (contacts propres) =====================
function QcExtPreviewDialog({ open, onOpenChange, reportKey, label, year, onDownload }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const family = !reportKey ? null
    : reportKey.startsWith("etats_financiers") ? "ef"
    : reportKey.startsWith("bilan") ? "bilan"
    : reportKey.startsWith("pnl") ? "pnl" : "tb";
  useEffect(() => {
    if (!open || !reportKey || !year) return;
    setLoading(true); setData(null);
    const fetcher = family === "ef" ? api.qcEtatsFinanciers({ year })
      : family === "bilan" ? api.qcBilan({ year })
      : family === "pnl" ? api.qcPnl({ year })
      : api.qcTrialBalance({ year });
    fetcher.then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [open, reportKey, year, family]);

  const lineCls = (k) => k === "title" ? "bg-[#0F172A] text-white font-700"
    : k === "total" ? "border-t-2 border-[#0F172A] bg-slate-100 font-700"
    : k === "subtotal" ? "border-t border-slate-300 font-600"
    : k === "header" ? "font-600 text-[#22C55E]" : "";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="qc-ext-preview-dialog" className="max-h-[88vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Eye size={16} className="text-[#22C55E]" /> Aperçu — {label}</DialogTitle>
          <DialogDescription className="text-xs">Exercice {year} · Aperçu du document qui sera transmis au contact.</DialogDescription>
        </DialogHeader>
        {loading ? <p className="py-8 text-center text-sm text-slate-400">Chargement…</p>
          : !data ? <p className="py-8 text-center text-sm text-slate-400" data-testid="qc-ext-preview-empty">Aperçu indisponible.</p>
          : family === "tb" ? (
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-ext-preview-tb">
              <thead><tr className="bg-[#0F172A] text-left text-xs uppercase text-white"><th className="px-3 py-2">Compte</th><th className="px-3 py-2">Libellé</th><th className="px-3 py-2 text-right">Débit</th><th className="px-3 py-2 text-right">Crédit</th></tr></thead>
              <tbody className="divide-y divide-slate-50">
                {(data.rows || []).map((r, i) => (
                  <tr key={i}><td className="px-3 py-1.5 font-mono-data text-xs">{r.account}</td><td className="px-3 py-1.5">{r.account_name}</td><td className="px-3 py-1.5 text-right font-mono-data">{r.debit ? money(r.debit) : "—"}</td><td className="px-3 py-1.5 text-right font-mono-data">{r.credit ? money(r.credit) : "—"}</td></tr>
                ))}
              </tbody>
              <tfoot><tr className="border-t-2 border-[#0F172A] bg-slate-100 font-700"><td className="px-3 py-2" colSpan={2}>TOTAL</td><td className="px-3 py-2 text-right font-mono-data">{money(data.total_debit)}</td><td className="px-3 py-2 text-right font-mono-data">{money(data.total_credit)}</td></tr></tfoot>
            </table></div>
          ) : family === "ef" ? <EfPreview ef={data} year={year} />
          : (
            <div className="overflow-x-auto"><table className="w-full text-sm" data-testid="qc-ext-preview-lines">
              <tbody>
                {(data.lines || []).map((ln, i) => {
                  const isText = ln.kind === "title" || ln.kind === "header";
                  const cols = family === "bilan" ? ["cumulative"] : ["cur"];
                  return (
                    <tr key={i} className={lineCls(ln.kind)}>
                      <td className="px-3 py-1.5 font-mono-data text-xs">{ln.gl || ""}</td>
                      <td className="px-3 py-1.5">{ln.label}</td>
                      {isText ? <td></td> : cols.map((k) => <td key={k} className={`px-3 py-1.5 text-right font-mono-data ${(ln[k] || 0) < 0 ? "text-red-600" : ""}`}>{ln[k] === undefined || ln[k] === null ? "" : money(ln[k])}</td>)}
                    </tr>
                  );
                })}
              </tbody>
            </table></div>
          )}
        <DialogFooter>
          {reportKey && <Button variant="outline" onClick={() => onDownload(reportKey)} className="gap-2"><Download size={14} /> Télécharger</Button>}
          <Button onClick={() => onOpenChange(false)} className="bg-[#22C55E] hover:bg-[#22C55E]/90">Fermer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function EfPreview({ ef, year }) {
  const c = ef.cur, p = ef.prev, bl = ef.bilan, bn = ef.bnr;
  const Row = ({ l, a, b, bold }) => <tr className={bold ? "border-t border-slate-300 font-700" : ""}><td className="px-3 py-1.5">{l}</td><td className="px-3 py-1.5 text-right font-mono-data">{money(a)}</td>{b !== undefined && <td className="px-3 py-1.5 text-right font-mono-data">{money(b)}</td>}</tr>;
  return (
    <div className="space-y-4" data-testid="qc-ext-preview-ef">
      <div className="overflow-x-auto">
        <p className="mb-1 text-xs font-700 uppercase text-[#22C55E]">État des résultats</p>
        <table className="w-full text-sm"><thead><tr className="bg-slate-50 text-xs uppercase text-slate-500"><th className="px-3 py-1.5 text-left">Poste</th><th className="px-3 py-1.5 text-right">{year}</th><th className="px-3 py-1.5 text-right">{year - 1}</th></tr></thead>
          <tbody className="divide-y divide-slate-50">
            <Row l="Produits" a={c.rev} b={p.rev} />
            <Row l="Total des charges" a={c.charges} b={p.charges} />
            <Row l="Quote-part" a={c.qp} b={p.qp} />
            <Row l="Impôts" a={c.impots} b={p.impots} />
            <Row l="Bénéfice net" a={c.net} b={p.net} bold />
            <Row l="BNR à la fin" a={bn.fin_cur} b={bn.fin_prev} bold />
          </tbody></table>
      </div>
      <div className="overflow-x-auto">
        <p className="mb-1 text-xs font-700 uppercase text-[#22C55E]">Bilan</p>
        <table className="w-full text-sm"><tbody className="divide-y divide-slate-50">
          <Row l="Total de l'actif" a={bl.total_actif} bold />
          <Row l="Total du passif" a={bl.total_passif} />
          <Row l="Capital-actions" a={bl.capital} />
          <Row l="Bénéfices non répartis" a={bl.bnr} />
          <Row l="Total du passif et de l'avoir" a={bl.total_pc} bold />
        </tbody></table>
      </div>
    </div>
  );
}

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
  const [preview, setPreview] = useState(null);

  const load = useCallback(() => api.qcExternalContacts().then((r) => setContacts(r || [])), []);
  const loadHistory = useCallback(() => { if (cid) api.qcExternalEmailLog({ contact_id: cid }).then((r) => setHistory(r || [])).catch(() => setHistory([])); else setHistory([]); }, [cid]);
  useEffect(() => { load(); api.qcExternalCatalog().then(setCatalog).catch(() => {}); api.acctEmailStatus().then(setEmailCfg).catch(() => {}); }, [load]);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  useEffect(() => { if (!year && years.length) setYear(years[0].year); }, [years, year]);

  const contact = contacts.find((c) => c.id === cid);
  const labelOf = (k) => (catalog.find((c) => c.key === k) || {}).label || k;
  const fmtOf = (k) => (catalog.find((c) => c.key === k) || {}).fmt || "xlsx";
  const ls = contact?.last_sent;
  const fmt = (iso) => fmtSent(iso);

  const download = async (key) => {
    try { const b = await api.qcExternalReport({ key, year }); const url = URL.createObjectURL(b); const a = document.createElement("a"); a.href = url; a.download = `${key}_9434_${year}.${fmtOf(key)}`; a.click(); URL.revokeObjectURL(url); toast.success("Téléchargé"); }
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
              className="h-9 min-w-[220px] rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 focus:border-[#22C55E] focus:outline-none">
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
          {cid && contact && <Button size="sm" onClick={sendAll} disabled={busy || !emailCfg.configured} title={emailCfg.configured ? `Envoyer à ${contact.email || "(aucun courriel)"}` : "Service d'email non configuré"} data-testid="qc-external-email" className="gap-2 bg-[#22C55E] hover:bg-[#22C55E]/90"><Send size={15} /> {busy ? "…" : "Envoyer le package"}</Button>}
          {cid && <Button size="sm" variant="outline" onClick={() => setHistOpen(true)} data-testid="qc-external-history-btn" className="gap-2"><Clock size={15} /> Historique{history.length ? ` (${history.length})` : ""}</Button>}
          {isAdmin && <Button size="sm" variant="outline" onClick={() => setManageOpen(true)} data-testid="qc-external-manage" className="gap-2"><Settings2 size={15} /> Gérer les contacts</Button>}
        </div>
      </div>

      <p className="text-xs text-slate-400">Astuce : cliquez sur une ligne de rapport pour <strong>prévisualiser</strong> le document qui sera envoyé à ce contact.</p>

      {!cid ? <p className="p-6 text-center text-sm text-slate-400">Sélectionnez un contact externe pour préparer son package.</p>
        : (
          <div className="card overflow-hidden" data-testid="qc-external-package">
            <div className="border-b border-slate-100 px-5 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h3 className="font-display text-base font-700 text-[#0F172A]">Package — {contact.name}</h3>
                {ls
                  ? <span data-testid="qc-external-last-sent" className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-600 text-emerald-700"><CheckCircle2 size={13} /> Dernier envoi : {fmt(ls.sent_at)} · {ls.year} · {ls.doc_count || 0} doc(s)</span>
                  : <span data-testid="qc-external-last-sent" className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-600 text-slate-500"><Clock size={13} /> Aucun envoi enregistré</span>}
              </div>
              <p className="mt-0.5 text-xs text-slate-400">Exercice {year || "—"} · {contact.email || "aucun courriel"} · {contact.report_types?.length || 0} document(s)</p>
            </div>
            <div className="divide-y divide-slate-50">
              {(contact.report_types || []).map((key) => (
                <div key={key} onClick={() => setPreview({ key, label: labelOf(key) })} title="Cliquer pour prévisualiser" className="flex cursor-pointer items-center justify-between gap-3 px-5 py-3 hover:bg-[#22C55E]/5" data-testid={`qc-external-report-${key}`}>
                  <p className="flex items-center gap-2 text-sm font-600 text-slate-700"><Eye size={14} className="text-[#22C55E]" /> {labelOf(key)}</p>
                  <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                    <Button size="sm" variant="ghost" onClick={() => setPreview({ key, label: labelOf(key) })} data-testid={`qc-external-preview-${key}`} className="gap-1.5 text-[#22C55E] hover:bg-[#22C55E]/10"><Eye size={14} /> Aperçu</Button>
                    <Button size="sm" variant="outline" onClick={() => download(key)} data-testid={`qc-external-download-${key}`} className="gap-1.5"><Download size={14} /> {fmtOf(key) === "pdf" ? "PDF" : "Excel"}</Button>
                    <span className="text-xs font-600 text-emerald-600">Prêt</span>
                  </div>
                </div>
              ))}
              {(contact.report_types || []).length === 0 && <p className="p-6 text-center text-sm text-slate-400">Aucun document sélectionné pour ce contact (voir « Gérer les contacts »).</p>}
            </div>
          </div>
        )}

      <QcExtPreviewDialog open={!!preview} onOpenChange={(v) => !v && setPreview(null)} reportKey={preview?.key} label={preview?.label} year={year} onDownload={download} />

      {isAdmin && <QcContactsDialog open={manageOpen} onOpenChange={setManageOpen} contacts={contacts} catalog={catalog} onChanged={load} />}

      <Dialog open={histOpen} onOpenChange={setHistOpen}>
        <DialogContent data-testid="qc-external-history-dialog" className="max-h-[85vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><Clock size={16} className="text-[#22C55E]" /> Historique des envois — {contact?.name || ""}</DialogTitle>
            <DialogDescription className="text-xs">Journal des documents financiers transmis à ce contact.</DialogDescription>
          </DialogHeader>
          {history.length === 0
            ? <p className="py-8 text-center text-sm text-slate-400">Aucun envoi enregistré pour ce contact.</p>
            : <div className="space-y-2">
                {history.map((h, i) => (
                  <div key={i} className="rounded-lg border border-slate-200 px-3 py-2.5">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-600 text-[#0F172A]">Exercice {h.year}</span>
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
        <div className="space-y-3 rounded-lg border border-[#22C55E]/30 bg-[#22C55E]/5 p-3" data-testid="qc-contact-form">
          <p className="text-xs font-700 text-[#0F172A]">{editId ? "Modifier le contact" : "Nouveau contact"}</p>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Nom du contact" data-testid="qc-contact-name" className="h-9" />
          <Input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="Courriel" data-testid="qc-contact-email" className="h-9" />
          <div>
            <p className="mb-1 text-xs font-600 text-slate-500">Documents à envoyer</p>
            <div className="flex flex-wrap gap-2">
              {catalog.map((c) => (
                <label key={c.key} className="flex cursor-pointer items-center gap-2 rounded-md border border-slate-200 px-2 py-1.5 text-sm text-slate-700 hover:border-[#22C55E]" data-testid={`qc-contact-type-${c.key}`}>
                  <input type="checkbox" checked={form.report_types.includes(c.key)} onChange={() => toggleType(c.key)} /> {c.label}
                </label>
              ))}
            </div>
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={save} data-testid="qc-contact-save" className="bg-[#22C55E] hover:bg-[#22C55E]/90">Enregistrer</Button>
            {editId && <Button size="sm" variant="outline" onClick={reset}>Annuler</Button>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
