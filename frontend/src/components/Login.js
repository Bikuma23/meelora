import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
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
  const { t } = useLang();
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
    <div className="flex min-h-screen bg-[#F3F4F6]">
      {/* Panneau de marque — héros */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden p-12 lg:flex">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: "url('https://images.unsplash.com/photo-1599398766380-23b3144142c7?crop=entropy&cs=srgb&fm=jpg&q=85&w=1400')" }}
        />
        <div className="absolute inset-0 bg-[#0F172A]/85" />
        <div className="relative z-10 inline-flex items-center rounded-2xl bg-white px-5 py-4 shadow-lg" data-testid="login-brand">
          <img src="/meelora-logo-full.png" alt="Meelora — Votre entreprise, clairement." className="h-16 w-auto" />
        </div>

        <div className="relative z-10">
          <div className="max-w-md border border-white/20 p-8">
            <p className="overline mb-4 text-white/70">{t("Plateforme financière")}</p>
            <h2 className="font-display text-4xl font-300 leading-[1.15] text-white">
              {t("De la paie au bilan,")}<br />{t("tout au")}{" "}
              <span className="font-400 underline decoration-[#22C55E] decoration-2 underline-offset-4">{t("même endroit")}</span>.
            </h2>
          </div>
          <div className="mt-8 space-y-3">
            {[[TrendingUp, "Calculs de paie et charges en temps réel"], [BarChart3, "Bilan, État des résultats & flux de trésorerie"], [ShieldCheck, "Accès par rôle et journal d'audit"]].map(([Ic, text], i) => (
              <div key={i} className="flex items-center gap-3 border-l-2 border-[#22C55E] pl-3 text-sm text-slate-200">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10"><Ic size={16} className="text-[#22C55E]" /></span>
                {t(text)}
              </div>
            ))}
          </div>
        </div>
        <p className="relative z-10 text-xs text-slate-300">© {new Date().getFullYear()} Meelora inc.</p>
      </div>

      {/* Formulaire */}
      <div className="flex w-full items-center justify-center p-6 lg:w-1/2">
        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center lg:hidden">
            <img src="/meelora-logo.png" alt="Meelora" className="h-9 w-auto" />
          </div>
          <form onSubmit={submit} className="card p-8" data-testid="login-form">
            <p className="overline mb-2">{t("Espace sécurisé")}</p>
            <h2 className="font-display mb-1 text-3xl font-300 text-[#0F172A]">{t("Bon retour")}</h2>
            <p className="mb-6 text-sm text-slate-500">{t("Connectez-vous à votre tableau de bord.")}</p>
            <div className="space-y-4">
              <div>
                <Label className="overline">{t("Courriel")}</Label>
                <Input data-testid="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                  className="mt-1.5" required />
              </div>
              <div>
                <Label className="overline">{t("Mot de passe")}</Label>
                <Input data-testid="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                  className="mt-1.5" required />
              </div>
              {error && <p data-testid="login-error" className="text-sm font-500 text-red-600">{error}</p>}
              <Button data-testid="login-submit" type="submit" disabled={loading}
                className="w-full gap-2 rounded-md bg-[#22C55E] font-600 text-white hover:bg-[#22C55E]/90">
                <LogIn size={16} /> {loading ? t("Connexion…") : t("Se connecter")}
              </Button>
            </div>
          </form>
          <p className="mt-6 text-center text-xs text-slate-400">{t("Accès sécurisé · réservé au personnel autorisé")}</p>
        </div>
      </div>
    </div>
  );
}
