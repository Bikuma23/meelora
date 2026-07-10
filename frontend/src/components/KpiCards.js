import { motion } from "framer-motion";
import { formatCurrency } from "../lib/calculations";
import { Wallet, ShieldCheck, TrendingDown, TrendingUp } from "lucide-react";

function Kpi({ label, value, sub, accent, icon: Icon, testId }) {
  return (
    <div
      data-testid={testId}
      className="flex flex-col justify-between border border-[#D4D4D8] bg-white p-5"
    >
      <div className="flex items-start justify-between">
        <span className="max-w-[70%] text-[11px] font-semibold uppercase tracking-widest text-[#52525B]">
          {label}
        </span>
        <Icon size={18} style={{ color: accent }} strokeWidth={2} />
      </div>
      <motion.div
        key={value}
        initial={{ opacity: 0.4 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.15 }}
      >
        <p
          className="mt-4 font-mono-data text-3xl font-600 leading-none tracking-tight lg:text-4xl"
          style={{ color: accent }}
        >
          {value}
        </p>
        {sub && <p className="mt-2 font-mono-data text-xs text-[#52525B]">{sub}</p>}
      </motion.div>
    </div>
  );
}

export default function KpiCards({ result }) {
  const soldePositive = result.solde >= 0;
  const consumed = ((result.totalMasse / result.budget) * 100).toFixed(1);
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
      <Kpi
        testId="kpi-masse-salariale"
        label="Total Masse Salariale (annuel)"
        value={formatCurrency(result.totalMasse)}
        sub={`${result.totalHeadcount} employés · ${consumed}% du budget`}
        accent="#09090B"
        icon={Wallet}
      />
      <Kpi
        testId="kpi-cotisations-ccq"
        label="Total Cotisations CCQ"
        value={formatCurrency(result.totalCCQ)}
        sub="Avantages sociaux horaires CCQ"
        accent="#0055FF"
        icon={ShieldCheck}
      />
      <Kpi
        testId="kpi-solde-tresorerie"
        label="Solde de Trésorerie Restant"
        value={formatCurrency(result.solde)}
        sub={`Budget: ${formatCurrency(result.budget)}`}
        accent={soldePositive ? "#00C781" : "#FF4500"}
        icon={soldePositive ? TrendingUp : TrendingDown}
      />
    </div>
  );
}
