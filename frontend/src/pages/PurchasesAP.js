import { useState, useEffect, useCallback } from "react";
import { useNav } from "../context/NavContext";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Loader2, Plus, Trash2, Building2, Inbox, FileText, Banknote, FileMinus, Clock, LayoutDashboard } from "lucide-react";

const money = (v, c) => `${Number(v || 0).toFixed(2)} ${c || ""}`.trim();
const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || "").filter(Boolean).join(" — ") || "Erreur de validation";
  return "Erreur";
};

const COUNTRIES = [{ v: "CA", l: "Canada" }, { v: "CH", l: "Suisse" }, { v: "", l: "Autre / International" }];
const REGIONS = {
  CA: [["QC", "Québec"], ["ON", "Ontario"], ["BC", "Colombie-Britannique"], ["AB", "Alberta"], ["MB", "Manitoba"],
       ["SK", "Saskatchewan"], ["NS", "Nouvelle-Écosse"], ["NB", "Nouveau-Brunswick"], ["NL", "Terre-Neuve-et-Labrador"],
       ["PE", "Île-du-Prince-Édouard"], ["NT", "Territoires du Nord-Ouest"], ["YT", "Yukon"], ["NU", "Nunavut"]],
  CH: [["GE", "Genève"], ["VD", "Vaud"], ["ZH", "Zurich"], ["BE", "Berne"], ["VS", "Valais"], ["FR", "Fribourg"],
       ["TI", "Tessin"], ["BS", "Bâle-Ville"], ["LU", "Lucerne"], ["SG", "Saint-Gall"]],
};

const TABS = [
  { key: "overview", label: "Aperçu", icon: LayoutDashboard },
  { key: "inbox", label: "Factures à traiter", icon: Inbox },
  { key: "suppliers", label: "Fournisseurs", icon: Building2 },
  { key: "invoices", label: "Factures", icon: FileText },
  { key: "payments", label: "Paiements", icon: Banknote },
  { key: "credits", label: "Crédits", icon: FileMinus },
  { key: "aging", label: "Aging", icon: Clock },
];

const SUP_SECTIONS = [
  { key: "general", label: "Général" },
  { key: "addresses", label: "Adresses & contacts" },
  { key: "billing", label: "Facturation & paiement" },
  { key: "tax", label: "Fiscalité" },
  { key: "accounting", label: "Comptabilité" },
  { key: "documents", label: "Documents" },
  { key: "history", label: "Historique" },
];

const EMPTY_SUP = {
  name: "", trade_name: "", code: "", status: "active", language: "fr", internal_notes: "",
  legal_address: "", remit_to_address: "", email: "", phone: "", website: "",
  country: "", region: "", jurisdiction: "",
  default_currency: "CAD", payment_terms: "", due_days: "", preferred_payment_method: "",
  tax_regime: "", tax_ids: "", tax_exemptions: "",
  default_expense_account_code: "", default_ap_account_code: "", requires_po: false,
  contacts: [], primary_contact: "",
  bank_iban: "", bank_transit: "", bank_account: "",
};

export default function PurchasesAP() {
  const { activeCompanyId: cid } = useNav();
  const [tab, setTab] = useState("suppliers");
  return (
    <div className="mx-auto max-w-6xl" data-testid="ap-page">
      <div className="mb-5 flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button key={t.key} type="button" data-testid={`ap-tab-${t.key}`} onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-600 transition-colors ${tab === t.key ? "border-b-2 border-[#22C55E] text-[#0F172A]" : "text-slate-500 hover:text-[#0F172A]"}`}>
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>
      {tab === "suppliers" ? <SuppliersTab cid={cid} />
        : tab === "invoices" ? <InvoicesTab cid={cid} toProcess={false} />
        : tab === "inbox" ? <InvoicesTab cid={cid} toProcess={true} />
        : <ComingSoon label={TABS.find((t) => t.key === tab)?.label} />}
    </div>
  );
}

function ComingSoon({ label }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 p-10 text-center" data-testid="ap-coming-soon">
      <p className="text-sm font-600 text-[#063044]">{label}</p>
      <p className="mt-1 text-sm text-slate-400">Module Achats & Fournisseurs — disponible dans une prochaine tranche (A4.2+).</p>
    </div>
  );
}

const DOC_ST = {
  draft: { label: "Brouillon", cls: "bg-slate-100 text-slate-600" },
  verified: { label: "Vérifiée", cls: "bg-blue-100 text-blue-700" },
  submitted: { label: "Soumise", cls: "bg-indigo-100 text-indigo-700" },
  po_missing: { label: "PO manquant", cls: "bg-amber-100 text-amber-700" },
  discrepancy: { label: "Écart", cls: "bg-orange-100 text-orange-700" },
  approved: { label: "Approuvée", cls: "bg-emerald-100 text-emerald-700" },
  rejected: { label: "Rejetée", cls: "bg-rose-100 text-rose-700" },
};

function InvoicesTab({ cid, toProcess }) {
  const [invoices, setInvoices] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [taxCodes, setTaxCodes] = useState([]);
  const [functional, setFunctional] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [fetchingRate, setFetchingRate] = useState(false);
  const emptyLine = { description: "", qty: 1, unit_price: "", tax_code: "EXEMPT" };
  const [form, setForm] = useState({ supplier_id: "", period_id: "", supplier_invoice_number: "", invoice_date: "", currency: "", fx_rate: "", purchase_order_id: "", reference: "", lines: [{ ...emptyLine }] });

  const load = useCallback(async () => {
    if (!cid) return;
    setLoading(true);
    try {
      const [inv, sup, per, tc] = await Promise.all([
        api.apInvoices(cid, toProcess ? { to_process: true } : {}), api.apSuppliers(cid), api.glPeriods(cid), api.arTaxCodes(cid),
      ]);
      setInvoices(inv.invoices || []); setSuppliers(sup.suppliers || []);
      setPeriods(per.periods || per || []); setTaxCodes(tc.tax_codes || tc || []);
    } catch (e) { /* gated */ }
    setLoading(false);
  }, [cid, toProcess]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.getCompany(cid).then((c) => setFunctional((c.functional_currency || "").toUpperCase())).catch(() => {}); }, [cid]);

  const supName = (id) => suppliers.find((s) => s.id === id)?.name || (id || "").slice(0, 8);
  const onSupplier = (id) => setForm((f) => { const s = suppliers.find((x) => x.id === id); return { ...f, supplier_id: id, currency: f.currency || (s?.default_currency || "").toUpperCase() }; });
  const setLine = (i, k, v) => setForm((f) => ({ ...f, lines: f.lines.map((l, j) => j === i ? { ...l, [k]: v } : l) }));
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, { ...emptyLine }] }));
  const rmLine = (i) => setForm((f) => ({ ...f, lines: f.lines.filter((_, j) => j !== i) }));

  const fetchRate = async () => {
    const cur = (form.currency || "").toUpperCase();
    const datev = form.invoice_date || new Date().toISOString().slice(0, 10);
    if (!cur || !functional) { toast.error("Devise et date requises."); return; }
    if (cur === functional) { setForm((f) => ({ ...f, fx_rate: "1" })); toast.info("Même devise : taux 1."); return; }
    setFetchingRate(true);
    try {
      const r = await api.arOandaRate(cid, { from_currency: cur, to_currency: functional, on_date: datev });
      if (r.available) { setForm((f) => ({ ...f, fx_rate: String(r.rate) })); toast.success(`Taux OANDA ${cur}/${functional} = ${r.rate}`); }
      else toast.error(r.reason || "Taux OANDA indisponible.");
    } catch (e) { toast.error("Erreur OANDA"); }
    setFetchingRate(false);
  };
  const create = async () => {
    try {
      const body = { supplier_id: form.supplier_id, period_id: form.period_id,
        supplier_invoice_number: form.supplier_invoice_number || undefined, invoice_date: form.invoice_date || undefined,
        currency: form.currency || undefined, fx_rate: form.fx_rate ? Number(form.fx_rate) : undefined,
        purchase_order_id: form.purchase_order_id || undefined, reference: form.reference || undefined,
        lines: form.lines.map((l) => ({ ...l, qty: Number(l.qty || 1), unit_price: Number(l.unit_price || 0) })) };
      await api.apCreateInvoice(cid, body);
      toast.success("Facture fournisseur créée"); setOpen(false);
      setForm({ supplier_id: "", period_id: "", supplier_invoice_number: "", invoice_date: "", currency: "", fx_rate: "", purchase_order_id: "", reference: "", lines: [{ ...emptyLine }] });
      load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const act = async (id, action, body, okMsg) => { try { await api.apInvoiceAction(cid, id, action, body); toast.success(okMsg || "Fait"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const upload = async (id, file) => { if (!file) return; try { await api.apUploadInvoicePdf(cid, id, file); toast.success("PDF joint"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const fxDisabled = !form.currency || form.currency.toUpperCase() === functional;

  return (
    <div className="space-y-4" data-testid={toProcess ? "ap-inbox-tab" : "ap-invoices-tab"}>
      {!toProcess && (
        <Button data-testid="apinv-toggle" onClick={() => setOpen((v) => !v)} className="h-9 gap-1 bg-[#063044] text-white"><Plus size={14} /> Nouvelle facture</Button>
      )}
      {open && !toProcess && (
        <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="apinv-form">
          <div className="flex flex-wrap items-end gap-3">
            <div><label className="text-[11px] uppercase text-slate-500">Fournisseur</label>
              <select data-testid="apinv-supplier" value={form.supplier_id} onChange={(e) => onSupplier(e.target.value)} className="mt-1 h-9 w-52 rounded-md border border-slate-200 px-2 text-sm">
                <option value="">—</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
            <div><label className="text-[11px] uppercase text-slate-500">Période</label>
              <select data-testid="apinv-period" value={form.period_id} onChange={(e) => setForm({ ...form, period_id: e.target.value })} className="mt-1 h-9 w-36 rounded-md border border-slate-200 px-2 text-sm">
                <option value="">—</option>{periods.map((p) => <option key={p.id} value={p.id}>{p.code} ({p.status})</option>)}</select></div>
            <div><label className="text-[11px] uppercase text-slate-500">N° facture fourn.</label><Input data-testid="apinv-number" value={form.supplier_invoice_number} onChange={(e) => setForm({ ...form, supplier_invoice_number: e.target.value })} className="mt-1 h-9 w-36" /></div>
            <div><label className="text-[11px] uppercase text-slate-500">Date</label><Input data-testid="apinv-date" type="date" value={form.invoice_date} onChange={(e) => setForm({ ...form, invoice_date: e.target.value })} className="mt-1 h-9 w-40" /></div>
            <div><label className="text-[11px] uppercase text-slate-500">Devise</label><Input data-testid="apinv-currency" value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} className="mt-1 h-9 w-24" /></div>
            <div><label className="text-[11px] uppercase text-slate-500">Taux FX</label><Input data-testid="apinv-fx" value={form.fx_rate} placeholder="auto" onChange={(e) => setForm({ ...form, fx_rate: e.target.value })} className="mt-1 h-9 w-24" /></div>
            <Button type="button" variant="outline" size="sm" disabled={fxDisabled || fetchingRate} onClick={fetchRate} data-testid="apinv-fetch-rate" className="h-9 gap-1"><Loader2 size={13} className={fetchingRate ? "animate-spin" : "hidden"} />Récupérer le taux</Button>
            <div><label className="text-[11px] uppercase text-slate-500">PO</label><Input data-testid="apinv-po" value={form.purchase_order_id} onChange={(e) => setForm({ ...form, purchase_order_id: e.target.value })} className="mt-1 h-9 w-32" /></div>
          </div>
          <div className="mt-3 space-y-2">
            {form.lines.map((l, i) => (
              <div key={i} className="flex flex-wrap items-end gap-2" data-testid={`apinv-line-${i}`}>
                <Input placeholder="Description" value={l.description} onChange={(e) => setLine(i, "description", e.target.value)} className="h-9 w-56" data-testid={`apinv-line-desc-${i}`} />
                <Input placeholder="Qté" value={l.qty} onChange={(e) => setLine(i, "qty", e.target.value)} className="h-9 w-16" data-testid={`apinv-line-qty-${i}`} />
                <Input placeholder="Prix" value={l.unit_price} onChange={(e) => setLine(i, "unit_price", e.target.value)} className="h-9 w-24" data-testid={`apinv-line-price-${i}`} />
                <select value={l.tax_code} onChange={(e) => setLine(i, "tax_code", e.target.value)} className="h-9 w-40 rounded-md border border-slate-200 px-2 text-sm" data-testid={`apinv-line-tax-${i}`}>
                  {taxCodes.map((t) => <option key={t.code} value={t.code}>{t.label || t.code}</option>)}
                </select>
                {form.lines.length > 1 && <Button type="button" variant="ghost" size="sm" className="h-9 text-rose-500" onClick={() => rmLine(i)}><Trash2 size={14} /></Button>}
              </div>
            ))}
            <Button type="button" variant="outline" size="sm" className="h-8 gap-1" data-testid="apinv-add-line" onClick={addLine}><Plus size={12} /> Ligne</Button>
          </div>
          <div className="mt-4 border-t border-slate-100 pt-3">
            <Button data-testid="apinv-create" onClick={create} disabled={!form.supplier_id || !form.period_id} className="h-9 gap-1 bg-[#22C55E] text-white"><Plus size={14} /> Créer</Button>
          </div>
        </div>
      )}

      {loading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-300" /></div>
        : invoices.length === 0 ? <p className="text-sm text-slate-400" data-testid="ap-invoices-empty">{toProcess ? "Aucune facture à traiter." : "Aucune facture fournisseur."}</p>
        : (
          <div className="space-y-2">
            {invoices.map((inv) => {
              const st = DOC_ST[inv.document_status] || DOC_ST.draft;
              return (
                <div key={inv.id} data-testid={`apinv-row-${inv.id}`} className="rounded-xl border border-slate-200 bg-white p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-3">
                      <span className="font-600 text-[#0F172A]">{supName(inv.supplier_id)}</span>
                      <span className="font-mono-data text-xs text-slate-500">{inv.supplier_invoice_number || "—"}</span>
                      <span className="text-sm text-slate-500">{inv.invoice_date} · éch. {inv.due_date || "—"} · {money(inv.total, inv.currency)}</span>
                      <span className={`rounded-full px-2 py-0.5 text-[11px] font-600 ${st.cls}`}>{st.label}</span>
                      {inv.posting_status === "posted" && <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-600 text-emerald-800">Comptabilisée</span>}
                      {inv.po_required && !inv.purchase_order_id && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-600 text-amber-700">PO requis</span>}
                      {inv.source_document_id && <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-600 text-slate-600">PDF joint</span>}
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      {inv.document_status === "draft" && <>
                        <label className="cursor-pointer rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50" data-testid={`apinv-upload-${inv.id}`}>Joindre PDF<input type="file" accept="application/pdf,image/*" className="hidden" onChange={(e) => upload(inv.id, e.target.files?.[0])} /></label>
                        <Button size="sm" variant="outline" className="h-8" data-testid={`apinv-verify-${inv.id}`} onClick={() => act(inv.id, "verify", null, "Vérifiée")}>Vérifier</Button>
                      </>}
                      {(inv.document_status === "verified" || inv.document_status === "po_missing") && <Button size="sm" variant="outline" className="h-8" data-testid={`apinv-submit-${inv.id}`} onClick={() => act(inv.id, "submit", null, "Soumise")}>Soumettre</Button>}
                      {inv.document_status === "submitted" && <>
                        <Button size="sm" className="h-8 bg-emerald-600 text-white" data-testid={`apinv-approve-${inv.id}`} onClick={() => act(inv.id, "approve", null, "Approuvée")}>Approuver</Button>
                        <Button size="sm" variant="outline" className="h-8 text-rose-600" data-testid={`apinv-reject-${inv.id}`} onClick={() => act(inv.id, "reject", { reason: "Rejetée" }, "Rejetée")}>Rejeter</Button>
                      </>}
                      {inv.document_status === "approved" && inv.posting_status !== "posted" && <Button size="sm" className="h-8 bg-[#063044] text-white" data-testid={`apinv-post-${inv.id}`} onClick={() => act(inv.id, "post", null, "Comptabilisée")}>Comptabiliser</Button>}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
    </div>
  );
}

function SuppliersTab({ cid }) {
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [section, setSection] = useState("general");
  const [taxProposal, setTaxProposal] = useState(null);
  const [form, setForm] = useState({ ...EMPTY_SUP });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const load = useCallback(async () => {
    if (!cid) return;
    setLoading(true);
    try { const r = await api.apSuppliers(cid); setSuppliers(r.suppliers || []); } catch (e) { /* gated */ }
    setLoading(false);
  }, [cid]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (!form.country) { setTaxProposal(null); return; }
    api.getTaxJurisdictionConfig({ country: form.country, region: form.region || undefined })
      .then((cfg) => { setTaxProposal(cfg); setForm((f) => ({ ...f, jurisdiction: cfg.jurisdiction })); })
      .catch(() => setTaxProposal(null));
  }, [form.country, form.region]); // eslint-disable-line react-hooks/exhaustive-deps

  const addContact = () => set("contacts", [...(form.contacts || []), { name: "", email: "", phone: "", role: "" }]);
  const setContact = (i, k, v) => set("contacts", (form.contacts || []).map((c, j) => j === i ? { ...c, [k]: v } : c));
  const rmContact = (i) => set("contacts", (form.contacts || []).filter((_, j) => j !== i));

  const create = async () => {
    try {
      const bank_info = (form.bank_iban || form.bank_transit || form.bank_account)
        ? { iban: form.bank_iban || undefined, transit: form.bank_transit || undefined, account: form.bank_account || undefined } : undefined;
      const body = {
        name: form.name, trade_name: form.trade_name || undefined, code: form.code || undefined, status: form.status,
        language: form.language, internal_notes: form.internal_notes || undefined,
        legal_address: form.legal_address || undefined, remit_to_address: form.remit_to_address || undefined,
        email: form.email || undefined, phone: form.phone || undefined, website: form.website || undefined,
        country: form.country || undefined, region: form.region || undefined, jurisdiction: form.jurisdiction || undefined,
        default_currency: form.default_currency, payment_terms: form.payment_terms || undefined,
        due_days: form.due_days ? Number(form.due_days) : undefined, preferred_payment_method: form.preferred_payment_method || undefined,
        tax_regime: form.tax_regime || undefined,
        default_expense_account_code: form.default_expense_account_code || undefined,
        default_ap_account_code: form.default_ap_account_code || undefined, requires_po: !!form.requires_po,
        contacts: (form.contacts || []).filter((c) => c.name || c.email || c.phone),
        primary_contact: form.primary_contact ? { name: form.primary_contact } : undefined,
        tax_exemptions: form.tax_exemptions ? String(form.tax_exemptions).split(",").map((s) => ({ code: s.trim() })).filter((x) => x.code) : [],
        bank_info,
      };
      if (form.tax_ids) { const tt = {}; form.tax_ids.split(",").forEach((p) => { const [k, v] = p.split(":"); if (k && v) tt[k.trim()] = v.trim(); }); body.tax_ids = tt; }
      await api.apCreateSupplier(cid, body);
      toast.success("Fournisseur créé"); setForm({ ...EMPTY_SUP }); setTaxProposal(null); setSection("general"); setOpen(false); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  const F = (k, label, props = {}) => (
    <div><label className="text-[11px] uppercase text-slate-500">{label}</label>
      <Input data-testid={`sup-${k}`} value={form[k]} onChange={(e) => set(k, props.upper ? e.target.value.toUpperCase() : e.target.value)} className="mt-1 h-9 w-full" placeholder={props.ph || ""} /></div>
  );

  return (
    <div className="space-y-4" data-testid="ap-suppliers-tab">
      <Button data-testid="sup-toggle" onClick={() => setOpen((v) => !v)} className="h-9 gap-1 bg-[#063044] text-white"><Plus size={14} /> Nouveau fournisseur</Button>

      {open && (
        <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="sup-form">
          <div className="mb-4 flex flex-wrap gap-1 border-b border-slate-200">
            {SUP_SECTIONS.map((s) => (
              <button key={s.key} type="button" data-testid={`sup-section-${s.key}`} onClick={() => setSection(s.key)}
                className={`px-3 py-2 text-sm font-600 transition-colors ${section === s.key ? "border-b-2 border-[#22C55E] text-[#0F172A]" : "text-slate-500 hover:text-[#0F172A]"}`}>{s.label}</button>
            ))}
          </div>

          {section === "general" && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-3" data-testid="sup-sec-general">
              {F("name", "Raison sociale")}
              {F("trade_name", "Nom commercial")}
              {F("code", "N° fournisseur")}
              <div><label className="text-[11px] uppercase text-slate-500">Statut</label>
                <select data-testid="sup-status" value={form.status} onChange={(e) => set("status", e.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm">
                  <option value="active">Actif</option><option value="inactive">Inactif</option></select></div>
              <div><label className="text-[11px] uppercase text-slate-500">Langue</label>
                <select data-testid="sup-language" value={form.language} onChange={(e) => set("language", e.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm">
                  <option value="fr">Français</option><option value="en">Anglais</option></select></div>
              {F("website", "Site Web")}
              <div className="col-span-2 lg:col-span-3">{F("internal_notes", "Notes internes")}</div>
            </div>
          )}

          {section === "addresses" && (
            <div className="space-y-3" data-testid="sup-sec-addresses">
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                {F("legal_address", "Adresse légale")}
                {F("remit_to_address", "Adresse de paiement")}
                {F("phone", "Téléphone")}
                {F("email", "Courriel")}
                <div><label className="text-[11px] uppercase text-slate-500">Pays</label>
                  <select data-testid="sup-country" value={form.country} onChange={(e) => { set("country", e.target.value); set("region", ""); }} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm">
                    {COUNTRIES.map((c) => <option key={c.v} value={c.v}>{c.l}</option>)}</select></div>
                <div><label className="text-[11px] uppercase text-slate-500">{form.country === "CH" ? "Canton" : "Province / Territoire"}</label>
                  <select data-testid="sup-region" value={form.region} onChange={(e) => set("region", e.target.value)} disabled={!REGIONS[form.country]} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm disabled:bg-slate-50">
                    <option value="">—</option>{(REGIONS[form.country] || []).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3" data-testid="sup-contacts">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[11px] font-700 uppercase text-slate-500">Contacts</span>
                  <Button type="button" variant="outline" size="sm" className="h-7 gap-1" data-testid="sup-contact-add" onClick={addContact}><Plus size={12} /> Ajouter</Button>
                </div>
                {(form.contacts || []).length === 0 && <p className="text-xs text-slate-400">Aucun contact.</p>}
                {(form.contacts || []).map((ct, i) => (
                  <div key={i} className="mb-2 flex flex-wrap items-center gap-2" data-testid={`sup-contact-${i}`}>
                    <Input placeholder="Nom" value={ct.name} onChange={(e) => setContact(i, "name", e.target.value)} className="h-9 w-40" data-testid={`sup-contact-name-${i}`} />
                    <Input placeholder="Courriel" value={ct.email} onChange={(e) => setContact(i, "email", e.target.value)} className="h-9 w-48" data-testid={`sup-contact-email-${i}`} />
                    <Input placeholder="Téléphone" value={ct.phone} onChange={(e) => setContact(i, "phone", e.target.value)} className="h-9 w-36" data-testid={`sup-contact-phone-${i}`} />
                    <label className="flex items-center gap-1 text-xs text-slate-500"><input type="radio" name="sup_primary" checked={form.primary_contact === (ct.name || `#${i}`)} onChange={() => set("primary_contact", ct.name || `#${i}`)} data-testid={`sup-contact-primary-${i}`} /> Principal</label>
                    <Button type="button" variant="ghost" size="sm" className="h-9 text-rose-500" onClick={() => rmContact(i)}><Trash2 size={14} /></Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {section === "billing" && (
            <div className="space-y-3" data-testid="sup-sec-billing">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                <div><label className="text-[11px] uppercase text-slate-500">Devise par défaut</label>
                  <Input data-testid="sup-currency" value={form.default_currency} onChange={(e) => set("default_currency", e.target.value.toUpperCase())} className="mt-1 h-9 w-full" /></div>
                {F("payment_terms", "Conditions de paiement", { ph: "Net 30" })}
                {F("due_days", "Échéance (jours)", { ph: "30" })}
                {F("preferred_payment_method", "Méthode de paiement préférée", { ph: "Virement / Chèque…" })}
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <span className="text-[11px] font-700 uppercase text-slate-500">Coordonnées bancaires (paiement)</span>
                <div className="mt-2 grid grid-cols-2 gap-3 lg:grid-cols-3">
                  {F("bank_iban", "IBAN")}
                  {F("bank_transit", "Transit / Institution")}
                  {F("bank_account", "N° de compte")}
                </div>
                <p className="mt-1 text-[11px] text-slate-400">Les numéros seront masqués après enregistrement.</p>
              </div>
            </div>
          )}

          {section === "tax" && (
            <div className="space-y-3" data-testid="sup-sec-tax">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                {F("tax_regime", "Régime fiscal", { ph: "Standard / Exempté…" })}
                {F("tax_ids", "Numéros fiscaux", { ph: "TPS:123, TVQ:456, TVA:CHE-789" })}
                {F("tax_exemptions", "Exemptions fiscales", { ph: "Ex: revente, OSBL…" })}
              </div>
              {form.country && (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid="sup-tax-proposal">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[11px] font-700 uppercase text-slate-500">Configuration fiscale proposée {taxProposal?.jurisdiction ? `· ${taxProposal.jurisdiction}` : ""}</span>
                    {taxProposal && !taxProposal.supported && <span className="text-[11px] text-amber-600">Juridiction à configurer manuellement</span>}
                  </div>
                  {taxProposal ? (
                    <div className="flex flex-wrap gap-1.5" data-testid="sup-tax-codes">
                      {taxProposal.tax_codes.filter((c) => c.tax_kind === "taxable").map((c) => (
                        <span key={c.code} className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-600 text-slate-500">
                          {c.label} · {c.components.map((k) => `${(k.rate * 100).toFixed(k.rate * 100 % 1 ? 3 : 0)}%`).join(" + ") || "0%"}
                        </span>
                      ))}
                    </div>
                  ) : <p className="text-xs text-slate-400">Sélectionnez un pays (et une province/canton).</p>}
                  <p className="mt-2 text-[11px] text-slate-400">Défaut intelligent basé sur la juridiction — les taux sont versionnés par date d'effet ; une facture historique n'est jamais recalculée.</p>
                </div>
              )}
            </div>
          )}

          {section === "accounting" && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-3" data-testid="sup-sec-accounting">
              {F("default_expense_account_code", "Compte de charge par défaut", { ph: "ex. 6000" })}
              {F("default_ap_account_code", "Compte fournisseurs par défaut", { ph: "ex. 2000" })}
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-sm text-slate-600">
                  <input type="checkbox" checked={form.requires_po} onChange={(e) => set("requires_po", e.target.checked)} data-testid="sup-requires-po" />
                  Bon de commande obligatoire
                </label>
              </div>
            </div>
          )}

          {section === "documents" && (
            <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400" data-testid="sup-sec-documents">
              Les documents liés (contrats, W-9, coordonnées bancaires) apparaîtront ici après la création du fournisseur.
            </div>
          )}

          {section === "history" && (
            <div className="rounded-lg border border-slate-200 p-4 text-sm text-slate-500" data-testid="sup-sec-history">
              L'historique d'audit (création, modifications, statut) sera visible ici une fois le fournisseur enregistré.
            </div>
          )}

          <div className="mt-4 border-t border-slate-100 pt-3">
            <Button data-testid="sup-create" onClick={create} disabled={!form.name.trim()} className="h-9 gap-1 bg-[#22C55E] text-white"><Plus size={14} /> Créer le fournisseur</Button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-300" /></div>
      ) : suppliers.length === 0 ? (
        <p className="text-sm text-slate-400" data-testid="ap-suppliers-empty">Aucun fournisseur.</p>
      ) : (
        <div className="space-y-2">
          {suppliers.map((s) => (
            <div key={s.id} data-testid={`sup-row-${s.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-600 text-[#0F172A]">{s.name}</span>
                  {s.code && <span className="font-mono-data text-xs text-slate-400">{s.code}</span>}
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-600 ${s.status === "active" ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{s.status === "active" ? "Actif" : "Inactif"}</span>
                  {s.requires_po && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-600 text-amber-700">PO requis</span>}
                </div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {s.jurisdiction || s.country || "—"}{s.region ? ` / ${s.region}` : ""} · {s.default_currency || "—"}
                  {s.payment_terms ? ` · ${s.payment_terms}` : ""}{s.email ? ` · ${s.email}` : ""}
                </div>
              </div>
              {s.credit_balance ? <span className="text-sm font-600 text-emerald-600">Crédit {money(s.credit_balance, s.default_currency)}</span> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
