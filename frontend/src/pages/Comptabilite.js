import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid, Cell, LineChart, Line } from "recharts";
import {
  Upload, FileSpreadsheet, Lock, Unlock, CheckCircle2, AlertTriangle, Clock, FileText, Layers, Construction, Info, Plus, Minus, TrendingUp, TrendingDown, Wallet, Receipt, PiggyBank, BarChart3,
} from "lucide-react";

const MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];

function money(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  const abs = Math.abs(n).toLocaleString("fr-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${abs})` : abs;
}

function moneyM(v) {
  if (v == null || v === "") return "—";
  const n = Number(v) / 1e6;
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
function Sparkline({ data, color }) {
  const d = (data || []).map((v, i) => ({ i, v }));
  if (d.length < 2) return <div style={{ height: 36 }} className="mt-3" />;
  return (
    <div style={{ height: 36 }} className="mt-3" aria-hidden>
      <ResponsiveContainer width="100%" height={36}>
        <LineChart data={d} margin={{ top: 4, right: 2, left: 2, bottom: 0 }}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function KpiCard({ label, value, series, idx, positiveIsGood = true, icon: Icon, testid }) {
  const prev = idx > 0 ? series[idx - 1] : null;
  const cur = idx >= 0 ? series[idx] : (series.length ? series[series.length - 1] : value);
  const delta = prev != null && prev !== 0 ? ((cur - prev) / Math.abs(prev)) * 100 : null;
  const up = delta != null && delta >= 0;
  const good = delta == null ? true : (up === positiveIsGood);
  return (
    <div className="card card-hover relative overflow-hidden p-4 pl-5" data-testid={testid}>
      <span className="absolute left-0 top-0 h-full w-1 bg-[#15AF97]" />
      <div className="flex items-start justify-between">
        <span className="overline">{label}</span>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#15AF97]/10 text-[#15AF97]"><Icon size={16} /></span>
      </div>
      <p className="font-display mt-2 text-2xl font-700 tracking-tight text-[#063044]">{money(value)}</p>
      <div className="mt-1 flex items-center gap-1.5 text-xs font-600" style={{ color: delta == null ? "#94A3B8" : (good ? "#10B981" : "#EF4444") }}>
        {delta != null && (up ? <TrendingUp size={14} /> : <TrendingDown size={14} />)}
        {delta != null ? `${up ? "+" : ""}${delta.toFixed(1)}% vs période préc.` : "Aucune donnée antérieure"}
      </div>
      <Sparkline data={series.slice(0, (idx >= 0 ? idx : series.length - 1) + 1)} color={good ? "#063044" : "#F8A942"} />
    </div>
  );
}

export function AcctDashboard() {
  const [d, setD] = useState(null);
  const { periods } = usePeriods();
  const [period, setPeriod] = useState("");
  const [summary, setSummary] = useState(null);
  const [trend, setTrend] = useState([]);
  useEffect(() => { api.acctDashboard().then(setD).catch(() => {}); api.acctTrend().then(setTrend).catch(() => {}); }, []);
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
  const trendData = trend.map((t) => ({
    name: `${t.month_label.slice(0, 3)} ${t.year}`, "Bénéfice net (mois)": t.benefice_mois, "Bénéfice net (cumulatif)": t.benefice_cumulatif,
  }));
  const selIdx = trend.findIndex((t) => t.period === period);
  const idx = selIdx >= 0 ? selIdx : trend.length - 1;
  const cur = idx >= 0 ? trend[idx] : null;
  const revSeries = trend.map((t) => t.revenus_cumulatif ?? 0);
  const cogsSeries = trend.map((t) => t.cogs_cumulatif ?? 0);
  const baiiaSeries = trend.map((t) => t.baiia_cumulatif ?? 0);
  const benSeries = trend.map((t) => t.benefice_cumulatif ?? 0);
  return (
    <div className="space-y-6" data-testid="acct-dashboard">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-600 text-slate-500">Période affichée :</span>
          <PeriodPicker periods={periods} value={period} onChange={setPeriod} />
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <span className="inline-flex items-center gap-1.5"><FileSpreadsheet size={13} /> {d.template_imported ? `${d.template_accounts} comptes` : "Modèle non importé"}</span>
          <span className="inline-flex items-center gap-1.5"><Layers size={13} /> {d.period_count} périodes</span>
        </div>
      </div>

      {cur && (
        <div className="grid max-w-5xl gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="acct-kpi-grid">
          <KpiCard label="Revenus (cumulatif)" value={cur.revenus_cumulatif} series={revSeries} idx={idx} positiveIsGood icon={Wallet} testid="kpi-revenus" />
          <KpiCard label="COGS (cumulatif)" value={cur.cogs_cumulatif} series={cogsSeries} idx={idx} positiveIsGood={false} icon={Receipt} testid="kpi-cogs" />
          <KpiCard label="BAIIA (cumulatif)" value={cur.baiia_cumulatif} series={baiiaSeries} idx={idx} positiveIsGood icon={BarChart3} testid="kpi-baiia" />
          <KpiCard label="Bénéfice net (cumulatif)" value={cur.benefice_cumulatif} series={benSeries} idx={idx} positiveIsGood icon={PiggyBank} testid="kpi-benefice" />
        </div>
      )}

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
                <Bar dataKey="Réel" fill="#063044" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Budget CA" fill="#F8A942" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Budget Rév-1" fill="#808080" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {trendData.length > 1 && (
        <div className="card p-5" data-testid="acct-dashboard-trend">
          <h3 className="mb-1 text-sm font-700">Évolution du bénéfice net</h3>
          <p className="mb-4 text-xs text-slate-400">Trajectoire sur les mois chargés — mensuel et cumulatif (exercice à date).</p>
          <div style={{ width: "100%", height: 300 }}>
            <ResponsiveContainer>
              <LineChart data={trendData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toLocaleString("fr-CA")} k`} width={70} />
                <Tooltip formatter={(v) => money(v)} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="Bénéfice net (mois)" stroke="#063044" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="Bénéfice net (cumulatif)" stroke="#F8A942" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
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
            <span className={`inline-flex cursor-pointer items-center gap-2 rounded-lg bg-[#063044] px-4 py-2 text-sm font-600 text-white hover:bg-[#063044]/90 ${busy ? "opacity-60" : ""}`}><Upload size={15} /> {busy ? "Traitement…" : "Uploader la BV (.xlsx)"}</span>
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
                  className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-[#063044]"
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
// Reproduit le format Excel d'une ligne de rapport (fond, couleur police, gras, bordures).
function excelRowStyle(ln) {
  const st = (ln && ln.style) || {};
  const isDark = st.f === "dark";
  const isGrey = st.f === "grey";
  const cls = [];
  if (isDark || isGrey || st.b || ln.kind === "total" || ln.kind === "header") cls.push("font-700");
  if (st.t) cls.push("border-t border-slate-300");
  if (st.u) cls.push("border-b-2 border-slate-300");
  const bg = isDark ? "#063044" : isGrey ? "#eef1f5" : undefined;
  let color;
  if (isDark) color = st.c || "#FFFFFF";
  else if (st.c) color = st.c;
  else if (ln.kind === "header") color = "#063044";
  else color = undefined;
  return { cls: cls.join(" "), bg, color, isDark };
}
function excelCellColor(s, val, ecart) {
  if (s.isDark) return val < 0 ? "#FCA5A5" : (s.color || "#FFFFFF");
  if (val < 0) return "#DC2626";
  if (ecart) return "#64748B";
  return s.color || undefined;
}

function ReportView({ type, title }) {
  const { periods } = usePeriods();
  const [period, setPeriod] = useState("");
  const [rep, setRep] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hideZero, setHideZero] = useState(false);
  const [hiddenGroups, setHiddenGroups] = useState({});
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
    bud_rev2: "Bud. Rév-2", ecart_rev2: "Écart Rév-2", bud_rev1: "Bud. Rév-1",
    ecart_rev1: "Écart Rév-1", bud_ca: "Bud. CA", ecart_ca: "Écart CA", reel_prec: "Réel an. préc.",
    bud_rev2_cum: "Bud. Rév-2", ecart_rev2_cum: "Écart Rév-2", bud_rev1_cum: "Bud. Rév-1",
    ecart_rev1_cum: "Écart Rév-1", bud_ca_cum: "Bud. CA", ecart_ca_cum: "Écart CA", prec_cum: "Cumul. an. préc.",
    mois: rep ? `${rep.month_label} ${rep.year}` : "Mois",
  }[k] || k);
  const isEcart = (k) => k.startsWith("ecart");
  const toggleGroups = rep?.col_toggle_groups || null;
  const hiddenKeys = new Set(
    (toggleGroups || []).filter((g) => hiddenGroups[g.id]).flatMap((g) => g.keys)
  );
  const visibleCols = !rep ? [] : rep.value_cols.filter((k) => !hiddenKeys.has(k));
  const visibleGroups = !rep?.col_groups ? null : rep.col_groups
    .map((g) => ({ ...g, keys: g.keys.filter((k) => !hiddenKeys.has(k)) }))
    .filter((g) => g.keys.length > 0);
  const showSep = (k) => k === "cumulatif" && visibleGroups && visibleGroups.length > 1;
  const visibleLines = rep ? rep.lines.filter((ln) => !(hideZero && ln.kind === "data" && visibleCols.every((k) => Math.abs(ln.values[k] || 0) < 0.005))) : [];

  return (
    <div className="space-y-4" data-testid={`acct-report-${type}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <PeriodPicker periods={periods} value={period} onChange={setPeriod} />
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600" data-testid="acct-hidezero-label">
            <input type="checkbox" checked={hideZero} onChange={(e) => setHideZero(e.target.checked)} data-testid="acct-hidezero-toggle" className="h-4 w-4 rounded border-slate-300" />
            Masquer les comptes à solde zéro
          </label>
          {rep?.col_toggle_groups && (
            <div className="flex flex-wrap items-center gap-2" data-testid="acct-colgroups">
              <span className="text-sm text-slate-500">Colonnes :</span>
              {rep.col_toggle_groups.map((g) => {
                const hidden = !!hiddenGroups[g.id];
                return (
                  <button key={g.id} type="button" data-testid={`acct-colgroup-${g.id}`}
                    onClick={() => setHiddenGroups((s) => ({ ...s, [g.id]: !s[g.id] }))}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-600 transition-colors ${hidden ? "border-slate-200 bg-white text-slate-400" : "border-[#063044]/30 bg-[#063044]/10 text-[#063044]"}`}>
                    {hidden ? <Plus size={13} /> : <Minus size={13} />} {g.label}
                  </button>
                );
              })}
            </div>
          )}
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
          <div className="overflow-auto max-h-[calc(100vh-230px)]">
            <table className="w-full text-sm">
              <thead>
                {visibleGroups && (
                  <tr className="sticky top-0 z-20 border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="bg-white px-4 py-1.5" colSpan={2}></th>
                    {visibleGroups.map((g, gi) => (
                      <th key={g.label} colSpan={g.keys.length} className={`bg-white px-4 py-1.5 text-center font-700 text-slate-600 ${gi > 0 ? "border-l-2 border-slate-200" : ""}`}>{g.label}</th>
                    ))}
                  </tr>
                )}
                <tr className={`sticky z-20 border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400 ${visibleGroups ? "top-[30px]" : "top-0"}`}>
                <th className="bg-white px-4 py-2.5 text-left font-600">Compte</th>
                <th className="bg-white px-4 py-2.5 text-left font-600">Description</th>
                {visibleCols.map((k) => <th key={k} className={`bg-white px-4 py-2.5 text-right font-600 ${isEcart(k) ? "text-slate-500" : ""} ${showSep(k) ? "border-l-2 border-slate-200" : ""}`}>{colLabel(k)}</th>)}
              </tr></thead>
              <tbody className="font-mono-data">
                {visibleLines.map((ln) => {
                  const s = excelRowStyle(ln);
                  return (
                  <tr key={ln.row} data-testid={`acct-line-${ln.row}`}
                    className={`border-b border-slate-50 ${s.cls}`} style={{ background: s.bg }}>
                    <td className="px-4 py-1.5 text-left" style={{ color: s.isDark ? "#94A3B8" : "#94A3B8" }}>{ln.account || ""}</td>
                    <td className="px-4 py-1.5 text-left font-sans" style={{ color: s.color || (ln.kind === "data" ? "#334155" : undefined) }}>{ln.label}</td>
                    {visibleCols.map((k) => (
                      <td key={k} className={`px-4 py-1.5 text-right ${isEcart(k) ? "italic" : ""} ${showSep(k) ? "border-l-2 border-slate-200" : ""}`} style={{ color: excelCellColor(s, ln.values[k], isEcart(k)) }}>{ln.kind === "header" ? "" : money(ln.values[k])}</td>
                    ))}
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function ViewToggle({ value, onChange, options }) {
  return (
    <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm" data-testid="acct-view-toggle">
      {options.map((o) => (
        <button key={o.value} data-testid={`acct-view-${o.value}`} onClick={() => onChange(o.value)}
          className={`rounded-lg px-4 py-1.5 text-sm font-600 transition-colors ${value === o.value ? "bg-[#063044] text-white" : "text-slate-500 hover:text-slate-900"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function AcctBilan() {
  const [v, setV] = useState("detaille");
  return (
    <div className="space-y-4">
      <ViewToggle value={v} onChange={setV} options={[{ value: "detaille", label: "Bilan détaillé" }, { value: "sommaire", label: "Bilan sommaire" }, { value: "sommaire_m", label: "Bilan sommaire (M$)" }]} />
      {v === "detaille" ? <ReportView type="bilan" title="Bilan détaillé" />
        : v === "sommaire_m" ? <BilanSommaireView millions />
        : <BilanSommaireView />}
    </div>
  );
}

export function AcctPnl() {
  const [v, setV] = useState("detaille");
  return (
    <div className="space-y-4">
      <ViewToggle value={v} onChange={setV} options={[{ value: "detaille", label: "État détaillé" }, { value: "sommaire", label: "Résultat sommaire" }]} />
      {v === "detaille" ? <ReportView type="pnl" title="État des résultats" /> : <ReportView type="pnl_sommaire" title="Résultat sommaire" />}
    </div>
  );
}

function BilanSommaireView({ millions = false }) {
  const { periods } = usePeriods();
  const [period, setPeriod] = useState("");
  const [rep, setRep] = useState(null);
  const [loading, setLoading] = useState(false);
  const fmt = millions ? moneyM : money;
  useEffect(() => { if (!period && periods.length) setPeriod(periods[0].id); }, [periods, period]);
  useEffect(() => {
    if (!period) return;
    const [y, m] = period.split("-").map(Number);
    setLoading(true); setRep(null);
    api.acctReport({ type: "bilan_sommaire", year: y, month: m })
      .then(setRep).catch((e) => toast.error(e.response?.data?.detail || "Rapport indisponible")).finally(() => setLoading(false));
  }, [period]);

  const exportExcel = async () => {
    const [y, m] = period.split("-").map(Number);
    try {
      const blob = await api.acctReportExcel({ type: "bilan_sommaire", year: y, month: m });
      const url = URL.createObjectURL(blob); const a = document.createElement("a");
      a.href = url; a.download = `bilan_sommaire_${period}.xlsx`; a.click(); URL.revokeObjectURL(url);
      toast.success("Export téléchargé");
    } catch (e) { toast.error(e.response?.data?.detail || "Export impossible"); }
  };

  const Side = ({ title, rows }) => (
    <div>
      <h4 className="mb-2 border-b-2 border-[#063044] pb-1.5 font-display text-sm font-800 uppercase tracking-wide text-[#063044]">{title}</h4>
      <table className="w-full text-sm">
        <tbody className="font-mono-data">
          {rows.map((l, i) => {
            const s = excelRowStyle(l);
            return (
            <tr key={i} className={`border-b border-slate-50 ${s.cls}`} style={{ background: s.bg }}>
              <td className={`px-3 py-1.5 text-left font-sans ${l.kind === "data" ? "pl-5" : ""}`} style={{ color: s.color || (l.kind === "data" ? "#334155" : undefined) }}>{l.label}</td>
              <td className="px-3 py-1.5 text-right" style={{ color: l.value == null ? undefined : excelCellColor(s, l.value, false) }}>{l.value == null ? "" : fmt(l.value)}</td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="space-y-4" data-testid="acct-bilan-sommaire">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PeriodPicker periods={periods} value={period} onChange={setPeriod} />
        <Button size="sm" onClick={exportExcel} disabled={!rep} data-testid="acct-bilansom-export" className="gap-2 bg-[#063044] hover:bg-[#063044]/90"><FileSpreadsheet size={15} /> Excel</Button>
      </div>
      {rep && !rep.locked && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-600 text-amber-700">
          <AlertTriangle size={16} /> Données provisoires — ce mois n'est pas verrouillé.
        </div>
      )}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="font-display text-sm font-700">Bilan sommaire{millions ? " (en M$)" : ""}{rep ? ` — ${rep.month_label} ${rep.year}` : ""}</h3>
          {rep && <span className={`inline-flex items-center gap-1 text-xs font-600 ${Math.abs(rep.validation) < 1 ? "text-emerald-600" : "text-red-600"}`} data-testid="acct-bilansom-balance">{Math.abs(rep.validation) < 1 ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}{Math.abs(rep.validation) < 1 ? "Balancé" : `Écart ${money(rep.validation)}`}</span>}
        </div>
        {loading ? <p className="px-5 py-8 text-sm text-slate-500">Chargement…</p> : !rep ? <p className="px-5 py-8 text-sm text-slate-400">Sélectionnez une période.</p> : (
          <div className="grid gap-8 p-5 lg:grid-cols-2">
            <Side title="Actif" rows={rep.actif} />
            <Side title="Passif et capitaux" rows={rep.passif} />
          </div>
        )}
      </div>
    </div>
  );
}

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
    const steps = [{ name: "Ouverture", range: [0, run], fill: "#808080", delta: run }];
    [["Exploitation", rep.exploitation_total], ["Investissement", rep.investissement_total], ["Financement", rep.financement_total]].forEach(([name, delta]) => {
      const start = run, end = run + delta;
      steps.push({ name, range: [Math.min(start, end), Math.max(start, end)], fill: delta >= 0 ? "#15AF97" : "#F8A942", delta });
      run = end;
    });
    steps.push({ name: "Clôture", range: [0, run], fill: "#063044", delta: run });
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
