import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { useLang } from "../context/LanguageContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { Textarea } from "../components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Building2, BriefcaseBusiness, Plus, Pencil, Search, Users, Loader2, CircleCheck, CircleAlert, Upload, FileSpreadsheet, Ban, RotateCw, ArrowRight, History, ImagePlus, Trash2 } from "lucide-react";
import { useNav } from "../context/NavContext";
import { toast } from "sonner";

const INDUSTRIES = [
  ["services", "Services professionnels"], ["retail", "Commerce / Retail"], ["distribution", "Distribution"],
  ["construction", "Construction"], ["hospitality", "Restauration / Hôtellerie"], ["manufacturing", "Manufacturing"],
  ["real_estate", "Immobilier"], ["technology", "SaaS / Technologie"], ["transport", "Transport / Logistique"],
  ["healthcare", "Santé"], ["agriculture", "Agriculture / Agroalimentaire"], ["other", "Autre"],
];
const COMPANY_TYPES = [
  ["operating", "Société opérationnelle"], ["holding", "Holding"], ["real_estate", "Société immobilière"],
  ["nonprofit", "Association / Fondation"], ["other", "Autre"],
];
// --- Extensible tax model, driven by jurisdiction (NOT Canada-exclusive) ---
const TAX_FIELDS = {
  CA: [
    { key: "bn", label: "Numéro d'entreprise (BN)" },
    { key: "gst", label: "TPS / GST" },
    { key: "qst", label: "TVQ / QST (Québec)", when: (f) => {
      const r = (f.region || "").toLowerCase();
      return r === "qc" || r.includes("quebec") || r.includes("québec");
    } },
    { key: "pst", label: "PST (selon province)", when: (f) => ["bc", "sk", "mb"].includes((f.region || "").toLowerCase()) },
  ],
  CH: [
    { key: "uid", label: "IDE / UID" },
    { key: "vat", label: "TVA / MWST" },
  ],
};
const ENTITY_TYPES = [
  ["inc", "Société par actions (Inc.)"], ["sencrl", "SENCRL / SEC"], ["snc", "Société en nom collectif"],
  ["enr", "Entreprise individuelle (Enr.)"], ["cooperative", "Coopérative"], ["asbl", "Association / OBNL"],
  ["gmbh", "GmbH / Sàrl"], ["sa", "SA"], ["other", "Autre"],
];
const LANGUAGES = [["fr", "Français"], ["en", "English"], ["de", "Deutsch"], ["it", "Italiano"]];
const COUNTRIES = [["CA", "Canada"], ["CH", "Suisse"], ["FR", "France"], ["US", "États-Unis"], ["other", "Autre"]];
const MODULES_LIST = [
  ["REPORTING", "Reporting"], ["BUDGETS", "Gestion des Budgets"], ["ACCOUNTING", "Comptabilité"],
  ["FIXED_ASSETS", "Immobilisations"], ["CONSOLIDATION", "Consolidation"],
];
const emptyCompany = {
  name: "", legal_name: "", trade_name: "", company_code: "", entity_type: "inc", business_number: "",
  jurisdiction: "CA", country: "CA", region: "", city: "", address_line1: "", address_line2: "", postal_code: "",
  phone: "", email: "", functional_currency: "CAD", language: "fr", industry: "services",
  company_type: "operating", fiscal_year_start: "01-01", subscribed_modules: ["ACCOUNTING"], admin_email: "",
  tax: {}, accent_color: "",
};

function FormSection({ title, children }) {
  return (
    <div className="space-y-3 rounded-xl border border-slate-200 p-4">
      <p className="text-[11px] font-700 uppercase tracking-wide text-[#063044]">{title}</p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">{children}</div>
    </div>
  );
}
function F({ label, children, full }) {
  return <div className={full ? "sm:col-span-2" : ""}><Label className="text-[11px] uppercase text-slate-500">{label}</Label>{children}</div>;
}

export async function applyCompanyLogo(companyId, payload) {
  if (!companyId) return;
  if (payload?._logo?.data_base64) {
    await api.uploadCompanyLogo(companyId, payload._logo);
  } else if (payload?._logoRemove) {
    try { await api.deleteCompanyLogo(companyId); } catch (e) { /* no logo to remove */ }
  }
}

export async function createCompanyWithAdmin(payload, t = (x) => x) {
  const adminAction = payload._admin_action;
  const adminEmail = payload.admin_email;
  const body = { ...payload }; delete body._admin_action; delete body._logo; delete body._logoRemove;
  const created = await api.createCompany(body);
  await applyCompanyLogo(created.id, payload);
  if (adminEmail && adminAction) {
    try {
      if (adminAction === "invite") {
        await api.createInvitation({ email: adminEmail, kind: "company", company_id: created.id, membership_type: "company_user", company_role: "admin" });
        toast.success(t("Invitation d'activation envoyée à l'administrateur"));
      } else if (adminAction === "associate") {
        await api.createCompanyMember(created.id, { email: adminEmail, membership_type: "company_user", role: "admin" });
        toast.success(t("Administrateur associé (identité vérifiée)"));
      } else if (adminAction === "activation_required") {
        toast.warning(t("Administrateur non associé : activation/preuve de contrôle requise."));
      }
    } catch (e2) { toast.error(t("Société créée, mais action administrateur échouée : ") + (e2.response?.data?.detail || "")); }
  }
  return created;
}

export function CompanyForm({ open, onOpenChange, initial, onSubmit, saving }) {
  const { t } = useLang();
  const [f, setF] = useState(emptyCompany);
  const [adminCheck, setAdminCheck] = useState(null);
  const [checking, setChecking] = useState(false);
  const [logo, setLogo] = useState({ preview: null, data: null, remove: false });
  useEffect(() => {
    // Load the current company logo (edit) for preview; reset on open/create.
    let url = null;
    setLogo({ preview: null, data: null, remove: false });
    if (initial?.id && initial?.branding?.has_logo) {
      api.getCompanyLogoBlob(initial.id).then((blob) => { url = URL.createObjectURL(blob); setLogo((p) => ({ ...p, preview: url })); }).catch(() => {});
    }
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [initial, open]);
  const LOGO_TYPES = ["image/png", "image/jpeg", "image/jpg", "image/svg+xml", "image/webp"];
  const onLogoFile = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!LOGO_TYPES.includes(file.type)) { toast.error(t("Format non supporté (PNG, JPG, SVG, WEBP)")); return; }
    if (file.size > 2 * 1024 * 1024) { toast.error(t("Image trop volumineuse (max 2 Mo)")); return; }
    const reader = new FileReader();
    reader.onload = () => setLogo({ preview: reader.result, data: { data_base64: reader.result, mime: file.type, filename: file.name }, remove: false });
    reader.readAsDataURL(file);
  };
  const clearLogo = () => setLogo({ preview: null, data: null, remove: true });
  const checkAdmin = async () => {
    const email = f.admin_email.trim();
    if (!email) return toast.error(t("Saisissez d'abord un courriel"));
    setChecking(true);
    try { setAdminCheck(await api.adminCandidate(email)); }
    catch (e) { toast.error(e.response?.data?.detail || t("Vérification impossible")); setAdminCheck(null); }
    finally { setChecking(false); }
  };
  useEffect(() => {
    setF(initial ? { ...emptyCompany,
      ...Object.fromEntries(Object.keys(emptyCompany).map((k) => [k, initial[k] != null ? initial[k] : emptyCompany[k]])),
      tax: initial.tax_profile || {},
      accent_color: initial.branding?.accent_color || "",
      subscribed_modules: initial.subscribed_modules?.length ? initial.subscribed_modules : emptyCompany.subscribed_modules,
    } : emptyCompany);
  }, [initial, open]);
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const setTax = (k, v) => setF((p) => ({ ...p, tax: { ...p.tax, [k]: v } }));
  const toggleModule = (code) => setF((p) => ({ ...p, subscribed_modules: p.subscribed_modules.includes(code) ? p.subscribed_modules.filter((x) => x !== code) : [...p.subscribed_modules, code] }));
  const taxFields = (TAX_FIELDS[f.jurisdiction] || []).filter((x) => !x.when || x.when(f));
  const submit = () => {
    if (!f.name.trim()) return toast.error(t("Nom de société requis"));
    if (!f.functional_currency || f.functional_currency.length !== 3) return toast.error(t("Devise invalide"));
    const tax_profile = Object.fromEntries(Object.entries(f.tax || {}).filter(([, v]) => (v || "").toString().trim()));
    onSubmit({
      name: f.name.trim(), legal_name: f.legal_name.trim() || null, trade_name: f.trade_name.trim() || null,
      company_code: f.company_code.trim() || null, entity_type: f.entity_type || null, business_number: f.business_number.trim() || null,
      jurisdiction: f.jurisdiction, country: f.country || null, region: f.region.trim() || null, city: f.city.trim() || null,
      address_line1: f.address_line1.trim() || null, address_line2: f.address_line2.trim() || null, postal_code: f.postal_code.trim() || null,
      phone: f.phone.trim() || null, email: f.email.trim() || null, functional_currency: f.functional_currency,
      language: f.language, industry: f.industry, company_type: f.company_type, fiscal_year_start: f.fiscal_year_start,
      subscribed_modules: f.subscribed_modules, admin_email: f.admin_email.trim() || null, tax_profile,
      accent_color: (f.accent_color || "").trim() || null,
      _admin_action: f.admin_email.trim() ? (adminCheck?.action || null) : null,
      _logo: logo.data || null, _logoRemove: logo.remove || false,
    });
  };
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto" data-testid="company-form-dialog">
      <DialogHeader><DialogTitle>{initial ? t("Modifier la société / client") : t("Créer une société / client")}</DialogTitle><DialogDescription className="text-xs">{t("Renseignez l'identification, l'adresse, la fiscalité (selon la juridiction), les modules souscrits et l'administrateur.")}</DialogDescription></DialogHeader>
      <div className="space-y-4 py-1">
        <FormSection title={t("Identification")}>
          <F label={t("Nom d'affichage")}><Input value={f.name} onChange={(e) => set("name", e.target.value)} data-testid="company-name" /></F>
          <F label={t("Nom légal")}><Input value={f.legal_name} onChange={(e) => set("legal_name", e.target.value)} data-testid="company-legal-name" /></F>
          <F label={t("Nom commercial")}><Input value={f.trade_name} onChange={(e) => set("trade_name", e.target.value)} data-testid="company-trade-name" /></F>
          <F label={t("Type d'entité")}><Select value={f.entity_type} onValueChange={(v) => set("entity_type", v)}><SelectTrigger data-testid="company-entity-type"><SelectValue /></SelectTrigger><SelectContent>{ENTITY_TYPES.map(([v, l]) => <SelectItem key={v} value={v}>{t(l)}</SelectItem>)}</SelectContent></Select></F>
          <F label={t("Code société")}><Input value={f.company_code} onChange={(e) => set("company_code", e.target.value)} placeholder="CA-001" data-testid="company-code" /></F>
          <F label={t("Numéro d'entreprise")}><Input value={f.business_number} onChange={(e) => set("business_number", e.target.value)} data-testid="company-business-number" /></F>
        </FormSection>

        <FormSection title={t("Logo & identité visuelle")}>
          <div className="sm:col-span-2 flex items-center gap-4" data-testid="company-logo-section">
            <div className="flex h-20 w-20 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
              {logo.preview
                ? <img src={logo.preview} alt="logo" className="h-full w-full object-contain" data-testid="company-logo-preview" />
                : <span className="text-lg font-800 text-slate-300" data-testid="company-logo-fallback">{(f.name || "?").trim().slice(0, 2).toUpperCase()}</span>}
            </div>
            <div className="space-y-2">
              <div className="flex gap-2">
                <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 px-3 py-2 text-sm font-600 text-[#063044] hover:bg-slate-50" data-testid="company-logo-upload">
                  <ImagePlus size={15} /> {logo.preview ? t("Remplacer") : t("Téléverser un logo")}
                  <input type="file" accept="image/png,image/jpeg,image/svg+xml,image/webp" className="hidden" onChange={onLogoFile} data-testid="company-logo-input" />
                </label>
                {logo.preview && <Button type="button" variant="ghost" size="sm" className="h-9 text-rose-500" onClick={clearLogo} data-testid="company-logo-remove"><Trash2 size={14} /> {t("Retirer")}</Button>}
              </div>
              <p className="text-xs text-slate-400">{t("PNG, JPG, SVG ou WEBP · max 2 Mo · le ratio est conservé. Utilisé comme identité officielle dans les rapports.")}</p>
            </div>
          </div>
        </FormSection>

        <FormSection title={t("Adresse & coordonnées")}>
          <F label={t("Adresse (ligne 1)")} full><Input value={f.address_line1} onChange={(e) => set("address_line1", e.target.value)} data-testid="company-address1" /></F>
          <F label={t("Adresse (ligne 2)")} full><Input value={f.address_line2} onChange={(e) => set("address_line2", e.target.value)} /></F>
          <F label={t("Ville")}><Input value={f.city} onChange={(e) => set("city", e.target.value)} data-testid="company-city" /></F>
          <F label={t("Province / Canton / État")}><Input value={f.region} onChange={(e) => set("region", e.target.value)} placeholder="QC, BC, VD…" data-testid="company-region" /></F>
          <F label={t("Code postal")}><Input value={f.postal_code} onChange={(e) => set("postal_code", e.target.value)} data-testid="company-postal" /></F>
          <F label={t("Pays")}><Select value={f.country} onValueChange={(v) => set("country", v)}><SelectTrigger data-testid="company-country"><SelectValue /></SelectTrigger><SelectContent>{COUNTRIES.map(([v, l]) => <SelectItem key={v} value={v}>{t(l)}</SelectItem>)}</SelectContent></Select></F>
          <F label={t("Juridiction")}><Select value={f.jurisdiction} onValueChange={(v) => { set("jurisdiction", v); if (!initial) set("functional_currency", v === "CA" ? "CAD" : v === "CH" ? "CHF" : "EUR"); }}><SelectTrigger data-testid="company-jurisdiction"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="CA">Canada</SelectItem><SelectItem value="CH">Suisse</SelectItem></SelectContent></Select></F>
          <F label={t("Téléphone")}><Input value={f.phone} onChange={(e) => set("phone", e.target.value)} data-testid="company-phone" /></F>
          <F label={t("Courriel")}><Input value={f.email} onChange={(e) => set("email", e.target.value)} data-testid="company-email" /></F>
        </FormSection>

        <FormSection title={t("Fiscalité")}>
          {taxFields.length === 0
            ? <p className="sm:col-span-2 text-xs text-slate-400" data-testid="tax-none">{t("Aucun champ fiscal spécifique pour cette juridiction.")}</p>
            : taxFields.map((tf) => <F key={tf.key} label={t(tf.label)}><Input value={f.tax[tf.key] || ""} onChange={(e) => setTax(tf.key, e.target.value)} data-testid={`tax-${tf.key}`} /></F>)}
        </FormSection>

        <FormSection title={t("Paramètres")}>
          <F label={t("Devise fonctionnelle")}><Input maxLength={3} className="uppercase" value={f.functional_currency} onChange={(e) => set("functional_currency", e.target.value.toUpperCase())} data-testid="company-currency" /></F>
          <F label={t("Couleur d'accent (marque)")}>
            <div className="flex items-center gap-2">
              <input type="color" value={f.accent_color || "#063044"} onChange={(e) => set("accent_color", e.target.value)} data-testid="company-accent-color" className="h-9 w-12 cursor-pointer rounded border border-slate-200 bg-white p-0.5" />
              <Input value={f.accent_color || ""} placeholder="#063044" onChange={(e) => set("accent_color", e.target.value)} data-testid="company-accent-hex" className="h-9 flex-1 font-mono-data" />
              {f.accent_color && <button type="button" onClick={() => set("accent_color", "")} data-testid="company-accent-clear" className="text-xs text-slate-400 hover:text-rose-500">Effacer</button>}
            </div>
          </F>
          <F label={t("Langue")}><Select value={f.language} onValueChange={(v) => set("language", v)}><SelectTrigger data-testid="company-language"><SelectValue /></SelectTrigger><SelectContent>{LANGUAGES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent></Select></F>
          <F label={t("Secteur")}><Select value={f.industry} onValueChange={(v) => set("industry", v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{INDUSTRIES.map(([v, l]) => <SelectItem key={v} value={v}>{t(l)}</SelectItem>)}</SelectContent></Select></F>
          <F label={t("Type de société")}><Select value={f.company_type} onValueChange={(v) => set("company_type", v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{COMPANY_TYPES.map(([v, l]) => <SelectItem key={v} value={v}>{t(l)}</SelectItem>)}</SelectContent></Select></F>
          <F label={t("Début d'exercice (MM-JJ)")}><Input value={f.fiscal_year_start} onChange={(e) => set("fiscal_year_start", e.target.value)} placeholder="01-01" className="max-w-[180px]" /></F>
        </FormSection>

        <FormSection title={t("Modules souscrits")}>
          <div className="sm:col-span-2 grid grid-cols-2 gap-2" data-testid="company-modules">
            {MODULES_LIST.map(([code, label]) => (
              <button type="button" key={code} onClick={() => toggleModule(code)} data-testid={`module-${code}`}
                className={`flex items-center justify-between rounded-lg border px-3 py-2 text-left text-sm ${f.subscribed_modules.includes(code) ? "border-[#22C55E] bg-[#A7F3DD]/25 text-[#0F172A]" : "border-slate-200 hover:bg-slate-50"}`}>
                <span>{t(label)}</span>
                <span className={`h-4 w-4 rounded border ${f.subscribed_modules.includes(code) ? "border-[#22C55E] bg-[#22C55E]" : "border-slate-300"}`} />
              </button>
            ))}
          </div>
        </FormSection>

        <FormSection title={t("Administrateur à associer / inviter")}>
          <div className="sm:col-span-2 space-y-2">
            <div className="flex items-end gap-2">
              <div className="flex-1"><Label className="text-[11px] uppercase text-slate-500">{t("Courriel de l'administrateur")}</Label><Input value={f.admin_email} onChange={(e) => { set("admin_email", e.target.value); setAdminCheck(null); }} placeholder="admin@societe.com" data-testid="company-admin-email" /></div>
              <Button type="button" variant="outline" onClick={checkAdmin} disabled={checking || !f.admin_email.trim()} data-testid="admin-check-btn">{checking ? <Loader2 size={14} className="animate-spin" /> : t("Vérifier l'identité")}</Button>
            </div>
            {adminCheck && (
              <div className={`rounded-lg border p-3 text-xs ${adminCheck.status === "verified" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : adminCheck.status === "absent" ? "border-blue-200 bg-blue-50 text-blue-700" : "border-amber-200 bg-amber-50 text-amber-700"}`} data-testid="admin-check-result" data-status={adminCheck.status}>
                <p className="font-600">{adminCheck.status === "verified" ? t("Associer comme administrateur") : adminCheck.status === "absent" ? t("Envoyer une invitation d'activation") : t("Activation / preuve de contrôle requise")}</p>
                <p className="mt-0.5">{adminCheck.message}</p>
                {adminCheck.status === "unverified" && <p className="mt-1 font-600">{t("Aucun accès ne sera créé tant que l'identité n'est pas activée.")}</p>}
              </div>
            )}
            <p className="text-[11px] text-slate-400">{t("La simple correspondance d'un courriel ne crée jamais d'accès automatiquement (réutilise l'invitation/activation P1.13).")}</p>
          </div>
        </FormSection>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>{t("Annuler")}</Button><Button disabled={saving} onClick={submit} className="bg-[#0F172A] hover:bg-[#0F172A]/90" data-testid="company-submit">{saving && <Loader2 size={14} className="mr-2 animate-spin" />}{t("Enregistrer")}</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}

function MandateForm({ open, onOpenChange, company, mandate, users, onSubmit, saving }) {
  const { t } = useLang();
  const activeUsers = useMemo(() => (users || []).filter((u) => u.status !== "inactive" && u.role !== "admin"), [users]);
  const [code, setCode] = useState("");
  const [principal, setPrincipal] = useState("");
  const [collabs, setCollabs] = useState([]);
  useEffect(() => {
    setCode(mandate?.mandate_code || company?.company_code || "");
    setPrincipal(mandate?.principal_user_id || "");
    setCollabs(mandate?.collaborator_user_ids || []);
  }, [open, mandate, company]);
  const toggle = (id) => setCollabs((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id]);
  const submit = () => {
    if (!code.trim()) return toast.error(t("Code mandat requis"));
    if (!principal) return toast.error(t("Responsable principal requis"));
    onSubmit({ mandate_code: code.trim(), principal_user_id: principal, collaborator_user_ids: collabs.filter((x) => x !== principal) });
  };
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="max-w-xl" data-testid="mandate-form-dialog">
      <DialogHeader><DialogTitle>{mandate ? t("Modifier le mandat") : t("Créer le mandat")}</DialogTitle><DialogDescription>{company?.name}</DialogDescription></DialogHeader>
      <div className="space-y-4 py-1">
        <div><Label className="text-[11px] uppercase text-slate-500">{t("Code mandat")}</Label><Input value={code} onChange={(e) => setCode(e.target.value)} /></div>
        <div><Label className="text-[11px] uppercase text-slate-500">{t("Responsable principal")}</Label><Select value={principal} onValueChange={(v) => { setPrincipal(v); setCollabs((p) => p.filter((x) => x !== v)); }}><SelectTrigger><SelectValue placeholder={t("Sélectionner un utilisateur")} /></SelectTrigger><SelectContent>{activeUsers.map((u) => <SelectItem key={u.id} value={u.id}>{u.name}</SelectItem>)}</SelectContent></Select></div>
        <div><Label className="text-[11px] uppercase text-slate-500">{t("Collaborateurs autorisés")}</Label><div className="mt-1 max-h-48 space-y-1 overflow-auto rounded-xl border border-slate-200 p-2">{activeUsers.filter((u) => u.id !== principal).map((u) => <button key={u.id} type="button" onClick={() => toggle(u.id)} className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm ${collabs.includes(u.id) ? "bg-[#A7F3DD]/25 text-[#0F172A]" : "hover:bg-slate-50"}`}><span>{u.name}</span><span className={`h-4 w-4 rounded border ${collabs.includes(u.id) ? "border-[#22C55E] bg-[#22C55E]" : "border-slate-300"}`} /></button>)}{activeUsers.length === 0 && <p className="p-3 text-center text-xs text-slate-400">{t("Créez d'abord un utilisateur standard.")}</p>}</div></div>
      </div>
      <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>{t("Annuler")}</Button><Button disabled={saving || !activeUsers.length} onClick={submit} className="bg-[#0F172A] hover:bg-[#0F172A]/90">{saving && <Loader2 size={14} className="mr-2 animate-spin" />}{t("Enregistrer")}</Button></DialogFooter>
    </DialogContent>
  </Dialog>;
}

function ImportCompaniesDialog({ open, onOpenChange, onDone }) {
  const { t } = useLang(); const inputRef = useRef(null); const [file,setFile]=useState(null); const [preview,setPreview]=useState(null); const [busy,setBusy]=useState(false);
  useEffect(()=>{ if(!open){setFile(null);setPreview(null);} },[open]);
  const choose=async(f)=>{ if(!f)return; setFile(f);setBusy(true); try{setPreview(await api.previewCompaniesImport(f));}catch(e){toast.error(e.response?.data?.detail || t("Fichier invalide"));setPreview(null);}finally{setBusy(false);} };
  const commit=async()=>{setBusy(true);try{const r=await api.commitCompaniesImport(file);toast.success(`${r.created} ${t("société(s) créée(s)")}`);onOpenChange(false);await onDone();}catch(e){const d=e.response?.data?.detail;toast.error(typeof d==="string"?d:(d?.message||t("Import impossible")));}finally{setBusy(false);} };
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent className="max-w-4xl"><DialogHeader><DialogTitle>{t("Importer des sociétés depuis Excel")}</DialogTitle><DialogDescription>{t("Le fichier est toujours validé avant toute création. Colonnes: Nom, Code société, Juridiction, Devise, Secteur, Type. Pour une fiduciaire: Code mandat, Responsable principal et Collaborateurs.")}</DialogDescription></DialogHeader>
    <input ref={inputRef} type="file" accept=".xlsx,.xlsm" className="hidden" onChange={e=>choose(e.target.files?.[0])}/>
    {!preview && <button type="button" onClick={()=>inputRef.current?.click()} className="flex min-h-40 w-full flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 bg-slate-50/60 text-slate-500 hover:border-slate-400"><FileSpreadsheet size={30}/><span className="mt-2 text-sm font-600">{file?.name || t("Choisir un fichier Excel")}</span><span className="mt-1 text-xs">.xlsx</span></button>}
    {busy && <div className="flex justify-center py-5 text-sm text-slate-500"><Loader2 size={17} className="mr-2 animate-spin"/>{t("Validation...")}</div>}
    {preview && !busy && <div className="space-y-3"><div className="grid grid-cols-4 gap-2 text-center text-xs"><div className="rounded-lg bg-slate-50 p-2"><b className="block text-lg">{preview.total}</b>{t("Lignes")}</div><div className="rounded-lg bg-emerald-50 p-2 text-emerald-700"><b className="block text-lg">{preview.valid}</b>{t("Valides")}</div><div className="rounded-lg bg-amber-50 p-2 text-amber-700"><b className="block text-lg">{preview.warnings}</b>{t("Warnings")}</div><div className="rounded-lg bg-red-50 p-2 text-red-700"><b className="block text-lg">{preview.errors}</b>{t("Erreurs")}</div></div><div className="max-h-72 overflow-auto rounded-xl border"><table className="w-full text-xs"><thead className="sticky top-0 bg-slate-50 text-left"><tr><th className="p-2">#</th><th>{t("Société")}</th><th>{t("Code")}</th><th>{t("Juridiction")}</th><th>{t("Validation")}</th></tr></thead><tbody>{preview.rows.map(r=><tr key={r.row} className="border-t"><td className="p-2 text-slate-400">{r.row}</td><td>{r.name||"—"}</td><td>{r.company_code||"—"}</td><td>{r.jurisdiction||"—"}</td><td className="py-2 pr-2">{r.errors?.length?<span className="text-red-600">{r.errors.join(" · ")}</span>:r.warnings?.length?<span className="text-amber-600">{r.warnings.join(" · ")}</span>:<span className="text-emerald-600">OK</span>}</td></tr>)}</tbody></table></div></div>}
    <DialogFooter><Button variant="outline" onClick={()=>onOpenChange(false)}>{t("Annuler")}</Button>{preview&&<Button variant="outline" onClick={()=>inputRef.current?.click()}>{t("Changer de fichier")}</Button>}<Button disabled={!preview||preview.errors>0||busy} onClick={commit} className="bg-[#0F172A] hover:bg-[#0F172A]/90">{t("Confirmer l'import")}</Button></DialogFooter>
  </DialogContent></Dialog>;
}

export default function Companies() {
  const { user } = useAuth();
  const { t } = useLang();
  const orgType = user?.workspace?.organization_type || user?.organization_type || "company";
  const fiduciary = orgType === "fiduciary";
  const admin = user?.role === "admin";
  const [companies, setCompanies] = useState([]);
  const [mandates, setMandates] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [jurisdiction, setJurisdiction] = useState("all");
  const [companyDialog, setCompanyDialog] = useState({ open:false, item:null });
  const [mandateDialog, setMandateDialog] = useState({ open:false, company:null, mandate:null });
  const [saving, setSaving] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState("all");
  const [statusDialog, setStatusDialog] = useState({ open: false, company: null, next: "inactive" });
  const [statusReason, setStatusReason] = useState("");
  const [historyDialog, setHistoryDialog] = useState({ open: false, company: null });
  const { enterMandat } = useNav();

  const load = async () => {
    setLoading(true);
    try {
      const [cs, ms, us] = await Promise.all([
        api.getCompanies(admin),
        fiduciary ? api.listMandates().catch(() => []) : Promise.resolve([]),
        admin ? api.listUsers().catch(() => []) : Promise.resolve([]),
      ]);
      setCompanies(cs || []); setMandates(ms || []); setUsers(us || []);
    } catch (e) { toast.error(e.response?.data?.detail || t("Impossible de charger les sociétés")); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [fiduciary, admin]); // eslint-disable-line react-hooks/exhaustive-deps

  const isActive = (c) => c.status !== "inactive" && c.active !== false;
  const changeStatus = async (c, next, reason = "") => {
    try {
      await api.updateCompany(c.id, { status: next, status_reason: reason });
      toast.success(next === "inactive" ? t("Société rendue inactive") : t("Société réactivée"));
      setStatusDialog({ open: false, company: null, next: "inactive" }); setStatusReason(""); await load();
    } catch (e) { toast.error(e.response?.data?.detail || t("Action impossible")); }
  };
  const openStatusDialog = (c, next) => { setStatusReason(""); setStatusDialog({ open: true, company: c, next }); };

  const mandateByCompany = useMemo(() => Object.fromEntries(mandates.map((m) => [m.company_id, m])), [mandates]);
  const userById = useMemo(() => Object.fromEntries(users.map((u) => [u.id, u])), [users]);
  const rows = useMemo(() => companies.filter((c) => {
    const m = mandateByCompany[c.id];
    const principal = userById[m?.principal_user_id]?.name || "";
    const needle = `${c.name || ""} ${c.company_code || ""} ${principal}`.toLowerCase();
    return (!query || needle.includes(query.toLowerCase())) && (jurisdiction === "all" || c.jurisdiction === jurisdiction)
      && (statusFilter === "all" || (statusFilter === "active" ? isActive(c) : !isActive(c)));
  }), [companies, mandateByCompany, userById, query, jurisdiction, statusFilter]);

  const saveCompany = async (payload) => {
    setSaving(true);
    const adminAction = payload._admin_action;
    const adminEmail = payload.admin_email;
    const body = { ...payload }; delete body._admin_action; delete body._logo; delete body._logoRemove;
    try {
      if (companyDialog.item) { await api.updateCompany(companyDialog.item.id, body); await applyCompanyLogo(companyDialog.item.id, payload); toast.success(t("Société mise à jour")); }
      else { await createCompanyWithAdmin(payload, t); toast.success(t("Société créée")); }
      setCompanyDialog({ open:false, item:null }); await load();
    } catch (e) { toast.error(e.response?.data?.detail || t("Erreur lors de l'enregistrement")); }
    finally { setSaving(false); }
  };
  const saveMandate = async (payload) => {
    setSaving(true);
    try {
      const d = mandateDialog;
      if (d.mandate) await api.updateMandate(d.mandate.id, payload);
      else await api.createMandate({ ...payload, company_id: d.company.id });
      toast.success(t(d.mandate ? "Mandat mis à jour" : "Mandat créé"));
      setMandateDialog({ open:false, company:null, mandate:null }); await load();
    } catch (e) { toast.error(e.response?.data?.detail || t("Erreur lors de l'enregistrement du mandat")); }
    finally { setSaving(false); }
  };

  const heading = fiduciary ? t("Mandats") : t("Sociétés");
  return <div className="space-y-4" data-testid="companies-page">
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div><p className="text-sm font-600 text-[#0F172A]">{heading}</p><p className="mt-0.5 text-xs text-slate-500">{admin ? t("Gérez les entités financières de votre organisation et leurs responsables.") : t("Vous ne voyez que les sociétés qui vous sont attribuées.")}</p></div>
      {admin && <div className="flex gap-2"><Button variant="outline" className="gap-1.5" onClick={() => setImportOpen(true)}><Upload size={15}/>{t("Importer Excel")}</Button><Button data-testid="add-company-btn" className="gap-1.5 bg-[#0F172A] hover:bg-[#0F172A]/90" onClick={() => setCompanyDialog({ open:true, item:null })}><Plus size={16}/>{t("Nouvelle société")}</Button></div>}
    </div>

    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <div className="relative max-w-md flex-1"><Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/><Input value={query} onChange={(e) => setQuery(e.target.value)} className="pl-9" placeholder={t("Rechercher société, code ou responsable...")} /></div>
      <Select value={jurisdiction} onValueChange={setJurisdiction}><SelectTrigger className="w-full sm:w-[180px]"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{t("Toutes juridictions")}</SelectItem><SelectItem value="CH">Suisse</SelectItem><SelectItem value="CA">Canada</SelectItem></SelectContent></Select>
      <Select value={statusFilter} onValueChange={setStatusFilter}><SelectTrigger className="w-full sm:w-[150px]" data-testid="company-status-filter"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">{t("Toutes")}</SelectItem><SelectItem value="active">{t("Actives")}</SelectItem><SelectItem value="inactive">{t("Inactives")}</SelectItem></SelectContent></Select>
    </div>

    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      {loading && <div className="col-span-full flex items-center justify-center py-16 text-slate-400"><Loader2 className="mr-2 animate-spin" size={18}/>{t("Chargement...")}</div>}
      {!loading && rows.map((c) => {
        const m = mandateByCompany[c.id]; const principal = userById[m?.principal_user_id];
        return <div key={c.id} className="card group p-4 transition hover:-translate-y-0.5 hover:shadow-md" data-testid={`company-card-${c.id}`}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 gap-3"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#A7F3DD]/30 text-[#15803D]">{fiduciary ? <BriefcaseBusiness size={19}/> : <Building2 size={19}/>}</div><div className="min-w-0"><p className="truncate font-700 text-[#0F172A]">{c.name}</p><p className="mt-0.5 text-[11px] text-slate-400">{[c.company_code, c.jurisdiction, c.functional_currency].filter(Boolean).join(" · ") || c.id}</p></div></div>
            {admin && <button title={t("Modifier la société")} onClick={() => setCompanyDialog({ open:true, item:c })} className="rounded-lg p-1.5 text-slate-400 opacity-0 transition hover:bg-slate-100 hover:text-[#0F172A] group-hover:opacity-100"><Pencil size={14}/></button>}
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-lg bg-slate-50 px-2.5 py-2"><span className="block text-[10px] uppercase text-slate-400">{t("Secteur")}</span><b className="font-600 text-slate-700">{INDUSTRIES.find(([v]) => v === c.industry)?.[1] || c.industry || "—"}</b></div>
            <div className="rounded-lg bg-slate-50 px-2.5 py-2"><span className="block text-[10px] uppercase text-slate-400">{t("Statut")}</span>
              {isActive(c)
                ? <b className="inline-flex items-center gap-1 font-600 text-[#15803D]" data-testid={`company-status-${c.id}`}><CircleCheck size={12}/>{t("Active")}</b>
                : <b className="inline-flex items-center gap-1 font-600 text-slate-500" data-testid={`company-status-${c.id}`}><Ban size={12}/>{t("Inactive")}</b>}
            </div>
          </div>
          {admin && <div className="mt-3 flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`company-access-${c.id}`} disabled={!isActive(c)} onClick={() => enterMandat(c.id)}>{t("Accéder")} <ArrowRight size={13}/></Button>
            {c.legacy_prefix !== "acct" && (isActive(c)
              ? <Button size="sm" variant="outline" className="h-8 gap-1 text-rose-600 hover:text-rose-700" data-testid={`company-deactivate-${c.id}`} onClick={() => openStatusDialog(c, "inactive")}><Ban size={13}/>{t("Rendre inactive")}</Button>
              : <Button size="sm" variant="outline" className="h-8 gap-1 text-emerald-600 hover:text-emerald-700" data-testid={`company-reactivate-${c.id}`} onClick={() => openStatusDialog(c, "active")}><RotateCw size={13}/>{t("Réactiver")}</Button>)}
            {(c.status_history || []).length > 0 && <Button size="sm" variant="ghost" className="h-8 gap-1 text-slate-500" data-testid={`company-history-${c.id}`} onClick={() => setHistoryDialog({ open: true, company: c })}><History size={13}/>{t("Historique")}</Button>}
          </div>}
          {!isActive(c) && c.status_reason && <div className="mt-2 rounded-lg bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-700" data-testid={`company-reason-${c.id}`}><span className="font-600">{t("Motif")} : </span>{c.status_reason}</div>}
          {fiduciary && <div className="mt-3 border-t border-slate-100 pt-3">
            {m ? <div className="flex items-center justify-between gap-2"><div className="min-w-0"><p className="text-[10px] uppercase text-slate-400">{t("Responsable principal")}</p><p className="truncate text-xs font-600 text-slate-700">{principal?.name || m.principal_user_id}</p><p className="mt-0.5 text-[10px] text-slate-400">{m.mandate_code} · {(m.collaborator_user_ids || []).length} {t("collaborateur(s)")}</p></div>{admin && <Button size="sm" variant="outline" className="h-8" onClick={() => setMandateDialog({ open:true, company:c, mandate:m })}><Users size={13} className="mr-1"/>{t("Affecter")}</Button>}</div>
            : <div className="flex items-center justify-between gap-2"><span className="inline-flex items-center gap-1 text-xs font-600 text-amber-600"><CircleAlert size={13}/>{t("Mandat à configurer")}</span>{admin && <Button size="sm" variant="outline" className="h-8" onClick={() => setMandateDialog({ open:true, company:c, mandate:null })}>{t("Configurer")}</Button>}</div>}
          </div>}
        </div>;
      })}
      {!loading && rows.length === 0 && <div className="col-span-full rounded-xl border border-dashed border-slate-300 bg-white py-16 text-center"><Building2 className="mx-auto mb-3 text-slate-300" size={34}/><p className="text-sm font-600 text-slate-500">{t("Aucune société trouvée")}</p>{admin && <p className="mt-1 text-xs text-slate-400">{t("Créez votre première société pour commencer.")}</p>}</div>}
    </div>

    <ImportCompaniesDialog open={importOpen} onOpenChange={setImportOpen} onDone={load}/>    {companyDialog.open && <CompanyForm open={companyDialog.open} onOpenChange={(v) => setCompanyDialog((p) => ({...p, open:v}))} initial={companyDialog.item} onSubmit={saveCompany} saving={saving}/>} 
    {mandateDialog.open && <MandateForm open={mandateDialog.open} onOpenChange={(v) => setMandateDialog((p) => ({...p, open:v}))} company={mandateDialog.company} mandate={mandateDialog.mandate} users={users} onSubmit={saveMandate} saving={saving}/>}
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
  </div>;
}
