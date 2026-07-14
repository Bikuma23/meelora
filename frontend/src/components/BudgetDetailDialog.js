import { fmtCAD } from "../lib/format";
import { api } from "../lib/api";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../components/ui/dialog";
import { Pencil, FileDown } from "lucide-react";
import { Button } from "../components/ui/button";
import { toast } from "sonner";
import { useState } from "react";

function Row({ label, value, strong, accent }) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5 text-sm">
      <span className={strong ? "text-xs font-700 uppercase tracking-wide" : "text-slate-500"}>{label}</span>
      <span className="font-mono-data" style={accent ? { color: accent } : {}}>{value}</span>
    </div>
  );
}

const SCEN_LABEL = { ca: "Budget CA", revue1: "Revue Budgétaire 1", revue2: "Revue Budgétaire 2" };

export default function BudgetDetailDialog({ open, onOpenChange, line, year, scenario, onEdit, canEdit, scenarioOptions, onScenarioChange, baselineTotal }) {
  const [busy, setBusy] = useState(false);
  if (!line) return null;
  const ccq = line.is_ccq;
  const exportPdf = async () => {
    setBusy(true);
    try {
      const blob = await api.downloadEmployeeFiche(line.employee_id, year, scenario);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url;
      a.download = `fiche_${line.name.replace(/\s+/g, "_")}_${scenario}_${year}.pdf`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Fiche PDF téléchargée");
    } catch { toast.error("Export PDF échoué"); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto" data-testid="budget-detail-dialog">
        <DialogHeader>
          <DialogTitle>{line.name} — #{String(line.employee_number).padStart(3, "0")}</DialogTitle>
          <DialogDescription className="font-mono-data text-xs">
            {SCEN_LABEL[scenario] || scenario} {year} · {line.employment_type} · {line.department_label}
          </DialogDescription>
        </DialogHeader>

        {scenarioOptions && (
          <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-1" data-testid="detail-scenario-switch">
            {scenarioOptions.map(([k, lbl]) => (
              <button key={k} data-testid={`detail-scenario-${k}`} onClick={() => onScenarioChange(k)}
                className={`flex-1 rounded-md px-3 py-1.5 text-xs font-700 transition-colors ${scenario === k ? "bg-white text-slate-800 shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
                {lbl}
              </button>
            ))}
          </div>
        )}
        {scenarioOptions && baselineTotal != null && scenario !== "ca" && (() => {
          const diff = line.total_cost - baselineTotal;
          const pct = baselineTotal ? (diff / baselineTotal * 100).toFixed(1) : "0.0";
          const c = diff > 0 ? "#DC2626" : diff < 0 ? "#0E9488" : "#64748B";
          return (
            <div className="flex items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm" data-testid="detail-ecart">
              <span className="text-slate-500">Écart vs Budget CA</span>
              <span className="font-mono-data font-700" style={{ color: c }}>{diff > 0 ? "+" : ""}{fmtCAD(diff)} ({diff > 0 ? "+" : ""}{pct} %)</span>
            </div>
          );
        })()}

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Salaire</h3></div>
              <div className="divide-y divide-slate-100">
                <Row label="Salaire de base (actuel)" value={fmtCAD(line.base_salary)} />
                <Row label="Augmentation" value={`${(line.augmentation * 100).toFixed(2)} %`} />
                <Row label="Nouveau salaire" value={fmtCAD(line.new_salary)} strong accent="#2563EB" />
                <Row label="Taux horaire (réf. 2080 h)" value={`${line.taux_horaire} $/h`} />
                {line.salary_change_date && <Row label="Changement de salaire" value={new Date(line.salary_change_date).toLocaleDateString("fr-CA")} accent="#B45309" />}
                <Row label="Vacances" value={fmtCAD(line.vacation)} />
              </div>
            </div>
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">{ccq ? "Primes & Allocations" : "Rémunération additionnelle"}</h3></div>
              <div className="divide-y divide-slate-100">
                {ccq && <Row label={`Prime (${line.prime_type})`} value={fmtCAD(line.prime_amount)} />}
                {ccq && <Row label="Prime de garde" value={fmtCAD(line.garde)} />}
                {ccq && <Row label="Prime HALO" value={fmtCAD(line.halo)} />}
                {ccq && <Row label="Alloc. sécurité" value={fmtCAD(line.alloc)} />}
                {!ccq && <Row label="Boni" value={fmtCAD(line.boni)} />}
                {!ccq && line.tedy > 0 && <Row label="Prime Tedy" value={fmtCAD(line.tedy)} />}
                {!ccq && line.telus > 0 && <Row label="Prime Telus" value={fmtCAD(line.telus)} />}
                {!ccq && <Row label="Alloc. sécurité" value={fmtCAD(line.alloc)} />}
                <Row label="Total primes & boni" value={fmtCAD(line.primes_total)} strong accent="#F59E0B" />
                <Row label="Salaire brut total" value={fmtCAD(line.new_salary + line.vacation + line.primes_total)} strong accent="#0E9488" />
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Cotisations & avantages (max. assurables)</h3></div>
              <div className="divide-y divide-slate-100">
                <Row label="RRQ" value={fmtCAD(line.rrq)} /><Row label="AE" value={fmtCAD(line.ae)} />
                <Row label="RQAP" value={fmtCAD(line.rqap)} /><Row label="FSS" value={fmtCAD(line.fss)} />
                {ccq && <Row label="Avantages CCQ (32.33%)" value={fmtCAD(line.ccq_avantages)} accent="#2563EB" />}
                <Row label="CSST" value={fmtCAD(line.csst)} />
                {!ccq && <Row label="RPDB / REER" value={fmtCAD(line.reer)} />}
                {!ccq && <Row label="Assu. collectives" value={fmtCAD(line.assurance)} />}
                <Row label="Total avantages sociaux" value={fmtCAD(line.avantages)} strong accent="#8B5CF6" />
              </div>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-[#0E1526] px-4 py-3">
              <span className="text-xs font-700 uppercase tracking-widest text-white">Masse salariale totale</span>
              <span className="font-mono-data text-lg font-700 text-[#14B8A6]" data-testid="detail-total">{fmtCAD(line.total_cost)}</span>
            </div>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button data-testid="detail-pdf-btn" variant="outline" onClick={exportPdf} disabled={busy} className="flex-1 gap-1.5">
                <FileDown size={15} /> {busy ? "Génération…" : "Exporter en PDF"}
              </Button>
              {canEdit && (
                <Button data-testid="detail-edit-btn" onClick={() => { onOpenChange(false); onEdit(line); }} className="flex-1 gap-1.5 bg-[#2563EB] hover:bg-[#2563EB]/90">
                  <Pencil size={15} /> Modifier cette fiche
                </Button>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
