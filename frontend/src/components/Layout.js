import { useState, useEffect } from "react";
import { useAuth } from "../context/AuthContext";
import { YearProvider, useYear } from "../context/YearContext";
import {
  LayoutDashboard, Users, DollarSign, Settings, Building2, FileText, ScrollText, LogOut, Briefcase, Plus, CalendarRange, ShieldCheck, Menu, X, UserCog, ChevronUp, ChevronDown,
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
import { AcctDashboard, AcctBV, AcctBilan, AcctBilanSommaire, AcctPnl, AcctPnlSommaire, AcctCashflow, AcctAudit } from "../pages/Comptabilite";
import { Calculator, Landmark, ClipboardList, Wallet, FileBarChart } from "lucide-react";

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
  acct_dashboard: { title: "Comptabilité — Tableau de bord", sub: "Vue d'ensemble du mois", comp: AcctDashboard },
  acct_bv: { title: "Balance de vérification", sub: "Upload & gestion mensuelle", comp: AcctBV },
  acct_bilan: { title: "Bilan détaillé", sub: "Bilan à la fin du mois", comp: AcctBilan },
  acct_bilan_sommaire: { title: "Bilan sommaire", sub: "Vue synthétique du bilan", comp: AcctBilanSommaire },
  acct_pnl: { title: "État des résultats", sub: "P&L du mois", comp: AcctPnl },
  acct_pnl_sommaire: { title: "Résultat sommaire", sub: "P&L synthétique", comp: AcctPnlSommaire },
  acct_cashflow: { title: "Flux de trésorerie", sub: "Méthode indirecte", comp: AcctCashflow },
  acct_audit: { title: "Rapports d'audit", sub: "À venir", comp: AcctAudit },
};

const NAV_ACCT = [
  { key: "acct_dashboard", label: "Tableau de bord", sub: "Vue d'ensemble", icon: LayoutDashboard },
  { key: "acct_bv", label: "Balance de vérification", sub: "Upload mensuel", icon: ClipboardList },
  { key: "acct_bilan", label: "Bilan détaillé", sub: "État de situation", icon: Landmark },
  { key: "acct_bilan_sommaire", label: "Bilan sommaire", sub: "Synthèse", icon: Landmark },
  { key: "acct_pnl", label: "États des résultats", sub: "P&L détaillé", icon: FileBarChart },
  { key: "acct_pnl_sommaire", label: "Résultat sommaire", sub: "P&L synthèse", icon: FileBarChart },
  { key: "acct_cashflow", label: "Flux de trésorerie", sub: "Méthode indirecte", icon: Wallet },
  { key: "acct_audit", label: "Rapports d'audit", sub: "À venir", icon: FileText },
];

const NAV_TOP = [{ key: "dashboard", label: "Tableau de bord", sub: "Vue globale", icon: LayoutDashboard }];
const NAV_GROUP = [
  { key: "employes", label: "Employés", sub: "Gestion RH", icon: Users },
  { key: "budget", label: "Salaires & Budget", sub: "Saisie & calculs", icon: DollarSign },
  { key: "hypotheses", label: "Hypothèses", sub: "Taux & paramètres", icon: Settings },
  { key: "departements", label: "Départements", sub: "Codes & superviseurs", icon: Building2 },
  { key: "rapports", label: "Rapports", sub: "Prédéfinis & custom", icon: FileText },
];
const NAV_BOTTOM = [
  { key: "journal", label: "Journal", sub: "Historique des modifications", icon: ScrollText },
];

function NavItem({ item, active, onClick }) {
  const Icon = item.icon;
  const on = active === item.key;
  return (
    <button
      data-testid={`nav-${item.key}`}
      onClick={() => onClick(item.key)}
      className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${
        on ? "bg-[#063044]/[0.06] text-[#063044]" : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
      }`}
    >
      {on && <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-[#063044]" />}
      <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${on ? "bg-[#063044] text-white" : "bg-slate-100 text-slate-400 group-hover:bg-slate-200 group-hover:text-slate-600"}`}>
        <Icon size={16} strokeWidth={2.2} />
      </span>
      <span className="min-w-0">
        <span className={`block truncate text-sm ${on ? "font-700" : "font-600"}`}>{item.label}</span>
        <span className={`block truncate text-[11px] ${on ? "text-[#063044]/55" : "text-slate-400"}`}>{item.sub}</span>
      </span>
    </button>
  );
}

function YearControls() {
  const { years, year, selectYear, refresh } = useYear();
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
      <Button variant="outline" size="sm" className="h-8 gap-1.5" data-testid="new-year-btn" onClick={openDialog}><Plus size={14} /> Année</Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="new-year-dialog">
          <DialogHeader>
            <DialogTitle>Nouvelle année budgétaire</DialogTitle>
            <DialogDescription className="text-xs">Le scénario source de l'année de départ devient le « Salaire actuel » de la nouvelle année.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-3 py-1 sm:grid-cols-3">
            <div><label className="text-[11px] uppercase text-slate-500">Nouvelle année</label>
              <Input data-testid="ny-year" type="number" className="mt-1 font-mono-data" value={f.year} onChange={(e) => setF((p) => ({ ...p, year: e.target.value }))} /></div>
            <div><label className="text-[11px] uppercase text-slate-500">Année source</label>
              <Select value={f.source_year} onValueChange={(v) => setF((p) => ({ ...p, source_year: v }))}>
                <SelectTrigger data-testid="ny-source-year" className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
              </Select></div>
            <div><label className="text-[11px] uppercase text-slate-500">Report basé sur</label>
              <Select value={f.source_scenario} onValueChange={(v) => setF((p) => ({ ...p, source_scenario: v }))}>
                <SelectTrigger data-testid="ny-source-scenario" className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="ca">Budget CA</SelectItem><SelectItem value="revue1">Revue Budgétaire 1</SelectItem><SelectItem value="revue2">Revue Budgétaire 2</SelectItem></SelectContent>
              </Select></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>Annuler</Button>
            <Button data-testid="ny-create-btn" className="bg-[#063044] hover:bg-[#063044]/90" onClick={create}>Créer l'année</Button>
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
  const [active, setActive] = useState("dashboard");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [avatarColor, setAvatarColor] = useState("#F8A942");
  const page = PAGES[active];
  const Active = page.comp;
  const go = (k) => { setActive(k); setMobileOpen(false); };
  const roleMeta = { admin: { label: "Admin", c: "#063044", t: "#93B4FF" }, editor: { label: "Éditeur", c: "#0E9488", t: "#5EEAD4" }, user: { label: "Utilisateur", c: "#64748B", t: "#94A3B8" } }[user?.role] || { label: "Utilisateur", c: "#64748B", t: "#94A3B8" };
  useEffect(() => { api.getPreferences().then((p) => { applyTheme(p?.theme); if (p?.avatar_color) setAvatarColor(p.avatar_color); }).catch(() => {}); }, []);

  return (
    <div className="flex min-h-screen bg-[#F4F6F8]">
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-overlay" />}
      <aside className={`fixed left-0 top-0 z-40 flex h-screen w-64 flex-col border-r border-slate-200 bg-white px-3 py-4 transition-transform duration-200 lg:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="mb-6 flex items-center justify-between gap-2.5 px-2">
          <div className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#063044]">
              <DollarSign size={20} className="text-white" strokeWidth={2.4} />
            </span>
            <div>
              <h1 className="font-display text-base font-800 leading-none text-slate-900">Budget Salaires</h1>
              <p className="text-[11px] font-600 uppercase tracking-widest text-[#F8A942]">Pro</p>
            </div>
          </div>
          <button className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-close-btn"><X size={20} /></button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto">
          {NAV_TOP.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          <div className="flex items-center gap-2 px-3 pb-1 pt-4">
            <Briefcase size={13} className="text-slate-400" />
            <span className="text-[11px] font-700 uppercase tracking-widest text-slate-400">Masse Salariale</span>
          </div>
          {NAV_GROUP.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          <div className="flex items-center gap-2 px-3 pb-1 pt-4">
            <Calculator size={13} className="text-slate-400" />
            <span className="text-[11px] font-700 uppercase tracking-widest text-slate-400">Comptabilité</span>
          </div>
          {NAV_ACCT.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          {user?.role === "admin" && (
            <div className="pt-4">
              {NAV_BOTTOM.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
            </div>
          )}
        </nav>

        <div className="mt-3 border-t border-slate-200 pt-3">
          {userMenuOpen && (
            <div className="mb-2 space-y-1" data-testid="user-submenu">
              <NavItem item={{ key: "preferences", label: "Mon profil", sub: "Préférences & apparence", icon: UserCog }} active={active} onClick={(k) => { go(k); setUserMenuOpen(false); }} />
              {user?.role === "admin" && <NavItem item={{ key: "utilisateurs", label: "Utilisateurs", sub: "Comptes & accès", icon: ShieldCheck }} active={active} onClick={(k) => { go(k); setUserMenuOpen(false); }} />}
              <button data-testid="logout-btn" onClick={logout}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-600 text-slate-500 transition-colors hover:bg-red-50 hover:text-red-600">
                <LogOut size={16} /> Déconnexion
              </button>
            </div>
          )}
          <button data-testid="user-menu-toggle" onClick={() => setUserMenuOpen((o) => !o)}
            className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-slate-100">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg text-sm font-700 text-white" style={{ backgroundColor: avatarColor }}>
              {(user?.name || "U").charAt(0)}
            </span>
            <div className="min-w-0 flex-1 text-left">
              <div className="flex items-center gap-1.5">
                <p className="truncate text-sm font-600 text-slate-900">{user?.name}</p>
                <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-700 uppercase" style={{ backgroundColor: roleMeta.c + "1A", color: roleMeta.c }}>{roleMeta.label}</span>
              </div>
              <p className="truncate text-[11px] text-slate-400">{user?.email}</p>
            </div>
            {userMenuOpen ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronUp size={16} className="text-slate-400" />}
          </button>
        </div>
      </aside>

      <div className="flex-1 lg:ml-64">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 py-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2.5">
            <button className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(true)} data-testid="sidebar-open-btn"><Menu size={22} /></button>
            <div className="min-w-0">
              <h2 className="font-display truncate text-lg font-800 tracking-tight text-slate-900 sm:text-xl">{page.title}</h2>
              <p className="truncate text-xs text-slate-500">{page.sub}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {!active.startsWith("acct_") && <span className="hidden rounded-full bg-[#063044]/10 px-3 py-1 text-xs font-600 text-[#063044] sm:inline-flex">Budget actif</span>}
            <YearControls />
          </div>
        </header>
        <main className="p-4 sm:p-6 lg:p-8">
          <Active />
        </main>
      </div>
    </div>
  );
}
