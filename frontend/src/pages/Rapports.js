import { FileText, Clock } from "lucide-react";

export default function Rapports() {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 p-16 text-center" data-testid="rapports-page">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-[#2563EB]/10 text-[#2563EB]"><FileText size={26} /></span>
      <h3 className="text-lg font-700">Rapports — prédéfinis & personnalisés</h3>
      <p className="max-w-md text-sm text-slate-500">
        Générez et exportez des rapports budgétaires (par département, par type d'emploi, ventilation mensuelle) en PDF et Excel.
      </p>
      <span className="mt-1 flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 text-xs font-600 text-amber-700"><Clock size={13} /> Bientôt disponible (Phase 2)</span>
    </div>
  );
}
