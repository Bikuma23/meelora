import { useState } from "react";
import "./App.css";
import { Toaster } from "sonner";
import { Users, SlidersHorizontal, Calculator, LayoutDashboard, HardHat } from "lucide-react";
import EmployeesPage from "./components/EmployeesPage";
import HypothesesPage from "./components/HypothesesPage";
import BudgetPage from "./components/BudgetPage";
import DashboardPage from "./components/DashboardPage";

const TABS = [
  { key: "dashboard", label: "Tableau de bord", icon: LayoutDashboard, comp: DashboardPage },
  { key: "employees", label: "Employés", icon: Users, comp: EmployeesPage },
  { key: "budget", label: "Budget Salaires", icon: Calculator, comp: BudgetPage },
  { key: "hypotheses", label: "Hypothèses", icon: SlidersHorizontal, comp: HypothesesPage },
];

function App() {
  const [active, setActive] = useState("dashboard");
  const Active = TABS.find((t) => t.key === active).comp;

  return (
    <div className="App min-h-screen bg-[#F4F4F5]">
      <header className="sticky top-0 z-30 border-b border-[#D4D4D8] bg-white">
        <div className="flex items-center gap-6 px-6">
          <div className="flex items-center gap-2.5 py-3">
            <span className="flex h-9 w-9 items-center justify-center bg-[#0055FF]">
              <HardHat size={19} className="text-white" strokeWidth={2.2} />
            </span>
            <div>
              <h1 className="font-heading text-base font-800 uppercase leading-none tracking-tight">
                Budget Masse Salariale
              </h1>
              <p className="font-mono-data text-[10px] uppercase tracking-widest text-[#52525B]">
                Gestion CCQ · Québec 2026
              </p>
            </div>
          </div>
          <nav className="flex h-full items-stretch">
            {TABS.map((t) => {
              const Icon = t.icon;
              const on = active === t.key;
              return (
                <button
                  key={t.key}
                  data-testid={`nav-${t.key}`}
                  onClick={() => setActive(t.key)}
                  className={`relative flex items-center gap-2 border-b-2 px-4 text-sm font-semibold transition-colors duration-150 ${
                    on
                      ? "border-[#0055FF] text-[#0055FF]"
                      : "border-transparent text-[#52525B] hover:text-[#09090B]"
                  }`}
                >
                  <Icon size={16} strokeWidth={2.2} />
                  <span className="font-heading uppercase tracking-tight">{t.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-[1600px] p-6">
        <Active />
      </main>
      <Toaster position="top-right" theme="light" />
    </div>
  );
}

export default App;
