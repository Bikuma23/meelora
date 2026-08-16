import { useState, useEffect, useRef } from "react";
import { useAuth } from "../context/AuthContext";
import { YearProvider, useYear } from "../context/YearContext";
import { useLang } from "../context/LanguageContext";
import {
  LayoutDashboard, Users, DollarSign, Settings, Building2, FileText, ScrollText, LogOut, Briefcase, Plus, CalendarRange, ShieldCheck, Menu, X, UserCog, ChevronUp, ChevronDown, ChevronRight, Minimize2, HelpCircle, Bell, Camera, Trash2, Pencil, AlertTriangle, Layers,
} from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Avatar, AvatarImage, AvatarFallback } from "./ui/avatar";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator } from "./ui/dropdown-menu";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/dialog";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { toast } from "sonner";
import { api } from "../lib/api";
import Dashboard from "../pages/Dashboard";
import Employes from "../pages/Employes";
import SalairesBudget from "../pages/SalairesBudget";
import Hypotheses from "../pages/Hypotheses";
import Departements from "../pages/Departements";
import Rapports from "../pages/Rapports";
import Logs from "../pages/Logs";
import UsersPage from "../pages/Users";
import AccessManagement from "../pages/AccessManagement";
import CompaniesPage from "../pages/Companies";
import Preferences from "../pages/Preferences";
import { applyTheme } from "../lib/theme";
import { AcctDashboard, AcctBV, AcctBilan, AcctPnl, AcctCashflow, AcctReports } from "../pages/Comptabilite";
import QcEntity from "../pages/QcEntity";
import { PlatformHome, PlatformClients, PlatformLogs, PlatformMeeloraManage } from "../pages/Platform";
import { ReportingHome, FixedAssetsHome, ConsolidationHome } from "../pages/ModulePlaceholder";
import MandatsList from "../pages/MandatsList";
import { NavContext } from "../context/NavContext";
import { Calculator, Landmark, ClipboardList, Wallet, FileBarChart, Building, Server } from "lucide-react";

const PAGES = {
  dashboard: { title: "Tableau de bord", sub: "Vue globale", comp: Dashboard },
  employes: { title: "Employés", sub: "Gestion RH", comp: Employes },
  budget: { title: "Salaires & Budget", sub: "Saisie & calculs", comp: SalairesBudget },
  hypotheses: { title: "Hypothèses", sub: "Taux & paramètres", comp: Hypotheses },
  departements: { title: "Départements", sub: "Codes & superviseurs", comp: Departements },
  rapports: { title: "Rapports", sub: "Prédéfinis & custom", comp: Rapports },
  companies: { title: "Sociétés / Mandats", sub: "Portefeuille & affectations", comp: CompaniesPage },
  utilisateurs: { title: "Utilisateurs", sub: "Comptes & accès", comp: UsersPage },
  access: { title: "Utilisateurs et accès", sub: "Invitations & permissions", comp: AccessManagement },
  logs: { title: "Logs", sub: "Historique des activités", comp: Logs },
  preferences: { title: "Mon profil", sub: "Préférences & apparence", comp: Preferences },
  acct_dashboard: { title: "Tableau de bord", sub: "Vue d'ensemble du mois", comp: AcctDashboard },
  acct_bv: { title: "Balance de vérification", sub: "Upload & gestion mensuelle", comp: AcctBV },
  acct_bilan: { title: "Bilan", sub: "État de situation financière", comp: AcctBilan },
  acct_pnl: { title: "État des résultats", sub: "P&L du mois", comp: AcctPnl },
  acct_cashflow: { title: "Flux de trésorerie", sub: "Méthode indirecte", comp: AcctCashflow },
  acct_audit: { title: "Rapports", sub: "Génération centralisée", comp: AcctReports },
  acct_qc9434: { title: "9434-3977 QC inc.", sub: "Commandité", comp: QcEntity },
  platform_home: { title: "Tableau de bord", sub: "Supervision Meelora", comp: PlatformHome },
  platform_clients: { title: "Sociétés / Clients", sub: "Registre des sociétés Meelora", comp: PlatformClients },
  platform_meelora_manage: { title: "Société Meelora — Gestion", sub: "Environnement opérationnel interne", comp: PlatformMeeloraManage },
  platform_logs: { title: "Logs plateforme", sub: "Audit des évènements plateforme", comp: PlatformLogs },
  mandats_list: { title: "Tous les mandats", sub: "Vos sociétés accessibles", comp: MandatsList },
  reporting_home: { title: "Reporting", sub: "Module Reporting", comp: ReportingHome },
  fixed_assets_home: { title: "Immobilisations", sub: "Module Immobilisations", comp: FixedAssetsHome },
  consolidation_home: { title: "Consolidation", sub: "Module Consolidation", comp: ConsolidationHome },
};

// P1.13E — module canonique -> rendu de navigation (aucun menu codé selon user.role).
const MODULE_NAV = {
  REPORTING: { type: "item", label: "Reporting", icon: FileBarChart, item: { key: "reporting_home", label: "Reporting", sub: "Module Reporting", icon: FileBarChart } },
  BUDGETS: { type: "parent", label: "Gestion des Budgets", icon: DollarSign,
             parent: { key: "budget", label: "Gestion des Budgets", sub: "Salaires & budget", icon: DollarSign }, children: null },
  ACCOUNTING: { type: "group", label: "Comptabilité", icon: Calculator, items: null },
  FIXED_ASSETS: { type: "item", label: "Immobilisations", icon: Landmark, item: { key: "fixed_assets_home", label: "Immobilisations", sub: "Module Immobilisations", icon: Landmark } },
  CONSOLIDATION: { type: "item", label: "Consolidation", icon: Layers, item: { key: "consolidation_home", label: "Consolidation", sub: "Module Consolidation", icon: Layers } },
};
// Pages autorisées par module (pour garder la page active cohérente avec les droits).
const MODULE_PAGES = {
  REPORTING: ["reporting_home"],
  BUDGETS: ["dashboard", "budget", "employes", "hypotheses", "departements", "rapports"],
  ACCOUNTING: ["acct_dashboard", "acct_bv", "acct_bilan", "acct_pnl", "acct_cashflow", "acct_audit", "acct_qc9434"],
  FIXED_ASSETS: ["fixed_assets_home"],
  CONSOLIDATION: ["consolidation_home"],
};

const NAV_PLATFORM = [
  { key: "platform_home", label: "Tableau de bord", sub: "Pilotage plateforme", icon: LayoutDashboard },
  { key: "platform_clients", label: "Sociétés / Clients", sub: "Registre des sociétés", icon: Building2 },
];
const NAV_PLATFORM_LOGS = { key: "platform_logs", label: "Logs plateforme", sub: "Audit plateforme", icon: ScrollText };

const NAV_ACCT = [
  { key: "acct_dashboard", label: "Tableau de bord", sub: "Vue d'ensemble", icon: LayoutDashboard },
  { key: "acct_bv", label: "Balance de vérification", sub: "Upload mensuel", icon: ClipboardList },
  { key: "acct_audit", label: "Rapports", sub: "Génération centralisée", icon: FileText },
  { key: "acct_qc9434", label: "9434-3977 QC inc.", sub: "Commandité", icon: Building },
];

const NAV_GROUP = [
  { key: "dashboard", label: "Tableau de bord", sub: "Vue globale", icon: LayoutDashboard },
];
const NAV_FOUNDATION = [
  { key: "companies", label: "Sociétés / Mandats", sub: "Portefeuille & affectations", icon: Building2 },
];
const BUDGET_PARENT = { key: "budget", label: "Salaires & Budget", sub: "Saisie & calculs", icon: DollarSign };
const BUDGET_CHILDREN = [
  { key: "employes", label: "Employés", icon: Users },
  { key: "hypotheses", label: "Hypothèses", icon: Settings },
  { key: "departements", label: "Départements", icon: Building2 },
  { key: "rapports", label: "Rapports", icon: FileText },
];
const NAV_BOTTOM = [
  { key: "companies", label: "Sociétés / Clients", sub: "Portefeuille & création", icon: Building2 },
  { key: "access", label: "Utilisateurs et accès", sub: "Invitations & permissions", icon: ShieldCheck },
  { key: "logs", label: "Logs", sub: "Historique des activités", icon: ScrollText },
];

export function MeeloraLogo({ compact = false, className = "" }) {
  return (
    <img
      src={compact ? "/meelora-mark.png" : "/meelora-logo.png"}
      alt="Meelora"
      data-testid="brand-logo"
      draggable={false}
      className={`${compact ? "h-7" : "h-8"} w-auto select-none ${className}`}
    />
  );
}

const ROLE_META = {
  admin: { label: "Admin", c: "#0F172A" },
  editor: { label: "Utilisateur", c: "#64748B" },
  user: { label: "Utilisateur", c: "#64748B" },
};

function getInitials(name) {
  const parts = (name || "").trim().split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return "U";
}

function NotificationsBell({ go }) {
  const [data, setData] = useState({ count: 0, items: [] });
  useEffect(() => {
    const load = () => api.getNotifications().then(setData).catch(() => {});
    load();
    const id = setInterval(load, 60000);
    return () => clearInterval(id);
  }, []);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button data-testid="header-notif-btn" title="Notifications" className="relative hidden rounded-full p-2 text-slate-500 transition-colors hover:bg-[#F3F4F6] hover:text-[#0F172A] sm:block">
          <Bell size={18} />
          {data.count > 0
            ? <span data-testid="notif-badge" className="absolute -right-0.5 -top-0.5 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-700 text-white">{data.count > 9 ? "9+" : data.count}</span>
            : <span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full bg-[#22C55E]" />}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={8} className="w-80 max-h-[70vh] overflow-auto" data-testid="notif-menu">
        <div className="px-3 py-2 text-sm font-700 text-[#0F172A]">Notifications{data.count > 0 && <span className="font-500 text-slate-400"> · {data.count}</span>}</div>
        <DropdownMenuSeparator />
        {(!data.items || data.items.length === 0) && <div className="px-3 py-6 text-center text-xs text-slate-400" data-testid="notif-empty">Aucune alerte pour le moment 🎉</div>}
        {(data.items || []).map((n) => (
          <DropdownMenuItem key={n.id + n.type} data-testid="notif-item" onSelect={() => go(n.target)} className="flex items-start gap-2.5 py-2">
            <span className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${n.severity === "high" ? "bg-red-500/12 text-red-600" : "bg-[#FBBF24]/15 text-[#B45309]"}`}><AlertTriangle size={13} /></span>
            <span className="min-w-0">
              <p className="truncate text-xs font-600 text-[#0F172A]">{n.title}</p>
              <p className="truncate text-[11px] text-slate-400">{n.detail}</p>
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu({ user, logout, go, t }) {
  const [ts, setTs] = useState(0);
  const [hasAvatar, setHasAvatar] = useState(!!user?.has_avatar);
  const fileRef = useRef(null);
  const role = ROLE_META[user?.role] || ROLE_META.user;
  const initials = getInitials(user?.name);
  const src = user?.id ? `${process.env.REACT_APP_BACKEND_URL}/api/users/${user.id}/avatar?v=${ts}` : undefined;

  const onFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 5 * 1024 * 1024) { toast.error("Image trop volumineuse (max 5 Mo)"); e.target.value = ""; return; }
    try { await api.uploadAvatar(f); setHasAvatar(true); setTs(Date.now()); toast.success("Photo de profil mise à jour"); }
    catch { toast.error("Échec du téléversement"); }
    e.target.value = "";
  };
  const onRemove = async () => {
    try { await api.deleteAvatar(); setHasAvatar(false); setTs(Date.now()); toast.success("Photo retirée"); }
    catch { toast.error("Échec de la suppression"); }
  };

  return (
    <DropdownMenu>
      <input type="file" ref={fileRef} accept="image/*" className="hidden" onChange={onFile} data-testid="avatar-file-input" />
      <DropdownMenuTrigger asChild>
        <button data-testid="user-menu-toggle" className="rounded-full outline-none ring-offset-2 transition hover:ring-2 hover:ring-[#22C55E]/40 focus-visible:ring-2 focus-visible:ring-[#22C55E]">
          <Avatar className="h-9 w-9 border border-[#F3F4F6]">
            <AvatarImage src={src} alt={user?.name} />
            <AvatarFallback style={{ backgroundColor: role.c }} className="text-xs font-700 text-white">{initials}</AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={8} className="w-64" data-testid="user-menu">
        <div className="flex items-center gap-3 px-2 py-2">
          <div className="group relative shrink-0">
            <Avatar className="h-14 w-14 border border-[#F3F4F6]">
              <AvatarImage src={src} alt={user?.name} />
              <AvatarFallback style={{ backgroundColor: role.c }} className="text-base font-700 text-white">{initials}</AvatarFallback>
            </Avatar>
            <button type="button" data-testid="avatar-change" title="Changer la photo"
              onClick={(e) => { e.preventDefault(); fileRef.current?.click(); }}
              className="absolute inset-0 flex items-center justify-center rounded-full bg-[#0F172A]/55 opacity-0 transition-opacity group-hover:opacity-100">
              <Pencil size={16} className="text-white" />
            </button>
            {hasAvatar && (
              <button type="button" data-testid="avatar-remove" title="Retirer la photo"
                onClick={(e) => { e.preventDefault(); onRemove(); }}
                className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-white opacity-0 shadow transition-opacity group-hover:opacity-100">
                <X size={11} />
              </button>
            )}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <p className="truncate text-sm font-600 text-[#0F172A]">{user?.name}</p>
              <span className="shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-700 uppercase" style={{ backgroundColor: role.c + "1A", color: role.c }}>{t(role.label)}</span>
            </div>
            <p className="truncate text-[11px] text-slate-400">{user?.email}</p>
          </div>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem data-testid="menu-profile" onSelect={() => go("preferences")}>
          <UserCog size={15} className="mr-2 text-slate-500" /> {t("Mon profil")}
        </DropdownMenuItem>
        {user?.role === "admin" && (
          <DropdownMenuItem data-testid="menu-users" onSelect={() => go("utilisateurs")}>
            <ShieldCheck size={15} className="mr-2 text-slate-500" /> {t("Utilisateurs")}
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem data-testid="logout-btn" onSelect={logout} className="text-red-600 focus:bg-red-50 focus:text-red-700">
          <LogOut size={15} className="mr-2" /> {t("Déconnexion")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function NavItem({ item, active, onClick }) {
  const { t } = useLang();
  const Icon = item.icon;
  const on = active === item.key;
  return (
    <button
      data-testid={`nav-${item.key}`}
      onClick={() => onClick(item.key)}
      className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${
        on ? "bg-[#A7F3DD]/40 text-[#0F172A]" : "text-slate-600 hover:bg-[#F3F4F6] hover:text-[#0F172A]"
      }`}
    >
      {on && <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-[#22C55E]" />}
      <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${on ? "bg-[#22C55E] text-white" : "bg-[#F3F4F6] text-slate-500 group-hover:bg-[#A7F3DD]/50 group-hover:text-[#22C55E]"}`}>
        <Icon size={16} strokeWidth={2.2} />
      </span>
      <span className="min-w-0">
        <span className={`block truncate text-sm ${on ? "font-700" : "font-600"}`}>{t(item.label)}</span>
        <span className={`block truncate text-[11px] ${on ? "text-[#22C55E]" : "text-slate-400"}`}>{t(item.sub)}</span>
      </span>
    </button>
  );
}

function NavSubItem({ item, active, onClick }) {
  const { t } = useLang();
  const Icon = item.icon;
  const on = active === item.key;
  return (
    <button data-testid={`nav-${item.key}`} onClick={() => onClick(item.key)}
      className={`group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 ${on ? "bg-[#A7F3DD]/40 font-700 text-[#0F172A]" : "font-600 text-slate-600 hover:bg-[#F3F4F6] hover:text-[#0F172A]"}`}>
      {on && <span className="absolute left-0 top-1/2 h-4 w-1 -translate-y-1/2 rounded-r-full bg-[#22C55E]" />}
      <Icon size={15} strokeWidth={2.2} className={on ? "text-[#22C55E]" : "text-slate-400 group-hover:text-[#22C55E]"} />
      <span className="truncate">{t(item.label)}</span>
    </button>
  );
}

function NavParent({ item, children, active, onClick }) {
  const { t } = useLang();
  const Icon = item.icon;
  const childActive = children.some((c) => c.key === active);
  const on = active === item.key;
  const [open, setOpen] = useState(childActive || on);
  useEffect(() => { if (childActive || on) setOpen(true); }, [childActive, on]);
  return (
    <div>
      <div className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${on ? "bg-[#A7F3DD]/40 text-[#0F172A]" : "text-slate-600 hover:bg-[#F3F4F6] hover:text-[#0F172A]"}`}>
        {on && <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-[#22C55E]" />}
        <button data-testid={`nav-${item.key}`} onClick={() => { onClick(item.key); setOpen(true); }} className="flex min-w-0 flex-1 items-center gap-3 text-left">
          <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${on ? "bg-[#22C55E] text-white" : "bg-[#F3F4F6] text-slate-500 group-hover:bg-[#A7F3DD]/50 group-hover:text-[#22C55E]"}`}>
            <Icon size={16} strokeWidth={2.2} />
          </span>
          <span className="min-w-0">
            <span className={`block truncate text-sm ${on ? "font-700" : "font-600"}`}>{t(item.label)}</span>
            <span className={`block truncate text-[11px] ${on ? "text-[#22C55E]" : "text-slate-400"}`}>{t(item.sub)}</span>
          </span>
        </button>
        <button data-testid={`nav-${item.key}-toggle`} onClick={(e) => { e.stopPropagation(); setOpen((o) => !o); }} className="rounded-md p-1 text-slate-400 hover:text-[#0F172A]">
          {open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        </button>
      </div>
      {open && (
        <div className="mt-1 space-y-1 border-l border-[#F3F4F6] pl-3 ml-5">
          {children.map((c) => <NavSubItem key={c.key} item={c} active={active} onClick={onClick} />)}
        </div>
      )}
    </div>
  );
}

function YearControls() {
  const { years, year, selectYear, refresh } = useYear();
  const { t } = useLang();
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ year: "", source_year: "", source_scenario: "ca" });
  const openDialog = () => {
    const next = Math.max(...years) + 1;
    setF({ year: String(next), source_year: String(year), source_scenario: "ca" });
    setOpen(true);
  };
  const create = async () => {
    try {
      await api.createYear({ year: Number(f.year), source_year: Number(f.source_year), source_scenario: f.source_scenario });
      toast.success(`Année ${f.year} créée (report ${f.source_scenario === "ca" ? "Budget CA" : "Revue"} ${f.source_year})`);
      await refresh(); await selectYear(Number(f.year)); setOpen(false);
    } catch (e) { toast.error(e.response?.data?.detail || "Création impossible"); }
  };
  return (
    <div className="flex items-center gap-2">
      <CalendarRange size={15} className="text-[#0F172A]" />
      <Select value={String(year)} onValueChange={(v) => selectYear(v)}>
        <SelectTrigger className="h-8 w-24" data-testid="header-year-select"><SelectValue /></SelectTrigger>
        <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
      </Select>
      <Button variant="outline" size="sm" className="h-8 gap-1.5" data-testid="new-year-btn" onClick={openDialog}><Plus size={14} /> {t("Année")}</Button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="new-year-dialog">
          <DialogHeader>
            <DialogTitle>{t("Nouvelle année budgétaire")}</DialogTitle>
            <DialogDescription className="text-xs">{t("Le scénario source de l'année de départ devient le « Salaire actuel » de la nouvelle année.")}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-3 py-1 sm:grid-cols-3">
            <div><label className="text-[11px] uppercase text-slate-500">{t("Nouvelle année")}</label>
              <Input data-testid="ny-year" type="number" className="mt-1 font-mono-data" value={f.year} onChange={(e) => setF((p) => ({ ...p, year: e.target.value }))} /></div>
            <div><label className="text-[11px] uppercase text-slate-500">{t("Année source")}</label>
              <Select value={f.source_year} onValueChange={(v) => setF((p) => ({ ...p, source_year: v }))}>
                <SelectTrigger data-testid="ny-source-year" className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent>{years.map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
              </Select></div>
            <div><label className="text-[11px] uppercase text-slate-500">{t("Report basé sur")}</label>
              <Select value={f.source_scenario} onValueChange={(v) => setF((p) => ({ ...p, source_scenario: v }))}>
                <SelectTrigger data-testid="ny-source-scenario" className="mt-1"><SelectValue /></SelectTrigger>
                <SelectContent><SelectItem value="ca">{t("Budget CA")}</SelectItem><SelectItem value="revue1">{t("Revue Budgétaire 1")}</SelectItem><SelectItem value="revue2">{t("Revue Budgétaire 2")}</SelectItem></SelectContent>
              </Select></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>{t("Annuler")}</Button>
            <Button data-testid="ny-create-btn" className="bg-[#0F172A] hover:bg-[#0F172A]/90" onClick={create}>{t("Créer l'année")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function Layout() {
  return <YearProvider><LayoutInner /></YearProvider>;
}

function SectionHeader({ icon: Icon, label }) {
  return (
    <div className="flex items-center gap-2 px-3 pb-1 pt-4">
      <Icon size={13} className="text-[#22C55E]" />
      <span className="overline" style={{ color: "#94A3B8" }}>{label}</span>
    </div>
  );
}

// Shared module rendering (used by the company sidebar AND the platform extension).
function ModulesNav({ modules, active, go }) {
  return (modules || []).map((m) => {
    const cfg = MODULE_NAV[m.module_code];
    if (!cfg) return null;
    return (
      <div key={m.module_code} data-testid={`nav-module-${m.module_code}`}>
        <SectionHeader icon={cfg.icon} label={cfg.label} />
        {cfg.type === "parent" && (
          <>
            <NavItem item={{ key: "dashboard", label: "Tableau de bord", sub: "Vue budgétaire", icon: LayoutDashboard }} active={active} onClick={go} />
            <NavParent item={cfg.parent} children={BUDGET_CHILDREN} active={active} onClick={go} />
          </>
        )}
        {cfg.type === "group" && NAV_ACCT.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
        {cfg.type === "item" && <NavItem item={cfg.item} active={active} onClick={go} />}
      </div>
    );
  });
}

function DynamicCompanyNav({ manifest, active, go, companies, activeCompanyId }) {
  const modules = manifest?.modules || [];
  const adminView = !!manifest?.admin_view;
  const activeCompany = (companies || []).find((c) => c.id === activeCompanyId);
  const multi = (companies || []).length > 1;
  return (
    <div data-testid="company-nav">
      {multi && (
        <NavItem item={{ key: "mandats_list", label: "Tous les mandats", sub: "Vos sociétés accessibles", icon: Building2 }} active={active} onClick={go} />
      )}

      {activeCompany && (
        <div className="mt-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5" data-testid="active-mandat">
          <span className="overline block" style={{ color: "#94A3B8" }}>Mandat actif</span>
          <span className="mt-0.5 block truncate text-sm font-700 text-[#063044]" data-testid="active-mandat-name">{activeCompany.name}</span>
        </div>
      )}

      {!activeCompanyId && (
        <p className="px-3 py-6 text-xs text-slate-400" data-testid="company-nav-choose">Choisissez un mandat dans « Tous les mandats » pour afficher ses modules.</p>
      )}
      {activeCompanyId && modules.length === 0 && (
        <p className="px-3 py-4 text-xs text-slate-400" data-testid="company-nav-empty">Aucun module ne vous est attribué pour ce mandat.</p>
      )}

      <ModulesNav modules={modules} active={active} go={go} />

      {adminView && (
        <div className="pt-4" data-testid="nav-admin-section">
          <SectionHeader icon={ShieldCheck} label="Administration" />
          {NAV_BOTTOM.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
        </div>
      )}
    </div>
  );
}

function CompanySelector({ active, onNavigate }) {
  const [companies, setCompanies] = useState([]);
  useEffect(() => { api.getCompanies().then(setCompanies).catch(() => setCompanies([])); }, []);
  if (!companies.length) return null;
  // Mandat actif déduit de la page : la page dédiée 9434 → qc9434 ; toutes les autres pages Compta → acct (Meelora).
  const activePrefix = active === "acct_qc9434" ? "qc9434" : "acct";
  const TARGET = { acct: "acct_dashboard", qc9434: "acct_qc9434" };
  return (
    <div className="flex items-center gap-2" data-testid="company-selector">
      <Building2 size={15} className="text-[#0F172A]" />
      <Select value={activePrefix} onValueChange={(v) => onNavigate(TARGET[v] || "acct_dashboard")}>
        <SelectTrigger className="h-8 w-[190px]" data-testid="company-select"><SelectValue /></SelectTrigger>
        <SelectContent>
          {companies.map((c) => (
            <SelectItem key={c.legacy_prefix} value={c.legacy_prefix} data-testid={`company-option-${c.legacy_prefix}`}>{c.name}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

function LayoutInner() {
  const { user, logout } = useAuth();
  const { t } = useLang();
  const isPlatformStaff = !!user?.platform_role;
  const [active, setActive] = useState(() => {
    try {
      const s = localStorage.getItem("acct:lastPage");
      if (s && PAGES[s]) {
        if (isPlatformStaff && !s.startsWith("platform_")) return "platform_home";
        return s;
      }
    } catch (e) { /* ignore */ }
    return isPlatformStaff ? "platform_home" : "dashboard";
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [avatarColor, setAvatarColor] = useState("#FBBF24");
  const [presentation, setPresentation] = useState(false);
  // P1.13E — dynamic company navigation (backend authority).
  const [navCompanies, setNavCompanies] = useState([]);
  const [activeCompanyId, setActiveCompanyId] = useState(() => {
    try { return localStorage.getItem("meelora:activeCompany") || null; } catch (e) { return null; }
  });
  const [navManifest, setNavManifest] = useState(null);
  const isPlatformPage = active.startsWith("platform_");
  const page = PAGES[active] || PAGES.dashboard;
  const Active = page.comp;
  const go = (k) => { setActive(k); setMobileOpen(false); };
  useEffect(() => { try { localStorage.setItem("acct:lastPage", active); } catch (e) { /* ignore */ } }, [active]);
  // Companies the user may operate in (platform staff — to reach "Société Meelora"
  // — AND business users).
  useEffect(() => {
    api.getCompanyContext().then((d) => {
      const cs = d.companies || [];
      setNavCompanies(cs);
      if (!isPlatformStaff) {
        setActiveCompanyId((prev) => (prev && cs.some((c) => c.id === prev)) ? prev : (cs[0]?.id || null));
      }
    }).catch(() => setNavCompanies([]));
  }, [isPlatformStaff]);
  // Recompute the sidebar manifest whenever the active company changes.
  useEffect(() => {
    if (!activeCompanyId) { setNavManifest(null); return; }
    api.getCompanyNavigation(activeCompanyId).then(setNavManifest).catch(() => setNavManifest({ modules: [], admin_view: false }));
  }, [activeCompanyId]);
  const switchCompany = (cid) => {
    setActiveCompanyId(cid);
    try { localStorage.setItem("meelora:activeCompany", cid); } catch (e) { /* ignore */ }
  };
  const enterMandat = (cid) => { switchCompany(cid); setActive("dashboard"); setMobileOpen(false); };
  // Platform staff: "Accéder" on Société Meelora opens its full operational
  // management console (users / invitations / module access / sensitive perms /
  // effective access). It NEVER adds financial modules to the platform sidebar
  // and grants no financial authority (platform_role ≠ authority).
  const enterMeelora = () => { setActive("platform_meelora_manage"); setMobileOpen(false); };
  const LANDING = { REPORTING: "reporting_home", BUDGETS: "budget", ACCOUNTING: "acct_dashboard", FIXED_ASSETS: "fixed_assets_home", CONSOLIDATION: "consolidation_home" };
  const moduleEntry = (mods, adminView) => {
    if (adminView) return "dashboard";
    if (mods.some((m) => m.module_code === "ACCOUNTING")) return "acct_dashboard"; // Comptabilité prioritaire
    if (mods.some((m) => m.module_code === "BUDGETS")) return "dashboard";
    return mods.length ? (LANDING[mods[0].module_code] || "dashboard") : "dashboard";
  };
  const allowedBusinessPages = (mods, adminView) => {
    const allowed = new Set(["preferences", "mandats_list"]);
    if (adminView) ["companies", "access", "logs", "utilisateurs", "dashboard"].forEach((k) => allowed.add(k));
    mods.forEach((m) => (MODULE_PAGES[m.module_code] || []).forEach((k) => allowed.add(k)));
    return allowed;
  };
  // Non-platform business users: land on modules (Comptabilité first); multi-mandate
  // users land on "Tous les mandats" (client home with Accéder). No ghost pages.
  useEffect(() => {
    if (isPlatformStaff || !navManifest || active.startsWith("platform_")) return;
    const mods = navManifest.modules || [];
    const adminView = !!navManifest.admin_view;
    const multi = navCompanies.length > 1;
    const allowed = allowedBusinessPages(mods, adminView);
    if (!allowed.has(active)) { setActive(multi && !adminView ? "mandats_list" : moduleEntry(mods, adminView)); return; }
    if (active === "dashboard" && !adminView) {
      if (multi) { setActive("mandats_list"); return; }
      const entry = moduleEntry(mods, adminView);
      if (entry !== "dashboard") setActive(entry);
    }
  }, [navManifest, navCompanies]); // eslint-disable-line react-hooks/exhaustive-deps
  // Platform staff stay within platform pages only. Business modules never
  // appear in the platform sidebar; Société Meelora modules are managed from its
  // console (platform_meelora_manage), never granted to the platform admin.
  useEffect(() => {
    if (!isPlatformStaff) return;
    if (!active.startsWith("platform_") && active !== "preferences") setActive("platform_home");
  }, [isPlatformStaff, active]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const handler = (e) => { if (e.detail) { setActive(e.detail); setMobileOpen(false); } };
    window.addEventListener("acct-navigate", handler);
    return () => window.removeEventListener("acct-navigate", handler);
  }, []);
  useEffect(() => {
    const ph = (e) => setPresentation(!!e.detail);
    const fh = () => { if (!document.fullscreenElement) setPresentation(false); };
    window.addEventListener("acct-presentation", ph);
    document.addEventListener("fullscreenchange", fh);
    return () => { window.removeEventListener("acct-presentation", ph); document.removeEventListener("fullscreenchange", fh); };
  }, []);
  const exitPresentation = () => { try { document.exitFullscreen?.(); } catch (e) { /* ignore */ } setPresentation(false); };
  const isPlaceholderPage = ["reporting_home", "fixed_assets_home", "consolidation_home", "mandats_list"].includes(active);
  const breadcrumbSection = isPlatformPage ? "Plateforme Meelora"
    : active === "mandats_list" ? "Tous les mandats"
    : active === "reporting_home" ? "Reporting"
    : active === "fixed_assets_home" ? "Immobilisations"
    : active === "consolidation_home" ? "Consolidation"
    : active === "companies" ? t(user?.workspace?.organization_type === "fiduciary" ? "Mandats" : "Sociétés")
    : active === "access" || active === "logs" || active === "utilisateurs" ? "Administration"
    : active.startsWith("acct_") ? t("Comptabilité")
    : active === "dashboard" ? t("Vue globale")
    : "Gestion des Budgets";
  const roleMeta = { admin: { label: "Admin", c: "#0F172A", t: "#93B4FF" }, editor: { label: "Utilisateur", c: "#64748B", t: "#94A3B8" }, user: { label: "Utilisateur", c: "#64748B", t: "#94A3B8" } }[user?.role] || { label: "Utilisateur", c: "#64748B", t: "#94A3B8" };
  useEffect(() => { api.getPreferences().then((p) => { applyTheme(p?.theme); if (p?.avatar_color) setAvatarColor(p.avatar_color); }).catch(() => {}); }, []);

  return (
    <div className="flex min-h-screen bg-[#F3F4F6]">
      {mobileOpen && <div className="fixed inset-0 z-30 bg-black/50 lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-overlay" />}
      <aside className={`fixed left-0 top-0 z-40 flex h-screen w-64 flex-col border-r border-[#F3F4F6] bg-white px-3 py-4 transition-transform duration-200 ${presentation ? "-translate-x-full" : "lg:translate-x-0"} ${mobileOpen ? "translate-x-0" : "-translate-x-full"}`}>
        <div className="mb-6 flex items-center justify-between gap-2.5 px-2">
          <MeeloraLogo />
          <button className="rounded-lg p-1.5 text-slate-500 hover:bg-[#F3F4F6] lg:hidden" onClick={() => setMobileOpen(false)} data-testid="sidebar-close-btn"><X size={20} /></button>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto">
          {isPlatformStaff ? (
            <div className="flex h-full flex-col" data-testid="platform-nav">
              <div className="flex items-center gap-2 px-3 pb-1 pt-1">
                <Server size={13} className="text-[#15AF97]" />
                <span className="overline" style={{ color: "#94A3B8" }}>Plateforme Meelora</span>
              </div>
              {NAV_PLATFORM.map((i) => <NavItem key={i.key} item={i} active={active} onClick={go} />)}
              <div className="mt-auto border-t border-slate-200 pt-3" data-testid="platform-logs-anchor">
                <NavItem item={NAV_PLATFORM_LOGS} active={active} onClick={go} />
              </div>
            </div>
          ) : (
          <DynamicCompanyNav
            manifest={navManifest}
            active={active}
            go={go}
            companies={navCompanies}
            activeCompanyId={activeCompanyId}
          />
          )}
        </nav>
      </aside>

      <div className={`flex-1 ${presentation ? "" : "lg:ml-64"}`}>
        {!presentation && (
        <header className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-200 bg-white/80 px-4 py-4 backdrop-blur-xl sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-2.5">
            <button className="rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setMobileOpen(true)} data-testid="sidebar-open-btn"><Menu size={22} /></button>
            <div className="min-w-0">
              <p className="overline mb-0.5" data-testid="breadcrumb">{breadcrumbSection} <span className="mx-1 text-slate-300">›</span> {t(page.title)}</p>
              <h2 className="font-display truncate text-lg font-800 tracking-tight text-[#0F172A] dark:text-white sm:text-2xl">{t(page.title)}</h2>
              <p className="truncate text-xs text-slate-500">{t(page.sub)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            {!isPlatformPage && active.startsWith("acct_") && <CompanySelector active={active} onNavigate={go} />}
            {!isPlatformPage && !isPlaceholderPage && !active.startsWith("acct_") && <span className="hidden rounded-full bg-[#22C55E]/10 px-3 py-1 text-xs font-600 text-[#22C55E] sm:inline-flex">{t("Budget actif")}</span>}
            {!isPlatformPage && !isPlaceholderPage && !active.startsWith("acct_") && <YearControls />}
            <div className="ml-1 flex items-center gap-1 border-l border-slate-200 pl-2">
              <button data-testid="header-help-btn" title={t("Aide")} className="hidden rounded-full p-2 text-slate-500 transition-colors hover:bg-[#F3F4F6] hover:text-[#0F172A] sm:block"><HelpCircle size={18} /></button>
              <NotificationsBell go={go} />
              <UserMenu user={user} logout={logout} go={go} t={t} />
            </div>
          </div>
        </header>
        )}
        {presentation && (
          <button onClick={exitPresentation} data-testid="presentation-exit-btn" title="Quitter le mode présentation"
            className="fixed right-4 top-4 z-50 inline-flex items-center gap-1.5 rounded-full bg-[#0F172A] px-3 py-1.5 text-xs font-600 text-white shadow-lg hover:bg-[#0F172A]/90">
            <Minimize2 size={14} /> Quitter
          </button>
        )}
        <main className={presentation ? "p-3" : "p-4 sm:p-6 lg:p-8"}>
          <NavContext.Provider value={{ go, enterMandat, enterMeelora, activeCompanyId, companies: navCompanies }}>
            <Active />
          </NavContext.Provider>
        </main>
        {!presentation && (
          <footer className="mt-4 flex flex-col items-center justify-between gap-2 border-t border-[#F3F4F6] px-4 py-5 sm:flex-row sm:px-6 lg:px-8" data-testid="app-footer">
            <div className="flex items-center gap-2">
              <MeeloraLogo compact />
              <span className="text-xs text-slate-400">© 2026 Meelora inc. Tous droits réservés.</span>
            </div>
            <div className="flex items-center gap-4 text-xs text-slate-400">
              <button className="hover:text-[#22C55E]" data-testid="footer-privacy">Confidentialité</button>
              <button className="hover:text-[#22C55E]" data-testid="footer-terms">Conditions d'utilisation</button>
              <button className="hover:text-[#22C55E]" data-testid="footer-help" onClick={() => go("preferences")}>Aide</button>
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}
