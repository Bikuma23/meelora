import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useYear } from "../context/YearContext";
import { fmtCAD } from "../lib/format";
import BudgetFicheDialog from "../components/BudgetFicheDialog";
import { Pencil } from "lucide-react";

const SCENARIOS = [["ca", "Budget CA"], ["revue", "Revue Budgétaire"]];

export default function SalairesBudget() {
  const { year } = useYear();
  const [scenario, setScenario] = useState("ca");
  const [b, setB] = useState(null);
  const [fiche, setFiche] = useState({ open: false, line: null });
  const load = () => api.getBudget({ year, scenario }).then(setB);
  useEffect(() => { setB(null); load(); /* eslint-disable-next-line */ }, [year, scenario]);
  if (!b) return <p className="font-mono-data text-sm text-slate-500">Chargement…</p>;

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
        <p className="text-xs text-slate-500">
          {scenario === "ca"
            ? "Budget CA : bâti à partir du salaire actuel + augmentations/primes."
            : "Revue Budgétaire : ajustez primes, augmentations et vacances sans toucher au Budget CA."}
        </p>
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
        <div className="border-b border-slate-200 px-5 py-3.5">
          <h3 className="text-sm font-700">Saisie & calculs par employé</h3>
          <p className="text-xs text-slate-500">Cliquez « modifier » pour ajuster la fiche Salaires & Budget d'un employé.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
                <th className="px-4 py-3 text-left font-600">#</th>
                <th className="px-4 py-3 text-left font-600">Nom</th>
                <th className="px-4 py-3 text-left font-600">Type</th>
                <th className="px-4 py-3 text-right font-600">Nouveau salaire</th>
                <th className="px-4 py-3 text-right font-600">Vacances</th>
                <th className="px-4 py-3 text-right font-600">Primes</th>
                <th className="px-4 py-3 text-right font-600">Avantages</th>
                <th className="px-4 py-3 text-right font-600">Coût total</th>
                <th className="px-4 py-3 text-right font-600">Modifier</th>
              </tr>
            </thead>
            <tbody>
              {b.lines.map((ln) => (
                <tr key={ln.employee_number} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`budget-row-${ln.employee_number}`}>
                  <td className="px-4 py-2.5 font-mono-data text-slate-400">{String(ln.employee_number).padStart(3, "0")}</td>
                  <td className="px-4 py-2.5 font-600">{ln.name}{ln.overridden && <span className="ml-2 rounded bg-[#14B8A61a] px-1.5 py-0.5 text-[9px] font-700 uppercase text-[#0E9488]">Ajusté</span>}</td>
                  <td className="px-4 py-2.5"><span className="rounded px-1.5 py-0.5 text-[10px] font-600 uppercase text-white" style={{ backgroundColor: ln.is_ccq ? "#2563EB" : "#64748B" }}>{ln.is_ccq ? "CCQ" : ln.employment_type}</span></td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(ln.new_salary)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(ln.vacation)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(ln.primes_total)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(ln.avantages)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data font-700">{fmtCAD(ln.total_cost)}</td>
                  <td className="px-4 py-2.5 text-right">
                    <button data-testid={`edit-line-${ln.employee_number}`} onClick={() => setFiche({ open: true, line: ln })} className="p-1.5 text-slate-400 hover:text-[#2563EB]"><Pencil size={15} /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {fiche.open && fiche.line && (
        <BudgetFicheDialog open={fiche.open} onOpenChange={(v) => setFiche((p) => ({ ...p, open: v }))} line={fiche.line} year={year} scenario={scenario} onSaved={load} />
      )}
    </div>
  );
}
