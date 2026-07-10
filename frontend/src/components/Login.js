import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { DollarSign, LogIn } from "lucide-react";

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
    <div className="flex min-h-screen items-center justify-center bg-[#0E1526] p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-[#2563EB] to-[#14B8A6]">
            <DollarSign size={24} className="text-white" strokeWidth={2.4} />
          </span>
          <div>
            <h1 className="text-xl font-800 text-white">Budget Salaires</h1>
            <p className="text-xs font-500 uppercase tracking-widest text-[#14B8A6]">Pro · Québec</p>
          </div>
        </div>
        <form onSubmit={submit} className="rounded-2xl border border-white/10 bg-[#1B2438] p-7" data-testid="login-form">
          <h2 className="mb-1 text-lg font-700 text-white">Connexion</h2>
          <p className="mb-6 text-sm text-slate-400">Accédez à votre tableau de bord budgétaire.</p>
          <div className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wide text-slate-400">Courriel</Label>
              <Input data-testid="login-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                className="mt-1 border-white/10 bg-[#0E1526] text-white placeholder:text-slate-500" required />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wide text-slate-400">Mot de passe</Label>
              <Input data-testid="login-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                className="mt-1 border-white/10 bg-[#0E1526] text-white" required />
            </div>
            {error && <p data-testid="login-error" className="text-sm text-red-400">{error}</p>}
            <Button data-testid="login-submit" type="submit" disabled={loading}
              className="w-full gap-2 bg-[#2563EB] font-600 hover:bg-[#2563EB]/90">
              <LogIn size={16} /> {loading ? "Connexion…" : "Se connecter"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
