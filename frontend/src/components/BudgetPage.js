import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { fmtCAD } from "../lib/format";
import { Input } from "./ui/input";

const VENTIL = [
  ["salaire_base", "Salaire de base"],
  ["vacances", "Vacances"],
  ["primes", "Primes & Boni"],
  ["avantages", "Avantages sociaux"],
  ["csst", "CSST"],
  ["reer", "RPDB / REER"],
  ["assurance", "Assu. collectives"],
];

const SECTION_COLORS = { actuel: "#09090B", ca: "#0055FF", revue: "#FF4500" };

export default function BudgetPage() {
  const [budget, setBudget] = useState(null);
  const [aug, setAug] = useState({ aug_reg_ca: 5, aug_reg_revue: 3.5, aug_ccq: 3.3333 });
  const [detail, setDetail] = useState("ca");

  useEffect(() => {
    const t = setTimeout(() => {
      api.getBudget({
        aug_reg_ca: aug.aug_reg_ca / 100,
        aug_reg_revue: aug.aug_reg_revue / 100,
        aug_ccq: aug.aug_ccq / 100,
      }).then(setBudget);
    }, 250);
    return () => clearTimeout(t);
  }, [aug]);

  const detailSection = useMemo(
    () => budget?.sections.find((s) => s.key === detail),
    [budget, detail]
  );

  if (!budget) return <p className="font-mono-data text-sm text-[#52525B]">Chargement…</p>;

  return (
    <div className="space-y-5" data-testid="budget-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="font-heading text-2xl font-800 uppercase tracking-tight">Budget Salaires</h2>
          <p className="font-mono-data text-xs text-[#52525B]">Comparatif Salaire Actuel · Budget CA · Budget Revue</p>
        </div>
        <div className="flex flex-wrap items-end gap-3 border border-[#D4D4D8] bg-white p-3">
          {[
            ["aug_reg_ca", "Augm. Réguliers (CA)"],
            ["aug_reg_revue", "Augm. Réguliers (Revue)"],
            ["aug_ccq", "Augm. CCQ (convention)"],
          ].map(([k, lbl]) => (
            <div key={k}>
              <label className="text-[10px] font-600 uppercase tracking-wide text-[#52525B]">{lbl}</label>
              <div className="mt-1 flex items-center gap-1">
                <Input
                  data-testid={`aug-${k}`}
                  type="number"
                  step="0.1"
                  className="w-24 rounded-none font-mono-data"
                  value={aug[k]}
                  onChange={(e) => setAug((p) => ({ ...p, [k]: Number(e.target.value) }))}
                />
                <span className="font-mono-data text-xs text-[#52525B]">%</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Comparatif 3 sections */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {budget.sections.map((s) => (
          <div key={s.key} className="border border-[#D4D4D8] bg-white" data-testid={`budget-section-${s.key}`}>
            <div className="flex items-center justify-between border-b border-[#D4D4D8] px-4 py-3" style={{ borderTopColor: SECTION_COLORS[s.key], borderTopWidth: 3 }}>
              <h3 className="font-heading text-sm font-700 uppercase tracking-tight">{s.label}</h3>
              <span className="font-mono-data text-[11px] text-[#52525B]">
                +{(s.augmentation.regulier * 100).toFixed(1)}% / CCQ +{(s.augmentation.ccq * 100).toFixed(2)}%
              </span>
            </div>
            <div className="divide-y divide-[#F4F4F5]">
              {VENTIL.map(([k, lbl]) => (
                <div key={k} className="flex items-center justify-between px-4 py-2 text-sm">
                  <span className="text-[#52525B]">{lbl}</span>
                  <span className="font-mono-data" data-testid={`budget-${s.key}-${k}`}>{fmtCAD(s.totals[k])}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between px-4 py-3" style={{ backgroundColor: SECTION_COLORS[s.key] }}>
              <span className="font-heading text-xs font-800 uppercase tracking-wide text-white">Budget total</span>
              <span className="font-mono-data text-lg font-600 text-white" data-testid={`budget-${s.key}-total`}>{fmtCAD(s.totals.budget_total)}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Détail par employé */}
      <div className="border border-[#D4D4D8] bg-white">
        <div className="flex items-center gap-px border-b border-[#D4D4D8] bg-[#D4D4D8]">
          {budget.sections.map((s) => (
            <button
              key={s.key}
              data-testid={`detail-tab-${s.key}`}
              onClick={() => setDetail(s.key)}
              className={`px-4 py-2.5 text-xs font-700 uppercase tracking-tight transition-colors ${detail === s.key ? "bg-[#09090B] text-white" : "bg-white text-[#52525B] hover:bg-[#F4F4F5]"}`}
            >
              Détail — {s.label}
            </button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#D4D4D8] text-[11px] uppercase tracking-wider text-[#52525B]">
                <th className="px-3 py-2.5 text-left font-600">#</th>
                <th className="px-3 py-2.5 text-left font-600">Nom</th>
                <th className="px-3 py-2.5 text-left font-600">Type</th>
                <th className="px-3 py-2.5 text-right font-600">Nouveau salaire</th>
                <th className="px-3 py-2.5 text-right font-600">Vacances</th>
                <th className="px-3 py-2.5 text-right font-600">Primes</th>
                <th className="px-3 py-2.5 text-right font-600">Avantages</th>
                <th className="px-3 py-2.5 text-right font-600">CSST</th>
                <th className="px-3 py-2.5 text-right font-600">Coût total</th>
              </tr>
            </thead>
            <tbody>
              {detailSection.lines.map((ln) => (
                <tr key={ln.employee_number} className="border-b border-[#F4F4F5] hover:bg-[#F4F4F5]" data-testid={`detail-row-${ln.employee_number}`}>
                  <td className="px-3 py-2 font-mono-data text-[#52525B]">{String(ln.employee_number).padStart(3, "0")}</td>
                  <td className="px-3 py-2 font-medium">{ln.name}</td>
                  <td className="px-3 py-2">
                    <span className="px-1.5 py-0.5 text-[10px] font-600 uppercase text-white" style={{ backgroundColor: ln.is_ccq ? "#0055FF" : "#09090B" }}>{ln.employment_type}</span>
                  </td>
                  <td className="px-3 py-2 text-right font-mono-data">{fmtCAD(ln.new_salary)}</td>
                  <td className="px-3 py-2 text-right font-mono-data">{fmtCAD(ln.vacation)}</td>
                  <td className="px-3 py-2 text-right font-mono-data">{fmtCAD(ln.primes_total)}</td>
                  <td className="px-3 py-2 text-right font-mono-data">{fmtCAD(ln.avantages)}</td>
                  <td className="px-3 py-2 text-right font-mono-data">{fmtCAD(ln.csst)}</td>
                  <td className="px-3 py-2 text-right font-mono-data font-600">{fmtCAD(ln.total_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
