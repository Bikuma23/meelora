import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { DollarSign, LogIn, TrendingUp, ShieldCheck, BarChart3 } from "lucide-react";

function formatErr(detail) {
  if (!detail) return "Une erreur est survenue.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("admin@accslegro.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(formatErr(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen bg-[#F4F6F8]">
      {/* Panneau de marque */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-[#063044] p-12 lg:flex">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#F8A942]">
            <DollarSign size={22} className="text-white" strokeWidth={2.4} />
          </span>
          <div>
            <h1 className="font-display text-lg font-800 text-white">Budget Salaires</h1>
            <p className="text-[11px] font-600 uppercase tracking-widest text-[#F8A942]">Pro · Québec</p>
          </div>
        </div>
        <div className="relative z-10">
          <h2 className="font-display text-4xl font-900 leading-tight text-white">
            Pilotez votre<br />masse salariale<br />&amp; vos états financiers.
          </h2>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-slate-300">
            Projections de paie CCQ, scénarios budgétaires multi-années et reporting comptable (Bilan, P&amp;L, flux de trésorerie) — en un seul endroit.
          </p>
          <div className="mt-8 space-y-3">
            {[[TrendingUp, "Calculs de paie et charges en temps réel"], [BarChart3, "Bilan, État des résultats & flux de trésorerie"], [ShieldCheck, "Accès par rôle et journal d'audit"]].map(([Ic, t], i) => (
              <div key={i} className="flex items-center gap-3 text-sm text-slate-200">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10"><Ic size={16} className="text-[#F8A942]" /></span>
                {t}
              </div>
            ))}
          </div>
        </div>
        <p className="relative z-10 text-xs text-slate-400">© {new Date().getFullYear()} Budget Salaires Pro</p>
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-[#F8A942]/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-32 -left-16 h-80 w-80 rounded-full bg-[#1A3B42] blur-3xl" />
      </div>

      {/* Formulaire */}
      <div className="flex w-full items-center justify-center p-6 lg:w-1/2">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#063044]">
              <DollarSign size={22} className="text-white" strokeWidth={2.4} />
            </span>
            <div>
              <h1 className="font-display text-lg font-800 text-slate-900">Budget Salaires</h1>
              <p className="text-[11px] font-600 uppercase tracking-widest text-[#F8A942]">Pro · Québec</p>
            </div>
          </div>
          <form onSubmit={submit} className="card p-8" data-testid="login-form">
            <h2 className="font-display mb-1 text-2xl font-800 text-slate-900">Bon retour</h2>
            <p className="mb-6 text-sm text-slate-500">Connectez-vous à votre tableau de bord.</p>
            <div className="space-y-4">
              <div>
                <Label className="text-xs font-600 uppercase tracking-wide text-slate-500">Courriel</Label>
                <Input data-testid="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="mt-1.5" required />
              </div>
              <div>
                <Label className="text-xs font-600 uppercase tracking-wide text-slate-500">Mot de passe</Label>
                <Input data-testid="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  className="mt-1.5" required />
              </div>
              {error && <p data-testid="login-error" className="text-sm font-500 text-red-600">{error}</p>}
              <Button data-testid="login-submit" type="submit" disabled={loading}
                className="w-full gap-2 bg-[#063044] font-600 hover:bg-[#063044]/90">
                <LogIn size={16} /> {loading ? "Connexion…" : "Se connecter"}
              </Button>
            </div>
          </form>
          <p className="mt-6 text-center text-xs text-slate-400">Accès sécurisé · réservé au personnel autorisé</p>
        </div>
      </div>
    </div>
  );
}
