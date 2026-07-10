import { motion } from "framer-motion";

export default function ScenarioTabs({ scenarios, active, onChange }) {
  return (
    <div data-testid="scenario-tabs" className="space-y-2">
      <p className="font-heading text-xs font-800 uppercase tracking-widest text-[#52525B]">
        Scénario budgétaire
      </p>
      <div className="grid grid-cols-1 gap-px border border-[#D4D4D8] bg-[#D4D4D8]">
        {scenarios.map((s) => {
          const isActive = s.name === active;
          return (
            <button
              key={s.name}
              data-testid={`scenario-tab-${s.name.replace(/\s+/g, "-").toLowerCase()}`}
              onClick={() => onChange(s.name)}
              className={`relative px-3 py-2.5 text-left text-sm font-semibold transition-colors duration-150 ${
                isActive
                  ? "bg-[#09090B] text-white"
                  : "bg-white text-[#09090B] hover:bg-[#F4F4F5]"
              }`}
            >
              <span className="font-heading uppercase tracking-tight">{s.name}</span>
              {isActive && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-1 text-[11px] font-normal normal-case leading-snug text-white/70"
                >
                  {s.description}
                </motion.p>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
