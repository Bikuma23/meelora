import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useYear } from "../context/YearContext";
import { fmtCAD } from "../lib/format";
import { Button } from "../components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { FileSpreadsheet, FileText, Filter } from "lucide-react";
import { toast } from "sonner";

const VENTIL = [
  ["salaire_base", "Salaire de base"], ["vacances", "Vacances"], ["primes", "Primes & Boni"],
  ["avantages", "Avantages sociaux"], ["csst", "CSST"], ["reer", "RPDB/REER"], ["assurance", "Assu. collectives"],
];
const SCEN = [["actuel", "Salaires actuels"], ["ca", "Budget CA"], ["revue", "Revue Budgétaire"]];

export default function Rapports() {
  const { year, years, selectYear } = useYear();
  const [departments, setDepartments] = useState([]);
  const [dept, setDept] = useState("all");
  const [scenario, setScenario] = useState("ca");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState("");

  useEffect(() => { api.listDepartments().then(setDepartments); }, []);
  useEffect(() => { setData(null); api.getBudget({ year, scenario, ...(dept !== "all" ? { department: dept } : {}) }).then(setData); }, [dept, year, scenario]);

  const download = async (kind, ext) => {
    setBusy(kind);
    try {
      const blob = await api.downloadReport(kind, dept, year, scenario);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url;
      a.download = `rapport_${scenario}_${year}${dept !== "all" ? "_" + dept : ""}.${ext}`; a.click();
      URL.revokeObjectURL(url);
      toast.success(`Rapport ${ext.toUpperCase()} téléchargé`);
    } catch { toast.error("Export échoué"); } finally { setBusy(""); }
  };

  const scopeLabel = useMemo(() => dept === "all" ? "Tous les départements" : departments.find((d) => d.code === dept)?.description || dept, [dept, departments]);

  return (
    <div className="space-y-5" data-testid="rapports-page">
      <div className="card flex flex-wrap items-end justify-between gap-4 p-5">
        <div>
          <p className="flex items-center gap-1.5 text-xs font-700 uppercase tracking-widest text-slate-500"><Filter size={13} /> Portée du rapport</p>
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <div>
              <label className="text-[11px] uppercase text-slate-500">Année</label>
              <Select value={String(year)} onValueChange={(v) => selectYear(v)}><SelectTrigger className="mt-1 w-28" data-testid="report-year"><SelectValue /></SelectTrigger>
                <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent></Select>
            </div>
            <div>
              <label className="text-[11px] uppercase text-slate-500">Catégorie</label>
              <Select value={scenario} onValueChange={setScenario}>
                <SelectTrigger className="mt-1 w-48" data-testid="report-scenario"><SelectValue /></SelectTrigger>
                <SelectContent>{SCEN.map(([k, l]) => <SelectItem key={k} value={k}>{l}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <label className="text-[11px] uppercase text-slate-500">Département</label>
              <Select value={dept} onValueChange={setDept}>
                <SelectTrigger className="mt-1 w-64" data-testid="report-department"><SelectValue /></SelectTrigger>
                <SelectContent className="max-h-64">
                  <SelectItem value="all">Tous les départements</SelectItem>
                  {departments.map((d) => <SelectItem key={d.code} value={d.code}>{d.code} — {d.description}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button data-testid="export-excel-btn" disabled={busy} onClick={() => download("excel", "xlsx")} className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90">
            <FileSpreadsheet size={16} /> Exporter Excel
          </Button>
          <Button data-testid="export-pdf-btn" disabled={busy} onClick={() => download("pdf", "pdf")} className="gap-2 bg-[#EF4444] hover:bg-[#EF4444]/90">
            <FileText size={16} /> Exporter PDF
          </Button>
        </div>
      </div>

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[["Effectif", data.kpis.headcount], ["Masse salariale", fmtCAD(data.totals.salaire_base)],
              ["Budget global", fmtCAD(data.totals.budget_total)], ["Salaire moyen", fmtCAD(data.kpis.salaire_moyen)]].map(([l, v]) => (
              <div key={l} className="card p-4"><p className="text-[11px] font-600 uppercase tracking-wide text-slate-500">{l}</p><p className="mt-1.5 font-mono-data text-lg font-700">{v}</p></div>
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="card p-5">
              <h3 className="mb-3 text-sm font-700">Aperçu — Ventilation ({scopeLabel})</h3>
              <div className="divide-y divide-slate-100">
                {VENTIL.map(([k, l]) => (
                  <div key={k} className="flex justify-between py-1.5 text-sm"><span className="text-slate-500">{l}</span><span className="font-mono-data">{fmtCAD(data.totals[k])}</span></div>
                ))}
                <div className="flex justify-between py-2 text-sm font-700"><span>Budget total</span><span className="font-mono-data text-[#0E9488]">{fmtCAD(data.totals.budget_total)}</span></div>
              </div>
            </div>
            <div className="card p-5">
              <h3 className="mb-3 text-sm font-700">Budget par département</h3>
              <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto">
                {data.by_department.map((d) => (
                  <div key={d.department} className="flex justify-between py-1.5 text-sm">
                    <span className="text-slate-600">{d.department} — {d.label}</span><span className="font-mono-data">{fmtCAD(d.budget)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
