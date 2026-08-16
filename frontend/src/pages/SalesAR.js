import { useState, useEffect, useCallback } from "react";
import { useNav } from "../context/NavContext";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Loader2, Plus, Users, FileText, Settings2, Trash2, Send, ThumbsUp, Stamp, RotateCcw, Banknote, FileMinus } from "lucide-react";

const INV_STATUS = {
  draft: { label: "Brouillon", cls: "bg-slate-100 text-slate-600" },
  submitted: { label: "Soumise", cls: "bg-blue-100 text-blue-700" },
  approved: { label: "Approuvée", cls: "bg-amber-100 text-amber-700" },
  posted: { label: "Comptabilisée", cls: "bg-emerald-100 text-emerald-700" },
  partially_paid: { label: "Partiel. payée", cls: "bg-teal-100 text-teal-700" },
  paid: { label: "Payée", cls: "bg-emerald-100 text-emerald-800" },
  void: { label: "Extournée", cls: "bg-rose-100 text-rose-700" },
};
const money = (v, c) => `${Number(v || 0).toFixed(2)} ${c || ""}`.trim();
const CN_STATUS = {
  draft: { label: "Brouillon", cls: "bg-slate-100 text-slate-600" },
  submitted: { label: "Soumise", cls: "bg-blue-100 text-blue-700" },
  approved: { label: "Approuvée", cls: "bg-amber-100 text-amber-700" },
  posted: { label: "Comptabilisée", cls: "bg-emerald-100 text-emerald-700" },
};
const TABS = [
  { key: "invoices", label: "Factures", icon: FileText },
  { key: "credit_notes", label: "Notes de crédit", icon: FileMinus },
  { key: "customers", label: "Clients", icon: Users },
  { key: "config", label: "Configuration", icon: Settings2 },
];

export default function SalesAR() {
  const { activeCompanyId: cid } = useNav();
  const [tab, setTab] = useState("invoices");
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

  if (!cid) return <div className="p-6 text-sm text-slate-400">Sélectionnez un mandat.</div>;
  if (loading) return <div className="flex items-center gap-2 p-6 text-slate-500"><Loader2 className="animate-spin" size={16}/> Chargement…</div>;

  return (
    <div className="space-y-5" data-testid="ar-page">
      <div className="flex gap-1 border-b border-slate-200">
        {TABS.map((T) => (
          <button key={T.key} data-testid={`ar-tab-${T.key}`} onClick={() => setTab(T.key)}
            className={`flex items-center gap-2 px-4 py-2.5 text-sm font-600 transition-colors ${tab === T.key ? "border-b-2 border-[#22C55E] text-[#0F172A]" : "text-slate-500 hover:text-[#0F172A]"}`}>
            <T.icon size={15} /> {T.label}
          </button>
        ))}
      </div>
      {tab === "invoices" && <InvoicesTab cid={cid} customers={customers} taxCodes={taxCodes} periods={periods} invoices={invoices} reload={reload} />}
      {tab === "credit_notes" && <CreditNotesTab cid={cid} creditNotes={creditNotes} invoices={invoices} reload={reload} />}
      {tab === "customers" && <CustomersTab cid={cid} customers={customers} taxCodes={taxCodes} reload={reload} />}
      {tab === "config" && <ConfigTab cid={cid} reload={reload} />}
    </div>
  );
}

function CreditNotesTab({ cid, creditNotes, invoices, reload }) {
  const invNum = (id) => { const i = invoices.find((x) => x.id === id); return i ? (i.number || i.id.slice(0, 8)) : id.slice(0, 8); };
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); reload(); } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); } };
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

function CustomersTab({ cid, customers, taxCodes, reload }) {
  const [form, setForm] = useState({ name: "", default_currency: "CAD", default_tax_code: "" });
  const create = async () => {
    try { await api.arCreateCustomer(cid, form); toast.success("Client créé"); setForm({ name: "", default_currency: "CAD", default_tax_code: "" }); reload(); }
    catch (e) { toast.error(e.response?.data?.detail || "Erreur"); }
  };
  return (
    <div className="space-y-4" data-testid="ar-customers-tab">
      <div className="flex flex-wrap items-end gap-2 rounded-xl border border-slate-200 bg-white p-3">
        <div><label className="text-[11px] uppercase text-slate-500">Nom</label>
          <Input data-testid="cust-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-1 h-9 w-52" /></div>
        <div><label className="text-[11px] uppercase text-slate-500">Devise</label>
          <Input data-testid="cust-currency" value={form.default_currency} onChange={(e) => setForm({ ...form, default_currency: e.target.value.toUpperCase() })} className="mt-1 h-9 w-24" /></div>
        <div><label className="text-[11px] uppercase text-slate-500">Code taxe défaut</label>
          <select data-testid="cust-tax" value={form.default_tax_code} onChange={(e) => setForm({ ...form, default_tax_code: e.target.value })} className="mt-1 h-9 w-40 rounded-md border border-slate-200 px-2 text-sm">
            <option value="">—</option>{taxCodes.map((t) => <option key={t.code} value={t.code}>{t.code}</option>)}
          </select></div>
        <Button data-testid="cust-create" onClick={create} disabled={!form.name.trim()} className="h-9 gap-1 bg-[#063044] text-white"><Plus size={14}/> Créer</Button>
      </div>
      <div className="space-y-2">
        {customers.length === 0 && <p className="text-sm text-slate-400" data-testid="ar-customers-empty">Aucun client.</p>}
        {customers.map((c) => (
          <div key={c.id} data-testid={`cust-row-${c.id}`} className="flex items-center justify-between rounded-xl border border-slate-200 bg-white p-3">
            <div><span className="font-600 text-[#0F172A]">{c.name}</span> <span className="ml-2 text-xs text-slate-400">{c.default_currency} · {c.default_tax_code || "—"}</span></div>
            {c.credit_balance > 0 && <span className="text-xs font-600 text-teal-600" data-testid={`cust-credit-${c.id}`}>Crédit dispo : {money(c.credit_balance, c.default_currency)}</span>}
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
  const seed = async () => { try { const r = await api.arSeedTaxCodes(cid); toast.success(`Codes de taxe : ${r.created.length || "déjà présents"}`); reload(); } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); } };
  const saveMapping = async () => { try { await api.arSetMapping(cid, mapping); toast.success("Mapping enregistré"); } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); } };
  const recordFx = async () => { try { await api.arRecordFxRate(cid, { ...fx, rate: Number(fx.rate) }); toast.success("Taux enregistré"); setFx({ ...fx, rate: "" }); } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); } };
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

function InvoicesTab({ cid, customers, taxCodes, periods, invoices, reload }) {
  const [creating, setCreating] = useState(false);
  const emptyLine = { description: "", qty: 1, unit_price: "", tax_code: taxCodes[0]?.code || "EXEMPT" };
  const [form, setForm] = useState({ customer_id: "", period_id: "", currency: "", fx_rate: "", issue_date: "", lines: [{ ...emptyLine }] });

  const create = async () => {
    try {
      const body = { ...form, fx_rate: form.fx_rate ? Number(form.fx_rate) : undefined,
        lines: form.lines.map((l) => ({ ...l, qty: Number(l.qty || 1), unit_price: Number(l.unit_price || 0) })) };
      await api.arCreateInvoice(cid, body);
      toast.success("Facture créée"); setCreating(false);
      setForm({ customer_id: "", period_id: "", currency: "", fx_rate: "", issue_date: "", lines: [{ ...emptyLine }] });
      reload();
    } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); }
  };
  return (
    <div className="space-y-4" data-testid="ar-invoices-tab">
      <Button data-testid="inv-new" onClick={() => setCreating((v) => !v)} className="h-9 gap-1 bg-[#063044] text-white"><Plus size={14}/> Nouvelle facture</Button>
      {creating && (
        <div className="space-y-3 rounded-xl border border-slate-200 bg-white p-4" data-testid="inv-form">
          <div className="flex flex-wrap gap-3">
            <div><label className="text-[11px] uppercase text-slate-500">Client</label>
              <select data-testid="inv-customer" value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: e.target.value })} className="mt-1 h-9 w-52 rounded-md border border-slate-200 px-2 text-sm">
                <option value="">—</option>{customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div><label className="text-[11px] uppercase text-slate-500">Période</label>
              <select data-testid="inv-period" value={form.period_id} onChange={(e) => setForm({ ...form, period_id: e.target.value })} className="mt-1 h-9 w-36 rounded-md border border-slate-200 px-2 text-sm">
                <option value="">—</option>{periods.map((p) => <option key={p.id} value={p.id}>{p.code} ({p.status})</option>)}</select></div>
            <div><label className="text-[11px] uppercase text-slate-500">Devise</label><Input data-testid="inv-currency" value={form.currency} placeholder="défaut client" onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} className="mt-1 h-9 w-28"/></div>
            <div><label className="text-[11px] uppercase text-slate-500">Taux FX</label><Input data-testid="inv-fx" value={form.fx_rate} placeholder="auto" onChange={(e) => setForm({ ...form, fx_rate: e.target.value })} className="mt-1 h-9 w-24"/></div>
            <div><label className="text-[11px] uppercase text-slate-500">Date</label><Input data-testid="inv-date" type="date" value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} className="mt-1 h-9 w-40"/></div>
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
        {invoices.map((inv) => <InvoiceRow key={inv.id} cid={cid} inv={inv} reload={reload} />)}
      </div>
    </div>
  );
}

function InvoiceRow({ cid, inv, reload }) {
  const [payOpen, setPayOpen] = useState(false);
  const [cnOpen, setCnOpen] = useState(false);
  const [pay, setPay] = useState({ amount: "", fx_rate: "" });
  const [cn, setCn] = useState({ invoice_line_index: 0, net_credit: "" });
  const M = INV_STATUS[inv.status] || INV_STATUS.draft;
  const act = async (fn, msg) => { try { await fn(); toast.success(msg); reload(); } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); } };
  const doPay = async () => { try { await api.arCreatePayment(cid, { invoice_id: inv.id, amount: Number(pay.amount), fx_rate: pay.fx_rate ? Number(pay.fx_rate) : undefined }); toast.success("Encaissement enregistré"); setPayOpen(false); setPay({ amount: "", fx_rate: "" }); reload(); } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); } };
  const doCn = async () => { try { const c = await api.arCreateCreditNote(cid, { invoice_id: inv.id, lines: [{ invoice_line_index: Number(cn.invoice_line_index), net_credit: Number(cn.net_credit) }] }); await api.arSubmitCreditNote(cid, c.id); toast.success("Note de crédit créée & soumise (à approuver)"); setCnOpen(false); setCn({ invoice_line_index: 0, net_credit: "" }); reload(); } catch (e) { toast.error(e.response?.data?.detail || "Erreur"); } };
  return (
    <div data-testid={`inv-row-${inv.id}`} className="rounded-xl border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="font-mono-data text-sm font-600 text-[#0F172A]">{inv.number || inv.id.slice(0, 10)}</span>
          <span className={`rounded-full px-2 py-0.5 text-[11px] font-600 ${M.cls}`} data-testid={`inv-status-${inv.id}`}>{M.label}</span>
          <span className="text-sm text-slate-500">Total {money(inv.total, inv.currency)} · Solde {money(inv.balance, inv.currency)}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {inv.status === "draft" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-submit-${inv.id}`} onClick={() => act(() => api.arSubmitInvoice(cid, inv.id), "Soumise")}><Send size={13}/>Soumettre</Button>}
          {inv.status === "submitted" && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-approve-${inv.id}`} onClick={() => act(() => api.arApproveInvoice(cid, inv.id), "Approuvée")}><ThumbsUp size={13}/>Approuver</Button>}
          {inv.status === "approved" && <Button size="sm" className="h-8 gap-1 bg-emerald-600 text-white" data-testid={`inv-post-${inv.id}`} onClick={() => act(() => api.arPostInvoice(cid, inv.id), "Comptabilisée")}><Stamp size={13}/>Comptabiliser</Button>}
          {inv.status === "posted" && inv.amount_paid === 0 && <Button size="sm" variant="outline" className="h-8 gap-1 text-rose-600" data-testid={`inv-void-${inv.id}`} onClick={() => act(() => api.arVoidInvoice(cid, inv.id), "Extournée")}><RotateCcw size={13}/>Extourner</Button>}
          {["posted", "partially_paid"].includes(inv.status) && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-pay-${inv.id}`} onClick={() => setPayOpen((v) => !v)}><Banknote size={13}/>Encaisser</Button>}
          {["posted", "partially_paid", "paid"].includes(inv.status) && <Button size="sm" variant="outline" className="h-8 gap-1" data-testid={`inv-credit-${inv.id}`} onClick={() => setCnOpen((v) => !v)}><FileMinus size={13}/>Note de crédit</Button>}
        </div>
      </div>
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
