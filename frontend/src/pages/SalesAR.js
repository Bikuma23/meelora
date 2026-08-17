import { useState, useEffect, useCallback } from "react";
import { useNav } from "../context/NavContext";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import {
  Loader2, Plus, Users, FileText, Settings2, Trash2, Send, ThumbsUp, Stamp, RotateCcw,
  Banknote, FileMinus, LayoutDashboard, Clock, Bell, FileDown, Link2, ChevronDown, ChevronRight, RefreshCw,
} from "lucide-react";

const INV_STATUS = {
  draft: { label: "Brouillon", cls: "bg-slate-100 text-slate-600" },
  submitted: { label: "Soumise", cls: "bg-blue-100 text-blue-700" },
  approved: { label: "Approuvée", cls: "bg-amber-100 text-amber-700" },
  posted: { label: "Comptabilisée", cls: "bg-emerald-100 text-emerald-700" },
  partially_paid: { label: "Partiel. payée", cls: "bg-teal-100 text-teal-700" },
  paid: { label: "Payée", cls: "bg-emerald-100 text-emerald-800" },
  void: { label: "Extournée", cls: "bg-rose-100 text-rose-700" },
};
const CN_STATUS = {
  draft: { label: "Brouillon", cls: "bg-slate-100 text-slate-600" },
  submitted: { label: "Soumise", cls: "bg-blue-100 text-blue-700" },
  approved: { label: "Approuvée", cls: "bg-amber-100 text-amber-700" },
  posted: { label: "Comptabilisée", cls: "bg-emerald-100 text-emerald-700" },
};
const money = (v, c) => `${Number(v || 0).toFixed(2)} ${c || ""}`.trim();
// Safely stringify FastAPI errors (422 detail may be an array of objects → never render an object).
const errMsg = (e) => {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => x?.msg || "").filter(Boolean).join(" — ") || "Erreur de validation";
  return "Erreur";
};
const BUCKETS = [
  { key: "current", label: "Courant" }, { key: "d1_30", label: "1–30 j" },
  { key: "d31_60", label: "31–60 j" }, { key: "d61_90", label: "61–90 j" }, { key: "d90_plus", label: "90+ j" },
];
const TABS = [
  { key: "overview", label: "Aperçu AR", icon: LayoutDashboard },
  { key: "invoices", label: "Factures", icon: FileText },
  { key: "payments", label: "Paiements", icon: Banknote },
  { key: "credit_notes", label: "Notes de crédit", icon: FileMinus },
  { key: "customers", label: "Clients", icon: Users },
  { key: "aging", label: "Aging", icon: Clock },
  { key: "reminders", label: "Relances", icon: Bell },
  { key: "config", label: "Configuration", icon: Settings2 },
];

async function openDocument(cid, docId) {
  try {
    const blob = await api.arDownloadDocument(cid, docId);
    const url = URL.createObjectURL(blob);
    const win = window.open(url, "_blank");
    if (!win) {
      const a = document.createElement("a");
      a.href = url; a.download = "document.pdf"; document.body.appendChild(a); a.click(); a.remove();
    }
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (e) { toast.error("Document indisponible"); }
}

export default function SalesAR() {
  const { activeCompanyId: cid } = useNav();
  const [tab, setTab] = useState("overview");
  const [customers, setCustomers] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [taxCodes, setTaxCodes] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [creditNotes, setCreditNotes] = useState([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    if (!cid) return;
    setLoading(true);
    try {
      const [c, i, t, p, cn] = await Promise.all([
        api.arCustomers(cid), api.arInvoices(cid), api.arTaxCodes(cid), api.glPeriods(cid), api.arCreditNotes(cid),
      ]);
      setCustomers(c.customers || []); setInvoices(i.invoices || []);
      setTaxCodes(t.tax_codes || []); setPeriods(p.periods || []); setCreditNotes(cn.credit_notes || []);
    } catch (e) { /* gating handled by page */ }
    setLoading(false);
  }, [cid]);
  useEffect(() => { reload(); }, [reload]);

  // Deep-link focus from the Company Home "recent activity" click.
  useEffect(() => {
    let raw = null;
    try { raw = sessionStorage.getItem("ar_focus"); } catch (e) { /* ignore */ }
    if (!raw) return;
    try { sessionStorage.removeItem("ar_focus"); } catch (e) { /* ignore */ }
    let f = null;
    try { f = JSON.parse(raw); } catch (e) { return; }
    if (f?.tab) setTab(f.tab);
    if (f?.id) {
      setTimeout(() => {
        const el = document.querySelector(`[data-testid$="row-${f.id}"]`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          el.classList.add("ring-2", "ring-emerald-400", "ring-offset-2");
          setTimeout(() => el.classList.remove("ring-2", "ring-emerald-400", "ring-offset-2"), 2600);
        }
      }, 600);
    }
  }, []);

  const custName = (id) => customers.find((x) => x.id === id)?.name || (id || "").slice(0, 8);

  if (!cid) return <div className="p-6 text-sm text-slate-400">Sélectionnez un mandat.</div>;
  if (loading) return <div className="flex items-center gap-2 p-6 text-slate-500"><Loader2 className="animate-spin" size={16}/> Chargement…</div>;

  return (
    <div className="space-y-5" data-testid="ar-page">
      <div className="flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((T) => (
          <button key={T.key} data-testid={`ar-tab-${T.key}`} onClick={() => setTab(T.key)}
            className={`flex items-center gap-2 px-3.5 py-2.5 text-sm font-600 transition-colors ${tab === T.key ? "border-b-2 border-[#22C55E] text-[#0F172A]" : "text-slate-500 hover:text-[#0F172A]"}`}>
            <T.icon size={15} /> {T.label}
          </button>
        ))}
      </div>
      {tab === "overview" && <OverviewTab cid={cid} onGo={setTab} />}
      {tab === "invoices" && <InvoicesTab cid={cid} customers={customers} taxCodes={taxCodes} periods={periods} invoices={invoices} reload={reload} custName={custName} />}
      {tab === "payments" && <PaymentsTab cid={cid} invoices={invoices} custName={custName} />}
      {tab === "credit_notes" && <CreditNotesTab cid={cid} creditNotes={creditNotes} invoices={invoices} reload={reload} />}
      {tab === "customers" && <CustomersTab cid={cid} customers={customers} taxCodes={taxCodes} reload={reload} />}
      {tab === "aging" && <AgingTab cid={cid} custName={custName} />}
      {tab === "reminders" && <RemindersTab cid={cid} custName={custName} />}
      {tab === "config" && <ConfigTab cid={cid} reload={reload} />}
    </div>
  );
}

function Kpi({ label, value, sub, testid }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid={testid}>
      <p className="text-[11px] uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-700 text-[#063044]">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

function OverviewTab({ cid, onGo }) {
  const [ov, setOv] = useState(null);
  useEffect(() => { api.arOverview(cid).then(setOv).catch(() => setOv(null)); }, [cid]);
  if (!ov) return <p className="text-sm text-slate-400" data-testid="ar-overview-empty">Aucune donnée.</p>;
  const cur = ov.functional_currency;
  return (
    <div className="space-y-4" data-testid="ar-overview-tab">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi testid="ov-open-ar" label="Créances ouvertes" value={money(ov.open_ar_functional, cur)} sub="Solde clients (devise fonct.)" />
        <Kpi testid="ov-overdue" label="Échu" value={money(ov.overdue_functional, cur)} sub="Factures en retard" />
        <Kpi testid="ov-credit" label="Crédits clients dispo." value={money(ov.unapplied_customer_credit, cur)} />
        <Kpi testid="ov-customers" label="Clients" value={ov.customer_count} />
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="font-600 text-[#063044]">Balance âgée</h3>
          <Button size="sm" variant="outline" className="h-8" data-testid="ov-go-aging" onClick={() => onGo("aging")}>Détail Aging</Button>
        </div>
        <div className="grid grid-cols-5 gap-2">
          {BUCKETS.map((b) => (
            <div key={b.key} className="rounded-lg bg-slate-50 p-3 text-center" data-testid={`ov-bucket-${b.key}`}>
              <p className="text-[11px] uppercase text-slate-500">{b.label}</p>
              <p className="mt-1 text-sm font-600 text-[#0F172A]">{money(ov.buckets[b.key], cur)}</p>
            </div>
          ))}
        </div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="mb-3 font-600 text-[#063044]">Factures par statut</h3>
        <div className="flex flex-wrap gap-2">
          {Object.entries(ov.invoice_counts || {}).map(([k, v]) => (
            <span key={k} className={`rounded-full px-3 py-1 text-xs font-600 ${(INV_STATUS[k] || INV_STATUS.draft).cls}`} data-testid={`ov-count-${k}`}>
              {(INV_STATUS[k] || { label: k }).label} : {v}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function PaymentsTab({ cid, invoices, custName }) {
  const [payments, setPayments] = useState([]);
  const invNum = (id) => invoices.find((x) => x.id === id)?.number || (id || "").slice(0, 8);
  useEffect(() => { api.arPayments(cid).then((r) => setPayments(r.payments || [])).catch(() => setPayments([])); }, [cid]);
  return (
    <div className="space-y-2" data-testid="ar-payments-tab">
      {payments.length === 0 && <p className="text-sm text-slate-400" data-testid="ar-payments-empty">Aucun encaissement.</p>}
      {payments.map((p) => (
        <div key={p.id} data-testid={`pay-row-${p.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3">
          <div className="flex items-center gap-3">
            <span className="font-mono-data text-sm font-600 text-[#0F172A]">{money(p.amount, p.currency)}</span>
            <span className="text-sm text-slate-500">Facture {invNum(p.invoice_id)} · {custName(p.customer_id)}</span>
            <span className="text-xs text-slate-400">{p.date} · {p.method}</span>
          </div>
          {p.realized_fx ? <span className={`text-xs font-600 ${p.realized_fx > 0 ? "text-emerald-600" : "text-rose-600"}`}>FX {p.realized_fx > 0 ? "+" : ""}{p.realized_fx}</span> : null}
        </div>
      ))}
    </div>
  );
}

function AgingTab({ cid, custName }) {
  const [ag, setAg] = useState(null);
  useEffect(() => { api.arAging(cid).then(setAg).catch(() => setAg(null)); }, [cid]);
  if (!ag) return <p className="text-sm text-slate-400" data-testid="ar-aging-empty">Aucune donnée.</p>;
  const cur = ag.functional_currency;
  return (
    <div className="space-y-4" data-testid="ar-aging-tab">
      <div className="grid grid-cols-5 gap-2">
        {BUCKETS.map((b) => (
          <div key={b.key} className="rounded-lg border border-slate-200 bg-white p-3 text-center" data-testid={`aging-bucket-${b.key}`}>
            <p className="text-[11px] uppercase text-slate-500">{b.label}</p>
            <p className="mt-1 text-sm font-600 text-[#0F172A]">{money(ag.buckets[b.key], cur)}</p>
          </div>
        ))}
      </div>
      <div className="rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-slate-100 text-left text-[11px] uppercase text-slate-500">
            <th className="p-3">Facture</th><th className="p-3">Client</th><th className="p-3">Échéance</th><th className="p-3">Tranche</th><th className="p-3 text-right">Solde</th>
          </tr></thead>
          <tbody>
            {ag.rows.length === 0 && <tr><td colSpan={5} className="p-3 text-slate-400" data-testid="aging-rows-empty">Aucune facture ouverte.</td></tr>}
            {ag.rows.map((r) => (
              <tr key={r.invoice_id} className="border-b border-slate-50" data-testid={`aging-row-${r.invoice_id}`}>
                <td className="p-3 font-mono-data">{r.number || r.invoice_id.slice(0, 8)}</td>
                <td className="p-3">{custName(r.customer_id)}</td>
                <td className="p-3">{r.due_date}</td>
                <td className="p-3">{(BUCKETS.find((b) => b.key === r.bucket) || {}).label}</td>
                <td className="p-3 text-right">{money(r.balance, r.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RemindersTab({ cid, custName }) {
  const [overdue, setOverdue] = useState([]);
  const [reminders, setReminders] = useState([]);
  const [msg, setMsg] = useState("");
  const [openFor, setOpenFor] = useState(null);
  const load = useCallback(async () => {
    try {
      const [o, r] = await Promise.all([api.arOverdue(cid), api.arReminders(cid)]);
      setOverdue(o.overdue || []); setReminders(r.reminders || []);
    } catch (e) { /* gated */ }
  }, [cid]);
  useEffect(() => { load(); }, [load]);
  const send = async (invoice_id) => {
    try {
      const r = await api.arCreateReminder(cid, { invoice_id, message: msg });
      if (r.status === "sent") toast.success(`Relance envoyée à ${r.sent_to}`);
      else if (r.status === "failed") toast.warning(`Relance générée mais envoi échoué : ${r.error || ""}`);
      else toast.success("Relance générée");
      setOpenFor(null); setMsg(""); load();
    } catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <div className="space-y-5" data-testid="ar-reminders-tab">
      <div>
        <h3 className="mb-2 font-600 text-[#063044]">Factures échues</h3>
        {overdue.length === 0 && <p className="text-sm text-slate-400" data-testid="ar-overdue-empty">Aucune facture échue.</p>}
        <div className="space-y-2">
          {overdue.map((o) => (
            <div key={o.invoice_id} data-testid={`overdue-row-${o.invoice_id}`} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-3">
                  <span className="font-mono-data text-sm font-600 text-[#0F172A]">{o.number || o.invoice_id.slice(0, 8)}</span>
                  <span className="text-sm text-slate-500">{custName(o.customer_id)} · Solde {money(o.balance, o.currency)}</span>
                  <span className="rounded-full bg-rose-100 px-2 py-0.5 text-[11px] font-600 text-rose-700">{o.days_overdue} j de retard</span>
                  {o.reminders_sent > 0 && <span className="text-[11px] text-slate-400">{o.reminders_sent} relance(s)</span>}
                </div>
                <Button size="sm" className="h-8 gap-1 bg-[#063044] text-white" data-testid={`send-reminder-${o.invoice_id}`} onClick={() => setOpenFor(openFor === o.invoice_id ? null : o.invoice_id)}>
                  <Send size={13}/> Relancer
                </Button>
              </div>
              {openFor === o.invoice_id && (
                <div className="mt-3 flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3" data-testid={`reminder-form-${o.invoice_id}`}>
                  <div className="flex-1"><label className="text-[11px] uppercase text-slate-500">Message (optionnel)</label>
                    <Input data-testid={`reminder-msg-${o.invoice_id}`} value={msg} onChange={(e) => setMsg(e.target.value)} className="mt-1 h-9" placeholder="Merci de régulariser le solde dû." /></div>
                  <Button size="sm" className="h-9 bg-[#22C55E] text-white" data-testid={`reminder-confirm-${o.invoice_id}`} onClick={() => send(o.invoice_id)}>Générer & envoyer</Button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
      <div>
        <h3 className="mb-2 font-600 text-[#063044]">Historique des relances</h3>
        {reminders.length === 0 && <p className="text-sm text-slate-400" data-testid="ar-reminders-empty">Aucune relance.</p>}
        <div className="space-y-2">
          {reminders.map((r) => (
            <div key={r.id} data-testid={`reminder-row-${r.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex items-center gap-3">
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-600 text-slate-600">Niveau {r.level}</span>
                <span className="text-sm text-slate-500">{custName(r.customer_id)} · {r.sent_to || r.channel}</span>
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-600 ${r.status === "sent" ? "bg-emerald-100 text-emerald-700" : r.status === "failed" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}`}>{r.status}</span>
                <span className="text-xs text-slate-400">{(r.sent_at || "").slice(0, 16).replace("T", " ")}</span>
              </div>
              {r.document_id && <Button size="sm" variant="ghost" className="h-8 gap-1" data-testid={`reminder-pdf-${r.id}`} onClick={() => openDocument(cid, r.document_id)}><FileDown size={13}/>PDF</Button>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function CreditNotesTab({ cid, creditNotes, invoices, reload }) {
  const invNum = (id) => { const i = invoices.find((x) => x.id === id); return i ? (i.number || i.id.slice(0, 8)) : (id || "").slice(0, 8); };
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); reload(); } catch (e) { toast.error(errMsg(e)); } };
  return (
    <div className="space-y-2" data-testid="ar-credit-notes-tab">
      <p className="text-xs text-slate-400">Créez une note de crédit depuis l'onglet Factures. Approbation & comptabilisation ici (maker-checker : le créateur ne peut pas approuver).</p>
      {creditNotes.length === 0 && <p className="text-sm text-slate-400" data-testid="ar-cn-empty">Aucune note de crédit.</p>}
      {creditNotes.map((cn) => {
        const M = CN_STATUS[cn.status] || CN_STATUS.draft;
        return (
          <div key={cn.id} data-testid={`cn-row-${cn.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white p-3">
            <div className="flex items-center gap-3">
              <span className="font-mono-data text-sm font-600 text-[#0F172A]">{cn.number || cn.id.slice(0, 10)}</span>
              <span className={`rounded-full px-2 py-0.5 text-[11px] font-600 ${M.cls}`} data-testid={`cn-status-${cn.id}`}>{M.label}</span>
              <span className="text-sm text-slate-500">Facture {invNum(cn.invoice_id)} · {money(cn.total, cn.currency)}</span>
              {cn.creates_customer_credit && <span className="text-[11px] font-600 text-teal-600">→ crédit client</span>}
            </div>
            <div className="flex gap-1.5">
              {cn.status === "draft" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`cn-submit-btn-${cn.id}`} onClick={() => act(() => api.arSubmitCreditNote(cid, cn.id), "Soumise")}><Send size={13}/>Soumettre</Button>}
              {cn.status === "submitted" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`cn-approve-${cn.id}`} onClick={() => act(() => api.arApproveCreditNote(cid, cn.id), "Approuvée")}><ThumbsUp size={13}/>Approuver</Button>}
              {cn.status === "approved" && <Button size="sm" className="h-8 gap-1 bg-emerald-600 text-white" data-testid={`cn-post-${cn.id}`} onClick={() => act(() => api.arPostCreditNote(cid, cn.id), "Comptabilisée")}><Stamp size={13}/>Comptabiliser</Button>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const EMPTY_CUST = {
  name: "", legal_name: "", code: "", status: "active", default_currency: "CAD", default_tax_code: "", billing_email: "", phone: "",
  legal_address: "", billing_address: "", shipping_address: "", country: "", region: "", jurisdiction: "", language: "fr",
  payment_terms: "", due_days: "", tax_regime: "", customer_po: "", credit_limit: "", tax_ids: "", tax_exemptions: "", internal_notes: "",
  contacts: [], primary_contact: "",
};
const CUST_SECTIONS = [
  { key: "general", label: "Général" },
  { key: "addresses", label: "Adresses & contacts" },
  { key: "billing", label: "Facturation" },
  { key: "tax", label: "Fiscalité" },
  { key: "documents", label: "Documents" },
  { key: "history", label: "Historique" },
];
const COUNTRIES = [{ v: "CA", l: "Canada" }, { v: "CH", l: "Suisse" }, { v: "", l: "Autre / International" }];
const REGIONS = {
  CA: [["QC", "Québec"], ["ON", "Ontario"], ["BC", "Colombie-Britannique"], ["AB", "Alberta"], ["MB", "Manitoba"],
       ["SK", "Saskatchewan"], ["NS", "Nouvelle-Écosse"], ["NB", "Nouveau-Brunswick"], ["NL", "Terre-Neuve-et-Labrador"],
       ["PE", "Île-du-Prince-Édouard"], ["NT", "Territoires du Nord-Ouest"], ["YT", "Yukon"], ["NU", "Nunavut"]],
  CH: [["GE", "Genève"], ["VD", "Vaud"], ["ZH", "Zurich"], ["BE", "Berne"], ["VS", "Valais"], ["FR", "Fribourg"],
       ["TI", "Tessin"], ["BS", "Bâle-Ville"], ["LU", "Lucerne"], ["SG", "Saint-Gall"]],
};
function CustomersTab({ cid, customers, taxCodes, reload }) {
  const [form, setForm] = useState({ ...EMPTY_CUST });
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(null);
  const [taxProposal, setTaxProposal] = useState(null);
  const [section, setSection] = useState("general");
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  // Country + region → propose the applicable tax configuration from the central
  // engine (no rate hardcoded here).
  useEffect(() => {
    if (!form.country) { setTaxProposal(null); return; }
    api.getTaxJurisdictionConfig({ country: form.country, region: form.region || undefined })
      .then((cfg) => {
        setTaxProposal(cfg);
        setForm((f) => ({ ...f, jurisdiction: cfg.jurisdiction, default_tax_code: cfg.default_tax_code || f.default_tax_code }));
      }).catch(() => setTaxProposal(null));
  }, [form.country, form.region]); // eslint-disable-line react-hooks/exhaustive-deps

  const create = async () => {
    try {
      const body = { ...form, credit_limit: form.credit_limit ? Number(form.credit_limit) : undefined,
        due_days: form.due_days ? Number(form.due_days) : undefined,
        contacts: (form.contacts || []).filter((c) => c.name || c.email || c.phone),
        primary_contact: form.primary_contact ? { name: form.primary_contact } : undefined,
        tax_exemptions: form.tax_exemptions ? String(form.tax_exemptions).split(",").map((s) => ({ code: s.trim() })).filter((x) => x.code) : [] };
      if (form.tax_ids) { const tt = {}; form.tax_ids.split(",").forEach((p) => { const [k, v] = p.split(":"); if (k && v) tt[k.trim()] = v.trim(); }); body.tax_ids = tt; }
      else delete body.tax_ids;
      await api.arCreateCustomer(cid, body); toast.success("Client créé"); setForm({ ...EMPTY_CUST }); setTaxProposal(null); setSection("general"); setOpen(false); reload();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const F = (k, label, props = {}) => (
    <div><label className="text-[11px] uppercase text-slate-500">{label}</label>
      <Input data-testid={`cust-${k}`} value={form[k]} onChange={(e) => set(k, props.upper ? e.target.value.toUpperCase() : e.target.value)} className="mt-1 h-9 w-full" placeholder={props.ph || ""} /></div>
  );
  const addContact = () => set("contacts", [...(form.contacts || []), { name: "", email: "", phone: "", role: "" }]);
  const setContact = (i, k, v) => set("contacts", (form.contacts || []).map((c, j) => j === i ? { ...c, [k]: v } : c));
  const rmContact = (i) => set("contacts", (form.contacts || []).filter((_, j) => j !== i));
  return (
    <div className="space-y-4" data-testid="ar-customers-tab">
      <Button data-testid="cust-toggle" onClick={() => setOpen((v) => !v)} className="h-9 gap-1 bg-[#063044] text-white"><Plus size={14}/> Nouveau client</Button>
      {open && (
        <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="cust-form">
          <div className="mb-4 flex flex-wrap gap-1 border-b border-slate-200">
            {CUST_SECTIONS.map((s) => (
              <button key={s.key} type="button" data-testid={`cust-section-${s.key}`} onClick={() => setSection(s.key)}
                className={`px-3 py-2 text-sm font-600 transition-colors ${section === s.key ? "border-b-2 border-[#22C55E] text-[#0F172A]" : "text-slate-500 hover:text-[#0F172A]"}`}>{s.label}</button>
            ))}
          </div>

          {section === "general" && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-3" data-testid="cust-sec-general">
              {F("name", "Nom / Raison sociale")}
              {F("legal_name", "Dénomination légale")}
              {F("code", "N° client")}
              <div><label className="text-[11px] uppercase text-slate-500">Statut</label>
                <select data-testid="cust-status" value={form.status} onChange={(e) => set("status", e.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm">
                  <option value="active">Actif</option><option value="inactive">Inactif</option></select></div>
              <div><label className="text-[11px] uppercase text-slate-500">Langue</label>
                <select data-testid="cust-language" value={form.language} onChange={(e) => set("language", e.target.value)} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm">
                  <option value="fr">Français</option><option value="en">Anglais</option></select></div>
              <div className="col-span-2 lg:col-span-3">{F("internal_notes", "Notes")}</div>
            </div>
          )}

          {section === "addresses" && (
            <div className="space-y-3" data-testid="cust-sec-addresses">
              <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
                {F("legal_address", "Adresse légale")}
                {F("billing_address", "Adresse de facturation")}
                {F("shipping_address", "Adresse de livraison")}
                {F("phone", "Téléphone")}
                {F("billing_email", "Courriel de facturation")}
                <div><label className="text-[11px] uppercase text-slate-500">Pays</label>
                  <select data-testid="cust-country" value={form.country} onChange={(e) => set("country", e.target.value) || set("region", "")} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm">
                    {COUNTRIES.map((c) => <option key={c.v} value={c.v}>{c.l}</option>)}</select></div>
                <div><label className="text-[11px] uppercase text-slate-500">{form.country === "CH" ? "Canton" : "Province / Territoire"}</label>
                  <select data-testid="cust-region" value={form.region} onChange={(e) => set("region", e.target.value)} disabled={!REGIONS[form.country]} className="mt-1 h-9 w-full rounded-md border border-slate-200 px-2 text-sm disabled:bg-slate-50">
                    <option value="">—</option>{(REGIONS[form.country] || []).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3" data-testid="cust-contacts">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-[11px] font-700 uppercase text-slate-500">Contacts</span>
                  <Button type="button" variant="outline" size="sm" className="h-7 gap-1" data-testid="cust-contact-add" onClick={addContact}><Plus size={12}/> Ajouter</Button>
                </div>
                {(form.contacts || []).length === 0 && <p className="text-xs text-slate-400">Aucun contact.</p>}
                {(form.contacts || []).map((ct, i) => (
                  <div key={i} className="mb-2 flex flex-wrap items-center gap-2" data-testid={`cust-contact-${i}`}>
                    <Input placeholder="Nom" value={ct.name} onChange={(e) => setContact(i, "name", e.target.value)} className="h-9 w-40" data-testid={`cust-contact-name-${i}`} />
                    <Input placeholder="Courriel" value={ct.email} onChange={(e) => setContact(i, "email", e.target.value)} className="h-9 w-48" data-testid={`cust-contact-email-${i}`} />
                    <Input placeholder="Téléphone" value={ct.phone} onChange={(e) => setContact(i, "phone", e.target.value)} className="h-9 w-36" data-testid={`cust-contact-phone-${i}`} />
                    <label className="flex items-center gap-1 text-xs text-slate-500"><input type="radio" name="primary_contact" checked={form.primary_contact === (ct.name || `#${i}`)} onChange={() => set("primary_contact", ct.name || `#${i}`)} data-testid={`cust-contact-primary-${i}`} /> Principal</label>
                    <Button type="button" variant="ghost" size="sm" className="h-9 text-rose-500" onClick={() => rmContact(i)}><Trash2 size={14}/></Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {section === "billing" && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-3" data-testid="cust-sec-billing">
              <div><label className="text-[11px] uppercase text-slate-500">Devise de facturation</label>
                <Input data-testid="cust-currency" value={form.default_currency} onChange={(e) => set("default_currency", e.target.value.toUpperCase())} className="mt-1 h-9 w-full" /></div>
              {F("payment_terms", "Conditions de paiement", { ph: "Net 30" })}
              {F("due_days", "Échéance (jours)", { ph: "30" })}
              {F("customer_po", "Référence / PO client")}
              {F("credit_limit", "Limite de crédit")}
            </div>
          )}

          {section === "tax" && (
            <div className="space-y-3" data-testid="cust-sec-tax">
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                {F("tax_regime", "Régime fiscal", { ph: "Standard / Exempté…" })}
                {F("tax_ids", "Identifiants fiscaux", { ph: "TVA:CHE-123, GST:456" })}
                {F("tax_exemptions", "Exemptions fiscales", { ph: "Ex: revente, OSBL…" })}
              </div>
              {form.country && (
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3" data-testid="cust-tax-proposal">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-[11px] font-700 uppercase text-slate-500">Configuration fiscale proposée {taxProposal?.jurisdiction ? `· ${taxProposal.jurisdiction}` : ""}</span>
                    {taxProposal && !taxProposal.supported && <span className="text-[11px] text-amber-600">Juridiction à configurer manuellement</span>}
                  </div>
                  {taxProposal ? (
                    <div className="space-y-2">
                      <div className="flex flex-wrap gap-1.5" data-testid="cust-tax-codes">
                        {taxProposal.tax_codes.filter((c) => c.tax_kind === "taxable").map((c) => (
                          <button key={c.code} type="button" data-testid={`cust-tax-pick-${c.code}`} onClick={() => set("default_tax_code", c.code)}
                            className={`rounded-full border px-3 py-1 text-xs font-600 transition ${form.default_tax_code === c.code ? "border-[#22C55E] bg-[#22C55E]/10 text-[#063044]" : "border-slate-200 bg-white text-slate-500 hover:border-slate-300"}`}>
                            {c.label} · {c.components.map((k) => `${(k.rate * 100).toFixed(k.rate * 100 % 1 ? 3 : 0)}%`).join(" + ") || "0%"}
                          </button>
                        ))}
                      </div>
                      <p className="text-[11px] text-slate-400">Défaut du client — modifiable par un utilisateur autorisé. Les taux sont versionnés : une facture historique n'est jamais recalculée.</p>
                    </div>
                  ) : <p className="text-xs text-slate-400">Sélectionnez un pays (et une province/canton) pour proposer la configuration.</p>}
                </div>
              )}
            </div>
          )}

          {section === "documents" && (
            <div className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-sm text-slate-400" data-testid="cust-sec-documents">
              Les documents liés (contrats, pièces justificatives) apparaîtront ici après la création du client.
            </div>
          )}

          {section === "history" && (
            <div className="rounded-lg border border-slate-200 p-4 text-sm text-slate-500" data-testid="cust-sec-history">
              L'historique d'audit (création, modifications, statut) sera visible ici une fois le client enregistré.
            </div>
          )}

          <div className="mt-4 border-t border-slate-100 pt-3"><Button data-testid="cust-create" onClick={create} disabled={!form.name.trim()} className="h-9 gap-1 bg-[#22C55E] text-white"><Plus size={14}/> Créer le client</Button></div>
        </div>
      )}
      <div className="space-y-2">
        {customers.length === 0 && <p className="text-sm text-slate-400" data-testid="ar-customers-empty">Aucun client.</p>}
        {customers.map((c) => (
          <div key={c.id} data-testid={`cust-row-${c.id}`} className="rounded-xl border border-slate-200 bg-white p-3">
            <div className="flex cursor-pointer items-center justify-between" onClick={() => setExpanded(expanded === c.id ? null : c.id)}>
              <div className="flex items-center gap-2">
                {expanded === c.id ? <ChevronDown size={15} className="text-slate-400"/> : <ChevronRight size={15} className="text-slate-400"/>}
                <span className="font-600 text-[#0F172A]">{c.name}</span>
                <span className="text-xs text-slate-400">{c.code ? `#${c.code} · ` : ""}{c.default_currency} · {c.default_tax_code || "—"}</span>
              </div>
              {c.credit_balance > 0 && <span className="text-xs font-600 text-teal-600" data-testid={`cust-credit-${c.id}`}>Crédit dispo : {money(c.credit_balance, c.default_currency)}</span>}
            </div>
            {expanded === c.id && (
              <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 border-t border-slate-100 pt-3 text-xs text-slate-600 lg:grid-cols-3" data-testid={`cust-detail-${c.id}`}>
                <div><span className="text-slate-400">Courriel : </span>{c.billing_email || "—"}</div>
                <div><span className="text-slate-400">Tél : </span>{c.phone || "—"}</div>
                <div><span className="text-slate-400">Conditions : </span>{c.payment_terms || "—"}{c.due_days ? ` (${c.due_days} j)` : ""}</div>
                <div><span className="text-slate-400">Facturation : </span>{c.billing_address || "—"}</div>
                <div><span className="text-slate-400">Livraison : </span>{c.shipping_address || "—"}</div>
                <div><span className="text-slate-400">Juridiction : </span>{c.jurisdiction || c.country || "—"}{c.region ? ` / ${c.region}` : ""}</div>
                <div><span className="text-slate-400">Régime fiscal : </span>{c.tax_regime || "—"}</div>
                <div><span className="text-slate-400">Taxe défaut : </span>{c.default_tax_code || "—"}</div>
                <div><span className="text-slate-400">Réf/PO : </span>{c.customer_po || "—"}</div>
                <div><span className="text-slate-400">Limite crédit : </span>{c.credit_limit != null ? money(c.credit_limit, c.default_currency) : "—"}</div>
                <div><span className="text-slate-400">N° fiscaux : </span>{Object.entries(c.tax_ids || {}).map(([k, v]) => `${k}:${v}`).join(", ") || "—"}</div>
                <div className="col-span-2 lg:col-span-3"><span className="text-slate-400">Notes : </span>{c.internal_notes || "—"}</div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function ConfigTab({ cid, reload }) {
  const [mapping, setMapping] = useState(null);
  const [fx, setFx] = useState({ from_currency: "USD", to_currency: "CAD", rate: "", rate_date: "" });
  useEffect(() => { api.arMapping(cid).then(setMapping).catch(() => setMapping({})); }, [cid]);
  const seed = async () => { try { const r = await api.arSeedTaxCodes(cid); toast.success(`Codes de taxe : ${r.created.length || "déjà présents"}`); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const saveMapping = async () => { try { await api.arSetMapping(cid, mapping); toast.success("Mapping enregistré"); } catch (e) { toast.error(errMsg(e)); } };
  const recordFx = async () => { try { await api.arRecordFxRate(cid, { ...fx, rate: Number(fx.rate) }); toast.success("Taux enregistré"); setFx({ ...fx, rate: "" }); } catch (e) { toast.error(errMsg(e)); } };
  const M = (k, label) => (
    <div><label className="text-[11px] uppercase text-slate-500">{label}</label>
      <Input data-testid={`map-${k}`} value={(mapping || {})[k] || ""} onChange={(e) => setMapping({ ...mapping, [k]: e.target.value })} className="mt-1 h-9 w-40" /></div>
  );
  return (
    <div className="space-y-5" data-testid="ar-config-tab">
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="mb-2 font-600 text-[#063044]">Codes de taxe</h3>
        <Button data-testid="ar-seed-taxes" onClick={seed} variant="outline" className="h-9 gap-1"><Plus size={14}/> Initialiser les codes de la juridiction</Button>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="mb-3 font-600 text-[#063044]">Mapping des comptes (GL)</h3>
        <div className="flex flex-wrap gap-3">{M("ar_account_code", "Comptes clients")}{M("bank_account_code", "Banque")}{M("default_revenue_account_code", "Produits")}{M("fx_gain_account_code", "Gain FX")}{M("fx_loss_account_code", "Perte FX")}</div>
        <Button data-testid="ar-save-mapping" onClick={saveMapping} className="mt-3 h-9 bg-[#063044] text-white">Enregistrer</Button>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="mb-3 font-600 text-[#063044]">Taux de change</h3>
        <div className="flex flex-wrap items-end gap-2">
          <div><label className="text-[11px] uppercase text-slate-500">De</label><Input data-testid="fx-from" value={fx.from_currency} onChange={(e) => setFx({ ...fx, from_currency: e.target.value.toUpperCase() })} className="mt-1 h-9 w-20"/></div>
          <div><label className="text-[11px] uppercase text-slate-500">Vers</label><Input data-testid="fx-to" value={fx.to_currency} onChange={(e) => setFx({ ...fx, to_currency: e.target.value.toUpperCase() })} className="mt-1 h-9 w-20"/></div>
          <div><label className="text-[11px] uppercase text-slate-500">Taux</label><Input data-testid="fx-rate" value={fx.rate} onChange={(e) => setFx({ ...fx, rate: e.target.value })} className="mt-1 h-9 w-24"/></div>
          <div><label className="text-[11px] uppercase text-slate-500">Date</label><Input data-testid="fx-date" type="date" value={fx.rate_date} onChange={(e) => setFx({ ...fx, rate_date: e.target.value })} className="mt-1 h-9 w-40"/></div>
          <Button data-testid="fx-save" onClick={recordFx} disabled={!fx.rate || !fx.rate_date} className="h-9 bg-[#063044] text-white">Enregistrer</Button>
        </div>
      </div>
    </div>
  );
}

function InvoicesTab({ cid, customers, taxCodes, periods, invoices, reload, custName }) {
  const [creating, setCreating] = useState(false);
  const [functional, setFunctional] = useState("");
  const [fetchingRate, setFetchingRate] = useState(false);
  const emptyLine = { description: "", qty: 1, unit_price: "", tax_code: taxCodes[0]?.code || "EXEMPT" };
  const [form, setForm] = useState({ customer_id: "", period_id: "", currency: "", fx_rate: "", issue_date: "", due_date: "", customer_po: "", reference: "", lines: [{ ...emptyLine }] });

  useEffect(() => { api.getCompany(cid).then((c) => setFunctional((c.functional_currency || "").toUpperCase())).catch(() => {}); }, [cid]);

  const termDays = (c) => c?.due_days ?? (String(c?.payment_terms || "").match(/\d+/)?.[0] ? Number(String(c.payment_terms).match(/\d+/)[0]) : null);
  const addDays = (iso, n) => { try { const d = new Date(iso); d.setDate(d.getDate() + Number(n)); return d.toISOString().slice(0, 10); } catch { return ""; } };

  const onCustomer = (id) => {
    const c = customers.find((x) => x.id === id);
    setForm((f) => {
      const next = { ...f, customer_id: id };
      if (c) {
        if (!f.customer_po) next.customer_po = c.customer_po || "";
        if (!f.currency) next.currency = (c.default_currency || "").toUpperCase();
        const dd = termDays(c);
        if (dd != null && f.issue_date) next.due_date = addDays(f.issue_date, dd);
      }
      return next;
    });
  };
  const onIssueDate = (v) => setForm((f) => {
    const c = customers.find((x) => x.id === f.customer_id);
    const dd = termDays(c);
    return { ...f, issue_date: v, due_date: (dd != null && v) ? addDays(v, dd) : f.due_date };
  });
  const fetchRate = async () => {
    const cur = (form.currency || "").toUpperCase();
    const datev = form.issue_date || new Date().toISOString().slice(0, 10);
    if (!cur || !functional) { toast.error("Devise et date requises."); return; }
    if (cur === functional) { setForm((f) => ({ ...f, fx_rate: "1" })); toast.info("Même devise : taux 1."); return; }
    setFetchingRate(true);
    try {
      const r = await api.arOandaRate(cid, { from_currency: cur, to_currency: functional, on_date: datev });
      if (r.available) { setForm((f) => ({ ...f, fx_rate: String(r.rate) })); toast.success(`Taux OANDA ${cur}/${functional} au ${datev} = ${r.rate}`); }
      else toast.error(r.reason || "Taux OANDA indisponible.");
    } catch (e) { toast.error(e.response?.data?.detail || "Erreur OANDA"); }
    setFetchingRate(false);
  };

  const create = async () => {
    try {
      const body = { ...form, fx_rate: form.fx_rate ? Number(form.fx_rate) : undefined,
        customer_po: form.customer_po || undefined, reference: form.reference || undefined,
        lines: form.lines.map((l) => ({ ...l, qty: Number(l.qty || 1), unit_price: Number(l.unit_price || 0) })) };
      await api.arCreateInvoice(cid, body);
      toast.success("Facture créée"); setCreating(false);
      setForm({ customer_id: "", period_id: "", currency: "", fx_rate: "", issue_date: "", due_date: "", customer_po: "", reference: "", lines: [{ ...emptyLine }] });
      reload();
    } catch (e) { toast.error(errMsg(e)); }
  };
  const fxDisabled = !form.currency || form.currency.toUpperCase() === functional;
  return (
    <div className="space-y-4" data-testid="ar-invoices-tab">
      <Button data-testid="inv-new" onClick={() => setCreating((v) => !v)} className="h-9 gap-1 bg-[#063044] text-white"><Plus size={14}/> Nouvelle facture</Button>
      {creating && (
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4" data-testid="inv-form">
          <div className="flex flex-wrap gap-3">
            <div><label className="text-[11px] uppercase text-slate-500">Client</label>
              <select data-testid="inv-customer" value={form.customer_id} onChange={(e) => onCustomer(e.target.value)} className="mt-1 h-9 w-52 rounded-md border border-slate-200 px-2 text-sm">
                <option value="">—</option>{customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div><label className="text-[11px] uppercase text-slate-500">Période</label>
              <select data-testid="inv-period" value={form.period_id} onChange={(e) => setForm({ ...form, period_id: e.target.value })} className="mt-1 h-9 w-36 rounded-md border border-slate-200 px-2 text-sm">
                <option value="">—</option>{periods.map((p) => <option key={p.id} value={p.id}>{p.code} ({p.status})</option>)}</select></div>
            <div><label className="text-[11px] uppercase text-slate-500">Devise</label><Input data-testid="inv-currency" value={form.currency} placeholder="défaut client" onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} className="mt-1 h-9 w-28"/></div>
            <div><label className="text-[11px] uppercase text-slate-500">Taux FX</label><Input data-testid="inv-fx" value={form.fx_rate} placeholder="auto" onChange={(e) => setForm({ ...form, fx_rate: e.target.value })} className="mt-1 h-9 w-24"/></div>
            <div><label className="text-[11px] uppercase text-slate-500">&nbsp;</label>
              <Button type="button" variant="outline" size="sm" disabled={fxDisabled || fetchingRate} onClick={fetchRate}
                title={fxDisabled ? "Devise fonctionnelle : aucun taux requis" : "Récupérer le taux OANDA à la date de facture"}
                data-testid="inv-fetch-rate" className="mt-1 h-9 gap-1"><RefreshCw size={13} className={fetchingRate ? "animate-spin" : ""}/> Récupérer le taux</Button></div>
            <div><label className="text-[11px] uppercase text-slate-500">Date</label><Input data-testid="inv-date" type="date" value={form.issue_date} onChange={(e) => onIssueDate(e.target.value)} className="mt-1 h-9 w-40"/></div>
            <div><label className="text-[11px] uppercase text-slate-500">Échéance (auto)</label><Input data-testid="inv-due" type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} className="mt-1 h-9 w-40"/></div>
            <div><label className="text-[11px] uppercase text-slate-500">Réf. / PO client</label><Input data-testid="inv-po" value={form.customer_po} placeholder="auto (fiche client)" onChange={(e) => setForm({ ...form, customer_po: e.target.value })} className="mt-1 h-9 w-40"/></div>
            <div><label className="text-[11px] uppercase text-slate-500">Référence</label><Input data-testid="inv-reference" value={form.reference} onChange={(e) => setForm({ ...form, reference: e.target.value })} className="mt-1 h-9 w-40"/></div>
          </div>
          {form.lines.map((l, i) => (
            <div key={i} className="flex flex-wrap items-end gap-2" data-testid={`inv-line-${i}`}>
              <div><label className="text-[11px] uppercase text-slate-500">Description</label><Input data-testid={`inv-line-desc-${i}`} value={l.description} onChange={(e) => { const ls = [...form.lines]; ls[i].description = e.target.value; setForm({ ...form, lines: ls }); }} className="mt-1 h-9 w-52"/></div>
              <div><label className="text-[11px] uppercase text-slate-500">Qté</label><Input data-testid={`inv-line-qty-${i}`} value={l.qty} onChange={(e) => { const ls = [...form.lines]; ls[i].qty = e.target.value; setForm({ ...form, lines: ls }); }} className="mt-1 h-9 w-16"/></div>
              <div><label className="text-[11px] uppercase text-slate-500">Prix</label><Input data-testid={`inv-line-price-${i}`} value={l.unit_price} onChange={(e) => { const ls = [...form.lines]; ls[i].unit_price = e.target.value; setForm({ ...form, lines: ls }); }} className="mt-1 h-9 w-24"/></div>
              <div><label className="text-[11px] uppercase text-slate-500">Taxe</label>
                <select data-testid={`inv-line-tax-${i}`} value={l.tax_code} onChange={(e) => { const ls = [...form.lines]; ls[i].tax_code = e.target.value; setForm({ ...form, lines: ls }); }} className="mt-1 h-9 w-36 rounded-md border border-slate-200 px-2 text-sm">
                  {taxCodes.map((t) => <option key={t.code} value={t.code}>{t.code}</option>)}</select></div>
              {form.lines.length > 1 && <Button variant="ghost" size="sm" className="h-9 text-rose-500" onClick={() => setForm({ ...form, lines: form.lines.filter((_, j) => j !== i) })}><Trash2 size={14}/></Button>}
            </div>
          ))}
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="h-8" onClick={() => setForm({ ...form, lines: [...form.lines, { ...emptyLine }] })}>+ Ligne</Button>
            <Button data-testid="inv-create" onClick={create} disabled={!form.customer_id || !form.period_id} className="h-9 bg-[#22C55E] text-white">Créer la facture</Button>
          </div>
        </div>
      )}
      <div className="space-y-2">
        {invoices.length === 0 && <p className="text-sm text-slate-400" data-testid="ar-invoices-empty">Aucune facture.</p>}
        {invoices.map((inv) => <InvoiceRow key={inv.id} cid={cid} inv={inv} reload={reload} custName={custName} />)}
      </div>
    </div>
  );
}

function InvoiceRow({ cid, inv, reload, custName }) {
  const [payOpen, setPayOpen] = useState(false);
  const [cnOpen, setCnOpen] = useState(false);
  const [drillOpen, setDrillOpen] = useState(false);
  const [source, setSource] = useState(null);
  const [pay, setPay] = useState({ amount: "", fx_rate: "" });
  const [cn, setCn] = useState({ invoice_line_index: 0, net_credit: "" });
  const M = INV_STATUS[inv.status] || INV_STATUS.draft;
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const doPay = async () => { try { await api.arCreatePayment(cid, { invoice_id: inv.id, amount: Number(pay.amount), fx_rate: pay.fx_rate ? Number(pay.fx_rate) : undefined }); toast.success("Encaissement enregistré"); setPayOpen(false); setPay({ amount: "", fx_rate: "" }); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const doCn = async () => { try { const c = await api.arCreateCreditNote(cid, { invoice_id: inv.id, lines: [{ invoice_line_index: Number(cn.invoice_line_index), net_credit: Number(cn.net_credit) }] }); await api.arSubmitCreditNote(cid, c.id); toast.success("Note de crédit créée & soumise (à approuver)"); setCnOpen(false); setCn({ invoice_line_index: 0, net_credit: "" }); reload(); } catch (e) { toast.error(errMsg(e)); } };
  const loadSource = async () => {
    const next = !drillOpen; setDrillOpen(next);
    if (next && inv.journal_entry_id && !source) {
      try { setSource(await api.arJournalSource(cid, inv.journal_entry_id)); } catch (e) { /* ignore */ }
    }
  };
  return (
    <div data-testid={`inv-row-${inv.id}`} className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="font-mono-data text-sm font-600 text-[#0F172A]">{inv.number || inv.id.slice(0, 10)}</span>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-600 ${M.cls}`} data-testid={`inv-status-${inv.id}`}>{M.label}</span>
          <span className="text-sm text-slate-500">{custName(inv.customer_id)} · Total {money(inv.total, inv.currency)} · Solde {money(inv.balance, inv.currency)}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {inv.status === "draft" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-submit-${inv.id}`} onClick={() => act(() => api.arSubmitInvoice(cid, inv.id), "Soumise")}><Send size={13}/>Soumettre</Button>}
          {inv.status === "submitted" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-approve-${inv.id}`} onClick={() => act(() => api.arApproveInvoice(cid, inv.id), "Approuvée (PDF figé)")}><ThumbsUp size={13}/>Approuver</Button>}
          {inv.status === "approved" && <Button size="sm" className="h-8 gap-1 bg-emerald-600 text-white" data-testid={`inv-post-${inv.id}`} onClick={() => act(() => api.arPostInvoice(cid, inv.id), "Comptabilisée")}><Stamp size={13}/>Comptabiliser</Button>}
          {inv.source_document_id && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-pdf-${inv.id}`} onClick={() => openDocument(cid, inv.source_document_id)}><FileDown size={13}/>PDF</Button>}
          {inv.journal_entry_id && <Button size="sm" variant="ghost" className="h-8 gap-1" data-testid={`inv-drill-${inv.id}`} onClick={loadSource}><Link2 size={13}/>Traçabilité</Button>}
          {inv.status === "posted" && inv.amount_paid === 0 && <Button size="sm" variant="outline" className="h-8 gap-1 text-rose-600" data-testid={`inv-void-${inv.id}`} onClick={() => act(() => api.arVoidInvoice(cid, inv.id), "Extournée")}><RotateCcw size={13}/>Extourner</Button>}
          {["posted", "partially_paid"].includes(inv.status) && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-pay-${inv.id}`} onClick={() => setPayOpen((v) => !v)}><Banknote size={13}/>Encaisser</Button>}
          {["posted", "partially_paid", "paid"].includes(inv.status) && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-credit-${inv.id}`} onClick={() => setCnOpen((v) => !v)}><FileMinus size={13}/>Note de crédit</Button>}
        </div>
      </div>
      {drillOpen && (
        <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600" data-testid={`inv-drill-panel-${inv.id}`}>
          <p className="font-600 text-[#063044]">Chaîne de traçabilité</p>
          <p className="mt-1">Facture {inv.number} → Document source {inv.source_document_id ? <button className="text-teal-600 underline" data-testid={`drill-doc-${inv.id}`} onClick={() => openDocument(cid, inv.source_document_id)}>PDF v{inv.source_document_version}</button> : "—"} → Écriture <span className="font-mono-data">{inv.journal_entry_id}</span></p>
          {source && <p className="mt-1 text-slate-500">Retour depuis journal : source = {source.source_type} · {source.external_id} · doc {source.source_document_id || "—"}</p>}
        </div>
      )}
      {payOpen && (
        <div className="mt-3 flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3" data-testid={`inv-pay-form-${inv.id}`}>
          <div><label className="text-[11px] uppercase text-slate-500">Montant ({inv.currency})</label><Input data-testid={`pay-amount-${inv.id}`} value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} className="mt-1 h-9 w-28"/></div>
          <div><label className="text-[11px] uppercase text-slate-500">Taux FX</label><Input data-testid={`pay-fx-${inv.id}`} value={pay.fx_rate} placeholder="auto" onChange={(e) => setPay({ ...pay, fx_rate: e.target.value })} className="mt-1 h-9 w-24"/></div>
          <Button size="sm" className="h-9 bg-[#063044] text-white" data-testid={`pay-submit-${inv.id}`} onClick={doPay} disabled={!pay.amount}>Encaisser</Button>
        </div>
      )}
      {cnOpen && (
        <div className="mt-3 flex flex-wrap items-end gap-2 rounded-lg bg-slate-50 p-3" data-testid={`inv-cn-form-${inv.id}`}>
          <div><label className="text-[11px] uppercase text-slate-500">Ligne #</label><Input data-testid={`cn-line-${inv.id}`} value={cn.invoice_line_index} onChange={(e) => setCn({ ...cn, invoice_line_index: e.target.value })} className="mt-1 h-9 w-16"/></div>
          <div><label className="text-[11px] uppercase text-slate-500">Montant net à créditer</label><Input data-testid={`cn-amount-${inv.id}`} value={cn.net_credit} onChange={(e) => setCn({ ...cn, net_credit: e.target.value })} className="mt-1 h-9 w-32"/></div>
          <Button size="sm" className="h-9 bg-[#063044] text-white" data-testid={`cn-submit-${inv.id}`} onClick={doCn} disabled={!cn.net_credit}>Créer la note de crédit</Button>
        </div>
      )}
    </div>
  );
}
