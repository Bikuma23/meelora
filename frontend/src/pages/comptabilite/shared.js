import { useState, useEffect, useCallback } from "react";
import { api } from "../../lib/api";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../../components/ui/select";
import { CalendarDays } from "lucide-react";

export const MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];

export function money(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  const abs = Math.abs(n).toLocaleString("fr-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${abs})` : abs;
}

export function moneyM(v) {
  if (v == null || v === "") return "—";
  const n = Number(v) / 1e6;
  const abs = Math.abs(n).toLocaleString("fr-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${abs})` : abs;
}

export function usePeriods() {
  const [periods, setPeriods] = useState([]);
  const reload = useCallback(() => api.acctPeriods().then(setPeriods).catch(() => {}), []);
  useEffect(() => { reload(); }, [reload]);
  return { periods, reload };
}

export function PeriodSelect({ periods, value, onChange, testId = "acct" }) {
  const years = [...new Set(periods.map((p) => p.year))].sort((a, b) => b - a);
  const [y, m] = value ? value.split("-").map(Number) : [null, null];
  const monthsForYear = periods.filter((p) => p.year === y).sort((a, b) => a.month - b.month);
  const setYear = (ny) => {
    ny = Number(ny);
    const monthsY = periods.filter((p) => p.year === ny).map((p) => p.month).sort((a, b) => a - b);
    const nm = monthsY.includes(m) ? m : monthsY[0];
    if (nm) onChange(`${ny}-${String(nm).padStart(2, "0")}`);
  };
  const setMonth = (nm) => onChange(`${y}-${String(Number(nm)).padStart(2, "0")}`);
  return (
    <div className="flex items-center gap-2">
      <CalendarDays size={15} className="text-[#063044]" />
      <Select value={y ? String(y) : ""} onValueChange={setYear}>
        <SelectTrigger data-testid={`${testId}-year-select`} className="w-24"><SelectValue placeholder="Année" /></SelectTrigger>
        <SelectContent>
          {years.length === 0 && <SelectItem value="none" disabled>—</SelectItem>}
          {years.map((yy) => <SelectItem key={yy} value={String(yy)} data-testid={`${testId}-year-opt-${yy}`}>{yy}</SelectItem>)}
        </SelectContent>
      </Select>
      <Select value={m ? String(m) : ""} onValueChange={setMonth}>
        <SelectTrigger data-testid={`${testId}-month-select`} className="w-40"><SelectValue placeholder="Mois" /></SelectTrigger>
        <SelectContent>
          {monthsForYear.length === 0 && <SelectItem value="none" disabled>—</SelectItem>}
          {monthsForYear.map((p) => (
            <SelectItem key={p.month} value={String(p.month)} data-testid={`${testId}-month-opt-${p.month}`}>
              {MONTHS[p.month - 1]} {p.locked ? "🔒" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
