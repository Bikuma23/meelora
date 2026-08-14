import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { YearProvider, useYear } from "../context/YearContext";
import { useLang } from "../context/LanguageContext";
import {
  LayoutDashboard, Users, DollarSign, Settings, Building2, FileText, ScrollText, LogOut, Briefcase, Plus, CalendarRange, ShieldCheck, Menu, X, UserCog, ChevronUp, ChevronDown, ChevronRight, Minimize2, HelpCircle, Bell,
} from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { toast } from "sonner";
import { api } from "../lib/api";
import Dashboard from "../pages/Dashboard";
import Employes from "../pages/Employes";
import SalairesBudget from "../pages/SalairesBudget";
import Hypotheses from "../pages/Hypotheses";
import Departements from "../pages/Departements";
import Rapports from "../pages/Rapports";
import Journal from "../pages/Journal";
import UsersPage from "../pages/Users";
import Preferences from "../pages/Preferences";
import { applyTheme } from "../lib/theme";
import { AcctDashboard, AcctBV, AcctBilan, AcctPnl, AcctCashflow, AcctReports } from "../pages/Comptabilite";
import QcEntity from "../pages/QcEntity";
import { Calculator, Landmark, ClipboardList, Wallet, FileBarChart, Building } from "lucide-react";

const PAGES = {
  dashboard: { title: "Tableau de bord", sub: "Vue globale", comp: Dashboard },
  employes: { title: "Employés", sub: "Gestion RH", comp: Employes },
  budget: { title: "Salaires & Budget", sub: "Saisie & calculs", comp: SalairesBudget },
  hypotheses: { title: "Hypothèses", sub: "Taux & paramètres", comp: Hypotheses },
  departements: { title: "Départements", sub: "Codes & superviseurs", comp: Departements },
  rapports: { title: "Rapports", sub: "Prédéfinis & custom", comp: Rapports },
  utilisateurs: { title: "Utilisateurs", sub: "Comptes & accès", comp: UsersPage },
  journal: { title: "Journal", sub: "Historique des modifications", comp: Journal },
  preferences: { title: "Mon profil", sub: "Préférences & apparence", comp: Preferences },
  acct_dashboard: { title: "Tableau de bord", sub: "Vue d'ensemble du mois", comp: AcctDashboard },
  acct_bv: { title: "Balance de vérification", sub: "Upload & gestion mensuelle", comp: AcctBV },
  acct_bilan: { title: "Bilan", sub: "État de situation financière", comp: AcctBilan },
  acct_pnl: { title: "État des résultats", sub: "P&L du mois", comp: AcctPnl },
  acct_cashflow: { title: "Flux de trésorerie", sub: "Méthode indirecte", comp: AcctCashflow },
  acct_audit: { title: "Rapports", sub: "Génération centralisée", comp: AcctReports },
  acct_qc9434: { title: "9434-3977 QC inc.", sub: "Commandité", comp: QcEntity },
};

const NAV_ACCT = [
  { key: "acct_dashboard", label: "Tableau de bord", sub: "Vue d'ensemble", icon: LayoutDashboard },
  { key: "acct_bv", label: "Balance de vérification", sub: "Upload mensuel", icon: ClipboardList },
  { key: "acct_audit", label: "Rapports", sub: "Génération centralisée", icon: FileText },
  { key: "acct_qc9434", label: "9434-3977 QC inc.", sub: "Commandité", icon: Building },
];

const NAV_GROUP = [
  { key: "dashboard", label: "Tableau de bord", sub: "Vue globale", icon: LayoutDashboard },
];
const BUDGET_PARENT = { key: "budget", label: "Salaires & Budget", sub: "Saisie & calculs", icon: DollarSign };
const BUDGET_CHILDREN = [
  { key: "employes", label: "Employés", icon: Users },
  { key: "hypotheses", label: "Hypothèses", icon: Settings },
  { key: "departements", label: "Départements", icon: Building2 },
  { key: "rapports", label: "Rapports", icon: FileText },
];
const NAV_BOTTOM = [
  { key: "journal", label: "Journal", sub: "Historique des modifications", icon: ScrollText },
];

export function MeeloraLogo({ compact = false }) {
  return (
    <span className="flex items-center gap-2" data-testid="brand-logo">
      <svg width="34" height="34" viewBox="0 0 48 48" fill="none" aria-label="Meelora">
        <path d="M8 40V15c0-3.2 3.8-4.9 6.1-2.7L24 21l9.9-8.7C36.2 10.1 40 11.8 40 15v25" stroke="#22C55E" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="33.5" cy="33.5" r="5.5" fill="#FBBF24" />
      </svg>
      {!compact && <span className="font-display text-2xl font-900 lowercase tracking-tight text-[#0F172A]">meelora</span>}
    </span>
  );
}

function NavItem({ item, active, onClick }) {
  const { t } = useLang();
  const Icon = item.icon;
  const on = active === item.key;
  return (
    <button
      data-testid={`nav-${item.key}`}
      onClick={() => onClick(item.key)}
      className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${
        on ? "bg-[#A7F3DD]/40 text-[#0F172A]" : "text-slate-600 hover:bg-[#F3F4F6] hover:text-[#0F172A]"
      }`}
    >
      {on && <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-[#22C55E]" />}
      <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${on ? "bg-[#22C55E] text-white" : "bg-[#F3F4F6] text-slate-500 group-hover:bg-[#A7F3DD]/50 group-hover:text-[#22C55E]"}`}>
        <Icon size={16} strokeWidth={2.2} />
      </span>
      <span className="min-w-0">
        <span className={`block truncate text-sm ${on ? "font-700" : "font-600"}`}>{t(item.label)}</span>
        <span className={`block truncate text-[11px] ${on ? "text-[#22C55E]" : "text-slate-400"}`}>{t(item.sub)}</span>
      </span>
    </button>
  );
}

function NavSubItem({ item, active, onClick }) {
  const { t } = useLang();
  const Icon = item.icon;
  const on = active === item.key;
  return (
    <button data-testid={`nav-${item.key}`} onClick={() => onClick(item.key)}
      className={`group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 ${on ? "bg-[#A7F3DD]/40 font-700 text-[#0F172A]" : "font-600 text-slate-600 hover:bg-[#F3F4F6] hover:text-[#0F172A]"}`}>
      {on && <span className="absolute left-0 top-1/2 h-4 w-1 -translate-y-1/2 rounded-r-full bg-[#22C55E]" />}
      <Icon size={15} strokeWidth={2.2} className={on ? "text-[#22C55E]" : "text-slate-400 group-hover:text-[#22C55E]"} />
      <span className="truncate">{t(item.label)}</span>
    </button>
  );
}

function NavParent({ item, children, active, onClick }) {
  const { t } = useLang();
  const Icon = item.icon;
  const childActive = children.some((c) => c.key === active);
  const on = active === item.key;
  const [open, setOpen] = useState(childActive || on);
  useEffect(() => { if (childActive || on) setOpen(true); }, [childActive, on]);
  return (
    <div>
      <div className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${on ? "bg-[#A7F3DD]/40 text-[#0F172A]" : "text-slate-600 hover:bg-[#F3F4F6] hover:text-[#0F172A]"}`}>
        {on && <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-[#22C55E]" />}
        <button data-testid={`nav-${item.key}`} onClick={() => { onClick(item.key); setOpen(true); }} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${on ? "bg-[#22C55E] text-white" : "bg-[#F3F4F6] text-slate-500 group-hover:bg-[#A7F3DD]/50 group-hover:text-[#22C55E]"}`}>
            <Icon size={16} strokeWidth={2.2} />
          </span>
          <span className="min-w-0">
            <span className={`block truncate text-sm ${on ? "font-700" : "font-600"}`}>{t(item.label)}</span>
            <span className={`block truncate text-[11px] ${on ? "text-[#22C55E]" : "text-slate-400"}`}>{t(item.sub)}</span>
          </span>
        </button>
        <button data-testid={`nav-${item.key}-toggle`} onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }} className="rounded-md p-1 text-slate-400 hover:text-[#0F172A]">
          {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
      </div>
      {open && (
        <div className="mt-1 space-y-1 border-l border-[#F3F4F6] pl-3 ml-5">
          {children.map((c) => <NavSubItem key={c.key} item={c} active={active} onClick={onClick} />)}
        </div>
      )}
    </div>
  );
}

function YearControls() {
  const { years, year, selectYear, refresh } = useYear();
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ year: "", source_year: "", source_scenario: "ca" });
  const openDialog = () => {
    const next = Math.max(...years) + 1;
    setF({ year: String(next), source_year: String(year), source_scenario: "ca" });
    setOpen(true);
  };
  const create = async () => {
    try {
      await api.createYear({ year: Number(f.year), source_year: Number(f.source_year), source_scenario: f.source_scenario });
      toast.success(`Année ${f.year} créée (report ${f.source_scenario === "ca" ? "Budget CA" : "Revue"} ${f.source_year})`);
      await refresh(); await selectYear(Number(f.year)); setOpen(false);
    } catch (e) { toast.error(e.response?.data?.detail || "Création impossible"); }
  };
  return (
    <div className="flex items-center gap-2">
      <CalendarRange size={15} className="text-[#0F172A]" />
      <Select value={String(year)} onValueChange={(v) => selectYear(v)}>
        <SelectTrigger className="h-8 w-24" data-testid="header-year-select"><SelectValue /></SelectTrigger>
        <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
      </Select>
      <Button variant="outline" size="sm" className="h-8 gap-1.5" data-testid="new-year-btn" onClick={openDialog}><Plus size={14} /> {t("Année")}</Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="new-year-dialog">
          <DialogHeader>
            <DialogTitle>{t("Nouvelle année budgétaire")}</DialogTitle>
            <DialogDescription className="text-xs">{t("Le scénario source de l'année de départ devient le « Salaire actuel » de la nouvelle année.")}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-3 py-1 sm:grid-cols-3">
            <div><label className="text-[11px] uppercase text-slate-500">{t("Nouvelle année")}</label>
              <Input data-testid="ny-year" type="number" className="mt-1 font-mono-data" value={f.year} onChange={(e) => setF((p) => ({ ...p, year: e.target.value }))} /></div>
            <div><label className="text-[11px] uppercase text-slate-500">{t("Année source")}</label>
              <Select value={f.source_year} onValueChange={(v) => setF((p) => ({ ...p, source_year: v }))}>
                <SelectTrigger data-testid="ny-source-year" className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
              </Select></div>
            <div><label className="text-[11px] uppercase text-slate-500">{t("Report basé sur")}</label>
              <Select value={f.source_scenario} onValueChange={(v) => setF((p) => ({ ...p, source_scenario: v }))}>
                <SelectTrigger data-testid="ny-source-scenario" className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="ca">{t("Budget CA")}</SelectItem><SelectItem value="revue1">{t("Revue Budgétaire 1")}</SelectItem><SelectItem value="revue2">{t("Revue Budgétaire 2")}</SelectItem></SelectContent>
              </Select></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{t("Annuler")}</Button>
            <Button data-testid="ny-create-btn" className="bg-[#0F172A] hover:bg-[#0F172A]/90" onClick={create}>{t("Créer l'année")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Layout() {
  return <YearProvider><LayoutInner /></YearProvider>;
}

function CompanySelector({ active, onNavigate }) {
  const [companies, setCompanies] = useState([]);
  useEffect(() => { api.getCompanies().then(setCompanies).catch(() => setCompanies([])); }, []);
  if (!companies.length) return null;
  // Mandat actif déduit de la page : la page dédiée 9434 → qc9434 ; toutes les autres pages Compta → acct (Meelora).
  const activePrefix = active === "acct_qc9434" ? "qc9434" : "acct";
  const TARGET = { acct: "acct_dashboard", qc9434: "acct_qc9434" };
  return (
    <div className="flex items-center gap-2" data-testid="company-selector">
      <Building2 size={15} className="text-[#0F172A]" />
      <Select value={activePrefix} onValueChange={(v) => onNavigate(TARGET[v] || "acct_dashboard")}>
        <SelectTrigger className="h-8 w-[190px]" data-testid="company-select"><SelectValue /></SelectTrigger>
        <SelectContent>
          {companies.map((c) => (
            <SelectItem key={c.legacy_prefix} value={c.legacy_prefix} data-testid={`company-option-${c.legacy_prefix}`}>{c.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function LayoutInner() {
  const { user, logout } = useAuth();
  const { t } = useLang();
  const [active, setActive] = useState(() => {
    try { const s = localStorage.getItem("acct:lastPage"); if (s && PAGES[s]) return s; } catch (e) { /* ignore */ }
    return "dashboard";
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [avatarColor, setAvatarColor] = useState("#FBBF24");
  const [presentation, setPresentation] = useState(false);
  const page = PAGES[active];
  const Active = page.comp;
  const go = (k) => { setActive(k); setMobileOpen(false); };
  useEffect(() => { try { localStorage.setItem("acct:lastPage", active); } catch (e) { /* ignore */ } }, [active]);
  useEffect(() => {
    const handler = (e) => { if (e.detail) { setActive(e.detail); setMobileOpen(false); } };
    window.addEventListener("acct-navigate", handler);
    return () => window.removeEventListener("acct-navigate", handler);
  }, []);
  useEffect(() => {
    const ph = (e) => setPresentation(!!e.detail);
    const fh = () => { if (!document.fullscreenElement) setPresentation(false); };
    window.addEventListener("acct-presentation", ph);
    document.addEventListener("fullscreenchange", fh);
    return () => { window.removeEventListener("acct-presentation", ph); document.removeEventListener("fullscreenchange", fh); };
  }, []);
  const exitPresentation = () => { try { document.exitFullscreen?.(); } catch (e) { /* ignore */ } setPresentation(false); };
  const roleMeta = { admin: { label: "Admin", c: "#0F172A", t: "#93B4FF" }, editor: { label: "Éditeur", c: "#22C55E", t: "#5EEAD4" }, user: { label: "Utilisateur", c: "#64748B", t: "#94A3B8" } }[user?.role] || { label: "Utilisateur", c: "#64748B", t: "#94A3B8" };
  useEffect(() => { api.getPreferences().then((p) => { applyTheme(p?.theme); if (p?.avatar_color) setAvatarColor(p.avatar_color); }).catch(() => {}); }, []);

  return (
    <div className="flex min-h-screen bg-[#F3F4F6]">
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-overlay" />}
      <aside className={`fixed left-0 top-0 z-40 flex h-screen w-64 flex-col border-r border-[#F3F4F6] bg-white px-3 py-4 transition-transform duration-200 ${presentation ? "-translate-x-full" : "lg:translate-x-0"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="mb-6 flex items-center justify-between gap-2.5 px-2">
          <MeeloraLogo />
          <button className="rounded-lg p-1.5 text-slate-500 hover:bg-[#F3F4F6] lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-close-btn"><X size={20} /></button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto">
          <div className="flex items-center gap-2 px-3 pb-1 pt-1">
            <Briefcase size={13} className="text-[#22C55E]" />
            <span className="overline" style={{ color: "#94A3B8" }}>{t("Masse Salariale")}</span>
          </div>
          {NAV_GROUP.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          <NavParent item={BUDGET_PARENT} children={BUDGET_CHILDREN} active={active} onClick={go} />
          <div className="flex items-center gap-2 px-3 pb-1 pt-4">
            <Calculator size={13} className="text-[#22C55E]" />
            <span className="overline" style={{ color: "#94A3B8" }}>{t("Comptabilité")}</span>
          </div>
          {NAV_ACCT.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          {user?.role === "admin" && (
            <div className="pt-4">
              {NAV_BOTTOM.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
            </div>
          )}
        </nav>

        <div className="mt-3 border-t border-[#F3F4F6] pt-3">
          <div className="mb-3 flex items-center gap-2.5 rounded-xl bg-[#A7F3DD]/25 px-3 py-2.5" data-testid="sidebar-tagline">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#22C55E]/15 text-[#22C55E]"><Briefcase size={15} strokeWidth={2.2} /></span>
            <p className="text-xs font-600 leading-tight text-[#0F172A]">Votre entreprise,<br /><span className="text-[#22C55E]">clairement.</span></p>
          </div>
          {userMenuOpen && (
            <div className="mb-2 space-y-1" data-testid="user-submenu">
              <NavItem item={{ key: "preferences", label: "Mon profil", sub: "Préférences & apparence", icon: UserCog }} active={active} onClick={(k) => { go(k); setUserMenuOpen(false); }} />
              {user?.role === "admin" && <NavItem item={{ key: "utilisateurs", label: "Utilisateurs", sub: "Comptes & accès", icon: ShieldCheck }} active={active} onClick={(k) => { go(k); setUserMenuOpen(false); }} />}
              <button data-testid="logout-btn" onClick={logout}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-600 text-slate-600 transition-colors hover:bg-red-500/10 hover:text-red-600">
                <LogOut size={16} /> {t("Déconnexion")}
              </button>
            </div>
          )}
          <button data-testid="user-menu-toggle" onClick={() => setUserMenuOpen((o) => !o)}
            className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-[#F3F4F6]">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg text-sm font-700 text-white" style={{ backgroundColor: avatarColor }}>
              {(user?.name || "U").charAt(0)}
            </span>
            <div className="min-w-0 flex-1 text-left">
              <div className="flex items-center gap-1.5">
                <p className="truncate text-sm font-600 text-[#0F172A]">{user?.name}</p>
                <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-700 uppercase" style={{ backgroundColor: roleMeta.c + "1A", color: roleMeta.c }}>{t(roleMeta.label)}</span>
              </div>
              <p className="truncate text-[11px] text-slate-400">{user?.email}</p>
            </div>
            {userMenuOpen ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronUp size={16} className="text-slate-400" />}
          </button>
        </div>
      </aside>

      <div className={`flex-1 ${presentation ? "" : "lg:ml-64"}`}>
        {!presentation && (
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 py-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2.5">
            <button className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(true)} data-testid="sidebar-open-btn"><Menu size={22} /></button>
            <div className="min-w-0">
              <p className="overline mb-0.5" data-testid="breadcrumb">{active.startsWith("acct_") ? t("Comptabilité") : t("Masse salariale")} <span className="mx-1 text-slate-300">›</span> {t(page.title)}</p>
              <h2 className="font-display truncate text-lg font-800 tracking-tight text-[#0F172A] dark:text-white sm:text-2xl">{t(page.title)}</h2>
              <p className="truncate text-xs text-slate-500">{t(page.sub)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {active.startsWith("acct_") && <CompanySelector active={active} onNavigate={go} />}
            {!active.startsWith("acct_") && <span className="hidden rounded-full bg-[#22C55E]/10 px-3 py-1 text-xs font-600 text-[#22C55E] sm:inline-flex">{t("Budget actif")}</span>}
            {!active.startsWith("acct_") && <YearControls />}
            <div className="ml-1 hidden items-center gap-1 border-l border-slate-200 pl-2 sm:flex">
              <button data-testid="header-help-btn" title={t("Aide")} className="rounded-full p-2 text-slate-500 transition-colors hover:bg-[#F3F4F6] hover:text-[#0F172A]"><HelpCircle size={18} /></button>
              <button data-testid="header-notif-btn" title="Notifications" className="relative rounded-full p-2 text-slate-500 transition-colors hover:bg-[#F3F4F6] hover:text-[#0F172A]"><Bell size={18} /><span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[#22C55E]" /></button>
              <button data-testid="header-settings-btn" title={t("Mon profil")} onClick={() => go("preferences")} className="rounded-full p-2 text-slate-500 transition-colors hover:bg-[#F3F4F6] hover:text-[#0F172A]"><Settings size={18} /></button>
            </div>
          </div>
        </header>
        )}
        {presentation && (
          <button onClick={exitPresentation} data-testid="presentation-exit-btn" title="Quitter le mode présentation"
            className="fixed right-4 top-4 z-50 inline-flex items-center gap-1.5 rounded-full bg-[#0F172A] px-3 py-1.5 text-xs font-600 text-white shadow-lg hover:bg-[#0F172A]/90">
            <Minimize2 size={14} /> Quitter
          </button>
        )}
        <main className={presentation ? "p-3" : "p-4 sm:p-6 lg:p-8"}>
          <Active />
        </main>
        {!presentation && (
          <footer className="mt-4 flex flex-col items-center justify-between gap-2 border-t border-[#F3F4F6] px-4 py-5 sm:flex-row sm:px-6 lg:px-8" data-testid="app-footer">
            <div className="flex items-center gap-2">
              <MeeloraLogo compact />
              <span className="text-xs text-slate-400">© 2026 Meelora inc. Tous droits réservés.</span>
            </div>
            <div className="flex items-center gap-4 text-xs text-slate-400">
              <button className="hover:text-[#22C55E]" data-testid="footer-privacy">Confidentialité</button>
              <button className="hover:text-[#22C55E]" data-testid="footer-terms">Conditions d'utilisation</button>
              <button className="hover:text-[#22C55E]" data-testid="footer-help" onClick={() => go("preferences")}>Aide</button>
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}
