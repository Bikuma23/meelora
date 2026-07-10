import { Slider } from "./ui/slider";
import { CATEGORIES } from "../lib/calculations";
import { Zap, Snowflake, Building2, Lock } from "lucide-react";

const ICONS = {
  electricien: Zap,
  frigoriste: Snowflake,
  standard: Building2,
};

function ControlRow({ label, value, suffix, min, max, step, color, onChange, testId, disabled }) {
  return (
    <div className={disabled ? "opacity-50" : ""}>
      <div className="mb-1.5 flex items-baseline justify-between">
        <span className="text-[11px] font-medium uppercase tracking-wide text-[#52525B]">
          {label}
        </span>
        <span className="font-mono-data text-sm font-600 text-[#09090B]" data-testid={`${testId}-value`}>
          {value}
          {suffix}
        </span>
      </div>
      <div className="slider-track">
        <Slider
          data-testid={testId}
          value={[value]}
          min={min}
          max={max}
          step={step}
          disabled={disabled}
          onValueChange={(v) => onChange(v[0])}
          style={{ "--slider-color": color }}
          className="[&_[data-orientation=horizontal]>span]:bg-[var(--slider-color)] [&_[role=slider]]:border-[var(--slider-color)] [&_[role=slider]]:h-4 [&_[role=slider]]:w-4"
        />
      </div>
    </div>
  );
}

export default function CategoryControls({ controls, setControls, catBase, scenario }) {
  const update = (key, field, val) =>
    setControls((prev) => ({ ...prev, [key]: { ...prev[key], [field]: val } }));

  return (
    <div className="space-y-px border border-[#D4D4D8] bg-[#D4D4D8]">
      {CATEGORIES.map((cat) => {
        const Icon = ICONS[cat.key];
        const c = controls[cat.key];
        const info = catBase?.[cat.key];
        const hiringFrozen = scenario?.hiring_frozen;
        return (
          <div key={cat.key} className="bg-white p-4" data-testid={`category-${cat.key}`}>
            <div className="mb-3 flex items-center gap-2">
              <span
                className="flex h-6 w-6 items-center justify-center"
                style={{ backgroundColor: cat.color }}
              >
                <Icon size={14} strokeWidth={2.5} className="text-white" />
              </span>
              <h3 className="font-heading text-sm font-700 uppercase tracking-tight">
                {cat.label}
              </h3>
            </div>
            {info && (
              <p className="mb-3 font-mono-data text-[11px] text-[#52525B]">
                {info.headcount} actifs
                {info.effectiveHires > 0 && (
                  <span className="text-[#00C781]"> · +{info.effectiveHires} embauches</span>
                )}
              </p>
            )}
            <div className="space-y-4">
              <ControlRow
                label="Augmentation salaire"
                value={c.augmentation}
                suffix=" %"
                min={0}
                max={20}
                step={0.5}
                color={cat.color}
                onChange={(v) => update(cat.key, "augmentation", v)}
                testId={`slider-${cat.key}-augmentation`}
              />
              <ControlRow
                label="Heures suppl. estimées"
                value={c.overtime}
                suffix=" h/sem"
                min={0}
                max={20}
                step={1}
                color={cat.color}
                onChange={(v) => update(cat.key, "overtime", v)}
                testId={`slider-${cat.key}-overtime`}
              />
              <ControlRow
                label={hiringFrozen ? "Nouveaux recrutements (gelé)" : "Nouveaux recrutements"}
                value={c.hires}
                suffix=" pers."
                min={0}
                max={15}
                step={1}
                color={cat.color}
                disabled={hiringFrozen}
                onChange={(v) => update(cat.key, "hires", v)}
                testId={`slider-${cat.key}-hires`}
              />
              {hiringFrozen && (
                <p className="flex items-center gap-1 text-[11px] text-[#FF4500]">
                  <Lock size={11} /> Embauches gelées par le scénario
                </p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
