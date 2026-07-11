import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useYear } from "../context/YearContext";
import { fmtCAD } from "../lib/format";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell,
} from "recharts";
import { Users, DollarSign, Wallet, TrendingUp, Calendar, PieChart as PieIcon, BarChart3, Layers, Scale } from "lucide-react";

const TEAL = "#14B8A6", NAVY = "#0E1526", ORANGE = "#F59E0B", BLUE = "#2563EB", VIOLET = "#8B5CF6";
const TYPE_COLORS = { "CCQ": BLUE, "Régulier temps plein": TEAL, "Stagiaire": ORANGE };
const SEX_CATS = ["Masculin", "Féminin", "Autre", "Non spécifié"];
const SEX_COLORS = { "Masculin": BLUE, "Féminin": "#EC4899", "Autre": TEAL, "Non spécifié": "#94A3B8" };
const SCEN = [["ca", "Budget CA"], ["revue1", "Revue Budgétaire 1"], ["revue2", "Revue Budgétaire 2"]];

const Tip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2.5 text-xs shadow-lg">
      {label && <p className="mb-1 font-700">{label}</p>}
      {payload.map((p, i) => <p key={i} className="font-mono-data">{p.name}: {fmtCAD(p.value)}</p>)}
    </div>
  );
};

function Kpi({ label, value, sub, icon: Icon, tint, testId }) {
  return (
    <div className="card p-5" data-testid={testId}>
      <div className="flex items-start justify-between">
        <span className="text-[11px] font-600 uppercase tracking-widest text-slate-500">{label}</span>
        <span className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ backgroundColor: tint + "1a", color: tint }}>
          <Icon size={18} />
        </span>
      </div>
      <p className="mt-3 font-mono-data text-2xl font-700 tracking-tight lg:text-3xl">{value}</p>
      <p className="mt-1 text-xs text-slate-500">{sub}</p>
    </div>
  );
}

export default function Dashboard() {
  const { year, years, selectYear } = useYear();
  const [b, setB] = useState(null);
  const [cmp, setCmp] = useState(null);
  const [evo, setEvo] = useState(null);
  const [scenario, setScenario] = useState("ca");
  const [departments, setDepartments] = useState([]);
  const [dept, setDept] = useState("all");
  useEffect(() => { api.listDepartments().then(setDepartments); }, []);
  useEffect(() => {
    setB(null);
    const p = dept !== "all" ? { department: dept } : {};
    api.getBudget({ year, scenario, ...p }).then(setB);
    api.getBudgetCompare({ year, ...p }).then(setCmp);
    api.getBudgetEvolution(p).then(setEvo);
  }, [dept, year, scenario]);

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div className="card flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <label className="text-[11px] uppercase text-slate-500">Année</label>
            <Select value={String(year)} onValueChange={(v) => selectYear(v)}><SelectTrigger className="mt-1 h-9 w-28" data-testid="dash-year"><SelectValue /></SelectTrigger>
              <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent></Select>
          </div>
          <div>
            <label className="text-[11px] uppercase text-slate-500">Scénario</label>
            <Select value={scenario} onValueChange={setScenario}><SelectTrigger className="mt-1 h-9 w-48" data-testid="dash-scenario"><SelectValue /></SelectTrigger>
              <SelectContent>{SCEN.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent></Select>
          </div>
          <div>
            <label className="text-[11px] uppercase text-slate-500">Département</label>
            <Select value={dept} onValueChange={setDept}>
              <SelectTrigger className="mt-1 h-9 w-64" data-testid="dash-department"><SelectValue /></SelectTrigger>
              <SelectContent className="max-h-64">
                <SelectItem value="all">Tous les départements</SelectItem>
                {departments.map((d) => <SelectItem key={d.code} value={d.code}>{d.code} — {d.description}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <span className="font-mono-data text-xs text-slate-500">{b ? `${b.kpis.headcount} entrée(s) affichée(s)` : "…"}</span>
      </div>

      {cmp && <Comparatif cmp={cmp} />}
      {evo && evo.years.length > 1 && <Evolution evo={evo} />}
      {!b ? <p className="font-mono-data text-sm text-slate-500">Chargement…</p> : <DashboardBody b={b} />}
    </div>
  );
}

function Comparatif({ cmp }) {
  const rows = [
    ["Salaires actuels", cmp.actuel.masse, "#64748B", "Somme des salaires de base"],
    ["Budget CA", cmp.ca.masse, BLUE, "Après augmentations & primes"],
    ["Revue Budgétaire 1", cmp.revue1.masse, VIOLET, "1re revue budgétaire"],
    ["Revue Budgétaire 2", cmp.revue2.masse, ORANGE, "2e revue budgétaire"],
  ];
  const chart = [
    { name: "Masse salariale", "Salaires actuels": cmp.actuel.masse, "Budget CA": cmp.ca.masse, "Revue 1": cmp.revue1.masse, "Revue 2": cmp.revue2.masse },
    { name: "Budget total", "Salaires actuels": cmp.actuel.budget_total, "Budget CA": cmp.ca.budget_total, "Revue 1": cmp.revue1.budget_total, "Revue 2": cmp.revue2.budget_total },
  ];
  const dCA = cmp.actuel.masse ? ((cmp.ca.masse - cmp.actuel.masse) / cmp.actuel.masse) * 100 : 0;
  return (
    <div className="card p-6" data-testid="comparatif-card">
      <h3 className="mb-5 flex items-center gap-2 text-sm font-700"><Scale size={16} className="text-[#2563EB]" /> Comparatif des masses salariales — {cmp.year}</h3>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="grid grid-cols-2 gap-3">
          {rows.map(([lbl, val, c, sub]) => (
            <div key={lbl} className="rounded-xl border border-slate-200 p-4" data-testid={`cmp-${lbl}`}>
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: c }} />
              <p className="mt-2 text-[11px] font-600 uppercase tracking-wide text-slate-500">{lbl}</p>
              <p className="mt-1 font-mono-data text-lg font-700" style={{ color: c }}>{fmtCAD(val)}</p>
              <p className="mt-0.5 text-[10px] text-slate-400">{sub}</p>
            </div>
          ))}
        </div>
        <div>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chart} margin={{ left: 4, right: 8 }} barGap={3}>
              <CartesianGrid stroke="#EEF2F7" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }} axisLine={false} tickLine={false} width={40} />
              <Tooltip content={<Tip />} />
              <Bar dataKey="Salaires actuels" fill="#64748B" radius={[3, 3, 0, 0]} maxBarSize={26} />
              <Bar dataKey="Budget CA" fill={BLUE} radius={[3, 3, 0, 0]} maxBarSize={26} />
              <Bar dataKey="Revue 1" fill={VIOLET} radius={[3, 3, 0, 0]} maxBarSize={26} />
              <Bar dataKey="Revue 2" fill={ORANGE} radius={[3, 3, 0, 0]} maxBarSize={26} />
            </BarChart>
          </ResponsiveContainer>
          <p className="mt-2 text-[11px] text-slate-500">Budget CA vs Salaires actuels : <b className="text-[#2563EB]">{dCA >= 0 ? "+" : ""}{dCA.toFixed(1)}%</b></p>
        </div>
      </div>
    </div>
  );
}

function Evolution({ evo }) {
  const data = evo.years.map((y) => ({ year: String(y.year), "Salaires actuels": y.actuel, "Budget CA": y.ca, "Revue 1": y.revue1, "Revue 2": y.revue2 }));
  return (
    <div className="card p-6" data-testid="evolution-card">
      <h3 className="mb-5 flex items-center gap-2 text-sm font-700"><TrendingUp size={16} className="text-[#14B8A6]" /> Évolution pluriannuelle de la masse salariale</h3>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ left: 4, right: 8 }} barGap={3}>
          <CartesianGrid stroke="#EEF2F7" vertical={false} />
          <XAxis dataKey="year" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }} axisLine={false} tickLine={false} />
          <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }} axisLine={false} tickLine={false} width={40} />
          <Tooltip content={<Tip />} />
          <Bar dataKey="Salaires actuels" fill="#64748B" radius={[3, 3, 0, 0]} maxBarSize={30} />
          <Bar dataKey="Budget CA" fill={BLUE} radius={[3, 3, 0, 0]} maxBarSize={30} />
          <Bar dataKey="Revue 1" fill={VIOLET} radius={[3, 3, 0, 0]} maxBarSize={30} />
          <Bar dataKey="Revue 2" fill={ORANGE} radius={[3, 3, 0, 0]} maxBarSize={30} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function EmployeesKpi({ k }) {
  const sx = k.sex_counts || {};
  const typeRows = [["CCQ", k.ccq_count, "#2563EB"], ["Non-CCQ", k.non_ccq_count, "#64748B"], ["Stagiaire", k.stagiaire_count, "#F59E0B"]];
  const sexRows = [["Masculin", sx.Masculin], ["Féminin", sx.Féminin], ["Autre", sx.Autre], ["Non spéc.", sx["Non spécifié"]]];
  return (
    <div className="card p-5" data-testid="kpi-employes">
      <div className="flex items-start justify-between">
        <span className="text-[11px] font-600 uppercase tracking-widest text-slate-500">Employés actifs</span>
        <span className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ backgroundColor: BLUE + "1a", color: BLUE }}><Users size={18} /></span>
      </div>
      <p className="mt-2 font-mono-data text-2xl font-700 tracking-tight lg:text-3xl">{k.headcount}</p>
      <div className="mt-3 grid grid-cols-3 gap-1.5">
        {typeRows.map(([lbl, val, c]) => (
          <div key={lbl} className="rounded-md bg-slate-50 px-2 py-1.5 text-center" data-testid={`emp-type-${lbl}`}>
            <p className="font-mono-data text-sm font-700" style={{ color: c }}>{val ?? 0}</p>
            <p className="text-[9px] font-600 uppercase leading-tight text-slate-400">{lbl}</p>
          </div>
        ))}
      </div>
      <div className="mt-1.5 grid grid-cols-4 gap-1.5">
        {sexRows.map(([lbl, val]) => (
          <div key={lbl} className="rounded-md bg-slate-50 px-1 py-1.5 text-center" data-testid={`emp-sex-${lbl}`}>
            <p className="font-mono-data text-sm font-700 text-slate-700">{val ?? 0}</p>
            <p className="text-[9px] font-600 uppercase leading-tight text-slate-400">{lbl}</p>
          </div>
        ))}
      </div>
      <p className="mt-1.5 text-[9px] uppercase tracking-wide text-slate-400">Sexe à la naissance</p>
    </div>
  );
}

function SexDistribution({ b }) {
  const sc = b.kpis.sex_counts || {};
  const pieData = SEX_CATS.map((s) => ({ name: s, value: sc[s === "Non spécifié" ? "Non spécifié" : s] || 0 })).filter((d) => d.value > 0);
  const depts = (b.sex_by_department || []).filter((d) => d.total > 0);
  return (
    <div className="card p-5" data-testid="chart-sex">
      <h3 className="mb-4 flex items-center gap-2 text-sm font-700"><PieIcon size={16} className="text-[#EC4899]" /> Répartition par sexe à la naissance</h3>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <ResponsiveContainer width="100%" height={170}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={44} outerRadius={70} paddingAngle={2} isAnimationActive={false}>
                {pieData.map((d, i) => <Cell key={i} fill={SEX_COLORS[d.name]} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-1 grid grid-cols-2 gap-1">
            {SEX_CATS.map((s) => (
              <div key={s} className="flex items-center justify-between text-[10px]">
                <span className="flex items-center gap-1 text-slate-500"><span className="h-2 w-2 rounded-sm" style={{ background: SEX_COLORS[s] }} />{s}</span>
                <span className="font-mono-data font-700">{sc[s] || 0}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="lg:col-span-2">
          <p className="mb-1.5 text-[10px] font-600 uppercase tracking-wide text-slate-400">Par département</p>
          <div className="max-h-[220px] overflow-y-auto">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-white">
                <tr className="text-slate-400">
                  <th className="px-2 py-1 text-left font-600">Dépt</th>
                  {SEX_CATS.map((s) => <th key={s} className="px-1.5 py-1 text-right font-600" style={{ color: SEX_COLORS[s] }}>{s === "Non spécifié" ? "N/S" : s.slice(0, 3)}</th>)}
                  <th className="px-1.5 py-1 text-right font-700 text-slate-600">Tot.</th>
                </tr>
              </thead>
              <tbody className="font-mono-data">
                {depts.map((d) => (
                  <tr key={d.department} className="border-t border-slate-100" data-testid={`sex-dept-${d.department}`}>
                    <td className="px-2 py-1 text-left"><b className="text-slate-700">{d.department}</b> <span className="text-slate-400">{d.label}</span></td>
                    {SEX_CATS.map((s) => <td key={s} className="px-1.5 py-1 text-right">{d[s] || 0}</td>)}
                    <td className="px-1.5 py-1 text-right font-700 text-slate-700">{d.total}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function DashboardBody({ b }) {
  const k = b.kpis;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <EmployeesKpi k={k} />
        <Kpi testId="kpi-masse" label="Masse salariale" value={fmtCAD(k.masse_salariale)} sub="total charges salariales" icon={DollarSign} tint={TEAL} />
        <Kpi testId="kpi-budget-global" label="Budget global" value={fmtCAD(k.budget_global)} sub="avec charges sociales" icon={Wallet} tint="#8B5CF6" />
        <Kpi testId="kpi-salaire-moyen" label="Salaire moyen" value={fmtCAD(k.salaire_moyen)} sub="par employé" icon={TrendingUp} tint={ORANGE} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card p-6 lg:col-span-2" data-testid="chart-departments">
          <h3 className="mb-5 flex items-center gap-2 text-sm font-700"><BarChart3 size={16} className="text-[#2563EB]" /> Budget par département</h3>
          <ResponsiveContainer width="100%" height={Math.max(240, b.by_department.length * 46)}>
            <BarChart data={b.by_department} layout="vertical" margin={{ left: 8, right: 16 }} barGap={2}>
              <CartesianGrid stroke="#EEF2F7" horizontal={false} />
              <XAxis type="number" tickFormatter={(v) => `${Math.round(v / 1000)}k`} tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }} axisLine={false} tickLine={false} />
              <YAxis type="category" dataKey="department" width={44} tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#64748B" }} axisLine={false} tickLine={false} />
              <Tooltip cursor={{ fill: "rgba(0,0,0,.03)" }} content={<Tip />} />
              <Bar dataKey="salaire" name="Salaire" fill={NAVY} radius={[0, 4, 4, 0]} maxBarSize={12} />
              <Bar dataKey="budget" name="Budget total" fill={TEAL} radius={[0, 4, 4, 0]} maxBarSize={12} />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-3 flex gap-4 text-[11px] text-slate-500">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: NAVY }} /> Salaire</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: TEAL }} /> Budget total</span>
          </div>
        </div>

        <div className="card p-6" data-testid="chart-types">
          <h3 className="mb-5 flex items-center gap-2 text-sm font-700"><PieIcon size={16} className="text-[#2563EB]" /> Types d'emploi</h3>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart>
              <Pie data={b.by_type} dataKey="total" nameKey="type" cx="50%" cy="50%" innerRadius={58} outerRadius={92} paddingAngle={2} isAnimationActive={false}>
                {b.by_type.map((t, i) => <Cell key={i} fill={TYPE_COLORS[t.type] || "#94A3B8"} />)}
              </Pie>
              <Tooltip content={<Tip />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-2 space-y-1.5">
            {b.by_type.map((t) => (
              <div key={t.type} className="flex items-center justify-between text-[11px]">
                <span className="flex items-center gap-1.5 text-slate-500"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: TYPE_COLORS[t.type] || "#94A3B8" }} />{t.type}</span>
                <span className="font-mono-data">{fmtCAD(t.total)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <SexDistribution b={b} />

      <div className="card p-6" data-testid="chart-monthly">
        <div className="mb-4 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-700"><Calendar size={16} className="text-[#2563EB]" /> Ventilation mensuelle — paie hebdomadaire réelle</h3>
          <span className="font-mono-data text-xs text-slate-500">Total avec charges : <b className="text-slate-800">{fmtCAD(b.totals.budget_total)}</b></span>
        </div>
        <div className="mb-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-400">
                <th className="px-2 py-1.5 text-left font-600"></th>
                {b.monthly.map((m) => <th key={m.month} className="px-2 py-1.5 text-center font-600">{m.month}</th>)}
                <th className="px-2 py-1.5 text-center font-700 text-slate-700">Total</th>
              </tr>
            </thead>
            <tbody className="font-mono-data">
              {[
                ["Sem. paie", "sem_paie", (m) => m.sem_paie],
                ["Jours std", "jours_std", (m) => m.jours_std],
                ["Jours CCQ", "jours_ccq", (m) => m.jours_ccq],
              ].map(([lbl, key, get]) => (
                <tr key={key} className="border-t border-slate-100">
                  <td className="px-2 py-1.5 text-slate-500">{lbl}</td>
                  {b.monthly.map((m) => <td key={m.month} className="px-2 py-1.5 text-center">{get(m)}</td>)}
                  <td className="px-2 py-1.5 text-center font-700">{b.monthly.reduce((s, m) => s + get(m), 0)}</td>
                </tr>
              ))}
              <tr className="border-t border-slate-200 bg-slate-50">
                <td className="px-2 py-1.5 font-700 text-slate-700">Total + charges</td>
                {b.monthly.map((m) => <td key={m.month} className="px-2 py-1.5 text-center text-[#0E9488]">{fmtCAD(m.total)}</td>)}
                <td className="px-2 py-1.5 text-center font-700">{fmtCAD(b.totals.budget_total)}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={b.monthly} margin={{ left: 4, right: 4 }}>
            <CartesianGrid stroke="#EEF2F7" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#94A3B8" }} axisLine={false} tickLine={false} width={40} />
            <Tooltip cursor={{ fill: "rgba(0,0,0,.03)" }} content={<Tip />} />
            <Bar dataKey="salaires" name="Salaires" stackId="a" fill={NAVY} maxBarSize={40} />
            <Bar dataKey="charges" name="Charges sociales" stackId="a" fill={TEAL} radius={[3, 3, 0, 0]} maxBarSize={40} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-6" data-testid="decomposition">
          <h3 className="mb-5 flex items-center gap-2 text-sm font-700"><Layers size={16} className="text-[#2563EB]" /> Décomposition du budget</h3>
          <div className="space-y-3.5">
            {b.decomposition.map((d) => (
              <div key={d.label}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span className="text-slate-600">{d.label}</span>
                  <span className="font-mono-data"><b>{fmtCAD(d.value)}</b> <span className="text-slate-400">{d.pct}%</span></span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, d.pct)}%`, background: d.color }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="card p-6" data-testid="top5">
          <h3 className="mb-5 flex items-center gap-2 text-sm font-700"><TrendingUp size={16} className="text-[#2563EB]" /> Top 5 — Budget le plus élevé</h3>
          <div className="space-y-3">
            {b.top5.map((t) => (
              <div key={t.rank} className="flex items-center gap-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-xs font-700 text-slate-500">{t.rank}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-600">{t.name}</p>
                  <p className="truncate text-[11px] text-slate-500">{t.title} · {t.department}</p>
                </div>
                <div className="text-right">
                  <p className="font-mono-data text-sm font-700">{fmtCAD(t.total)}</p>
                  <p className="font-mono-data text-[11px] text-slate-400">{fmtCAD(t.base)} base</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
