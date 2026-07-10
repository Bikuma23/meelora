import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { computeProjection, defaultControls } from "../lib/calculations";
import ScenarioTabs from "./ScenarioTabs";
import CategoryControls from "./CategoryControls";
import KpiCards from "./KpiCards";
import SalaryChart from "./SalaryChart";
import EmployeeTable from "./EmployeeTable";
import { HardHat, RotateCcw } from "lucide-react";
import { toast } from "sonner";

export default function Dashboard() {
  const [config, setConfig] = useState(null);
  const [employees, setEmployees] = useState([]);
  const [activeScenario, setActiveScenario] = useState("Budget Initial");
  const [controls, setControls] = useState(defaultControls());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.getConfig(), api.getEmployees()])
      .then(([cfg, emps]) => {
        setConfig(cfg);
        setEmployees(emps);
      })
      .catch(() => toast.error("Erreur de chargement des données"))
      .finally(() => setLoading(false));
  }, []);

  const scenario = useMemo(
    () => config?.scenarios.find((s) => s.name === activeScenario),
    [config, activeScenario]
  );

  const result = useMemo(() => {
    if (!config || !scenario) return null;
    return computeProjection({ employees, controls, scenario, config });
  }, [employees, controls, scenario, config]);

  const reset = () => {
    setControls(defaultControls());
    toast.success("Ajustements réinitialisés");
  };

  const onCreate = async (data) => {
    const created = await api.createEmployee(data);
    setEmployees((p) => [...p, created]);
  };
  const onUpdate = async (id, data) => {
    const updated = await api.updateEmployee(id, data);
    setEmployees((p) => p.map((e) => (e.id === id ? updated : e)));
  };
  const onDelete = async (id) => {
    await api.deleteEmployee(id);
    setEmployees((p) => p.filter((e) => e.id !== id));
  };

  if (loading || !config || !result) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#F4F4F5]">
        <p className="font-mono-data text-sm text-[#52525B]">Chargement…</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[#F4F4F5] lg:flex-row">
      {/* LEFT PANEL */}
      <aside className="flex w-full flex-col border-b border-[#D4D4D8] bg-white lg:h-screen lg:w-96 lg:border-b-0 lg:border-r">
        <div className="flex items-center gap-2.5 border-b border-[#D4D4D8] px-5 py-4">
          <span className="flex h-8 w-8 items-center justify-center bg-[#0055FF]">
            <HardHat size={18} className="text-white" strokeWidth={2.2} />
          </span>
          <div>
            <h1 className="font-heading text-base font-800 uppercase leading-none tracking-tight">
              Masse Salariale
            </h1>
            <p className="font-mono-data text-[10px] uppercase tracking-widest text-[#52525B]">
              Budgétisation CCQ
            </p>
          </div>
        </div>
        <div className="flex-1 space-y-6 overflow-y-auto p-5">
          <ScenarioTabs
            scenarios={config.scenarios}
            active={activeScenario}
            onChange={setActiveScenario}
          />
          <div>
            <div className="mb-2 flex items-center justify-between">
              <p className="font-heading text-xs font-800 uppercase tracking-widest text-[#52525B]">
                Ajustements globaux
              </p>
              <button
                data-testid="reset-controls-btn"
                onClick={reset}
                className="flex items-center gap-1 text-[11px] text-[#52525B] transition-colors hover:text-[#0055FF]"
              >
                <RotateCcw size={11} /> Réinitialiser
              </button>
            </div>
            <CategoryControls
              controls={controls}
              setControls={setControls}
              catBase={result.catBase}
              scenario={scenario}
            />
          </div>
        </div>
      </aside>

      {/* RIGHT CANVAS */}
      <main className="flex-1 space-y-6 overflow-y-auto p-6">
        <KpiCards result={result} />
        <SalaryChart data={result.monthly} />
        <EmployeeTable
          employees={employees}
          onCreate={onCreate}
          onUpdate={onUpdate}
          onDelete={onDelete}
        />
      </main>
    </div>
  );
}
