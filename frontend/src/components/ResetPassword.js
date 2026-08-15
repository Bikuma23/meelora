import { useState } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Lock, Eye, EyeOff, ArrowRight, CheckCircle2, Loader2 } from "lucide-react";

function formatErr(detail) {
  if (!detail) return "Une erreur est survenue.";
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

export default function ResetPassword() {
  const token = new URLSearchParams(window.location.search).get("token") || "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password.length < 6) return setError("Le mot de passe doit contenir au moins 6 caractères.");
    if (password !== confirm) return setError("Les mots de passe ne correspondent pas.");
    setLoading(true);
    try {
      await api.resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(formatErr(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6" data-testid="reset-page">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <img src="/meelora-logo.png" alt="Meelora" className="mb-8 h-9 w-auto" />

        {done ? (
          <div className="text-center" data-testid="reset-success">
            <CheckCircle2 size={44} className="mx-auto mb-4 text-[#22C55E]" strokeWidth={1.6} />
            <h2 className="font-display text-2xl font-light text-[#0F172A]">Mot de passe réinitialisé</h2>
            <p className="mt-2 text-sm text-slate-500">Vous pouvez maintenant vous connecter avec votre nouveau mot de passe.</p>
            <Button
              data-testid="reset-go-login"
              onClick={() => { window.location.href = "/"; }}
              className="mt-6 h-[50px] w-full gap-2 rounded-xl bg-[#22C55E] font-semibold text-white hover:bg-[#1EAF54]"
            >
              Aller à la connexion <ArrowRight size={18} />
            </Button>
          </div>
        ) : (
          <form onSubmit={submit} data-testid="reset-form">
            <h2 className="font-display text-3xl font-light text-[#0F172A]">Nouveau mot de passe</h2>
            <p className="mt-2 text-sm text-slate-500">Choisissez un mot de passe sécurisé pour votre compte Meelora.</p>

            {!token && (
              <p className="mt-6 rounded-lg bg-red-50 p-3 text-sm text-red-600" data-testid="reset-no-token">
                Lien invalide ou incomplet. Veuillez refaire une demande depuis la page de connexion.
              </p>
            )}

            <div className="mt-7 space-y-5">
              <div>
                <label className="mb-2 block text-sm font-medium text-[#0F172A]">Mot de passe</label>
                <div className="relative">
                  <Lock size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <Input
                    data-testid="reset-password" type={showPw ? "text" : "password"} required
                    value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••••"
                    className="h-[52px] rounded-xl border-slate-200 bg-slate-50/60 px-12 text-[15px] focus-visible:ring-[#22C55E]"
                  />
                  <button type="button" onClick={() => setShowPw((s) => !s)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700" aria-label="toggle">
                    {showPw ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-[#0F172A]">Confirmer le mot de passe</label>
                <div className="relative">
                  <Lock size={18} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
                  <Input
                    data-testid="reset-confirm" type={showPw ? "text" : "password"} required
                    value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="••••••••••"
                    className="h-[52px] rounded-xl border-slate-200 bg-slate-50/60 pl-12 pr-4 text-[15px] focus-visible:ring-[#22C55E]"
                  />
                </div>
              </div>
              {error && <p data-testid="reset-error" className="text-sm font-medium text-red-600">{error}</p>}
              <Button
                data-testid="reset-submit" type="submit" disabled={loading || !token}
                className="h-[52px] w-full gap-2 rounded-xl bg-[#22C55E] text-[15px] font-semibold text-white hover:bg-[#1EAF54]"
              >
                {loading ? <Loader2 size={18} className="animate-spin" /> : null}
                {loading ? "Réinitialisation…" : "Réinitialiser le mot de passe"}
              </Button>
              <button type="button" data-testid="reset-back" onClick={() => { window.location.href = "/"; }}
                className="w-full text-center text-sm font-medium text-slate-500 hover:text-[#16A34A]">
                ← Retour à la connexion
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
