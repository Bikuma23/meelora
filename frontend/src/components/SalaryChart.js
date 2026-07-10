import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import { CATEGORIES, formatCurrency } from "../lib/calculations";

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((s, p) => s + p.value, 0);
  return (
    <div className="border border-[#09090B] bg-white p-3 font-mono-data text-xs shadow-none">
      <p className="mb-2 font-heading text-sm font-700 uppercase">{label}</p>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center justify-between gap-6">
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2" style={{ backgroundColor: p.color }} />
            {CATEGORIES.find((c) => c.key === p.dataKey)?.label}
          </span>
          <span>{formatCurrency(p.value)}</span>
        </div>
      ))}
      <div className="mt-2 flex justify-between border-t border-[#D4D4D8] pt-1.5 font-600">
        <span>TOTAL</span>
        <span>{formatCurrency(total)}</span>
      </div>
    </div>
  );
};

export default function SalaryChart({ data }) {
  return (
    <div className="border border-[#D4D4D8] bg-white p-5" data-testid="salary-chart">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-heading text-sm font-700 uppercase tracking-tight">
          Répartition mensuelle de la masse salariale
        </h2>
        <div className="flex gap-4">
          {CATEGORIES.map((c) => (
            <span key={c.key} className="flex items-center gap-1.5 text-[11px] text-[#52525B]">
              <span className="h-2.5 w-2.5" style={{ backgroundColor: c.color }} />
              {c.trade}
            </span>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="0" stroke="#E4E4E7" vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#52525B" }}
            axisLine={{ stroke: "#D4D4D8" }}
            tickLine={false}
          />
          <YAxis
            tickFormatter={(v) => `${Math.round(v / 1000)}k`}
            tick={{ fontSize: 11, fontFamily: "IBM Plex Mono", fill: "#52525B" }}
            axisLine={false}
            tickLine={false}
            width={44}
          />
          <Tooltip cursor={{ fill: "rgba(0,0,0,0.04)" }} content={<CustomTooltip />} />
          <Legend wrapperStyle={{ display: "none" }} />
          {CATEGORIES.map((c) => (
            <Bar
              key={c.key}
              dataKey={c.key}
              stackId="masse"
              fill={c.color}
              isAnimationActive={false}
              maxBarSize={38}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
