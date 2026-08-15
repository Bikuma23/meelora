import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "../components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";
import { UserPlus, Search, Loader2, ShieldCheck, ChevronRight, Send, RefreshCw, XCircle, Info } from "lucide-react";

const MODULE_LABEL = { REPORTING: "Reporting", ACCOUNTING: "Comptabilité", FIXED_ASSETS: "Immobilisations", CONSOLIDATION: "Consolidation" };
const LEVELS = ["none", "read", "contribute", "manage"];
const LEVEL_LABEL = (code, lvl) => {
  const map = { none: "Aucun", read: "Lecture", contribute: code === "ACCOUNTING" ? "Saisie" : "Contribution", manage: "Gestion" };
  return map[lvl] || lvl;
};
const STATUS_LABEL = { active: "Actif", suspended: "Suspendu", inactive: "Accès retiré", pending: "Invitation en attente",
  accepted: "Actif", expired: "Invitation expirée", revoked: "Invitation révoquée", pending_verification: "En attente d'activation", disabled: "Désactivé" };
const STATUS_COLOR = { active: "bg-emerald-100 text-emerald-700", accepted: "bg-emerald-100 text-emerald-700",
  suspended: "bg-amber-100 text-amber-700", disabled: "bg-red-100 text-red-700", inactive: "bg-slate-100 text-slate-600",
  pending: "bg-blue-100 text-blue-700", expired: "bg-amber-100 text-amber-700", revoked: "bg-slate-100 text-slate-500" };

// Business-friendly grouped sensitive permissions (subset shown; codes are canonical)
const PERM_GROUPS = {
  ACCOUNTING: [
    { title: "Comptabilisation", perms: [["accounting.entry_post", "Comptabiliser les écritures"], ["accounting.customer_invoice_post", "Comptabiliser les factures clients"], ["accounting.supplier_invoice_post", "Comptabiliser les factures fournisseurs"]] },
    { title: "Validation", perms: [["accounting.po_approve", "Approuver les PO"], ["accounting.reconciliation_approve", "Valider les réconciliations"]] },
    { title: "Administration comptable", perms: [["accounting.chart_manage", "Gérer le plan comptable"], ["accounting.period_close", "Clôturer une période"], ["accounting.period_reopen", "Rouvrir une période"]] },
  ],
  REPORTING: [{ title: "Rapports", perms: [["reporting.report_finalize", "Finaliser les rapports"], ["reporting.external_send", "Envoyer des rapports externes"], ["reporting.template_manage", "Gérer les modèles"]] }],
  FIXED_ASSETS: [{ title: "Immobilisations", perms: [["fixed_assets.disposal_authorize", "Autoriser les cessions"], ["fixed_assets.depreciation_approve", "Approuver l'amortissement"]] }],
  CONSOLIDATION: [{ title: "Consolidation", perms: [["consolidation.approve", "Approuver la consolidation"], ["consolidation.close", "Clôturer la consolidation"]] }],
};

function Badge2({ status }) {
  return <span className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_COLOR[status] || "bg-slate-100 text-slate-600"}`} data-testid={`status-${status}`}>{STATUS_LABEL[status] || status}</span>;
}

function InviteWizard({ open, onClose, companies, onDone }) {
  const [step, setStep] = useState(1);
  const [email, setEmail] = useState(""); const [name, setName] = useState("");
  const [kind, setKind] = useState("company"); const [companyId, setCompanyId] = useState("");
  const [role, setRole] = useState("user"); const [busy, setBusy] = useState(false);
  useEffect(() => { if (open) { setStep(1); setEmail(""); setName(""); setKind("company"); setCompanyId(companies[0]?.id || ""); setRole("user"); } }, [open, companies]);
  const send = async () => {
    setBusy(true);
    try {
      const body = kind === "workspace" ? { email, name, kind: "workspace", role }
        : { email, name, kind: "company", company_id: companyId, membership_type: "company_user", company_role: role };
      await api.createInvitation(body);
      toast.success(`Invitation envoyée à ${email}.`);
      onDone(); onClose();
    } catch (e) { toast.error(e.response?.data?.detail || "Échec de l'invitation."); }
    finally { setBusy(false); }
  };
  const company = companies.find((c) => c.id === companyId);
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-lg" data-testid="invite-wizard">
        <DialogHeader><DialogTitle>Inviter un utilisateur — étape {step}/3</DialogTitle></DialogHeader>
        {step === 1 && (
          <div className="space-y-4">
            <div><label className="overline text-slate-500">Adresse courriel</label>
              <Input data-testid="invite-email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="personne@societe.com" className="mt-1 h-11" /></div>
            <div><label className="overline text-slate-500">Nom (optionnel)</label>
              <Input data-testid="invite-name" value={name} onChange={(e) => setName(e.target.value)} className="mt-1 h-11" /></div>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-4">
            <div><label className="overline text-slate-500">Portée</label>
              <Select value={kind} onValueChange={setKind}><SelectTrigger className="mt-1 h-11" data-testid="invite-kind"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="company">Une société</SelectItem><SelectItem value="workspace">Espace de travail</SelectItem></SelectContent></Select></div>
            {kind === "company" && (
              <div><label className="overline text-slate-500">Société</label>
                <Select value={companyId} onValueChange={setCompanyId}><SelectTrigger className="mt-1 h-11" data-testid="invite-company"><SelectValue /></SelectTrigger>
                  <SelectContent>{companies.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}</SelectContent></Select></div>
            )}
            <div><label className="overline text-slate-500">Rôle</label>
              <Select value={role} onValueChange={setRole}><SelectTrigger className="mt-1 h-11" data-testid="invite-role"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="user">Utilisateur</SelectItem><SelectItem value="admin">Administrateur</SelectItem></SelectContent></Select></div>
            <p className="text-xs text-slate-500">Les modules et autorisations sensibles s'attribuent ensuite depuis la fiche de l'utilisateur, une fois son compte activé.</p>
          </div>
        )}
        {step === 3 && (
          <div className="space-y-3 text-sm">
            <p className="text-slate-600"><b>{email}</b> recevra une invitation à usage unique.</p>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div>Portée : <b>{kind === "workspace" ? "Espace de travail" : company?.name}</b></div>
              <div>Rôle : <b>{role === "admin" ? "Administrateur" : "Utilisateur"}</b></div>
            </div>
            <p className="text-xs text-slate-500">Aucune autorité financière n'est accordée automatiquement.</p>
          </div>
        )}
        <DialogFooter>
          {step > 1 && <Button variant="outline" onClick={() => setStep(step - 1)} data-testid="invite-back">Retour</Button>}
          {step < 3 && <Button onClick={() => setStep(step + 1)} disabled={step === 1 && !email} data-testid="invite-next" className="bg-[#063044] text-white">Continuer</Button>}
          {step === 3 && <Button onClick={send} disabled={busy} data-testid="invite-send" className="gap-2 bg-[#22C55E] text-white">{busy ? <Loader2 className="animate-spin" size={16} /> : <Send size={16} />} Envoyer l'invitation</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function UserDetail({ uid, open, onClose, onChanged }) {
  const [data, setData] = useState(null);
  const load = useCallback(() => { if (uid) api.getAccessUser(uid).then(setData).catch(() => setData(null)); }, [uid]);
  useEffect(() => { if (open) load(); }, [open, load]);
  if (!open) return null;
  const identity = data?.identity;
  const setLevel = async (cid, code, level) => {
    try { await api.setModuleAccess(cid, uid, code, level); toast.success("Accès mis à jour."); load(); onChanged?.(); }
    catch (e) { toast.error(e.response?.data?.detail || "Erreur."); }
  };
  const togglePerm = async (cid, code, granted) => {
    try { await api.setUserPermission(cid, uid, code, granted); toast.success(granted ? "Autorisation accordée." : "Autorisation retirée."); load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Erreur."); }
  };
  const toggleSuspend = async () => {
    const next = identity?.status === "active" ? "suspended" : "active";
    try { await api.setIdentityStatus(uid, next); toast.success(next === "active" ? "Accès rétabli." : "Compte suspendu."); load(); onChanged?.(); }
    catch (e) { toast.error(e.response?.data?.detail || "Erreur."); }
  };
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="user-detail">
        {!data ? <div className="flex items-center gap-2 p-6 text-slate-500"><Loader2 className="animate-spin" size={16} /> Chargement…</div> : (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-3">{identity?.name || identity?.email}
                <Badge2 status={identity?.status} /></DialogTitle>
              <p className="text-sm text-slate-500">{identity?.email}</p>
            </DialogHeader>
            {(data.companies || []).length === 0 && <p className="text-sm text-slate-500">Aucune société attribuée pour l'instant.</p>}
            {(data.companies || []).map((c) => (
              <div key={c.company_id} className="mt-2 rounded-xl border border-slate-200 p-4" data-testid={`company-block-${c.company_id}`}>
                <div className="mb-3 text-sm font-semibold text-[#063044]">Société {c.company_id.slice(0, 8)} · {c.membership_type} / {c.role}</div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {(c.modules || []).map((m) => (
                    <div key={m.module_code} className={`rounded-lg border p-3 ${m.entitled ? "border-slate-200" : "border-slate-100 opacity-50"}`} data-testid={`module-card-${m.module_code}`}>
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-[#0F172A]">{MODULE_LABEL[m.module_code]}</span>
                        <span className="text-xs text-slate-500">{LEVEL_LABEL(m.module_code, m.effective_level)}</span>
                      </div>
                      <Select value={m.assigned_level} onValueChange={(v) => setLevel(c.company_id, m.module_code, v)} disabled={!m.entitled}>
                        <SelectTrigger className="mt-2 h-9 text-xs" data-testid={`level-${c.company_id}-${m.module_code}`}><SelectValue /></SelectTrigger>
                        <SelectContent>{LEVELS.map((l) => <SelectItem key={l} value={l}>{LEVEL_LABEL(m.module_code, l)}</SelectItem>)}</SelectContent>
                      </Select>
                      {!m.entitled && <p className="mt-1 text-[11px] text-slate-400">Module non souscrit</p>}
                      {m.assigned_level !== "none" && PERM_GROUPS[m.module_code] && (
                        <div className="mt-3 space-y-2">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">Autorisations sensibles</p>
                          {PERM_GROUPS[m.module_code].map((g) => (
                            <div key={g.title}>
                              {g.perms.map(([code, label]) => {
                                const on = (m.sensitive_permissions || []).includes(code);
                                return (
                                  <label key={code} className="flex items-center gap-2 py-0.5 text-xs text-slate-600">
                                    <input type="checkbox" checked={on} onChange={(e) => togglePerm(c.company_id, code, e.target.checked)}
                                      data-testid={`perm-${c.company_id}-${code}`} />
                                    {label}
                                  </label>
                                );
                              })}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4">
              <p className="text-xs text-slate-400">Les autorisations sensibles sont attribuées séparément.</p>
              <Button variant={identity?.status === "active" ? "destructive" : "default"} onClick={toggleSuspend} data-testid="toggle-suspend">
                {identity?.status === "active" ? "Suspendre le compte" : "Rétablir l'accès"}
              </Button>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default function AccessManagement() {
  const [users, setUsers] = useState([]); const [invitations, setInvitations] = useState([]);
  const [tab, setTab] = useState("users"); const [q, setQ] = useState("");
  const [companies, setCompanies] = useState([]); const [invite, setInvite] = useState(false);
  const [detailUid, setDetailUid] = useState(null); const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    setLoading(true);
    Promise.all([api.listAccessUsers().catch(() => ({ users: [] })), api.listInvitations().catch(() => ({ invitations: [] })), api.getCompanies().catch(() => [])])
      .then(([u, i, c]) => { setUsers(u.users || []); setInvitations(i.invitations || []); setCompanies(c || []); })
      .finally(() => setLoading(false));
  }, []);
  useEffect(() => { load(); }, [load]);
  const pending = invitations.filter((i) => i.status === "pending").length;
  const expired = invitations.filter((i) => i.status === "expired").length;
  const activeUsers = users.filter((u) => u.identity?.status === "active").length;
  const filtered = users.filter((u) => !q || (u.identity?.email || "").toLowerCase().includes(q.toLowerCase()) || (u.identity?.name || "").toLowerCase().includes(q.toLowerCase()));
  const resend = async (id) => { try { await api.resendInvitation(id); toast.success("Invitation renvoyée."); load(); } catch (e) { toast.error("Erreur."); } };
  const revoke = async (id) => { try { await api.revokeInvitation(id); toast.success("Invitation révoquée."); load(); } catch (e) { toast.error("Erreur."); } };

  return (
    <div className="space-y-6" data-testid="access-management">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex gap-6 text-sm">
          <div><div className="text-2xl font-light text-[#063044]" data-testid="stat-active-users">{activeUsers}</div><div className="text-slate-500">utilisateurs actifs</div></div>
          <div><div className="text-2xl font-light text-[#063044]" data-testid="stat-pending">{pending}</div><div className="text-slate-500">invitations en attente</div></div>
          {expired > 0 && <div><div className="text-2xl font-light text-amber-600">{expired}</div><div className="text-slate-500">expirées</div></div>}
        </div>
        <Button onClick={() => setInvite(true)} className="gap-2 bg-[#22C55E] text-white" data-testid="invite-user-btn"><UserPlus size={16} /> Inviter un utilisateur</Button>
      </div>

      <div className="flex gap-2">
        <button onClick={() => setTab("users")} data-testid="tab-users" className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "users" ? "bg-[#063044] text-white" : "bg-slate-100 text-slate-600"}`}>Utilisateurs</button>
        <button onClick={() => setTab("invitations")} data-testid="tab-invitations" className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === "invitations" ? "bg-[#063044] text-white" : "bg-slate-100 text-slate-600"}`}>Invitations</button>
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
      ) : (
        <div className="space-y-3">
          {invitations.length === 0 ? <p className="text-sm text-slate-500" data-testid="invitations-empty">Aucune invitation.</p> :
            invitations.map((i) => (
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
      )}

      <InviteWizard open={invite} onClose={() => setInvite(false)} companies={companies} onDone={load} />
      <UserDetail uid={detailUid} open={!!detailUid} onClose={() => setDetailUid(null)} onChanged={load} />
    </div>
  );
}
