import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { fmtCAD } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Save, RotateCcw } from "lucide-react";
import { toast } from "sonner";

function Row({ label, value, strong, accent }) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5 text-sm">
      <span className={strong ? "text-xs font-700 uppercase tracking-wide" : "text-slate-500"}>{label}</span>
      <span className="font-mono-data" style={accent ? { color: accent } : {}}>{value}</span>
    </div>
  );
}

export default function BudgetFicheDialog({ open, onOpenChange, line, onSaved }) {
  const isCCQ = line.is_ccq;
  const [f, setF] = useState(() => ({
    base_salary: String(line.base_salary),
    augmentation_pct: String(+(line.augmentation * 100).toFixed(3)),
    vacation_rate_pct: String(+(line.vacation_rate * 100).toFixed(2)),
    prime_type: line.prime_type,
    prime_garde: line.garde > 0, prime_halo: line.halo > 0, alloc_securite: line.alloc > 0,
    boni: String(line.boni || 0), reer: String(line.reer || 0), assurance: String(line.assurance || 0),
  }));
  const [p, setP] = useState(line);
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));

  const override = useMemo(() => {
    const o = {
      base_salary: Number(f.base_salary) || 0, augmentation: Number(f.augmentation_pct) / 100,
      vacation_rate: Number(f.vacation_rate_pct) / 100, prime_type: f.prime_type,
      prime_garde: f.prime_garde, prime_halo: f.prime_halo, alloc_securite: f.alloc_securite,
    };
    if (!isCCQ) { o.boni = Number(f.boni) || 0; o.reer = Number(f.reer) || 0; o.assurance = Number(f.assurance) || 0; }
    return o;
  }, [f, isCCQ]);

  useEffect(() => {
    const t = setTimeout(() => { api.budgetPreview(line.employee_id, override).then(setP).catch(() => {}); }, 200);
    return () => clearTimeout(t);
  }, [override, line.employee_id]);

  const save = async () => { await api.saveBudgetOverride(line.employee_id, override); toast.success("Fiche enregistrée"); onSaved(); onOpenChange(false); };
  const reset = async () => { await api.saveBudgetOverride(line.employee_id, {}); toast.success("Ligne réinitialisée"); onSaved(); onOpenChange(false); };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto" data-testid="budget-fiche-dialog">
        <DialogHeader>
          <DialogTitle>Fiche Salaires & Budget — {line.name}</DialogTitle>
          <DialogDescription className="font-mono-data text-xs">{line.employment_type} · #{String(line.employee_number).padStart(3, "0")} · {line.department_label}</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Salaire</h3></div>
              <div className="grid grid-cols-2 gap-3 p-3">
                <div><Label className="text-[11px] uppercase text-slate-500">Salaire de base ($)</Label>
                  <Input data-testid="fiche-base-salary" type="number" className="mt-1 font-mono-data" value={f.base_salary} onChange={(e) => set("base_salary", e.target.value)} /></div>
                <div><Label className="text-[11px] uppercase text-slate-500">Augmentation (%)</Label>
                  <Input data-testid="fiche-augmentation" type="number" step="0.1" className="mt-1 font-mono-data" value={f.augmentation_pct} onChange={(e) => set("augmentation_pct", e.target.value)} /></div>
                <div><Label className="text-[11px] uppercase text-slate-500">Taux vacances (%)</Label>
                  <Input data-testid="fiche-vacation" type="number" step="0.1" disabled={isCCQ} className="mt-1 font-mono-data" value={f.vacation_rate_pct} onChange={(e) => set("vacation_rate_pct", e.target.value)} /></div>
                <div><Label className="text-[11px] uppercase text-slate-500">Type de prime</Label>
                  <Select value={f.prime_type} onValueChange={(v) => set("prime_type", v)}>
                    <SelectTrigger data-testid="fiche-prime-type" className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>{["Aucune Prime", "Prime 8%", "Prime 11%", "Prime 12%"].map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent>
                  </Select></div>
              </div>
            </div>
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Primes & Allocations</h3></div>
              <div className="grid grid-cols-3 gap-2 p-3">
                {[["prime_garde", "Prime de garde"], ["prime_halo", "Prime HALO 5%"], ["alloc_securite", "Alloc. sécurité"]].map(([k, lbl]) => (
                  <label key={k} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-2.5 py-2">
                    <span className="text-[11px] font-500">{lbl}</span><Switch data-testid={`fiche-${k}`} checked={f[k]} onCheckedChange={(v) => set(k, v)} />
                  </label>
                ))}
              </div>
              {!isCCQ && (
                <div className="grid grid-cols-3 gap-3 border-t border-slate-200 p-3">
                  <div><Label className="text-[11px] uppercase text-slate-500">RPDB/REER ($)</Label><Input data-testid="fiche-reer" type="number" className="mt-1 font-mono-data" value={f.reer} onChange={(e) => set("reer", e.target.value)} /></div>
                  <div><Label className="text-[11px] uppercase text-slate-500">Assu. coll. ($)</Label><Input data-testid="fiche-assurance" type="number" className="mt-1 font-mono-data" value={f.assurance} onChange={(e) => set("assurance", e.target.value)} /></div>
                  <div><Label className="text-[11px] uppercase text-slate-500">BONI ($)</Label><Input data-testid="fiche-boni" type="number" className="mt-1 font-mono-data" value={f.boni} onChange={(e) => set("boni", e.target.value)} /></div>
                </div>
              )}
              {isCCQ && <p className="border-t border-slate-200 px-3 py-2 text-[11px] text-[#2563EB]">Employé CCQ : RPDB, BONI et Assu. collectives non applicables. Avantages CCQ appliqués.</p>}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Calcul automatique</h3></div>
              <div className="divide-y divide-slate-100">
                <Row label="Nouveau salaire" value={fmtCAD(p.new_salary)} strong accent="#2563EB" />
                <Row label="Taux horaire (réf. 2080 h)" value={`${p.taux_horaire} $/h`} />
                <Row label="Vacances (sur salaire + primes)" value={fmtCAD(p.vacation)} />
                <Row label={`Prime (${p.prime_type})`} value={fmtCAD(p.prime_amount)} />
                <Row label="Prime de garde" value={fmtCAD(p.garde)} />
                {p.compagnon > 0 && <Row label="Prime électricien compagnon" value={fmtCAD(p.compagnon)} />}
                <Row label="Prime HALO" value={fmtCAD(p.halo)} />
                <Row label="Alloc. sécurité" value={fmtCAD(p.alloc)} />
                {!isCCQ && <Row label="BONI" value={fmtCAD(p.boni)} />}
              </div>
            </div>
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Cotisations & avantages (max. assurables)</h3></div>
              <div className="divide-y divide-slate-100">
                <Row label="RRQ" value={fmtCAD(p.rrq)} /><Row label="AE" value={fmtCAD(p.ae)} />
                <Row label="RQAP" value={fmtCAD(p.rqap)} /><Row label="FSS" value={fmtCAD(p.fss)} />
                {isCCQ && <Row label="Avantages CCQ (32.33%)" value={fmtCAD(p.ccq_avantages)} accent="#2563EB" />}
                <Row label="CSST" value={fmtCAD(p.csst)} />
                {!isCCQ && <Row label="RPDB / REER" value={fmtCAD(p.reer)} />}
                {!isCCQ && <Row label="Assu. collectives" value={fmtCAD(p.assurance)} />}
              </div>
            </div>
            <div className="flex items-center justify-between rounded-xl bg-[#0E1526] px-4 py-3">
              <span className="text-xs font-700 uppercase tracking-widest text-white">Masse salariale totale</span>
              <span className="font-mono-data text-lg font-700 text-[#14B8A6]" data-testid="fiche-total">{fmtCAD(p.total_cost)}</span>
            </div>
          </div>
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
          <Button variant="outline" data-testid="fiche-reset-btn" onClick={reset} className="gap-1.5"><RotateCcw size={15} /> Réinitialiser</Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Fermer</Button>
            <Button data-testid="fiche-save-btn" onClick={save} className="gap-1.5 bg-[#2563EB] hover:bg-[#2563EB]/90"><Save size={15} /> Enregistrer</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
