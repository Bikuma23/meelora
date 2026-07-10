import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { fmtCAD } from "../lib/format";
import { motion } from "framer-motion";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";
import { Wallet, Users, HardHat, ShieldCheck } from "lucide-react";

const CTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="border border-[#09090B] bg-white p-2.5 font-mono-data text-xs">
      {label && <p className="mb-1 font-heading uppercase">{label}</p>}
      {payload.map((p, i) => (
        <p key={i}>{p.name}: {fmtCAD(p.value)}</p>
      ))}
    </div>
  );
};

function Kpi({ label, value, sub, accent, icon: Icon, testId }) {
  return (
    <div data-testid={testId} className="flex flex-col justify-between border border-[#D4D4D8] bg-white p-5">
      <div className="flex items-start justify-between">
        <span className="max-w-[70%] text-[11px] font-600 uppercase tracking-widest text-[#52525B]">{label}</span>
        <Icon size={18} style={{ color: accent }} strokeWidth={2} />
      </div>
      <div>
        <p className="mt-4 font-mono-data text-3xl font-600 leading-none tracking-tight lg:text-4xl" style={{ color: accent }}>{value}</p>
        {sub && <p className="mt-2 font-mono-data text-xs text-[#52525B]">{sub}</p>}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [budget, setBudget] = useState(null);

  useEffect(() => { api.getBudget().then(setBudget); }, []);

  if (!budget) return <p className="font-mono-data text-sm text-[#52525B]">Chargement…</p>;
  const d = budget.dashboard;
  const caTotal = d.section_totals.find((s) => s.section === "Budget (CA)")?.total || 0;

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5" data-testid="dashboard-page">
      <div>
        <h2 className="font-heading text-2xl font-800 uppercase tracking-tight">Tableau de bord</h2>
        <p className="font-mono-data text-xs text-[#52525B]">Vue d'ensemble — Budget CA {budget.sections[0] ? "2026" : ""}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        <Kpi testId="kpi-budget-total" label="Budget total (CA)" value={fmtCAD(caTotal)} sub="Masse salariale projetée" accent="#0055FF" icon={Wallet} />
        <Kpi testId="kpi-headcount" label="Effectif total" value={d.headcount} sub={`${d.ccq_count} CCQ · ${d.regulier_count} Réguliers`} accent="#09090B" icon={Users} />
        <Kpi testId="kpi-ccq" label="Employés CCQ" value={d.ccq_count} sub="Convention collective" accent="#FF4500" icon={HardHat} />
        <Kpi testId="kpi-garde" label="Prime de garde moyenne" value={fmtCAD(d.garde_moyenne)} sub="par employé admissible / an" accent="#00C781" icon={ShieldCheck} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="border border-[#D4D4D8] bg-white p-5 lg:col-span-2" data-testid="chart-sections">
          <h3 className="mb-4 font-heading text-sm font-700 uppercase tracking-tight">Comparatif des scénarios budgétaires</h3>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={d.section_totals} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid strokeDasharray="0" stroke="#E4E4E7" vertical={false} />
              <XAxis dataKey="section" tick={{ fontSize: 12, fontFamily: "IBM Plex Mono", fill: "#52525B" }} axisLine={{ stroke: "#D4D4D8" }} tickLine={false} />
              <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#52525B" }} axisLine={false} tickLine={false} width={48} />
              <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} content={<CTip />} />
              <Bar dataKey="total" name="Budget" isAnimationActive={false} maxBarSize={90}>
                {d.section_totals.map((s, i) => (
                  <Cell key={i} fill={["#09090B", "#0055FF", "#FF4500"][i]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="border border-[#D4D4D8] bg-white p-5" data-testid="chart-type">
          <h3 className="mb-4 font-heading text-sm font-700 uppercase tracking-tight">Répartition CCQ / Régulier</h3>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={d.by_type} dataKey="total" nameKey="type" cx="50%" cy="50%" outerRadius={95} isAnimationActive={false}>
                {d.by_type.map((s, i) => (
                  <Cell key={i} fill={s.type === "CCQ" ? "#0055FF" : "#09090B"} />
                ))}
              </Pie>
              <Tooltip content={<CTip />} />
            </PieChart>
          </ResponsiveContainer>
          <div className="mt-2 flex justify-center gap-5">
            {d.by_type.map((s) => (
              <span key={s.type} className="flex items-center gap-1.5 text-[11px] text-[#52525B]">
                <span className="h-2.5 w-2.5" style={{ backgroundColor: s.type === "CCQ" ? "#0055FF" : "#09090B" }} />
                {s.type} · {fmtCAD(s.total)}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="border border-[#D4D4D8] bg-white p-5" data-testid="chart-departments">
        <h3 className="mb-4 font-heading text-sm font-700 uppercase tracking-tight">Coût par département (Budget CA)</h3>
        <ResponsiveContainer width="100%" height={Math.max(220, d.by_department.length * 32)}>
          <BarChart data={d.by_department} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="0" stroke="#E4E4E7" horizontal={false} />
            <XAxis type="number" tickFormatter={(v) => `${Math.round(v / 1000)}k`} tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#52525B" }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="department" width={190} tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#52525B" }} axisLine={false} tickLine={false} />
            <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} content={<CTip />} />
            <Bar dataKey="total" name="Coût" fill="#0055FF" isAnimationActive={false} maxBarSize={22} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </motion.div>
  );
}
