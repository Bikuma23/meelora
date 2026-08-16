import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { applyTheme } from "../lib/theme";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Sun, Moon, RotateCcw, SlidersHorizontal, Languages } from "lucide-react";
import { toast } from "sonner";

const SCEN = { actuel: "Salaires actuels", ca: "Budget CA", revue1: "Revue Budgétaire 1", revue2: "Revue Budgétaire 2" };
const EMP_SORT = { employee_number: "#", title: "Titre", name: "Nom", department: "Département", employment_type: "Type", security_class: "Classe de sécurité", current_annual_salary: "Salaire", age: "Âge", seniority: "Ancienneté" };
const BUD_SORT = { employee_number: "#", name: "Nom", department: "Dépt", employment_type: "Type", new_salary: "Nouveau salaire", vacation: "Vacances", primes_total: "Primes", salaire_brut: "Salaire brut total", avantages: "Avantages", total_budgeted: "Coût total" };
const DIR = { asc: "croissant", desc: "décroissant" };
const DEFAULTS = { theme: "light", default_year: null, budget_scenario: "ca", employees_sort: { key: "employee_number", dir: "asc" }, budget_sort: { key: "employee_number", dir: "asc" } };
const AVATAR_COLORS = ["#FBBF24", "#0F172A", "#8B5CF6", "#F59E0B", "#EC4899", "#EF4444", "#0EA5E9", "#64748B"];

function EmailChangeCard() {
  const { user } = useAuth();
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [newEmail, setNewEmail] = useState("");
  const [pending, setPending] = useState(null); // {verify_token, verify_link, email_sent}
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const request = async () => {
    if (!newEmail.trim()) return toast.error(t("Saisissez la nouvelle adresse"));
    setBusy(true);
    try { const r = await api.requestEmailChange(newEmail.trim()); setPending(r); toast.success(t("Vérification envoyée à la nouvelle adresse")); }
    catch (e) { toast.error(e.response?.data?.detail || t("Demande impossible")); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    if (!pending?.verify_token) return;
    setBusy(true);
    try {
      const r = await api.confirmEmailChange(pending.verify_token);
      setDone(true); setPending(null);
      toast.success(t("Adresse de connexion mise à jour : ") + r.email);
    } catch (e) { toast.error(e.response?.data?.detail || t("Confirmation impossible")); }
    finally { setBusy(false); }
  };
  return (
    <div className="card p-5" data-testid="email-login-card">
      <h3 className="mb-1 text-sm font-700">{t("Courriel de connexion")}</h3>
      <p className="mb-3 text-xs text-slate-500">{t("Opération sensible : la nouvelle adresse doit être vérifiée. L'adresse actuelle reste active jusqu'à la validation. Vos rôles et accès ne changent pas.")}</p>
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono-data text-sm text-slate-700" data-testid="current-login-email">{user?.email}</span>
        {!open && !done && <Button variant="outline" size="sm" data-testid="email-change-open" onClick={() => setOpen(true)}>{t("Modifier")}</Button>}
        {done && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-600 text-emerald-700" data-testid="email-change-done">{t("Reconnectez-vous avec la nouvelle adresse")}</span>}
      </div>
      {open && !done && (
        <div className="mt-4 space-y-3 rounded-xl border border-slate-200 p-4" data-testid="email-change-panel">
          <div>
            <Label className="text-[11px] uppercase text-slate-500">{t("Nouvelle adresse de connexion")}</Label>
            <Input type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} placeholder="nouvelle@meelora.com" data-testid="email-change-input" />
          </div>
          {!pending ? (
            <div className="flex gap-2">
              <Button size="sm" disabled={busy} onClick={request} data-testid="email-change-request">{t("Envoyer la vérification")}</Button>
              <Button size="sm" variant="ghost" onClick={() => { setOpen(false); setNewEmail(""); }}>{t("Annuler")}</Button>
            </div>
          ) : (
            <div className="space-y-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-800" data-testid="email-change-verify">
              <p><b>{t("Vérification requise")}</b> — {pending.email_sent ? t("un lien a été envoyé à ") : t("(aperçu : email non configuré) confirmez pour ")} <b>{pending.pending_email}</b>.</p>
              <Button size="sm" disabled={busy} onClick={confirm} data-testid="email-change-confirm">{t("J'ai vérifié — appliquer le changement")}</Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Preferences() {
  const { user } = useAuth();
  const { t, lang, setLang } = useLang();
  const [prefs, setPrefs] = useState(null);

  const sortLabel = (map, s) => s?.key ? `${t(map[s.key] || s.key)} · ${t(DIR[s.dir] || s.dir)}` : "—";

  useEffect(() => { api.getPreferences().then((p) => setPrefs(p || {})).catch(() => setPrefs({})); }, []);

  const setTheme = async (theme) => {
    applyTheme(theme);
    setPrefs((p) => ({ ...p, theme }));
    try { await api.updatePreferences({ theme }); } catch { toast.error(t("Enregistrement du thème échoué")); }
  };

  const changeLang = (l) => { setLang(l); toast.success(t("Langue mise à jour")); };

  const setAvatarColor = async (avatar_color) => {
    setPrefs((p) => ({ ...p, avatar_color }));
    try { await api.updatePreferences({ avatar_color }); toast.success(t("Avatar mis à jour")); } catch { toast.error(t("Enregistrement échoué")); }
  };

  const reset = async () => {
    try {
      const next = await api.updatePreferences(DEFAULTS);
      setPrefs(next); applyTheme(next.theme || "light");
      toast.success(t("Préférences réinitialisées"));
    } catch { toast.error(t("Réinitialisation échouée")); }
  };

  if (!prefs) return <p className="font-mono-data text-sm text-slate-500">{t("Chargement…")}</p>;
  const theme = prefs.theme === "dark" ? "dark" : "light";
  const avatarColor = prefs.avatar_color || "#FBBF24";

  return (
    <div className="max-w-3xl space-y-5" data-testid="preferences-page">
      <div className="card flex items-center gap-3 p-5">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl text-lg font-700 text-white" style={{ backgroundColor: avatarColor }}>{(user?.name || "U").charAt(0)}</span>
        <div>
          <div className="flex items-center gap-2">
            <p className="font-700">{user?.name}</p>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-700 uppercase" style={{ backgroundColor: (user?.role === "admin" ? "#0F172A" : "#64748B") + "22", color: user?.role === "admin" ? "#0F172A" : "#64748B" }} data-testid="profile-role-badge">{user?.role === "admin" ? t("Administrateur") : t("Utilisateur")}</span>
          </div>
          <p className="text-xs text-slate-500">{user?.email}</p>
        </div>
      </div>

      <EmailChangeCard />

      <div className="card p-5" data-testid="avatar-card">
        <h3 className="mb-1 text-sm font-700">{t("Avatar")}</h3>
        <p className="mb-3 text-xs text-slate-500">{t("Choisissez la couleur de votre avatar (initiale de votre nom).")}</p>
        <div className="flex flex-wrap gap-2">
          {AVATAR_COLORS.map((c) => (
            <button key={c} data-testid={`avatar-color-${c.slice(1)}`} onClick={() => setAvatarColor(c)}
              className={`flex h-9 w-9 items-center justify-center rounded-lg text-sm font-700 text-white ring-offset-2 transition ${avatarColor === c ? "ring-2 ring-slate-400" : ""}`} style={{ backgroundColor: c }}>
              {(user?.name || "U").charAt(0)}
            </button>
          ))}
        </div>
      </div>

      <div className="card p-5" data-testid="lang-card">
        <h3 className="mb-1 flex items-center gap-2 text-sm font-700"><Languages size={16} className="text-[#22C55E]" /> {t("Langue")}</h3>
        <p className="mb-3 text-xs text-slate-500">{t("Choisissez la langue de l'interface. Ce réglage est propre à votre compte.")}</p>
        <div className="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1">
          <button data-testid="lang-fr-btn" onClick={() => changeLang("fr")}
            className={`rounded-lg px-4 py-2 text-sm font-600 transition-colors ${lang === "fr" ? "bg-[#0F172A] text-white shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            {t("Français")}
          </button>
          <button data-testid="lang-en-btn" onClick={() => changeLang("en")}
            className={`rounded-lg px-4 py-2 text-sm font-600 transition-colors ${lang === "en" ? "bg-[#0F172A] text-white shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            {t("Anglais (US)")}
          </button>
        </div>
      </div>

      <div className="card p-5" data-testid="theme-card">
        <h3 className="mb-1 text-sm font-700">{t("Apparence")}</h3>
        <p className="mb-3 text-xs text-slate-500">{t("Choisissez le thème de l'interface. Ce réglage est propre à votre compte.")}</p>
        <div className="inline-flex rounded-xl border border-slate-200 bg-slate-50 p-1">
          <button data-testid="theme-light-btn" onClick={() => setTheme("light")}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-600 transition-colors ${theme === "light" ? "bg-white text-[#0E1526] shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            <Sun size={16} /> {t("Clair")}
          </button>
          <button data-testid="theme-dark-btn" onClick={() => setTheme("dark")}
            className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-600 transition-colors ${theme === "dark" ? "bg-[#0E1526] text-white shadow-sm" : "text-slate-500 hover:text-slate-700"}`}>
            <Moon size={16} /> {t("Sombre")}
          </button>
        </div>
      </div>

      <div className="card p-5" data-testid="prefs-summary-card">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-700"><SlidersHorizontal size={16} className="text-[#0F172A]" /> {t("Mes réglages enregistrés")}</h3>
          <Button data-testid="reset-prefs-btn" variant="outline" size="sm" className="gap-1.5" onClick={reset}><RotateCcw size={14} /> {t("Réinitialiser")}</Button>
        </div>
        <div className="divide-y divide-slate-100">
          {[
            [t("Année par défaut"), prefs.default_year || t("Année active de l'application")],
            [t("Scénario (Salaires & Budget)"), t(SCEN[prefs.budget_scenario] || SCEN.ca)],
            [t("Tri — Employés"), sortLabel(EMP_SORT, prefs.employees_sort)],
            [t("Tri — Salaires & Budget"), sortLabel(BUD_SORT, prefs.budget_sort)],
            [t("Thème"), theme === "dark" ? t("Sombre") : t("Clair")],
          ].map(([l, v]) => (
            <div key={l} className="flex items-center justify-between py-2.5 text-sm">
              <span className="text-slate-500">{l}</span>
              <span className="font-600 text-slate-700">{v}</span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-[11px] text-slate-400">{t("Les tris et le scénario se mettent à jour automatiquement lorsque vous les modifiez sur les pages Employés et Salaires & Budget.")}</p>
      </div>
    </div>
  );
}
