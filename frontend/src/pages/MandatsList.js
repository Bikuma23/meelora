import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { useNav } from "../context/NavContext";
import { Building2, MapPin, ArrowRight, Loader2 } from "lucide-react";

// P1.13E — "Tous les mandats" : the user's accessible mandates/companies.
// Choosing a mandate sets the current context and opens its module workspace.
export default function MandatsList() {
  const { enterMandat, activeCompanyId } = useNav();
  const [companies, setCompanies] = useState(null);
  useEffect(() => {
    api.getCompanyContext().then((d) => setCompanies(d.companies || [])).catch(() => setCompanies([]));
  }, []);

  if (!companies) return <div className="flex items-center gap-2 text-slate-500" data-testid="mandats-loading"><Loader2 className="animate-spin" size={16} /> Chargement…</div>;

  return (
    <div className="space-y-5" data-testid="mandats-list">
      <p className="text-sm text-slate-500">Choisissez un mandat pour accéder à son espace de travail.</p>
      {companies.length === 0 ? (
        <p className="text-sm text-slate-500" data-testid="mandats-empty">Aucun mandat ne vous est accessible.</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {companies.map((c) => (
            <div key={c.id} data-testid={`mandat-card-${c.id}`}
              className={`flex flex-col rounded-2xl border bg-white p-5 transition-colors hover:border-[#15AF97] ${c.id === activeCompanyId ? "border-[#15AF97] ring-1 ring-[#15AF97]/30" : "border-slate-200"}`}>
              <div className="flex items-start gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#063044]/8 text-[#063044]"><Building2 size={20} /></span>
                <div className="min-w-0">
                  <h4 className="truncate font-medium text-[#0F172A]">{c.name}</h4>
                  <p className="mt-0.5 flex items-center gap-1 text-xs text-slate-400"><MapPin size={12} /> {c.jurisdiction || c.legacy_prefix || "—"}</p>
                </div>
              </div>
              <div className="mt-3 flex items-center justify-between">
                <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-[11px] font-medium text-emerald-700">Actif</span>
                <Button size="sm" className="gap-1.5 bg-[#063044] text-white hover:bg-[#0a4a68]"
                  data-testid={`mandat-access-${c.id}`} onClick={() => enterMandat(c.id)}>
                  Accéder <ArrowRight size={14} />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
