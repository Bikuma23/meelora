import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useYear } from "../context/YearContext";
import { useAuth } from "../context/AuthContext";
import { fmtCAD } from "../lib/format";
import BudgetFicheDialog from "../components/BudgetFicheDialog";
import BudgetDetailDialog from "../components/BudgetDetailDialog";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Pencil, Lock, Unlock, ShieldCheck, TrendingUp, ChevronUp, ChevronDown, ChevronsUpDown, Search } from "lucide-react";
import { toast } from "sonner";

const SCENARIOS = [["ca", "Budget CA"], ["revue1", "Revue Budgétaire 1"], ["revue2", "Revue Budgétaire 2"]];
const LABEL = Object.fromEntries(SCENARIOS);
const TYPE_LABELS = { "Régulier temps plein": "Rég. Temps Plein", "Régulier temps partiel": "Rég. Temps Partiel" };
const typeLabel = (t) => TYPE_LABELS[t] || t;
const COLS = [
  { key: "employee_number", label: "#", align: "left" },
  { key: "name", label: "Nom", align: "left" },
  { key: "department", label: "Dépt", align: "left" },
  { key: "employment_type", label: "Type", align: "left" },
  { key: "new_salary", label: "Nouveau salaire", align: "right" },
  { key: "vacation", label: "Vacances", align: "right" },
  { key: "primes_total", label: "Primes", align: "right" },
  { key: "salaire_brut", label: "Salaire brut total", align: "right" },
  { key: "avantages", label: "Avantages", align: "right" },
  { key: "total_budgeted", label: "Coût total", align: "right" },
];

export default function SalairesBudget() {
  const { year } = useYear();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [scenario, setScenario] = useState("ca");
  const [b, setB] = useState(null);
  const [locks, setLocks] = useState({});
  const [fiche, setFiche] = useState({ open: false, line: null });
  const [detail, setDetail] = useState({ open: false, line: null });
  const [augCcq, setAugCcq] = useState("");
  const [augStd, setAugStd] = useState("");
  const [applying, setApplying] = useState(false);
  const [sort, setSort] = useState({ key: "employee_number", dir: "asc" });
  const [tableQuery, setTableQuery] = useState("");

  const toggleSort = (key) => setSort((s) => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });

  const lockKey = `${year}:${scenario}`;
  const lockInfo = locks[lockKey];
  const locked = !!lockInfo?.locked;
  const canEdit = isAdmin || !locked;

  const load = () => api.getBudget({ year, scenario }).then(setB);
  const loadLocks = () => api.getLocks({ year }).then(setLocks);
  const loadHypo = () => api.getHypotheses(year).then((h) => {
    setAugCcq(String(+(h.augmentation_ccq * 100).toFixed(3)));
    setAugStd(String(+(h.augmentation_autres * 100).toFixed(3)));
  }).catch(() => {});
  useEffect(() => { setB(null); load(); loadLocks(); loadHypo(); /* eslint-disable-next-line */ }, [year, scenario]);
  if (!b) return <p className="font-mono-data text-sm text-slate-500">Chargement…</p>;

  const applyAug = async () => {
    if (!canEdit) { toast.error("Budget verrouillé — seul un administrateur peut modifier."); return; }
    setApplying(true);
    try {
      const r = await api.applyAugmentation({ ccq_pct: Number(augCcq) || 0, std_pct: Number(augStd) || 0 }, { year, scenario });
      toast.success(`Augmentation appliquée à ${r.updated} employé(s)`);
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Application impossible"); }
    finally { setApplying(false); }
  };

  const toggleLock = async () => {
    try {
      await api.setLock({ year, scenario, locked: !locked });
      toast.success(!locked ? `${LABEL[scenario]} ${year} verrouillé` : `${LABEL[scenario]} ${year} déverrouillé`);
      loadLocks();
    } catch (e) { toast.error(e.response?.data?.detail || "Action impossible"); }
  };

  const q = tableQuery.trim().toLowerCase();
  const filteredLines = !q ? b.lines : b.lines.filter((l) => {
    const hay = [String(l.employee_number).padStart(3, "0"), l.name, l.department, l.title,
      l.is_ccq ? "ccq" : (TYPE_LABELS[l.employment_type] || l.employment_type),
      fmtCAD(l.new_salary), fmtCAD(l.vacation), fmtCAD(l.primes_total), fmtCAD(l.salaire_brut), fmtCAD(l.avantages), fmtCAD(l.total_budgeted)]
      .join(" ").toLowerCase();
    return hay.includes(q);
  });
  const sortedLines = [...filteredLines].sort((a, c) => {
    const va = a[sort.key], vc = c[sort.key];
    const cmp = typeof va === "string" ? va.localeCompare(vc, "fr") : (va - vc);
    return sort.dir === "asc" ? cmp : -cmp;
  });

  const cards = [
    ["Salaire de base", b.totals.salaire_base, "#2563EB"],
    ["Vacances", b.totals.vacances, "#14B8A6"],
    ["Primes & Boni", b.totals.primes, "#F59E0B"],
    ["Avantages soc.", b.totals.avantages, "#8B5CF6"],
    ["Budget total", b.totals.budget_total, "#0E1526"],
  ];

  return (
    <div className="space-y-5" data-testid="budget-page">
      <div className="card flex flex-wrap items-center justify-between gap-3 p-3">
        <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1" data-testid="scenario-toggle">
          {SCENARIOS.map(([k, lbl]) => (
            <button key={k} data-testid={`scenario-${k}`} onClick={() => setScenario(k)}
              className={`rounded-md px-3.5 py-1.5 text-xs font-700 transition-colors ${scenario === k ? "bg-white text-[#0E1526] shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
              {lbl}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3">
          {locked && (
            <span className="flex items-center gap-1.5 rounded-full bg-red-50 px-3 py-1 text-xs font-700 text-red-600" data-testid="lock-badge">
              <Lock size={13} /> Verrouillé{lockInfo?.locked_by ? ` · ${lockInfo.locked_by}${lockInfo.locked_at ? " le " + new Date(lockInfo.locked_at).toLocaleDateString("fr-CA") : ""}` : ""}
            </span>
          )}
          {isAdmin && (
            <Button variant="outline" size="sm" onClick={toggleLock} data-testid="lock-toggle-btn"
              className={`gap-1.5 ${locked ? "border-red-200 text-red-600 hover:bg-red-50" : "border-emerald-200 text-emerald-700 hover:bg-emerald-50"}`}>
              {locked ? <><Unlock size={14} /> Déverrouiller</> : <><ShieldCheck size={14} /> Verrouiller le budget</>}
            </Button>
          )}
        </div>
      </div>

      {locked && !isAdmin && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs text-red-700" data-testid="lock-notice">
          Ce budget est verrouillé. Seul un administrateur peut y apporter des modifications.
        </div>
      )}

      <div className="card flex flex-wrap items-end gap-4 p-4" data-testid="global-aug-panel">
        <div className="flex items-center gap-2 self-center pr-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#2563EB1a] text-[#2563EB]"><TrendingUp size={16} /></span>
          <div>
            <p className="text-sm font-700 leading-tight">Augmentation globale</p>
            <p className="text-[11px] text-slate-500">Appliquée à tous — {LABEL[scenario]} {year}</p>
          </div>
        </div>
        <div className="w-28">
          <Label className="text-[11px] uppercase text-slate-500">CCQ (%)</Label>
          <Input data-testid="global-aug-ccq" type="number" step="0.1" disabled={!canEdit} className="mt-1 font-mono-data" value={augCcq} onChange={(e) => setAugCcq(e.target.value)} />
        </div>
        <div className="w-28">
          <Label className="text-[11px] uppercase text-slate-500">Standard (%)</Label>
          <Input data-testid="global-aug-std" type="number" step="0.1" disabled={!canEdit} className="mt-1 font-mono-data" value={augStd} onChange={(e) => setAugStd(e.target.value)} />
        </div>
        <Button data-testid="global-aug-apply" onClick={applyAug} disabled={!canEdit || applying} className="gap-1.5 bg-[#2563EB] hover:bg-[#2563EB]/90">
          <TrendingUp size={15} /> {applying ? "Application…" : "Appliquer à tous"}
        </Button>
        <p className="w-full text-[11px] text-slate-400 sm:w-auto sm:flex-1 sm:text-right">Écrase l'augmentation de chaque employé pour ce scénario. Vous pourrez ensuite ajuster individuellement via la fiche.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {cards.map(([lbl, val, c]) => (
          <div key={lbl} className="card p-4">
            <p className="text-[11px] font-600 uppercase tracking-wide text-slate-500">{lbl}</p>
            <p className="mt-1.5 font-mono-data text-lg font-700" style={{ color: c }}>{fmtCAD(val)}</p>
          </div>
        ))}
      </div>

      <div className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3.5">
          <div>
            <h3 className="text-sm font-700">Saisie & calculs par employé — {LABEL[scenario]} {year}</h3>
            <p className="text-xs text-slate-500">{canEdit ? "Cliquez sur une ligne pour voir le détail, ou « modifier » pour ajuster la fiche." : "Cliquez sur une ligne pour voir le détail. Budget verrouillé — consultation seule."}</p>
          </div>
          <div className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-2">
            <Search size={15} className="text-slate-400" />
            <input data-testid="budget-table-search" className="w-64 bg-transparent text-sm outline-none"
              placeholder="Rechercher (nom, dépt, type, montant…)" value={tableQuery} onChange={(e) => setTableQuery(e.target.value)} />
          </div>
        </div>
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
                {COLS.map((col) => (
                  <th key={col.key} data-testid={`sort-${col.key}`} onClick={() => toggleSort(col.key)}
                    className={`cursor-pointer select-none px-4 py-3 font-600 hover:text-slate-600 ${col.align === "right" ? "text-right" : "text-left"}`}>
                    <span className={`inline-flex items-center gap-1 ${col.align === "right" ? "flex-row-reverse" : ""}`}>
                      {col.label}
                      {sort.key === col.key
                        ? (sort.dir === "asc" ? <ChevronUp size={13} className="text-[#2563EB]" /> : <ChevronDown size={13} className="text-[#2563EB]" />)
                        : <ChevronsUpDown size={12} className="opacity-40" />}
                    </span>
                  </th>
                ))}
                <th className="px-4 py-3 text-right font-600">Modifier</th>
              </tr>
            </thead>
            <tbody>
              {sortedLines.map((ln) => (
                <tr key={ln.employee_number} onClick={() => setDetail({ open: true, line: ln })} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50" data-testid={`budget-row-${ln.employee_number}`}>
                  <td className="px-4 py-2.5 font-mono-data text-slate-400">{String(ln.employee_number).padStart(3, "0")}</td>
                  <td className="px-4 py-2.5 font-600">{ln.name}{ln.overridden && <span className="ml-2 rounded bg-[#14B8A61a] px-1.5 py-0.5 text-[9px] font-700 uppercase text-[#0E9488]">Ajusté</span>}{ln.prorated && <span className="ml-2 rounded bg-[#F59E0B1a] px-1.5 py-0.5 text-[9px] font-700 uppercase text-[#B45309]">Pro-rata {ln.months_active} mois</span>}</td>
                  <td className="px-4 py-2.5 font-mono-data text-slate-500">{ln.department}</td>
                  <td className="px-4 py-2.5"><span className="rounded px-1.5 py-0.5 text-[10px] font-600 uppercase text-white" style={{ backgroundColor: ln.is_ccq ? "#2563EB" : "#64748B" }}>{ln.is_ccq ? "CCQ" : typeLabel(ln.employment_type)}</span></td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(ln.new_salary)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(ln.vacation)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(ln.primes_total)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data font-600" style={{ color: "#0E9488" }}>{fmtCAD(ln.salaire_brut)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(ln.avantages)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data font-700">{fmtCAD(ln.total_budgeted)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button data-testid={`edit-line-${ln.employee_number}`} disabled={!canEdit} onClick={(ev) => { ev.stopPropagation(); setFiche({ open: true, line: ln }); }}
                      className="p-1.5 text-slate-400 hover:text-[#2563EB] disabled:cursor-not-allowed disabled:opacity-30">
                      {canEdit ? <Pencil size={15} /> : <Lock size={15} />}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t-2 border-slate-300 bg-slate-50 text-sm font-700" data-testid="budget-total-row">
                <td className="px-4 py-3" colSpan={4}>TOTAL — {sortedLines.length} employé(s)</td>
                <td className="px-4 py-3 text-right font-mono-data">{fmtCAD(sortedLines.reduce((s, l) => s + l.new_salary, 0))}</td>
                <td className="px-4 py-3 text-right font-mono-data">{fmtCAD(sortedLines.reduce((s, l) => s + l.vacation, 0))}</td>
                <td className="px-4 py-3 text-right font-mono-data">{fmtCAD(sortedLines.reduce((s, l) => s + l.primes_total, 0))}</td>
                <td className="px-4 py-3 text-right font-mono-data" style={{ color: "#0E9488" }}>{fmtCAD(sortedLines.reduce((s, l) => s + l.salaire_brut, 0))}</td>
                <td className="px-4 py-3 text-right font-mono-data">{fmtCAD(sortedLines.reduce((s, l) => s + l.avantages, 0))}</td>
                <td className="px-4 py-3 text-right font-mono-data">{fmtCAD(sortedLines.reduce((s, l) => s + l.total_budgeted, 0))}</td>
                <td className="px-4 py-3"></td>
              </tr>
            </tfoot>
          </table>
        </div>

        <div className="divide-y divide-slate-100 md:hidden" data-testid="budget-cards">
          {sortedLines.map((ln) => (
            <div key={ln.employee_number} onClick={() => setDetail({ open: true, line: ln })} className="cursor-pointer p-4 active:bg-slate-50" data-testid={`budget-card-${ln.employee_number}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-700">{ln.name}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className="font-mono-data text-[11px] text-slate-400">#{String(ln.employee_number).padStart(3, "0")}</span>
                    <span className="font-mono-data text-[11px] text-slate-400">· Dépt {ln.department}</span>
                    <span className="rounded px-1.5 py-0.5 text-[9px] font-600 uppercase text-white" style={{ backgroundColor: ln.is_ccq ? "#2563EB" : "#64748B" }}>{ln.is_ccq ? "CCQ" : typeLabel(ln.employment_type)}</span>
                    {ln.overridden && <span className="rounded bg-[#14B8A61a] px-1.5 py-0.5 text-[9px] font-700 uppercase text-[#0E9488]">Ajusté</span>}
                    {ln.prorated && <span className="rounded bg-[#F59E0B1a] px-1.5 py-0.5 text-[9px] font-700 uppercase text-[#B45309]">Pro-rata {ln.months_active}m</span>}
                  </div>
                </div>
                <button data-testid={`edit-line-card-${ln.employee_number}`} disabled={!canEdit} onClick={(ev) => { ev.stopPropagation(); setFiche({ open: true, line: ln }); }}
                  className="shrink-0 rounded-lg border border-slate-200 p-2 text-slate-400 hover:text-[#2563EB] disabled:opacity-30">
                  {canEdit ? <Pencil size={15} /> : <Lock size={15} />}
                </button>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[13px]">
                {[["Nouveau salaire", ln.new_salary], ["Vacances", ln.vacation], ["Primes", ln.primes_total], ["Avantages", ln.avantages]].map(([l, v]) => (
                  <div key={l} className="flex justify-between"><span className="text-slate-500">{l}</span><span className="font-mono-data">{fmtCAD(v)}</span></div>
                ))}
                <div className="col-span-2 mt-1 flex justify-between border-t border-slate-100 pt-1.5"><span className="font-600 text-slate-600">Salaire brut</span><span className="font-mono-data font-600" style={{ color: "#0E9488" }}>{fmtCAD(ln.salaire_brut)}</span></div>
                <div className="col-span-2 flex justify-between"><span className="font-700">Coût total</span><span className="font-mono-data font-700">{fmtCAD(ln.total_budgeted)}</span></div>
              </div>
            </div>
          ))}
          <div className="flex items-center justify-between bg-slate-50 px-4 py-3 text-sm font-700" data-testid="budget-cards-total">
            <span>TOTAL — {sortedLines.length} employé(s)</span>
            <span className="font-mono-data">{fmtCAD(sortedLines.reduce((s, l) => s + l.total_budgeted, 0))}</span>
          </div>
        </div>
      </div>

      {fiche.open && fiche.line && (
        <BudgetFicheDialog open={fiche.open} onOpenChange={(v) => setFiche((p) => ({ ...p, open: v }))} line={fiche.line} year={year} scenario={scenario} locks={locks} isAdmin={isAdmin} onSaved={load} />
      )}
      {detail.open && detail.line && (
        <BudgetDetailDialog open={detail.open} onOpenChange={(v) => setDetail((p) => ({ ...p, open: v }))} line={detail.line} year={year} scenario={scenario}
          canEdit={canEdit} onEdit={(ln) => setFiche({ open: true, line: ln })} />
      )}
    </div>
  );
}
