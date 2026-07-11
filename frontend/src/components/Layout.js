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
};

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
      className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${
        on ? "bg-white/10 text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
      }`}
    >
      <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${on ? "bg-[#14B8A6] text-white" : "bg-white/5"}`}>
        <Icon size={16} strokeWidth={2.2} />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-600">{item.label}</span>
        <span className="block truncate text-[11px] text-slate-500">{item.sub}</span>
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
      <CalendarRange size={15} className="text-[#2563EB]" />
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
            <Button data-testid="ny-create-btn" className="bg-[#2563EB] hover:bg-[#2563EB]/90" onClick={create}>Créer l'année</Button>
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
  const page = PAGES[active];
  const Active = page.comp;
  const go = (k) => { setActive(k); setMobileOpen(false); };
  useEffect(() => { api.getPreferences().then((p) => applyTheme(p?.theme)).catch(() => {}); }, []);

  return (
    <div className="flex min-h-screen bg-[#F1F5F9]">
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-overlay" />}
      <aside className={`fixed left-0 top-0 z-40 flex h-screen w-64 flex-col bg-[#0E1526] px-3 py-4 transition-transform duration-200 lg:translate-x-0 ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="mb-6 flex items-center justify-between gap-2.5 px-2">
          <div className="flex items-center gap-2.5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#2563EB] to-[#14B8A6]">
              <DollarSign size={20} className="text-white" strokeWidth={2.4} />
            </span>
            <div>
              <h1 className="text-base font-800 leading-none text-white">Budget Salaires</h1>
              <p className="text-[11px] font-500 uppercase tracking-widest text-[#14B8A6]">Pro</p>
            </div>
          </div>
          <button className="rounded-lg p-1.5 text-slate-400 hover:bg-white/5 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-close-btn"><X size={20} /></button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto">
          {NAV_TOP.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          <div className="flex items-center gap-2 px-3 pb-1 pt-4">
            <Briefcase size={14} className="text-slate-500" />
            <span className="text-[11px] font-700 uppercase tracking-widest text-slate-500">Masse Salariale</span>
          </div>
          {NAV_GROUP.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          <div className="pt-4">
            {NAV_BOTTOM.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
          </div>
        </nav>

        <div className="mt-3 border-t border-white/10 pt-3">
          {userMenuOpen && (
            <div className="mb-2 space-y-1" data-testid="user-submenu">
              <NavItem item={{ key: "preferences", label: "Mon profil", sub: "Préférences & apparence", icon: UserCog }} active={active} onClick={(k) => { go(k); setUserMenuOpen(false); }} />
              {user?.role === "admin" && <NavItem item={{ key: "utilisateurs", label: "Utilisateurs", sub: "Comptes & accès", icon: ShieldCheck }} active={active} onClick={(k) => { go(k); setUserMenuOpen(false); }} />}
              <button data-testid="logout-btn" onClick={logout}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-600 text-slate-400 transition-colors hover:bg-white/5 hover:text-red-300">
                <LogOut size={16} /> Déconnexion
              </button>
            </div>
          )}
          <button data-testid="user-menu-toggle" onClick={() => setUserMenuOpen((o) => !o)}
            className="flex w-full items-center gap-2.5 rounded-xl px-2 py-2 transition-colors hover:bg-white/5">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#14B8A6] text-sm font-700 text-white">
              {(user?.name || "U").charAt(0)}
            </span>
            <div className="min-w-0 flex-1 text-left">
              <p className="truncate text-sm font-600 text-white">{user?.name}</p>
              <p className="truncate text-[11px] text-slate-500">{user?.email}</p>
            </div>
            {userMenuOpen ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronUp size={16} className="text-slate-400" />}
          </button>
        </div>
      </aside>

      <div className="flex-1 lg:ml-64">
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-200 bg-[#F1F5F9]/90 px-4 py-4 backdrop-blur sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2.5">
            <button className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-200 lg:hidden" onClick={() => setMobileOpen(true)} data-testid="sidebar-open-btn"><Menu size={22} /></button>
            <div className="min-w-0">
              <h2 className="truncate text-base font-800 tracking-tight sm:text-lg">{page.title}</h2>
              <p className="truncate text-xs text-slate-500">{page.sub}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <span className="hidden rounded-full bg-[#2563EB]/10 px-3 py-1 text-xs font-600 text-[#2563EB] sm:inline-flex">Budget actif</span>
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
