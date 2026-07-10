import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { fmtCAD, computeAge, computeSeniority } from "../lib/format";
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
import { Plus, Pencil, Trash2, Search, Cake, CalendarClock } from "lucide-react";
import { toast } from "sonner";

const REQUIRED_MSG = "Ce champ est obligatoire";

const emptyForm = {
  name: "", department: "", title: "", employment_type: "Régulier",
  ccq_category: "N/A", current_annual_salary: "", vacation_rate_pct: "",
  sick_personal_days: "", holiday_days: "", prime_type: "Prime 8%",
  prime_garde: false, prime_chef_equipe: false, prime_halo: false,
  alloc_securite: false, hire_date: "", birth_date: "",
};

function Field({ label, error, children, testId }) {
  return (
    <div>
      <Label className="text-[11px] font-600 uppercase tracking-wide text-[#52525B]">{label}</Label>
      <div className="mt-1">{children}</div>
      {error && (
        <p data-testid={`${testId}-error`} className="mt-1 text-[11px] font-medium text-[#FF4500]">
          {error}
        </p>
      )}
    </div>
  );
}

function EmployeeForm({ open, onOpenChange, initial, departments, onSubmit }) {
  const [f, setF] = useState(emptyForm);
  const [errors, setErrors] = useState({});

  useEffect(() => {
    if (initial) {
      setF({
        name: initial.name, department: initial.department, title: initial.title,
        employment_type: initial.employment_type, ccq_category: initial.ccq_category,
        current_annual_salary: String(initial.current_annual_salary),
        vacation_rate_pct: String(+(initial.vacation_rate * 100).toFixed(2)),
        sick_personal_days: String(initial.sick_personal_days),
        holiday_days: String(initial.holiday_days), prime_type: initial.prime_type,
        prime_garde: initial.prime_garde, prime_chef_equipe: initial.prime_chef_equipe,
        prime_halo: initial.prime_halo, alloc_securite: initial.alloc_securite,
        hire_date: initial.hire_date, birth_date: initial.birth_date,
      });
    } else {
      setF(emptyForm);
    }
    setErrors({});
  }, [initial, open]);

  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const isCCQ = f.employment_type === "CCQ";

  const validate = () => {
    const e = {};
    if (!f.name.trim()) e.name = REQUIRED_MSG;
    if (!f.department) e.department = REQUIRED_MSG;
    if (!f.title.trim()) e.title = REQUIRED_MSG;
    if (!f.employment_type) e.employment_type = REQUIRED_MSG;
    if (isCCQ && (f.ccq_category === "N/A" || !f.ccq_category)) e.ccq_category = "Sélectionnez Électricien ou Frigoriste";
    if (f.current_annual_salary === "" || Number(f.current_annual_salary) <= 0) e.current_annual_salary = "Salaire requis (> 0)";
    if (f.vacation_rate_pct === "" || Number(f.vacation_rate_pct) < 0) e.vacation_rate_pct = REQUIRED_MSG;
    if (f.sick_personal_days === "") e.sick_personal_days = REQUIRED_MSG;
    if (f.holiday_days === "") e.holiday_days = REQUIRED_MSG;
    if (!f.prime_type) e.prime_type = REQUIRED_MSG;
    if (!f.hire_date) e.hire_date = REQUIRED_MSG;
    if (!f.birth_date) e.birth_date = REQUIRED_MSG;
    setErrors(e);
    return Object.keys(e).length === 0;
  };

  const submit = () => {
    if (!validate()) {
      toast.error("Veuillez corriger les champs obligatoires");
      return;
    }
    onSubmit({
      name: f.name.trim(), department: f.department, title: f.title.trim(),
      employment_type: f.employment_type,
      ccq_category: isCCQ ? f.ccq_category : "N/A",
      current_annual_salary: Number(f.current_annual_salary),
      vacation_rate: Number(f.vacation_rate_pct) / 100,
      sick_personal_days: parseInt(f.sick_personal_days, 10),
      holiday_days: parseInt(f.holiday_days, 10),
      is_ccq: isCCQ, prime_type: f.prime_type,
      prime_garde: f.prime_garde, prime_chef_equipe: f.prime_chef_equipe,
      prime_halo: f.prime_halo, alloc_securite: f.alloc_securite,
      hire_date: f.hire_date, birth_date: f.birth_date,
    });
  };

  const age = computeAge(f.birth_date);
  const seniority = computeSeniority(f.hire_date);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto rounded-none border border-[#09090B] sm:max-w-2xl" data-testid="employee-form-dialog">
        <DialogHeader>
          <DialogTitle className="font-heading uppercase tracking-tight">
            {initial ? `Modifier — #${initial.employee_number} ${initial.name}` : "Nouvel employé"}
          </DialogTitle>
          <DialogDescription className="text-xs text-[#52525B]">
            Tous les champs sont obligatoires. L'âge et l'ancienneté se calculent automatiquement.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 py-2 sm:grid-cols-2">
          <Field label="Nom complet" error={errors.name} testId="f-name">
            <Input data-testid="f-name" className="rounded-none" value={f.name} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <Field label="Titre / Poste" error={errors.title} testId="f-title">
            <Input data-testid="f-title" className="rounded-none" value={f.title} onChange={(e) => set("title", e.target.value)} />
          </Field>

          <Field label="Département" error={errors.department} testId="f-department">
            <Select value={f.department} onValueChange={(v) => set("department", v)}>
              <SelectTrigger data-testid="f-department" className="rounded-none"><SelectValue placeholder="Sélectionner…" /></SelectTrigger>
              <SelectContent className="max-h-64">
                {departments.map((d) => <SelectItem key={d.code} value={d.code}>{d.code}</SelectItem>)}
              </SelectContent>
            </Select>
          </Field>
          <Field label="Type d'emploi" error={errors.employment_type} testId="f-type">
            <Select value={f.employment_type} onValueChange={(v) => set("employment_type", v)}>
              <SelectTrigger data-testid="f-type" className="rounded-none"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="Régulier">Régulier</SelectItem>
                <SelectItem value="CCQ">CCQ (conventionné)</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          {isCCQ && (
            <Field label="Catégorie CCQ" error={errors.ccq_category} testId="f-ccq-category">
              <Select value={f.ccq_category} onValueChange={(v) => set("ccq_category", v)}>
                <SelectTrigger data-testid="f-ccq-category" className="rounded-none"><SelectValue placeholder="Sélectionner…" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="Électricien">Électricien</SelectItem>
                  <SelectItem value="Frigoriste">Frigoriste</SelectItem>
                </SelectContent>
              </Select>
            </Field>
          )}
          <Field label="Salaire annuel actuel ($)" error={errors.current_annual_salary} testId="f-salary">
            <Input data-testid="f-salary" type="number" className="rounded-none font-mono-data" value={f.current_annual_salary} onChange={(e) => set("current_annual_salary", e.target.value)} />
          </Field>

          <Field label="Taux de vacances (%)" error={errors.vacation_rate_pct} testId="f-vacation">
            <Input data-testid="f-vacation" type="number" step="0.1" className="rounded-none font-mono-data" value={f.vacation_rate_pct} onChange={(e) => set("vacation_rate_pct", e.target.value)} />
          </Field>
          <Field label="Type de prime" error={errors.prime_type} testId="f-prime-type">
            <Select value={f.prime_type} onValueChange={(v) => set("prime_type", v)}>
              <SelectTrigger data-testid="f-prime-type" className="rounded-none"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="Prime 8%">Prime 8%</SelectItem>
                <SelectItem value="Prime 11%">Prime 11%</SelectItem>
                <SelectItem value="Prime 12%">Prime 12%</SelectItem>
              </SelectContent>
            </Select>
          </Field>

          <Field label="Jours maladie / perso" error={errors.sick_personal_days} testId="f-sick">
            <Input data-testid="f-sick" type="number" className="rounded-none font-mono-data" value={f.sick_personal_days} onChange={(e) => set("sick_personal_days", e.target.value)} />
          </Field>
          <Field label="Jours fériés (Noël & Jour de l'an)" error={errors.holiday_days} testId="f-holiday">
            <Input data-testid="f-holiday" type="number" className="rounded-none font-mono-data" value={f.holiday_days} onChange={(e) => set("holiday_days", e.target.value)} />
          </Field>

          <Field label="Date d'embauche" error={errors.hire_date} testId="f-hire">
            <Input data-testid="f-hire" type="date" className="rounded-none font-mono-data" value={f.hire_date} onChange={(e) => set("hire_date", e.target.value)} />
          </Field>
          <div className="flex items-end pb-1">
            <div className="flex w-full items-center gap-2 border border-dashed border-[#D4D4D8] bg-[#F4F4F5] px-3 py-2">
              <CalendarClock size={15} className="text-[#0055FF]" />
              <span className="text-[11px] uppercase tracking-wide text-[#52525B]">Ancienneté</span>
              <span data-testid="f-seniority" className="ml-auto font-mono-data text-sm font-600">
                {seniority != null ? `${seniority} an${seniority > 1 ? "s" : ""}` : "—"}
              </span>
            </div>
          </div>

          <Field label="Date de naissance" error={errors.birth_date} testId="f-birth">
            <Input data-testid="f-birth" type="date" className="rounded-none font-mono-data" value={f.birth_date} onChange={(e) => set("birth_date", e.target.value)} />
          </Field>
          <div className="flex items-end pb-1">
            <div className="flex w-full items-center gap-2 border border-dashed border-[#D4D4D8] bg-[#F4F4F5] px-3 py-2">
              <Cake size={15} className="text-[#0055FF]" />
              <span className="text-[11px] uppercase tracking-wide text-[#52525B]">Âge</span>
              <span data-testid="f-age" className="ml-auto font-mono-data text-sm font-600">
                {age != null ? `${age} ans` : "—"}
              </span>
            </div>
          </div>
        </div>

        <div className="border-t border-[#D4D4D8] pt-4">
          <p className="mb-3 font-heading text-xs font-800 uppercase tracking-widest text-[#52525B]">
            Primes & allocations
          </p>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
              ["prime_garde", "Prime de garde"],
              ["prime_chef_equipe", "Chef d'équipe"],
              ["prime_halo", "Prime HALO 5%"],
              ["alloc_securite", "Alloc. sécurité"],
            ].map(([k, lbl]) => (
              <label key={k} className="flex items-center justify-between gap-2 border border-[#D4D4D8] px-3 py-2">
                <span className="text-[11px] font-medium">{lbl}</span>
                <Switch data-testid={`f-${k}`} checked={f[k]} onCheckedChange={(v) => set(k, v)} />
              </label>
            ))}
          </div>
          {isCCQ && (
            <p className="mt-3 text-[11px] text-[#0055FF]">
              Employé CCQ : RPDB, BONI et Assurances collectives non applicables · avantages CCQ appliqués.
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" className="rounded-none" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="employee-save-btn" className="rounded-none bg-[#0055FF] hover:bg-[#0055FF]/90" onClick={submit}>
            Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function EmployeesPage() {
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [query, setQuery] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);

  const load = (q) => api.listEmployees(q).then(setEmployees);

  useEffect(() => {
    api.getHypotheses().then((h) => setDepartments(h.departments || []));
    load();
  }, []);

  useEffect(() => {
    const t = setTimeout(() => load(query), 250);
    return () => clearTimeout(t);
  }, [query]);

  const openNew = () => { setEditing(null); setDialogOpen(true); };
  const openEdit = (e) => { setEditing(e); setDialogOpen(true); };

  const handleSubmit = async (data) => {
    try {
      if (editing) { await api.updateEmployee(editing.id, data); toast.success("Employé mis à jour"); }
      else { await api.createEmployee(data); toast.success("Employé ajouté"); }
      setDialogOpen(false);
      load(query);
    } catch {
      toast.error("Erreur lors de l'enregistrement");
    }
  };

  const handleDelete = async (e) => {
    await api.deleteEmployee(e.id);
    toast.success("Employé supprimé");
    load(query);
  };

  const totalMasse = useMemo(
    () => employees.reduce((s, e) => s + e.current_annual_salary, 0),
    [employees]
  );

  return (
    <div className="space-y-4" data-testid="employees-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-heading text-2xl font-800 uppercase tracking-tight">Employés</h2>
          <p className="font-mono-data text-xs text-[#52525B]">
            {employees.length} employés · masse salariale actuelle {fmtCAD(totalMasse)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#52525B]" />
            <Input
              data-testid="employee-search"
              placeholder="Rechercher nom, département, titre…"
              className="w-72 rounded-none pl-9"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <Button data-testid="add-employee-btn" onClick={openNew} className="gap-1.5 rounded-none bg-[#09090B] hover:bg-[#09090B]/90">
            <Plus size={16} /> Ajouter
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto border border-[#D4D4D8] bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#D4D4D8] text-[11px] uppercase tracking-wider text-[#52525B]">
              <th className="px-3 py-2.5 text-left font-600">#</th>
              <th className="px-3 py-2.5 text-left font-600">Nom</th>
              <th className="px-3 py-2.5 text-left font-600">Département</th>
              <th className="px-3 py-2.5 text-left font-600">Type</th>
              <th className="px-3 py-2.5 text-left font-600">Catégorie</th>
              <th className="px-3 py-2.5 text-right font-600">Salaire</th>
              <th className="px-3 py-2.5 text-right font-600">Âge</th>
              <th className="px-3 py-2.5 text-right font-600">Ancienneté</th>
              <th className="px-3 py-2.5 text-right font-600">Actions</th>
            </tr>
          </thead>
          <tbody>
            {employees.map((e) => (
              <tr key={e.id} className="border-b border-[#F4F4F5] hover:bg-[#F4F4F5]" data-testid={`employee-row-${e.employee_number}`}>
                <td className="px-3 py-2.5 font-mono-data text-[#52525B]">{String(e.employee_number).padStart(3, "0")}</td>
                <td className="px-3 py-2.5 font-medium">{e.name}<div className="text-[11px] text-[#52525B]">{e.title}</div></td>
                <td className="px-3 py-2.5 text-[13px]">{e.department}</td>
                <td className="px-3 py-2.5">
                  <span className="px-1.5 py-0.5 text-[10px] font-600 uppercase text-white" style={{ backgroundColor: e.is_ccq ? "#0055FF" : "#09090B" }}>
                    {e.employment_type}
                  </span>
                </td>
                <td className="px-3 py-2.5 text-[13px]">{e.ccq_category !== "N/A" ? e.ccq_category : "—"}</td>
                <td className="px-3 py-2.5 text-right font-mono-data">{fmtCAD(e.current_annual_salary)}</td>
                <td className="px-3 py-2.5 text-right font-mono-data">{computeAge(e.birth_date)}</td>
                <td className="px-3 py-2.5 text-right font-mono-data">{computeSeniority(e.hire_date)} ans</td>
                <td className="px-3 py-2.5">
                  <div className="flex justify-end gap-1">
                    <button data-testid={`edit-employee-${e.employee_number}`} onClick={() => openEdit(e)} className="p-1.5 text-[#52525B] transition-colors hover:text-[#0055FF]"><Pencil size={14} /></button>
                    <button data-testid={`delete-employee-${e.employee_number}`} onClick={() => handleDelete(e)} className="p-1.5 text-[#52525B] transition-colors hover:text-[#FF4500]"><Trash2 size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {employees.length === 0 && (
              <tr><td colSpan={9} className="px-3 py-10 text-center text-sm text-[#52525B]">Aucun employé trouvé.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {dialogOpen && (
        <EmployeeForm open={dialogOpen} onOpenChange={setDialogOpen} initial={editing} departments={departments} onSubmit={handleSubmit} />
      )}
    </div>
  );
}
