import { fmtCAD, computeAge, computeSeniority } from "../lib/format";
import { useLang } from "../context/LanguageContext";
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

export default function EmployeeDetailDialog({ open, onOpenChange, employee, departments = [], securityClasses = [], year, versions, canEdit, onEdit, onViewBudget }) {
  const { t } = useLang();
  if (!employee) return null;
  const e = employee;
  const dept = departments.find((d) => d.code === e.department);
  const secClass = (securityClasses || []).find((c) => c.code === e.security_class);
  const yesNo = (b) => (b ? t("Oui") : t("Non"));
  const yd = (e.years || {})[String(year)] || {};
  const deptFor = (sc) => (yd[sc] && yd[sc].department) || e.department;
  const deptName = (code) => { const d = departments.find((x) => x.code === code); return d ? `${code} — ${d.description}` : code; };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-4xl overflow-y-auto" data-testid="employee-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {e.name} — #{String(e.employee_number).padStart(3, "0")}
            {e.active === false && <span className="rounded bg-red-100 px-1.5 py-0.5 text-[9px] font-700 uppercase text-red-600">{t("Inactif")}</span>}
          </DialogTitle>
          <DialogDescription className="font-mono-data text-xs">
            {e.title || "—"} · {e.department} {dept ? `— ${dept.description}` : ""} · {e.is_ccq ? "CCQ" : t(typeLabel(e.employment_type))}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            <Section title={t("Informations")}>
              <Row label={t("Matricule")} value={String(e.employee_number).padStart(3, "0")} />
              <Row label={t("Titre / Poste")} value={e.title || "—"} />
              <Row label={t("Département")} value={`${e.department}${dept ? " — " + dept.description : ""}`} />
              <Row label={t("Superviseur")} value={e.supervisor || dept?.superviseur || "—"} />
              <Row label={t("Type d'emploi")} value={t(typeLabel(e.employment_type))} />
              {e.is_ccq && <Row label={t("Catégorie CCQ")} value={e.ccq_category || "—"} />}
              <Row label={t("Sexe à la naissance")} value={e.sex_at_birth ? t(e.sex_at_birth) : "—"} />
              <Row label={t("Statut")} value={e.active === false ? t("Inactif") : t("Actif")} accent={e.active === false ? "#EF4444" : "#0E9488"} />
            </Section>
            <Section title={t("Classe de sécurité CNESST")}>
              <Row label={t("Code")} value={e.security_class || "—"} />
              <Row label={t("Description")} value={secClass?.description || "—"} />
              {secClass && <Row label={t("Taux")} value={`${(secClass.rate * 100).toFixed(4)} %`} />}
            </Section>
            <Section title={`${t("Par version")}${year ? " — " + year : ""}`}>
              {[["ca", "Budget CA"], ["revue1", "Revue 1"], ["revue2", "Revue 2"]].map(([sc, lbl]) => {
                const v = versions && versions[sc];
                const code = (v && v.department) || deptFor(sc);
                const moved = code !== e.department;
                const etype = (v && v.employment_type) || (yd[sc] && yd[sc].employment_type) || e.employment_type;
                const rate = v && v.employment_rate != null && v.employment_rate < 1 ? ` (${Math.round(v.employment_rate * 100)}%)` : "";
                return (
                  <div key={sc} className="px-3 py-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-700 text-slate-700">{t(lbl)}</span>
                      {v ? <span className="font-mono-data font-700">{fmtCAD(v.total_budgeted)}</span> : <span className="text-[11px] text-slate-400">…</span>}
                    </div>
                    <div className="mt-0.5 flex items-center justify-between text-[12px]">
                      <span style={moved ? { color: "#B45309" } : { color: "#64748B" }}>{deptName(code)}</span>
                      <span className="text-slate-400">{t(typeLabel(etype))}{rate}</span>
                    </div>
                  </div>
                );
              })}
            </Section>
          </div>

          <div className="space-y-4">
            <Section title={t("Rémunération")}>
              <Row label={t("Salaire annuel actuel")} value={fmtCAD(e.current_annual_salary)} accent="#063044" />
              <Row label={t("Taux de vacances")} value={`${(e.vacation_rate * 100).toFixed(2)} %`} />
              <Row label={t("Jours maladie / personnels")} value={e.sick_personal_days} />
              <Row label={t("Jours fériés")} value={e.holiday_days} />
            </Section>
            <Section title={t("Primes & allocations")}>
              <Row label={t("Type de prime")} value={t(e.prime_type || "Aucune Prime")} />
              <Row label={t("Prime de garde")} value={yesNo(e.prime_garde)} />
              <Row label={t("Prime HALO")} value={yesNo(e.prime_halo)} />
              <Row label={t("Alloc. sécurité")} value={yesNo(e.alloc_securite)} />
            </Section>
            <Section title={t("Dates & ancienneté")}>
              <Row label={t("Date d'embauche")} value={fmtDate(e.hire_date)} />
              <Row label={t("Date de naissance")} value={`${fmtDate(e.birth_date)} (${computeAge(e.birth_date)} ${t("ans")})`} />
              {e.end_date && <Row label={t("Date de fin d'emploi")} value={fmtDate(e.end_date)} accent="#B45309" />}
              <Row label={t("Ancienneté")} value={`${computeSeniority(e.hire_date)} ${t("ans")}`} />
            </Section>
          </div>
        </div>

        {(onViewBudget || canEdit) && (
          <div className="flex flex-col gap-2 sm:flex-row">
            {onViewBudget && (
              <Button data-testid="employee-detail-budget-btn" variant="outline" onClick={() => { onOpenChange(false); onViewBudget(e); }} className="flex-1 gap-1.5">
                <TrendingUp size={15} /> {t("Voir le budget")}
              </Button>
            )}
            {canEdit && (
              <Button data-testid="employee-detail-edit-btn" onClick={() => { onOpenChange(false); onEdit(e); }} className="flex-1 gap-1.5 bg-[#063044] hover:bg-[#063044]/90">
                <Pencil size={15} /> {t("Modifier cet employé")}
              </Button>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
