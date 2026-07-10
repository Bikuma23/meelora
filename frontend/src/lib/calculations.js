export const MONTHS = [
  "Jan", "Fév", "Mar", "Avr", "Mai", "Juin",
  "Juil", "Août", "Sep", "Oct", "Nov", "Déc",
];

export const WEEKS_PER_MONTH = 4.33;

export const CATEGORIES = [
  { key: "electricien", label: "Électriciens (CCQ)", trade: "Électricien", type: "CCQ", color: "#0055FF" },
  { key: "frigoriste", label: "Frigoristes (CCQ)", trade: "Frigoriste", type: "CCQ", color: "#FF4500" },
  { key: "standard", label: "Employés Standard (Admin/Bureau)", trade: "Admin", type: "Standard", color: "#09090B" },
];

export const defaultControls = () =>
  CATEGORIES.reduce((acc, c) => {
    acc[c.key] = { augmentation: 0, overtime: 0, hires: 0 };
    return acc;
  }, {});

export const formatCurrency = (v) =>
  new Intl.NumberFormat("fr-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 0,
  }).format(v || 0);

const categoryOf = (emp) => {
  if (emp.trade === "Électricien") return "electricien";
  if (emp.trade === "Frigoriste") return "frigoriste";
  return "standard";
};

// Monthly cost of a single employee given category controls + active scenario
function employeeMonthlyCost(emp, ctrl, scenario, ccqRateMap, employerTax) {
  const augFactor = 1 + (ctrl.augmentation || 0) / 100;

  if (emp.type === "CCQ") {
    const hourly = emp.base_hourly_rate * augFactor;
    const otHours = (ctrl.overtime || 0) * scenario.overtime_multiplier;
    const weeklyHours = scenario.base_weekly_hours + otHours;
    const monthlyHours = weeklyHours * WEEKS_PER_MONTH;
    const gross = hourly * monthlyHours;
    const ccq = (ccqRateMap[emp.trade] || 0) * monthlyHours;
    const tax = employerTax * hourly * monthlyHours;
    return { gross, ccq, total: gross + ccq + tax };
  }

  // Standard employee
  const hoursFactor = scenario.base_weekly_hours / 40;
  const salary = emp.base_monthly_salary * augFactor * hoursFactor;
  const otPay = emp.base_hourly_rate * augFactor * (ctrl.overtime || 0) * WEEKS_PER_MONTH;
  const gross = salary + otPay;
  const tax = gross * employerTax;
  return { gross, ccq: 0, total: gross + tax };
}

// Representative (average) monthly cost per new hire in a category
function representativeCost(emps, ctrl, scenario, ccqRateMap, employerTax) {
  if (emps.length === 0) return { gross: 0, ccq: 0, total: 0 };
  const sum = emps.reduce(
    (acc, e) => {
      const c = employeeMonthlyCost(e, ctrl, scenario, ccqRateMap, employerTax);
      acc.gross += c.gross;
      acc.ccq += c.ccq;
      acc.total += c.total;
      return acc;
    },
    { gross: 0, ccq: 0, total: 0 }
  );
  return {
    gross: sum.gross / emps.length,
    ccq: sum.ccq / emps.length,
    total: sum.total / emps.length,
  };
}

export function computeProjection({ employees, controls, scenario, config }) {
  const ccqRateMap = {};
  (config.ccq_rates || []).forEach((r) => (ccqRateMap[r.trade] = r.hourly_benefits_charge));
  const employerTax = config.employer_tax_rate;
  const budget = config.treasury_budget;

  // Group employees by category
  const byCat = { electricien: [], frigoriste: [], standard: [] };
  employees.forEach((e) => byCat[categoryOf(e)].push(e));

  // Base monthly cost + rep cost + effective new hires per category
  const catBase = {};
  CATEGORIES.forEach((cat) => {
    const ctrl = controls[cat.key];
    const emps = byCat[cat.key];
    const base = emps.reduce(
      (acc, e) => {
        const c = employeeMonthlyCost(e, ctrl, scenario, ccqRateMap, employerTax);
        acc.gross += c.gross;
        acc.ccq += c.ccq;
        acc.total += c.total;
        return acc;
      },
      { gross: 0, ccq: 0, total: 0 }
    );
    const rep = representativeCost(emps, ctrl, scenario, ccqRateMap, employerTax);
    const scenarioHires = cat.type === "CCQ" ? scenario.extra_ccq_hires : 0;
    const effectiveHires = scenario.hiring_frozen ? 0 : (ctrl.hires || 0) + scenarioHires;
    catBase[cat.key] = { base, rep, effectiveHires, headcount: emps.length };
  });

  // Monthly series with progressive ramp of new hires across the year
  const monthly = MONTHS.map((label, i) => {
    const row = { month: label };
    let totalCCQ = 0;
    CATEGORIES.forEach((cat) => {
      const b = catBase[cat.key];
      const activeHires = Math.round((b.effectiveHires * (i + 1)) / 12);
      const total = b.base.total + activeHires * b.rep.total;
      const ccq = b.base.ccq + activeHires * b.rep.ccq;
      row[cat.key] = Math.round(total);
      totalCCQ += ccq;
    });
    row._ccq = totalCCQ;
    return row;
  });

  const totalMasse = monthly.reduce(
    (s, m) => s + m.electricien + m.frigoriste + m.standard,
    0
  );
  const totalCCQ = monthly.reduce((s, m) => s + m._ccq, 0);
  const solde = budget - totalMasse;

  // Final headcount incl. new hires (end of year)
  const totalHeadcount = CATEGORIES.reduce(
    (s, cat) => s + catBase[cat.key].headcount + catBase[cat.key].effectiveHires,
    0
  );

  return { monthly, totalMasse, totalCCQ, solde, budget, totalHeadcount, catBase };
}
