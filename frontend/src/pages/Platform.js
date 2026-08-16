import { useState, useEffect, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useNav } from "../context/NavContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { toast } from "sonner";
import {
  Building2, Users, ShieldCheck, Boxes, ScrollText, LifeBuoy, ChevronLeft, ChevronRight,
  Loader2, Server, Search, CheckCircle2, AlertTriangle, Layers, ArrowRight,
} from "lucide-react";
import AccessManagement from "./AccessManagement";
import { CompanyForm, createCompanyWithAdmin } from "./Companies";
import { useLang } from "../context/LanguageContext";

const MODULE_LABEL = { REPORTING: "Reporting", ACCOUNTING: "Comptabilité", FIXED_ASSETS: "Immobilisations", CONSOLIDATION: "Consolidation" };
const ENT_LABEL = { active: "Actif", trial: "Essai", inactive: "Inactif", suspended: "Suspendu" };
const ENT_COLOR = { active: "bg-emerald-100 text-emerald-700", trial: "bg-blue-100 text-blue-700", inactive: "bg-slate-100 text-slate-500", suspended: "bg-amber-100 text-amber-700" };

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
  const internalWsId = user?.workspace?.id;
  const isPlatformAdmin = user?.platform_role === "platform_admin";
  const [clients, setClients] = useState(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState(null);
  const [formOpen, setFormOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const reload = useCallback(() => { api.platformClients().then((d) => setClients(d.clients || [])).catch(() => setClients([])); }, []);
  useEffect(() => { reload(); }, [reload]);
  const submitCompany = async (payload) => {
    setSaving(true);
    try { await createCompanyWithAdmin(payload, t); toast.success(t("Société / client créé")); setFormOpen(false); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || t("Création impossible")); }
    finally { setSaving(false); }
  };
  if (selected) return <ClientCard client={selected} onBack={() => setSelected(null)} />;
  if (!clients) return <div className="flex items-center gap-2 text-slate-500"><Loader2 className="animate-spin" size={16} /> Chargement…</div>;
  const filtered = clients.filter((c) => !q || (c.name || "").toLowerCase().includes(q.toLowerCase()));
  // Internal Meelora card always first; external clients after.
  const internal = filtered.filter((c) => c.id === internalWsId);
  const externals = filtered.filter((c) => c.id !== internalWsId);
  return (
    <div className="space-y-4" data-testid="platform-clients">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500">Registre central des sociétés utilisant Meelora. La société interne apparaît en premier.</p>
        {isPlatformAdmin && (
          <Button className="gap-1.5 bg-[#22C55E] text-[#0F172A] hover:bg-[#22C55E]/90 font-600" data-testid="platform-new-company-btn" onClick={() => setFormOpen(true)}>
            + Nouvelle société / client
          </Button>
        )}
      </div>
      <div className="relative max-w-sm">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un client…" className="h-11 pl-9" data-testid="platform-clients-search" />
      </div>
      <CompanyForm open={formOpen} onOpenChange={setFormOpen} initial={null} onSubmit={submitCompany} saving={saving} />
      {internal.map((c) => (
        <div key={c.id} data-testid="platform-internal-card"
          className="flex flex-col gap-3 rounded-xl border border-[#15AF97]/40 bg-[#15AF97]/8 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#15AF97]/20 text-[#0f8f7c]"><Building2 size={18} /></span>
            <div>
              <div className="flex items-center gap-2 font-medium text-[#063044]">{c.name}
                <span className="rounded-full bg-[#15AF97] px-2 py-0.5 text-[10px] font-semibold uppercase text-white">Société interne</span>
              </div>
              <div className="text-xs text-slate-500">{c.jurisdiction} · {c.companies_count} société(s) · {c.active_users_count} utilisateur(s)</div>
            </div>
          </div>
          <Button className="gap-1.5 bg-[#063044] text-white hover:bg-[#0a4a68]" data-testid="platform-internal-access" onClick={enterMeelora}>
            Accéder <ArrowRight size={14} />
          </Button>
        </div>
      ))}
      {externals.length === 0 && internal.length > 0 && (
        <p className="pt-2 text-xs text-slate-400" data-testid="platform-no-clients">Aucun client externe pour le moment.</p>
      )}
      {externals.map((c) => (
        <div key={c.id} data-testid={`platform-client-row-${c.id}`}
          className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4 transition-colors hover:border-[#15AF97]">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#063044]/8 text-[#063044]"><Building2 size={18} /></span>
            <div>
              <div className="font-medium text-[#0F172A]">{c.name}</div>
              <div className="text-xs text-slate-400">{c.jurisdiction} · {c.organization_type} · {c.companies_count} société(s)</div>
            </div>
          </div>
          <Button variant="outline" size="sm" data-testid={`platform-client-access-${c.id}`} onClick={() => setSelected(c)}>
            Accéder <ArrowRight size={14} className="ml-1" />
          </Button>
        </div>
      ))}
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

// ---------------------------------------------------------------------------
// Fiche client Meelora
// ---------------------------------------------------------------------------
const TABS = [
  { key: "overview", label: "Aperçu", icon: Building2 },
  { key: "admins", label: "Administrateurs", icon: ShieldCheck },
  { key: "users", label: "Utilisateurs", icon: Users },
  { key: "modules", label: "Modules", icon: Boxes },
  { key: "logs", label: "Logs", icon: ScrollText },
  { key: "support", label: "Support", icon: LifeBuoy },
];

function ClientCard({ client, onBack }) {
  const [tab, setTab] = useState("overview");
  return (
    <div className="space-y-5" data-testid="client-card">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-slate-500 hover:text-[#063044]" data-testid="client-card-back">
        <ChevronLeft size={16} /> Tous les clients
      </button>
      <div className="flex items-center gap-3">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#063044] text-white"><Building2 size={22} /></span>
        <div>
          <h3 className="text-lg font-semibold text-[#063044]" data-testid="client-card-name">{client.name}</h3>
          <p className="text-xs text-slate-400">{client.jurisdiction} · {client.organization_type} · {client.id}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 border-b border-slate-200 pb-2" data-testid="client-card-tabs">
        {TABS.map((tt) => {
          const Icon = tt.icon; const on = tab === tt.key;
          return (
            <button key={tt.key} onClick={() => setTab(tt.key)} data-testid={`client-tab-${tt.key}`}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${on ? "bg-[#063044] text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"}`}>
              <Icon size={15} /> {tt.label}
            </button>
          );
        })}
      </div>
      <div data-testid={`client-panel-${tab}`}>
        {tab === "overview" && <OverviewTab wsId={client.id} />}
        {tab === "admins" && <AdminsTab wsId={client.id} />}
        {tab === "users" && <UsersTab wsId={client.id} />}
        {tab === "modules" && <ModulesTab wsId={client.id} />}
        {tab === "logs" && <LogsTab wsId={client.id} />}
        {tab === "support" && <SupportTab wsId={client.id} />}
      </div>
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

function OverviewTab({ wsId }) {
  const [data] = useTabData(api.platformClient, wsId);
  if (data === null) return <Loading />;
  if (data === false) return <p className="text-sm text-red-500">Erreur de chargement.</p>;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Sociétés" value={data.companies.length} icon={Layers} testid="overview-stat-companies" />
        <StatCard label="Utilisateurs" value={data.users_count} icon={Users} testid="overview-stat-users" />
        <StatCard label="Administrateurs clients" value={data.client_admins_count} icon={ShieldCheck} testid="overview-stat-admins" />
      </div>
      <div className="card p-5">
        <h4 className="mb-3 text-sm font-semibold text-[#063044]">Sociétés du mandat</h4>
        <div className="space-y-2">
          {data.companies.map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-lg border border-slate-100 px-4 py-2.5 text-sm" data-testid={`overview-company-${c.id}`}>
              <span className="font-medium text-[#0F172A]">{c.name}</span>
              <span className="text-xs text-slate-400">{c.legacy_prefix} · {c.status}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="card p-5">
        <h4 className="mb-3 text-sm font-semibold text-[#063044]">Modules souscrits (entitlements)</h4>
        <div className="flex flex-wrap gap-2">
          {data.entitlements.map((e) => (
            <span key={e.module_code} className={`rounded-full px-3 py-1 text-xs font-medium ${ENT_COLOR[e.status] || "bg-slate-100 text-slate-500"}`} data-testid={`overview-ent-${e.module_code}`}>
              {MODULE_LABEL[e.module_code] || e.module_code} — {ENT_LABEL[e.status] || e.status}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function AdminsTab({ wsId }) {
  const [data, reload] = useTabData(api.platformClientAdmins, wsId);
  const [replace, setReplace] = useState(null);
  if (data === null) return <Loading />;
  if (data === false) return <p className="text-sm text-red-500">Erreur de chargement.</p>;
  return (
    <div className="space-y-3" data-testid="admins-tab">
      {data.companies.map((c) => {
        const current = (c.current_admins || []).filter((a) => a && a.membership_id);
        return (
          <div key={c.company_id} className="card p-4" data-testid={`admin-company-${c.company_id}`}>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-[#0F172A]">{c.company_name}</div>
                <div className="text-xs text-slate-500">{current.map((a) => a.email).join(", ") || "Aucun administrateur"}</div>
              </div>
              <Button variant="outline" size="sm" className="text-red-600" data-testid={`replace-admin-${c.company_id}`}
                disabled={!current.length} onClick={() => setReplace({ companyId: c.company_id, companyName: c.company_name, current: current[0] })}
                title={!current.length ? "Aucun administrateur actuel à remplacer" : undefined}>
                Remplacer l'administrateur
              </Button>
            </div>
            {!current.length && <p className="mt-1 text-[11px] text-slate-400" data-testid={`replace-admin-hint-${c.company_id}`}>Aucun administrateur actuel à remplacer pour cette société.</p>}
            {(c.replacements || []).length > 0 && (
              <div className="mt-3 border-t border-slate-100 pt-3">
                <p className="mb-1 text-[11px] uppercase tracking-wide text-slate-400">Historique des remplacements</p>
                {c.replacements.map((r, i) => (
                  <div key={i} className="text-xs text-slate-500" data-testid={`admin-repl-${c.company_id}-${i}`}>{fmtDate(r.date)} → {r.new_email}</div>
                ))}
              </div>
            )}
          </div>
        );
      })}
      <ReplaceAdminDialog info={replace} onClose={() => setReplace(null)} onDone={() => { setReplace(null); reload(); }} />
    </div>
  );
}

function ReplaceAdminDialog({ info, onClose, onDone }) {
  const [step, setStep] = useState(1); const [email, setEmail] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { if (info) { setStep(1); setEmail(""); } }, [info]);
  const submit = async () => {
    if (!info?.current) { toast.error("Aucun administrateur actif à remplacer."); return; }
    setBusy(true);
    try {
      await api.replaceCompanyAdmin(info.companyId, { old_membership_id: info.current.membership_id, new_email: email });
      setStep(3);
      toast.success("Administrateur remplacé. Le nouvel administrateur a reçu son lien d'activation.");
    } catch (e) { toast.error(e.response?.data?.detail || "Erreur."); }
    finally { setBusy(false); }
  };
  return (
    <Dialog open={!!info} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md" data-testid="replace-admin-dialog">
        <DialogHeader>
          <DialogTitle>Remplacer l'administrateur — {info?.companyName}</DialogTitle>
          <DialogDescription className="text-xs">Action d'autorité plateforme. Meelora ne définit jamais de mot de passe.</DialogDescription>
        </DialogHeader>
        {step === 1 && (
          <div className="space-y-3 text-sm">
            <p className="rounded-lg bg-amber-50 p-3 text-amber-800">⚠️ L'ancien administrateur perdra <b>immédiatement</b> son accès et ses sessions seront révoquées.</p>
            <p className="text-slate-600">Administrateur actuel : <b>{info?.current?.email || "aucun"}</b></p>
            <DialogFooter><Button onClick={() => setStep(2)} disabled={!info?.current} data-testid="replace-continue" className="bg-[#063044] text-white">Continuer</Button></DialogFooter>
          </div>
        )}
        {step === 2 && (
          <div className="space-y-3">
            <label className="overline text-slate-500">Courriel du nouvel administrateur</label>
            <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="nouvel.admin@societe.com" className="h-11" data-testid="replace-email" />
            <DialogFooter>
              <Button variant="outline" onClick={() => setStep(1)}>Retour</Button>
              <Button onClick={submit} disabled={busy || !email} data-testid="replace-confirm" className="gap-2 bg-red-600 text-white">{busy ? <Loader2 className="animate-spin" size={16} /> : null} Confirmer</Button>
            </DialogFooter>
          </div>
        )}
        {step === 3 && (
          <div className="space-y-3 text-sm" data-testid="replace-done">
            <div className="flex items-center gap-2 text-emerald-600"><CheckCircle2 size={18} /> Remplacement effectué</div>
            <DialogFooter><Button onClick={onDone} className="bg-[#063044] text-white">Terminer</Button></DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function UsersTab({ wsId }) {
  const [data] = useTabData(api.platformClientUsers, wsId);
  if (data === null) return <Loading />;
  if (data === false) return <p className="text-sm text-red-500">Erreur de chargement.</p>;
  return (
    <div className="space-y-2" data-testid="users-tab">
      {(data.users || []).length === 0 && <p className="text-sm text-slate-500">Aucun utilisateur.</p>}
      {(data.users || []).map((u) => (
        <div key={u.identity.id} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-4" data-testid={`platform-user-${u.identity.id}`}>
          <div>
            <div className="flex items-center gap-2 font-medium text-[#0F172A]">
              {u.identity.name || u.identity.email}
              {u.identity.platform_role && <span className="rounded-full bg-[#063044] px-2 py-0.5 text-[10px] uppercase text-white">{u.identity.platform_role}</span>}
            </div>
            <div className="text-sm text-slate-500">{u.identity.email}</div>
          </div>
          <div className="text-right text-xs text-slate-400">
            <div>{u.workspace_membership ? `workspace: ${u.workspace_membership.role}` : "—"}</div>
            <div>{(u.company_memberships || []).length} société(s)</div>
          </div>
        </div>
      ))}
      <p className="pt-1 text-[11px] text-slate-400">Vue en lecture seule. L'administration des accès financiers reste dans le contexte société.</p>
    </div>
  );
}

function ModulesTab({ wsId }) {
  const [data] = useTabData(api.platformClientModules, wsId);
  if (data === null) return <Loading />;
  if (data === false) return <p className="text-sm text-red-500">Erreur de chargement.</p>;
  return (
    <div className="space-y-4" data-testid="modules-tab">
      <div className="card p-5">
        <h4 className="mb-3 text-sm font-semibold text-[#063044]">Entitlements workspace</h4>
        <div className="flex flex-wrap gap-2">
          {data.entitlements.map((e) => (
            <span key={e.module_code} className={`rounded-full px-3 py-1 text-xs font-medium ${ENT_COLOR[e.status] || "bg-slate-100 text-slate-500"}`} data-testid={`mod-ent-${e.module_code}`}>
              {MODULE_LABEL[e.module_code] || e.module_code} — {ENT_LABEL[e.status] || e.status}
            </span>
          ))}
        </div>
      </div>
      {data.companies.map((c) => (
        <div key={c.company_id} className="card p-5" data-testid={`mod-company-${c.company_id}`}>
          <h4 className="mb-3 text-sm font-semibold text-[#063044]">{c.company_name} — activation par société</h4>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {c.enablement.map((m) => (
              <div key={m.module_code} className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2 text-sm" data-testid={`mod-enable-${c.company_id}-${m.module_code}`}>
                <span className="text-[#0F172A]">{MODULE_LABEL[m.module_code] || m.module_code}</span>
                <span className={`text-xs font-medium ${m.enabled ? "text-emerald-600" : "text-red-500"}`}>{m.enabled ? "Activé" : "Désactivé"}</span>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function LogsTab({ wsId }) {
  const [data] = useTabData(api.platformClientLogs, wsId);
  if (data === null) return <Loading />;
  if (data === false) return <p className="text-sm text-red-500">Erreur de chargement.</p>;
  return (
    <div className="space-y-2" data-testid="logs-tab">
      <p className="text-xs text-slate-400">Logs opérationnels (tenant) de ce client. Les évènements plateforme n'apparaissent jamais ici.</p>
      {(data || []).length === 0 && <p className="text-sm text-slate-500">Aucune activité.</p>}
      <div className="card divide-y divide-slate-100">
        {(data || []).slice(0, 200).map((e) => (
          <div key={e.id} className="flex items-start justify-between gap-4 px-4 py-2.5" data-testid="client-log-entry">
            <div className="min-w-0">
              <p className="text-sm"><span className="font-semibold text-[#063044]">{e.action || e.event_type}</span> <span className="text-slate-400">· {e.entity || ""}</span> <span className="text-slate-600">{e.label}</span></p>
              <p className="text-[11px] text-slate-400">{e.user_name || e.user_email}</p>
            </div>
            <span className="shrink-0 font-mono-data text-xs text-slate-400">{fmtDate(e.timestamp)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SupportTab({ wsId }) {
  const [data] = useTabData(api.platformClientSupport, wsId);
  if (data === null) return <Loading />;
  if (data === false) return <p className="text-sm text-red-500">Erreur de chargement.</p>;
  return (
    <div className="space-y-4" data-testid="support-tab">
      <div className="card p-5">
        <h4 className="mb-3 text-sm font-semibold text-[#063044]">Contacts administrateurs</h4>
        {(data.contacts || []).length === 0 ? <p className="text-sm text-slate-500">Aucun contact.</p> :
          (data.contacts || []).map((c, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg border border-slate-100 px-4 py-2.5 text-sm" data-testid={`support-contact-${i}`}>
              <span className="font-medium text-[#0F172A]">{c.name || c.email}</span>
              <span className="text-xs text-slate-400">{c.email}</span>
            </div>
          ))}
      </div>
      <div className="card p-5">
        <h4 className="mb-3 text-sm font-semibold text-[#063044]">Journal des actions plateforme (ce client)</h4>
        {(data.activity || []).length === 0 ? <p className="text-sm text-slate-500">Aucune action plateforme enregistrée.</p> :
          (data.activity || []).map((a) => (
            <div key={a.id} className="flex items-start justify-between gap-4 border-b border-slate-100 py-2.5 last:border-0" data-testid="support-activity">
              <div className="flex items-start gap-2">
                <AlertTriangle size={14} className="mt-0.5 text-amber-500" />
                <div><p className="text-sm text-[#063044]">{a.label || a.event_type}</p><p className="text-[11px] text-slate-400">{a.actor_email}</p></div>
              </div>
              <span className="shrink-0 font-mono-data text-xs text-slate-400">{fmtDate(a.timestamp)}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

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
