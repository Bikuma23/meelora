import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Save, HardHat, Briefcase, ShieldCheck, TrendingUp, Settings2 } from "lucide-react";
import { toast } from "sonner";

const MONTHS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"];

export default function Hypotheses() {
  const [h, setH] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.getHypotheses().then(setH); }, []);
  if (!h) return <p className="font-mono-data text-sm text-slate-500">Chargement…</p>;

  const setF = (k, v) => setH((p) => ({ ...p, [k]: v }));
  const setCharge = (i, key, v) => setH((p) => { const c = [...p.charges]; c[i] = { ...c[i], [key]: v }; return { ...p, charges: c }; });
  const setDays = (arr, i, v) => setH((p) => { const a = [...p[arr]]; a[i] = Number(v) || 0; return { ...p, [arr]: a }; });

  const save = async () => {
    setSaving(true);
    try { await api.updateHypotheses(h); toast.success("Hypothèses enregistrées"); }
    catch { toast.error("Erreur d'enregistrement"); } finally { setSaving(false); }
  };

  const DayGrid = ({ arr, total, tint, icon: Icon, title }) => (
    <div className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-700"><Icon size={16} style={{ color: tint }} /> {title}</h3>
        <span className="rounded-full px-2.5 py-0.5 text-xs font-700" style={{ background: tint + "1a", color: tint }}>{h[arr].reduce((s, x) => s + x, 0)} jours</span>
      </div>
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
        {MONTHS.map((m, i) => (
          <div key={m} className="rounded-lg border border-slate-200 p-2 text-center">
            <p className="text-[10px] uppercase text-slate-400">{m}</p>
            <Input type="number" className="mt-1 h-7 rounded-md border-0 p-0 text-center font-mono-data text-sm" value={h[arr][i]} onChange={(e) => setDays(arr, i, e.target.value)} data-testid={`${arr}-${i}`} />
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="space-y-5" data-testid="hypotheses-page">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">Paramètres pour <b className="text-slate-800">{h.year}</b> — alimentent tous les calculs budgétaires</p>
        <Button data-testid="save-hypotheses-btn" onClick={save} disabled={saving} className="gap-1.5 bg-[#2563EB] hover:bg-[#2563EB]/90"><Save size={16} /> {saving ? "Enregistrement…" : "Enregistrer"}</Button>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DayGrid arr="working_days_ccq" tint="#F59E0B" icon={HardHat} title={`Jours ouvrables CCQ — ${h.year}`} />
        <DayGrid arr="working_days_std" tint="#2563EB" icon={Briefcase} title={`Jours ouvrables (standard) — ${h.year}`} />
      </div>

      <div className="card p-5" data-testid="charges-card">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-700"><ShieldCheck size={16} className="text-[#8B5CF6]" /> Charges sociales — part employeur (maximums assurables selon les règles du Québec)</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-[11px] uppercase tracking-wider text-slate-400">
              <th className="px-3 py-2 text-left font-600">Code</th><th className="px-3 py-2 text-left font-600">Description</th>
              <th className="px-3 py-2 text-right font-600">Taux (%)</th><th className="px-3 py-2 text-right font-600">Max. assurable ($)</th><th className="px-3 py-2 text-right font-600">Exemption ($)</th>
            </tr></thead>
            <tbody>
              {h.charges.map((c, i) => (
                <tr key={c.code} className="border-t border-slate-100">
                  <td className="px-3 py-2"><span className="rounded bg-slate-100 px-2 py-0.5 font-mono-data text-xs font-600">{c.code}</span></td>
                  <td className="px-3 py-2 text-slate-600">{c.name}</td>
                  <td className="px-3 py-2 text-right"><Input data-testid={`charge-rate-${c.code}`} type="number" step="0.01" className="ml-auto h-8 w-24 text-right font-mono-data" value={+(c.rate * 100).toFixed(4)} onChange={(e) => setCharge(i, "rate", Number(e.target.value) / 100)} /></td>
                  <td className="px-3 py-2 text-right"><Input data-testid={`charge-ceiling-${c.code}`} type="number" className="ml-auto h-8 w-28 text-right font-mono-data" value={c.ceiling} onChange={(e) => setCharge(i, "ceiling", Number(e.target.value))} /></td>
                  <td className="px-3 py-2 text-right"><Input type="number" className="ml-auto h-8 w-24 text-right font-mono-data" value={c.exemption} onChange={(e) => setCharge(i, "exemption", Number(e.target.value))} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] text-slate-400">Max. assurable = 0 signifie aucun plafond (ex. FSS).</p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-700"><TrendingUp size={16} className="text-[#14B8A6]" /> Augmentation</h3>
          <div className="grid grid-cols-2 gap-3">
            <div><label className="text-[11px] uppercase text-slate-500">Augmentation Autres (%)</label><Input data-testid="aug-autres" type="number" step="0.01" className="mt-1 font-mono-data" value={+(h.augmentation_autres * 100).toFixed(3)} onChange={(e) => setF("augmentation_autres", Number(e.target.value) / 100)} /></div>
            <div><label className="text-[11px] uppercase text-slate-500">Augmentation CCQ (%)</label><Input data-testid="aug-ccq" type="number" step="0.01" className="mt-1 font-mono-data" value={+(h.augmentation_ccq * 100).toFixed(3)} onChange={(e) => setF("augmentation_ccq", Number(e.target.value) / 100)} /></div>
          </div>
        </div>
        <div className="card p-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-700"><Settings2 size={16} className="text-[#2563EB]" /> Autres paramètres</h3>
          <div className="grid grid-cols-2 gap-3">
            {[
              ["ccq_rate", "Avantages CCQ (%)", true], ["ccq_electricien_compagnon_rate", "Compagnon élec. (%)", true],
              ["reer_rate", "REER (%)", true], ["prime_halo_rate", "Prime HALO (%)", true],
              ["assurance_annuelle", "Assurance ($/an)", false], ["alloc_securite_montant", "Alloc. sécurité ($/an)", false],
              ["prime_garde_cout_unitaire", "Garde — coût unitaire ($)", false], ["prime_garde_nb_annuel", "Garde — nb / an", false],
            ].map(([k, lbl, pct]) => (
              <div key={k}><label className="text-[11px] uppercase text-slate-500">{lbl}</label>
                <Input data-testid={`param-${k}`} type="number" step={pct ? "0.01" : "1"} className="mt-1 font-mono-data"
                  value={pct ? +(h[k] * 100).toFixed(4) : h[k]}
                  onChange={(e) => setF(k, pct ? Number(e.target.value) / 100 : Number(e.target.value))} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
