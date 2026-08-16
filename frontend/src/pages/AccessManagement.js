import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { UserPlus, Search, Loader2, ChevronRight, ChevronDown, Send, RefreshCw, XCircle, HelpCircle, CheckCircle2 } from "lucide-react";

const MODULE_LABEL = { REPORTING: "Reporting", ACCOUNTING: "Comptabilité", FIXED_ASSETS: "Immobilisations", CONSOLIDATION: "Consolidation" };
const LEVELS = ["none", "read", "contribute", "manage"];
const LEVEL_LABEL = (code, lvl) => ({ none: "Aucun", read: "Lecture", contribute: code === "ACCOUNTING" ? "Saisie" : "Contribution", manage: "Gestion" }[lvl] || lvl);
const STATUS_LABEL = { active: "Actif", suspended: "Suspendu", inactive: "Accès retiré", pending: "Invitation en attente", accepted: "Actif", expired: "Invitation expirée", revoked: "Invitation révoquée", pending_verification: "En attente d'activation", disabled: "Désactivé" };
const STATUS_COLOR = { active: "bg-emerald-100 text-emerald-700", accepted: "bg-emerald-100 text-emerald-700", suspended: "bg-amber-100 text-amber-700", disabled: "bg-red-100 text-red-700", inactive: "bg-slate-100 text-slate-600", pending: "bg-blue-100 text-blue-700", expired: "bg-amber-100 text-amber-700", revoked: "bg-slate-100 text-slate-500" };

const PERM_GROUPS = {
  ACCOUNTING: [
    { title: "Comptabilisation", perms: [["accounting.entry_post", "Comptabiliser les écritures"], ["accounting.entry_reverse", "Extourner une écriture"], ["accounting.customer_invoice_post", "Comptabiliser les factures clients"], ["accounting.supplier_invoice_post", "Comptabiliser les factures fournisseurs"]] },
    { title: "Validation", perms: [["accounting.po_approve", "Approuver les PO"], ["accounting.reconciliation_approve", "Valider les réconciliations"]] },
    { title: "Administration comptable", perms: [["accounting.chart_manage", "Gérer le plan comptable"], ["accounting.period_close", "Clôturer une période"], ["accounting.period_reopen", "Rouvrir une période"]] },
  ],
  REPORTING: [{ title: "Rapports", perms: [["reporting.report_finalize", "Finaliser les rapports"], ["reporting.external_send", "Envoyer des rapports externes"], ["reporting.template_manage", "Gérer les modèles"]] }],
  FIXED_ASSETS: [{ title: "Immobilisations", perms: [["fixed_assets.disposal_authorize", "Autoriser les cessions"], ["fixed_assets.depreciation_approve", "Approuver l'amortissement"]] }],
  CONSOLIDATION: [{ title: "Consolidation", perms: [["consolidation.approve", "Approuver la consolidation"], ["consolidation.close", "Clôturer la consolidation"]] }],
};

// UX-only presets (NOT backend roles): pre-select module levels + permissions.
const PRESETS = {
  lecture: { label: "Lecture seule", levels: { REPORTING: "read", ACCOUNTING: "read", FIXED_ASSETS: "read", CONSOLIDATION: "read" }, perms: [] },
  junior: { label: "Junior", levels: { ACCOUNTING: "contribute", REPORTING: "read" }, perms: ["accounting.customer_invoice_post"] },
  comptable: { label: "Comptable", levels: { ACCOUNTING: "contribute", REPORTING: "read" }, perms: ["accounting.entry_post", "accounting.customer_invoice_post", "accounting.supplier_invoice_post"] },
  resp_fin: { label: "Responsable financier", levels: { ACCOUNTING: "manage", REPORTING: "manage" }, perms: ["accounting.entry_post", "accounting.po_approve", "accounting.reconciliation_approve", "accounting.period_close", "reporting.report_finalize"] },
  resp_rep: { label: "Responsable reporting", levels: { REPORTING: "manage" }, perms: ["reporting.report_finalize", "reporting.external_send", "reporting.template_manage"] },
  resp_cons: { label: "Responsable consolidation", levels: { CONSOLIDATION: "manage" }, perms: ["consolidation.approve", "consolidation.close"] },
  custom: { label: "Personnalisé", levels: {}, perms: [] },
};

function Badge2({ status }) {
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLOR[status] || "bg-slate-100 text-slate-600"}`} data-testid={`status-${status}`}>{STATUS_LABEL[status] || status}</span>;
}

function ModuleAccessEditor({ companyId, entitledCodes, grant, onLevel, onPerm }) {
  const [open, setOpen] = useState({});
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {["REPORTING", "ACCOUNTING", "FIXED_ASSETS", "CONSOLIDATION"].map((code) => {
        const entitled = entitledCodes.includes(code);
        const level = grant.levels[code] || "none";
        const perms = grant.perms || [];
        return (
          <div key={code} className={`rounded-lg border p-3 ${entitled ? "border-slate-200" : "border-slate-100 opacity-50"}`} data-testid={`wiz-module-${companyId}-${code}`}>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-[#0F172A]">{MODULE_LABEL[code]}</span>
              {!entitled && <span className="text-[11px] text-slate-400">Non souscrit</span>}
            </div>
            <Select value={level} onValueChange={(v) => onLevel(code, v)} disabled={!entitled}>
              <SelectTrigger className="mt-2 h-9 text-xs" data-testid={`wiz-level-${companyId}-${code}`}><SelectValue /></SelectTrigger>
              <SelectContent>{LEVELS.map((l) => <SelectItem key={l} value={l}>{LEVEL_LABEL(code, l)}</SelectItem>)}</SelectContent>
            </Select>
            {entitled && level !== "none" && PERM_GROUPS[code] && (
              <div className="mt-2">
                <button type="button" onClick={() => setOpen((o) => ({ ...o, [code]: !o[code] }))} className="flex items-center gap-1 text-[11px] font-semibold text-slate-500" data-testid={`wiz-perms-toggle-${companyId}-${code}`}>
                  {open[code] ? <ChevronDown size={13} /> : <ChevronRight size={13} />} Autorisations sensibles
                </button>
                {open[code] && PERM_GROUPS[code].map((g) => (
                  <div key={g.title} className="ml-1 mt-1">
                    <p className="text-[10px] uppercase tracking-wide text-slate-400">{g.title}</p>
                    {g.perms.map(([pc, lbl]) => (
                      <label key={pc} className="flex items-center gap-2 py-0.5 text-xs text-slate-600">
                        <input type="checkbox" checked={perms.includes(pc)} onChange={(e) => onPerm(pc, e.target.checked)} data-testid={`wiz-perm-${companyId}-${pc}`} /> {lbl}
                      </label>
                    ))}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function InviteWizard({ open, onClose, companies, entitledCodes, onDone }) {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState(""); const [name, setName] = useState("");
  const [selCompanies, setSelCompanies] = useState([]);
  const [grants, setGrants] = useState({}); // companyId -> {role, levels:{}, perms:[]}
  const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setStep(1); setEmail(""); setName(""); setSelCompanies([]); setGrants({}); } }, [open]);

  const toggleCompany = (cid) => setSelCompanies((s) => {
    const has = s.includes(cid);
    if (has) { const g = { ...grants }; delete g[cid]; setGrants(g); return s.filter((x) => x !== cid); }
    setGrants((g) => ({ ...g, [cid]: { role: "user", levels: {}, perms: [] } }));
    return [...s, cid];
  });
  const applyPreset = (cid, key) => {
    const p = PRESETS[key]; if (!p) return;
    setGrants((g) => ({ ...g, [cid]: { ...g[cid], levels: { ...p.levels }, perms: [...p.perms] } }));
  };
  const setLevel = (cid, code, v) => setGrants((g) => ({ ...g, [cid]: { ...g[cid], levels: { ...g[cid].levels, [code]: v } } }));
  const setPerm = (cid, pc, on) => setGrants((g) => {
    const cur = g[cid].perms || [];
    return { ...g, [cid]: { ...g[cid], perms: on ? [...cur, pc] : cur.filter((x) => x !== pc) } };
  });

  const send = async () => {
    setBusy(true);
    try {
      const access = [], permissions = [], comps = [];
      selCompanies.forEach((cid) => {
        const g = grants[cid];
        comps.push({ company_id: cid, role: g.role || "user" });
        Object.entries(g.levels || {}).forEach(([code, lvl]) => { if (lvl && lvl !== "none") access.push({ company_id: cid, module_code: code, access_level: lvl }); });
        (g.perms || []).forEach((pc) => permissions.push({ company_id: cid, permission_code: pc }));
      });
      await api.createInvitation({ email, name, companies: comps, access, permissions });
      toast.success(`Invitation envoyée à ${email}.`);
      onDone(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Échec de l'invitation."); }
    finally { setBusy(false); }
  };

  const cname = (cid) => companies.find((c) => c.id === cid)?.name || cid;
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" aria-describedby={undefined} data-testid="invite-wizard">
        <DialogHeader><DialogTitle>Inviter un utilisateur — étape {step}/4</DialogTitle></DialogHeader>

        {step === 1 && (
          <div className="space-y-4">
            <div><label className="overline text-slate-500">Adresse courriel</label>
              <Input data-testid="invite-email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="personne@societe.com" className="mt-1 h-11" /></div>
            <div><label className="overline text-slate-500">Nom (optionnel)</label>
              <Input data-testid="invite-name" value={name} onChange={(e) => setName(e.target.value)} className="mt-1 h-11" /></div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-2">
            <p className="text-sm text-slate-500">À quelle(s) société(s) cette personne doit-elle accéder ?</p>
            {companies.map((c) => (
              <label key={c.id} className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 text-sm" data-testid={`invite-company-${c.id}`}>
                <input type="checkbox" checked={selCompanies.includes(c.id)} onChange={() => toggleCompany(c.id)} data-testid={`invite-company-check-${c.id}`} />
                {c.name}
              </label>
            ))}
            {companies.length === 0 && <p className="text-sm text-slate-400">Aucune société disponible.</p>}
          </div>
        )}

        {step === 3 && (
          <div className="space-y-5">
            {selCompanies.length === 0 && <p className="text-sm text-amber-600">Sélectionnez au moins une société à l'étape précédente.</p>}
            {selCompanies.map((cid) => (
              <div key={cid} className="rounded-xl border border-slate-200 p-4" data-testid={`invite-access-${cid}`}>
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm font-semibold text-[#063044]">{cname(cid)}</span>
                  <Select onValueChange={(v) => applyPreset(cid, v)}>
                    <SelectTrigger className="h-9 w-52 text-xs" data-testid={`invite-preset-${cid}`}><SelectValue placeholder="Profil préréglé…" /></SelectTrigger>
                    <SelectContent>{Object.entries(PRESETS).map(([k, p]) => <SelectItem key={k} value={k}>{p.label}</SelectItem>)}</SelectContent>
                  </Select>
                </div>
                <ModuleAccessEditor companyId={cid} entitledCodes={entitledCodes}
                  grant={grants[cid] || { levels: {}, perms: [] }}
                  onLevel={(code, v) => setLevel(cid, code, v)} onPerm={(pc, on) => setPerm(cid, pc, on)} />
                <p className="mt-3 text-[11px] text-slate-400">Les autorisations sensibles restent séparées du niveau « Gestion ».</p>
              </div>
            ))}
          </div>
        )}

        {step === 4 && (
          <div className="space-y-3 text-sm" data-testid="invite-summary">
            <p className="text-slate-600"><b>{email}</b> recevra une invitation à usage unique et choisira son propre mot de passe.</p>
            {selCompanies.map((cid) => {
              const g = grants[cid] || { levels: {}, perms: [] };
              const mods = Object.entries(g.levels).filter(([, l]) => l && l !== "none");
              return (
                <div key={cid} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <div className="font-semibold text-[#063044]">{cname(cid)}</div>
                  {mods.length === 0 ? <div className="text-xs text-slate-400">Aucun module</div> :
                    mods.map(([code, lvl]) => <div key={code} className="text-slate-600">{MODULE_LABEL[code]} — {LEVEL_LABEL(code, lvl)}</div>)}
                  {(g.perms || []).length > 0 && <div className="mt-1 text-xs text-slate-500">+ {g.perms.length} autorisation(s) sensible(s)</div>}
                </div>
              );
            })}
            <p className="text-[11px] text-slate-400">Aucune autorité financière n'est accordée sans permission explicite.</p>
          </div>
        )}

        <DialogFooter>
          {step > 1 && <Button variant="outline" onClick={() => setStep(step - 1)} data-testid="invite-back">Retour</Button>}
          {step < 4 && <Button onClick={() => setStep(step + 1)} disabled={(step === 1 && !email) || (step === 2 && selCompanies.length === 0)} data-testid="invite-next" className="bg-[#063044] text-white">Continuer</Button>}
          {step === 4 && <Button onClick={send} disabled={busy || selCompanies.length === 0} data-testid="invite-send" className="gap-2 bg-[#22C55E] text-white">{busy ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />} Envoyer l'invitation</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function WhyAccess({ cid, uid, code }) {
  const [data, setData] = useState(null); const [open, setOpen] = useState(false);
  const load = () => { setOpen(true); api.explainAccess(cid, uid, { module: code }).then(setData).catch(() => setData(null)); };
  return (
    <>
      <button type="button" onClick={load} className="mt-1 flex items-center gap-1 text-[11px] text-[#15AF97]" data-testid={`why-${cid}-${code}`}><HelpCircle size={12} /> Pourquoi cet accès ?</button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md" aria-describedby={undefined} data-testid="why-dialog">
          <DialogHeader><DialogTitle>{MODULE_LABEL[code]}</DialogTitle></DialogHeader>
          {!data ? <Loader2 className="animate-spin" size={16} /> : (
            <div className="space-y-2 text-sm">
              <div className={`font-semibold ${data.allowed ? "text-emerald-600" : "text-amber-600"}`}>{data.allowed ? "Accès autorisé" : "Accès refusé"}</div>
              <p className="text-slate-600">{data.reason}</p>
              {(data.factors || []).map((f, i) => <div key={i} className="flex items-center gap-2 text-xs text-slate-500"><CheckCircle2 size={13} className="text-emerald-500" /> {f.check} : {String(f.value)}</div>)}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

function UserDetail({ uid, open, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const load = useCallback(() => { if (uid) api.getAccessUser(uid).then(setData).catch(() => setData(null)); }, [uid]);
  useEffect(() => { if (open) load(); }, [open, load]);
  if (!open) return null;
  const identity = data?.identity;
  const setLevel = async (cid, code, level) => { try { await api.setModuleAccess(cid, uid, code, level); toast.success("Accès mis à jour."); load(); onChanged?.(); } catch (e) { toast.error(e.response?.data?.detail || "Erreur."); } };
  const togglePerm = async (cid, code, granted) => { try { await api.setUserPermission(cid, uid, code, granted); toast.success(granted ? "Autorisation accordée." : "Autorisation retirée."); load(); } catch (e) { toast.error(e.response?.data?.detail || "Erreur."); } };
  const toggleSuspend = async () => {
    const next = identity?.status === "active" ? "suspended" : "active";
    if (next === "suspended" && !window.confirm("Suspendre ce compte ? L'utilisateur perdra immédiatement l'accès.")) return;
    try { await api.setIdentityStatus(uid, next); toast.success(next === "active" ? "Accès rétabli." : "Compte suspendu."); load(); onChanged?.(); } catch (e) { toast.error(e.response?.data?.detail || "Erreur."); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" aria-describedby={undefined} data-testid="user-detail">
        {!data ? <div className="flex items-center gap-2 p-6 text-slate-500"><Loader2 className="animate-spin" size={16} /> Chargement…</div> : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-3">{identity?.name || identity?.email} <Badge2 status={identity?.status} /></DialogTitle>
              <p className="text-sm text-slate-500">{identity?.email}</p>
            </DialogHeader>
            {(data.companies || []).length === 0 && <p className="text-sm text-slate-500">Aucune société attribuée pour l'instant.</p>}
            {(data.companies || []).map((c) => (
              <div key={c.company_id} className="mt-2 rounded-xl border border-slate-200 p-4" data-testid={`company-block-${c.company_id}`}>
                <div className="mb-3 text-sm font-semibold text-[#063044]">Société {c.company_id.slice(0, 8)} · {c.role}</div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {(c.modules || []).map((m) => (
                    <div key={m.module_code} className={`rounded-lg border p-3 ${m.entitled ? "border-slate-200" : "border-slate-100 opacity-50"}`} data-testid={`module-card-${c.company_id}-${m.module_code}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-[#0F172A]">{MODULE_LABEL[m.module_code]}</span>
                        <span className="text-xs text-slate-500" data-testid={`eff-${c.company_id}-${m.module_code}`}>{LEVEL_LABEL(m.module_code, m.effective_level)}</span>
                      </div>
                      <Select value={m.assigned_level} onValueChange={(v) => setLevel(c.company_id, m.module_code, v)} disabled={!m.entitled}>
                        <SelectTrigger className="mt-2 h-9 text-xs" data-testid={`level-${c.company_id}-${m.module_code}`}><SelectValue /></SelectTrigger>
                        <SelectContent>{LEVELS.map((l) => <SelectItem key={l} value={l}>{LEVEL_LABEL(m.module_code, l)}</SelectItem>)}</SelectContent>
                      </Select>
                      {!m.entitled && <p className="mt-1 text-[11px] text-slate-400">Module non souscrit</p>}
                      {m.entitled && <WhyAccess cid={c.company_id} uid={uid} code={m.module_code} />}
                      {m.assigned_level !== "none" && PERM_GROUPS[m.module_code] && (
                        <div className="mt-2 space-y-1">
                          {PERM_GROUPS[m.module_code].map((g) => g.perms.map(([code, label]) => {
                            const on = (m.sensitive_permissions || []).includes(code);
                            return (<label key={code} className="flex items-center gap-2 py-0.5 text-xs text-slate-600"><input type="checkbox" checked={on} onChange={(e) => togglePerm(c.company_id, code, e.target.checked)} data-testid={`perm-${c.company_id}-${code}`} /> {label}</label>);
                          }))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4">
              <p className="text-xs text-slate-400">Les autorisations sensibles sont attribuées séparément.</p>
              <Button variant={identity?.status === "active" ? "destructive" : "default"} onClick={toggleSuspend} data-testid="toggle-suspend">{identity?.status === "active" ? "Suspendre le compte" : "Rétablir l'accès"}</Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function ReplaceAdminDialog({ companyId, companyName, adminHist, open, onClose, onDone }) {
  const [step, setStep] = useState(1); const [email, setEmail] = useState(""); const [busy, setBusy] = useState(false); const [link, setLink] = useState("");
  useEffect(() => { if (open) { setStep(1); setEmail(""); setLink(""); } }, [open]);
  const current = (adminHist?.current_admins || []).filter((a) => a && a.membership_id)[0];
  const submit = async () => {
    if (!current) { toast.error("Aucun administrateur actif à remplacer."); return; }
    setBusy(true);
    try {
      const out = await api.replaceCompanyAdmin(companyId, { old_membership_id: current.membership_id, new_email: email });
      setLink(out.activation_link || ""); setStep(3);
      toast.success("L'administrateur précédent a été désactivé et le nouvel administrateur a reçu son invitation.");
    } catch (e) { toast.error(e.response?.data?.detail || "Erreur."); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md" aria-describedby={undefined} data-testid="replace-admin-dialog">
        <DialogHeader><DialogTitle>Remplacer l'administrateur — {companyName}</DialogTitle></DialogHeader>
        {step === 1 && (
          <div className="space-y-3 text-sm">
            <p className="rounded-lg bg-amber-50 p-3 text-amber-800">⚠️ L'ancien administrateur perdra <b>immédiatement</b> son accès à cette société et ses sessions seront révoquées.</p>
            <p className="text-slate-600">Administrateur actuel : <b>{current?.email || "aucun"}</b></p>
            <p className="text-xs text-slate-400">Meelora ne définit ni n'affiche jamais de mot de passe. Le nouvel administrateur choisira le sien via un lien d'activation à usage unique.</p>
            <DialogFooter><Button onClick={() => setStep(2)} disabled={!current} data-testid="replace-continue" className="bg-[#063044] text-white">Continuer</Button></DialogFooter>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-3">
            <label className="overline text-slate-500">Courriel du nouvel administrateur</label>
            <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="nouvel.admin@societe.com" className="h-11" data-testid="replace-email" />
            <DialogFooter>
              <Button variant="outline" onClick={() => setStep(1)}>Retour</Button>
              <Button onClick={submit} disabled={busy || !email} data-testid="replace-confirm" className="gap-2 bg-red-600 text-white">{busy ? <Loader2 className="animate-spin" size={16} /> : null} Confirmer le remplacement</Button>
            </DialogFooter>
          </div>
        )}
        {step === 3 && (
          <div className="space-y-3 text-sm" data-testid="replace-done">
            <div className="flex items-center gap-2 text-emerald-600"><CheckCircle2 size={18} /> Remplacement effectué</div>
            <p className="text-slate-600">Le nouvel administrateur a reçu son lien d'activation. L'ancien administrateur n'a plus accès.</p>
            <DialogFooter><Button onClick={onDone} className="bg-[#063044] text-white">Terminer</Button></DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function AccessManagement() {
  const [users, setUsers] = useState([]); const [invitations, setInvitations] = useState([]);
  const [tab, setTab] = useState("users"); const [q, setQ] = useState(""); const [invFilter, setInvFilter] = useState("pending");
  const [companies, setCompanies] = useState([]); const [entitledCodes, setEntitledCodes] = useState([]);
  const [invite, setInvite] = useState(false); const [detailUid, setDetailUid] = useState(null); const [loading, setLoading] = useState(true);
  const [adminHist, setAdminHist] = useState({}); const [replaceCid, setReplaceCid] = useState(null);
  const load = useCallback(() => {
    setLoading(true);
    Promise.all([
      api.listAccessUsers().catch(() => ({ users: [] })),
      api.listInvitations().catch(() => ({ invitations: [] })),
      api.getCompanies().catch(() => []),
      api.wsEntitlements().catch(() => ({ entitlements: [] })),
    ]).then(([u, i, c, e]) => {
      setUsers(u.users || []); setInvitations(i.invitations || []); setCompanies(c || []);
      setEntitledCodes((e.entitlements || []).filter((x) => ["active", "trial"].includes(x.status)).map((x) => x.module_code));
    }).finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (tab === "admins" && companies.length) {
      companies.forEach((c) => api.companyAdminHistory(c.id).then((h) => setAdminHist((s) => ({ ...s, [c.id]: h }))).catch(() => {}));
    }
  }, [tab, companies]);
  const pending = invitations.filter((i) => i.status === "pending").length;
  const expired = invitations.filter((i) => i.status === "expired").length;
  const activeUsers = users.filter((u) => u.identity?.status === "active").length;
  const filtered = users.filter((u) => !q || (u.identity?.email || "").toLowerCase().includes(q.toLowerCase()) || (u.identity?.name || "").toLowerCase().includes(q.toLowerCase()));
  const invShown = invitations.filter((i) => invFilter === "all" || i.status === invFilter);
  const resend = async (id) => { try { await api.resendInvitation(id); toast.success("Invitation renvoyée."); load(); } catch { toast.error("Erreur."); } };
  const revoke = async (id) => { if (!window.confirm("Révoquer cette invitation ?")) return; try { await api.revokeInvitation(id); toast.success("Invitation révoquée."); load(); } catch { toast.error("Erreur."); } };
  const cname = (cid) => companies.find((c) => c.id === cid)?.name || cid;

  return (
    <div className="space-y-6" data-testid="access-management">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex gap-6 text-sm">
          <div><div className="text-2xl font-light text-[#063044]" data-testid="stat-active-users">{activeUsers}</div><div className="text-slate-500">utilisateurs actifs</div></div>
          <div><div className="text-2xl font-light text-[#063044]" data-testid="stat-pending">{pending}</div><div className="text-slate-500">invitations en attente</div></div>
          {expired > 0 && <div><div className="text-2xl font-light text-amber-600" data-testid="stat-expired">{expired}</div><div className="text-slate-500">expirées</div></div>}
        </div>
        <Button onClick={() => setInvite(true)} className="gap-2 bg-[#22C55E] text-white" data-testid="invite-user-btn"><UserPlus size={16} /> Inviter un utilisateur</Button>
      </div>

      <div className="flex gap-2">
        <button onClick={() => setTab("users")} data-testid="tab-users" className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "users" ? "bg-[#063044] text-white" : "bg-slate-100 text-slate-600"}`}>Utilisateurs</button>
        <button onClick={() => setTab("invitations")} data-testid="tab-invitations" className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "invitations" ? "bg-[#063044] text-white" : "bg-slate-100 text-slate-600"}`}>Invitations</button>
        <button onClick={() => setTab("admins")} data-testid="tab-admins" className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "admins" ? "bg-[#063044] text-white" : "bg-slate-100 text-slate-600"}`}>Administrateurs</button>
      </div>

      {loading ? <div className="flex items-center gap-2 text-slate-500"><Loader2 className="animate-spin" size={16} /> Chargement…</div> : tab === "users" ? (
        <div className="space-y-3">
          <div className="relative max-w-sm"><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher…" className="h-11 pl-9" data-testid="user-search" /></div>
          {filtered.length === 0 ? <p className="text-sm text-slate-500" data-testid="users-empty">Commencez par inviter votre premier collaborateur.</p> :
            filtered.map((u) => (
              <div key={u.identity.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4" data-testid={`user-row-${u.identity.id}`}>
                <div>
                  <div className="flex items-center gap-2 font-medium text-[#0F172A]">{u.identity.name || u.identity.email} <Badge2 status={u.identity.status} /></div>
                  <div className="text-sm text-slate-500">{u.identity.email}</div>
                  <div className="mt-1 text-xs text-slate-400">{(u.company_memberships || []).length} société(s)</div>
                </div>
                <Button variant="outline" onClick={() => setDetailUid(u.identity.id)} className="gap-1" data-testid={`manage-${u.identity.id}`}>Gérer <ChevronRight size={14} /></Button>
              </div>
            ))}
        </div>
      ) : tab === "invitations" ? (
        <div className="space-y-3">
          <div className="flex gap-2" data-testid="inv-filters">
            {[["pending", "En attente"], ["accepted", "Acceptées"], ["expired", "Expirées"], ["revoked", "Révoquées"], ["all", "Toutes"]].map(([k, lbl]) => (
              <button key={k} onClick={() => setInvFilter(k)} data-testid={`inv-filter-${k}`} className={`rounded-full px-3 py-1 text-xs ${invFilter === k ? "bg-[#15AF97] text-white" : "bg-slate-100 text-slate-600"}`}>{lbl}</button>
            ))}
          </div>
          {invShown.length === 0 ? <p className="text-sm text-slate-500" data-testid="invitations-empty">Aucune invitation.</p> :
            invShown.map((i) => (
              <div key={i.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4" data-testid={`invitation-row-${i.id}`}>
                <div>
                  <div className="flex items-center gap-2 font-medium text-[#0F172A]">{i.email} <Badge2 status={i.status} /></div>
                  <div className="text-xs text-slate-400">Expire le {(i.expires_at || "").slice(0, 10)}</div>
                </div>
                {i.status === "pending" && (
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => resend(i.id)} className="gap-1" data-testid={`resend-${i.id}`}><RefreshCw size={13} /> Renvoyer</Button>
                    <Button variant="outline" size="sm" onClick={() => revoke(i.id)} className="gap-1 text-red-600" data-testid={`revoke-${i.id}`}><XCircle size={13} /> Révoquer</Button>
                  </div>
                )}
              </div>
            ))}
        </div>
      ) : (
        <div className="space-y-3" data-testid="admins-tab">
          {companies.map((c) => {
            const h = adminHist[c.id];
            return (
              <div key={c.id} className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`admin-company-${c.id}`}>
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium text-[#0F172A]">{c.name}</div>
                    <div className="text-xs text-slate-500">{(h?.current_admins || []).filter(Boolean).map((a) => a.email).join(", ") || "Aucun administrateur"}</div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => setReplaceCid(c.id)} className="text-red-600" data-testid={`replace-admin-${c.id}`}>Remplacer l'administrateur</Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <InviteWizard open={invite} onClose={() => setInvite(false)} companies={companies} entitledCodes={entitledCodes} onDone={load} />
      <UserDetail uid={detailUid} open={!!detailUid} onClose={() => setDetailUid(null)} onChanged={load} />
      <ReplaceAdminDialog companyId={replaceCid} companyName={cname(replaceCid)} adminHist={adminHist[replaceCid]} open={!!replaceCid} onClose={() => setReplaceCid(null)} onDone={() => { setReplaceCid(null); load(); }} />
    </div>
  );
}
