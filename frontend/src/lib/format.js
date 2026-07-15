export const fmtCAD = (v) =>
  new Intl.NumberFormat("fr-CA", {
    style: "decimal",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(v || 0);

export const fmtPct = (v) => `${((v || 0) * 100).toFixed(2)} %`;

const yearsBetween = (dateStr, ref = new Date()) => {
  if (!dateStr) return null;
  const d = new Date(dateStr + "T00:00:00");
  if (isNaN(d)) return null;
  let years = ref.getFullYear() - d.getFullYear();
  const m = ref.getMonth() - d.getMonth();
  if (m < 0 || (m === 0 && ref.getDate() < d.getDate())) years--;
  return years;
};

export const computeAge = (birthDate) => yearsBetween(birthDate);
export const computeSeniority = (hireDate) => yearsBetween(hireDate);

export const DEPARTMENTS_FALLBACK = [];
