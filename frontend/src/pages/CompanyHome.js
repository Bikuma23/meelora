import { useEffect, useState } from "react";
import { useNav } from "../context/NavContext";
import { useLang } from "../context/LanguageContext";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { CompanyLogo } from "../components/CompanyLogo";
import { MapPin, Phone, Mail, Globe, Loader2, TrendingUp, FileText, Wallet, Receipt } from "lucide-react";

function Kpi({ icon: Icon, label, value, sub, testid }) {
  return (
    <div className="card p-5" data-testid={testid}>
      <div className="mb-2 flex items-center justify-between">
        <span className="text-[11px] font-600 uppercase tracking-wide text-slate-500">{label}</span>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#22C55E]/10 text-[#22C55E]"><Icon size={16} /></span>
      </div>
      <p className="text-2xl font-800 text-[#063044]">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

const money = (v, c) => `${Number(v || 0).toLocaleString("fr-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${c || ""}`.trim();

export default function CompanyHome() {
  const { activeCompanyId } = useNav();
  const { t } = useLang();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeCompanyId) { setLoading(false); return; }
    setLoading(true);
    api.getCompanyHome(activeCompanyId).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [activeCompanyId]);

  if (loading) return <div className="flex items-center gap-2 p-8 text-slate-500" data-testid="company-home-loading"><Loader2 className="animate-spin" size={16} /> {t("Chargement…")}</div>;
  if (!data) return <div className="p-8 text-sm text-slate-400" data-testid="company-home-empty">{t("Sélectionnez un mandat.")}</div>;

  const c = data.company || {};
  const cur = c.currency;
  const kpis = data.kpis;
  const locality = [c.city, c.region].filter(Boolean).join(", ");
  const userName = (user && (user.name || user.email)) || "";

  return (
    <div className="mx-auto max-w-5xl space-y-8" data-testid="company-home">
      {/* Welcome header — the connected user is the primary element; the company/
          mandate is identified below in a clearly smaller size. */}
      <div className="flex flex-col items-center py-10 text-center" data-testid="company-home-header">
        <p className="text-sm font-500 tracking-wide text-slate-400">{t("Bonjour")}</p>
        <h1 className="font-display mt-1 text-4xl font-800 tracking-tight text-[#063044] sm:text-5xl" data-testid="company-home-user">{userName}</h1>
        <div className="mt-5 flex items-center gap-2.5 rounded-full border border-slate-200 bg-white px-4 py-2 shadow-sm" data-testid="company-home-company">
          <CompanyLogo cid={activeCompanyId} hasLogo={c.branding?.has_logo} name={c.name} size={36} />
          <span className="text-base font-700 text-[#0F172A]" data-testid="company-home-name">{c.name}</span>
        </div>
        <p className="mt-2 text-xs font-500 uppercase tracking-wide text-slate-400" data-testid="company-home-entrypoint">{t("Point d'entrée du mandat")}</p>
        <div className="mt-4 flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-xs text-slate-500">
          {(c.address || locality || c.country) && (
            <span className="flex items-center gap-1.5" data-testid="company-home-address">
              <MapPin size={13} className="text-slate-400" />
              {[c.address, locality, c.postal_code, c.country].filter(Boolean).join(" · ")}
            </span>
          )}
          {c.phone && <span className="flex items-center gap-1.5" data-testid="company-home-phone"><Phone size={13} className="text-slate-400" /> {c.phone}</span>}
          {c.email && <span className="flex items-center gap-1.5" data-testid="company-home-email"><Mail size={13} className="text-slate-400" /> {c.email}</span>}
          {c.website && <a href={c.website} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 hover:text-[#22C55E]" data-testid="company-home-website"><Globe size={13} className="text-slate-400" /> {c.website.replace(/^https?:\/\//, "")}</a>}
        </div>
      </div>

      {/* KPIs — only when the user has access to a module that provides them */}
      {kpis ? (
        <div>
          <h2 className="mb-3 text-base font-700 text-[#0F172A]">{t("Aperçu du mandat")}</h2>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4" data-testid="company-home-kpis">
            <Kpi testid="kpi-revenue-month" icon={TrendingUp} label={t("CA du mois")} value={money(kpis.revenue_month, cur)} />
            <Kpi testid="kpi-revenue-ytd" icon={Receipt} label={t("CA de l'exercice")} value={money(kpis.revenue_ytd, cur)} />
            <Kpi testid="kpi-open-invoices" icon={FileText} label={t("Factures clients ouvertes")} value={kpis.open_invoices_count} sub={money(kpis.open_invoices_amount, cur)} />
            <Kpi testid="kpi-collections-month" icon={Wallet} label={t("Encaissements du mois")} value={money(kpis.collections_month, cur)} />
          </div>
        </div>
      ) : (
        <div className="card flex flex-col items-center gap-2 py-10 text-center" data-testid="company-home-no-kpis">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-400"><TrendingUp size={18} /></span>
          <p className="text-sm font-600 text-slate-500">{t("Aucun indicateur disponible pour le moment")}</p>
          <p className="max-w-md text-xs text-slate-400">{t("Les indicateurs apparaîtront ici en fonction des modules acquis et de vos accès.")}</p>
        </div>
      )}

      <p className="pb-4 text-center text-xs text-slate-400" data-testid="company-home-hint">{t("Choisissez un module dans le menu de gauche pour commencer.")}</p>
    </div>
  );
}
