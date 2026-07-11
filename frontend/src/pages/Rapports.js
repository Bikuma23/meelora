import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useYear } from "../context/YearContext";
import { useAuth } from "../context/AuthContext";
import { fmtCAD } from "../lib/format";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { FileSpreadsheet, FileText, Filter, BarChart3, Layers, Table2, LayoutDashboard, Save } from "lucide-react";
import { toast } from "sonner";
import { BarChart, Bar, XAxis, YAxis, ResponsiveContainer, Tooltip, Cell, CartesianGrid } from "recharts";

const VENTIL = [
  ["salaire_base", "Salaire de base"], ["vacances", "Vacances"], ["primes", "Primes & Boni"],
  ["avantages", "Avantages sociaux"], ["csst", "CSST"], ["reer", "RPDB/REER"], ["assurance", "Assu. collectives"],
];
const SCEN = [["actuel", "Salaires actuels"], ["ca", "Budget CA"], ["revue1", "Revue Budgétaire 1"], ["revue2", "Revue Budgétaire 2"]];
const TYPES = ["all", "CCQ", "Régulier temps plein", "Régulier temps partiel", "Stagiaire"];
const TABS = [["synthese", "Synthèse", LayoutDashboard], ["pnl", "État des résultats (P&L)", BarChart3], ["classe", "Masse par classe", Layers], ["custom", "Constructeur personnalisé", Table2]];
const COLORS = ["#2563EB", "#14B8A6", "#F59E0B", "#EC4899", "#8B5CF6", "#EF4444", "#0EA5E9"];
const fmtK = (v) => `${Math.round(v / 1000)}k`;

export default function Rapports() {
  const { year, years, selectYear } = useYear();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [departments, setDepartments] = useState([]);
  const [dept, setDept] = useState("all");
  const [scenario, setScenario] = useState("ca");
  const [tab, setTab] = useState("synthese");
  const [data, setData] = useState(null);
  const [pnl, setPnl] = useState(null);
  const [byClass, setByClass] = useState(null);
  const [busy, setBusy] = useState("");
  const [allCols, setAllCols] = useState([]);
  const [cols, setCols] = useState(["employee_number", "name", "department", "salaire_brut", "total_budgeted"]);
  const [empType, setEmpType] = useState("all");
  const [groupBy, setGroupBy] = useState("");
  const [custom, setCustom] = useState(null);
  const [templates, setTemplates] = useState([]);
  const [tplName, setTplName] = useState("");

  const params = useMemo(() => ({ year, scenario, ...(dept !== "all" ? { department: dept } : {}) }), [year, scenario, dept]);

  useEffect(() => { api.listDepartments().then(setDepartments); api.getCustomColumns().then((r) => setAllCols(r.columns)); api.listReportTemplates().then(setTemplates).catch(() => {}); }, []);
  useEffect(() => { setData(null); api.getBudget(params).then(setData); }, [params]);
  useEffect(() => { if (tab === "pnl") { setPnl(null); api.getPnl(params).then(setPnl); } if (tab === "classe") { setByClass(null); api.getByClass(params).then(setByClass); } }, [tab, params]);

  const dl = async (kind, name, extra) => {
    setBusy(kind);
    try {
      const blob = extra ? await api.downloadReportParams(kind, { ...params, ...extra }) : await api.downloadReport(kind, dept, year, scenario);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `${name}_${scenario}_${year}.${kind.includes("pdf") ? "pdf" : "xlsx"}`; a.click();
      URL.revokeObjectURL(url); toast.success("Export téléchargé");
    } catch { toast.error("Export échoué"); } finally { setBusy(""); }
  };

  const runCustom = () => { api.getCustomReport({ ...params, columns: cols.join(","), employment_type: empType, group_by: groupBy }).then(setCustom); };
  const toggleCol = (k) => setCols((p) => p.includes(k) ? p.filter((c) => c !== k) : [...p, k]);
  const scopeLabel = dept === "all" ? "Tous les départements" : departments.find((d) => d.code === dept)?.description || dept;

  const saveTemplate = async () => {
    if (!tplName.trim()) { toast.error("Donnez un nom au modèle"); return; }
    try {
      await api.createReportTemplate({ name: tplName.trim(), columns: cols, employment_type: empType, group_by: groupBy, department: dept });
      setTplName(""); setTemplates(await api.listReportTemplates()); toast.success("Modèle enregistré");
    } catch { toast.error("Enregistrement du modèle échoué"); }
  };
  const applyTemplate = (t) => {
    setCols(t.columns && t.columns.length ? t.columns : cols);
    setEmpType(t.employment_type || "all"); setGroupBy(t.group_by || "");
    if (t.department) setDept(t.department);
    api.getCustomReport({ year, scenario, ...(t.department && t.department !== "all" ? { department: t.department } : {}), columns: (t.columns || []).join(","), employment_type: t.employment_type || "all", group_by: t.group_by || "" }).then(setCustom);
    toast.success(`Modèle « ${t.name} » appliqué`);
  };
  const deleteTemplate = async (t) => {
    try { await api.deleteReportTemplate(t.id); setTemplates(await api.listReportTemplates()); toast.success("Modèle supprimé"); }
    catch { toast.error("Suppression échouée"); }
  };

  return (
    <div className="space-y-5" data-testid="rapports-page">
      <div className="card flex flex-wrap items-end gap-3 p-5">
        <p className="flex w-full items-center gap-1.5 text-xs font-700 uppercase tracking-widest text-slate-500"><Filter size={13} /> Portée</p>
        <div><label className="text-[11px] uppercase text-slate-500">Année</label>
          <Select value={String(year)} onValueChange={(v) => selectYear(v)}><SelectTrigger className="mt-1 w-24" data-testid="report-year"><SelectValue /></SelectTrigger>
            <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent></Select></div>
        <div><label className="text-[11px] uppercase text-slate-500">Scénario</label>
          <Select value={scenario} onValueChange={setScenario}><SelectTrigger className="mt-1 w-44" data-testid="report-scenario"><SelectValue /></SelectTrigger>
            <SelectContent>{SCEN.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent></Select></div>
        <div><label className="text-[11px] uppercase text-slate-500">Département</label>
          <Select value={dept} onValueChange={setDept}><SelectTrigger className="mt-1 w-60" data-testid="report-department"><SelectValue /></SelectTrigger>
            <SelectContent className="max-h-64"><SelectItem value="all">Tous les départements</SelectItem>
              {departments.map((d) => <SelectItem key={d.code} value={d.code}>{d.code} — {d.description}</SelectItem>)}</SelectContent></Select></div>
      </div>

      <div className="flex flex-wrap gap-2" data-testid="report-tabs">
        {TABS.map(([k, l, Icon]) => (
          <button key={k} data-testid={`tab-${k}`} onClick={() => setTab(k)}
            className={`flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-600 transition-colors ${tab === k ? "bg-[#2563EB] text-white" : "bg-white text-slate-600 hover:bg-slate-100"}`}>
            <Icon size={15} /> {l}
          </button>
        ))}
      </div>

      {tab === "synthese" && data && (
        <>
          <div className="flex flex-wrap gap-2">
            <Button data-testid="export-excel-btn" disabled={busy} onClick={() => dl("excel", "rapport")} className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><FileSpreadsheet size={16} /> Synthèse Excel</Button>
            <Button data-testid="export-pdf-btn" disabled={busy} onClick={() => dl("pdf", "rapport")} className="gap-2 bg-[#EF4444] hover:bg-[#EF4444]/90"><FileText size={16} /> Synthèse PDF</Button>
            <Button data-testid="export-fiches-excel-btn" disabled={busy} variant="outline" onClick={() => dl("fiches-excel", "fiches")} className="gap-2"><FileSpreadsheet size={16} /> Fiches (Excel)</Button>
            <Button data-testid="export-fiches-pdf-btn" disabled={busy} variant="outline" onClick={() => dl("fiches-pdf", "fiches")} className="gap-2"><FileText size={16} /> Fiches (PDF)</Button>
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[["Effectif", data.kpis.headcount], ["Masse salariale", fmtCAD(data.totals.salaire_base)], ["Budget global", fmtCAD(data.totals.budget_total)], ["Salaire moyen", fmtCAD(data.kpis.salaire_moyen)]].map(([l, v]) => (
              <div key={l} className="card p-4"><p className="text-[11px] font-600 uppercase tracking-wide text-slate-500">{l}</p><p className="mt-1.5 font-mono-data text-lg font-700">{v}</p></div>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="card p-5"><h3 className="mb-3 text-sm font-700">Ventilation ({scopeLabel})</h3>
              <div className="divide-y divide-slate-100">
                {VENTIL.map(([k, l]) => <div key={k} className="flex justify-between py-1.5 text-sm"><span className="text-slate-500">{l}</span><span className="font-mono-data">{fmtCAD(data.totals[k])}</span></div>)}
                <div className="flex justify-between py-2 text-sm font-700"><span>Budget total</span><span className="font-mono-data text-[#0E9488]">{fmtCAD(data.totals.budget_total)}</span></div>
              </div></div>
            <div className="card p-5"><h3 className="mb-3 text-sm font-700">Budget par département</h3>
              <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
                {[...data.by_department].sort((a, b) => (parseInt(a.department, 10) || 0) - (parseInt(b.department, 10) || 0)).map((d) => <div key={d.department} className="flex justify-between py-1.5 text-sm"><span className="text-slate-600">{d.department} — {d.label}</span><span className="font-mono-data">{fmtCAD(d.budget)}</span></div>)}
              </div></div>
          </div>
        </>
      )}

      {tab === "pnl" && (
        <div className="card p-5" data-testid="pnl-report">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-700">État des résultats — ventilation mensuelle par compte GL</h3>
            <Button data-testid="pnl-excel-btn" size="sm" disabled={busy} onClick={() => dl("pnl-excel", "pnl", {})} className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><FileSpreadsheet size={15} /> Excel</Button>
          </div>
          {!pnl ? <p className="text-sm text-slate-500">Chargement…</p> : (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={pnl.months.map((m, i) => ({ mois: m, total: pnl.totals.monthly[i] }))}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} /><XAxis dataKey="mois" tick={{ fontSize: 11 }} /><YAxis tickFormatter={fmtK} tick={{ fontSize: 11 }} />
                  <Tooltip formatter={(v) => fmtCAD(v)} /><Bar dataKey="total" fill="#2563EB" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead><tr className="border-b border-slate-200 text-slate-400"><th className="px-2 py-1.5 text-left font-600">Compte GL</th>{pnl.months.map((m) => <th key={m} className="px-2 py-1.5 text-right font-600">{m}</th>)}<th className="px-2 py-1.5 text-right font-700">Total</th></tr></thead>
                  <tbody className="font-mono-data">
                    {pnl.rows.map((r) => <tr key={r.gl} className="border-b border-slate-100" data-testid={`pnl-row-${r.gl}`}><td className="px-2 py-1.5 text-left font-700 text-slate-700">{r.gl}</td>{r.monthly.map((v, i) => <td key={i} className="px-2 py-1.5 text-right">{fmtCAD(v)}</td>)}<td className="px-2 py-1.5 text-right font-700">{fmtCAD(r.total)}</td></tr>)}
                    <tr className="border-t-2 border-slate-300 bg-slate-50 font-700"><td className="px-2 py-2 text-left">TOTAL</td>{pnl.totals.monthly.map((v, i) => <td key={i} className="px-2 py-2 text-right">{fmtCAD(v)}</td>)}<td className="px-2 py-2 text-right text-[#0E9488]">{fmtCAD(pnl.totals.total)}</td></tr>
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      )}

      {tab === "classe" && (
        <div className="card p-5" data-testid="class-report">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-700">Masse salariale par classe de sécurité CSST {byClass ? `· max assurable ${fmtCAD(byClass.csst_max_assurable)}` : ""}</h3>
            <Button data-testid="class-excel-btn" size="sm" disabled={busy} onClick={() => dl("by-class-excel", "masse_classe", {})} className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><FileSpreadsheet size={15} /> Excel</Button>
          </div>
          {!byClass ? <p className="text-sm text-slate-500">Chargement…</p> : (
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={byClass.rows.map((r) => ({ nom: r.code, budget: r.budget }))} layout="vertical" margin={{ left: 20 }}>
                  <XAxis type="number" tickFormatter={fmtK} tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="nom" tick={{ fontSize: 11 }} width={60} />
                  <Tooltip formatter={(v) => fmtCAD(v)} /><Bar dataKey="budget" radius={[0, 4, 4, 0]}>{byClass.rows.map((r, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}</Bar>
                </BarChart>
              </ResponsiveContainer>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead><tr className="border-b border-slate-200 text-slate-400"><th className="px-2 py-1.5 text-left font-600">Classe</th><th className="px-2 py-1.5 text-left font-600">Desc.</th><th className="px-2 py-1.5 text-right font-600">Taux</th><th className="px-2 py-1.5 text-right font-600">Empl.</th><th className="px-2 py-1.5 text-right font-600">CSST</th><th className="px-2 py-1.5 text-right font-700">Coût total</th></tr></thead>
                  <tbody className="font-mono-data">
                    {byClass.rows.map((r) => <tr key={r.code} className="border-b border-slate-100" data-testid={`class-report-${r.code}`}><td className="px-2 py-1.5 text-left font-700 text-slate-700">{r.code}</td><td className="px-2 py-1.5 text-left text-slate-500">{r.description}</td><td className="px-2 py-1.5 text-right">{(r.rate * 100).toFixed(2)}%</td><td className="px-2 py-1.5 text-right">{r.count}</td><td className="px-2 py-1.5 text-right">{fmtCAD(r.csst)}</td><td className="px-2 py-1.5 text-right font-700">{fmtCAD(r.budget)}</td></tr>)}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "custom" && (
        <div className="space-y-4" data-testid="custom-report">
          <div className="card p-5" data-testid="templates-card">
            <h3 className="mb-3 text-sm font-700">Modèles enregistrés</h3>
            {templates.length === 0 ? (
              <p className="text-[11px] text-slate-400">Aucun modèle. Configurez colonnes et filtres ci-dessous, puis enregistrez pour générer ce rapport en un clic plus tard.</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {templates.map((t) => (
                  <div key={t.id} data-testid={`template-${t.id}`} className="group flex items-center gap-1 rounded-full border border-[#0E9488]/40 bg-[#0E9488]/10 py-1 pl-3 pr-1.5 text-xs font-600 text-[#0E7168]">
                    <button data-testid={`template-apply-${t.id}`} onClick={() => applyTemplate(t)} className="hover:underline">{t.name}</button>
                    {isAdmin && <button data-testid={`template-del-${t.id}`} onClick={() => deleteTemplate(t)} className="rounded-full px-1 text-slate-400 hover:bg-red-100 hover:text-red-500" title="Supprimer">✕</button>}
                  </div>
                ))}
              </div>
            )}
            <div className="mt-3 flex items-end gap-2">
              <input data-testid="template-name" value={tplName} onChange={(e) => setTplName(e.target.value)} placeholder={isAdmin ? "Nom du modèle (ex. Masse par département)" : "Enregistrement réservé aux administrateurs"} disabled={!isAdmin}
                className="h-9 flex-1 rounded-lg border border-slate-200 px-3 text-sm outline-none focus:border-[#2563EB] disabled:bg-slate-50 disabled:text-slate-400" />
              <Button data-testid="save-template-btn" onClick={saveTemplate} disabled={!isAdmin} className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><Save size={15} /> Enregistrer le modèle</Button>
            </div>
          </div>
          <div className="card p-5">
            <h3 className="mb-3 text-sm font-700">Constructeur de rapport personnalisé</h3>
            <p className="text-[11px] font-600 uppercase text-slate-500">Colonnes</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {allCols.map((c) => (
                <button key={c.key} data-testid={`col-${c.key}`} onClick={() => toggleCol(c.key)}
                  className={`rounded-full border px-3 py-1 text-xs font-600 ${cols.includes(c.key) ? "border-[#2563EB] bg-[#2563EB]/10 text-[#2563EB]" : "border-slate-200 text-slate-500 hover:bg-slate-50"}`}>{c.label}</button>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <div><label className="text-[11px] uppercase text-slate-500">Type d'emploi</label>
                <Select value={empType} onValueChange={setEmpType}><SelectTrigger className="mt-1 w-48" data-testid="custom-type"><SelectValue /></SelectTrigger>
                  <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t === "all" ? "Tous" : t}</SelectItem>)}</SelectContent></Select></div>
              <div><label className="text-[11px] uppercase text-slate-500">Regrouper par</label>
                <Select value={groupBy || "none"} onValueChange={(v) => setGroupBy(v === "none" ? "" : v)}><SelectTrigger className="mt-1 w-48" data-testid="custom-group"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="none">Aucun regroupement</SelectItem><SelectItem value="department">Département</SelectItem><SelectItem value="employment_type">Type</SelectItem><SelectItem value="security_class">Classe de sécurité</SelectItem></SelectContent></Select></div>
              <Button data-testid="run-custom-btn" onClick={runCustom} className="gap-2 bg-[#2563EB] hover:bg-[#2563EB]/90"><Table2 size={15} /> Générer</Button>
              <Button data-testid="custom-excel-btn" variant="outline" disabled={busy} onClick={() => dl("custom-excel", "rapport_perso", { columns: cols.join(","), employment_type: empType, group_by: groupBy })} className="gap-2"><FileSpreadsheet size={15} /> Excel</Button>
            </div>
          </div>
          {custom && (
            <div className="card overflow-x-auto p-5" data-testid="custom-result">
              <table className="w-full text-[11px]">
                <thead><tr className="border-b border-slate-200 text-slate-400">{custom.columns.map((c) => <th key={c.key} className={`px-2 py-1.5 font-600 ${custom.numeric.includes(c.key) ? "text-right" : "text-left"}`}>{c.label}</th>)}</tr></thead>
                <tbody className="font-mono-data">
                  {custom.grouped
                    ? custom.groups.map((g) => (
                      <>
                        <tr key={g.key} className="bg-slate-50"><td colSpan={custom.columns.length} className="px-2 py-1.5 text-left font-700 text-slate-700">▸ {g.key}</td></tr>
                        {g.rows.map((row, i) => <tr key={g.key + i} className="border-b border-slate-100">{custom.columns.map((c) => <td key={c.key} className={`px-2 py-1.5 ${custom.numeric.includes(c.key) ? "text-right" : "text-left"}`}>{custom.numeric.includes(c.key) ? fmtCAD(row[c.key]) : row[c.key]}</td>)}</tr>)}
                        <tr className="border-b border-slate-200 font-700 text-slate-600">{custom.columns.map((c, i) => <td key={c.key} className={`px-2 py-1.5 ${custom.numeric.includes(c.key) ? "text-right" : "text-left"}`}>{i === 0 ? "Sous-total" : (custom.numeric.includes(c.key) ? fmtCAD(g.subtotals[c.key]) : "")}</td>)}</tr>
                      </>
                    ))
                    : custom.rows.map((row, i) => <tr key={i} className="border-b border-slate-100">{custom.columns.map((c) => <td key={c.key} className={`px-2 py-1.5 ${custom.numeric.includes(c.key) ? "text-right" : "text-left"}`}>{custom.numeric.includes(c.key) ? fmtCAD(row[c.key]) : row[c.key]}</td>)}</tr>)}
                  <tr className="border-t-2 border-slate-300 bg-slate-50 font-700">{custom.columns.map((c, i) => <td key={c.key} className={`px-2 py-2 ${custom.numeric.includes(c.key) ? "text-right" : "text-left"}`}>{i === 0 ? "TOTAL" : (custom.numeric.includes(c.key) ? fmtCAD(custom.totals[c.key]) : "")}</td>)}</tr>
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
