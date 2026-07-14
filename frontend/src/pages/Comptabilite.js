import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid, Cell } from "recharts";
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
  const { periods } = usePeriods();
  const [period, setPeriod] = useState("");
  const [summary, setSummary] = useState(null);
  useEffect(() => { api.acctDashboard().then(setD).catch(() => {}); }, []);
  useEffect(() => { if (!period && periods.length) setPeriod(periods[0].id); }, [periods, period]);
  useEffect(() => {
    if (!period) { setSummary(null); return; }
    const [y, m] = period.split("-").map(Number);
    api.acctSummary({ year: y, month: m }).then(setSummary).catch(() => setSummary(null));
  }, [period]);
  if (!d) return <p className="text-sm text-slate-500">Chargement…</p>;
  const sel = periods.find((p) => p.id === period);
  const newCount = Array.isArray(sel?.new_accounts) ? sel.new_accounts.length : (sel?.new_accounts ?? 0);
  const chartData = summary?.categories?.map((c) => ({
    name: c.label, "Réel": c.values.reel, "Budget CA": c.values.bud_ca, "Budget Rév-1": c.values.bud_rev1,
  })) || [];
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
          <p className="text-2xl font-800">{d.latest ? `${MONTHS[d.latest.month - 1]} ${d.latest.year}` : "—"}</p>
          <p className="text-xs text-slate-400">{d.latest?.last_upload_by ? `par ${d.latest.last_upload_by}` : "aucun upload"}</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-600 text-slate-500">Période affichée :</span>
        <PeriodPicker periods={periods} value={period} onChange={setPeriod} />
      </div>

      {sel ? (
        <div className="card p-5" data-testid="acct-dashboard-latest">
          <h3 className="mb-4 text-sm font-700">Statut — {MONTHS[sel.month - 1]} {sel.year}</h3>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className={`rounded-xl border p-4 ${sel.locked ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"}`}>
              <div className="flex items-center gap-2">{sel.locked ? <Lock size={16} className="text-red-600" /> : <Unlock size={16} className="text-amber-600" />}
                <span className="text-sm font-700">{sel.locked ? "Verrouillé" : "Non verrouillé"}</span></div>
              <p className="mt-1 text-xs text-slate-500">{sel.locked ? "Données finales" : "Données provisoires"}</p>
            </div>
            <div className={`rounded-xl border p-4 ${sel.balanced ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
              <div className="flex items-center gap-2">{sel.balanced ? <CheckCircle2 size={16} className="text-emerald-600" /> : <AlertTriangle size={16} className="text-red-600" />}
                <span className="text-sm font-700">{sel.balanced ? "Balancé" : "Déséquilibre"}</span></div>
              <p className="mt-1 text-xs text-slate-500">Écart bilan : {money(sel.diff)}</p>
            </div>
            <div className="rounded-xl border border-slate-200 p-4">
              <div className="flex items-center gap-2"><Info size={16} className="text-slate-500" /><span className="text-sm font-700">{newCount} nouveau(x) compte(s)</span></div>
              <p className="mt-1 text-xs text-slate-500">non affecté(s) à cet upload</p>
            </div>
          </div>
        </div>
      ) : <p className="text-sm text-slate-400">Aucune période — uploadez une balance de vérification.</p>}

      {chartData.length > 0 && (
        <div className="card p-5" data-testid="acct-dashboard-chart">
          <h3 className="mb-1 text-sm font-700">Réel vs Budget — {summary.month_label} {summary.year}</h3>
          <p className="mb-4 text-xs text-slate-400">Revenus, dépenses et bénéfice net du mois comparés aux budgets.</p>
          <div style={{ width: "100%", height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toLocaleString("fr-CA")} k`} width={70} />
                <Tooltip formatter={(v) => money(v)} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Réel" fill="#2563EB" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Budget CA" fill="#0E9488" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Budget Rév-1" fill="#F59E0B" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
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
  const [accts, setAccts] = useState([]);
  const [assign, setAssign] = useState({});
  const loadTmpl = useCallback(() => api.acctGetTemplate().then(setTmpl).catch(() => {}), []);
  useEffect(() => { loadTmpl(); api.acctAccounts().then(setAccts).catch(() => {}); }, [loadTmpl]);

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
      if (r.new_accounts?.length) { setAssign({}); setNewAcct({ open: true, list: r.new_accounts }); }
      if (r.balanced === false) toast.warning(`BV chargée mais déséquilibre (écart ${money(r.diff)})`);
      else toast.success(`BV ${MONTHS[month - 1]} ${year} chargée${r.balanced ? " — balancée" : ""}`);
      reload();
    } catch (err) { toast.error(err.response?.data?.detail || "Upload impossible"); } finally { setBusy(false); }
  };
  const toggleLock = async (p) => {
    try { await api.acctLock({ year: p.year, month: p.month, locked: !p.locked }); toast.success(!p.locked ? "Mois verrouillé" : "Mois déverrouillé"); reload(); }
    catch (err) { toast.error(err.response?.data?.detail || "Action impossible"); }
  };
  const saveAssignments = async () => {
    const clean = {};
    for (const [k, v] of Object.entries(assign)) if (v) clean[k] = v;
    try {
      await api.acctAccountMap(clean, { year, month });
      toast.success(`${Object.keys(clean).length} compte(s) affecté(s)`);
      setNewAcct({ open: false, list: [] }); setAssign({}); reload();
    } catch (err) { toast.error(err.response?.data?.detail || "Enregistrement impossible"); }
  };
  const allAssigned = newAcct.list.length > 0 && newAcct.list.every((a) => assign[a.account]);

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

      <Dialog open={newAcct.open} onOpenChange={() => { /* bloquant : fermeture via bouton uniquement */ }}>
        <DialogContent data-testid="acct-newacct-dialog" className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Affectation requise — nouveaux comptes détectés</DialogTitle>
            <DialogDescription>Ces comptes sont présents dans la BV mais absents du modèle. Affectez chacun à un compte existant du rapport (son montant y sera regroupé). L'affectation est mémorisée pour les prochains uploads.</DialogDescription>
          </DialogHeader>
          <datalist id="acct-target-list">
            {accts.map((a) => <option key={a.account} value={`${a.account} — ${a.name}`} />)}
          </datalist>
          <div className="max-h-80 space-y-2 overflow-y-auto" data-testid="acct-newacct-list">
            {newAcct.list.map((a) => (
              <div key={a.account} className="grid grid-cols-2 items-center gap-3 rounded-lg border border-slate-200 p-2">
                <div className="text-sm"><span className="font-mono-data text-slate-500">{a.account}</span> <span className="text-slate-700">{a.name}</span></div>
                <input list="acct-target-list" data-testid={`acct-assign-${a.account}`} placeholder="Regrouper avec le compte…"
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-[#2563EB]"
                  onChange={(e) => { const m = e.target.value.match(/^(\d+)/); setAssign((s) => ({ ...s, [a.account]: m ? Number(m[1]) : "" })); }} />
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" data-testid="acct-newacct-skip" onClick={() => { setNewAcct({ open: false, list: [] }); toast.warning("Comptes non affectés — rapports incomplets jusqu'à l'affectation."); }}>Plus tard</Button>
            <Button data-testid="acct-newacct-save" disabled={!allAssigned} onClick={saveAssignments}>Enregistrer les affectations</Button>
          </DialogFooter>
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
  const [hideZero, setHideZero] = useState(false);
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
  const colLabel = (k) => ({
    reel: rep ? `Réel ${rep.month_label}` : "Réel", cumulatif: "Réel à date",
    bud_rev2: "Budget Rév-2", ecart_rev2: "Écart Rév-2", bud_rev1: "Budget Rév-1",
    ecart_rev1: "Écart Rév-1", bud_ca: "Budget CA", ecart_ca: "Écart CA", mois: rep ? `${rep.month_label} ${rep.year}` : "Mois",
  }[k] || k);
  const isEcart = (k) => k.startsWith("ecart");
  const visibleLines = rep ? rep.lines.filter((ln) => !(hideZero && ln.kind === "data" && rep.value_cols.every((k) => Math.abs(ln.values[k] || 0) < 0.005))) : [];

  return (
    <div className="space-y-4" data-testid={`acct-report-${type}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <PeriodPicker periods={periods} value={period} onChange={setPeriod} />
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600" data-testid="acct-hidezero-label">
            <input type="checkbox" checked={hideZero} onChange={(e) => setHideZero(e.target.checked)} data-testid="acct-hidezero-toggle" className="h-4 w-4 rounded border-slate-300" />
            Masquer les comptes à solde zéro
          </label>
        </div>
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
                <th className="px-4 py-2.5 text-left font-600">Compte</th>
                <th className="px-4 py-2.5 text-left font-600">Description</th>
                {rep.value_cols.map((k) => <th key={k} className={`px-4 py-2.5 text-right font-600 ${isEcart(k) ? "text-slate-500" : ""}`}>{colLabel(k)}</th>)}
              </tr></thead>
              <tbody className="font-mono-data">
                {visibleLines.map((ln) => (
                  <tr key={ln.row} data-testid={`acct-line-${ln.row}`}
                    className={`border-b border-slate-50 ${ln.kind === "total" ? "bg-slate-50 font-700" : ln.kind === "header" ? "font-700 text-slate-800" : ""}`}>
                    <td className="px-4 py-1.5 text-left text-slate-400">{ln.account || ""}</td>
                    <td className={`px-4 py-1.5 text-left ${ln.kind === "data" ? "font-sans text-slate-600" : "font-sans"}`}>{ln.label}</td>
                    {rep.value_cols.map((k) => (
                      <td key={k} className={`px-4 py-1.5 text-right ${isEcart(k) ? "italic" : ""}`} style={{ color: ln.values[k] < 0 ? "#DC2626" : (isEcart(k) ? "#64748B" : undefined) }}>{ln.kind === "header" ? "" : money(ln.values[k])}</td>
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

export function AcctCashflow() { return <CashflowView />; }
export function AcctAudit() { return <AcctComingSoon label="Rapports d'audit" />; }

// ---------- Flux de trésorerie (méthode indirecte) ----------
function CashflowView() {
  const { periods } = usePeriods();
  const [closeP, setCloseP] = useState("");
  const [openP, setOpenP] = useState("");
  const [rep, setRep] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!periods.length) return;
    if (!closeP) setCloseP(periods[0].id);
    if (!openP) setOpenP((periods[1] || periods[0]).id);
  }, [periods, closeP, openP]);

  useEffect(() => {
    if (!openP || !closeP || openP === closeP) { setRep(null); return; }
    const [oy, om] = openP.split("-").map(Number);
    const [cy, cm] = closeP.split("-").map(Number);
    setLoading(true); setRep(null);
    api.acctCashflow({ open_year: oy, open_month: om, close_year: cy, close_month: cm })
      .then(setRep).catch((e) => toast.error(e.response?.data?.detail || "Flux indisponible")).finally(() => setLoading(false));
  }, [openP, closeP]);

  const exportExcel = async () => {
    const [oy, om] = openP.split("-").map(Number);
    const [cy, cm] = closeP.split("-").map(Number);
    try {
      const blob = await api.acctCashflowExcel({ open_year: oy, open_month: om, close_year: cy, close_month: cm });
      const url = URL.createObjectURL(blob); const a = document.createElement("a");
      a.href = url; a.download = `flux_tresorerie_${openP}_${closeP}.xlsx`; a.click(); URL.revokeObjectURL(url);
      toast.success("Export téléchargé");
    } catch (e) { toast.error(e.response?.data?.detail || "Export impossible"); }
  };

  const waterfall = rep ? (() => {
    let run = rep.encaisse_ouverture;
    const steps = [{ name: "Ouverture", range: [0, run], fill: "#64748B", delta: run }];
    [["Exploitation", rep.exploitation_total], ["Investissement", rep.investissement_total], ["Financement", rep.financement_total]].forEach(([name, delta]) => {
      const start = run, end = run + delta;
      steps.push({ name, range: [Math.min(start, end), Math.max(start, end)], fill: delta >= 0 ? "#0E9488" : "#DC2626", delta });
      run = end;
    });
    steps.push({ name: "Clôture", range: [0, run], fill: "#2563EB", delta: run });
    return steps;
  })() : [];

  const Row = ({ label, value, kind, indent }) => (
    <tr className={`border-b border-slate-50 ${kind === "section" ? "bg-slate-100 font-800 text-slate-800" : kind === "subtotal" ? "bg-slate-50 font-700" : kind === "net" ? "border-t-2 border-slate-300 font-800" : ""}`}>
      <td className={`px-4 py-2 text-left ${indent ? "pl-9 font-sans text-slate-600" : "font-sans"}`}>{label}</td>
      <td className="px-4 py-2 text-right font-mono-data" style={{ color: value != null && value < 0 ? "#DC2626" : undefined }}>
        {value == null ? "" : money(value)}
      </td>
    </tr>
  );

  return (
    <div className="space-y-4" data-testid="acct-cashflow">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-600 text-slate-500">Ouverture (solde de départ)</label>
            <div className="mt-1"><PeriodPicker periods={periods} value={openP} onChange={setOpenP} /></div>
          </div>
          <div>
            <label className="block text-xs font-600 text-slate-500">Clôture (période courante)</label>
            <div className="mt-1"><PeriodPicker periods={periods} value={closeP} onChange={setCloseP} /></div>
          </div>
        </div>
        <Button size="sm" onClick={exportExcel} disabled={!rep} data-testid="acct-cashflow-export" className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><FileSpreadsheet size={15} /> Excel</Button>
      </div>
      <div className="flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2.5 text-xs text-sky-800" data-testid="acct-cashflow-hint">
        <Info size={15} className="mt-0.5 shrink-0" /> Méthode indirecte. Pour un flux « depuis le début de l'exercice », choisissez comme ouverture la BV de fin d'exercice précédent. Les variations = solde de clôture − solde d'ouverture.
      </div>
      {rep && (
        <div className="card p-5" data-testid="acct-cashflow-waterfall">
          <h3 className="mb-1 text-sm font-700">De l'encaisse d'ouverture à la clôture</h3>
          <p className="mb-4 text-xs text-slate-400">Contribution de chaque activité à la variation de l'encaisse (cascade).</p>
          <div style={{ width: "100%", height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={waterfall} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toLocaleString("fr-CA")} k`} width={70} />
                <Tooltip cursor={{ fill: "#F1F5F9" }} contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  formatter={(v, n, p) => [money(p.payload.delta), "Montant"]} />
                <Bar dataKey="range" radius={[4, 4, 0, 0]}>
                  {waterfall.map((s, i) => <Cell key={i} fill={s.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      {rep && !rep.locked && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-600 text-amber-700">
          <AlertTriangle size={16} /> Données provisoires — le mois de clôture n'est pas verrouillé.
        </div>
      )}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="text-sm font-700">État des flux de trésorerie{rep ? ` — du ${rep.open_label} au ${rep.close_label}` : ""}</h3>
          {rep && <span className={`inline-flex items-center gap-1 text-xs font-600 ${rep.balanced ? "text-emerald-600" : "text-red-600"}`} data-testid="acct-cashflow-reconcile">{rep.balanced ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}{rep.balanced ? "Réconcilié" : `Écart ${money(rep.ecart)}`}</span>}
        </div>
        {loading ? <p className="px-5 py-8 text-sm text-slate-500">Chargement…</p> : !rep ? <p className="px-5 py-8 text-sm text-slate-400">Sélectionnez deux périodes différentes avec des BV chargées.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
                <th className="px-4 py-2.5 text-left font-600">Poste</th>
                <th className="px-4 py-2.5 text-right font-600">Montant</th>
              </tr></thead>
              <tbody>
                <Row label="ACTIVITÉS D'EXPLOITATION" kind="section" />
                <Row label="Bénéfice net (perte nette)" value={rep.benefice_net} indent />
                {Math.abs(rep.amortissement) >= 0.005 && <Row label="Amortissement" value={rep.amortissement} indent />}
                {rep.fdr.length > 0 && <Row label="Variation des éléments hors caisse du fonds de roulement :" />}
                {rep.fdr.map((l, i) => <Row key={`f${i}`} label={l.label} value={l.value} indent />)}
                <Row label="Flux liés aux activités d'exploitation" value={rep.exploitation_total} kind="subtotal" />
                <Row label="ACTIVITÉS D'INVESTISSEMENT" kind="section" />
                {rep.investissement.map((l, i) => <Row key={`i${i}`} label={l.label} value={l.value} indent />)}
                {rep.investissement.length === 0 && <Row label="Aucune activité d'investissement" indent />}
                <Row label="Flux liés aux activités d'investissement" value={rep.investissement_total} kind="subtotal" />
                <Row label="ACTIVITÉS DE FINANCEMENT" kind="section" />
                {rep.financement.map((l, i) => <Row key={`n${i}`} label={l.label} value={l.value} indent />)}
                {rep.financement.length === 0 && <Row label="Aucune activité de financement" indent />}
                <Row label="Flux liés aux activités de financement" value={rep.financement_total} kind="subtotal" />
                <Row label="VARIATION NETTE DE LA TRÉSORERIE" value={rep.variation_nette} kind="net" />
                <Row label="Encaisse à l'ouverture" value={rep.encaisse_ouverture} indent />
                <Row label="Encaisse à la clôture" value={rep.encaisse_cloture} kind="subtotal" />
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
