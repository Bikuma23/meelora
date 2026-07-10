import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { fmtCAD } from "../lib/format";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Switch } from "./ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "./ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "./ui/select";
import { Save, RotateCcw } from "lucide-react";
import { toast } from "sonner";

function Computed({ label, value, strong, accent }) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5 text-sm">
      <span className={strong ? "font-heading text-xs font-700 uppercase tracking-wide" : "text-[#52525B]"}>{label}</span>
      <span className="font-mono-data" style={accent ? { color: accent } : {}}>{value}</span>
    </div>
  );
}

export default function BudgetFicheDialog({ open, onOpenChange, line, section, sectionLabel, augReg, augCcq, onSaved }) {
  const isCCQ = line.is_ccq;
  const [f, setF] = useState(() => ({
    base_salary: String(line.base_salary),
    augmentation_pct: String(+(line.augmentation * 100).toFixed(3)),
    vacation_rate_pct: String(+(line.vacation_rate * 100).toFixed(2)),
    prime_type: line.prime_type,
    prime_garde: line.garde > 0,
    prime_halo: line.halo > 0,
    prime_chef_equipe: line.chef > 0,
    alloc_securite: line.alloc > 0,
    boni: String(line.boni || 0),
    reer: String(line.reer || 0),
    assurance: String(line.assurance || 0),
  }));
  const [preview, setPreview] = useState(line);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  const override = useMemo(() => {
    const o = {
      base_salary: Number(f.base_salary) || 0,
      augmentation: Number(f.augmentation_pct) / 100,
      vacation_rate: Number(f.vacation_rate_pct) / 100,
      prime_type: f.prime_type,
      prime_garde: f.prime_garde,
      prime_halo: f.prime_halo,
      prime_chef_equipe: f.prime_chef_equipe,
      alloc_securite: f.alloc_securite,
    };
    if (!isCCQ) {
      o.boni = Number(f.boni) || 0;
      o.reer = Number(f.reer) || 0;
      o.assurance = Number(f.assurance) || 0;
    }
    return o;
  }, [f, isCCQ]);

  useEffect(() => {
    const t = setTimeout(() => {
      api.budgetPreview(line.employee_id, { section, override, aug_reg: augReg, aug_ccq: augCcq })
        .then(setPreview)
        .catch(() => {});
    }, 200);
    return () => clearTimeout(t);
  }, [override, line.employee_id, section, augReg, augCcq]);

  const save = async () => {
    await api.saveBudgetOverride(line.employee_id, { section, override, aug_reg: augReg, aug_ccq: augCcq });
    toast.success("Fiche enregistrée");
    onSaved();
    onOpenChange(false);
  };

  const reset = async () => {
    await api.saveBudgetOverride(line.employee_id, { section, override: {}, aug_reg: augReg, aug_ccq: augCcq });
    toast.success("Ligne réinitialisée");
    onSaved();
    onOpenChange(false);
  };

  const p = preview;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto rounded-none border border-[#09090B]" data-testid="budget-fiche-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading uppercase tracking-tight">
            Fiche Salaires & Budget — {line.name}
          </DialogTitle>
          <DialogDescription className="font-mono-data text-xs text-[#52525B]">
            Section « {sectionLabel} » · {line.employment_type} · #{String(line.employee_number).padStart(3, "0")}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {/* SAISIE */}
          <div className="space-y-4">
            <div className="border border-[#D4D4D8]">
              <div className="border-b border-[#D4D4D8] bg-[#F4F4F5] px-3 py-2">
                <h3 className="font-heading text-xs font-800 uppercase tracking-widest">Salaire</h3>
              </div>
              <div className="grid grid-cols-2 gap-3 p-3">
                <div>
                  <Label className="text-[11px] uppercase tracking-wide text-[#52525B]">Salaire de base ($)</Label>
                  <Input data-testid="fiche-base-salary" type="number" className="mt-1 rounded-none font-mono-data" value={f.base_salary} onChange={(e) => set("base_salary", e.target.value)} />
                </div>
                <div>
                  <Label className="text-[11px] uppercase tracking-wide text-[#52525B]">Augmentation (%)</Label>
                  <Input data-testid="fiche-augmentation" type="number" step="0.1" className="mt-1 rounded-none font-mono-data" value={f.augmentation_pct} onChange={(e) => set("augmentation_pct", e.target.value)} />
                </div>
                <div>
                  <Label className="text-[11px] uppercase tracking-wide text-[#52525B]">Taux de vacances (%)</Label>
                  <Input data-testid="fiche-vacation" type="number" step="0.1" disabled={isCCQ} className="mt-1 rounded-none font-mono-data" value={f.vacation_rate_pct} onChange={(e) => set("vacation_rate_pct", e.target.value)} />
                </div>
                <div>
                  <Label className="text-[11px] uppercase tracking-wide text-[#52525B]">Type de prime</Label>
                  <Select value={f.prime_type} onValueChange={(v) => set("prime_type", v)}>
                    <SelectTrigger data-testid="fiche-prime-type" className="mt-1 rounded-none"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Aucune Prime">Aucune Prime</SelectItem>
                      <SelectItem value="Prime 8%">Prime 8%</SelectItem>
                      <SelectItem value="Prime 11%">Prime 11%</SelectItem>
                      <SelectItem value="Prime 12%">Prime 12%</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>

            <div className="border border-[#D4D4D8]">
              <div className="border-b border-[#D4D4D8] bg-[#F4F4F5] px-3 py-2">
                <h3 className="font-heading text-xs font-800 uppercase tracking-widest">Primes & Allocations</h3>
              </div>
              <div className="grid grid-cols-2 gap-2 p-3">
                {[
                  ["prime_garde", "Prime de garde"],
                  ["prime_chef_equipe", "Prime chef d'équipe"],
                  ["prime_halo", "Prime HALO 5%"],
                  ["alloc_securite", "Alloc. sécurité"],
                ].map(([k, lbl]) => (
                  <label key={k} className="flex items-center justify-between gap-2 border border-[#D4D4D8] px-2.5 py-2">
                    <span className="text-[11px] font-medium">{lbl}</span>
                    <Switch data-testid={`fiche-${k}`} checked={f[k]} onCheckedChange={(v) => set(k, v)} />
                  </label>
                ))}
              </div>
              {!isCCQ && (
                <div className="grid grid-cols-3 gap-3 border-t border-[#D4D4D8] p-3">
                  <div>
                    <Label className="text-[11px] uppercase tracking-wide text-[#52525B]">RPDB / REER ($)</Label>
                    <Input data-testid="fiche-reer" type="number" className="mt-1 rounded-none font-mono-data" value={f.reer} onChange={(e) => set("reer", e.target.value)} />
                  </div>
                  <div>
                    <Label className="text-[11px] uppercase tracking-wide text-[#52525B]">Assu. collectives ($)</Label>
                    <Input data-testid="fiche-assurance" type="number" className="mt-1 rounded-none font-mono-data" value={f.assurance} onChange={(e) => set("assurance", e.target.value)} />
                  </div>
                  <div>
                    <Label className="text-[11px] uppercase tracking-wide text-[#52525B]">BONI ($)</Label>
                    <Input data-testid="fiche-boni" type="number" className="mt-1 rounded-none font-mono-data" value={f.boni} onChange={(e) => set("boni", e.target.value)} />
                  </div>
                </div>
              )}
              {isCCQ && (
                <p className="border-t border-[#D4D4D8] px-3 py-2 text-[11px] text-[#0055FF]">
                  Employé CCQ : RPDB, BONI et Assu. collectives non applicables (masqués). Avantages CCQ appliqués automatiquement.
                </p>
              )}
            </div>
          </div>

          {/* CALCULS (live) */}
          <div className="space-y-4">
            <div className="border border-[#D4D4D8]">
              <div className="border-b border-[#D4D4D8] bg-[#F4F4F5] px-3 py-2">
                <h3 className="font-heading text-xs font-800 uppercase tracking-widest">Calcul automatique</h3>
              </div>
              <div className="divide-y divide-[#F4F4F5]">
                <Computed label="Nouveau salaire" value={fmtCAD(p.new_salary)} strong accent="#0055FF" />
                <Computed label="Taux horaire (réf. 2080 h)" value={`${p.taux_horaire} $/h`} />
                <Computed label="Vacances" value={fmtCAD(p.vacation)} />
                <Computed label={`Prime (${p.prime_type})`} value={fmtCAD(p.prime_amount)} />
                <Computed label="Prime de garde" value={fmtCAD(p.garde)} />
                {p.compagnon > 0 && <Computed label="Prime électricien compagnon" value={fmtCAD(p.compagnon)} />}
                <Computed label="Prime HALO" value={fmtCAD(p.halo)} />
                <Computed label="Prime chef d'équipe" value={fmtCAD(p.chef)} />
                <Computed label="Alloc. sécurité" value={fmtCAD(p.alloc)} />
                {!isCCQ && <Computed label="BONI" value={fmtCAD(p.boni)} />}
              </div>
            </div>

            <div className="border border-[#D4D4D8]">
              <div className="border-b border-[#D4D4D8] bg-[#F4F4F5] px-3 py-2">
                <h3 className="font-heading text-xs font-800 uppercase tracking-widest">Cotisations & avantages</h3>
              </div>
              <div className="divide-y divide-[#F4F4F5]">
                <Computed label="RRQ" value={fmtCAD(p.rrq)} />
                <Computed label="AE" value={fmtCAD(p.ae)} />
                <Computed label="RQAP" value={fmtCAD(p.rqap)} />
                <Computed label="FSS" value={fmtCAD(p.fss)} />
                {isCCQ && <Computed label="Avantages CCQ (32.33%)" value={fmtCAD(p.ccq_avantages)} accent="#0055FF" />}
                <Computed label="CSST" value={fmtCAD(p.csst)} />
                {!isCCQ && <Computed label="RPDB / REER" value={fmtCAD(p.reer)} />}
                {!isCCQ && <Computed label="Assu. collectives" value={fmtCAD(p.assurance)} />}
              </div>
            </div>

            <div className="border border-[#09090B]">
              <div className="flex items-center justify-between bg-[#09090B] px-3 py-2.5">
                <span className="font-heading text-xs font-800 uppercase tracking-widest text-white">Masse salariale totale</span>
                <span className="font-mono-data text-lg font-600 text-white" data-testid="fiche-total">{fmtCAD(p.total_cost)}</span>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
          <Button variant="outline" data-testid="fiche-reset-btn" onClick={reset} className="gap-1.5 rounded-none">
            <RotateCcw size={15} /> Réinitialiser la ligne
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" className="rounded-none" onClick={() => onOpenChange(false)}>Fermer</Button>
            <Button data-testid="fiche-save-btn" onClick={save} className="gap-1.5 rounded-none bg-[#0055FF] hover:bg-[#0055FF]/90">
              <Save size={15} /> Enregistrer
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
