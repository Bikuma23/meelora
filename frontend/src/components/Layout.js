import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { YearProvider, useYear } from "../context/YearContext";
import { useLang } from "../context/LanguageContext";
import {
  LayoutDashboard, Users, DollarSign, Settings, Building2, FileText, ScrollText, LogOut, Briefcase, Plus, CalendarRange, ShieldCheck, Menu, X, UserCog, ChevronUp, ChevronDown, ChevronRight, Minimize2,
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

function NavItem({ item, active, onClick }) {
  const { t } = useLang();
  const Icon = item.icon;
  const on = active === item.key;
  return (
    <button
      data-testid={`nav-${item.key}`}
      onClick={() => onClick(item.key)}
      className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${
        on ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/10 hover:text-white"
      }`}
    >
      {on && <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-[#15AF97]" />}
      <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${on ? "bg-[#15AF97] text-white" : "bg-white/5 text-slate-300 group-hover:bg-white/15 group-hover:text-white"}`}>
        <Icon size={16} strokeWidth={2.2} />
      </span>
      <span className="min-w-0">
        <span className={`block truncate text-sm ${on ? "font-700" : "font-600"}`}>{t(item.label)}</span>
        <span className={`block truncate text-[11px] ${on ? "text-[#15AF97]" : "text-slate-400"}`}>{t(item.sub)}</span>
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
      className={`group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 ${on ? "bg-white/10 font-700 text-white" : "font-600 text-slate-300 hover:bg-white/10 hover:text-white"}`}>
      {on && <span className="absolute left-0 top-1/2 h-4 w-1 -translate-y-1/2 rounded-r-full bg-[#15AF97]" />}
      <Icon size={15} strokeWidth={2.2} className={on ? "text-[#15AF97]" : "text-slate-400 group-hover:text-white"} />
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
      <div className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${on ? "bg-white/10 text-white" : "text-slate-300 hover:bg-white/10 hover:text-white"}`}>
        {on && <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-[#15AF97]" />}
        <button data-testid={`nav-${item.key}`} onClick={() => { onClick(item.key); setOpen(true); }} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${on ? "bg-[#15AF97] text-white" : "bg-white/5 text-slate-300 group-hover:bg-white/15 group-hover:text-white"}`}>
            <Icon size={16} strokeWidth={2.2} />
          </span>
          <span className="min-w-0">
            <span className={`block truncate text-sm ${on ? "font-700" : "font-600"}`}>{t(item.label)}</span>
            <span className={`block truncate text-[11px] ${on ? "text-[#15AF97]" : "text-slate-400"}`}>{t(item.sub)}</span>
          </span>
        </button>
        <button data-testid={`nav-${item.key}-toggle`} onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }} className="rounded-md p-1 text-slate-400 hover:text-white">
          {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
      </div>
      {open && (
        <div className="mt-1 space-y-1 border-l border-white/10 pl-3 ml-5">
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
      <CalendarRange size={15} className="text-[#063044]" />
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
            <Button data-testid="ny-create-btn" className="bg-[#063044] hover:bg-[#063044]/90" onClick={create}>{t("Créer l'année")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Layout() {
  return <YearProvider><LayoutInner /></YearProvider>;
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
  const [avatarColor, setAvatarColor] = useState("#F8A942");
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
  const roleMeta = { admin: { label: "Admin", c: "#063044", t: "#93B4FF" }, editor: { label: "Éditeur", c: "#0E9488", t: "#5EEAD4" }, user: { label: "Utilisateur", c: "#64748B", t: "#94A3B8" } }[user?.role] || { label: "Utilisateur", c: "#64748B", t: "#94A3B8" };
  useEffect(() => { api.getPreferences().then((p) => { applyTheme(p?.theme); if (p?.avatar_color) setAvatarColor(p.avatar_color); }).catch(() => {}); }, []);

  return (
    <div className="flex min-h-screen bg-[#F4F6F8]">
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-overlay" />}
      <aside className={`fixed left-0 top-0 z-40 flex h-screen w-64 flex-col border-r border-white/10 bg-[#063044] px-3 py-4 transition-transform duration-200 ${presentation ? "-translate-x-full" : "lg:translate-x-0"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="mb-6 flex items-center justify-between gap-2.5 px-2">
          <div className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#F8A942]">
              <DollarSign size={20} className="text-white" strokeWidth={2.4} />
            </span>
            <div>
              <h1 className="font-display text-base font-800 leading-none text-white">Budget Salaires</h1>
            </div>
          </div>
          <button className="rounded-lg p-1.5 text-slate-300 hover:bg-white/10 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-close-btn"><X size={20} /></button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto">
          <div className="flex items-center gap-2 px-3 pb-1 pt-1">
            <Briefcase size={13} className="text-[#15AF97]" />
            <span className="overline" style={{ color: "#94A3B8" }}>{t("Masse Salariale")}</span>
          </div>
          {NAV_GROUP.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          <NavParent item={BUDGET_PARENT} children={BUDGET_CHILDREN} active={active} onClick={go} />
          <div className="flex items-center gap-2 px-3 pb-1 pt-4">
            <Calculator size={13} className="text-[#15AF97]" />
            <span className="overline" style={{ color: "#94A3B8" }}>{t("Comptabilité")}</span>
          </div>
          {NAV_ACCT.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          {user?.role === "admin" && (
            <div className="pt-4">
              {NAV_BOTTOM.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
            </div>
          )}
        </nav>

        <div className="mt-3 border-t border-white/10 pt-3">
          {userMenuOpen && (
            <div className="mb-2 space-y-1" data-testid="user-submenu">
              <NavItem item={{ key: "preferences", label: "Mon profil", sub: "Préférences & apparence", icon: UserCog }} active={active} onClick={(k) => { go(k); setUserMenuOpen(false); }} />
              {user?.role === "admin" && <NavItem item={{ key: "utilisateurs", label: "Utilisateurs", sub: "Comptes & accès", icon: ShieldCheck }} active={active} onClick={(k) => { go(k); setUserMenuOpen(false); }} />}
              <button data-testid="logout-btn" onClick={logout}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-600 text-slate-300 transition-colors hover:bg-red-500/15 hover:text-red-300">
                <LogOut size={16} /> {t("Déconnexion")}
              </button>
            </div>
          )}
          <button data-testid="user-menu-toggle" onClick={() => setUserMenuOpen((o) => !o)}
            className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-white/10">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg text-sm font-700 text-white" style={{ backgroundColor: avatarColor }}>
              {(user?.name || "U").charAt(0)}
            </span>
            <div className="min-w-0 flex-1 text-left">
              <div className="flex items-center gap-1.5">
                <p className="truncate text-sm font-600 text-white">{user?.name}</p>
                <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-700 uppercase" style={{ backgroundColor: roleMeta.t + "22", color: roleMeta.t }}>{t(roleMeta.label)}</span>
              </div>
              <p className="truncate text-[11px] text-slate-400">{user?.email}</p>
            </div>
            {userMenuOpen ? <ChevronDown size={16} className="text-slate-300" /> : <ChevronUp size={16} className="text-slate-300" />}
          </button>
        </div>
      </aside>

      <div className={`flex-1 ${presentation ? "" : "lg:ml-64"}`}>
        {!presentation && (
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 py-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2.5">
            <button className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(true)} data-testid="sidebar-open-btn"><Menu size={22} /></button>
            <div className="min-w-0">
              <p className="overline mb-0.5">{active.startsWith("acct_") ? t("Comptabilité") : t("Masse salariale")}</p>
              <h2 className="font-display truncate text-lg font-400 tracking-tight text-[#063044] dark:text-white sm:text-2xl">{t(page.title)}</h2>
              <p className="truncate text-xs text-slate-500">{t(page.sub)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {!active.startsWith("acct_") && <span className="hidden rounded-full bg-[#15AF97]/10 px-3 py-1 text-xs font-600 text-[#15AF97] sm:inline-flex">{t("Budget actif")}</span>}
            {!active.startsWith("acct_") && <YearControls />}
          </div>
        </header>
        )}
        {presentation && (
          <button onClick={exitPresentation} data-testid="presentation-exit-btn" title="Quitter le mode présentation"
            className="fixed right-4 top-4 z-50 inline-flex items-center gap-1.5 rounded-full bg-[#063044] px-3 py-1.5 text-xs font-600 text-white shadow-lg hover:bg-[#063044]/90">
            <Minimize2 size={14} /> Quitter
          </button>
        )}
        <main className={presentation ? "p-3" : "p-4 sm:p-6 lg:p-8"}>
          <Active />
        </main>
      </div>
    </div>
  );
}
