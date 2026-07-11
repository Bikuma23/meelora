import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../lib/api";

const YearContext = createContext(null);
export const useYear = () => useContext(YearContext);

export function YearProvider({ children }) {
  const [years, setYears] = useState([]);
  const [year, setYear] = useState(null);

  const refresh = () => api.listYears().then((d) => {
    setYears(d.years);
    setYear((y) => (y && d.years.includes(y) ? y : d.active_year));
    return d;
  });
  useEffect(() => {
    refresh().then(async (d) => {
      try { const p = await api.getPreferences(); if (p?.default_year && d.years.includes(p.default_year)) setYear(p.default_year); } catch {}
    });
  }, []);

  const selectYear = async (y) => { const n = Number(y); setYear(n); try { await api.setActiveYear(n); } catch {} api.updatePreferences({ default_year: n }).catch(() => {}); };

  if (!year) return null;
  return (
    <YearContext.Provider value={{ years, year, selectYear, refresh }}>
      {children}
    </YearContext.Provider>
  );
}
