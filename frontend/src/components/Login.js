import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Checkbox } from "./ui/checkbox";
import {
  Mail, Lock, Eye, EyeOff, ArrowRight, ShieldCheck, FileText, Globe,
  Loader2, LockKeyhole,
} from "lucide-react";

function formatErr(detail) {
  if (!detail) return "Une erreur est survenue.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  if (detail?.message) return detail.message;
  return String(detail);
}

const GoogleIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1Z" />
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
    <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z" />
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z" />
  </svg>
);

const MicrosoftIcon = () => (
  <svg width="16" height="16" viewBox="0 0 23 23" aria-hidden="true">
    <path fill="#F25022" d="M1 1h10v10H1z" />
    <path fill="#7FBA00" d="M12 1h10v10H12z" />
    <path fill="#00A4EF" d="M1 12h10v10H1z" />
    <path fill="#FFB900" d="M12 12h10v10H12z" />
  </svg>
);

const LANGS = ["FR", "EN", "DE", "IT"];

export default function Login() {
  const { login } = useAuth();
  const { t, lang, setLang } = useLang();
  const [mode, setMode] = useState("login"); // login | forgot
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [remember, setRemember] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      await login(email.trim(), password, remember);
    } catch (err) {
      setError(formatErr(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  const submitForgot = async (e) => {
    e.preventDefault();
    setError(""); setNotice(""); setLoading(true);
    try {
      const { api } = await import("../lib/api");
      const r = await api.forgotPassword(email.trim());
      setNotice(r?.message || "Si un compte existe, un lien vous a été envoyé.");
    } catch (err) {
      setError(formatErr(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
    // THIS BREAKS THE AUTH.
    const redirectUrl = window.location.origin + "/";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="flex min-h-screen bg-white" data-testid="login-page">
      {/* ---- Left brand / hero panel ---- */}
      <div
        className="relative hidden w-1/2 flex-col justify-between overflow-hidden p-14 lg:flex"
        style={{ backgroundColor: "#0A1420" }}
      >
        <div
          className="pointer-events-none absolute inset-0 bg-cover bg-center opacity-90"
          style={{ backgroundImage: "url('/login-hero-wave.jpg')" }}
        />
        <div className="pointer-events-none absolute inset-0" style={{ background: "linear-gradient(120deg,rgba(10,20,32,.72) 0%,rgba(10,20,32,.35) 55%,rgba(10,20,32,.85) 100%)" }} />

        <div className="relative z-10" data-testid="login-brand">
          <img src="/meelora-logo-white.png" alt="Meelora" className="h-11 w-auto" />
        </div>

        <div className="relative z-10 max-w-md">
          <p className="mb-5 text-xs font-semibold tracking-[0.22em] text-[#34D399]">
            {t("VOTRE ENTREPRISE.")}
          </p>
          <h1 className="font-display text-6xl font-light leading-[1.02] text-white">
            {t("En toute")}<br />
            <span className="font-normal text-[#34D399]">{t("clarté")}</span>
            <span className="text-[#FBBF24]">.</span>
          </h1>
          <p className="mt-7 max-w-sm text-base leading-relaxed text-slate-300/90">
            {t("Paie, comptabilité et rapports financiers réunis dans un espace simple, fiable et sécurisé.")}
          </p>

          <div className="mt-12 grid grid-cols-3 gap-6">
            {[
              [ShieldCheck, "Données protégées", "Vos informations sont chiffrées et sécurisées en tout temps."],
              [LockKeyhole, "Accès sécurisé", "Authentification avancée et contrôle des accès par rôle."],
              [FileText, "Journal d'audit", "Suivi complet des activités pour une transparence totale."],
            ].map(([Ic, title, desc], i) => (
              <div key={i} className={i > 0 ? "border-l border-white/10 pl-6" : ""}>
                <Ic size={22} className="mb-3 text-[#34D399]" strokeWidth={1.6} />
                <p className="mb-1.5 text-sm font-semibold text-white">{t(title)}</p>
                <p className="text-xs leading-relaxed text-slate-400">{t(desc)}</p>
              </div>
            ))}
          </div>

          <div className="mt-12 flex items-center gap-4 rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-sm">
            <span className="flex h-11 w-11 flex-none items-center justify-center rounded-full border border-[#34D399]/40">
              <LockKeyhole size={18} className="text-[#34D399]" strokeWidth={1.6} />
            </span>
            <p className="text-sm leading-relaxed text-slate-300">
              {t("Vos données financières restent confidentielles et sous votre contrôle.")}
            </p>
          </div>
        </div>

        <p className="relative z-10 text-xs text-slate-500">© {new Date().getFullYear()} Meelora Inc.</p>
      </div>

      {/* ---- Right form panel ---- */}
      <div className="relative flex w-full items-center justify-center px-6 py-10 lg:w-1/2">
        {/* Language selector */}
        <div className="absolute right-8 top-8 flex items-center gap-1 text-sm" data-testid="login-lang-switch">
          <Globe size={16} className="mr-1 text-slate-400" />
          {LANGS.map((l) => {
            const active = lang.toUpperCase() === l;
            return (
              <button
                key={l}
                type="button"
                data-testid={`login-lang-${l.toLowerCase()}`}
                onClick={() => setLang(l.toLowerCase())}
                className={`rounded-md px-2 py-1 font-medium transition-colors ${active ? "text-[#16A34A]" : "text-slate-400 hover:text-slate-700"}`}
              >
                {l}
              </button>
            );
          })}
        </div>

        <div className="w-full max-w-md">
          <div className="mb-8 flex items-center lg:hidden">
            <img src="/meelora-logo.png" alt="Meelora" className="h-9 w-auto" />
          </div>

          {mode === "login" ? (
            <form onSubmit={submit} data-testid="login-form">
              <h2 className="font-display text-5xl font-light tracking-tight text-[#0F172A]">
                {t("Bon retour")}<span className="text-[#0F172A]">.</span>
              </h2>
              <p className="mt-3 text-base text-slate-500">
                {t("Connectez-vous à votre espace Meelora.")}
              </p>

              <div className="mt-9 space-y-5">
                <div>
                  <label className="mb-2 block text-sm font-medium text-[#0F172A]">{t("Courriel")}</label>
                  <div className="relative">
                    <Mail size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                      data-testid="login-email"
                      type="email" required value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder={t("nom@entreprise.com")}
                      className="h-[52px] rounded-xl border-slate-200 bg-slate-50/60 pl-12 text-[15px] focus-visible:ring-[#22C55E]"
                    />
                  </div>
                </div>

                <div>
                  <label className="mb-2 block text-sm font-medium text-[#0F172A]">{t("Mot de passe")}</label>
                  <div className="relative">
                    <Lock size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                      data-testid="login-password"
                      type={showPw ? "text" : "password"} required value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••"
                      className="h-[52px] rounded-xl border-slate-200 bg-slate-50/60 px-12 text-[15px] focus-visible:ring-[#22C55E]"
                    />
                    <button
                      type="button" data-testid="login-toggle-password"
                      onClick={() => setShowPw((s) => !s)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                      aria-label={showPw ? "Masquer" : "Afficher"}
                    >
                      {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <label className="flex cursor-pointer items-center gap-2.5 text-sm text-slate-600">
                    <Checkbox
                      data-testid="login-remember"
                      checked={remember}
                      onCheckedChange={(v) => setRemember(Boolean(v))}
                      className="h-5 w-5 rounded-md border-slate-300 data-[state=checked]:border-[#22C55E] data-[state=checked]:bg-[#22C55E]"
                    />
                    {t("Se souvenir de moi")}
                  </label>
                  <button
                    type="button" data-testid="login-forgot-link"
                    onClick={() => { setMode("forgot"); setError(""); setNotice(""); }}
                    className="text-sm font-medium text-[#16A34A] hover:underline"
                  >
                    {t("Mot de passe oublié ?")}
                  </button>
                </div>

                {error && <p data-testid="login-error" className="text-sm font-medium text-red-600">{error}</p>}

                <Button
                  data-testid="login-submit" type="submit" disabled={loading}
                  className="h-[52px] w-full gap-2 rounded-xl bg-[#22C55E] text-[15px] font-semibold text-white shadow-sm transition-colors hover:bg-[#1EAF54]"
                >
                  {loading ? <Loader2 size={18} className="animate-spin" /> : null}
                  {loading ? t("Connexion…") : <>{t("Se connecter")} <ArrowRight size={18} /></>}
                </Button>
              </div>

              <div className="my-7 flex items-center gap-4">
                <span className="h-px flex-1 bg-slate-200" />
                <span className="text-xs text-slate-400">{t("ou continuer avec")}</span>
                <span className="h-px flex-1 bg-slate-200" />
              </div>

              <div className="space-y-3">
                <button
                  type="button" data-testid="login-google" onClick={googleLogin}
                  className="flex h-[52px] w-full items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white text-[15px] font-semibold text-[#0F172A] transition-colors hover:bg-slate-50"
                >
                  <GoogleIcon /> {t("Continuer avec Google")}
                </button>
                <button
                  type="button" data-testid="login-microsoft"
                  onClick={() => { setError(""); setNotice(t("Connexion Microsoft bientôt disponible.")); }}
                  className="flex h-[52px] w-full items-center justify-center gap-3 rounded-xl border border-slate-200 bg-white text-[15px] font-semibold text-[#0F172A] transition-colors hover:bg-slate-50"
                >
                  <MicrosoftIcon /> {t("Continuer avec Microsoft")}
                </button>
              </div>

              {notice && <p data-testid="login-notice" className="mt-4 text-center text-sm text-slate-500">{notice}</p>}

              <div className="mt-8 flex items-start gap-2.5 text-xs leading-relaxed text-slate-400">
                <ShieldCheck size={26} className="mt-0.5 flex-none text-slate-300" strokeWidth={1.5} />
                <p>
                  {t("En vous connectant, vous acceptez nos")}{" "}
                  <a href="#" className="text-[#16A34A] hover:underline">{t("Conditions d'utilisation")}</a>{" "}
                  {t("et")}{" "}
                  <a href="#" className="text-[#16A34A] hover:underline">{t("Politique de confidentialité")}</a>.
                </p>
              </div>
            </form>
          ) : (
            <form onSubmit={submitForgot} data-testid="forgot-form">
              <h2 className="font-display text-4xl font-light tracking-tight text-[#0F172A]">
                {t("Mot de passe oublié")}<span>?</span>
              </h2>
              <p className="mt-3 text-base text-slate-500">
                {t("Entrez votre courriel : nous vous enverrons un lien de réinitialisation.")}
              </p>
              <div className="mt-8 space-y-5">
                <div>
                  <label className="mb-2 block text-sm font-medium text-[#0F172A]">{t("Courriel")}</label>
                  <div className="relative">
                    <Mail size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                      data-testid="forgot-email"
                      type="email" required value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder={t("nom@entreprise.com")}
                      className="h-[52px] rounded-xl border-slate-200 bg-slate-50/60 pl-12 text-[15px] focus-visible:ring-[#22C55E]"
                    />
                  </div>
                </div>
                {error && <p data-testid="forgot-error" className="text-sm font-medium text-red-600">{error}</p>}
                {notice && <p data-testid="forgot-notice" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{notice}</p>}
                <Button
                  data-testid="forgot-submit" type="submit" disabled={loading}
                  className="h-[52px] w-full gap-2 rounded-xl bg-[#22C55E] text-[15px] font-semibold text-white hover:bg-[#1EAF54]"
                >
                  {loading ? <Loader2 size={18} className="animate-spin" /> : null}
                  {loading ? t("Envoi…") : t("Envoyer le lien")}
                </Button>
                <button
                  type="button" data-testid="forgot-back"
                  onClick={() => { setMode("login"); setError(""); setNotice(""); }}
                  className="w-full text-center text-sm font-medium text-slate-500 hover:text-[#16A34A]"
                >
                  ← {t("Retour à la connexion")}
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
