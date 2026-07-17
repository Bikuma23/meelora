import { useState, useEffect } from "react";
import { api } from "../../lib/api";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../../components/ui/dialog";
import { toast } from "sonner";
import { FileText, Info, Sparkles, Wand2, ChevronDown, ChevronRight, AlertTriangle } from "lucide-react";
import { money, PeriodSelect } from "./shared";

export function AiConfigDialog({ open, onOpenChange }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) api.acctAiGetConfig().then(setCfg).catch(() => {}); }, [open]);
  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));
  const save = async () => {
    setSaving(true);
    try {
      const body = { enabled: cfg.enabled, provider: cfg.provider, model: cfg.model,
        azure_endpoint: cfg.azure_endpoint, azure_deployment: cfg.azure_deployment, azure_api_version: cfg.azure_api_version,
        variance_threshold_amount: Number(cfg.variance_threshold_amount), variance_threshold_pct: Number(cfg.variance_threshold_pct),
        anomaly_sensitivity: Number(cfg.anomaly_sensitivity) };
      if (cfg._openai_key) body.openai_api_key = cfg._openai_key;
      if (cfg._azure_key) body.azure_api_key = cfg._azure_key;
      const r = await api.acctAiSaveConfig(body);
      setCfg({ ...r, _openai_key: "", _azure_key: "" });
      toast.success(r.configured ? "IA configurée et activée" : "Configuration enregistrée (non active — vérifiez les identifiants)");
    } catch (e) { toast.error(e.response?.data?.detail || "Échec"); }
    finally { setSaving(false); }
  };
  const clearKeys = async () => { const r = await api.acctAiClearKeys(); setCfg({ ...r, _openai_key: "", _azure_key: "" }); toast.success("Clés effacées — IA désactivée"); };
  if (!cfg) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="ai-config-dialog" className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Configuration de l'assistant IA</DialogTitle>
          <DialogDescription className="text-xs">Les identifiants restent côté serveur. Retirez la clé pour revenir au comportement sans IA. {cfg.configured ? "✅ Actif" : "⚠️ Inactif"}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" data-testid="ai-enabled" checked={!!cfg.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Activer les fonctionnalités IA</label>
          <div>
            <label className="mb-1 block text-[11px] font-700 text-slate-600">Fournisseur</label>
            <select data-testid="ai-provider" value={cfg.provider} onChange={(e) => set("provider", e.target.value)} className="h-9 w-full rounded-md border border-slate-300 px-2 text-sm">
              <option value="emergent">Clé universelle Emergent (aucune clé requise)</option>
              <option value="openai">OpenAI (clé API)</option>
              <option value="azure">Azure OpenAI Service</option>
            </select>
          </div>
          {cfg.provider !== "azure" && (
            <div>
              <label className="mb-1 block text-[11px] font-700 text-slate-600">Modèle</label>
              <Input data-testid="ai-model" value={cfg.model || ""} onChange={(e) => set("model", e.target.value)} className="h-9" placeholder="gpt-4o" />
            </div>
          )}
          {cfg.provider === "openai" && (
            <div>
              <label className="mb-1 block text-[11px] font-700 text-slate-600">Clé API OpenAI {cfg.has_openai_key && "(déjà enregistrée)"}</label>
              <Input data-testid="ai-openai-key" type="password" value={cfg._openai_key || ""} onChange={(e) => set("_openai_key", e.target.value)} className="h-9" placeholder={cfg.has_openai_key ? "•••••• (laisser vide pour conserver)" : "sk-..."} />
            </div>
          )}
          {cfg.provider === "azure" && (
            <>
              <div><label className="mb-1 block text-[11px] font-700 text-slate-600">Endpoint Azure</label><Input data-testid="ai-azure-endpoint" value={cfg.azure_endpoint || ""} onChange={(e) => set("azure_endpoint", e.target.value)} className="h-9" placeholder="https://xxx.openai.azure.com" /></div>
              <div><label className="mb-1 block text-[11px] font-700 text-slate-600">Nom du déploiement</label><Input data-testid="ai-azure-deployment" value={cfg.azure_deployment || ""} onChange={(e) => set("azure_deployment", e.target.value)} className="h-9" placeholder="mon-deploiement-gpt4o" /></div>
              <div><label className="mb-1 block text-[11px] font-700 text-slate-600">Version API</label><Input value={cfg.azure_api_version || ""} onChange={(e) => set("azure_api_version", e.target.value)} className="h-9" placeholder="2024-08-01-preview" /></div>
              <div><label className="mb-1 block text-[11px] font-700 text-slate-600">Clé API Azure {cfg.has_azure_key && "(déjà enregistrée)"}</label><Input data-testid="ai-azure-key" type="password" value={cfg._azure_key || ""} onChange={(e) => set("_azure_key", e.target.value)} className="h-9" placeholder={cfg.has_azure_key ? "•••••• (laisser vide pour conserver)" : "clé"} /></div>
            </>
          )}
          <div className="grid grid-cols-3 gap-2 border-t border-slate-200 pt-3">
            <div><label className="mb-1 block text-[10px] font-700 text-slate-500">Seuil écart ($)</label><Input type="number" value={cfg.variance_threshold_amount} onChange={(e) => set("variance_threshold_amount", e.target.value)} className="h-8" /></div>
            <div><label className="mb-1 block text-[10px] font-700 text-slate-500">Seuil écart (%)</label><Input type="number" value={cfg.variance_threshold_pct} onChange={(e) => set("variance_threshold_pct", e.target.value)} className="h-8" /></div>
            <div><label className="mb-1 block text-[10px] font-700 text-slate-500">Sensibilité anomalies (z)</label><Input type="number" step="0.1" value={cfg.anomaly_sensitivity} onChange={(e) => set("anomaly_sensitivity", e.target.value)} className="h-8" /></div>
          </div>
        </div>
        <DialogFooter className="gap-2">
          {(cfg.has_openai_key || cfg.has_azure_key) && <Button variant="outline" data-testid="ai-clear-keys" onClick={clearKeys} className="text-red-600">Effacer les clés</Button>}
          <Button data-testid="ai-config-save" onClick={save} disabled={saving} className="bg-[#063044] hover:bg-[#063044]/90">{saving ? "…" : "Enregistrer"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

const VARIANCE_SCENARIOS = [
  { id: "ca", label: "Budget CA" },
  { id: "rev1", label: "Budget Rév-1" },
  { id: "rev2", label: "Budget Rév-2" },
];
const LS_SCENARIO_KEY = "acct.ai.variance.scenario";

export function VarianceCard({ year, month }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [openPoste, setOpenPoste] = useState(null);
  const [avail, setAvail] = useState(null);
  const [scenario, setScenario] = useState(() => localStorage.getItem(LS_SCENARIO_KEY) || "");

  useEffect(() => {
    setData(null); setOpenPoste(null); setAvail(null);
    api.acctAiVarianceScenarios({ year, month }).then((r) => setAvail(r.scenarios || {})).catch(() => setAvail({}));
  }, [year, month]);

  const gen = async (scen) => {
    if (!scen) return;
    setLoading(true); setOpenPoste(null);
    try { setData(await api.acctAiVariance({ year, month, scenario: scen })); }
    catch (e) { toast.error(e.response?.data?.detail || "Erreur IA"); }
    finally { setLoading(false); }
  };
  const selectScenario = (scen) => {
    if (loading || (avail && avail[scen] === false)) return;
    setScenario(scen);
    localStorage.setItem(LS_SCENARIO_KEY, scen);
    if (data) gen(scen); // changer de scénario régénère une analyse déjà présente
  };
  const detail = data?.detail || {};
  const postes = Object.keys(detail);
  return (
    <div className="card p-5" data-testid="ai-variance-card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-700 text-slate-700"><FileText size={15} className="text-[#0E9488]" /> Analyse de variance (IA)</h3>
        <Button size="sm" onClick={() => gen(scenario)} disabled={loading || !scenario} data-testid="ai-variance-btn" className="bg-[#063044] hover:bg-[#063044]/90">{loading ? "Analyse…" : "Générer"}</Button>
      </div>
      <div className="mb-3 flex flex-wrap items-center gap-2" data-testid="ai-variance-scenarios">
        <span className="text-[11px] font-700 uppercase tracking-wider text-slate-400">Scénario budgétaire :</span>
        {VARIANCE_SCENARIOS.map((s) => {
          const hasData = avail ? avail[s.id] !== false : true;
          const active = scenario === s.id;
          return (
            <button key={s.id} onClick={() => selectScenario(s.id)} disabled={!hasData || loading}
              title={!hasData ? "Aucune donnée pour ce scénario sur cette période" : undefined}
              data-testid={`ai-variance-scenario-${s.id}`}
              className={`rounded-full border px-3 py-1 text-xs font-600 transition-colors ${active ? "border-[#063044] bg-[#063044] text-white" : "border-slate-300 bg-white text-slate-600 hover:border-[#0E9488] hover:text-[#0E9488]"} ${(!hasData || loading) ? "cursor-not-allowed opacity-40 hover:border-slate-300 hover:text-slate-600" : ""}`}>
              {s.label}
            </button>
          );
        })}
      </div>
      {!scenario ? <p className="text-xs text-slate-400" data-testid="ai-variance-hint">Choisissez un scénario budgétaire ci-dessus puis cliquez « Générer » pour commenter les écarts réel vs budget les plus significatifs.</p>
        : !data ? <p className="text-xs text-slate-400">Cliquez « Générer » pour analyser les écarts réel vs {VARIANCE_SCENARIOS.find((s) => s.id === scenario)?.label} de la période.</p>
        : data.available === false ? <p className="text-xs text-amber-600" data-testid="ai-variance-unavailable">{data.reason || "Fonctionnalité IA non configurée."}</p>
        : data.empty ? <p className="text-xs text-slate-500">Aucun écart au-delà des seuils configurés pour cette période.</p>
        : (
          <>
            <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700" data-testid="ai-variance-text">{data.commentary}</p>
            {postes.length > 0 && (
              <div className="mt-4 space-y-2 border-t border-slate-100 pt-3" data-testid="ai-variance-detail">
                <p className="text-[11px] font-700 uppercase tracking-wider text-slate-400">Transactions détaillées (grand livre)</p>
                {postes.map((poste) => {
                  const d = detail[poste];
                  const isOpen = openPoste === poste;
                  const nOut = d.mode === "detail" ? (d.transactions || []).filter((t) => t.inhabituelle).length : 0;
                  return (
                    <div key={poste} className="rounded-lg border border-slate-200" data-testid={`ai-variance-detail-${poste}`}>
                      <button onClick={() => setOpenPoste(isOpen ? null : poste)} data-testid={`ai-variance-toggle-${poste}`}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left hover:bg-slate-50">
                        <span className="flex items-center gap-2 text-sm font-600 text-slate-700">
                          {isOpen ? <ChevronDown size={15} /> : <ChevronRight size={15} />} {poste}
                        </span>
                        <span className="flex items-center gap-2 text-[11px]">
                          {nOut > 0 && <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 font-700 text-[#B45309]"><AlertTriangle size={11} /> {nOut} inhabituelle{nOut > 1 ? "s" : ""}</span>}
                          <span className="text-slate-400">{d.n_transactions} txn</span>
                        </span>
                      </button>
                      {isOpen && (
                        <div className="overflow-x-auto border-t border-slate-100">
                          {d.mode === "resume" ? (
                            <>
                              <p className="px-3 py-2 text-[11px] text-slate-500">Résumé par description ({d.n_transactions} transactions)</p>
                              <table className="w-full text-sm">
                                <thead><tr className="border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-400"><th className="px-3 py-1.5 text-left font-600">Description</th><th className="px-3 py-1.5 text-right font-600">Nb</th><th className="px-3 py-1.5 text-right font-600">Total</th></tr></thead>
                                <tbody>{(d.groupes || []).map((g, i) => (<tr key={i} className="border-b border-slate-100"><td className="px-3 py-1.5 text-slate-700">{g.description}</td><td className="px-3 py-1.5 text-right font-mono-data text-slate-500">{g.count}</td><td className="px-3 py-1.5 text-right font-mono-data">{money(g.total)}</td></tr>))}</tbody>
                              </table>
                            </>
                          ) : (
                            <table className="w-full text-sm">
                              <thead><tr className="border-b border-slate-200 text-[10px] uppercase tracking-wider text-slate-400"><th className="px-3 py-1.5 text-left font-600">Date</th><th className="px-3 py-1.5 text-left font-600">Description</th><th className="px-3 py-1.5 text-right font-600">Montant</th></tr></thead>
                              <tbody>
                                {(d.transactions || []).map((t, i) => (
                                  <tr key={i} className={`border-b border-slate-100 ${t.inhabituelle ? "bg-amber-50" : ""}`} data-testid={`ai-variance-txn-${poste}-${i}`}>
                                    <td className="px-3 py-1.5 font-mono-data text-slate-500">{t.date}</td>
                                    <td className="px-3 py-1.5 text-slate-700">{t.inhabituelle && <AlertTriangle size={11} className="mr-1 inline text-[#B45309]" />}{t.description}</td>
                                    <td className="px-3 py-1.5 text-right font-mono-data" style={{ color: (t.montant || 0) < 0 ? "#DC2626" : "#0E9488" }}>{money(t.montant)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
    </div>
  );
}

export function AiChatPanel({ year, month }) {
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [sid] = useState(() => `chat-${Date.now()}`);
  const ask = async () => {
    if (!q.trim()) return;
    const question = q.trim(); setQ(""); setMsgs((m) => [...m, { role: "user", text: question }]); setLoading(true);
    try {
      const r = await api.acctAiChat({ session_id: sid, question, year, month });
      setMsgs((m) => [...m, { role: "ai", text: r.available === false ? (r.reason || "Fonctionnalité IA non configurée.") : r.answer }]);
    } catch (e) { setMsgs((m) => [...m, { role: "ai", text: e.response?.data?.detail || "Erreur IA" }]); }
    finally { setLoading(false); }
  };
  return (
    <div className="card flex flex-col p-5" data-testid="ai-chat-card">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-700 text-slate-700"><Info size={15} className="text-[#0E9488]" /> Questions sur les données (IA)</h3>
      <div className="mb-3 max-h-64 min-h-[80px] space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3" data-testid="ai-chat-messages">
        {msgs.length === 0 && <p className="text-xs text-slate-400">Ex. « Quelle a été l'évolution des charges sur les 6 derniers mois ? »</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`text-sm ${m.role === "user" ? "text-right" : ""}`}>
            <span className={`inline-block rounded-lg px-3 py-1.5 ${m.role === "user" ? "bg-[#063044] text-white" : "bg-white text-slate-700 shadow-sm"}`}>{m.text}</span>
          </div>
        ))}
        {loading && <p className="text-xs text-slate-400">L'assistant réfléchit…</p>}
      </div>
      <div className="flex gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} data-testid="ai-chat-input" className="h-9" placeholder="Poser une question…" />
        <Button onClick={ask} disabled={loading} data-testid="ai-chat-send" className="h-9 bg-[#063044] hover:bg-[#063044]/90">Envoyer</Button>
      </div>
    </div>
  );
}

export function AnomaliesCard({ periods }) {
  const [period, setPeriod] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => { if (periods.length && !periods.some((p) => p.id === period)) setPeriod(periods[0].id); }, [periods, period]);
  const detect = async () => {
    if (!period) return;
    const [y, m] = period.split("-").map(Number);
    setLoading(true);
    try { setData(await api.acctAiAnomalies({ year: y, month: m })); }
    catch (e) { toast.error(e.response?.data?.detail || "Erreur IA"); }
    finally { setLoading(false); }
  };
  if (!periods.length) return null;
  return (
    <div className="card p-5" data-testid="acct-anomalies-card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-700 text-slate-700"><Sparkles size={15} className="text-[#0E9488]" /> Détection d'anomalies (IA)</h3>
        <div className="flex items-center gap-2">
          <PeriodSelect periods={periods} value={period} onChange={setPeriod} testId="acct-anomalies" />
          <Button size="sm" onClick={detect} disabled={loading} data-testid="acct-anomalies-btn" className="bg-[#063044] hover:bg-[#063044]/90">{loading ? "Analyse…" : "Détecter"}</Button>
        </div>
      </div>
      {!data ? <p className="text-xs text-slate-400">Repère les comptes dont le solde s'écarte fortement de leur moyenne des 6 derniers mois. Signalements non bloquants.</p>
        : data.available === false ? <p className="text-xs text-amber-600" data-testid="acct-anomalies-unavailable">{data.reason || "Fonctionnalité IA non configurée."}</p>
        : (data.anomalies || []).length === 0 ? <p className="text-xs text-slate-500" data-testid="acct-anomalies-empty">Aucune anomalie détectée pour cette période.</p>
        : (
          <div className="space-y-3" data-testid="acct-anomalies-result">
            {data.summary && <p className="whitespace-pre-line rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-700" data-testid="acct-anomalies-summary">{data.summary}</p>}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
                  <th className="px-3 py-2 text-left font-600">Compte</th><th className="px-3 py-2 text-right font-600">Solde</th>
                  <th className="px-3 py-2 text-right font-600">Moyenne</th><th className="px-3 py-2 text-right font-600">Écart</th><th className="px-3 py-2 text-right font-600">z</th>
                </tr></thead>
                <tbody>
                  {data.anomalies.map((an) => (
                    <tr key={an.account} className="border-b border-slate-100" data-testid={`acct-anomaly-${an.account}`}>
                      <td className="px-3 py-2"><span className="font-mono-data text-slate-500">{an.account}</span> <span className="text-slate-700">{an.name}</span></td>
                      <td className="px-3 py-2 text-right font-mono-data">{money(an.value)}</td>
                      <td className="px-3 py-2 text-right font-mono-data text-slate-500">{money(an.moyenne)}</td>
                      <td className="px-3 py-2 text-right font-mono-data" style={{ color: an.ecart < 0 ? "#DC2626" : "#0E9488" }}>{money(an.ecart)}</td>
                      <td className="px-3 py-2 text-right font-mono-data font-700 text-[#B45309]">{an.z}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
    </div>
  );
}
