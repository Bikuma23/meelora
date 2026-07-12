import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useYear } from "../context/YearContext";
import { fmtCAD, computeAge, computeSeniority } from "../lib/format";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Plus, Pencil, Trash2, Search, Cake, CalendarClock, Upload, Download, ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";
import { toast } from "sonner";
import ImportErrorsDialog from "../components/ImportErrorsDialog";
import EmployeeDetailDialog from "../components/EmployeeDetailDialog";
import BudgetDetailDialog from "../components/BudgetDetailDialog";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "../components/ui/alert-dialog";

const REQ = "Ce champ est obligatoire";
const TYPES = ["CCQ", "Régulier temps plein", "Régulier temps partiel", "Stagiaire"];
const typeLabel = (t) => ({ "Régulier temps plein": "Rég. Temps Plein", "Régulier temps partiel": "Rég. Temps Partiel" }[t] || t);
const SEXES = ["Masculin", "Féminin", "Autre", "Préfère ne pas répondre"];
const empty = {
  name: "", department: "", title: "", employment_type: "Régulier temps plein", ccq_category: "N/A",
  current_annual_salary: "", vacation_rate_pct: "", sick_personal_days: "", holiday_days: "",
  prime_type: "Aucune Prime", prime_garde: false, prime_halo: false, alloc_securite: false, hire_date: "", birth_date: "",
  active: true, sex_at_birth: "", end_date: "", supervisor: "", security_class: "",
};

function Field({ label, error, testId, children }) {
  return (
    <div>
      <Label className="text-[11px] font-600 uppercase tracking-wide text-slate-500">{label}</Label>
      <div className="mt-1">{children}</div>
      {error && <p data-testid={`${testId}-error`} className="mt-1 text-[11px] font-500 text-red-500">{error}</p>}
    </div>
  );
}

function EmpForm({ open, onOpenChange, initial, departments, securityClasses = [], onSubmit }) {
  const [f, setF] = useState(empty);
  const [errors, setErrors] = useState({});
  useEffect(() => {
    if (initial) setF({
      name: initial.name, department: initial.department, title: initial.title, employment_type: initial.employment_type,
      ccq_category: initial.ccq_category, current_annual_salary: String(initial.current_annual_salary),
      vacation_rate_pct: String(+(initial.vacation_rate * 100).toFixed(2)), sick_personal_days: String(initial.sick_personal_days),
      holiday_days: String(initial.holiday_days), prime_type: initial.prime_type, prime_garde: initial.prime_garde,
      prime_halo: initial.prime_halo, alloc_securite: initial.alloc_securite, hire_date: initial.hire_date, birth_date: initial.birth_date,
      active: initial.active !== false, sex_at_birth: initial.sex_at_birth || "", end_date: initial.end_date || "",
      supervisor: (departments.find((d) => d.code === initial.department)?.superviseur) || initial.supervisor || "", security_class: initial.security_class || "",
    });
    else setF(empty);
    setErrors({});
  }, [initial, open]);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const isCCQ = f.employment_type === "CCQ";

  const submit = () => {
    const e = {};
    if (!f.name.trim()) e.name = REQ;
    if (!f.department) e.department = REQ;
    if (!f.title.trim()) e.title = REQ;
    if (isCCQ && f.ccq_category === "N/A") e.ccq_category = "Électricien ou Frigoriste";
    if (f.current_annual_salary === "" || Number(f.current_annual_salary) <= 0) e.current_annual_salary = "Salaire requis (> 0)";
    if (f.vacation_rate_pct === "") e.vacation_rate_pct = REQ;
    if (f.sick_personal_days === "") e.sick_personal_days = REQ;
    if (f.holiday_days === "") e.holiday_days = REQ;
    if (!f.hire_date) e.hire_date = REQ;
    if (!f.birth_date) e.birth_date = REQ;
    setErrors(e);
    if (Object.keys(e).length) { toast.error("Veuillez corriger les champs obligatoires"); return; }
    onSubmit({
      name: f.name.trim(), department: f.department, title: f.title.trim(), employment_type: f.employment_type,
      ccq_category: isCCQ ? f.ccq_category : "N/A", current_annual_salary: Number(f.current_annual_salary),
      vacation_rate: Number(f.vacation_rate_pct) / 100, sick_personal_days: parseInt(f.sick_personal_days, 10),
      holiday_days: parseInt(f.holiday_days, 10), is_ccq: isCCQ, prime_type: isCCQ ? f.prime_type : "Aucune Prime",
      prime_garde: isCCQ && f.prime_garde, prime_halo: isCCQ && f.prime_halo, alloc_securite: f.alloc_securite,
      hire_date: f.hire_date, birth_date: f.birth_date,
      active: f.active, sex_at_birth: f.sex_at_birth || null, end_date: f.end_date || null,
      supervisor: f.supervisor || null, security_class: f.security_class || null,
    });
  };

  const age = computeAge(f.birth_date), sen = computeSeniority(f.hire_date);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto" data-testid="employee-form-dialog">
        <DialogHeader>
          <DialogTitle>{initial ? `${initial.name} — #${String(initial.employee_number).padStart(3, "0")}` : "Nouvel employé"}</DialogTitle>
          <DialogDescription className="text-xs">Âge et ancienneté calculés automatiquement. Le sexe à la naissance est facultatif.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 py-1 sm:grid-cols-2">
          <Field label="Nom complet" error={errors.name} testId="f-name"><Input data-testid="f-name" value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
          <Field label="Statut" testId="f-active">
            <label className="flex h-10 w-full items-center justify-between gap-2 rounded-lg border border-slate-200 px-3">
              <span className={`text-[11px] font-600 uppercase ${f.active ? "text-emerald-600" : "text-red-500"}`}>{f.active ? "Actif" : "Inactif"}</span>
              <Switch data-testid="f-active" checked={f.active} onCheckedChange={(v) => set("active", v)} />
            </label>
          </Field>
          <Field label="Sexe à la naissance" testId="f-sex">
            <Select value={f.sex_at_birth} onValueChange={(v) => set("sex_at_birth", v)}>
              <SelectTrigger data-testid="f-sex"><SelectValue placeholder="Sélectionner…" /></SelectTrigger>
              <SelectContent>{SEXES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <div className="hidden sm:block" />
          <Field label="Date de naissance" error={errors.birth_date} testId="f-birth"><Input data-testid="f-birth" type="date" className="font-mono-data" value={f.birth_date} onChange={(e) => set("birth_date", e.target.value)} /></Field>
          <Field label="Âge (calculé)" testId="f-age-box">
            <div className="flex h-10 w-full items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3">
              <Cake size={15} className="text-[#2563EB]" />
              <span data-testid="f-age" className="ml-auto font-mono-data text-sm font-700">{age != null ? `${age} ans` : "—"}</span>
            </div>
          </Field>
          <Field label="Superviseur (du département)" testId="f-supervisor"><Input data-testid="f-supervisor" value={f.supervisor} readOnly placeholder="Sélectionnez un département" className="bg-slate-50 text-slate-600" /></Field>
          <Field label="Titre / Poste" error={errors.title} testId="f-title"><Input data-testid="f-title" value={f.title} onChange={(e) => set("title", e.target.value)} /></Field>
          <Field label="Département" error={errors.department} testId="f-department">
            <Select value={f.department} onValueChange={(v) => setF((p) => ({ ...p, department: v, supervisor: departments.find((d) => d.code === v)?.superviseur || "" }))}>
              <SelectTrigger data-testid="f-department"><SelectValue placeholder="Sélectionner…" /></SelectTrigger>
              <SelectContent className="max-h-64">{departments.map((d) => <SelectItem key={d.code} value={d.code}>{d.code} — {d.description}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Type d'emploi" error={errors.employment_type} testId="f-type">
            <Select value={f.employment_type} onValueChange={(v) => set("employment_type", v)}>
              <SelectTrigger data-testid="f-type"><SelectValue /></SelectTrigger>
              <SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          <Field label="Classe de sécurité (CSST)" testId="f-security-class">
            <Select value={f.security_class || "none"} onValueChange={(v) => set("security_class", v === "none" ? "" : v)}>
              <SelectTrigger data-testid="f-security-class"><SelectValue placeholder="Aucune" /></SelectTrigger>
              <SelectContent><SelectItem value="none">Aucune</SelectItem>{securityClasses.map((c) => <SelectItem key={c.code} value={c.code}>{c.code} — {c.description} ({(c.rate * 100).toFixed(2)}%)</SelectItem>)}</SelectContent>
            </Select>
          </Field>
          {isCCQ && (
            <Field label="Catégorie CCQ" error={errors.ccq_category} testId="f-ccq-category">
              <Select value={f.ccq_category} onValueChange={(v) => set("ccq_category", v)}>
                <SelectTrigger data-testid="f-ccq-category"><SelectValue placeholder="Sélectionner…" /></SelectTrigger>
                <SelectContent><SelectItem value="Électricien">Électricien</SelectItem><SelectItem value="Frigoriste">Frigoriste</SelectItem></SelectContent>
              </Select>
            </Field>
          )}
          {isCCQ && (
            <Field label="Type de prime" error={errors.prime_type} testId="f-prime-type">
              <Select value={f.prime_type} onValueChange={(v) => set("prime_type", v)}>
                <SelectTrigger data-testid="f-prime-type"><SelectValue /></SelectTrigger>
                <SelectContent>{["Aucune Prime", "Prime 8%", "Prime 11%", "Prime 12%"].map((x) => <SelectItem key={x} value={x}>{x}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          )}
          <Field label="Salaire annuel actuel ($)" error={errors.current_annual_salary} testId="f-salary"><Input data-testid="f-salary" type="number" className="font-mono-data" value={f.current_annual_salary} onChange={(e) => set("current_annual_salary", e.target.value)} /></Field>
          <Field label="Taux de vacances (%)" error={errors.vacation_rate_pct} testId="f-vacation"><Input data-testid="f-vacation" type="number" step="0.1" className="font-mono-data" value={f.vacation_rate_pct} onChange={(e) => set("vacation_rate_pct", e.target.value)} /></Field>
          <Field label="Jours maladie / perso (informatif)" error={errors.sick_personal_days} testId="f-sick"><Input data-testid="f-sick" type="number" className="font-mono-data" value={f.sick_personal_days} onChange={(e) => set("sick_personal_days", e.target.value)} /></Field>
          <Field label="Jours fériés (Noël & Jour de l'an) (informatif)" error={errors.holiday_days} testId="f-holiday"><Input data-testid="f-holiday" type="number" className="font-mono-data" value={f.holiday_days} onChange={(e) => set("holiday_days", e.target.value)} /></Field>
          <Field label="Date d'embauche" error={errors.hire_date} testId="f-hire"><Input data-testid="f-hire" type="date" className="font-mono-data" value={f.hire_date} onChange={(e) => set("hire_date", e.target.value)} /></Field>
          <Field label="Ancienneté (calculée)" testId="f-seniority-box">
            <div className="flex h-10 w-full items-center gap-2 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-3">
              <CalendarClock size={15} className="text-[#2563EB]" />
              <span data-testid="f-seniority" className="ml-auto font-mono-data text-sm font-700">{sen != null ? `${sen} an${sen > 1 ? "s" : ""}` : "—"}</span>
            </div>
          </Field>
          <Field label="Date de fin d'emploi (optionnel)" testId="f-end"><Input data-testid="f-end" type="date" className="font-mono-data" value={f.end_date} onChange={(e) => set("end_date", e.target.value)} /></Field>
          <div className="hidden sm:block" />
        </div>
        <div className="border-t border-slate-200 pt-4">
          <p className="mb-2 text-xs font-700 uppercase tracking-widest text-slate-500">Primes & allocations</p>
          {isCCQ ? (
            <div className="grid grid-cols-3 gap-3">
              {[["prime_garde", "Prime de garde"], ["prime_halo", "Prime HALO 5%"], ["alloc_securite", "Alloc. sécurité"]].map(([k, lbl]) => (
                <label key={k} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2"><span className="text-[11px] font-500">{lbl}</span><Switch data-testid={`f-${k}`} checked={f[k]} onCheckedChange={(v) => set(k, v)} /></label>
              ))}
            </div>
          ) : (
            <div className="space-y-2">
              <div className="grid grid-cols-3 gap-3">
                <label className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2"><span className="text-[11px] font-500">Alloc. sécurité</span><Switch data-testid="f-alloc_securite" checked={f.alloc_securite} onCheckedChange={(v) => set("alloc_securite", v)} /></label>
              </div>
              <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-3 py-2.5 text-[11px] text-slate-500">Primes CCQ (garde, HALO) non applicables. Le BONI, le REER et l'assurance collective se gèrent dans la fiche Salaires & Budget.</p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="employee-save-btn" className="bg-[#2563EB] hover:bg-[#2563EB]/90" onClick={submit}>Enregistrer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function Employes() {
  const { user } = useAuth();
  const { year } = useYear();
  const canEdit = ["admin", "editor"].includes(user?.role);
  const [employees, setEmployees] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [query, setQuery] = useState("");
  const [dialog, setDialog] = useState({ open: false, item: null });
  const [importErrors, setImportErrors] = useState({ open: false, errors: [], fileName: "" });
  const [confirmDel, setConfirmDel] = useState(null);
  const [detail, setDetail] = useState({ open: false, item: null });
  const [scenario, setScenario] = useState("ca");
  const [budgetDetail, setBudgetDetail] = useState({ open: false, line: null });
  const [showInactive, setShowInactive] = useState(false);
  const [securityClasses, setSecurityClasses] = useState([]);
  const [sort, setSort] = useState({ key: "employee_number", dir: "asc" });
  const [prefsLoaded, setPrefsLoaded] = useState(false);
  const toggleSort = (key) => setSort((s) => s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" });
  const fileRef = useRef();

  const load = (q, inc) => api.listEmployees({ ...(q ? { q } : {}), ...((inc ?? showInactive) ? { include_inactive: true } : {}) }).then(setEmployees);
  useEffect(() => { api.listDepartments().then(setDepartments); api.getHypotheses().then((h) => setSecurityClasses(h.security_classes || [])).catch(() => {}); load(); }, []);
  useEffect(() => { const t = setTimeout(() => load(query), 250); return () => clearTimeout(t); }, [query, showInactive]);
  useEffect(() => {
    api.getPreferences().then((p) => { if (p?.employees_sort?.key) setSort(p.employees_sort); if (p?.budget_scenario) setScenario(p.budget_scenario); }).catch(() => {}).finally(() => setPrefsLoaded(true));
  }, []);
  useEffect(() => {
    if (prefsLoaded) api.updatePreferences({ employees_sort: sort }).catch(() => {});
  }, [sort, prefsLoaded]);

  const submit = async (data) => {
    try {
      if (dialog.item) { await api.updateEmployee(dialog.item.id, data); toast.success("Employé mis à jour"); }
      else { await api.createEmployee(data); toast.success("Employé ajouté"); }
      setDialog({ open: false, item: null }); load(query);
    } catch { toast.error("Erreur lors de l'enregistrement"); }
  };
  const del = async (e) => { await api.deleteEmployee(e.id); toast.success("Employé supprimé"); load(query); };
  const onImport = async (ev) => {
    const file = ev.target.files?.[0];
    if (!file) return;
    try {
      const res = await api.importEmployees(file);
      if (res.aborted || res.errors?.length) {
        setImportErrors({ open: true, errors: res.errors || [], fileName: file.name });
        toast.error(`Importation annulée — ${res.errors.length} erreur(s)`);
      } else {
        toast.success(`${res.inserted} ajout(s)${res.updated ? `, ${res.updated} mise(s) à jour` : ""}`);
        load(query);
      }
    } catch (e) { toast.error(e.response?.data?.detail || "Import échoué"); }
    finally { ev.target.value = ""; }
  };

  const dl = employees.reduce((s, e) => s + e.current_annual_salary, 0);
  const classMap = Object.fromEntries((securityClasses || []).map((c) => [c.code, c]));

  const sortVal = (e, key) => {
    if (key === "age") return computeAge(e.birth_date) ?? -1;
    if (key === "seniority") return computeSeniority(e.hire_date) ?? -1;
    if (key === "employment_type") return e.is_ccq ? "CCQ" : typeLabel(e.employment_type);
    if (key === "security_class") return classMap[e.security_class]?.description || e.security_class || "";
    const v = e[key];
    return v == null ? "" : v;
  };
  const sortedEmployees = [...employees].sort((a, b) => {
    const va = sortVal(a, sort.key), vb = sortVal(b, sort.key);
    const cmp = typeof va === "string" ? va.localeCompare(vb, "fr") : (va - vb);
    return sort.dir === "asc" ? cmp : -cmp;
  });
  const HEAD = [
    ["#", "left", "employee_number"], ["Titre / Poste", "left", "title"], ["Nom", "left", "name"],
    ["Dépt", "left", "department"], ["Type", "left", "employment_type"], ["Classe de sécurité", "left", "security_class"],
    ["Salaire", "right", "current_annual_salary"], ["Âge", "right", "age"], ["Ancien.", "right", "seniority"], ["Actions", "right", null],
  ];

  const dlTemplate = async () => {
    try {
      const blob = await api.downloadTemplate("employees");
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = "modele_employes.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Téléchargement du modèle échoué"); }
  };

  const viewBudget = async (e) => {
    try {
      const b = await api.getBudget({ year, scenario });
      const line = (b.lines || []).find((l) => l.employee_number === e.employee_number || l.employee_id === e.id);
      if (!line) { toast.error(`Aucune fiche budget pour cet employé (${year} · ${scenario}).`); return; }
      setBudgetDetail({ open: true, line });
    } catch { toast.error("Chargement du budget échoué"); }
  };

  return (
    <div className="space-y-4" data-testid="employees-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500"><b className="text-slate-800">{employees.length}</b> employés · masse actuelle {fmtCAD(dl)}</p>
        <div className="flex flex-wrap items-center gap-2">
          <label className="card flex items-center gap-2 px-3 py-2 text-[11px] font-600 uppercase text-slate-500" data-testid="toggle-inactive-label">
            Afficher inactifs <Switch data-testid="toggle-inactive" checked={showInactive} onCheckedChange={setShowInactive} />
          </label>
          <div className="card flex items-center gap-2 px-3 py-2">
            <Search size={15} className="text-slate-400" />
            <input data-testid="employee-search" className="w-56 bg-transparent text-sm outline-none" placeholder="Rechercher…" value={query} onChange={(e) => setQuery(e.target.value)} />
          </div>
          <Button variant="outline" className="gap-1.5" data-testid="employee-template-btn" onClick={dlTemplate}><Download size={15} /> Modèle</Button>
          {canEdit && <>
          <input ref={fileRef} type="file" accept=".xlsx" className="hidden" data-testid="employee-import-input" onChange={onImport} />
          <Button variant="outline" className="gap-1.5" data-testid="employee-import-btn" onClick={() => fileRef.current?.click()}><Upload size={15} /> Importer Excel</Button>
          <Button data-testid="add-employee-btn" className="gap-1.5 bg-[#2563EB] hover:bg-[#2563EB]/90" onClick={() => setDialog({ open: true, item: null })}><Plus size={16} /> Ajouter</Button>
          </>}
        </div>
      </div>

      <div className="card">
        <div className="hidden overflow-x-auto md:block">
          <table className="w-full min-w-[860px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
                {HEAD.map(([h, al, key]) => (
                  <th key={h} data-testid={key ? `sort-${key}` : "col-actions"} onClick={key ? () => toggleSort(key) : undefined}
                    className={`px-4 py-3 font-600 ${al === "right" ? "text-right" : "text-left"} ${key ? "cursor-pointer select-none hover:text-slate-600" : ""}`}>
                    <span className={`inline-flex items-center gap-1 ${al === "right" ? "flex-row-reverse" : ""}`}>
                      {h}
                      {key && (sort.key === key
                        ? (sort.dir === "asc" ? <ChevronUp size={13} className="text-[#2563EB]" /> : <ChevronDown size={13} className="text-[#2563EB]" />)
                        : <ChevronsUpDown size={12} className="opacity-40" />)}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sortedEmployees.map((e) => (
                <tr key={e.id} onClick={() => setDetail({ open: true, item: e })} className={`cursor-pointer border-b border-slate-100 hover:bg-slate-50 ${e.active === false ? "opacity-60" : ""}`} data-testid={`employee-row-${e.employee_number}`}>
                  <td className="px-4 py-2.5 font-mono-data text-slate-400">{String(e.employee_number).padStart(3, "0")}</td>
                  <td className="px-4 py-2.5 text-[13px] text-slate-600">{e.title || "—"}</td>
                  <td className="px-4 py-2.5 font-600">{e.name}{e.active === false && <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-[9px] font-700 uppercase text-red-600">Inactif</span>}</td>
                  <td className="px-4 py-2.5 text-[13px]">{e.department}</td>
                  <td className="px-4 py-2.5"><span className="rounded px-1.5 py-0.5 text-[10px] font-600 uppercase text-white" style={{ backgroundColor: e.is_ccq ? "#2563EB" : "#64748B" }}>{e.is_ccq ? "CCQ" : typeLabel(e.employment_type)}</span></td>
                  <td className="px-4 py-2.5" data-testid={`employee-secclass-${e.employee_number}`}>
                    {e.security_class ? (
                      <div className="flex flex-col leading-tight">
                        <span className="font-mono-data text-[11px] font-700 text-slate-700">{e.security_class}</span>
                        <span className="text-[11px] text-slate-500">{classMap[e.security_class]?.description || "—"}</span>
                      </div>
                    ) : <span className="text-slate-300">—</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{fmtCAD(e.current_annual_salary)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{computeAge(e.birth_date)}</td>
                  <td className="px-4 py-2.5 text-right font-mono-data">{computeSeniority(e.hire_date)} ans</td>
                  <td className="px-4 py-2.5">
                    {canEdit ? (
                    <div className="flex justify-end gap-1">
                      <button data-testid={`edit-employee-${e.employee_number}`} onClick={(ev) => { ev.stopPropagation(); setDialog({ open: true, item: e }); }} className="p-1.5 text-slate-400 hover:text-[#2563EB]"><Pencil size={15} /></button>
                      <button data-testid={`delete-employee-${e.employee_number}`} onClick={(ev) => { ev.stopPropagation(); setConfirmDel(e); }} className="p-1.5 text-slate-400 hover:text-red-500"><Trash2 size={15} /></button>
                    </div>
                    ) : <div className="text-right text-slate-300">—</div>}
                  </td>
                </tr>
              ))}
              {employees.length === 0 && <tr><td colSpan={10} className="px-4 py-10 text-center text-sm text-slate-500">Aucun employé trouvé.</td></tr>}
            </tbody>
          </table>
        </div>

        <div className="divide-y divide-slate-100 md:hidden" data-testid="employee-cards">
          {sortedEmployees.map((e) => (
            <div key={e.id} onClick={() => setDetail({ open: true, item: e })} className={`cursor-pointer p-4 active:bg-slate-50 ${e.active === false ? "opacity-60" : ""}`} data-testid={`employee-card-${e.employee_number}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-700">{e.name}{e.active === false && <span className="ml-2 rounded bg-red-100 px-1.5 py-0.5 text-[9px] font-700 uppercase text-red-600">Inactif</span>}</p>
                  <p className="truncate text-[13px] text-slate-500">{e.title || "—"}</p>
                  <div className="mt-1 flex flex-wrap items-center gap-1.5">
                    <span className="font-mono-data text-[11px] text-slate-400">#{String(e.employee_number).padStart(3, "0")}</span>
                    <span className="font-mono-data text-[11px] text-slate-400">· Dépt {e.department}</span>
                    <span className="rounded px-1.5 py-0.5 text-[9px] font-600 uppercase text-white" style={{ backgroundColor: e.is_ccq ? "#2563EB" : "#64748B" }}>{e.is_ccq ? "CCQ" : typeLabel(e.employment_type)}</span>
                  </div>
                </div>
                {canEdit && (
                <div className="flex shrink-0 gap-1">
                  <button data-testid={`edit-employee-card-${e.employee_number}`} onClick={(ev) => { ev.stopPropagation(); setDialog({ open: true, item: e }); }} className="rounded-lg border border-slate-200 p-2 text-slate-400 hover:text-[#2563EB]"><Pencil size={15} /></button>
                  <button data-testid={`delete-employee-card-${e.employee_number}`} onClick={(ev) => { ev.stopPropagation(); setConfirmDel(e); }} className="rounded-lg border border-slate-200 p-2 text-slate-400 hover:text-red-500"><Trash2 size={15} /></button>
                </div>
                )}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-[13px]">
                <div className="flex justify-between"><span className="text-slate-500">Salaire</span><span className="font-mono-data">{fmtCAD(e.current_annual_salary)}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Âge</span><span className="font-mono-data">{computeAge(e.birth_date)}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Ancienneté</span><span className="font-mono-data">{computeSeniority(e.hire_date)} ans</span></div>
                <div className="flex justify-between"><span className="text-slate-500">Classe séc.</span><span className="font-mono-data text-right">{e.security_class ? `${e.security_class}` : "—"}</span></div>
                {e.security_class && classMap[e.security_class]?.description && <div className="col-span-2 text-right text-[11px] text-slate-400">{classMap[e.security_class].description}</div>}
              </div>
            </div>
          ))}
          {employees.length === 0 && <p className="px-4 py-10 text-center text-sm text-slate-500">Aucun employé trouvé.</p>}
        </div>
      </div>

      {dialog.open && <EmpForm open={dialog.open} onOpenChange={(v) => setDialog((p) => ({ ...p, open: v }))} initial={dialog.item} departments={departments} securityClasses={securityClasses} onSubmit={submit} />}
      <EmployeeDetailDialog open={detail.open} onOpenChange={(v) => setDetail((p) => ({ ...p, open: v }))} employee={detail.item} departments={departments} securityClasses={securityClasses} canEdit={canEdit} onEdit={(e) => setDialog({ open: true, item: e })} onViewBudget={viewBudget} />
      <BudgetDetailDialog open={budgetDetail.open} onOpenChange={(v) => setBudgetDetail((p) => ({ ...p, open: v }))} line={budgetDetail.line} year={year} scenario={scenario} canEdit={false} onEdit={() => {}} />
      <ImportErrorsDialog open={importErrors.open} onOpenChange={(v) => setImportErrors((p) => ({ ...p, open: v }))} errors={importErrors.errors} fileName={importErrors.fileName} />
      <AlertDialog open={!!confirmDel} onOpenChange={(v) => !v && setConfirmDel(null)}>
        <AlertDialogContent data-testid="delete-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer cet employé ?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDel ? `« ${confirmDel.name} » (#${String(confirmDel.employee_number).padStart(3, "0")}) sera définitivement supprimé, ainsi que ses budgets saisis. Cette action est irréversible.` : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="delete-cancel-btn">Annuler</AlertDialogCancel>
            <AlertDialogAction data-testid="delete-confirm-btn" className="bg-red-600 hover:bg-red-700"
              onClick={async () => { const e = confirmDel; setConfirmDel(null); await del(e); }}>
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
