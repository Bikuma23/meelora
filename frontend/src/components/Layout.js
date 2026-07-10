import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import {
  LayoutDashboard, Users, DollarSign, Settings, Building2, FileText, ScrollText, LogOut, Briefcase,
} from "lucide-react";
import Dashboard from "../pages/Dashboard";
import Employes from "../pages/Employes";
import SalairesBudget from "../pages/SalairesBudget";
import Hypotheses from "../pages/Hypotheses";
import Departements from "../pages/Departements";
import Rapports from "../pages/Rapports";
import Journal from "../pages/Journal";

const PAGES = {
  dashboard: { title: "Tableau de bord", sub: "Vue globale", comp: Dashboard },
  employes: { title: "Employés", sub: "Gestion RH", comp: Employes },
  budget: { title: "Salaires & Budget", sub: "Saisie & calculs", comp: SalairesBudget },
  hypotheses: { title: "Hypothèses", sub: "Taux & paramètres", comp: Hypotheses },
  departements: { title: "Départements", sub: "Codes & superviseurs", comp: Departements },
  rapports: { title: "Rapports", sub: "Prédéfinis & custom", comp: Rapports },
  journal: { title: "Journal", sub: "Historique des modifications", comp: Journal },
};

const NAV_TOP = [{ key: "dashboard", label: "Tableau de bord", sub: "Vue globale", icon: LayoutDashboard }];
const NAV_GROUP = [
  { key: "employes", label: "Employés", sub: "Gestion RH", icon: Users },
  { key: "budget", label: "Salaires & Budget", sub: "Saisie & calculs", icon: DollarSign },
  { key: "hypotheses", label: "Hypothèses", sub: "Taux & paramètres", icon: Settings },
  { key: "departements", label: "Départements", sub: "Codes & superviseurs", icon: Building2 },
  { key: "rapports", label: "Rapports", sub: "Prédéfinis & custom", icon: FileText },
];
const NAV_BOTTOM = [{ key: "journal", label: "Journal", sub: "Historique des modifications", icon: ScrollText }];

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

export default function Layout() {
  const { user, logout } = useAuth();
  const [active, setActive] = useState("dashboard");
  const page = PAGES[active];
  const Active = page.comp;

  return (
    <div className="flex min-h-screen bg-[#F1F5F9]">
      <aside className="fixed left-0 top-0 z-30 flex h-screen w-64 flex-col bg-[#0E1526] px-3 py-4">
        <div className="mb-6 flex items-center gap-2.5 px-2">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-[#2563EB] to-[#14B8A6]">
            <DollarSign size={20} className="text-white" strokeWidth={2.4} />
          </span>
          <div>
            <h1 className="text-base font-800 leading-none text-white">Budget Salaires</h1>
            <p className="text-[11px] font-500 uppercase tracking-widest text-[#14B8A6]">Pro</p>
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto">
          {NAV_TOP.map((i) => <NavItem key={i.key} item={i} active={active} onClick={setActive} />)}
          <div className="flex items-center gap-2 px-3 pb-1 pt-4">
            <Briefcase size={14} className="text-slate-500" />
            <span className="text-[11px] font-700 uppercase tracking-widest text-slate-500">Masse Salariale</span>
          </div>
          {NAV_GROUP.map((i) => <NavItem key={i.key} item={i} active={active} onClick={setActive} />)}
          <div className="pt-4">
            {NAV_BOTTOM.map((i) => <NavItem key={i.key} item={i} active={active} onClick={setActive} />)}
          </div>
        </nav>

        <div className="mt-3 border-t border-white/10 pt-3">
          <div className="flex items-center gap-2.5 px-2 py-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#14B8A6] text-sm font-700 text-white">
              {(user?.name || "U").charAt(0)}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-600 text-white">{user?.name}</p>
              <p className="truncate text-[11px] text-slate-500">{user?.email}</p>
            </div>
          </div>
          <button data-testid="logout-btn" onClick={logout}
            className="mt-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-600 text-slate-400 transition-colors hover:bg-white/5 hover:text-red-300">
            <LogOut size={16} /> Déconnexion
          </button>
        </div>
      </aside>

      <div className="ml-64 flex-1">
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-slate-200 bg-[#F1F5F9]/90 px-8 py-4 backdrop-blur">
          <div>
            <h2 className="text-lg font-800 tracking-tight">{page.title}</h2>
            <p className="text-xs text-slate-500">{page.sub}</p>
          </div>
          <span className="rounded-full bg-[#2563EB]/10 px-3 py-1 text-xs font-600 text-[#2563EB]">2026 — Budget actif</span>
        </header>
        <main className="p-8">
          <Active />
        </main>
      </div>
    </div>
  );
}
