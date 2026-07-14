import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import {
  Upload, FileSpreadsheet, Lock, Unlock, CheckCircle2, AlertTriangle, Clock, FileText, Layers, Construction, Info,
} from "lucide-react";

const MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];

function money(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  const abs = Math.abs(n).toLocaleString("fr-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${abs})` : abs;
}

function usePeriods() {
  const [periods, setPeriods] = useState([]);
  const reload = useCallback(() => api.acctPeriods().then(setPeriods).catch(() => {}), []);
  useEffect(() => { reload(); }, [reload]);
  return { periods, reload };
}

function PeriodPicker({ periods, value, onChange }) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger data-testid="acct-period-picker" className="w-56"><SelectValue placeholder="Choisir une période" /></SelectTrigger>
      <SelectContent>
        {periods.length === 0 && <SelectItem value="none" disabled>Aucune période</SelectItem>}
        {periods.map((p) => (
          <SelectItem key={p.id} value={p.id} data-testid={`acct-period-opt-${p.id}`}>
            {MONTHS[p.month - 1]} {p.year} {p.locked ? "🔒" : ""}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// ---------- Dashboard ----------
export function AcctDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { api.acctDashboard().then(setD).catch(() => {}); }, []);
  if (!d) return <p className="text-sm text-slate-500">Chargement…</p>;
  const L = d.latest;
  return (
    <div className="space-y-5" data-testid="acct-dashboard">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="card p-5">
          <div className="mb-1 flex items-center gap-2 text-slate-500"><FileSpreadsheet size={16} /><span className="text-xs font-600 uppercase tracking-wider">Modèle</span></div>
          <p className="text-2xl font-800">{d.template_imported ? `${d.template_accounts} comptes` : "Non importé"}</p>
          <p className="text-xs text-slate-400">{d.template_imported ? "Mapping actif" : "Un admin doit importer le modèle"}</p>
        </div>
        <div className="card p-5">
          <div className="mb-1 flex items-center gap-2 text-slate-500"><Layers size={16} /><span className="text-xs font-600 uppercase tracking-wider">Périodes</span></div>
          <p className="text-2xl font-800">{d.period_count}</p>
          <p className="text-xs text-slate-400">mois avec données</p>
        </div>
        <div className="card p-5">
          <div className="mb-1 flex items-center gap-2 text-slate-500"><Clock size={16} /><span className="text-xs font-600 uppercase tracking-wider">Dernier mois</span></div>
          <p className="text-2xl font-800">{L ? `${MONTHS[L.month - 1]} ${L.year}` : "—"}</p>
          <p className="text-xs text-slate-400">{L?.last_upload_by ? `par ${L.last_upload_by}` : "aucun upload"}</p>
        </div>
      </div>
      {L && (
        <div className="card p-5" data-testid="acct-dashboard-latest">
          <h3 className="mb-4 text-sm font-700">Statut — {MONTHS[L.month - 1]} {L.year}</h3>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className={`rounded-xl border p-4 ${L.locked ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"}`}>
              <div className="flex items-center gap-2">{L.locked ? <Lock size={16} className="text-red-600" /> : <Unlock size={16} className="text-amber-600" />}
                <span className="text-sm font-700">{L.locked ? "Verrouillé" : "Non verrouillé"}</span></div>
              <p className="mt-1 text-xs text-slate-500">{L.locked ? "Données finales" : "Données provisoires"}</p>
            </div>
            <div className={`rounded-xl border p-4 ${L.balanced ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
              <div className="flex items-center gap-2">{L.balanced ? <CheckCircle2 size={16} className="text-emerald-600" /> : <AlertTriangle size={16} className="text-red-600" />}
                <span className="text-sm font-700">{L.balanced ? "Balancé" : "Déséquilibre"}</span></div>
              <p className="mt-1 text-xs text-slate-500">Écart bilan : {money(L.diff)}</p>
            </div>
            <div className="rounded-xl border border-slate-200 p-4">
              <div className="flex items-center gap-2"><Info size={16} className="text-slate-500" /><span className="text-sm font-700">{L.new_accounts} nouveau(x) compte(s)</span></div>
              <p className="mt-1 text-xs text-slate-500">détectés au dernier upload</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------- Balance de vérification ----------
export function AcctBV() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { periods, reload } = usePeriods();
  const [tmpl, setTmpl] = useState(null);
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [newAcct, setNewAcct] = useState({ open: false, list: [] });
  const loadTmpl = useCallback(() => api.acctGetTemplate().then(setTmpl).catch(() => {}), []);
  useEffect(() => { loadTmpl(); }, [loadTmpl]);

  const onTemplate = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    setBusy(true);
    try { const r = await api.acctUploadTemplate(f); toast.success(`Modèle importé — ${r.account_count} comptes`); loadTmpl(); }
    catch (err) { toast.error(err.response?.data?.detail || "Import impossible"); } finally { setBusy(false); }
  };
  const onBV = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    setBusy(true);
    try {
      const r = await api.acctUploadBV(f, { year, month });
      setResult(r);
      if (r.new_accounts?.length) setNewAcct({ open: true, list: r.new_accounts });
      if (r.balanced === false) toast.warning(`BV chargée mais déséquilibre (écart ${money(r.diff)})`);
      else toast.success(`BV ${MONTHS[month - 1]} ${year} chargée${r.balanced ? " — balancée" : ""}`);
      reload();
    } catch (err) { toast.error(err.response?.data?.detail || "Upload impossible"); } finally { setBusy(false); }
  };
  const toggleLock = async (p) => {
    try { await api.acctLock({ year: p.year, month: p.month, locked: !p.locked }); toast.success(!p.locked ? "Mois verrouillé" : "Mois déverrouillé"); reload(); }
    catch (err) { toast.error(err.response?.data?.detail || "Action impossible"); }
  };

  return (
    <div className="space-y-5" data-testid="acct-bv-page">
      {isAdmin && (
        <div className="card p-5">
          <h3 className="mb-1 text-sm font-700">Modèle Bilan / États des résultats</h3>
          <p className="mb-3 text-xs text-slate-500">{tmpl?.imported ? `Importé — ${tmpl.account_count} comptes mappés (par ${tmpl.imported_by})` : "Aucun modèle importé. Importez le modèle Excel avec les formules pour extraire le mapping des comptes."}</p>
          <label className="inline-flex">
            <input type="file" accept=".xlsx" className="hidden" onChange={onTemplate} data-testid="acct-template-input" />
            <span className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-600 hover:bg-slate-50"><Upload size={15} /> {tmpl?.imported ? "Remplacer le modèle" : "Importer le modèle"}</span>
          </label>
        </div>
      )}

      <div className="card p-5">
        <h3 className="mb-3 text-sm font-700">Uploader une balance de vérification</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="block text-xs font-600 text-slate-500">Mois</label>
            <Select value={String(month)} onValueChange={(v) => setMonth(Number(v))}>
              <SelectTrigger data-testid="acct-bv-month" className="mt-1 w-40"><SelectValue /></SelectTrigger>
              <SelectContent>{MONTHS.map((m, i) => <SelectItem key={i} value={String(i + 1)}>{m}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><label className="block text-xs font-600 text-slate-500">Année</label>
            <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
              <SelectTrigger data-testid="acct-bv-year" className="mt-1 w-32"><SelectValue /></SelectTrigger>
              <SelectContent>{[now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1].map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <label className="inline-flex">
            <input type="file" accept=".xlsx" className="hidden" onChange={onBV} disabled={busy} data-testid="acct-bv-input" />
            <span className={`inline-flex cursor-pointer items-center gap-2 rounded-lg bg-[#2563EB] px-4 py-2 text-sm font-600 text-white hover:bg-[#2563EB]/90 ${busy ? "opacity-60" : ""}`}><Upload size={15} /> {busy ? "Traitement…" : "Uploader la BV (.xlsx)"}</span>
          </label>
        </div>
        {result && (
          <div className="mt-4 flex flex-wrap gap-3 text-sm" data-testid="acct-bv-result">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-600 ${result.balanced ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
              {result.balanced ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}{result.balanced ? "Balancée" : "Déséquilibre"} · écart {money(result.diff)}</span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 font-600 text-slate-600">{result.account_count} comptes</span>
            {result.new_accounts?.length > 0 && <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 font-600 text-amber-700"><Info size={14} /> {result.new_accounts.length} nouveau(x) compte(s)</span>}
            {!result.template_imported && <span className="text-amber-600">⚠ Aucun modèle importé — validation partielle</span>}
          </div>
        )}
      </div>

      <div className="card overflow-hidden">
        <div className="border-b border-slate-200 px-5 py-3"><h3 className="text-sm font-700">Périodes</h3></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
              <th className="px-5 py-2.5 text-left font-600">Mois</th><th className="px-5 py-2.5 text-left font-600">Statut</th>
              <th className="px-5 py-2.5 text-right font-600">Comptes</th><th className="px-5 py-2.5 text-right font-600">Écart bilan</th>
              <th className="px-5 py-2.5 text-left font-600">Dernier upload</th><th className="px-5 py-2.5 text-right font-600">Action</th>
            </tr></thead>
            <tbody>
              {periods.length === 0 && <tr><td colSpan={6} className="px-5 py-8 text-center text-slate-400">Aucune période.</td></tr>}
              {periods.map((p) => (
                <tr key={p.id} className="border-b border-slate-100" data-testid={`acct-period-row-${p.id}`}>
                  <td className="px-5 py-2.5 font-600">{MONTHS[p.month - 1]} {p.year}</td>
                  <td className="px-5 py-2.5">
                    {p.locked ? <span className="inline-flex items-center gap-1 text-red-600"><Lock size={13} /> Verrouillé</span>
                      : <span className="inline-flex items-center gap-1 text-amber-600"><Unlock size={13} /> Provisoire</span>}
                  </td>
                  <td className="px-5 py-2.5 text-right font-mono-data">{p.account_count ?? "—"}</td>
                  <td className="px-5 py-2.5 text-right font-mono-data" style={{ color: p.balanced ? "#0E9488" : "#DC2626" }}>{money(p.diff)}</td>
                  <td className="px-5 py-2.5 text-xs text-slate-500">{p.last_upload_at ? new Date(p.last_upload_at).toLocaleString("fr-CA") : "—"}</td>
                  <td className="px-5 py-2.5 text-right">
                    {isAdmin ? (
                      <Button size="sm" variant="outline" data-testid={`acct-lock-${p.id}`} onClick={() => toggleLock(p)}
                        className={`gap-1 ${p.locked ? "border-emerald-200 text-emerald-700" : "border-red-200 text-red-600"}`}>
                        {p.locked ? <><Unlock size={13} /> Déverrouiller</> : <><Lock size={13} /> Verrouiller</>}
                      </Button>
                    ) : <span className="text-xs text-slate-400">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <Dialog open={newAcct.open} onOpenChange={(v) => setNewAcct((s) => ({ ...s, open: v }))}>
        <DialogContent data-testid="acct-newacct-dialog">
          <DialogHeader>
            <DialogTitle>Nouveaux comptes détectés</DialogTitle>
            <DialogDescription>Ces comptes sont présents dans la BV mais absents du modèle. Ils apparaîtront dans les rapports une fois catégorisés (catégorisation détaillée à venir dans une prochaine phase).</DialogDescription>
          </DialogHeader>
          <div className="max-h-72 overflow-y-auto rounded-lg border border-slate-200 text-sm" data-testid="acct-newacct-list">
            {newAcct.list.map((a) => (
              <div key={a.account} className="flex items-center justify-between border-b border-slate-100 px-3 py-2 last:border-0">
                <span className="font-mono-data text-slate-500">{a.account}</span><span className="flex-1 px-3 text-slate-700">{a.name}</span>
              </div>
            ))}
          </div>
          <DialogFooter><Button data-testid="acct-newacct-ok" onClick={() => setNewAcct({ open: false, list: [] })}>Compris</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------- Rapport (Bilan / P&L) ----------
function ReportView({ type, title }) {
  const { periods } = usePeriods();
  const [period, setPeriod] = useState("");
  const [rep, setRep] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => { if (!period && periods.length) setPeriod(periods[0].id); }, [periods, period]);
  useEffect(() => {
    if (!period) return;
    const [y, m] = period.split("-").map(Number);
    setLoading(true); setRep(null);
    api.acctReport({ type, year: y, month: m }).then(setRep).catch((e) => toast.error(e.response?.data?.detail || "Rapport indisponible")).finally(() => setLoading(false));
  }, [period, type]);

  const exportExcel = async () => {
    const [y, m] = period.split("-").map(Number);
    try {
      const blob = await api.acctReportExcel({ type, year: y, month: m });
      const url = URL.createObjectURL(blob); const a = document.createElement("a");
      a.href = url; a.download = `${type === "bilan" ? "bilan" : "resultats"}_${period}.xlsx`; a.click(); URL.revokeObjectURL(url);
      toast.success("Export téléchargé");
    } catch (e) { toast.error(e.response?.data?.detail || "Export impossible"); }
  };
  const colLabel = { mois: rep ? `${rep.month_label} ${rep.year}` : "Mois", cumulatif: "Cumulatif" };

  return (
    <div className="space-y-4" data-testid={`acct-report-${type}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PeriodPicker periods={periods} value={period} onChange={setPeriod} />
        <Button size="sm" onClick={exportExcel} disabled={!rep} data-testid="acct-export-excel" className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><FileSpreadsheet size={15} /> Excel</Button>
      </div>
      {rep && !rep.locked && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-600 text-amber-700" data-testid="acct-provisional-banner">
          <AlertTriangle size={16} /> Données provisoires — ce mois n'est pas verrouillé.
        </div>
      )}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="text-sm font-700">{title}{rep ? ` — ${rep.month_label} ${rep.year}` : ""}</h3>
          {rep && <span className={`inline-flex items-center gap-1 text-xs font-600 ${rep.balanced ? "text-emerald-600" : "text-red-600"}`}>{rep.balanced ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}{rep.balanced ? "Balancé" : "Déséquilibre"}</span>}
        </div>
        {loading ? <p className="px-5 py-8 text-sm text-slate-500">Chargement…</p> : !rep ? <p className="px-5 py-8 text-sm text-slate-400">Sélectionnez une période avec une BV chargée.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
                <th className="px-5 py-2.5 text-left font-600">Compte</th>
                <th className="px-5 py-2.5 text-left font-600">Description</th>
                {rep.value_cols.map((k) => <th key={k} className="px-5 py-2.5 text-right font-600">{colLabel[k] || k}</th>)}
              </tr></thead>
              <tbody className="font-mono-data">
                {rep.lines.map((ln) => (
                  <tr key={ln.row} data-testid={`acct-line-${ln.row}`}
                    className={`border-b border-slate-50 ${ln.kind === "total" ? "bg-slate-50 font-700" : ln.kind === "header" ? "font-700 text-slate-800" : ""}`}>
                    <td className="px-5 py-1.5 text-left text-slate-400">{ln.account || ""}</td>
                    <td className={`px-5 py-1.5 text-left ${ln.kind === "data" ? "font-sans text-slate-600" : "font-sans"}`}>{ln.label}</td>
                    {rep.value_cols.map((k) => (
                      <td key={k} className="px-5 py-1.5 text-right" style={{ color: ln.values[k] < 0 ? "#DC2626" : undefined }}>{ln.kind === "header" ? "" : money(ln.values[k])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

export function AcctBilan() { return <ReportView type="bilan" title="Bilan" />; }
export function AcctPnl() { return <ReportView type="pnl" title="État des résultats" />; }

export function AcctComingSoon({ label }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 p-16 text-center" data-testid="acct-coming-soon">
      <Construction size={40} className="text-slate-300" />
      <h3 className="text-lg font-700">{label}</h3>
      <p className="max-w-md text-sm text-slate-500">Fonctionnalité à venir. Ce module sera développé dans une phase ultérieure.</p>
    </div>
  );
}

export function AcctCashflow() { return <AcctComingSoon label="Flux de trésorerie" />; }
export function AcctAudit() { return <AcctComingSoon label="Rapports d'audit" />; }
