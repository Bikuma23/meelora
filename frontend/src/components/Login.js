import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Checkbox } from "./ui/checkbox";
import {
  Mail, Lock, Eye, EyeOff, ArrowRight, ShieldCheck, FileText, Globe,
  ChevronDown, Loader2,
} from "lucide-react";

const NAVY = "#001a35";
const GREEN = "#00b978";
const YELLOW = "#ffb900";
const TEXT_MAIN = "#071a35";
const BORDER = "#d8e0ea";

function formatErr(detail) {
  if (!detail) return "Une erreur est survenue.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  if (detail?.message) return detail.message;
  return String(detail);
}

const GoogleIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1Z" />
    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z" />
    <path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z" />
    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.3 9.14 5.38 12 5.38Z" />
  </svg>
);

const MicrosoftIcon = () => (
  <svg width="18" height="18" viewBox="0 0 23 23" aria-hidden="true">
    <path fill="#F25022" d="M1 1h10v10H1z" />
    <path fill="#7FBA00" d="M12 1h10v10H12z" />
    <path fill="#00A4EF" d="M1 12h10v10H1z" />
    <path fill="#FFB900" d="M12 12h10v10H12z" />
  </svg>
);

const LANGS = ["FR", "EN", "DE", "IT"];
const FEATURES = [
  [ShieldCheck, "Données protégées", ["Vos informations sont", "chiffrées et sécurisées", "en tout temps."]],
  [Lock, "Accès sécurisé", ["Authentification avancée", "et contrôle des accès", "par rôle."]],
  [FileText, "Journal d'audit", ["Suivi complet des activités", "pour une transparence", "totale."]],
];

const fieldCls =
  "h-[60px] rounded-[11px] bg-white text-[15px] text-[#071a35] placeholder:text-[#9aa8bd] focus-visible:ring-2 focus-visible:ring-[#00b978]/40 focus-visible:border-[#00b978]";

export default function Login() {
  const { login } = useAuth();
  const { t, lang, setLang } = useLang();
  const [mode, setMode] = useState("login");
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
    <div className="grid min-h-screen grid-cols-1 bg-white lg:grid-cols-[60%_40%]" data-testid="login-page">
      {/* ---------- LEFT BRAND PANEL ---------- */}
      <div
        className="relative hidden flex-col overflow-hidden bg-cover bg-center lg:flex"
        style={{ backgroundColor: "#03152e", backgroundImage: "url('/login-bg.png')" }}
      >
        <div className="relative z-10 flex h-full flex-col px-[60px] pb-[46px] pt-[58px]">
          <img src="/meelora-wordmark-white.png" alt="Meelora" className="h-auto w-[212px] shrink-0 self-start" data-testid="login-brand" />

          <div className="mt-[76px] max-w-[540px]">
            <p className="text-[16px] font-bold uppercase tracking-[0.12em]" style={{ color: GREEN }}>
              {t("VOTRE ENTREPRISE.")}
            </p>
            <h1 className="mt-5 font-display text-[70px] font-normal leading-[1.04] text-white">
              {t("En toute")}<br />
              <span style={{ color: GREEN }}>{t("clarté")}</span>
              <span style={{ color: YELLOW }}>.</span>
            </h1>
            <p className="mt-6 max-w-[520px] text-[19px] font-light leading-[1.55] text-white/85">
              {t("Paie, comptabilité et rapports financiers réunis dans un espace simple, fiable et sécurisé.")}
            </p>
          </div>

          <div className="mt-[52px] grid max-w-[720px] grid-cols-3 gap-0">
            {FEATURES.map(([Ic, title, body], i) => (
              <div key={i} className={i > 0 ? "border-l border-white/12 pl-8" : "pr-8"}>
                <Ic size={32} strokeWidth={1.6} style={{ color: GREEN }} />
                <p className="mb-2 mt-4 text-[16px] font-semibold text-white">{t(title)}</p>
                <p className="text-[13.5px] leading-[1.5] text-white/65">
                  {body.map((ln, j) => (<span key={j}>{t(ln)}<br /></span>))}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-auto flex items-center gap-5 pt-[44px]">
            <span className="flex h-[54px] w-[54px] flex-none items-center justify-center rounded-full border" style={{ borderColor: "rgba(0,185,120,.45)" }}>
              <Lock size={20} strokeWidth={1.7} style={{ color: GREEN }} />
            </span>
            <p className="text-[15px] leading-[1.5] text-white/80">
              {t("Vos données financières restent")}<br />
              {t("confidentielles et sous votre contrôle.")}
            </p>
          </div>
        </div>

        <p className="relative z-10 px-[60px] pb-[10px] text-[13px] text-white/45">
          © {new Date().getFullYear()} Meelora Inc.
        </p>
      </div>

      {/* ---------- RIGHT LOGIN PANEL ---------- */}
      <div className="relative flex items-center justify-center px-6 py-10 sm:px-10">
        <div className="absolute right-[60px] top-[46px] flex items-center gap-2 text-[15px]" data-testid="login-lang-switch">
          <Globe size={17} style={{ color: GREEN }} />
          {LANGS.map((l, i) => {
            const active = lang.toUpperCase() === l;
            return (
              <button
                key={l} type="button" data-testid={`login-lang-${l.toLowerCase()}`}
                onClick={() => setLang(l.toLowerCase())}
                className="flex items-center gap-1 font-medium transition-colors"
                style={{ color: active ? GREEN : TEXT_MAIN, opacity: active ? 1 : 0.75 }}
              >
                {l}{i === 0 && <ChevronDown size={14} />}
              </button>
            );
          })}
        </div>

        <div className="w-full max-w-[540px]">
          <div className="mb-8 flex items-center lg:hidden">
            <img src="/meelora-logo.png" alt="Meelora" className="h-10 w-auto" />
          </div>

          {mode === "login" ? (
            <form onSubmit={submit} data-testid="login-form">
              <h2 className="font-display text-[46px] font-bold leading-none tracking-tight" style={{ color: TEXT_MAIN }}>
                {t("Bon retour")}.
              </h2>
              <p className="mt-4 text-[20px] leading-[1.4] text-[#7b8aa3]">
                {t("Connectez-vous à votre")}<br />{t("espace Meelora.")}
              </p>

              <div className="mt-9 space-y-5">
                <div>
                  <label htmlFor="login-email" className="mb-2 block text-[15px] font-medium" style={{ color: TEXT_MAIN }}>{t("Courriel")}</label>
                  <div className="relative">
                    <Mail size={19} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#9aa8bd]" />
                    <Input id="login-email" data-testid="login-email" type="email" required value={email}
                      onChange={(e) => setEmail(e.target.value)} placeholder={t("nom@entreprise.com")}
                      className={`${fieldCls} pl-12`} style={{ borderColor: BORDER }} />
                  </div>
                </div>

                <div>
                  <label htmlFor="login-password" className="mb-2 block text-[15px] font-medium" style={{ color: TEXT_MAIN }}>{t("Mot de passe")}</label>
                  <div className="relative">
                    <Lock size={19} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#9aa8bd]" />
                    <Input id="login-password" data-testid="login-password" type={showPw ? "text" : "password"} required value={password}
                      onChange={(e) => setPassword(e.target.value)} placeholder="••••••••••"
                      className={`${fieldCls} px-12`} style={{ borderColor: BORDER }} />
                    <button type="button" data-testid="login-toggle-password" onClick={() => setShowPw((s) => !s)}
                      className="absolute right-4 top-1/2 -translate-y-1/2 text-[#9aa8bd] hover:text-[#071a35]"
                      aria-label={showPw ? "Masquer le mot de passe" : "Afficher le mot de passe"}>
                      {showPw ? <EyeOff size={19} /> : <Eye size={19} />}
                    </button>
                  </div>
                </div>

                <div className="flex items-center justify-between">
                  <label className="flex cursor-pointer items-center gap-2.5 text-[15px] text-[#5b6b82]">
                    <Checkbox data-testid="login-remember" checked={remember}
                      onCheckedChange={(v) => setRemember(Boolean(v))}
                      className="h-5 w-5 rounded-[6px] border-[#c4cede] data-[state=checked]:border-[#00b978] data-[state=checked]:bg-[#00b978]" />
                    {t("Se souvenir de moi")}
                  </label>
                  <button type="button" data-testid="login-forgot-link"
                    onClick={() => { setMode("forgot"); setError(""); setNotice(""); }}
                    className="text-[15px] font-medium hover:underline" style={{ color: GREEN }}>
                    {t("Mot de passe oublié ?")}
                  </button>
                </div>

                {error && <p data-testid="login-error" className="text-sm font-medium text-red-600">{error}</p>}

                <Button data-testid="login-submit" type="submit" disabled={loading}
                  className="h-[60px] w-full gap-2 rounded-full text-[16px] font-semibold text-white shadow-sm transition-[filter] hover:brightness-[.95]"
                  style={{ background: "linear-gradient(90deg,#00a86b,#11bd79)" }}>
                  {loading ? <Loader2 size={19} className="animate-spin" /> : null}
                  {loading ? t("Connexion…") : <>{t("Se connecter")} <ArrowRight size={19} /></>}
                </Button>
              </div>

              <div className="my-7 flex items-center gap-4">
                <span className="h-px flex-1" style={{ backgroundColor: BORDER }} />
                <span className="text-[13px] text-[#7b8aa3]">{t("ou continuer avec")}</span>
                <span className="h-px flex-1" style={{ backgroundColor: BORDER }} />
              </div>

              <div className="space-y-3">
                <button type="button" data-testid="login-google" onClick={googleLogin}
                  className="flex h-[58px] w-full items-center justify-center gap-3 rounded-full border bg-white text-[15px] font-semibold transition-colors hover:bg-slate-50"
                  style={{ borderColor: BORDER, color: TEXT_MAIN }}>
                  <GoogleIcon /> {t("Continuer avec Google")}
                </button>
                <button type="button" data-testid="login-microsoft"
                  onClick={() => { setError(""); setNotice(t("Connexion Microsoft bientôt disponible.")); }}
                  className="flex h-[58px] w-full items-center justify-center gap-3 rounded-full border bg-white text-[15px] font-semibold transition-colors hover:bg-slate-50"
                  style={{ borderColor: BORDER, color: TEXT_MAIN }}>
                  <MicrosoftIcon /> {t("Continuer avec Microsoft")}
                </button>
              </div>

              {notice && <p data-testid="login-notice" className="mt-4 text-center text-sm text-[#7b8aa3]">{notice}</p>}

              <div className="mt-7 flex items-start gap-3 text-[13px] leading-[1.5] text-[#8b98ac]">
                <ShieldCheck size={30} strokeWidth={1.5} className="mt-0.5 flex-none text-[#c4cede]" />
                <p>
                  {t("En vous connectant, vous acceptez nos")}{" "}
                  <a href="#" className="font-medium hover:underline" style={{ color: GREEN }}>{t("Conditions d'utilisation")}</a>{" "}
                  {t("et")}{" "}
                  <a href="#" className="font-medium hover:underline" style={{ color: GREEN }}>{t("Politique de confidentialité")}</a>.
                </p>
              </div>
            </form>
          ) : (
            <form onSubmit={submitForgot} data-testid="forgot-form">
              <h2 className="font-display text-[40px] font-bold tracking-tight" style={{ color: TEXT_MAIN }}>
                {t("Mot de passe oublié")} ?
              </h2>
              <p className="mt-3 text-[18px] text-[#7b8aa3]">
                {t("Entrez votre courriel : nous vous enverrons un lien de réinitialisation.")}
              </p>
              <div className="mt-8 space-y-5">
                <div>
                  <label htmlFor="forgot-email" className="mb-2 block text-[15px] font-medium" style={{ color: TEXT_MAIN }}>{t("Courriel")}</label>
                  <div className="relative">
                    <Mail size={19} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[#9aa8bd]" />
                    <Input id="forgot-email" data-testid="forgot-email" type="email" required value={email}
                      onChange={(e) => setEmail(e.target.value)} placeholder={t("nom@entreprise.com")}
                      className={`${fieldCls} pl-12`} style={{ borderColor: BORDER }} />
                  </div>
                </div>
                {error && <p data-testid="forgot-error" className="text-sm font-medium text-red-600">{error}</p>}
                {notice && <p data-testid="forgot-notice" className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-700">{notice}</p>}
                <Button data-testid="forgot-submit" type="submit" disabled={loading}
                  className="h-[60px] w-full gap-2 rounded-full text-[16px] font-semibold text-white hover:brightness-[.95]"
                  style={{ background: "linear-gradient(90deg,#00a86b,#11bd79)" }}>
                  {loading ? <Loader2 size={19} className="animate-spin" /> : null}
                  {loading ? t("Envoi…") : t("Envoyer le lien")}
                </Button>
                <button type="button" data-testid="forgot-back"
                  onClick={() => { setMode("login"); setError(""); setNotice(""); }}
                  className="w-full text-center text-[15px] font-medium text-[#7b8aa3] hover:text-[#00b978]">
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
