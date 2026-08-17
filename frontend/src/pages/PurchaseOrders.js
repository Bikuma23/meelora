import { useState, useEffect, useCallback } from "react";
import { useNav } from "../context/NavContext";
import { api } from "../lib/api";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Loader2, Plus, ClipboardCheck, ListChecks, LayoutDashboard } from "lucide-react";

const money = (v, c) => (v == null ? "—" : `${Number(v).toLocaleString("fr-CH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${c || ""}`.trim());
const errMsg = (e) => e?.response?.data?.detail || e?.message || "Erreur";
const PO_ST = {
  draft: { label: "Brouillon", cls: "bg-slate-100 text-slate-600" },
  submitted: { label: "Soumis", cls: "bg-indigo-100 text-indigo-700" },
  approved: { label: "Approuvé", cls: "bg-blue-100 text-blue-700" },
  sent: { label: "Envoyé", cls: "bg-emerald-100 text-emerald-700" },
  rejected: { label: "Rejeté", cls: "bg-rose-100 text-rose-600" },
  cancelled: { label: "Annulé", cls: "bg-rose-100 text-rose-600" },
  closed: { label: "Fermé", cls: "bg-slate-200 text-slate-600" },
};
const INV_ST = { not_invoiced: "Non facturé", partially_invoiced: "Partiellement facturé", fully_invoiced: "Entièrement facturé" };
const TABS = [
  { key: "overview", label: "Aperçu", icon: LayoutDashboard },
  { key: "approve", label: "À approuver", icon: ListChecks },
  { key: "all", label: "Bons de commande", icon: ClipboardCheck },
];

export default function PurchaseOrders() {
  const { activeCompanyId: cid } = useNav();
  const [tab, setTab] = useState("overview");
  return (
    <div className="mx-auto max-w-6xl" data-testid="po-page">
      <div className="mb-5 flex flex-wrap gap-1 border-b border-slate-200">
        {TABS.map((t) => (
          <button key={t.key} data-testid={`po-tab-${t.key}`} onClick={() => setTab(t.key)}
            className={`flex items-center gap-1.5 px-3 py-2.5 text-sm font-600 transition-colors ${tab === t.key ? "border-b-2 border-[#22C55E] text-[#0F172A]" : "text-slate-500 hover:text-[#0F172A]"}`}>
            <t.icon size={15} /> {t.label}
          </button>
        ))}
      </div>
      {tab === "overview" ? <Overview cid={cid} /> : <POList cid={cid} onlyApprove={tab === "approve"} />}
    </div>
  );
}

function Overview({ cid }) {
  const [pos, setPos] = useState([]);
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    if (!cid) return;
    setLoading(true);
    try {
      const [p, s] = await Promise.all([api.poList(cid, {}), api.apSettings(cid)]);
      setPos(p.purchase_orders || []); setSettings(s);
    } catch (e) { /* gated */ }
    setLoading(false);
  }, [cid]);
  useEffect(() => { load(); }, [load]);

  const toApprove = pos.filter((p) => p.po_status === "submitted");
  const partial = pos.filter((p) => p.invoicing_status === "partially_invoiced");
  const setTol = async (preset) => { try { const s = await api.apSetSettings(cid, { match_tolerance: { preset } }); setSettings(s); toast.success("Tolérance mise à jour"); } catch (e) { toast.error(errMsg(e)); } };
  const [adv, setAdv] = useState(false);

  if (loading) return <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-300" /></div>;
  const tol = settings?.match_tolerance || {};
  return (
    <div className="space-y-4" data-testid="po-overview">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-3" data-testid="po-kpi-approve"><p className="text-[11px] uppercase text-slate-500">À approuver</p><p className="mt-1 text-lg font-700 text-indigo-600">{toApprove.length}</p></div>
        <div className="rounded-xl border border-slate-200 bg-white p-3" data-testid="po-kpi-partial"><p className="text-[11px] uppercase text-slate-500">Partiellement facturés</p><p className="mt-1 text-lg font-700 text-amber-600">{partial.length}</p></div>
        <div className="rounded-xl border border-slate-200 bg-white p-3" data-testid="po-kpi-total"><p className="text-[11px] uppercase text-slate-500">Bons de commande</p><p className="mt-1 text-lg font-700 text-[#063044]">{pos.length}</p></div>
      </div>
      <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="po-tolerance">
        <p className="text-sm font-600 text-[#063044]">Tolérance de rapprochement</p>
        <div className="mt-2 flex gap-1 rounded-lg bg-slate-100 p-1 w-fit">
          {["strict", "standard", "custom"].map((p) => (
            <button key={p} data-testid={`po-tol-${p}`} onClick={() => setTol(p)}
              className={`rounded-md px-3 py-1.5 text-xs font-600 capitalize transition-colors ${tol.preset === p ? "bg-white text-[#063044] shadow-sm" : "text-slate-500"}`}>
              {p === "custom" ? "Personnalisé" : p}</button>
          ))}
        </div>
        <button onClick={() => setAdv((v) => !v)} className="mt-2 text-xs text-slate-400 underline" data-testid="po-tol-advanced-toggle">Options avancées</button>
        {adv && <p className="mt-1 text-xs text-slate-500" data-testid="po-tol-advanced">Écart absolu {tol.amount_abs} · % {tol.amount_pct} · prix % {tol.price_pct} · qté {tol.qty_abs} · v{tol.policy_version}</p>}
        <p className="mt-1 text-[11px] text-slate-400">Standard conservateur : CHF 1.00 d'écart absolu. Tout dépassement devient une exception.</p>
      </div>
    </div>
  );
}

function POList({ cid, onlyApprove }) {
  const [pos, setPos] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ supplier_id: "", currency: "CHF", lines: [{ description: "", qty: 1, unit_price: "" }] });

  const load = useCallback(async () => {
    if (!cid) return;
    setLoading(true);
    try {
      const [p, s] = await Promise.all([api.poList(cid, onlyApprove ? { po_status: "submitted" } : {}), api.apSuppliers(cid)]);
      setPos(p.purchase_orders || []); setSuppliers(s.suppliers || []);
    } catch (e) { /* gated */ }
    setLoading(false);
  }, [cid, onlyApprove]);
  useEffect(() => { load(); }, [load]);

  const supName = (id) => suppliers.find((s) => s.id === id)?.name || (id || "").slice(0, 8);
  const act = async (id, action, body, okMsg) => { try { await api.poAction(cid, id, action, body); toast.success(okMsg || "Fait"); load(); } catch (e) { toast.error(errMsg(e)); } };
  const addLine = () => setForm((f) => ({ ...f, lines: [...f.lines, { description: "", qty: 1, unit_price: "" }] }));
  const setLine = (i, k, v) => setForm((f) => ({ ...f, lines: f.lines.map((l, idx) => idx === i ? { ...l, [k]: v } : l) }));
  const create = async () => {
    try {
      await api.poCreate(cid, { supplier_id: form.supplier_id, currency: form.currency,
        lines: form.lines.map((l) => ({ description: l.description, qty: Number(l.qty || 0), unit_price: Number(l.unit_price || 0), tax_code: "EXEMPT" })) });
      toast.success("Bon de commande créé"); setOpen(false);
      setForm({ supplier_id: "", currency: "CHF", lines: [{ description: "", qty: 1, unit_price: "" }] }); load();
    } catch (e) { toast.error(errMsg(e)); }
  };

  return (
    <div className="space-y-4" data-testid={onlyApprove ? "po-approve-list" : "po-all-list"}>
      {!onlyApprove && <Button data-testid="po-new-toggle" onClick={() => setOpen((v) => !v)} className="h-9 gap-1 bg-[#063044] text-white"><Plus size={14} /> Nouveau bon de commande</Button>}
      {open && !onlyApprove && (
        <div className="rounded-xl border border-slate-200 bg-white p-4" data-testid="po-form">
          <div className="flex flex-wrap items-end gap-3">
            <div><label className="text-[11px] uppercase text-slate-500">Fournisseur</label>
              <select data-testid="po-form-supplier" value={form.supplier_id} onChange={(e) => setForm({ ...form, supplier_id: e.target.value })} className="mt-1 h-9 w-56 rounded-md border border-slate-200 px-2 text-sm">
                <option value="">—</option>{suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></div>
            <div><label className="text-[11px] uppercase text-slate-500">Devise</label><Input value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value.toUpperCase() })} className="mt-1 h-9 w-20" /></div>
          </div>
          <div className="mt-3 space-y-2">
            {form.lines.map((l, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2" data-testid={`po-form-line-${i}`}>
                <Input placeholder="Description" value={l.description} onChange={(e) => setLine(i, "description", e.target.value)} className="h-9 w-56" />
                <Input placeholder="Qté" value={l.qty} onChange={(e) => setLine(i, "qty", e.target.value)} className="h-9 w-20" />
                <Input placeholder="Prix unitaire" value={l.unit_price} onChange={(e) => setLine(i, "unit_price", e.target.value)} className="h-9 w-32" data-testid={`po-form-price-${i}`} />
              </div>
            ))}
            <button onClick={addLine} className="text-xs text-[#22C55E]" data-testid="po-form-addline">+ Ligne</button>
          </div>
          <div className="mt-4 border-t border-slate-100 pt-3">
            <Button data-testid="po-form-create" onClick={create} disabled={!form.supplier_id} className="h-9 gap-1 bg-[#22C55E] text-white"><Plus size={14} /> Créer</Button>
          </div>
        </div>
      )}
      {loading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-slate-300" /></div>
        : pos.length === 0 ? <p className="text-sm text-slate-400" data-testid="po-empty">Aucun bon de commande.</p>
        : pos.map((p) => {
          const st = PO_ST[p.po_status] || PO_ST.draft;
          return (
            <div key={p.id} data-testid={`po-row-${p.id}`} className="rounded-xl border border-slate-200 bg-white p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-mono-data text-xs text-slate-500">{p.number || "—"}</span>
                  <span className="font-600 text-[#0F172A]">{supName(p.supplier_id)}</span>
                  <span className="text-sm text-slate-500">{money(p.total, p.currency)}</span>
                  <span className={`rounded-full px-2 py-0.5 text-[11px] font-600 ${st.cls}`}>{st.label}</span>
                  {p.invoicing_status !== "not_invoiced" && <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-600 text-amber-700">{INV_ST[p.invoicing_status]} · reste {money(p.remaining_amount, p.currency)}</span>}
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  {p.po_status === "draft" && <Button size="sm" variant="outline" className="h-8" data-testid={`po-submit-${p.id}`} onClick={() => act(p.id, "submit", null, "Soumis")}>Soumettre</Button>}
                  {p.po_status === "submitted" && <>
                    <Button size="sm" className="h-8 bg-emerald-600 text-white" data-testid={`po-approve-${p.id}`} onClick={() => act(p.id, "approve", null, "Approuvé")}>Approuver</Button>
                    <Button size="sm" variant="outline" className="h-8 text-rose-600" data-testid={`po-reject-${p.id}`} onClick={() => act(p.id, "reject", { reason: "Rejeté" }, "Rejeté")}>Rejeter</Button>
                  </>}
                  {p.po_status === "approved" && <Button size="sm" variant="outline" className="h-8" data-testid={`po-send-${p.id}`} onClick={() => act(p.id, "send", null, "Envoyé")}>Envoyer</Button>}
                  {["approved", "sent"].includes(p.po_status) && !p.linked_invoice_ids?.length && <Button size="sm" variant="outline" className="h-8 text-rose-600" data-testid={`po-cancel-${p.id}`} onClick={() => act(p.id, "cancel", null, "Annulé")}>Annuler</Button>}
                  {["sent", "approved"].includes(p.po_status) && p.invoicing_status === "fully_invoiced" && <Button size="sm" variant="outline" className="h-8" data-testid={`po-close-${p.id}`} onClick={() => act(p.id, "close", null, "Fermé")}>Fermer</Button>}
                </div>
              </div>
              {p.linked_invoice_ids?.length > 0 && (
                <div className="mt-2 border-t border-slate-100 pt-2 text-xs text-slate-500" data-testid={`po-linked-${p.id}`}>
                  Facturé {money(p.invoiced_total, p.currency)} · {p.linked_invoice_ids.length} facture(s) liée(s)
                </div>
              )}
            </div>
          );
        })}
    </div>
  );
}
