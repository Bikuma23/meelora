import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useNav } from "../context/NavContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import {
  Building2, Users, ScrollText, ChevronLeft,
  Loader2, Server, Search, Layers, ArrowRight, Pencil, Ban, CircleCheck, RotateCw, History,
} from "lucide-react";
import AccessManagement from "./AccessManagement";
import { CompanyForm, createCompanyWithAdmin } from "./Companies";
import { useLang } from "../context/LanguageContext";

const MODULE_LABEL = { REPORTING: "Reporting", ACCOUNTING: "Comptabilité", FIXED_ASSETS: "Immobilisations", CONSOLIDATION: "Consolidation" };

const fmtDate = (iso) => { try { return new Date(iso).toLocaleString("fr-CA", { dateStyle: "medium", timeStyle: "short" }); } catch { return iso || "—"; } };

function StatCard({ label, value, icon: Icon, testid }) {
  return (
    <div className="card flex items-center gap-4 p-5" data-testid={testid}>
      <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#15AF97]/12 text-[#15AF97]"><Icon size={20} /></span>
      <div>
        <div className="text-2xl font-light text-[#063044]">{value}</div>
        <div className="text-xs text-slate-500">{label}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Accueil plateforme
// ---------------------------------------------------------------------------
export function PlatformHome() {
  const [data, setData] = useState(null);
  useEffect(() => { api.platformSummary().then(setData).catch(() => setData({ clients: [] })); }, []);
  if (!data) return <div className="flex items-center gap-2 text-slate-500" data-testid="platform-home-loading"><Loader2 className="animate-spin" size={16} /> Chargement…</div>;
  return (
    <div className="space-y-6" data-testid="platform-home">
      <div className="rounded-2xl border border-[#063044]/10 bg-gradient-to-br from-[#063044] to-[#0a4a68] p-6 text-white" data-testid="platform-banner">
        <div className="flex items-center gap-2 text-[#7fe3cf]"><Server size={16} /><span className="text-xs font-semibold uppercase tracking-wider">Administration plateforme</span></div>
        <h3 className="mt-2 text-xl font-light">Supervision des mandats & clients Meelora</h3>
        <p className="mt-1 max-w-2xl text-sm text-white/70">Contexte strictement séparé des données financières des clients. Aucune autorité financière n'est accordée par le rôle plateforme.</p>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Clients / mandats" value={data.clients_count} icon={Building2} testid="platform-stat-clients" />
        <StatCard label="Sociétés" value={data.companies_count} icon={Layers} testid="platform-stat-companies" />
        <StatCard label="Utilisateurs" value={data.users_count} icon={Users} testid="platform-stat-users" />
        <StatCard label="Évènements plateforme" value={data.platform_events} icon={ScrollText} testid="platform-stat-events" />
      </div>
      <div className="card p-5">
        <h4 className="mb-3 text-sm font-semibold text-[#063044]">Clients récents</h4>
        <div className="space-y-2" data-testid="platform-home-clients">
          {(data.clients || []).map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-lg border border-slate-100 px-4 py-3" data-testid={`platform-home-client-${c.id}`}>
              <div><div className="font-medium text-[#0F172A]">{c.name}</div><div className="text-xs text-slate-400">{c.jurisdiction} · {c.organization_type}</div></div>
              <div className="text-xs text-slate-500">{c.companies_count} société(s) · {c.active_users_count} utilisateur(s)</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mandats / Clients (liste -> fiche client)
// ---------------------------------------------------------------------------
export function PlatformClients() {
  const { user } = useAuth();
  const { enterMeelora } = useNav();
  const { t } = useLang();
  const isPlatformAdmin = user?.platform_role === "platform_admin";
  const [companies, setCompanies] = useState(null);
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [statusDialog, setStatusDialog] = useState({ open: false, company: null, next: "inactive" });
  const [statusReason, setStatusReason] = useState("");
  const [historyDialog, setHistoryDialog] = useState({ open: false, company: null });
  const reload = useCallback(() => {
    api.platformCompanies().then((d) => setCompanies(d.companies || [])).catch(() => setCompanies([]));
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const openStatusDialog = (c, next) => { setStatusReason(""); setStatusDialog({ open: true, company: c, next }); };
  const changeStatus = async (c, next, reason) => {
    try {
      await api.updateCompany(c.id, { status: next, status_reason: reason });
      toast.success(next === "inactive" ? t("Société rendue inactive") : t("Société réactivée"));
      setStatusDialog({ open: false, company: null, next: "inactive" }); setStatusReason(""); reload();
    } catch (e) { toast.error(e.response?.data?.detail || t("Action impossible")); }
  };

  const submitCreate = async (payload) => {
    setSaving(true);
    try { await createCompanyWithAdmin(payload, t); toast.success(t("Société / client créé")); setFormOpen(false); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || t("Création impossible")); }
    finally { setSaving(false); }
  };
  const submitEdit = async (payload) => {
    setSaving(true);
    const body = { ...payload }; delete body._admin_action;
    try { await api.updateCompany(editing.id, body); toast.success(t("Société mise à jour")); setEditing(null); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || t("Modification impossible")); }
    finally { setSaving(false); }
  };

  if (selected) return <CompanyFicheCard company={selected} isPlatformAdmin={isPlatformAdmin}
    onBack={() => setSelected(null)} onEdit={(c) => setEditing(c)} />;
  if (!companies) return <div className="flex items-center gap-2 text-slate-500"><Loader2 className="animate-spin" size={16} /> Chargement…</div>;

  const isActive = (c) => c.status !== "inactive" && c.active !== false;
  const filtered = companies.filter((c) =>
    (!q || (c.name || "").toLowerCase().includes(q.toLowerCase()) || (c.company_code || "").toLowerCase().includes(q.toLowerCase()))
    && (statusFilter === "all" || (statusFilter === "active" ? isActive(c) : !isActive(c))));
  const internal = filtered.filter((c) => c.is_internal);
  const externals = filtered.filter((c) => !c.is_internal);

  const EditBtn = ({ c }) => isPlatformAdmin ? (
    <Button variant="outline" size="sm" className="gap-1" data-testid={`platform-company-edit-${c.id}`} onClick={() => setEditing(c)}>
      <Pencil size={14} /> Modifier
    </Button>
  ) : null;
  const StatusBadge = ({ c }) => isActive(c)
    ? <span className="inline-flex items-center gap-1 text-[11px] font-600 text-[#15803D]" data-testid={`platform-company-status-${c.id}`}><CircleCheck size={12}/>Active</span>
    : <span className="inline-flex items-center gap-1 text-[11px] font-600 text-slate-500" data-testid={`platform-company-status-${c.id}`}><Ban size={12}/>Inactive</span>;
  const LifecycleBtns = ({ c }) => isPlatformAdmin ? (
    <>
      {isActive(c)
        ? <Button size="sm" variant="outline" className="h-8 gap-1 text-rose-600 hover:text-rose-700" data-testid={`company-deactivate-${c.id}`} onClick={() => openStatusDialog(c, "inactive")}><Ban size={13}/>{t("Rendre inactive")}</Button>
        : <Button size="sm" variant="outline" className="h-8 gap-1 text-emerald-600 hover:text-emerald-700" data-testid={`company-reactivate-${c.id}`} onClick={() => openStatusDialog(c, "active")}><RotateCw size={13}/>{t("Réactiver")}</Button>}
      {(c.status_history || []).length > 0 && <Button size="sm" variant="ghost" className="h-8 gap-1 text-slate-500" data-testid={`company-history-${c.id}`} onClick={() => setHistoryDialog({ open: true, company: c })}><History size={13}/>{t("Historique")}</Button>}
    </>
  ) : null;
  const ReasonNote = ({ c }) => (!isActive(c) && c.status_reason)
    ? <div className="mt-2 rounded-lg bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-700" data-testid={`company-reason-${c.id}`}><span className="font-600">{t("Motif")} : </span>{c.status_reason}</div>
    : null;

  return (
    <div className="space-y-4" data-testid="platform-clients">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500">Portefeuille des sociétés gérées par Meelora. La société interne apparaît en premier.</p>
        {isPlatformAdmin && (
          <Button className="gap-1.5 bg-[#22C55E] text-[#0F172A] hover:bg-[#22C55E]/90 font-600" data-testid="platform-new-company-btn" onClick={() => setFormOpen(true)}>
            + Nouvelle société / client
          </Button>
        )}
      </div>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative max-w-sm flex-1">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher une société…" className="h-11 pl-9" data-testid="platform-clients-search" />
        </div>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="h-11 rounded-lg border border-slate-200 px-3 text-sm" data-testid="platform-company-status-filter">
          <option value="all">Toutes</option>
          <option value="active">Actives</option>
          <option value="inactive">Inactives</option>
        </select>
      </div>
      <CompanyForm open={formOpen} onOpenChange={setFormOpen} initial={null} onSubmit={submitCreate} saving={saving} />
      {editing && <CompanyForm open={!!editing} onOpenChange={(v) => !v && setEditing(null)} initial={editing} onSubmit={submitEdit} saving={saving} />}

      {internal.map((c) => (
        <div key={c.id} data-testid="platform-internal-card"
          className="flex flex-col gap-3 rounded-xl border border-[#15AF97]/40 bg-[#15AF97]/8 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#15AF97]/20 text-[#0f8f7c]"><Building2 size={18} /></span>
            <div>
              <div className="flex items-center gap-2 font-medium text-[#063044]">{c.name}
                <span className="rounded-full bg-[#15AF97] px-2 py-0.5 text-[10px] font-semibold uppercase text-white">Société interne</span>
                <StatusBadge c={c} />
              </div>
              <div className="text-xs text-slate-500">{[c.jurisdiction, c.functional_currency, c.company_code].filter(Boolean).join(" · ")}</div>
              <ReasonNote c={c} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <EditBtn c={c} />
            <LifecycleBtns c={c} />
            <Button variant="outline" size="sm" className="gap-1" data-testid={`platform-company-access-${c.id}`} onClick={() => setSelected(c)}>Fiche</Button>
            <Button className="gap-1.5 bg-[#063044] text-white hover:bg-[#0a4a68]" size="sm" data-testid="platform-internal-access" onClick={enterMeelora}>
              Accéder <ArrowRight size={14} />
            </Button>
          </div>
        </div>
      ))}
      {externals.length === 0 && internal.length > 0 && (
        <p className="pt-2 text-xs text-slate-400" data-testid="platform-no-clients">Aucune autre société pour le moment.</p>
      )}
      {externals.map((c) => (
        <div key={c.id} data-testid={`platform-company-row-${c.id}`}
          className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:border-[#15AF97] sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#063044]/8 text-[#063044]"><Building2 size={18} /></span>
            <div>
              <div className="flex items-center gap-2 font-medium text-[#0F172A]">{c.name} <StatusBadge c={c} /></div>
              <div className="text-xs text-slate-400">{[c.jurisdiction, c.functional_currency, c.company_code].filter(Boolean).join(" · ")}</div>
              <ReasonNote c={c} />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <EditBtn c={c} />
            <LifecycleBtns c={c} />
            <Button variant="outline" size="sm" data-testid={`platform-company-access-${c.id}`} onClick={() => setSelected(c)}>
              Accéder <ArrowRight size={14} className="ml-1" />
            </Button>
          </div>
        </div>
      ))}

      <Dialog open={statusDialog.open} onOpenChange={(v) => { if (!v) setStatusReason(""); setStatusDialog((p) => ({ ...p, open: v })); }}>
        <DialogContent data-testid={statusDialog.next === "inactive" ? "deactivate-dialog" : "reactivate-dialog"}>
          <DialogHeader>
            <DialogTitle>{statusDialog.next === "inactive"
              ? <>{t("Rendre")} {statusDialog.company?.name} {t("inactive ?")}</>
              : <>{t("Réactiver")} {statusDialog.company?.name} ?</>}</DialogTitle>
            <DialogDescription>{statusDialog.next === "inactive"
              ? t("Les utilisateurs ne pourront plus accéder à cette société tant qu'elle n'aura pas été réactivée. Les données et l'historique seront conservés.")
              : t("La société redeviendra accessible. Cette action est tracée dans l'historique de statut.")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label className="text-[11px] uppercase text-slate-500">{t("Motif")} {statusDialog.next === "inactive" ? <span className="text-rose-600">*</span> : <span className="text-slate-400">({t("optionnel")})</span>}</Label>
            <Textarea data-testid="status-reason" value={statusReason} onChange={(e) => setStatusReason(e.target.value)} rows={3}
              placeholder={statusDialog.next === "inactive" ? t("Expliquez pourquoi cette société est rendue inactive...") : t("Note de réactivation (optionnelle)...")} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setStatusReason(""); setStatusDialog({ open: false, company: null, next: "inactive" }); }}>{t("Annuler")}</Button>
            {statusDialog.next === "inactive"
              ? <Button className="bg-rose-600 hover:bg-rose-700" data-testid="deactivate-confirm" disabled={!statusReason.trim()} onClick={() => changeStatus(statusDialog.company, "inactive", statusReason.trim())}>{t("Rendre inactive")}</Button>
              : <Button className="bg-emerald-600 hover:bg-emerald-700" data-testid="reactivate-confirm" onClick={() => changeStatus(statusDialog.company, "active", statusReason.trim())}>{t("Réactiver")}</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={historyDialog.open} onOpenChange={(v) => setHistoryDialog((p) => ({ ...p, open: v }))}>
        <DialogContent data-testid="status-history-dialog">
          <DialogHeader>
            <DialogTitle>{t("Historique de statut")} — {historyDialog.company?.name}</DialogTitle>
            <DialogDescription>{t("Chaque désactivation et réactivation est tracée (date, statut, acteur, motif).")}</DialogDescription>
          </DialogHeader>
          <div className="max-h-[50vh] space-y-2 overflow-auto">
            {[...(historyDialog.company?.status_history || [])].reverse().map((h, i) => (
              <div key={i} className="rounded-lg border border-slate-200 p-3 text-xs" data-testid="status-history-entry">
                <div className="flex items-center justify-between gap-2">
                  <span className={`inline-flex items-center gap-1 font-600 ${h.to === "active" ? "text-emerald-600" : "text-rose-600"}`}>
                    {h.to === "active" ? <RotateCw size={12}/> : <Ban size={12}/>}
                    {t(h.from === "active" ? "Active" : "Inactive")} → {t(h.to === "active" ? "Active" : "Inactive")}
                  </span>
                  <span className="text-[10px] text-slate-400">{h.at ? new Date(h.at).toLocaleString() : ""}</span>
                </div>
                <p className="mt-1 text-slate-500">{t("Acteur")} : <b className="font-600 text-slate-700">{h.by || h.by_id || "—"}</b></p>
                {h.reason && <p className="mt-0.5 text-slate-500">{t("Motif")} : <span className="text-slate-700">{h.reason}</span></p>}
              </div>
            ))}
            {(historyDialog.company?.status_history || []).length === 0 && <p className="py-6 text-center text-sm text-slate-400">{t("Aucun changement de statut enregistré.")}</p>}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fiche détaillée d'une SOCIÉTÉ (portefeuille plateforme) : Aperçu · Utilisateurs
// · Modules. Action « Modifier » (platform_admin). Les utilisateurs proviennent
// des company_memberships de CETTE société (aucune fuite inter-sociétés).
// ---------------------------------------------------------------------------
const COMPANY_TABS = [
  { key: "overview", label: "Aperçu", icon: Building2 },
  { key: "users", label: "Utilisateurs", icon: Users },
];
const MEMBERSHIP_ACTIVE = new Set(["active"]);

function CompanyFicheCard({ company, isPlatformAdmin, onBack, onEdit }) {
  const [tab, setTab] = useState("overview");
  const isActive = company.status !== "inactive" && company.active !== false;
  return (
    <div className="space-y-5" data-testid="company-fiche-card">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-[#063044]" data-testid="company-fiche-back">
        <ChevronLeft size={16} /> Sociétés / Clients
      </button>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#063044] text-white"><Building2 size={22} /></span>
          <div>
            <h3 className="text-lg font-semibold text-[#063044]" data-testid="company-fiche-name">{company.name}
              {company.is_internal && <span className="ml-2 rounded-full bg-[#15AF97] px-2 py-0.5 text-[10px] font-semibold uppercase text-white">Interne</span>}</h3>
            <p className="text-xs text-slate-400">{[company.jurisdiction, company.functional_currency, company.company_code, company.id].filter(Boolean).join(" · ")}</p>
            <p className="mt-1 text-xs">{isActive
              ? <span className="inline-flex items-center gap-1 font-600 text-[#15803D]"><CircleCheck size={12}/>Active</span>
              : <span className="inline-flex items-center gap-1 font-600 text-slate-500"><Ban size={12}/>Inactive</span>}</p>
          </div>
        </div>
        {isPlatformAdmin && (
          <Button variant="outline" className="gap-1.5" data-testid="company-fiche-edit" onClick={() => onEdit(company)}>
            <Pencil size={15} /> Modifier
          </Button>
        )}
      </div>
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2" data-testid="company-fiche-tabs">
        {COMPANY_TABS.map((tt) => {
          const Icon = tt.icon; const on = tab === tt.key;
          return (
            <button key={tt.key} onClick={() => setTab(tt.key)} data-testid={`company-tab-${tt.key}`}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${on ? "bg-[#063044] text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
              <Icon size={15} /> {tt.label}
            </button>
          );
        })}
      </div>
      <div data-testid={`company-panel-${tab}`}>
        {tab === "overview" && <CompanyOverviewPanel company={company} />}
        {tab === "users" && <CompanyUsersPanel companyId={company.id} />}
      </div>
    </div>
  );
}

function CompanyOverviewPanel({ company }) {
  const [data] = useTabData(api.platformCompanyMembers, company.id);
  const count = data && data !== false ? (data.users || []).length : "…";
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      <StatCard label="Utilisateurs rattachés" value={count} icon={Users} testid="company-stat-users" />
      <StatCard label="Devise" value={company.functional_currency || "—"} icon={Layers} testid="company-stat-currency" />
      <StatCard label="Juridiction" value={company.jurisdiction || "—"} icon={Building2} testid="company-stat-jurisdiction" />
    </div>
  );
}

function CompanyUsersPanel({ companyId }) {
  const [data] = useTabData(api.platformCompanyMembers, companyId);
  if (data === null) return <Loading />;
  if (data === false) return <p className="text-sm text-red-500">Erreur de chargement.</p>;
  const users = data.users || [];
  const admins = users.filter((u) => u.role === "admin");
  const active = users.filter((u) => u.role !== "admin" && MEMBERSHIP_ACTIVE.has(u.membership_status));
  const suspended = users.filter((u) => u.role !== "admin" && !MEMBERSHIP_ACTIVE.has(u.membership_status));

  const Row = (u) => (
    <div key={u.identity.id} className="rounded-xl border border-slate-200 bg-white p-4" data-testid={`company-user-${u.identity.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 font-medium text-[#0F172A]">
            {u.identity.name || u.identity.email}
            {u.identity.platform_role && <span className="rounded-full bg-[#063044] px-2 py-0.5 text-[10px] uppercase text-white">{u.identity.platform_role}</span>}
          </div>
          <div className="text-sm text-slate-500" data-testid={`company-user-email-${u.identity.id}`}>{u.identity.email}</div>
          <div className="mt-1 flex flex-wrap gap-1.5 text-[11px]">
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">membership: {u.membership_type} · {u.role || "—"}</span>
            <span className={`rounded px-1.5 py-0.5 ${MEMBERSHIP_ACTIVE.has(u.membership_status) ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>{u.membership_status}</span>
            <span className="rounded bg-slate-100 px-1.5 py-0.5 text-slate-500">identité: {u.identity.status}</span>
          </div>
        </div>
        <div className="shrink-0 text-right text-[11px] text-slate-500" data-testid={`company-user-modules-${u.identity.id}`}>
          {(u.modules || []).length === 0 ? <span className="text-slate-400">Aucun module</span>
            : (u.modules || []).map((m) => <div key={m.module_code}>{MODULE_LABEL[m.module_code] || m.module_code} · <b>{m.level}</b></div>)}
        </div>
      </div>
    </div>
  );

  const Section = ({ title, list, testid }) => (
    <div className="space-y-2" data-testid={testid}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{title} ({list.length})</p>
      {list.length === 0 ? <p className="text-sm text-slate-400">—</p> : list.map(Row)}
    </div>
  );

  return (
    <div className="space-y-4" data-testid="company-users-panel">
      {users.length === 0 && <p className="text-sm text-slate-500" data-testid="company-users-empty">Aucun utilisateur rattaché à cette société.</p>}
      <Section title="Administrateurs" list={admins} testid="company-users-admins" />
      <Section title="Utilisateurs actifs" list={active} testid="company-users-active" />
      <Section title="Suspendus / inactifs" list={suspended} testid="company-users-suspended" />
      <p className="pt-1 text-[11px] text-slate-400">Vue lecture seule. Le personnel plateforme n'obtient aucun accès financier implicite.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Société Meelora — gestion opérationnelle interne (ouverte via Sociétés/Clients
// -> carte Meelora -> Accéder). Réutilise la console d'accès P1.13. Administrer
// ces accès n'accorde AUCUNE autorité financière au personnel plateforme.
// ---------------------------------------------------------------------------
export function PlatformMeeloraManage() {
  const { user } = useAuth();
  const { go } = useNav();
  return (
    <div className="space-y-5" data-testid="platform-meelora-manage">
      <button onClick={() => go("platform_clients")} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-[#063044]" data-testid="meelora-manage-back">
        <ChevronLeft size={16} /> Sociétés / Clients
      </button>
      <div className="rounded-2xl border border-[#15AF97]/40 bg-[#15AF97]/8 p-5" data-testid="meelora-manage-header">
        <div className="flex items-center gap-2 text-[#0f8f7c]"><Building2 size={16} /><span className="text-xs font-semibold uppercase tracking-wider">Société interne</span></div>
        <h3 className="mt-1 text-lg font-light text-[#063044]">{user?.workspace?.name || "Société Meelora"} — gestion opérationnelle</h3>
        <p className="mt-1 max-w-3xl text-sm text-slate-500">Administrateurs, utilisateurs, invitations, accès par module (none / read / contribute / manage), permissions sensibles et accès effectifs. Administrer ces accès <b>n'accorde aucune autorité financière</b> à l'administrateur plateforme (platform_role ≠ autorité).</p>
      </div>
      <AccessManagement />
    </div>
  );
}


function useTabData(fn, wsId) {
  const [data, setData] = useState(null);
  const reload = useCallback(() => { fn(wsId).then(setData).catch(() => setData(false)); }, [fn, wsId]);
  useEffect(() => { reload(); }, [reload]);
  return [data, reload];
}
const Loading = () => <div className="flex items-center gap-2 text-slate-500"><Loader2 className="animate-spin" size={16} /> Chargement…</div>;


// ---------------------------------------------------------------------------
// Logs plateforme (scope plateforme uniquement) — outil d'audit : recherche +
// filtres + détail. Aucun flux client agrégé ; aucun secret exposé (redaction
// côté serveur). Les logs propres à un client restent dans sa fiche (onglet Logs).
// ---------------------------------------------------------------------------
const PLATFORM_EVENT_TYPES = [
  "client.created", "client.activated", "client.deactivated",
  "client_admin.linked", "client_admin.replaced", "client_admin.deactivated",
  "platform.login", "platform.config", "support.action",
];
const RESULT_COLOR = { success: "bg-emerald-100 text-emerald-700", failure: "bg-rose-100 text-rose-700" };

export function PlatformLogs() {
  const [logs, setLogs] = useState(null);
  const [q, setQ] = useState("");
  const [eventType, setEventType] = useState("");
  const [result, setResult] = useState("");
  const [actor, setActor] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [expanded, setExpanded] = useState(null);
  const load = useCallback(() => {
    const params = {};
    if (q) params.q = q;
    if (eventType) params.event_type = eventType;
    if (result) params.result = result;
    if (actor) params.actor = actor;
    if (from) params.date_from = from;
    if (to) params.date_to = to;
    api.platformLogs(params).then(setLogs).catch(() => setLogs([]));
  }, [q, eventType, result, actor, from, to]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  const reset = () => { setQ(""); setEventType(""); setResult(""); setActor(""); setFrom(""); setTo(""); };
  return (
    <div className="space-y-4" data-testid="platform-logs">
      <p className="text-xs text-slate-400">Évènements de scope <b>plateforme</b> uniquement (création client, remplacement d'administrateur, actions support, configuration…). Aucun flux agrégé des opérations clients ; aucun secret n'est journalisé.</p>

      <div className="card space-y-3 p-4" data-testid="platform-logs-filters">
        <div className="relative">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher (utilisateur, email, société, évènement, ressource, IP, métadonnées…)" className="h-11 pl-9" data-testid="platform-logs-search" />
        </div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 lg:grid-cols-6">
          <select value={eventType} onChange={(e) => setEventType(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-2 text-sm" data-testid="platform-logs-filter-event">
            <option value="">Tous les types</option>
            {PLATFORM_EVENT_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <select value={result} onChange={(e) => setResult(e.target.value)} className="h-9 rounded-lg border border-slate-200 px-2 text-sm" data-testid="platform-logs-filter-result">
            <option value="">Tout résultat</option>
            <option value="success">Succès</option>
            <option value="failure">Échec</option>
          </select>
          <Input value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Acteur / email" className="h-9" data-testid="platform-logs-filter-actor" />
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-9" data-testid="platform-logs-from" />
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-9" data-testid="platform-logs-to" />
          <Button variant="outline" size="sm" onClick={reset} data-testid="platform-logs-reset">Réinitialiser</Button>
        </div>
      </div>

      {!logs ? <Loading /> : logs.length === 0 ? (
        <p className="text-sm text-slate-500" data-testid="platform-logs-empty">Aucun évènement plateforme ne correspond aux critères.</p>
      ) : (
        <div className="card divide-y divide-slate-100" data-testid="platform-logs-list">
          {logs.map((e) => (
            <div key={e.id} className="px-4 py-3" data-testid="platform-log-entry" data-event={e.event_type} data-result={e.result}>
              <div className="flex items-start justify-between gap-4 cursor-pointer" onClick={() => setExpanded(expanded === e.id ? null : e.id)} data-testid={`platform-log-toggle-${e.id}`}>
                <div className="flex items-start gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#063044]/8 text-[#063044]"><ScrollText size={15} /></span>
                  <div>
                    <p className="text-sm">
                      <span className="font-semibold text-[#063044]">{e.event_type}</span>
                      <span className="ml-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] uppercase text-slate-500">{e.category}</span>
                      {e.result && <span className={`ml-2 rounded-full px-2 py-0.5 text-[10px] uppercase ${RESULT_COLOR[e.result] || "bg-slate-100 text-slate-500"}`}>{e.result}</span>}
                    </p>
                    <p className="text-slate-600 text-sm">{e.label}</p>
                    <p className="text-[11px] text-slate-400">
                      {e.actor_email}{e.actor_platform_role ? ` (${e.actor_platform_role})` : ""}
                      {e.resource ? ` · ${e.resource}` : ""}
                      {e.target_workspace_id ? ` · client ${e.target_workspace_id}` : ""}
                      {e.ip ? ` · IP ${e.ip}` : ""}
                    </p>
                  </div>
                </div>
                <span className="shrink-0 font-mono-data text-xs text-slate-400">{fmtDate(e.timestamp)}</span>
              </div>
              {expanded === e.id && (
                <div className="mt-3 ml-11 rounded-lg bg-slate-50 p-3 text-[11px] text-slate-600" data-testid={`platform-log-detail-${e.id}`}>
                  <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
                    {e.request_id && <div><b>Request ID :</b> {e.request_id}</div>}
                    {e.user_agent && <div><b>User-Agent :</b> {e.user_agent}</div>}
                    {e.reason && <div><b>Motif :</b> {e.reason}</div>}
                    {e.action && <div><b>Action :</b> {e.action}</div>}
                    {e.target_user_id && <div><b>Utilisateur concerné :</b> {e.target_user_id}</div>}
                  </div>
                  {(e.before || e.after) && (
                    <pre className="mt-2 overflow-x-auto rounded bg-white p-2 font-mono-data" data-testid={`platform-log-diff-${e.id}`}>{JSON.stringify({ before: e.before, after: e.after }, null, 2)}</pre>
                  )}
                  <pre className="mt-2 overflow-x-auto rounded bg-white p-2 font-mono-data">{JSON.stringify(e.metadata || {}, null, 2)}</pre>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
