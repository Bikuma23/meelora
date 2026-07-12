import { fmtCAD, computeAge, computeSeniority } from "../lib/format";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "../components/ui/dialog";
import { Pencil, TrendingUp } from "lucide-react";
import { Button } from "../components/ui/button";

const typeLabel = (t) => ({ "Régulier temps plein": "Rég. Temps Plein", "Régulier temps partiel": "Rég. Temps Partiel" }[t] || t);
const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("fr-CA") : "—");

function Row({ label, value, accent }) {
  return (
    <div className="flex items-center justify-between px-3 py-1.5 text-sm">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono-data text-right" style={accent ? { color: accent } : {}}>{value}</span>
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div className="rounded-xl border border-slate-200">
      <div className="border-b border-slate-200 bg-slate-50 px-3 py-2"><h3 className="text-xs font-700 uppercase tracking-widest">{title}</h3></div>
      <div className="divide-y divide-slate-100">{children}</div>
    </div>
  );
}

export default function EmployeeDetailDialog({ open, onOpenChange, employee, departments = [], securityClasses = [], year, canEdit, onEdit, onViewBudget }) {
  if (!employee) return null;
  const e = employee;
  const dept = departments.find((d) => d.code === e.department);
  const secClass = (securityClasses || []).find((c) => c.code === e.security_class);
  const yesNo = (b) => (b ? "Oui" : "Non");
  const yd = (e.years || {})[String(year)] || {};
  const deptFor = (sc) => (yd[sc] && yd[sc].department) || e.department;
  const deptName = (code) => { const d = departments.find((x) => x.code === code); return d ? `${code} — ${d.description}` : code; };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto" data-testid="employee-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {e.name} — #{String(e.employee_number).padStart(3, "0")}
            {e.active === false && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[9px] font-700 uppercase text-red-600">Inactif</span>}
          </DialogTitle>
          <DialogDescription className="font-mono-data text-xs">
            {e.title || "—"} · {e.department} {dept ? `— ${dept.description}` : ""} · {e.is_ccq ? "CCQ" : typeLabel(e.employment_type)}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <Section title="Informations">
              <Row label="Matricule" value={String(e.employee_number).padStart(3, "0")} />
              <Row label="Titre / Poste" value={e.title || "—"} />
              <Row label="Département" value={`${e.department}${dept ? " — " + dept.description : ""}`} />
              <Row label="Superviseur" value={e.supervisor || dept?.superviseur || "—"} />
              <Row label="Type d'emploi" value={typeLabel(e.employment_type)} />
              {e.is_ccq && <Row label="Catégorie CCQ" value={e.ccq_category || "—"} />}
              <Row label="Sexe à la naissance" value={e.sex_at_birth || "—"} />
              <Row label="Statut" value={e.active === false ? "Inactif" : "Actif"} accent={e.active === false ? "#EF4444" : "#0E9488"} />
            </Section>
            <Section title="Classe de sécurité CNESST">
              <Row label="Code" value={e.security_class || "—"} />
              <Row label="Description" value={secClass?.description || "—"} />
              {secClass && <Row label="Taux" value={`${(secClass.rate * 100).toFixed(4)} %`} />}
            </Section>
            <Section title={`Département par version${year ? " — " + year : ""}`}>
              {[["ca", "Budget CA"], ["revue1", "Revue 1"], ["revue2", "Revue 2"]].map(([sc, lbl]) => {
                const code = deptFor(sc);
                const moved = code !== e.department;
                return <Row key={sc} label={lbl} value={deptName(code)} accent={moved ? "#B45309" : undefined} />;
              })}
            </Section>
          </div>

          <div className="space-y-4">
            <Section title="Rémunération">
              <Row label="Salaire annuel actuel" value={fmtCAD(e.current_annual_salary)} accent="#2563EB" />
              <Row label="Taux de vacances" value={`${(e.vacation_rate * 100).toFixed(2)} %`} />
              <Row label="Jours maladie / personnels" value={e.sick_personal_days} />
              <Row label="Jours fériés" value={e.holiday_days} />
            </Section>
            <Section title="Primes & allocations">
              <Row label="Type de prime" value={e.prime_type || "Aucune Prime"} />
              <Row label="Prime de garde" value={yesNo(e.prime_garde)} />
              <Row label="Prime HALO" value={yesNo(e.prime_halo)} />
              <Row label="Alloc. sécurité" value={yesNo(e.alloc_securite)} />
            </Section>
            <Section title="Dates & ancienneté">
              <Row label="Date d'embauche" value={fmtDate(e.hire_date)} />
              <Row label="Date de naissance" value={`${fmtDate(e.birth_date)} (${computeAge(e.birth_date)} ans)`} />
              {e.end_date && <Row label="Date de fin d'emploi" value={fmtDate(e.end_date)} accent="#B45309" />}
              <Row label="Ancienneté" value={`${computeSeniority(e.hire_date)} ans`} />
            </Section>
          </div>
        </div>

        {(onViewBudget || canEdit) && (
          <div className="flex flex-col gap-2 sm:flex-row">
            {onViewBudget && (
              <Button data-testid="employee-detail-budget-btn" variant="outline" onClick={() => { onOpenChange(false); onViewBudget(e); }} className="flex-1 gap-1.5">
                <TrendingUp size={15} /> Voir le budget
              </Button>
            )}
            {canEdit && (
              <Button data-testid="employee-detail-edit-btn" onClick={() => { onOpenChange(false); onEdit(e); }} className="flex-1 gap-1.5 bg-[#2563EB] hover:bg-[#2563EB]/90">
                <Pencil size={15} /> Modifier cet employé
              </Button>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
