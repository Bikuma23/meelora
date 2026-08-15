import { Landmark, Layers, FileBarChart } from "lucide-react";

const META = {
  REPORTING: { icon: FileBarChart, title: "Reporting", desc: "Le module Reporting sera bientôt disponible dans votre espace." },
  FIXED_ASSETS: { icon: Landmark, title: "Immobilisations", desc: "Le module Immobilisations sera bientôt disponible dans votre espace." },
  CONSOLIDATION: { icon: Layers, title: "Consolidation", desc: "Le module Consolidation sera bientôt disponible dans votre espace." },
};

export function ModulePlaceholder({ module }) {
  const m = META[module] || META.REPORTING;
  const Icon = m.icon;
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center text-center" data-testid={`module-placeholder-${module}`}>
      <span className="mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-[#15AF97]/12 text-[#15AF97]">
        <Icon size={30} />
      </span>
      <h3 className="text-xl font-light text-[#063044]">{m.title}</h3>
      <p className="mt-2 max-w-sm text-sm text-slate-500">{m.desc}</p>
      <span className="mt-4 rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-700">Bientôt disponible</span>
    </div>
  );
}

export const ReportingHome = () => <ModulePlaceholder module="REPORTING" />;
export const FixedAssetsHome = () => <ModulePlaceholder module="FIXED_ASSETS" />;
export const ConsolidationHome = () => <ModulePlaceholder module="CONSOLIDATION" />;
