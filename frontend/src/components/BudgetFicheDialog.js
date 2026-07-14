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

function fromLine(line) {
  return {
    base_salary: String(line.base_salary),
    department: line.department,
    employment_type: line.employment_type,
    employment_rate_pct: String(+(((line.employment_rate ?? 1)) * 100).toFixed(1)),
    augmentation_pct: String(+(line.augmentation * 100).toFixed(3)),
    vacation_rate_pct: String(+(line.vacation_rate * 100).toFixed(2)),
    salary_change_date: line.salary_change_date || "",
    prime_type: line.prime_type,
    prime_garde: line.garde > 0, prime_halo: line.halo > 0, alloc_securite: line.alloc > 0,
    boni: String(line.boni || 0), boni_mode: line.boni_mode || "montant", boni_pct: String(line.boni_pct || 0),
    tedy: String(line.tedy || 0), telus: String(line.telus || 0),
    reer: String(line.reer || 0), assurance: String(line.assurance || 0),
  };
}

const MANUAL_KEYS = ["new_salary", "vacation", "prime_amount", "garde", "halo", "alloc", "boni", "rrq", "ae", "rqap", "fss", "ccq_avantages", "csst", "reer", "assurance"];

const EMP_TYPES = ["CCQ", "Régulier temps plein", "Régulier temps partiel", "Stagiaire"];

function Row({ label, value, strong, accent }) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5 text-sm">
      <span className={strong ? "text-xs font-700 uppercase tracking-wide" : "text-slate-500"}>{label}</span>
      <span className="font-mono-data" style={accent ? { color: accent } : {}}>{value}</span>
    </div>
  );
}

function CalcRow({ label, mkey, value, editable, manual, setManualField, strong, accent, testId }) {
  if (editable) {
    const cur = manual[mkey] !== undefined ? manual[mkey] : String(+(value || 0).toFixed(2));
    return (
      <div className="flex items-center justify-between gap-3 px-3 py-1.5 text-sm">
        <span className={strong ? "text-xs font-700 uppercase tracking-wide" : "text-slate-500"}>{label}</span>
        <input data-testid={testId} type="number" step="0.01" value={cur} onChange={(e) => setManualField(mkey, e.target.value)}
          className="w-32 rounded-md border border-amber-300 bg-amber-50 px-2 py-1 text-right font-mono-data text-sm outline-none focus:border-amber-500" />
      </div>
    );
  }
  return <Row label={label} value={fmtCAD(value)} strong={strong} accent={accent} />;
}

const SCENARIOS = [["ca", "Budget CA"], ["revue1", "Revue Budgétaire 1"], ["revue2", "Revue Budgétaire 2"]];
const SCEN_LABEL = Object.fromEntries(SCENARIOS);
const MONTHS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"];

export default function BudgetFicheDialog({ open, onOpenChange, line, year, scenario = "ca", locks = {}, isAdmin = true, onSaved }) {
  const [scn, setScn] = useState(scenario);
  const [curLine, setCurLine] = useState(line);
  const [f, setF] = useState(() => fromLine(line));
  const [p, setP] = useState(line);
  const [departments, setDepartments] = useState([]);
  const [manualOn, setManualOn] = useState(false);
  const [manual, setManual] = useState({});
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const setManualField = (k, v) => setManual((x) => { const n = { ...x }; if (v === "" || v == null) delete n[k]; else n[k] = v; return n; });
  const isCCQ = f.employment_type === "CCQ";
  const isPartTime = f.employment_type === "Régulier temps partiel";
  const revueMode = scn.startsWith("revue");
  const manualAllowed = scn === "ca" || scn === "revue1";
  const locked = !isAdmin && !!locks[`${year}:${scn}`]?.locked;

  useEffect(() => { api.listDepartments().then(setDepartments).catch(() => {}); }, []);

  // Charger les valeurs sauvegardées du scénario sélectionné dans la fiche.
  useEffect(() => {
    let cancel = false;
    if (scn === scenario) { setCurLine(line); return; }
    api.getBudget({ year, scenario: scn }).then((d) => {
      if (cancel) return;
      const l = d.lines.find((x) => x.employee_id === line.employee_id);
      if (l) setCurLine(l);
    }).catch(() => {});
    return () => { cancel = true; };
    // eslint-disable-next-line
  }, [scn]);

  useEffect(() => {
    setF(fromLine(curLine));
    setP(curLine);
    const m = curLine.manual || {};
    setManual(m);
    setManualOn(Object.keys(m).length > 0);
  }, [curLine]);

  const override = useMemo(() => {
    const o = {
      augmentation: Number(f.augmentation_pct) / 100,
      vacation_rate: Number(f.vacation_rate_pct) / 100,
      department: f.department,
      employment_type: f.employment_type,
    };
    if (f.salary_change_date) o.salary_change_date = f.salary_change_date;
    if (f.employment_type === "Régulier temps partiel") o.employment_rate = (Number(f.employment_rate_pct) || 100) / 100;
    // En Revue, on ne touche jamais au salaire de base (salaire actuel partagé) ni au Budget CA.
    if (!revueMode) o.base_salary = Number(f.base_salary) || 0;
    if (isCCQ) {
      o.prime_type = f.prime_type; o.prime_garde = f.prime_garde; o.prime_halo = f.prime_halo; o.alloc_securite = f.alloc_securite;
    } else {
      o.alloc_securite = f.alloc_securite;
      o.reer = Number(f.reer) || 0; o.assurance = Number(f.assurance) || 0;
      o.boni_mode = f.boni_mode;
      if (f.boni_mode === "pct") o.boni_pct = Number(f.boni_pct) || 0;
      else o.boni = Number(f.boni) || 0;
      o.tedy = Number(f.tedy) || 0; o.telus = Number(f.telus) || 0;
    }
    if (manualAllowed && manualOn) {
      const m = {};
      for (const k of MANUAL_KEYS) if (manual[k] !== undefined && manual[k] !== "") m[k] = Number(manual[k]);
      o.manual = m;
    }
    return o;
  }, [f, isCCQ, revueMode, manualAllowed, manualOn, manual]);

  useEffect(() => {
    const t = setTimeout(() => { api.budgetPreview(line.employee_id, override, { year, scenario: scn }).then(setP).catch(() => {}); }, 200);
    return () => clearTimeout(t);
  }, [override, line.employee_id, year, scn]);

  const refetch = () => api.getBudget({ year, scenario: scn }).then((d) => {
    const l = d.lines.find((x) => x.employee_id === line.employee_id); if (l) setCurLine(l);
  }).catch(() => {});

  const save = async () => {
    if (locked) { toast.error("Budget verrouillé — seul un administrateur peut modifier."); return; }
    try {
      await api.saveBudgetOverride(line.employee_id, override, { year, scenario: scn });
      toast.success(`${SCEN_LABEL[scn]} enregistré`); onSaved(); await refetch();
    } catch (e) { toast.error(e.response?.data?.detail || "Enregistrement impossible"); }
  };
  const reset = async () => {
    if (locked) { toast.error("Budget verrouillé — seul un administrateur peut modifier."); return; }
    try { await api.saveBudgetOverride(line.employee_id, {}, { year, scenario: scn }); toast.success("Ligne réinitialisée"); onSaved(); await refetch(); }
    catch (e) { toast.error(e.response?.data?.detail || "Action impossible"); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto" data-testid="budget-fiche-dialog">
        <DialogHeader>
          <DialogTitle>{SCEN_LABEL[scn]} {year} — {line.name}</DialogTitle>
          <DialogDescription className="font-mono-data text-xs">{line.employment_type} · #{String(line.employee_number).padStart(3, "0")} · {line.department_label}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3" data-testid="fiche-scenario-bar">
          <span className="text-[11px] font-700 uppercase tracking-widest text-slate-500">Saisie</span>
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-1" data-testid="fiche-scenario-toggle">
            {SCENARIOS.map(([k, lbl]) => (
              <button key={k} data-testid={`fiche-scenario-${k}`} onClick={() => setScn(k)}
                className={`rounded-md px-3 py-1.5 text-xs font-700 transition-colors ${scn === k ? "bg-[#0E1526] text-white shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
                {lbl}
              </button>
            ))}
          </div>
          <span className="text-[11px]" style={{ color: revueMode ? "#8B5CF6" : "#64748B" }}>
            {revueMode
              ? "Revue Budgétaire : ajustez primes, augmentation et vacances — le Budget CA n'est pas modifié."
              : "Budget CA : bâti à partir du salaire actuel + augmentations/primes."}
          </span>
          {locked && <span className="flex items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-[11px] font-700 text-red-600" data-testid="fiche-lock-badge">🔒 Verrouillé — lecture seule</span>}
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200" data-testid="fiche-emploi-section">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Emploi & imputation</h3></div>
              <div className="grid grid-cols-2 gap-3 p-3">
                <div className={isPartTime ? "" : "col-span-2"}><Label className="text-[11px] uppercase text-slate-500">Type d'emploi</Label>
                  <Select value={f.employment_type} onValueChange={(v) => set("employment_type", v)}>
                    <SelectTrigger data-testid="fiche-employment-type" className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>{EMP_TYPES.map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent>
                  </Select></div>
                {isPartTime && (
                  <div><Label className="text-[11px] uppercase text-slate-500">Taux d'emploi (%)</Label>
                    <Input data-testid="fiche-employment-rate" type="number" step="1" min="1" max="100" className="mt-1 font-mono-data" value={f.employment_rate_pct} onChange={(e) => set("employment_rate_pct", e.target.value)} /></div>
                )}
                <div className="col-span-2"><Label className="text-[11px] uppercase text-slate-500">Département (cette version)</Label>
                  <Select value={f.department} onValueChange={(v) => set("department", v)}>
                    <SelectTrigger data-testid="fiche-department" className="mt-1"><SelectValue /></SelectTrigger>
                    <SelectContent>{departments.map((d) => <SelectItem key={d.code} value={d.code}>{d.code} — {d.description}</SelectItem>)}</SelectContent>
                  </Select></div>
              </div>
              <p className="border-t border-slate-200 px-3 py-2 text-[11px] text-slate-500">Le département/type d'emploi sont propres à cette version de budget. Le changement de département n'affecte que l'imputation (les déductions restent selon la classe de sécurité). Au verrouillage, le département de la fiche employé prendra celui de la version verrouillée.</p>
            </div>
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Salaire</h3></div>
              <div className="grid grid-cols-2 gap-3 p-3">
                <div><Label className="text-[11px] uppercase text-slate-500">Salaire de base ($){revueMode && <span className="ml-1 normal-case text-slate-400">— salaire actuel</span>}</Label>
                  <Input data-testid="fiche-base-salary" type="number" disabled={revueMode} className="mt-1 font-mono-data" value={f.base_salary} onChange={(e) => set("base_salary", e.target.value)} /></div>
                <div><Label className="text-[11px] uppercase text-slate-500">Augmentation (%)</Label>
                  <Input data-testid="fiche-augmentation" type="number" step="0.1" className="mt-1 font-mono-data" value={f.augmentation_pct} onChange={(e) => set("augmentation_pct", e.target.value)} /></div>
                <div><Label className="text-[11px] uppercase text-slate-500">Taux vacances (%)</Label>
                  <Input data-testid="fiche-vacation" type="number" step="0.1" className="mt-1 font-mono-data" value={f.vacation_rate_pct} onChange={(e) => set("vacation_rate_pct", e.target.value)} /></div>
                <div className="col-span-2"><Label className="text-[11px] uppercase text-slate-500">Date de changement de salaire (optionnel)</Label>
                  <Input data-testid="fiche-salary-change-date" type="date" className="mt-1 font-mono-data" value={f.salary_change_date} onChange={(e) => set("salary_change_date", e.target.value)} />
                  <p className="mt-1 text-[10px] text-slate-400">Avant cette date, le salaire actuel de base s'applique ; le nouveau salaire s'applique à partir de cette date (proratisé sur l'année).</p></div>
                {isCCQ && (
                  <div><Label className="text-[11px] uppercase text-slate-500">Type de prime</Label>
                    <Select value={f.prime_type} onValueChange={(v) => set("prime_type", v)}>
                      <SelectTrigger data-testid="fiche-prime-type" className="mt-1"><SelectValue /></SelectTrigger>
                      <SelectContent>{["Aucune Prime", "Prime 8%", "Prime 11%", "Prime 12%"].map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent>
                    </Select></div>
                )}
              </div>
            </div>
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">{isCCQ ? "Primes & Allocations" : "Rémunération additionnelle"}</h3></div>
              {isCCQ && (
                <div className="grid grid-cols-3 gap-2 p-3">
                  {[["prime_garde", "Prime de garde"], ["prime_halo", "Prime HALO 5%"], ["alloc_securite", "Alloc. sécurité"]].map(([k, lbl]) => (
                    <label key={k} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-2.5 py-2">
                      <span className="text-[11px] font-500">{lbl}</span><Switch data-testid={`fiche-${k}`} checked={f[k]} onCheckedChange={(v) => set(k, v)} />
                    </label>
                  ))}
                </div>
              )}
              {!isCCQ && (
                <div className="p-3">
                  <div className="grid grid-cols-3 gap-3">
                    <div><Label className="text-[11px] uppercase text-slate-500">RPDB/REER ($)</Label><Input data-testid="fiche-reer" type="number" className="mt-1 font-mono-data" value={f.reer} onChange={(e) => set("reer", e.target.value)} /></div>
                    <div><Label className="text-[11px] uppercase text-slate-500">Assu. coll. ($)</Label><Input data-testid="fiche-assurance" type="number" className="mt-1 font-mono-data" value={f.assurance} onChange={(e) => set("assurance", e.target.value)} /></div>
                    <div><Label className="text-[11px] uppercase text-slate-500">Boni</Label>
                      <div className="mt-1 flex gap-1">
                        <Select value={f.boni_mode} onValueChange={(v) => set("boni_mode", v)}>
                          <SelectTrigger data-testid="fiche-boni-mode" className="w-16 px-2"><SelectValue /></SelectTrigger>
                          <SelectContent><SelectItem value="montant">$</SelectItem><SelectItem value="pct">%</SelectItem></SelectContent>
                        </Select>
                        {f.boni_mode === "pct"
                          ? <Input data-testid="fiche-boni-pct" type="number" step="0.1" className="font-mono-data" value={f.boni_pct} onChange={(e) => set("boni_pct", e.target.value)} />
                          : <Input data-testid="fiche-boni" type="number" className="font-mono-data" value={f.boni} onChange={(e) => set("boni", e.target.value)} />}
                      </div>
                    </div>
                  </div>
                  <label className="mt-3 flex w-full items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 sm:w-1/3">
                    <span className="text-[11px] font-500">Alloc. sécurité</span><Switch data-testid="fiche-alloc_securite" checked={f.alloc_securite} onCheckedChange={(v) => set("alloc_securite", v)} />
                  </label>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div><Label className="text-[11px] uppercase text-slate-500">Prime Tedy ($)</Label><Input data-testid="fiche-tedy" type="number" className="mt-1 font-mono-data" value={f.tedy} onChange={(e) => set("tedy", e.target.value)} /></div>
                    <div><Label className="text-[11px] uppercase text-slate-500">Prime Telus ($)</Label><Input data-testid="fiche-telus" type="number" className="mt-1 font-mono-data" value={f.telus} onChange={(e) => set("telus", e.target.value)} /></div>
                  </div>
                  <p className="mt-2 text-[10px] text-slate-400">Tedy et Telus : montants fixes inclus uniquement dans les bases RRQ / FSS / RQAP / CSST.</p>
                </div>
              )}
              {!isCCQ && <p className="border-t border-slate-200 px-3 py-2 text-[11px] text-slate-500">Employé non-CCQ : primes CCQ (garde, HALO) non applicables. BONI, REER, assurance collective et Alloc. sécurité s'appliquent.</p>}
              {isCCQ && <p className="border-t border-slate-200 px-3 py-2 text-[11px] text-[#2563EB]">Employé CCQ : RPDB, BONI et Assu. collectives non applicables. Avantages CCQ appliqués.</p>}
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-xl border border-slate-200">
              <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50 px-3 py-2">
                <h3 className="text-xs font-700 uppercase tracking-widest">Calcul automatique</h3>
                {manualAllowed && (
                  <label className="flex items-center gap-2" data-testid="fiche-manual-toggle-label">
                    <span className={`text-[10px] font-700 uppercase ${manualOn ? "text-amber-600" : "text-slate-400"}`}>Saisie manuelle</span>
                    <Switch data-testid="fiche-manual-toggle" checked={manualOn} onCheckedChange={setManualOn} />
                  </label>
                )}
              </div>
              <div className="divide-y divide-slate-100">
                <CalcRow label="Nouveau salaire" mkey="new_salary" value={p.new_salary} editable={manualOn} manual={manual} setManualField={setManualField} strong accent="#2563EB" testId="manual-new_salary" />
                <Row label="Taux horaire (réf. 2080 h)" value={`${p.taux_horaire} $/h`} />
                <CalcRow label="Vacances" mkey="vacation" value={p.vacation} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-vacation" />
                {isCCQ && <CalcRow label={`Prime (${p.prime_type})`} mkey="prime_amount" value={p.prime_amount} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-prime_amount" />}
                {isCCQ && <CalcRow label="Prime de garde" mkey="garde" value={p.garde} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-garde" />}
                {isCCQ && <CalcRow label="Prime HALO" mkey="halo" value={p.halo} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-halo" />}
                {isCCQ && <CalcRow label="Alloc. sécurité" mkey="alloc" value={p.alloc} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-alloc" />}
                {!isCCQ && <CalcRow label="Boni" mkey="boni" value={p.boni} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-boni" />}
                {!isCCQ && <Row label="Prime Tedy" value={fmtCAD(p.tedy)} />}
                {!isCCQ && <Row label="Prime Telus" value={fmtCAD(p.telus)} />}
                {!isCCQ && <CalcRow label="Alloc. sécurité" mkey="alloc" value={p.alloc} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-alloc" />}
                <Row label="Salaire brut total" value={fmtCAD(p.new_salary + p.vacation + p.primes_total)} strong accent="#0E9488" />
              </div>
            </div>
            <div className="rounded-xl border border-slate-200">
              <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">Cotisations & avantages (max. assurables)</h3></div>
              <div className="divide-y divide-slate-100">
                <CalcRow label="RRQ" mkey="rrq" value={p.rrq} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-rrq" />
                <CalcRow label="AE" mkey="ae" value={p.ae} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-ae" />
                <CalcRow label="RQAP" mkey="rqap" value={p.rqap} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-rqap" />
                <CalcRow label="FSS" mkey="fss" value={p.fss} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-fss" />
                {isCCQ && <CalcRow label="Avantages CCQ (32.33%)" mkey="ccq_avantages" value={p.ccq_avantages} editable={manualOn} manual={manual} setManualField={setManualField} accent="#2563EB" testId="manual-ccq_avantages" />}
                <CalcRow label="CSST" mkey="csst" value={p.csst} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-csst" />
                {!isCCQ && <CalcRow label="RPDB / REER" mkey="reer" value={p.reer} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-reer" />}
                {!isCCQ && <CalcRow label="Assu. collectives" mkey="assurance" value={p.assurance} editable={manualOn} manual={manual} setManualField={setManualField} testId="manual-assurance" />}
              </div>
            </div>
            <div className="rounded-xl bg-[#0E1526] px-4 py-3">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-600 uppercase tracking-widest text-white/60">Masse salariale (année pleine)</span>
                <span className="font-mono-data text-sm text-white/80">{fmtCAD(p.total_cost)}</span>
              </div>
              <div className="mt-1 flex items-center justify-between">
                <span className="text-xs font-700 uppercase tracking-widest text-white">Total budgété{p.prorated ? ` · pro-rata ${p.months_active} mois` : ""}</span>
                <span className="font-mono-data text-lg font-700 text-[#14B8A6]" data-testid="fiche-total">{fmtCAD(p.total_budgeted)}</span>
              </div>
            </div>
          </div>
        </div>

        {p.monthly && (
          <div className="rounded-xl border border-slate-200" data-testid="fiche-ventilation">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 bg-slate-50 px-3 py-2">
              <h3 className="text-xs font-700 uppercase tracking-widest">Ventilation mensuelle {year}</h3>
              {p.prorated ? (() => {
                const act = p.monthly.map((v, i) => (v > 0 ? i : -1)).filter((i) => i >= 0);
                const first = act.length ? act[0] : 0, last = act.length ? act[act.length - 1] : 11;
                const late = first > 0, early = last < 11;
                let txt;
                if (late && early) txt = `Actif de ${MONTHS[first]} à ${MONTHS[last]} (${p.months_active} mois)`;
                else if (early) txt = `Fin d'emploi en cours d'année → actif jusqu'à ${MONTHS[last]} (${p.months_active} mois)`;
                else txt = `Embauche en cours d'année → pro-rata dès ${MONTHS[first]} (${p.months_active} mois)`;
                return <span className="text-[11px] text-[#B45309]">{txt}</span>;
              })() : <span className="text-[11px] text-slate-400">Répartie selon les jours ouvrables</span>}
            </div>
            <div className="grid grid-cols-4 gap-px bg-slate-100 sm:grid-cols-6 lg:grid-cols-12">
              {MONTHS.map((mo, i) => (
                <div key={mo} className={`bg-white p-2 text-center ${p.monthly[i] === 0 ? "opacity-40" : ""}`} data-testid={`fiche-month-${i}`}>
                  <p className="text-[10px] font-600 uppercase text-slate-400">{mo}</p>
                  <p className="mt-0.5 font-mono-data text-[11px] font-600">{fmtCAD(p.monthly[i])}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        <DialogFooter className="flex-col gap-2 sm:flex-row sm:justify-between">
          <Button variant="outline" data-testid="fiche-reset-btn" onClick={reset} disabled={locked} className="gap-1.5"><RotateCcw size={15} /> Réinitialiser</Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)}>Fermer</Button>
            <Button data-testid="fiche-save-btn" onClick={save} disabled={locked} className="gap-1.5 bg-[#2563EB] hover:bg-[#2563EB]/90"><Save size={15} /> Enregistrer</Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
