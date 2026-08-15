import { useState, useEffect } from "react";
import { api } from "../lib/api";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Lock, Eye, EyeOff, ArrowRight, CheckCircle2, Loader2, AlertTriangle, Building2 } from "lucide-react";

function formatErr(detail) {
  if (!detail) return "Une erreur est survenue.";
  if (typeof detail === "string") return detail;
  if (detail?.message) return detail.message;
  if (Array.isArray(detail)) return detail.map((e) => e?.msg || JSON.stringify(e)).join(" ");
  return String(detail);
}

const PURPOSE_LABEL = {
  workspace_invitation: "Accès à l'espace de travail",
  company_invitation: "Accès à une société",
  client_admin_activation: "Administrateur de société",
  client_admin_replacement: "Administrateur de société",
};

export default function Activate() {
  const token = new URLSearchParams(window.location.search).get("token") || "";
  const [state, setState] = useState("loading"); // loading | valid | invalid | done
  const [invitation, setInvitation] = useState(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) { setState("invalid"); setError("Cette invitation est invalide."); return; }
    api.activationPreview(token)
      .then((d) => { setInvitation(d); setState("valid"); })
      .catch((err) => {
        setState("invalid");
        setError(formatErr(err.response?.data?.detail) || "Cette invitation n'est plus valide.");
      });
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (password.length < 6) return setError("Le mot de passe doit contenir au moins 6 caractères.");
    if (password !== confirm) return setError("Les mots de passe ne correspondent pas.");
    setLoading(true);
    try {
      await api.activate(token, password, invitation?.name || undefined);
      setState("done");
    } catch (err) {
      setError(formatErr(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-6" data-testid="activate-page">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
        <img src="/meelora-logo.png" alt="Meelora" className="mb-8 h-9 w-auto" />

        {state === "loading" && (
          <div className="flex items-center gap-3 text-sm text-slate-500" data-testid="activate-loading">
            <Loader2 className="animate-spin" size={18} /> Vérification de votre invitation…
          </div>
        )}

        {state === "invalid" && (
          <div className="text-center" data-testid="activate-invalid">
            <AlertTriangle size={44} className="mx-auto mb-4 text-[#F8A942]" strokeWidth={1.6} />
            <h2 className="font-display text-2xl font-light text-[#0F172A]">Invitation indisponible</h2>
            <p className="mt-2 text-sm text-slate-500">{error || "Cette invitation a expiré, a été utilisée ou révoquée."}</p>
            <p className="mt-4 text-sm text-slate-500">Demandez à votre administrateur de vous envoyer une nouvelle invitation.</p>
            <Button data-testid="activate-go-login" onClick={() => { window.location.href = "/"; }}
              className="mt-6 h-[50px] w-full gap-2 rounded-xl bg-[#063044] font-semibold text-white hover:bg-[#0a4560]">
              Retour à la connexion <ArrowRight size={18} />
            </Button>
          </div>
        )}

        {state === "done" && (
          <div className="text-center" data-testid="activate-success">
            <CheckCircle2 size={44} className="mx-auto mb-4 text-[#22C55E]" strokeWidth={1.6} />
            <h2 className="font-display text-2xl font-light text-[#0F172A]">Compte activé</h2>
            <p className="mt-2 text-sm text-slate-500">Bienvenue sur Meelora. Vous accédez maintenant à votre espace.</p>
            <Button data-testid="activate-continue" onClick={() => { window.location.href = "/"; }}
              className="mt-6 h-[50px] w-full gap-2 rounded-xl bg-[#22C55E] font-semibold text-white hover:bg-[#1EAF54]">
              Continuer <ArrowRight size={18} />
            </Button>
          </div>
        )}

        {state === "valid" && (
          <form onSubmit={submit} data-testid="activate-form">
            <h2 className="font-display text-3xl font-light text-[#0F172A]">Activez votre accès</h2>
            <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-4" data-testid="activate-context">
              <div className="flex items-center gap-2 text-sm font-semibold text-[#063044]">
                <Building2 size={16} className="text-[#15AF97]" />
                {invitation?.workspace_name || "Meelora"}
              </div>
              <p className="mt-1 text-xs text-slate-500">{PURPOSE_LABEL[invitation?.purpose] || "Invitation"}</p>
              <p className="mt-2 text-sm text-slate-600" data-testid="activate-email">{invitation?.email}</p>
            </div>
            <p className="mt-5 text-sm text-slate-500">Choisissez votre mot de passe. Meelora ne connaît jamais votre mot de passe.</p>

            <label className="mt-5 block overline text-slate-500">Mot de passe</label>
            <div className="relative mt-1">
              <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input data-testid="activate-password" type={showPw ? "text" : "password"} value={password}
                onChange={(e) => setPassword(e.target.value)} className="h-12 pl-9 pr-10" placeholder="••••••••" autoComplete="new-password" />
              <button type="button" onClick={() => setShowPw((s) => !s)} className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400">
                {showPw ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>

            <label className="mt-4 block overline text-slate-500">Confirmer le mot de passe</label>
            <div className="relative mt-1">
              <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <Input data-testid="activate-confirm" type={showPw ? "text" : "password"} value={confirm}
                onChange={(e) => setConfirm(e.target.value)} className="h-12 pl-9" placeholder="••••••••" autoComplete="new-password" />
            </div>

            {error && <p className="mt-4 text-sm text-red-600" data-testid="activate-error">{error}</p>}

            <Button data-testid="activate-submit" type="submit" disabled={loading}
              className="mt-6 h-[50px] w-full gap-2 rounded-xl bg-[#22C55E] font-semibold text-white hover:bg-[#1EAF54]">
              {loading ? <Loader2 className="animate-spin" size={18} /> : <>Activer mon compte <ArrowRight size={18} /></>}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
