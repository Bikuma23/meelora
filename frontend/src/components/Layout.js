import { useState, useEffect, useRef } from "react";
import { useAuth } from "../context/AuthContext";
import { YearProvider, useYear } from "../context/YearContext";
import { useLang } from "../context/LanguageContext";
import {
  LayoutDashboard, Users, DollarSign, Settings, Building2, FileText, ScrollText, LogOut, Briefcase, Plus, CalendarRange, ShieldCheck, Menu, X, UserCog, ChevronUp, ChevronDown, ChevronRight, Minimize2, HelpCircle, Bell, Camera, Trash2, Pencil, AlertTriangle, Layers, Globe, ShieldAlert,
} from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./ui/select";
import { Avatar, AvatarImage, AvatarFallback } from "./ui/avatar";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubTrigger, DropdownMenuSubContent } from "./ui/dropdown-menu";
import { Popover, PopoverTrigger, PopoverContent } from "./ui/popover";
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
import { AcctEntries, AcctPeriods, makePlaceholder } from "../pages/AccountingA1";
import SalesAR from "../pages/SalesAR";
import CompanyHome from "../pages/CompanyHome";
import QcEntity from "../pages/QcEntity";
import { PlatformHome, PlatformClients, PlatformLogs, PlatformMeeloraManage } from "../pages/Platform";
import { ReportingHome, FixedAssetsHome, ConsolidationHome } from "../pages/ModulePlaceholder";
import MandatsList from "../pages/MandatsList";
import { NavContext } from "../context/NavContext";
import { Calculator, Landmark, FileBarChart, Server, BookOpen, Receipt, ShoppingCart, ClipboardCheck, Banknote, BookText, Scale, ListTree, PieChart, Percent, Boxes, Lock } from "lucide-react";

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
  company_home: { title: "Accueil", sub: "Point d'entrée du mandat", comp: CompanyHome },
  acct_dashboard: { title: "Tableau de bord", sub: "Vue d'ensemble du mois", comp: AcctDashboard },
  acct_bv: { title: "Balance de vérification", sub: "Upload & gestion mensuelle", comp: AcctBV },
  acct_bilan: { title: "Bilan", sub: "État de situation financière", comp: AcctBilan },
  acct_pnl: { title: "État des résultats", sub: "P&L du mois", comp: AcctPnl },
  acct_cashflow: { title: "Flux de trésorerie", sub: "Méthode indirecte", comp: AcctCashflow },
  acct_audit: { title: "Rapports", sub: "Génération centralisée", comp: AcctReports },
  acct_qc9434: { title: "9434-3977 QC inc.", sub: "Commandité", comp: QcEntity },
  // ACCOUNTING A1 — shell (Comptabilité en accordéon, 15 sous-menus).
  acct_overview: { title: "Aperçu", sub: "Comptabilité", comp: makePlaceholder("Aperçu comptable", "Vue d'ensemble du module Comptabilité (à venir).") },
  acct_apercu: { title: "Aperçu", sub: "Comptabilité", comp: makePlaceholder("Aperçu comptable", "Vue d'ensemble du module Comptabilité (à venir).") },
  acct_sales: { title: "Ventes & Clients", sub: "Comptabilité", comp: SalesAR },
  acct_purchases: { title: "Achats & Fournisseurs", sub: "Comptabilité", comp: makePlaceholder("Achats & Fournisseurs") },
  acct_po: { title: "Bons de commande", sub: "Comptabilité", comp: makePlaceholder("Bons de commande") },
  acct_bank: { title: "Banque & Trésorerie", sub: "Comptabilité", comp: makePlaceholder("Banque & Trésorerie") },
  acct_entries: { title: "Écritures comptables", sub: "Grand livre", comp: AcctEntries },
  acct_ledger: { title: "Grand livre", sub: "Comptabilité", comp: makePlaceholder("Grand livre") },
  acct_tb: { title: "Balance de vérification", sub: "Comptabilité", comp: makePlaceholder("Balance de vérification") },
  acct_coa: { title: "Plan comptable", sub: "Comptabilité", comp: makePlaceholder("Plan comptable") },
  acct_analytics: { title: "Analytique & Projets", sub: "Comptabilité", comp: makePlaceholder("Analytique & Projets") },
  acct_taxes: { title: "Taxes", sub: "Comptabilité", comp: makePlaceholder("Taxes") },
  acct_assets: { title: "Actifs & amortissements", sub: "Comptabilité", comp: makePlaceholder("Actifs & amortissements") },
  acct_close: { title: "Clôture & Réconciliation", sub: "Périodes GL", comp: AcctPeriods },
  acct_imports: { title: "Imports & Migration", sub: "Comptabilité", comp: makePlaceholder("Imports & Migration") },
  acct_reports2: { title: "Rapports & Analyses", sub: "Comptabilité", comp: makePlaceholder("Rapports & Analyses") },
  rep_statements: { title: "États financiers", sub: "Reporting", comp: makePlaceholder("États financiers") },
  rep_analytics: { title: "Analyses", sub: "Reporting", comp: makePlaceholder("Analyses") },
  fa_registry: { title: "Registre des actifs", sub: "Immobilisations", comp: makePlaceholder("Registre des actifs") },
  fa_depreciation: { title: "Amortissements", sub: "Immobilisations", comp: makePlaceholder("Amortissements") },
  fa_disposals: { title: "Cessions", sub: "Immobilisations", comp: makePlaceholder("Cessions") },
  cons_scope: { title: "Périmètre", sub: "Consolidation", comp: makePlaceholder("Périmètre de consolidation") },
  cons_elim: { title: "Éliminations", sub: "Consolidation", comp: makePlaceholder("Éliminations") },
  cons_statements: { title: "États consolidés", sub: "Consolidation", comp: makePlaceholder("États consolidés") },
  platform_home: { title: "Tableau de bord", sub: "Supervision Meelora", comp: PlatformHome },
  platform_clients: { title: "Sociétés / Clients", sub: "Registre des sociétés Meelora", comp: PlatformClients },
  platform_meelora_manage: { title: "Société Meelora — Gestion", sub: "Environnement opérationnel interne", comp: PlatformMeeloraManage },
  platform_logs: { title: "Logs plateforme", sub: "Audit des évènements plateforme", comp: PlatformLogs },
  mandats_list: { title: "Tous les mandats", sub: "Vos sociétés accessibles", comp: MandatsList },
  reporting_home: { title: "Reporting", sub: "Module Reporting", comp: ReportingHome },
  fixed_assets_home: { title: "Immobilisations", sub: "Module Immobilisations", comp: FixedAssetsHome },
  consolidation_home: { title: "Consolidation", sub: "Module Consolidation", comp: ConsolidationHome },
};

// P1.13E — module canonique -> configuration du panneau flottant (flyout).
// Aucun menu n'est déduit de user.role : le manifest/effective access décide de
// la visibilité des modules racines ; les sous-menus n'accordent aucun droit.
const MODULE_FLYOUT = {
  REPORTING: { label: "Reporting", icon: FileBarChart, landing: "reporting_home",
    groups: [{ label: null, items: [
      { key: "reporting_home", label: "Aperçu", icon: LayoutDashboard },
      { key: "rep_statements", label: "États financiers", icon: FileText },
      { key: "rep_analytics", label: "Analyses", icon: PieChart },
    ] }] },
  BUDGETS: { label: "Gestion des Budgets", icon: DollarSign, landing: "dashboard",
    groups: [{ label: null, items: [
      { key: "dashboard", label: "Aperçu", icon: LayoutDashboard },
      { key: "budget", label: "Salaires & Budget", icon: DollarSign },
      { key: "employes", label: "Employés", icon: Users },
      { key: "hypotheses", label: "Hypothèses", icon: Settings },
      { key: "departements", label: "Départements", icon: Building2 },
      { key: "rapports", label: "Rapports", icon: FileText },
    ] }] },
  ACCOUNTING: { label: "Comptabilité", icon: Calculator, landing: "acct_apercu",
    groups: [
      { label: "Opérations", items: [
        { key: "acct_apercu", label: "Aperçu", icon: LayoutDashboard },
        { key: "acct_sales", label: "Ventes & Clients", icon: Receipt },
        { key: "acct_purchases", label: "Achats & Fournisseurs", icon: ShoppingCart },
        { key: "acct_po", label: "Bons de commande", icon: ClipboardCheck },
        { key: "acct_bank", label: "Banque & Trésorerie", icon: Banknote },
      ] },
      { label: "Comptabilité", items: [
        { key: "acct_entries", label: "Écritures comptables", icon: BookOpen },
        { key: "acct_ledger", label: "Grand livre", icon: BookText },
        { key: "acct_tb", label: "Balance de vérification", icon: Scale },
        { key: "acct_coa", label: "Plan comptable", icon: ListTree },
        { key: "acct_analytics", label: "Analytique & Projets", icon: PieChart },
        { key: "acct_taxes", label: "Taxes", icon: Percent },
        { key: "acct_assets", label: "Actifs & amortissements", icon: Landmark },
      ] },
      { label: "Contrôle & analyse", items: [
        { key: "acct_close", label: "Clôture & Réconciliation", icon: Lock },
        { key: "acct_imports", label: "Imports & Migration", icon: Boxes },
        { key: "acct_reports2", label: "Rapports & Analyses", icon: FileBarChart },
      ] },
    ] },
  FIXED_ASSETS: { label: "Immobilisations", icon: Landmark, landing: "fixed_assets_home",
    groups: [{ label: null, items: [
      { key: "fixed_assets_home", label: "Aperçu", icon: LayoutDashboard },
      { key: "fa_registry", label: "Registre des actifs", icon: ListTree },
      { key: "fa_depreciation", label: "Amortissements", icon: Percent },
      { key: "fa_disposals", label: "Cessions", icon: Boxes },
    ] }] },
  CONSOLIDATION: { label: "Consolidation", icon: Layers, landing: "consolidation_home",
    groups: [{ label: null, items: [
      { key: "consolidation_home", label: "Aperçu", icon: LayoutDashboard },
      { key: "cons_scope", label: "Périmètre", icon: Building2 },
      { key: "cons_elim", label: "Éliminations", icon: Scale },
      { key: "cons_statements", label: "États consolidés", icon: FileBarChart },
    ] }] },
};
// Pages autorisées par module (dérivées du flyout) — cohérence page active/droits.
const MODULE_PAGES = Object.fromEntries(Object.entries(MODULE_FLYOUT).map(([code, cfg]) => [
  code, cfg.groups.flatMap((g) => g.items.map((i) => i.key)),
]));
// ACCOUNTING englobe fonctionnellement les pages Comptabilité legacy déjà câblées.
MODULE_PAGES.ACCOUNTING = [...MODULE_PAGES.ACCOUNTING, "acct_dashboard", "acct_bv", "acct_bilan", "acct_pnl", "acct_cashflow", "acct_audit", "acct_qc9434", "acct_overview"];

const NAV_PLATFORM = [
  { key: "platform_home", label: "Tableau de bord", sub: "Pilotage plateforme", icon: LayoutDashboard },
  { key: "platform_clients", label: "Sociétés / Clients", sub: "Registre des sociétés", icon: Building2 },
];
const NAV_PLATFORM_LOGS = { key: "platform_logs", label: "Logs plateforme", sub: "Audit plateforme", icon: ScrollText };

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

// Langues disponibles (ordre alphabétique en français). DE/IT sélectionnables
// une fois traduites — désactivées tant que les ressources n'existent pas.
const LANGUAGES = [
  { code: "de", label: "Allemand", enabled: false },
  { code: "en", label: "Anglais", enabled: true },
  { code: "fr", label: "Français", enabled: true },
  { code: "it", label: "Italien", enabled: false },
];

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

function UserMenu({ user, logout, go, t, adminView }) {
  const { lang, setLang } = useLang();
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
        {adminView && (
          <>
            <DropdownMenuSeparator />
            <div className="px-2 pb-1 pt-1.5 overline" style={{ color: "#94A3B8" }} data-testid="menu-admin-section">{t("Administration")}</div>
            <DropdownMenuItem data-testid="menu-admin" onSelect={() => go("access")}>
              <ShieldCheck size={15} className="mr-2 text-slate-500" /> {t("Utilisateurs et accès")}
            </DropdownMenuItem>
            <DropdownMenuItem data-testid="menu-logs" onSelect={() => go("logs")}>
              <ScrollText size={15} className="mr-2 text-slate-500" /> {t("Logs société")}
            </DropdownMenuItem>
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuSub>
          <DropdownMenuSubTrigger data-testid="menu-language">
            <Globe size={15} className="mr-2 text-slate-500" /> {t("Langue")}
            <span className="ml-auto text-xs font-700 text-slate-400">{(LANGUAGES.find((l) => l.code === lang) || {}).label ? t((LANGUAGES.find((l) => l.code === lang)).label) : lang.toUpperCase()}</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent data-testid="menu-language-list">
            {LANGUAGES.map((l) => (
              <DropdownMenuItem key={l.code} data-testid={`lang-option-${l.code}`}
                disabled={!l.enabled}
                onSelect={(e) => { if (!l.enabled) { e.preventDefault(); return; } setLang(l.code); }}
                className={lang === l.code ? "font-700 text-[#063044]" : ""}>
                <span className="mr-2 w-6 text-[10px] font-700 uppercase text-slate-400">{l.code}</span>
                {t(l.label)}
                {!l.enabled && <span className="ml-auto text-[10px] text-slate-300">{t("bientôt")}</span>}
                {lang === l.code && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-[#22C55E]" />}
              </DropdownMenuItem>
            ))}
          </DropdownMenuSubContent>
        </DropdownMenuSub>
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

// Reusable floating module navigation (popover) — same UX principle as the avatar
// menu. The sidebar stays compact (root modules only); sub-menus live in the flyout
// and never grant any authorization (P1.13 remains the sole authority).
function ModuleFlyout({ code, active, go, openModule, setOpenModule }) {
  const { t } = useLang();
  const cfg = MODULE_FLYOUT[code];
  if (!cfg) return null;
  const Icon = cfg.icon;
  const moduleActive = (MODULE_PAGES[code] || []).includes(active);
  const open = openModule === code;
  return (
    <Popover open={open} onOpenChange={(o) => setOpenModule(o ? code : null)}>
      <PopoverTrigger asChild>
        <button data-testid={`nav-module-${code}`}
          className={`group relative flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-150 ${moduleActive ? "bg-[#A7F3DD]/40 text-[#0F172A]" : "text-slate-600 hover:bg-[#F3F4F6] hover:text-[#0F172A]"}`}>
          {moduleActive && <span className="absolute left-0 top-1/2 h-6 w-1 -translate-y-1/2 rounded-r-full bg-[#22C55E]" />}
          <span className={`flex h-8 w-8 items-center justify-center rounded-lg transition-colors ${moduleActive ? "bg-[#22C55E] text-white" : "bg-[#F3F4F6] text-slate-500 group-hover:bg-[#A7F3DD]/50 group-hover:text-[#22C55E]"}`}><Icon size={16} strokeWidth={2.2} /></span>
          <span className="min-w-0 flex-1"><span className={`block truncate text-sm ${moduleActive ? "font-700" : "font-600"}`}>{t(cfg.label)}</span></span>
          <ChevronRight size={15} className={`shrink-0 text-slate-400 transition-transform ${open ? "rotate-90 text-[#22C55E]" : ""}`} />
        </button>
      </PopoverTrigger>
      <PopoverContent side="right" align="start" sideOffset={12} collisionPadding={12}
        className="w-72 max-h-[85vh] overflow-auto p-2" data-testid={`flyout-${code}`}>
        <div className="flex items-center gap-2 px-2 pb-2 pt-1">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#22C55E]/12 text-[#22C55E]"><Icon size={15} /></span>
          <span className="text-sm font-700 text-[#0F172A]">{t(cfg.label)}</span>
        </div>
        {cfg.groups.map((g, gi) => (
          <div key={gi} className="mb-1">
            {g.label && <div className="px-2 pb-1 pt-2 overline" style={{ color: "#94A3B8" }}>{t(g.label)}</div>}
            {g.items.map((it) => {
              const on = active === it.key; const I = it.icon;
              return (
                <button key={it.key} data-testid={`nav-${it.key}`} onClick={() => { go(it.key); setOpenModule(null); }}
                  className={`group relative flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors duration-150 ${on ? "bg-[#A7F3DD]/40 font-700 text-[#0F172A]" : "font-600 text-slate-600 hover:bg-[#F3F4F6] hover:text-[#0F172A]"}`}>
                  <I size={15} strokeWidth={2.2} className={on ? "text-[#22C55E]" : "text-slate-400 group-hover:text-[#22C55E]"} />
                  <span className="truncate">{t(it.label)}</span>
                </button>
              );
            })}
          </div>
        ))}
      </PopoverContent>
    </Popover>
  );
}

function ModulesNav({ modules, active, go, openModule, setOpenModule }) {
  // Product composition: when ACCOUNTING is accessible, REPORTING is not a separate
  // root module (its capabilities live in Comptabilité → Rapports & Analyses).
  // This is a navigation rule only; module codes stay canonically distinct and no
  // sensitive permission is ever inferred.
  const codes = (modules || []).map((m) => m.module_code);
  const hasAcct = codes.includes("ACCOUNTING");
  const visible = codes.filter((c) => MODULE_FLYOUT[c] && !(hasAcct && c === "REPORTING"));
  return visible.map((code) => (
    <ModuleFlyout key={code} code={code} active={active} go={go} openModule={openModule} setOpenModule={setOpenModule} />
  ));
}

// Compact active-mandate switcher — shown ONLY once inside a mandate's operational
// env (never on the "Tous les mandats" chooser). Switching recomputes the whole
// sidebar from the new mandate's effective access (fail-closed during load).
function MandatSwitcher({ companies, activeCompanyId, active, go, enterMandat }) {
  const list = companies || [];
  const activeCompany = list.find((c) => c.id === activeCompanyId);
  const multi = list.length > 1;
  if (active === "mandats_list" || !activeCompany) return null;
  if (!multi) {
    return (
      <div className="mb-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2" data-testid="mandat-switcher">
        <span className="overline block" style={{ color: "#94A3B8" }}>Mandat actif</span>
        <span className="mt-0.5 block truncate text-sm font-700 text-[#063044]" data-testid="active-mandat-name">{activeCompany.name}</span>
      </div>
    );
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button data-testid="mandat-switcher" className="mb-2 flex w-full items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-left transition hover:border-[#15AF97]">
          <span className="min-w-0 flex-1">
            <span className="overline block" style={{ color: "#94A3B8" }}>Mandat actif</span>
            <span className="mt-0.5 block truncate text-sm font-700 text-[#063044]" data-testid="active-mandat-name">{activeCompany.name}</span>
          </span>
          <ChevronDown size={15} className="shrink-0 text-slate-400" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60" data-testid="mandat-switcher-menu">
        {list.map((c) => (
          <DropdownMenuItem key={c.id} data-testid={`mandat-switch-${c.id}`} onSelect={() => enterMandat(c.id)}
            className={c.id === activeCompanyId ? "font-700 text-[#063044]" : ""}>
            <Building2 size={14} className="mr-2 text-slate-400" /> <span className="truncate">{c.name}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem data-testid="nav-mandats_list" onSelect={() => go("mandats_list")}>
          <Layers size={14} className="mr-2 text-slate-400" /> Tous les mandats
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function DynamicCompanyNav({ manifest, active, go, companies, activeCompanyId, enterMandat, openModule, setOpenModule }) {
  const modules = manifest?.modules || [];
  const choosing = active === "mandats_list";
  return (
    <div data-testid="company-nav">
      <MandatSwitcher companies={companies} activeCompanyId={activeCompanyId} active={active} go={go} enterMandat={enterMandat} />

      {!activeCompanyId && !choosing && (
        <p className="px-3 py-6 text-xs text-slate-400" data-testid="company-nav-choose">Choisissez un mandat dans « Tous les mandats » pour afficher ses modules.</p>
      )}
      {activeCompanyId && !choosing && modules.length === 0 && (
        <p className="px-3 py-4 text-xs text-slate-400" data-testid="company-nav-empty">Aucun module ne vous est attribué pour ce mandat.</p>
      )}
      {!choosing && (
        <ModulesNav modules={modules} active={active} go={go} openModule={openModule} setOpenModule={setOpenModule} />
      )}
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
  const [openModule, setOpenModule] = useState(null);
  const [justEntered, setJustEntered] = useState(false);
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
    if (cid === activeCompanyId) return;
    // Fail-closed: drop the previous mandate's manifest/menus immediately so no
    // stale modules survive during the recompute.
    setNavManifest(null);
    setOpenModule(null);
    setActiveCompanyId(cid);
    try { localStorage.setItem("meelora:activeCompany", cid); } catch (e) { /* ignore */ }
  };
  const enterMandat = (cid) => { switchCompany(cid); setJustEntered(true); setActive("company_home"); setMobileOpen(false); };
  // Platform staff: "Accéder" on Société Meelora opens its full operational
  // management console (users / invitations / module access / sensitive perms /
  // effective access). It NEVER adds financial modules to the platform sidebar
  // and grants no financial authority (platform_role ≠ authority).
  const enterMeelora = () => { setActive("platform_meelora_manage"); setMobileOpen(false); };
  const moduleEntry = (mods, adminView) => {
    const codes = mods.map((m) => m.module_code);
    if (codes.includes("ACCOUNTING")) return MODULE_FLYOUT.ACCOUNTING.landing; // Comptabilité prioritaire
    if (codes.includes("BUDGETS")) return MODULE_FLYOUT.BUDGETS.landing;
    for (const c of codes) if (MODULE_FLYOUT[c]) return MODULE_FLYOUT[c].landing;
    return adminView ? "preferences" : "mandats_list";
  };
  const allowedBusinessPages = (mods, adminView) => {
    const allowed = new Set(["preferences", "mandats_list", "company_home"]);
    // Admin functions moved to the avatar → Administration menu (Sociétés/Clients
    // is platform-only). Keep the pages reachable for company admins.
    if (adminView) ["access", "logs", "utilisateurs"].forEach((k) => allowed.add(k));
    mods.forEach((m) => (MODULE_PAGES[m.module_code] || []).forEach((k) => allowed.add(k)));
    return allowed;
  };
  // Non-platform business users: entering a mandate (via "Accéder") always lands
  // on the company home; multi-mandate users otherwise see the chooser. No ghost pages.
  useEffect(() => {
    if (isPlatformStaff || !navManifest || active.startsWith("platform_")) return;
    const mods = navManifest.modules || [];
    const adminView = !!navManifest.admin_view;
    const multi = navCompanies.length > 1;
    const allowed = allowedBusinessPages(mods, adminView);
    // Just entered a mandate from the chooser: land on the company home (welcome
    // + KPIs), before entering any module. Never bounce back to the chooser.
    if (justEntered) {
      setJustEntered(false);
      setActive("company_home");
      return;
    }
    if (!allowed.has(active)) { setActive(multi ? "mandats_list" : "company_home"); return; }
    // "dashboard" is the app default landing: multi users go to the chooser,
    // single-mandate users land on their company home.
    if (active === "dashboard") {
      setActive(multi ? "mandats_list" : "company_home");
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
    : active === "company_home" ? t("Mandat")
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
            enterMandat={enterMandat}
            openModule={openModule}
            setOpenModule={setOpenModule}
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
            {!isPlatformPage && !isPlaceholderPage && !active.startsWith("acct_") && active !== "company_home" && <span className="hidden rounded-full bg-[#22C55E]/10 px-3 py-1 text-xs font-600 text-[#22C55E] sm:inline-flex">{t("Budget actif")}</span>}
            {!isPlatformPage && !isPlaceholderPage && !active.startsWith("acct_") && active !== "company_home" && <YearControls />}
            <div className="ml-1 flex items-center gap-1 border-l border-slate-200 pl-2">
              <button data-testid="header-help-btn" title={t("Aide")} className="hidden rounded-full p-2 text-slate-500 transition-colors hover:bg-[#F3F4F6] hover:text-[#0F172A] sm:block"><HelpCircle size={18} /></button>
              <NotificationsBell go={go} />
              <UserMenu user={user} logout={logout} go={go} t={t} adminView={!!navManifest?.admin_view} />
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
