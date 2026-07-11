import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { applyTheme } from "../lib/theme";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Sun, Moon, RotateCcw, SlidersHorizontal } from "lucide-react";
import { toast } from "sonner";

const SCEN = { actuel: "Salaires actuels", ca: "Budget CA", revue1: "Revue Budgétaire 1", revue2: "Revue Budgétaire 2" };
const EMP_SORT = { employee_number: "#", title: "Titre", name: "Nom", department: "Département", employment_type: "Type", security_class: "Classe de sécurité", current_annual_salary: "Salaire", age: "Âge", seniority: "Ancienneté" };
const BUD_SORT = { employee_number: "#", name: "Nom", department: "Dépt", employment_type: "Type", new_salary: "Nouveau salaire", vacation: "Vacances", primes_total: "Primes", salaire_brut: "Salaire brut total", avantages: "Avantages", total_budgeted: "Coût total" };
const DIR = { asc: "croissant", desc: "décroissant" };
const DEFAULTS = { theme: "light", default_year: null, budget_scenario: "ca", employees_sort: { key: "employee_number", dir: "asc" }, budget_sort: { key: "employee_number", dir: "asc" } };
const AVATAR_COLORS = ["#14B8A6", "#2563EB", "#8B5CF6", "#F59E0B", "#EC4899", "#EF4444", "#0EA5E9", "#64748B"];

const sortLabel = (map, s) => s?.key ? `${map[s.key] || s.key} · ${DIR[s.dir] || s.dir}` : "—";

export default function Preferences() {
  const { user } = useAuth();
  const [prefs, setPrefs] = useState(null);

  useEffect(() => { api.getPreferences().then((p) => setPrefs(p || {})).catch(() => setPrefs({})); }, []);

  const setTheme = async (theme) => {
    applyTheme(theme);
    setPrefs((p) => ({ ...p, theme }));
    try { await api.updatePreferences({ theme }); } catch { toast.error("Enregistrement du thème échoué"); }
  };

  const setAvatarColor = async (avatar_color) => {
    setPrefs((p) => ({ ...p, avatar_color }));
    try { await api.updatePreferences({ avatar_color }); toast.success("Avatar mis à jour"); } catch { toast.error("Enregistrement échoué"); }
  };

  const reset = async () => {
    try {
      const next = await api.updatePreferences(DEFAULTS);
      setPrefs(next); applyTheme(next.theme || "light");
      toast.success("Préférences réinitialisées");
    } catch { toast.error("Réinitialisation échouée"); }
  };

  if (!prefs) return <p className="font-mono-data text-sm text-slate-500">Chargement…</p>;
  const theme = prefs.theme === "dark" ? "dark" : "light";
  const avatarColor = prefs.avatar_color || "#14B8A6";

  return (
    <div className="max-w-3xl space-y-5" data-testid="preferences-page">
      <div className="card flex items-center gap-3 p-5">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl text-lg font-700 text-white" style={{ backgroundColor: avatarColor }}>{(user?.name || "U").charAt(0)}</span>
        <div>
          <div className="flex items-center gap-2">
            <p className="font-700">{user?.name}</p>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-700 uppercase" style={{ backgroundColor: (user?.role === "admin" ? "#2563EB" : "#64748B") + "22", color: user?.role === "admin" ? "#2563EB" : "#64748B" }} data-testid="profile-role-badge">{user?.role === "admin" ? "Administrateur" : "Utilisateur"}</span>
          </div>
          <p className="text-xs text-slate-500">{user?.email}</p>
        </div>
      </div>

      <div className="card p-5" data-testid="avatar-card">
        <h3 className="mb-1 text-sm font-700">Avatar</h3>
        <p className="mb-3 text-xs text-slate-500">Choisissez la couleur de votre avatar (initiale de votre nom).</p>
        <div className="flex flex-wrap gap-2">
          {AVATAR_COLORS.map((c) => (
            <button key={c} data-testid={`avatar-color-${c.slice(1)}`} onClick={() => setAvatarColor(c)}
              className={`flex h-9 w-9 items-center justify-center rounded-lg text-sm font-700 text-white ring-offset-2 transition ${avatarColor === c ? "ring-2 ring-slate-400" : ""}`} style={{ backgroundColor: c }}>
              {(user?.name || "U").charAt(0)}
            </button>
          ))}
        </div>
      </div>

      <div className="card p-5" data-testid="theme-card">
        <h3 className="mb-1 text-sm font-700">Apparence</h3>
        <p className="mb-3 text-xs text-slate-500">Choisissez le thème de l'interface. Ce réglage est propre à votre compte.</p>
        <div className="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1">
          <button data-testid="theme-light-btn" onClick={() => setTheme("light")}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-600 transition-colors ${theme === "light" ? "bg-white text-[#0E1526] shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            <Sun size={16} /> Clair
          </button>
          <button data-testid="theme-dark-btn" onClick={() => setTheme("dark")}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-600 transition-colors ${theme === "dark" ? "bg-[#0E1526] text-white shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            <Moon size={16} /> Sombre
          </button>
        </div>
      </div>

      <div className="card p-5" data-testid="prefs-summary-card">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-700"><SlidersHorizontal size={16} className="text-[#2563EB]" /> Mes réglages enregistrés</h3>
          <Button data-testid="reset-prefs-btn" variant="outline" size="sm" className="gap-1.5" onClick={reset}><RotateCcw size={14} /> Réinitialiser</Button>
        </div>
        <div className="divide-y divide-slate-100">
          {[
            ["Année par défaut", prefs.default_year || "Année active de l'application"],
            ["Scénario (Salaires & Budget)", SCEN[prefs.budget_scenario] || SCEN.ca],
            ["Tri — Employés", sortLabel(EMP_SORT, prefs.employees_sort)],
            ["Tri — Salaires & Budget", sortLabel(BUD_SORT, prefs.budget_sort)],
            ["Thème", theme === "dark" ? "Sombre" : "Clair"],
          ].map(([l, v]) => (
            <div key={l} className="flex items-center justify-between py-2.5 text-sm">
              <span className="text-slate-500">{l}</span>
              <span className="font-600 text-slate-700">{v}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-slate-400">Les tris et le scénario se mettent à jour automatiquement lorsque vous les modifiez sur les pages Employés et Salaires & Budget.</p>
      </div>
    </div>
  );
}
