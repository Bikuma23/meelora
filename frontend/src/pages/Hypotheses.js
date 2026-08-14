import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useYear } from "../context/YearContext";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Save, HardHat, Briefcase, ShieldCheck, Settings2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const MONTHS = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"];

export default function Hypotheses() {
  const { year } = useYear();
  const { user } = useAuth();
  const { t } = useLang();
  const isAdmin = user?.role === "admin";
  const [h, setH] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setH(null); api.getHypotheses(year).then(setH); }, [year]);
  if (!h) return <p className="font-mono-data text-sm text-slate-500">{t("Chargement…")}</p>;

  const setF = (k, v) => setH((p) => ({ ...p, [k]: v }));
  const setCharge = (i, key, v) => setH((p) => { const c = [...p.charges]; c[i] = { ...c[i], [key]: v }; return { ...p, charges: c }; });
  const setDays = (arr, i, v) => setH((p) => { const a = [...p[arr]]; a[i] = Number(v) || 0; return { ...p, [arr]: a }; });
  const setClass = (i, key, v) => setH((p) => { const c = [...(p.security_classes || [])]; c[i] = { ...c[i], [key]: v }; return { ...p, security_classes: c }; });
  const addClass = () => setH((p) => ({ ...p, security_classes: [...(p.security_classes || []), { code: "", description: "", rate: 0 }] }));
  const removeClass = (i) => setH((p) => ({ ...p, security_classes: (p.security_classes || []).filter((_, j) => j !== i) }));

  const save = async () => {
    setSaving(true);
    try { const doc = await api.updateHypotheses(h, year); setH(doc); toast.success(`${t("Hypothèses")} ${year} ${t("enregistrées")}`); }
    catch { toast.error(t("Erreur d'enregistrement")); } finally { setSaving(false); }
  };

  const DayGrid = ({ arr, tint, icon: Icon, title }) => (
    <div className="card p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-700"><Icon size={16} style={{ color: tint }} /> {title}</h3>
        <span className="rounded-full px-2.5 py-0.5 text-xs font-700" style={{ background: tint + "1a", color: tint }}>{h[arr].reduce((s, x) => s + x, 0)} {t("jours")}</span>
      </div>
      <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
        {MONTHS.map((m, i) => (
          <div key={m} className="rounded-lg border border-slate-200 p-2 text-center">
            <p className="text-[10px] uppercase text-slate-400">{t(m)}</p>
            <Input type="number" className="mt-1 h-7 rounded-md border-0 p-0 text-center font-mono-data text-sm" value={h[arr][i]} onChange={(e) => setDays(arr, i, e.target.value)} data-testid={`${arr}-${i}`} />
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="space-y-5" data-testid="hypotheses-page">
      {h.rates_changed && (
        <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700" data-testid="rates-changed-banner">
          <AlertTriangle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-700">{t("Taux de charges sociales modifiés")}</p>
            <p className="mt-0.5 text-[13px] leading-snug">{h.rates_note || t("Les taux ont été mis à jour automatiquement. Cliquez sur Enregistrer pour les appliquer.")}</p>
            {Array.isArray(h.rates_diff) && h.rates_diff.length > 0 && (
              <ul className="mt-2 flex flex-col gap-1" data-testid="rates-diff-list">
                {h.rates_diff.map((c, i) => (
                  <li key={i} className="flex flex-wrap items-center gap-1.5 text-[12px]">
                    <span className="font-600">{c.label} :</span>
                    <span className="rounded bg-white px-1.5 py-0.5 font-mono-data line-through decoration-red-300">{c.old}</span>
                    <span>→</span>
                    <span className="rounded bg-white px-1.5 py-0.5 font-mono-data font-700 text-emerald-700">{c.new}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">{t("Paramètres pour")} <b className="text-slate-800">{h.year}</b> {t("— alimentent tous les calculs budgétaires")}</p>
        {isAdmin && <Button data-testid="save-hypotheses-btn" onClick={save} disabled={saving} className="gap-1.5 bg-[#0F172A] hover:bg-[#0F172A]/90"><Save size={16} /> {saving ? t("Enregistrement…") : t("Enregistrer")}</Button>}
      </div>

      <fieldset disabled={!isAdmin} className="m-0 min-w-0 space-y-5 border-0 p-0">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <DayGrid arr="working_days_ccq" tint="#F59E0B" icon={HardHat} title={`${t("Jours ouvrables CCQ —")} ${h.year}`} />
        <DayGrid arr="working_days_std" tint="#0F172A" icon={Briefcase} title={`${t("Jours ouvrables (standard) —")} ${h.year}`} />
      </div>

      <div className="card p-5" data-testid="charges-card">
        <h3 className="mb-4 flex items-center gap-2 text-sm font-700"><ShieldCheck size={16} className="text-[#8B5CF6]" /> {t("Charges sociales — part employeur (maximums assurables selon les règles du Québec)")}</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="text-[11px] uppercase tracking-wider text-slate-400">
              <th className="px-3 py-2 text-left font-600">{t("Code")}</th><th className="px-3 py-2 text-left font-600">{t("Description")}</th>
              <th className="px-3 py-2 text-right font-600">{t("Taux (%)")}</th><th className="px-3 py-2 text-right font-600">{t("Max. assurable ($)")}</th><th className="px-3 py-2 text-right font-600">{t("Exemption ($)")}</th>
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
        <p className="mt-2 text-[11px] text-slate-400">{t("Max. assurable = 0 signifie aucun plafond (ex. FSS).")}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="card p-5" data-testid="security-classes-card">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-sm font-700"><ShieldCheck size={16} className="text-[#FBBF24]" /> {t("Classe de sécurité CNESST")}</h3>
            <div className="flex items-center gap-2">
              <label className="text-[11px] uppercase text-slate-500">{t("Max. assurable ($)")}</label>
              <Input data-testid="csst-max" type="number" className="h-8 w-28 text-right font-mono-data" value={h.csst_max_assurable || 0} onChange={(e) => setF("csst_max_assurable", Number(e.target.value))} />
            </div>
          </div>
          <table className="w-full text-sm">
            <thead><tr className="text-[11px] uppercase tracking-wider text-slate-400">
              <th className="px-2 py-1.5 text-left font-600">{t("Code")}</th><th className="px-2 py-1.5 text-left font-600">{t("Description")}</th>
              <th className="px-2 py-1.5 text-right font-600">{t("Taux (%)")}</th><th className="w-8"></th>
            </tr></thead>
            <tbody>
              {(h.security_classes || []).map((c, i) => (
                <tr key={i} className="border-t border-slate-100" data-testid={`class-row-${i}`}>
                  <td className="px-2 py-1.5"><Input data-testid={`class-code-${i}`} className="h-8 w-24 font-mono-data" value={c.code} onChange={(e) => setClass(i, "code", e.target.value)} /></td>
                  <td className="px-2 py-1.5"><Input data-testid={`class-desc-${i}`} className="h-8" value={c.description} onChange={(e) => setClass(i, "description", e.target.value)} /></td>
                  <td className="px-2 py-1.5 text-right"><Input data-testid={`class-rate-${i}`} type="number" step="0.01" className="ml-auto h-8 w-24 text-right font-mono-data" value={+(c.rate * 100).toFixed(4)} onChange={(e) => setClass(i, "rate", Number(e.target.value) / 100)} /></td>
                  <td className="px-1 text-center"><button data-testid={`class-del-${i}`} onClick={() => removeClass(i)} className="text-slate-400 hover:text-red-500">✕</button></td>
                </tr>
              ))}
            </tbody>
          </table>
          <Button data-testid="add-class-btn" variant="outline" size="sm" className="mt-3 gap-1.5" onClick={addClass}>+ {t("Ajouter une classe")}</Button>
          <p className="mt-2 text-[11px] text-slate-400">{t("La déduction CSST de chaque employé utilise le taux de sa classe de sécurité, plafonné au maximum assurable.")}</p>
        </div>
        <div className="card p-5">
          <h3 className="mb-4 flex items-center gap-2 text-sm font-700"><Settings2 size={16} className="text-[#0F172A]" /> {t("Autres paramètres")}</h3>
          <div className="grid grid-cols-2 gap-3">
            {[
              ["ccq_rate", "Avantages CCQ (%)", true], ["prime_halo_rate", "Prime HALO (%)", true],
              ["reer_rate", "REER (%)", true],
              ["assurance_annuelle", "Assurance ($/an)", false], ["alloc_securite_montant", "Alloc. sécurité ($/an)", false],
              ["prime_garde_cout_unitaire", "Garde — coût unitaire ($)", false], ["prime_garde_nb_annuel", "Garde — nb / an / employé", false],
            ].map(([k, lbl, pct]) => (
              <div key={k}><label className="text-[11px] uppercase text-slate-500">{t(lbl)}</label>
                <Input data-testid={`param-${k}`} type="number" step={pct ? "0.01" : "1"} className="mt-1 font-mono-data"
                  value={pct ? +(h[k] * 100).toFixed(4) : h[k]}
                  onChange={(e) => setF(k, pct ? Number(e.target.value) / 100 : Number(e.target.value))} />
              </div>
            ))}
          </div>
        </div>
      </div>
      </fieldset>
    </div>
  );
}
