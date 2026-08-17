import { useEffect, useState } from "react";
import { useNav } from "../context/NavContext";
import { useLang } from "../context/LanguageContext";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { CompanyLogo } from "../components/CompanyLogo";
import {
  MapPin, Phone, Mail, Globe, Loader2, TrendingUp, ArrowUpRight, ArrowDownRight,
  FilePlus, Wallet, Users, BarChart3, CheckCircle2, Info, Lightbulb, AlertTriangle,
} from "lucide-react";

const QA_ICONS = { "file-plus": FilePlus, wallet: Wallet, users: Users, "bar-chart": BarChart3 };
const nf = (v, min = 2) => Number(v || 0).toLocaleString("fr-CA", { minimumFractionDigits: min, maximumFractionDigits: min });

function fmtValue(k) {
  if (k.format === "currency") return nf(k.value);
  if (k.format === "percent") return `${nf(k.value, 1)}\u00A0%`;
  return Number(k.value || 0).toLocaleString("fr-CA");
}

function Sparkline({ points }) {
  if (!points || points.length < 2 || points.every((p) => p === 0)) return null;
  const w = 120, h = 34, max = Math.max(...points), min = Math.min(...points);
  const span = max - min || 1;
  const d = points.map((p, i) => `${(i / (points.length - 1)) * w},${h - ((p - min) / span) * (h - 4) - 2}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-3 h-8 w-full" preserveAspectRatio="none" data-testid="kpi-sparkline">
      <polyline points={d} fill="none" stroke="#2563EB" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function KpiCard({ k, onClick }) {
  const cmp = k.comparison;
  const up = cmp && cmp.delta_pct >= 0;
  return (
    <button type="button" onClick={onClick} data-testid={`kpi-${k.code}`}
      className="card flex flex-col p-5 text-left transition-shadow hover:shadow-md">
      <span className="text-xs font-600 text-slate-500">{k.label}</span>
      <p className="mt-1.5 text-2xl font-800 leading-tight text-[#063044]">
        {fmtValue(k)}{k.format === "currency" && k.unit ? <span className="ml-1 text-sm font-600 text-slate-400">{k.unit}</span> : null}
      </p>
      {k.subvalue && <p className="mt-0.5 text-xs text-slate-400">{nf(k.subvalue.value)} {k.subvalue.unit}</p>}
      {cmp && cmp.delta_pct != null && (
        <p className={`mt-1 flex items-center gap-1 text-xs font-600 ${up ? "text-emerald-600" : "text-rose-600"}`}>
          {up ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{Math.abs(cmp.delta_pct)}% <span className="font-400 text-slate-400">{cmp.label}</span>
        </p>
      )}
      <Sparkline points={k.trend} />
    </button>
  );
}

const money = (v, c) => `${nf(v)} ${c || ""}`.trim();

export default function CompanyHome() {
  const { activeCompanyId, go } = useNav();
  const { t } = useLang();
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!activeCompanyId) { setLoading(false); return; }
    setLoading(true);
    api.getCompanyHome(activeCompanyId).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [activeCompanyId]);

  const openActivity = (r) => {
    if (r.ref_type && r.ref_id) {
      const tabMap = { invoice: "invoices", payment: "payments", credit_note: "credit_notes" };
      try { sessionStorage.setItem("ar_focus", JSON.stringify({ tab: tabMap[r.ref_type] || "overview", id: r.ref_id })); } catch (e) { /* ignore */ }
    }
    if (r.destination) go(r.destination);
  };

  if (loading) return <div className="flex items-center gap-2 p-8 text-slate-500" data-testid="company-home-loading"><Loader2 className="animate-spin" size={16} /> {t("Chargement…")}</div>;
  if (!data) return <div className="p-8 text-sm text-slate-400" data-testid="company-home-empty">{t("Sélectionnez un mandat.")}</div>;

  const c = data.company || {};
  const locality = [c.city, c.region].filter(Boolean).join(", ");
  const userName = (user && (user.name || user.email)) || "";
  const kpis = data.home_kpis || [];
  const quickActions = data.quick_actions || [];
  const recent = data.recent_activity || [];
  const info = data.informational_items || [];
  const gridCols = kpis.length >= 5 ? "lg:grid-cols-5" : kpis.length === 4 ? "lg:grid-cols-4" : kpis.length === 3 ? "lg:grid-cols-3" : kpis.length === 2 ? "sm:grid-cols-2" : "sm:grid-cols-1";

  return (
    <div data-testid="company-home">
      <div className="mx-auto max-w-6xl space-y-8">
      {/* Welcome header — logo aligned to the greeting line, slightly larger than the user name. */}
      <div className="flex flex-col items-start gap-5 py-6 sm:flex-row sm:gap-7" data-testid="company-home-header">
        <div className="flex shrink-0 items-start pt-1" data-testid="company-home-logo">
          <CompanyLogo cid={activeCompanyId} hasLogo={c.branding?.has_logo} name={c.name} size={52} bare />
        </div>
        <div className="min-w-0">
          <p className="text-sm font-500 tracking-wide text-slate-400">{t("Bonjour")}</p>
          <h1 className="font-display mt-0.5 text-3xl font-800 leading-tight tracking-tight text-[#063044] sm:text-4xl" data-testid="company-home-user">{userName}</h1>
          <div className="mt-2 flex items-center gap-2" data-testid="company-home-company">
            <span className="text-lg font-700 text-[#0F172A] sm:text-xl" data-testid="company-home-name">{c.name}</span>
            {c.status === "active"
              ? <CheckCircle2 size={18} className="shrink-0 fill-emerald-500 text-white" data-testid="company-home-status-active" />
              : <span className="h-2.5 w-2.5 shrink-0 rounded-full bg-slate-300" data-testid="company-home-status-neutral" />}
          </div>
          <div className="mt-4 flex flex-col gap-y-2 text-sm text-slate-500">
            {(c.address || locality || c.country) && (
              <span className="flex items-center gap-2" data-testid="company-home-address">
                <MapPin size={14} className="shrink-0 text-slate-400" />
                {[c.address, locality, c.postal_code, c.country].filter(Boolean).join(", ")}
              </span>
            )}
            <div className="flex flex-wrap items-center gap-x-8 gap-y-2">
              {c.phone && <span className="flex items-center gap-2" data-testid="company-home-phone"><Phone size={14} className="shrink-0 text-slate-400" /> {c.phone}</span>}
              {c.email && <span className="flex items-center gap-2" data-testid="company-home-email"><Mail size={14} className="shrink-0 text-slate-400" /> {c.email}</span>}
              {c.website && <a href={c.website} target="_blank" rel="noreferrer" className="flex items-center gap-2 hover:text-[#22C55E]" data-testid="company-home-website"><Globe size={14} className="shrink-0 text-slate-400" /> {c.website.replace(/^https?:\/\//, "")}</a>}
            </div>
          </div>
        </div>
      </div>

      {/* KPIs — dynamic, module- & permission-aware, capped at ~5, reflowing grid. */}
      {kpis.length > 0 ? (
        <div>
          <div className="mb-2 flex items-center justify-end">
            <span className="flex items-center gap-1 text-[11px] text-slate-400" data-testid="company-home-kpi-hint"><Info size={12} /> {t("KPI affichés selon vos modules et permissions")}</span>
          </div>
          <div className={`grid grid-cols-1 gap-4 sm:grid-cols-2 ${gridCols}`} data-testid="company-home-kpis">
            {kpis.map((k) => <KpiCard key={k.code} k={k} onClick={() => k.destination && go(k.destination)} />)}
          </div>
        </div>
      ) : (
        <div className="card flex flex-col items-center gap-2 py-10 text-center" data-testid="company-home-no-kpis">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-400"><TrendingUp size={18} /></span>
          <p className="text-sm font-600 text-slate-500">{t("Aucun indicateur disponible pour le moment")}</p>
          <p className="max-w-md text-xs text-slate-400">{t("Les indicateurs apparaîtront ici en fonction des modules acquis et de vos accès.")}</p>
        </div>
      )}

      {/* Quick actions + Recent activity | Informational items */}
      {(quickActions.length > 0 || recent.length > 0 || info.length > 0) && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="card p-5" data-testid="company-home-left">
            {quickActions.length > 0 && (
              <div data-testid="company-home-quick-actions">
                <h3 className="mb-3 text-sm font-700 text-[#0F172A]">{t("Accès rapides")}</h3>
                <div className="grid grid-cols-4 gap-2">
                  {quickActions.map((q) => {
                    const Icon = QA_ICONS[q.icon] || BarChart3;
                    return (
                      <button key={q.code} type="button" onClick={() => q.destination && go(q.destination)} data-testid={`quick-action-${q.code}`}
                        className="flex flex-col items-center gap-1.5 rounded-xl border border-transparent p-3 text-center transition-colors hover:border-slate-200 hover:bg-slate-50">
                        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-[#063044]"><Icon size={18} /></span>
                        <span className="text-[11px] font-600 text-slate-600">{t(q.label)}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {recent.length > 0 && (
              <div className={quickActions.length > 0 ? "mt-5" : ""} data-testid="company-home-recent">
                <h3 className="mb-2 text-sm font-700 text-[#0F172A]">{t("Activités récentes")}</h3>
                <ul className="divide-y divide-slate-100">
                  {recent.map((r, i) => {
                    const clickable = !!(r.destination || r.ref_id);
                    return (
                      <li key={i} data-testid={`recent-${i}`}>
                        <button type="button" onClick={() => clickable && openActivity(r)} disabled={!clickable}
                          data-testid={`recent-btn-${i}`}
                          className={`-mx-2 flex w-[calc(100%+1rem)] items-center justify-between gap-3 rounded-lg px-2 py-2.5 text-left text-sm transition-colors ${clickable ? "cursor-pointer hover:bg-slate-50" : "cursor-default"}`}>
                          <span className="min-w-0 flex-1 truncate text-slate-600">{r.label}</span>
                          <span className="shrink-0 text-xs text-slate-400">{r.date}</span>
                          <span className={`shrink-0 text-sm font-600 ${r.tone === "positive" ? "text-emerald-600" : r.tone === "negative" ? "text-rose-600" : "text-[#0F172A]"}`}>
                            {r.amount != null ? `${r.amount < 0 ? "-" : ""}${nf(Math.abs(r.amount))} ${r.currency || ""}`.trim() : ""}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
            )}
          </div>

          <div className="card p-5" data-testid="company-home-info">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-700 text-[#0F172A]"><Lightbulb size={16} className="text-[#22C55E]" /> {t("À savoir")}</h3>
            {info.length > 0 ? (
              <ul className="space-y-2.5">
                {info.map((it, i) => {
                  const warn = it.tone === "warning";
                  const IconC = warn ? AlertTriangle : CheckCircle2;
                  return (
                    <li key={it.code || i} className={`flex items-start gap-2 text-sm ${warn ? "text-[#B45309]" : "text-slate-600"}`} data-testid={`info-${i}`}>
                      <IconC size={16} className={`mt-0.5 shrink-0 ${warn ? "text-amber-500" : "text-emerald-500"}`} /> <span>{it.text}</span>
                    </li>
                  );
                })}
              </ul>
            ) : <p className="text-xs text-slate-400">{t("Aucune information pour le moment.")}</p>}
          </div>
        </div>
      )}
      </div>
    </div>
  );
}

