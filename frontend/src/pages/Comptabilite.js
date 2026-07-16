import { useEffect, useState, useCallback } from "react";
import { api } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "../components/ui/dialog";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "../components/ui/alert-dialog";
import { toast } from "sonner";
import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer, CartesianGrid, Cell, LineChart, Line } from "recharts";
import {
  Upload, FileSpreadsheet, Lock, Unlock, CheckCircle2, AlertTriangle, Clock, FileText, Layers, Construction, Info, Plus, Minus, TrendingUp, TrendingDown, Wallet, Receipt, PiggyBank, BarChart3, Trash2, CalendarDays, Scale, ArrowRight, ExternalLink, Sparkles, Wand2,
} from "lucide-react";

const MONTHS = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];

function money(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  const abs = Math.abs(n).toLocaleString("fr-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${abs})` : abs;
}

function moneyM(v) {
  if (v == null || v === "") return "—";
  const n = Number(v) / 1e6;
  const abs = Math.abs(n).toLocaleString("fr-CA", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return n < 0 ? `(${abs})` : abs;
}

function usePeriods() {
  const [periods, setPeriods] = useState([]);
  const reload = useCallback(() => api.acctPeriods().then(setPeriods).catch(() => {}), []);
  useEffect(() => { reload(); }, [reload]);
  return { periods, reload };
}

function PeriodSelect({ periods, value, onChange, testId = "acct" }) {
  const years = [...new Set(periods.map((p) => p.year))].sort((a, b) => b - a);
  const [y, m] = value ? value.split("-").map(Number) : [null, null];
  const monthsForYear = periods.filter((p) => p.year === y).sort((a, b) => a.month - b.month);
  const setYear = (ny) => {
    ny = Number(ny);
    const monthsY = periods.filter((p) => p.year === ny).map((p) => p.month).sort((a, b) => a - b);
    const nm = monthsY.includes(m) ? m : monthsY[0];
    if (nm) onChange(`${ny}-${String(nm).padStart(2, "0")}`);
  };
  const setMonth = (nm) => onChange(`${y}-${String(Number(nm)).padStart(2, "0")}`);
  return (
    <div className="flex items-center gap-2">
      <CalendarDays size={15} className="text-[#063044]" />
      <Select value={y ? String(y) : ""} onValueChange={setYear}>
        <SelectTrigger data-testid={`${testId}-year-select`} className="w-24"><SelectValue placeholder="Année" /></SelectTrigger>
        <SelectContent>
          {years.length === 0 && <SelectItem value="none" disabled>—</SelectItem>}
          {years.map((yy) => <SelectItem key={yy} value={String(yy)} data-testid={`${testId}-year-opt-${yy}`}>{yy}</SelectItem>)}
        </SelectContent>
      </Select>
      <Select value={m ? String(m) : ""} onValueChange={setMonth}>
        <SelectTrigger data-testid={`${testId}-month-select`} className="w-40"><SelectValue placeholder="Mois" /></SelectTrigger>
        <SelectContent>
          {monthsForYear.length === 0 && <SelectItem value="none" disabled>—</SelectItem>}
          {monthsForYear.map((p) => (
            <SelectItem key={p.month} value={String(p.month)} data-testid={`${testId}-month-opt-${p.month}`}>
              {MONTHS[p.month - 1]} {p.locked ? "🔒" : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

// ---------- Dashboard ----------
function NoPeriodsState({ testId = "acct-no-periods" }) {
  return (
    <div className="card flex flex-col items-center gap-2 px-5 py-14 text-center" data-testid={testId}>
      <FileSpreadsheet size={30} className="text-slate-300" />
      <p className="text-sm font-700 text-slate-600">Aucune période disponible</p>
      <p className="max-w-md text-xs text-slate-400">Aucune balance de vérification n'est chargée. Rendez-vous dans « Balance de vérification » pour uploader une BV (.xlsx).</p>
    </div>
  );
}

function Sparkline({ data, color }) {
  const d = (data || []).map((v, i) => ({ i, v }));
  if (d.length < 2) return <div style={{ height: 36 }} className="mt-3" />;
  return (
    <div style={{ height: 36 }} className="mt-3" aria-hidden>
      <ResponsiveContainer width="100%" height={36}>
        <LineChart data={d} margin={{ top: 4, right: 2, left: 2, bottom: 0 }}>
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function KpiCard({ label, value, series, idx, positiveIsGood = true, icon: Icon, testid }) {
  const prev = idx > 0 ? series[idx - 1] : null;
  const cur = idx >= 0 ? series[idx] : (series.length ? series[series.length - 1] : value);
  const delta = prev != null && prev !== 0 ? ((cur - prev) / Math.abs(prev)) * 100 : null;
  const up = delta != null && delta >= 0;
  const good = delta == null ? true : (up === positiveIsGood);
  return (
    <div className="card card-hover relative overflow-hidden p-5 pl-6" data-testid={testid}>
      <span className="absolute left-0 top-0 h-full w-1 bg-[#15AF97]" />
      <div className="flex items-start justify-between">
        <span className="overline">{label}</span>
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#15AF97]/10 text-[#15AF97]"><Icon size={18} /></span>
      </div>
      <p className="font-display mt-3 text-3xl font-700 tracking-tight text-[#063044]">{money(value)}</p>
      <div className="mt-1 flex items-center gap-1.5 text-xs font-600" style={{ color: delta == null ? "#94A3B8" : (good ? "#10B981" : "#EF4444") }}>
        {delta != null && (up ? <TrendingUp size={14} /> : <TrendingDown size={14} />)}
        {delta != null ? `${up ? "+" : ""}${delta.toFixed(1)}% vs période préc.` : "Aucune donnée antérieure"}
      </div>
      <Sparkline data={series.slice(0, (idx >= 0 ? idx : series.length - 1) + 1)} color={good ? "#063044" : "#F8A942"} />
    </div>
  );
}

const acctGoto = (navKey, periodId) => {
  if (periodId) sessionStorage.setItem("acct_focus_period", periodId);
  window.dispatchEvent(new CustomEvent("acct-navigate", { detail: navKey }));
};
const fmtDays = (v) => v == null ? "—" : `${Number(v).toLocaleString("fr-CA", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} j`;

const fmtDelta = (v, unit) => {
  const sign = v > 0 ? "+" : v < 0 ? "−" : "";
  const abs = Math.abs(v);
  if (unit === "days") return `${sign}${abs.toLocaleString("fr-CA", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} j`;
  return `${sign}${abs.toLocaleString("fr-CA", { maximumFractionDigits: 0 })}`;
};
function TrendBadge({ trend, higherIsBetter, unit, testid }) {
  if (!trend) return null;
  const { delta, delta_pct } = trend;
  const flat = Math.abs(delta) < 1e-9;
  const up = delta > 0;
  const good = flat ? null : (higherIsBetter ? up : !up);
  const color = flat ? "bg-slate-100 text-slate-400" : good ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-600";
  const Icon = flat ? Minus : up ? TrendingUp : TrendingDown;
  return (
    <span data-testid={testid} className={`inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-700 ${color}`} title="vs mois précédent">
      <Icon size={11} /> {fmtDelta(delta, unit)}{delta_pct != null ? ` · ${delta > 0 ? "+" : delta < 0 ? "−" : ""}${Math.abs(delta_pct).toLocaleString("fr-CA", { maximumFractionDigits: 1 })} %` : ""}
    </span>
  );
}

function IndicatorCard({ title, caption, mainText, sub, unavailable, reason, provisional, icon: Icon, onClick, testid, trendNode }) {
  return (
    <button data-testid={testid} onClick={unavailable ? undefined : onClick} disabled={unavailable}
      className={`card group relative flex flex-col gap-2 p-5 text-left transition-shadow ${unavailable ? "cursor-default opacity-90" : "cursor-pointer hover:shadow-md"}`}>
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-700 uppercase tracking-wide text-slate-500">{title}</span>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#063044]/8 text-[#063044]"><Icon size={16} /></span>
      </div>
      {unavailable ? (
        <div className="flex items-start gap-1.5 py-1 text-xs text-amber-600" data-testid={`${testid}-unavailable`}>
          <AlertTriangle size={14} className="mt-0.5 shrink-0" /><span>{reason || "Indicateur non calculable"}</span>
        </div>
      ) : (
        <>
          <span className="font-mono-data text-2xl font-800 text-[#063044]" data-testid={`${testid}-value`}>{mainText}</span>
          {sub && <span className="font-mono-data text-xs font-600 text-slate-500">{sub}</span>}
          {trendNode}
        </>
      )}
      <span className="text-[11px] leading-snug text-slate-400">{caption}</span>
      {provisional && !unavailable && (
        <span className="inline-flex w-fit items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-700 text-amber-700"><AlertTriangle size={11} /> Provisoire</span>
      )}
      {!unavailable && <span className="text-[11px] font-600 text-[#0E9488] opacity-0 transition-opacity group-hover:opacity-100">Voir le détail →</span>}
    </button>
  );
}

const DRow = ({ label, value, strong, mono = true }) => (
  <div className={`flex items-center justify-between gap-4 py-1.5 ${strong ? "border-t border-slate-200 font-700" : ""}`}>
    <span className={`text-sm ${strong ? "text-slate-800" : "text-slate-500"}`}>{label}</span>
    <span className={`text-sm ${mono ? "font-mono-data" : ""} ${strong ? "text-[#063044]" : "text-slate-700"}`}>{value}</span>
  </div>
);

function SourceLinks({ periodId, links }) {
  return (
    <div className="flex flex-wrap gap-2 pt-2">
      {links.map(([key, label]) => (
        <Button key={key} size="sm" variant="outline" data-testid={`kpi-goto-${key}`} className="gap-1.5"
          onClick={() => acctGoto(key, periodId)}><ExternalLink size={13} /> {label}</Button>
      ))}
    </div>
  );
}

function KpiDetailDialog({ open, onOpenChange, type, kpi }) {
  if (!kpi) return null;
  const { dso, dpo, fdr, period, month_label, year } = kpi;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="kpi-detail-dialog" className="max-h-[90vh] max-w-lg overflow-y-auto">
        {type === "dso" && (
          <>
            <DialogHeader>
              <DialogTitle>DSO — Délai moyen de recouvrement</DialogTitle>
              <DialogDescription className="text-xs">{month_label} {year} · (Comptes clients courants nets de taxes, hors retenues ÷ Ventes des 12 derniers mois) × 365</DialogDescription>
            </DialogHeader>
            {!dso.available ? (
              <div className="flex items-start gap-2 rounded-lg border border-dashed border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" /><span>{dso.reason}</span>
              </div>
            ) : (
              <div className="rounded-lg bg-slate-50 px-4 py-1">
                <DRow label={dso.ar_label || "Comptes à recevoir"} value={money(dso.ar)} />
                <DRow label="− Retenues contractuelles exclues" value={money(dso.retenues)} />
                <DRow label="= Comptes clients courants" value={money(dso.ar_courant)} />
                <DRow label={`÷ ${dso.tax_factor} (net TPS+TVQ)`} value={money(dso.ar_courant_net)} />
                {dso.dispute > 0 && <DRow label={`− Montant en litige${dso.dispute_note ? ` (${dso.dispute_note})` : ""}`} value={money(dso.dispute)} />}
                <DRow label="Ventes (12 derniers mois réels)" value={money(dso.sales_12m)} />
                <DRow label="DSO = CC courants nets ÷ ventes 12 mois × 365" value={fmtDays(dso.value)} strong />
              </div>
            )}
            <SourceLinks periodId={period} links={[["acct_bilan", "Voir le Bilan"], ["acct_pnl", "Voir l'État des résultats"]]} />
          </>
        )}
        {type === "dpo" && (
          <>
            <DialogHeader>
              <DialogTitle>DPO — Délai moyen de paiement fournisseurs</DialogTitle>
              <DialogDescription className="text-xs">{month_label} {year} · (Comptes fournisseurs nets de taxes ÷ Achats des 12 derniers mois) × 365 · Achats = COGS 12 mois + variation d'inventaire sur 12 mois</DialogDescription>
            </DialogHeader>
            {!dpo.available ? (
              <div className="flex items-start gap-2 rounded-lg border border-dashed border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-700">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" /><span>{dpo.reason}</span>
              </div>
            ) : (
              <div className="rounded-lg bg-slate-50 px-4 py-1">
                <DRow label={dpo.ap_label || "Comptes fournisseurs"} value={money(dpo.ap)} />
                <DRow label={`÷ ${dpo.tax_factor} (net TPS+TVQ)`} value={money(dpo.ap_net)} />
                {dpo.dispute > 0 && <DRow label={`− Montant en litige${dpo.dispute_note ? ` (${dpo.dispute_note})` : ""}`} value={money(dpo.dispute)} />}
                <DRow label="COGS (12 derniers mois réels)" value={money(dpo.cogs_12m)} />
                <DRow label="− Main-d'œuvre incluse au COGS (12 mois)" value={money(dpo.labor_12m)} />
                <DRow label="= COGS hors main-d'œuvre" value={money(dpo.cogs_ex_labor_12m)} />
                <DRow label="Inventaire (fin de période)" value={money(dpo.inv_current)} />
                <DRow label={`Inventaire il y a 12 mois${dpo.inv_12m_period ? ` (${dpo.inv_12m_period})` : ""}`} value={money(dpo.inv_12m)} />
                <DRow label="Variation d'inventaire (12 mois)" value={money(dpo.inv_variation)} />
                <DRow label="Achats 12 mois = COGS hors M.O. + variation" value={money(dpo.purchases_12m)} />
                <DRow label="DPO = CF nets ÷ achats 12 mois × 365" value={fmtDays(dpo.value)} strong />
              </div>
            )}
            <SourceLinks periodId={period} links={[["acct_bilan", "Voir le Bilan"], ["acct_pnl", "Voir l'État des résultats"]]} />
          </>
        )}
        {type === "fdr" && (
          <>
            <DialogHeader>
              <DialogTitle>Fonds de roulement (FDR) & Besoin en fonds de roulement (BFR)</DialogTitle>
              <DialogDescription className="text-xs">{month_label} {year} · Retenues contractuelles exclues (garantie de construction, encaissables hors cycle court terme)</DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div>
                <p className="mb-1 text-[11px] font-700 uppercase tracking-wide text-[#063044]">Actif à court terme</p>
                <div className="rounded-lg bg-slate-50 px-3 py-1">
                  {(fdr.actif_ct || []).map((l, i) => <DRow key={i} label={l.label} value={money(l.value)} />)}
                  <DRow label="Total actif court terme" value={money(fdr.current_assets)} strong />
                </div>
              </div>
              <div>
                <p className="mb-1 text-[11px] font-700 uppercase tracking-wide text-[#063044]">Passif à court terme</p>
                <div className="rounded-lg bg-slate-50 px-3 py-1">
                  {(fdr.passif_ct || []).map((l, i) => <DRow key={i} label={l.label} value={money(l.value)} />)}
                  <DRow label="Total passif court terme" value={money(fdr.current_liabilities)} strong />
                </div>
              </div>
            </div>
            <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-1">
              <DRow label={`Retenues contractuelles exclues${fdr.retenues_label ? ` (${fdr.retenues_label})` : ""}`} value={money(fdr.retenues)} />
              {!fdr.retenues_found && <p className="py-1 text-[11px] text-amber-600">Aucun compte de retenues contractuelles identifié dans le mapping — exclusion nulle appliquée.</p>}
            </div>
            <div className="rounded-lg bg-[#063044]/5 px-4 py-1">
              <DRow label="Actif court terme (hors retenues)" value={money(fdr.current_assets_excl)} />
              <DRow label="FDR = Actif CT (hors retenues) − Passif CT" value={money(fdr.value)} strong />
              <DRow label="Ratio de fonds de roulement" value={fdr.ratio != null ? `${fdr.ratio}` : "—"} strong />
            </div>
            {fdr.bfr && fdr.bfr.available ? (
              <div className="rounded-lg bg-[#0E9488]/8 px-4 py-1">
                <p className="pt-1 text-[11px] font-700 uppercase tracking-wide text-[#0E9488]">Besoin en fonds de roulement (BFR)</p>
                <DRow label="Comptes clients courants (hors retenues)" value={money(fdr.bfr.ar_courant)} />
                <DRow label="+ Inventaire" value={money(fdr.bfr.inventory)} />
                <DRow label="− Comptes fournisseurs" value={money(fdr.bfr.ap)} />
                <DRow label="BFR = CC courants + Inventaire − CF" value={money(fdr.bfr.value)} strong />
              </div>
            ) : fdr.bfr && fdr.bfr.reason ? (
              <p className="rounded-lg border border-dashed border-amber-300 bg-amber-50 px-3 py-2 text-[11px] text-amber-700">BFR non calculable : {fdr.bfr.reason}</p>
            ) : null}
            <SourceLinks periodId={period} links={[["acct_bilan", "Voir le Bilan"]]} />
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DsoCard({ kpi, provisional, onOpen, onSaved }) {
  const dso = kpi.dso;
  const [amount, setAmount] = useState(String(dso.dispute || 0));
  const [note, setNote] = useState(dso.dispute_note || "");
  const [saving, setSaving] = useState(false);
  useEffect(() => { setAmount(String(dso.dispute || 0)); setNote(dso.dispute_note || ""); }, [kpi.period, dso.dispute, dso.dispute_note]);
  const dirty = String(parseFloat(amount) || 0) !== String(dso.dispute || 0) || (note || "") !== (dso.dispute_note || "");
  const save = async () => {
    setSaving(true);
    try {
      await api.acctKpiAdjust({ year: kpi.year, month: kpi.month }, { dso_dispute: parseFloat(amount) || 0, dso_dispute_note: note });
      toast.success("Montant en litige mis à jour");
      onSaved && onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Échec de l'enregistrement"); }
    finally { setSaving(false); }
  };
  return (
    <div className="card relative flex flex-col gap-2 p-5" data-testid="indicator-dso">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-700 uppercase tracking-wide text-slate-500">DSO — Recouvrement clients</span>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#063044]/8 text-[#063044]"><Clock size={16} /></span>
      </div>
      {!dso.available ? (
        <div className="flex items-start gap-1.5 py-1 text-xs text-amber-600" data-testid="indicator-dso-unavailable"><AlertTriangle size={14} className="mt-0.5 shrink-0" /><span>{dso.reason}</span></div>
      ) : (
        <>
          <span className="font-mono-data text-2xl font-800 text-[#063044]" data-testid="indicator-dso-value">{fmtDays(dso.value)}</span>
          <span className="font-mono-data text-xs font-600 text-slate-500">CC courants nets {money(dso.ar_courant_net)} · ventes 12m {money(dso.sales_12m)}</span>
          <TrendBadge testid="trend-dso" trend={kpi.trend?.dso} higherIsBetter={false} unit="days" />
        </>
      )}
      <span className="text-[11px] leading-snug text-slate-400">Délai moyen d'encaissement (jours) — base glissante 12 mois, net de taxes.</span>
      {provisional && dso.available && <span className="inline-flex w-fit items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-700 text-amber-700"><AlertTriangle size={11} /> Provisoire</span>}

      <div className="mt-1 rounded-lg border border-dashed border-slate-300 bg-slate-50/60 p-3">
        <label className="mb-1 block text-[11px] font-700 text-slate-600">Montant en litige (net de taxes)</label>
        <div className="flex items-center gap-2">
          <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="dso-dispute-input"
            className="h-8 w-40 font-mono-data text-sm" placeholder="0" onClick={(e) => e.stopPropagation()} />
          <Button size="sm" onClick={save} disabled={!dirty || saving} data-testid="dso-dispute-save" className="h-8 bg-[#063044] hover:bg-[#063044]/90">
            {saving ? "…" : "Enregistrer"}
          </Button>
          {parseFloat(amount) > 0 && (
            <Button size="sm" variant="ghost" data-testid="dso-dispute-reset" className="h-8 text-slate-500" onClick={() => { setAmount("0"); setNote(""); }}>Remettre à 0</Button>
          )}
        </div>
        <Input value={note} onChange={(e) => setNote(e.target.value)} data-testid="dso-dispute-note"
          className="mt-2 h-8 text-xs" placeholder="Note (ex. Litige client ABC depuis 2025)" onClick={(e) => e.stopPropagation()} />
        {dso.dispute > 0 && (
          <p className="mt-2 text-[11px] text-slate-500" data-testid="dso-dispute-active">
            Exclu du calcul : <span className="font-mono-data font-700 text-red-600">{money(dso.dispute)}</span>{dso.dispute_note ? ` — ${dso.dispute_note}` : ""}
            {dso.dispute_carried && <span className="ml-1 italic text-slate-400" data-testid="dso-dispute-carried">(reporté depuis {dso.dispute_source})</span>}
          </p>
        )}
      </div>

      {dso.available && <button onClick={onOpen} data-testid="indicator-dso-detail" className="w-fit text-[11px] font-600 text-[#0E9488] hover:underline">Voir le détail →</button>}
    </div>
  );
}

function DpoCard({ kpi, provisional, onOpen, onSaved }) {
  const dpo = kpi.dpo;
  const [amount, setAmount] = useState(String(dpo.dispute || 0));
  const [note, setNote] = useState(dpo.dispute_note || "");
  const [saving, setSaving] = useState(false);
  useEffect(() => { setAmount(String(dpo.dispute || 0)); setNote(dpo.dispute_note || ""); }, [kpi.period, dpo.dispute, dpo.dispute_note]);
  const dirty = String(parseFloat(amount) || 0) !== String(dpo.dispute || 0) || (note || "") !== (dpo.dispute_note || "");
  const save = async () => {
    setSaving(true);
    try {
      await api.acctKpiAdjust({ year: kpi.year, month: kpi.month }, { dpo_dispute: parseFloat(amount) || 0, dpo_dispute_note: note });
      toast.success("Montant en litige mis à jour");
      onSaved && onSaved();
    } catch (e) { toast.error(e.response?.data?.detail || "Échec de l'enregistrement"); }
    finally { setSaving(false); }
  };
  return (
    <div className="card relative flex flex-col gap-2 p-5" data-testid="indicator-dpo">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-700 uppercase tracking-wide text-slate-500">DPO — Paiement fournisseurs</span>
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#063044]/8 text-[#063044]"><Clock size={16} /></span>
      </div>
      {!dpo.available ? (
        <div className="flex items-start gap-1.5 py-1 text-xs text-amber-600" data-testid="indicator-dpo-unavailable"><AlertTriangle size={14} className="mt-0.5 shrink-0" /><span>{dpo.reason}</span></div>
      ) : (
        <>
          <span className="font-mono-data text-2xl font-800 text-[#063044]" data-testid="indicator-dpo-value">{fmtDays(dpo.value)}</span>
          <span className="font-mono-data text-xs font-600 text-slate-500">CF nets {money(dpo.ap_net)} · achats 12m {money(dpo.purchases_12m)}</span>
          <TrendBadge testid="trend-dpo" trend={kpi.trend?.dpo} higherIsBetter={true} unit="days" />
        </>
      )}
      <span className="text-[11px] leading-snug text-slate-400">Délai moyen de paiement (jours) — base glissante 12 mois, net de taxes, hors main-d'œuvre du COGS.</span>
      {provisional && dpo.available && <span className="inline-flex w-fit items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-700 text-amber-700"><AlertTriangle size={11} /> Provisoire</span>}

      <div className="mt-1 rounded-lg border border-dashed border-slate-300 bg-slate-50/60 p-3">
        <label className="mb-1 block text-[11px] font-700 text-slate-600">Montant en litige (net de taxes)</label>
        <div className="flex items-center gap-2">
          <Input type="number" value={amount} onChange={(e) => setAmount(e.target.value)} data-testid="dpo-dispute-input"
            className="h-8 w-40 font-mono-data text-sm" placeholder="0" />
          <Button size="sm" onClick={save} disabled={!dirty || saving} data-testid="dpo-dispute-save" className="h-8 bg-[#063044] hover:bg-[#063044]/90">{saving ? "…" : "Enregistrer"}</Button>
          {parseFloat(amount) > 0 && (
            <Button size="sm" variant="ghost" data-testid="dpo-dispute-reset" className="h-8 text-slate-500" onClick={() => { setAmount("0"); setNote(""); }}>Remettre à 0</Button>
          )}
        </div>
        <Input value={note} onChange={(e) => setNote(e.target.value)} data-testid="dpo-dispute-note"
          className="mt-2 h-8 text-xs" placeholder="Note (ex. Facture fournisseur contestée)" />
        {dpo.dispute > 0 && (
          <p className="mt-2 text-[11px] text-slate-500" data-testid="dpo-dispute-active">
            Exclu du calcul : <span className="font-mono-data font-700 text-red-600">{money(dpo.dispute)}</span>{dpo.dispute_note ? ` — ${dpo.dispute_note}` : ""}
            {dpo.dispute_carried && <span className="ml-1 italic text-slate-400" data-testid="dpo-dispute-carried">(reporté depuis {dpo.dispute_source})</span>}
          </p>
        )}
      </div>

      {dpo.available && <button onClick={onOpen} data-testid="indicator-dpo-detail" className="w-fit text-[11px] font-600 text-[#0E9488] hover:underline">Voir le détail →</button>}
    </div>
  );
}

function TaxSettingsDialog({ open, onOpenChange, current, onSaved }) {
  const [val, setVal] = useState(String(current ?? 1.14975));
  const [saving, setSaving] = useState(false);
  useEffect(() => { setVal(String(current ?? 1.14975)); }, [current, open]);
  const save = async () => {
    setSaving(true);
    try {
      await api.acctSaveSettings({ tax_factor: parseFloat(val) });
      toast.success("Taux de taxe enregistré");
      onSaved && onSaved(); onOpenChange(false);
    } catch (e) { toast.error(e.response?.data?.detail || "Échec"); }
    finally { setSaving(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="tax-settings-dialog" className="max-w-md">
        <DialogHeader>
          <DialogTitle>Taux de taxe combiné (DSO / DPO)</DialogTitle>
          <DialogDescription className="text-xs">Facteur diviseur appliqué aux soldes clients/fournisseurs pour les ramener hors taxes. Standard Québec : 1,14975 (TPS 5% + TVQ 9,975%).</DialogDescription>
        </DialogHeader>
        <div className="flex items-center gap-2">
          <Input type="number" step="0.00001" value={val} onChange={(e) => setVal(e.target.value)} data-testid="tax-factor-input" className="h-9 w-40 font-mono-data" />
          <Button onClick={save} disabled={saving || !(parseFloat(val) > 0)} data-testid="tax-factor-save" className="bg-[#063044] hover:bg-[#063044]/90">Enregistrer</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ProjChart({ title, data, color, note, onOpen, testid }) {
  return (
    <div className="card p-5" data-testid={testid}>
      <div className="mb-1 flex items-center justify-between gap-2">
        <h3 className="text-sm font-700">{title}</h3>
        <button onClick={onOpen} data-testid={`${testid}-detail`} className="inline-flex items-center gap-1 rounded-full bg-[#F8A942]/15 px-2 py-0.5 text-[10px] font-700 uppercase tracking-wide text-[#B45309] hover:bg-[#F8A942]/25">Projection · détail</button>
      </div>
      <p className="mb-3 text-xs text-slate-400">{note}</p>
      <div style={{ width: "100%", height: 250 }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 10, right: 20, left: 10, bottom: 0 }} onClick={onOpen}>
            <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={1} />
            <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toLocaleString("fr-CA")} k`} width={64} />
            <Tooltip formatter={(v) => money(v)} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="reel" name="Réel" stroke={color} strokeWidth={2.2} dot={{ r: 2 }} connectNulls />
            <Line type="monotone" dataKey="projete" name="Projeté" stroke={color} strokeWidth={2} strokeDasharray="5 4" dot={{ r: 2 }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function ProjectionDetailDialog({ open, onOpenChange, series, proj }) {
  if (!proj || !series) return null;
  const keyMap = { cash: "cash", sales: "sales", charges: "charges", cogs: "cogs" };
  const k = keyMap[series.key];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="projection-detail-dialog" className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{series.title} — base de la projection</DialogTitle>
          <DialogDescription className="text-xs">
            Valeurs réelles (mois verrouillés) utilisées pour la régression linéaire.
            {series.key === "cash" && ` Trésorerie décalée du DSO (${proj.lag_in_months} mois d'encaissement) et du DPO (${proj.lag_out_months} mois de paiement).`}
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-lg bg-slate-50 px-3 py-1">
          {(proj.base || []).map((b, i) => (
            <div key={i} className="flex items-center justify-between gap-3 border-b border-slate-100 py-1.5 last:border-0">
              <span className="text-sm text-slate-600">{b.month_label} {b.year}</span>
              <span className="font-mono-data text-sm text-slate-800">{money(b[k])}</span>
              <button data-testid={`proj-goto-${b.year}-${b.month}`} onClick={() => acctGoto(series.key === "cash" ? "acct_bilan" : "acct_pnl", `${b.year}-${String(b.month).padStart(2, "0")}`)}
                className="inline-flex items-center gap-1 text-[11px] font-600 text-[#0E9488] hover:underline">source <ArrowRight size={12} /></button>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-slate-400">Projection statistique (tendance) — ce n'est pas un budget saisi manuellement.</p>
      </DialogContent>
    </Dialog>
  );
}

function AiConfigDialog({ open, onOpenChange }) {
  const [cfg, setCfg] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { if (open) api.acctAiGetConfig().then(setCfg).catch(() => {}); }, [open]);
  const set = (k, v) => setCfg((c) => ({ ...c, [k]: v }));
  const save = async () => {
    setSaving(true);
    try {
      const body = { enabled: cfg.enabled, provider: cfg.provider, model: cfg.model,
        azure_endpoint: cfg.azure_endpoint, azure_deployment: cfg.azure_deployment, azure_api_version: cfg.azure_api_version,
        variance_threshold_amount: Number(cfg.variance_threshold_amount), variance_threshold_pct: Number(cfg.variance_threshold_pct),
        anomaly_sensitivity: Number(cfg.anomaly_sensitivity) };
      if (cfg._openai_key) body.openai_api_key = cfg._openai_key;
      if (cfg._azure_key) body.azure_api_key = cfg._azure_key;
      const r = await api.acctAiSaveConfig(body);
      setCfg({ ...r, _openai_key: "", _azure_key: "" });
      toast.success(r.configured ? "IA configurée et activée" : "Configuration enregistrée (non active — vérifiez les identifiants)");
    } catch (e) { toast.error(e.response?.data?.detail || "Échec"); }
    finally { setSaving(false); }
  };
  const clearKeys = async () => { const r = await api.acctAiClearKeys(); setCfg({ ...r, _openai_key: "", _azure_key: "" }); toast.success("Clés effacées — IA désactivée"); };
  if (!cfg) return null;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="ai-config-dialog" className="max-h-[90vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Configuration de l'assistant IA</DialogTitle>
          <DialogDescription className="text-xs">Les identifiants restent côté serveur. Retirez la clé pour revenir au comportement sans IA. {cfg.configured ? "✅ Actif" : "⚠️ Inactif"}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" data-testid="ai-enabled" checked={!!cfg.enabled} onChange={(e) => set("enabled", e.target.checked)} /> Activer les fonctionnalités IA</label>
          <div>
            <label className="mb-1 block text-[11px] font-700 text-slate-600">Fournisseur</label>
            <select data-testid="ai-provider" value={cfg.provider} onChange={(e) => set("provider", e.target.value)} className="h-9 w-full rounded-md border border-slate-300 px-2 text-sm">
              <option value="emergent">Clé universelle Emergent (aucune clé requise)</option>
              <option value="openai">OpenAI (clé API)</option>
              <option value="azure">Azure OpenAI Service</option>
            </select>
          </div>
          {cfg.provider !== "azure" && (
            <div>
              <label className="mb-1 block text-[11px] font-700 text-slate-600">Modèle</label>
              <Input data-testid="ai-model" value={cfg.model || ""} onChange={(e) => set("model", e.target.value)} className="h-9" placeholder="gpt-4o" />
            </div>
          )}
          {cfg.provider === "openai" && (
            <div>
              <label className="mb-1 block text-[11px] font-700 text-slate-600">Clé API OpenAI {cfg.has_openai_key && "(déjà enregistrée)"}</label>
              <Input data-testid="ai-openai-key" type="password" value={cfg._openai_key || ""} onChange={(e) => set("_openai_key", e.target.value)} className="h-9" placeholder={cfg.has_openai_key ? "•••••• (laisser vide pour conserver)" : "sk-..."} />
            </div>
          )}
          {cfg.provider === "azure" && (
            <>
              <div><label className="mb-1 block text-[11px] font-700 text-slate-600">Endpoint Azure</label><Input data-testid="ai-azure-endpoint" value={cfg.azure_endpoint || ""} onChange={(e) => set("azure_endpoint", e.target.value)} className="h-9" placeholder="https://xxx.openai.azure.com" /></div>
              <div><label className="mb-1 block text-[11px] font-700 text-slate-600">Nom du déploiement</label><Input data-testid="ai-azure-deployment" value={cfg.azure_deployment || ""} onChange={(e) => set("azure_deployment", e.target.value)} className="h-9" placeholder="mon-deploiement-gpt4o" /></div>
              <div><label className="mb-1 block text-[11px] font-700 text-slate-600">Version API</label><Input value={cfg.azure_api_version || ""} onChange={(e) => set("azure_api_version", e.target.value)} className="h-9" placeholder="2024-08-01-preview" /></div>
              <div><label className="mb-1 block text-[11px] font-700 text-slate-600">Clé API Azure {cfg.has_azure_key && "(déjà enregistrée)"}</label><Input data-testid="ai-azure-key" type="password" value={cfg._azure_key || ""} onChange={(e) => set("_azure_key", e.target.value)} className="h-9" placeholder={cfg.has_azure_key ? "•••••• (laisser vide pour conserver)" : "clé"} /></div>
            </>
          )}
          <div className="grid grid-cols-3 gap-2 border-t border-slate-200 pt-3">
            <div><label className="mb-1 block text-[10px] font-700 text-slate-500">Seuil écart ($)</label><Input type="number" value={cfg.variance_threshold_amount} onChange={(e) => set("variance_threshold_amount", e.target.value)} className="h-8" /></div>
            <div><label className="mb-1 block text-[10px] font-700 text-slate-500">Seuil écart (%)</label><Input type="number" value={cfg.variance_threshold_pct} onChange={(e) => set("variance_threshold_pct", e.target.value)} className="h-8" /></div>
            <div><label className="mb-1 block text-[10px] font-700 text-slate-500">Sensibilité anomalies (z)</label><Input type="number" step="0.1" value={cfg.anomaly_sensitivity} onChange={(e) => set("anomaly_sensitivity", e.target.value)} className="h-8" /></div>
          </div>
        </div>
        <DialogFooter className="gap-2">
          {(cfg.has_openai_key || cfg.has_azure_key) && <Button variant="outline" data-testid="ai-clear-keys" onClick={clearKeys} className="text-red-600">Effacer les clés</Button>}
          <Button data-testid="ai-config-save" onClick={save} disabled={saving} className="bg-[#063044] hover:bg-[#063044]/90">{saving ? "…" : "Enregistrer"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function VarianceCard({ year, month }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const gen = async () => {
    setLoading(true);
    try { setData(await api.acctAiVariance({ year, month })); }
    catch (e) { toast.error(e.response?.data?.detail || "Erreur IA"); }
    finally { setLoading(false); }
  };
  return (
    <div className="card p-5" data-testid="ai-variance-card">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-700 text-slate-700"><FileText size={15} className="text-[#0E9488]" /> Analyse de variance (IA)</h3>
        <Button size="sm" onClick={gen} disabled={loading} data-testid="ai-variance-btn" className="bg-[#063044] hover:bg-[#063044]/90">{loading ? "Analyse…" : "Générer"}</Button>
      </div>
      {!data ? <p className="text-xs text-slate-400">Générez un commentaire des écarts réel vs budget les plus significatifs de la période.</p>
        : data.available === false ? <p className="text-xs text-amber-600" data-testid="ai-variance-unavailable">{data.reason || "Fonctionnalité IA non configurée."}</p>
        : data.empty ? <p className="text-xs text-slate-500">Aucun écart au-delà des seuils configurés pour cette période.</p>
        : <p className="whitespace-pre-line text-sm leading-relaxed text-slate-700" data-testid="ai-variance-text">{data.commentary}</p>}
    </div>
  );
}

function AiChatPanel({ year, month }) {
  const [msgs, setMsgs] = useState([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [sid] = useState(() => `chat-${Date.now()}`);
  const ask = async () => {
    if (!q.trim()) return;
    const question = q.trim(); setQ(""); setMsgs((m) => [...m, { role: "user", text: question }]); setLoading(true);
    try {
      const r = await api.acctAiChat({ session_id: sid, question, year, month });
      setMsgs((m) => [...m, { role: "ai", text: r.available === false ? (r.reason || "Fonctionnalité IA non configurée.") : r.answer }]);
    } catch (e) { setMsgs((m) => [...m, { role: "ai", text: e.response?.data?.detail || "Erreur IA" }]); }
    finally { setLoading(false); }
  };
  return (
    <div className="card flex flex-col p-5" data-testid="ai-chat-card">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-700 text-slate-700"><Info size={15} className="text-[#0E9488]" /> Questions sur les données (IA)</h3>
      <div className="mb-3 max-h-64 min-h-[80px] space-y-2 overflow-y-auto rounded-lg bg-slate-50 p-3" data-testid="ai-chat-messages">
        {msgs.length === 0 && <p className="text-xs text-slate-400">Ex. « Quelle a été l'évolution des charges sur les 6 derniers mois ? »</p>}
        {msgs.map((m, i) => (
          <div key={i} className={`text-sm ${m.role === "user" ? "text-right" : ""}`}>
            <span className={`inline-block rounded-lg px-3 py-1.5 ${m.role === "user" ? "bg-[#063044] text-white" : "bg-white text-slate-700 shadow-sm"}`}>{m.text}</span>
          </div>
        ))}
        {loading && <p className="text-xs text-slate-400">L'assistant réfléchit…</p>}
      </div>
      <div className="flex gap-2">
        <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()} data-testid="ai-chat-input" className="h-9" placeholder="Poser une question…" />
        <Button onClick={ask} disabled={loading} data-testid="ai-chat-send" className="h-9 bg-[#063044] hover:bg-[#063044]/90">Envoyer</Button>
      </div>
    </div>
  );
}

export function AcctDashboard() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [d, setD] = useState(null);
  const { periods } = usePeriods();
  const [period, setPeriod] = useState("");
  const [summary, setSummary] = useState(null);
  const [trend, setTrend] = useState([]);
  const [kpi, setKpi] = useState(null);
  const [kpiDialog, setKpiDialog] = useState({ open: false, type: null });
  const [proj, setProj] = useState(null);
  const [projDialog, setProjDialog] = useState({ open: false, series: null });
  const [taxDialog, setTaxDialog] = useState(false);
  const [aiDialog, setAiDialog] = useState(false);
  const [taxFactor, setTaxFactor] = useState(1.14975);
  useEffect(() => { api.acctDashboard().then(setD).catch(() => {}); api.acctTrend().then(setTrend).catch(() => {}); api.acctProjections().then(setProj).catch(() => {}); api.acctSettings().then((s) => setTaxFactor(s.tax_factor)).catch(() => {}); }, []);
  useEffect(() => { if (periods.length && !periods.some((p) => p.id === period)) setPeriod(periods[0].id); }, [periods, period]);
  const reloadKpi = useCallback(() => {
    if (!period) return;
    const [y, m] = period.split("-").map(Number);
    api.acctKpis({ year: y, month: m }).then(setKpi).catch(() => setKpi(null));
    api.acctProjections().then(setProj).catch(() => {});
  }, [period]);
  useEffect(() => {
    if (!period) { setSummary(null); setKpi(null); return; }
    const [y, m] = period.split("-").map(Number);
    api.acctSummary({ year: y, month: m }).then(setSummary).catch(() => setSummary(null));
    api.acctKpis({ year: y, month: m }).then(setKpi).catch(() => setKpi(null));
  }, [period]);
  if (!d) return <p className="text-sm text-slate-500">Chargement…</p>;
  const sel = periods.find((p) => p.id === period);
  const newCount = Array.isArray(sel?.new_accounts) ? sel.new_accounts.length : (sel?.new_accounts ?? 0);
  const chartData = summary?.categories?.map((c) => ({
    name: c.label, "Réel": c.values.reel, "Budget CA": c.values.bud_ca, "Budget Rév-1": c.values.bud_rev1,
  })) || [];
  const trendData = trend.map((t) => ({
    name: `${t.month_label.slice(0, 3)} ${t.year}`, "Bénéfice net (mois)": t.benefice_mois, "Bénéfice net (cumulatif)": t.benefice_cumulatif,
  }));
  const selIdx = trend.findIndex((t) => t.period === period);
  const idx = selIdx >= 0 ? selIdx : trend.length - 1;
  const cur = idx >= 0 ? trend[idx] : null;
  const revSeries = trend.map((t) => t.revenus_cumulatif ?? 0);
  const cogsSeries = trend.map((t) => t.cogs_cumulatif ?? 0);
  const baiiaSeries = trend.map((t) => t.baiia_cumulatif ?? 0);
  const benSeries = trend.map((t) => t.benefice_cumulatif ?? 0);
  const projChart = (key) => {
    if (!proj || proj.insufficient) return [];
    const short = (y, m) => `${MONTHS[m - 1].slice(0, 3)} ${String(y).slice(2)}`;
    const base = (proj.base || []).map((b) => ({ name: short(b.year, b.month), reel: b[key], projete: null }));
    const proje = (proj.projection || []).map((p) => ({ name: short(p.year, p.month), reel: null, projete: p[key] }));
    if (base.length) base[base.length - 1].projete = proj.base[proj.base.length - 1][key];
    return [...base, ...proje];
  };
  const projSeries = [
    { key: "cash", title: "Trésorerie (encaisse)", color: "#0E9488", testid: "proj-cash", note: `Solde d'encaisse projeté en tenant compte du DSO (${proj?.lag_in_months ?? "—"} mois) et du DPO (${proj?.lag_out_months ?? "—"} mois).` },
    { key: "sales", title: "Ventes", color: "#063044", testid: "proj-sales", note: "Ventes mensuelles réelles puis projetées (tendance)." },
    { key: "charges", title: "Frais (hors COGS)", color: "#F8A942", testid: "proj-charges", note: "Total des charges d'exploitation, hors coût des marchandises vendues." },
    { key: "cogs", title: "COGS (coût des marchandises vendues)", color: "#808080", testid: "proj-cogs", note: "Coût des marchandises vendues, mensuel." },
  ];
  const openKpi = (type) => setKpiDialog({ open: true, type });
  return (
    <div className="space-y-6" data-testid="acct-dashboard">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-sm font-600 text-slate-500">Période affichée :</span>
          <PeriodSelect periods={periods} value={period} onChange={setPeriod} testId="acct-dash" />
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <span className="inline-flex items-center gap-1.5"><FileSpreadsheet size={13} /> {d.template_imported ? `${d.template_accounts} comptes` : "Modèle non importé"}</span>
          <span className="inline-flex items-center gap-1.5"><Layers size={13} /> {d.period_count} périodes</span>
          {isAdmin && (
            <button onClick={() => setAiDialog(true)} data-testid="ai-config-btn" title="Configuration de l'assistant IA"
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 px-2.5 py-1 font-600 text-slate-500 hover:bg-slate-50">
              <Sparkles size={13} className="text-[#0E9488]" /> Assistant IA
            </button>
          )}
        </div>
      </div>

      {cur && (
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4" data-testid="acct-kpi-grid">
          <KpiCard label="Revenus (cumulatif)" value={cur.revenus_cumulatif} series={revSeries} idx={idx} positiveIsGood icon={Wallet} testid="kpi-revenus" />
          <KpiCard label="COGS (cumulatif)" value={cur.cogs_cumulatif} series={cogsSeries} idx={idx} positiveIsGood={false} icon={Receipt} testid="kpi-cogs" />
          <KpiCard label="BAIIA (cumulatif)" value={cur.baiia_cumulatif} series={baiiaSeries} idx={idx} positiveIsGood icon={BarChart3} testid="kpi-baiia" />
          <KpiCard label="Bénéfice net (cumulatif)" value={cur.benefice_cumulatif} series={benSeries} idx={idx} positiveIsGood icon={PiggyBank} testid="kpi-benefice" />
        </div>
      )}

      {kpi && (
        <div className="space-y-2" data-testid="acct-indicators">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-700 text-slate-700">Indicateurs — {kpi.month_label} {kpi.year}</h3>
            <div className="flex items-center gap-2">
              <button onClick={() => setTaxDialog(true)} data-testid="tax-settings-btn" className="inline-flex items-center gap-1 rounded-full border border-slate-200 px-2.5 py-1 text-[11px] font-600 text-slate-500 hover:bg-slate-50" title="Taux de taxe DSO/DPO">
                <Scale size={12} /> Taxe {taxFactor}
              </button>
              {!kpi.locked && (
                <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-xs font-600 text-amber-700" data-testid="kpi-provisional-banner">
                  <AlertTriangle size={13} /> Données provisoires — mois non verrouillé
                </span>
              )}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <DsoCard kpi={kpi} provisional={!kpi.locked} onOpen={() => openKpi("dso")} onSaved={reloadKpi} />
            <DpoCard kpi={kpi} provisional={!kpi.locked} onOpen={() => openKpi("dpo")} onSaved={reloadKpi} />
            <button data-testid="indicator-fdr" onClick={kpi.fdr.available ? () => openKpi("fdr") : undefined} disabled={!kpi.fdr.available}
              className={`card group relative flex flex-col gap-2 p-5 text-left transition-shadow sm:col-span-2 xl:col-span-1 ${kpi.fdr.available ? "cursor-pointer hover:shadow-md" : "cursor-default opacity-90"}`}>
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-700 uppercase tracking-wide text-slate-500">Fonds de roulement / BFR</span>
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#063044]/8 text-[#063044]"><Scale size={16} /></span>
              </div>
              {!kpi.fdr.available ? (
                <div className="flex items-start gap-1.5 py-1 text-xs text-amber-600" data-testid="indicator-fdr-unavailable"><AlertTriangle size={14} className="mt-0.5 shrink-0" /><span>{kpi.fdr.reason}</span></div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-[10px] font-700 uppercase tracking-wide text-slate-400">FDR</span>
                    <p className="font-mono-data text-xl font-800 text-[#063044]" data-testid="indicator-fdr-value">{money(kpi.fdr.value)}</p>
                    <span className="font-mono-data text-[11px] font-600 text-slate-500">Ratio {kpi.fdr.ratio ?? "—"}</span>
                    <div className="mt-1"><TrendBadge testid="trend-fdr" trend={kpi.trend?.fdr} higherIsBetter={true} unit="money" /></div>
                  </div>
                  <div>
                    <span className="text-[10px] font-700 uppercase tracking-wide text-slate-400">BFR</span>
                    <p className="font-mono-data text-xl font-800 text-[#0E9488]" data-testid="indicator-bfr-value">{kpi.fdr.bfr?.available ? money(kpi.fdr.bfr.value) : "—"}</p>
                    <span className="font-mono-data text-[11px] font-600 text-slate-500">Cycle opérationnel</span>
                    {kpi.fdr.bfr?.available && <div className="mt-1"><TrendBadge testid="trend-bfr" trend={kpi.trend?.bfr} higherIsBetter={false} unit="money" /></div>}
                  </div>
                </div>
              )}
              <span className="text-[11px] leading-snug text-slate-400">Retenues contractuelles exclues : <span className="font-mono-data text-slate-500">{money(kpi.fdr.retenues)}</span></span>
              {!kpi.locked && kpi.fdr.available && <span className="inline-flex w-fit items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-700 text-amber-700"><AlertTriangle size={11} /> Provisoire</span>}
              {kpi.fdr.available && <span className="text-[11px] font-600 text-[#0E9488] opacity-0 transition-opacity group-hover:opacity-100">Voir le détail →</span>}
            </button>
          </div>
        </div>
      )}

      {proj && !proj.insufficient && (
        <div className="space-y-2" data-testid="acct-projections">
          <div className="flex items-center gap-2">
            <TrendingUp size={16} className="text-[#0E9488]" />
            <h3 className="text-sm font-700 text-slate-700">Projection 12 mois</h3>
            <span className="inline-flex items-center gap-1 rounded-full bg-[#F8A942]/15 px-2 py-0.5 text-[10px] font-700 uppercase tracking-wide text-[#B45309]">Projection statistique</span>
          </div>
          <p className="text-xs text-slate-400">Tendance des {proj.n_base} derniers mois verrouillés (régression linéaire) — trait plein = réel, pointillé = projeté. Ce n'est pas un budget saisi manuellement.</p>
          <div className="grid gap-4 lg:grid-cols-2">
            {projSeries.map((s) => (
              <ProjChart key={s.key} testid={s.testid} title={s.title} color={s.color} note={s.note}
                data={projChart(s.key)} onOpen={() => setProjDialog({ open: true, series: s })} />
            ))}
          </div>
        </div>
      )}

      {sel ? (
        <div className="card p-5" data-testid="acct-dashboard-latest">
          <h3 className="mb-4 text-sm font-700">Statut — {MONTHS[sel.month - 1]} {sel.year}</h3>
          <div className="grid gap-4 sm:grid-cols-3">
            <div className={`rounded-xl border p-4 ${sel.locked ? "border-red-200 bg-red-50" : "border-amber-200 bg-amber-50"}`}>
              <div className="flex items-center gap-2">{sel.locked ? <Lock size={16} className="text-red-600" /> : <Unlock size={16} className="text-amber-600" />}
                <span className="text-sm font-700">{sel.locked ? "Verrouillé" : "Non verrouillé"}</span></div>
              <p className="mt-1 text-xs text-slate-500">{sel.locked ? "Données finales" : "Données provisoires"}</p>
            </div>
            <div className={`rounded-xl border p-4 ${sel.balanced ? "border-emerald-200 bg-emerald-50" : "border-red-200 bg-red-50"}`}>
              <div className="flex items-center gap-2">{sel.balanced ? <CheckCircle2 size={16} className="text-emerald-600" /> : <AlertTriangle size={16} className="text-red-600" />}
                <span className="text-sm font-700">{sel.balanced ? "Balancé" : "Déséquilibre"}</span></div>
              <p className="mt-1 text-xs text-slate-500">Écart bilan : {money(sel.diff)}</p>
            </div>
            <div className="rounded-xl border border-slate-200 p-4">
              <div className="flex items-center gap-2"><Info size={16} className="text-slate-500" /><span className="text-sm font-700">{newCount} nouveau(x) compte(s)</span></div>
              <p className="mt-1 text-xs text-slate-500">non affecté(s) à cet upload</p>
            </div>
          </div>
        </div>
      ) : <p className="text-sm text-slate-400">Aucune période — uploadez une balance de vérification.</p>}

      {chartData.length > 0 && (
        <div className="card p-5" data-testid="acct-dashboard-chart">
          <h3 className="mb-1 text-sm font-700">Réel vs Budget — {summary.month_label} {summary.year}</h3>
          <p className="mb-4 text-xs text-slate-400">Revenus, dépenses et bénéfice net du mois comparés aux budgets.</p>
          <div style={{ width: "100%", height: 320 }}>
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toLocaleString("fr-CA")} k`} width={70} />
                <Tooltip formatter={(v) => money(v)} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Réel" fill="#063044" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Budget CA" fill="#F8A942" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Budget Rév-1" fill="#808080" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {trendData.length > 1 && (
        <div className="card p-5" data-testid="acct-dashboard-trend">
          <h3 className="mb-1 text-sm font-700">Évolution du bénéfice net</h3>
          <p className="mb-4 text-xs text-slate-400">Trajectoire sur les mois chargés — mensuel et cumulatif (exercice à date).</p>
          <div style={{ width: "100%", height: 300 }}>
            <ResponsiveContainer>
              <LineChart data={trendData} margin={{ top: 10, right: 20, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toLocaleString("fr-CA")} k`} width={70} />
                <Tooltip formatter={(v) => money(v)} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="Bénéfice net (mois)" stroke="#063044" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="Bénéfice net (cumulatif)" stroke="#F8A942" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {period && (
        <div className="grid gap-4 lg:grid-cols-2" data-testid="acct-ai-section">
          <VarianceCard year={Number(period.split("-")[0])} month={Number(period.split("-")[1])} />
          <AiChatPanel year={Number(period.split("-")[0])} month={Number(period.split("-")[1])} />
        </div>
      )}

      <KpiDetailDialog open={kpiDialog.open} onOpenChange={(v) => setKpiDialog((p) => ({ ...p, open: v }))} type={kpiDialog.type} kpi={kpi} />
      <ProjectionDetailDialog open={projDialog.open} onOpenChange={(v) => setProjDialog((p) => ({ ...p, open: v }))} series={projDialog.series} proj={proj} />
      <TaxSettingsDialog open={taxDialog} onOpenChange={setTaxDialog} current={taxFactor} onSaved={() => { api.acctSettings().then((s) => setTaxFactor(s.tax_factor)).catch(() => {}); reloadKpi(); }} />
      <AiConfigDialog open={aiDialog} onOpenChange={setAiDialog} />
    </div>
  );
}

// ---------- Balance de vérification ----------
function AnomaliesCard({ periods }) {
  const [period, setPeriod] = useState("");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => { if (periods.length && !periods.some((p) => p.id === period)) setPeriod(periods[0].id); }, [periods, period]);
  const detect = async () => {
    if (!period) return;
    const [y, m] = period.split("-").map(Number);
    setLoading(true);
    try { setData(await api.acctAiAnomalies({ year: y, month: m })); }
    catch (e) { toast.error(e.response?.data?.detail || "Erreur IA"); }
    finally { setLoading(false); }
  };
  if (!periods.length) return null;
  return (
    <div className="card p-5" data-testid="acct-anomalies-card">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-sm font-700 text-slate-700"><Sparkles size={15} className="text-[#0E9488]" /> Détection d'anomalies (IA)</h3>
        <div className="flex items-center gap-2">
          <PeriodSelect periods={periods} value={period} onChange={setPeriod} testId="acct-anomalies" />
          <Button size="sm" onClick={detect} disabled={loading} data-testid="acct-anomalies-btn" className="bg-[#063044] hover:bg-[#063044]/90">{loading ? "Analyse…" : "Détecter"}</Button>
        </div>
      </div>
      {!data ? <p className="text-xs text-slate-400">Repère les comptes dont le solde s'écarte fortement de leur moyenne des 6 derniers mois. Signalements non bloquants.</p>
        : data.available === false ? <p className="text-xs text-amber-600" data-testid="acct-anomalies-unavailable">{data.reason || "Fonctionnalité IA non configurée."}</p>
        : (data.anomalies || []).length === 0 ? <p className="text-xs text-slate-500" data-testid="acct-anomalies-empty">Aucune anomalie détectée pour cette période.</p>
        : (
          <div className="space-y-3" data-testid="acct-anomalies-result">
            {data.summary && <p className="whitespace-pre-line rounded-lg bg-slate-50 p-3 text-sm leading-relaxed text-slate-700" data-testid="acct-anomalies-summary">{data.summary}</p>}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
                  <th className="px-3 py-2 text-left font-600">Compte</th><th className="px-3 py-2 text-right font-600">Solde</th>
                  <th className="px-3 py-2 text-right font-600">Moyenne</th><th className="px-3 py-2 text-right font-600">Écart</th><th className="px-3 py-2 text-right font-600">z</th>
                </tr></thead>
                <tbody>
                  {data.anomalies.map((an) => (
                    <tr key={an.account} className="border-b border-slate-100" data-testid={`acct-anomaly-${an.account}`}>
                      <td className="px-3 py-2"><span className="font-mono-data text-slate-500">{an.account}</span> <span className="text-slate-700">{an.name}</span></td>
                      <td className="px-3 py-2 text-right font-mono-data">{money(an.value)}</td>
                      <td className="px-3 py-2 text-right font-mono-data text-slate-500">{money(an.moyenne)}</td>
                      <td className="px-3 py-2 text-right font-mono-data" style={{ color: an.ecart < 0 ? "#DC2626" : "#0E9488" }}>{money(an.ecart)}</td>
                      <td className="px-3 py-2 text-right font-mono-data font-700 text-[#B45309]">{an.z}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
    </div>
  );
}

export function AcctBV() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const { periods, reload } = usePeriods();
  const [tmpl, setTmpl] = useState(null);
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [newAcct, setNewAcct] = useState({ open: false, list: [] });
  const [accts, setAccts] = useState([]);
  const [assign, setAssign] = useState({});
  const [assignText, setAssignText] = useState({});
  const [suggesting, setSuggesting] = useState({});
  const [confirmDel, setConfirmDel] = useState(null);
  const loadTmpl = useCallback(() => api.acctGetTemplate().then(setTmpl).catch(() => {}), []);
  useEffect(() => { loadTmpl(); api.acctAccounts().then(setAccts).catch(() => {}); }, [loadTmpl]);

  const onTemplate = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    setBusy(true);
    try { const r = await api.acctUploadTemplate(f); toast.success(`Modèle importé — ${r.account_count} comptes`); loadTmpl(); }
    catch (err) { toast.error(err.response?.data?.detail || "Import impossible"); } finally { setBusy(false); }
  };
  const onBV = async (e) => {
    const f = e.target.files?.[0]; e.target.value = "";
    if (!f) return;
    setBusy(true);
    try {
      const r = await api.acctUploadBV(f, { year, month });
      setResult(r);
      if (r.new_accounts?.length) { setAssign({}); setNewAcct({ open: true, list: r.new_accounts }); }
      if (r.balanced === false) toast.warning(`BV chargée mais déséquilibre (écart ${money(r.diff)})`);
      else toast.success(`BV ${MONTHS[month - 1]} ${year} chargée${r.balanced ? " — balancée" : ""}`);
      reload();
    } catch (err) { toast.error(err.response?.data?.detail || "Upload impossible"); } finally { setBusy(false); }
  };
  const toggleLock = async (p) => {
    try { await api.acctLock({ year: p.year, month: p.month, locked: !p.locked }); toast.success(!p.locked ? "Mois verrouillé" : "Mois déverrouillé"); reload(); }
    catch (err) { toast.error(err.response?.data?.detail || "Action impossible"); }
  };
  const deletePeriod = async (p) => {
    try { await api.acctDeletePeriod({ year: p.year, month: p.month }); toast.success(`BV ${MONTHS[p.month - 1]} ${p.year} supprimée`); reload(); }
    catch (err) { toast.error(err.response?.data?.detail || "Suppression impossible"); }
    finally { setConfirmDel(null); }
  };
  const saveAssignments = async () => {
    const clean = {};
    for (const [k, v] of Object.entries(assign)) if (v) clean[k] = v;
    try {
      await api.acctAccountMap(clean, { year, month });
      toast.success(`${Object.keys(clean).length} compte(s) affecté(s)`);
      setNewAcct({ open: false, list: [] }); setAssign({}); setAssignText({}); reload();
    } catch (err) { toast.error(err.response?.data?.detail || "Enregistrement impossible"); }
  };
  const suggestMapping = async (a) => {
    setSuggesting((s) => ({ ...s, [a.account]: true }));
    try {
      const r = await api.acctAiSuggestMapping({ account: a.account, name: a.name });
      if (r.available === false) { toast.warning(r.reason || "Fonctionnalité IA non configurée."); return; }
      const sug = r.suggestion || {};
      if (sug.account) {
        setAssign((s) => ({ ...s, [a.account]: Number(sug.account) }));
        setAssignText((s) => ({ ...s, [a.account]: `${sug.account} — ${sug.name || ""}` }));
        toast.success(`Suggestion : ${sug.account} — ${sug.name || ""}${sug.raison ? ` (${sug.raison})` : ""}`);
      } else {
        toast.info("Aucune suggestion pertinente trouvée.");
      }
    } catch (err) { toast.error(err.response?.data?.detail || "Suggestion impossible"); }
    finally { setSuggesting((s) => ({ ...s, [a.account]: false })); }
  };
  const allAssigned = newAcct.list.length > 0 && newAcct.list.every((a) => assign[a.account]);

  return (
    <div className="space-y-5" data-testid="acct-bv-page">
      {isAdmin && (
        <div className="card p-5">
          <h3 className="mb-1 text-sm font-700">Modèle Bilan / États des résultats</h3>
          <p className="mb-3 text-xs text-slate-500">{tmpl?.imported ? `Importé — ${tmpl.account_count} comptes mappés (par ${tmpl.imported_by})` : "Aucun modèle importé. Importez le modèle Excel avec les formules pour extraire le mapping des comptes."}</p>
          <label className="inline-flex">
            <input type="file" accept=".xlsx" className="hidden" onChange={onTemplate} data-testid="acct-template-input" />
            <span className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-600 hover:bg-slate-50"><Upload size={15} /> {tmpl?.imported ? "Remplacer le modèle" : "Importer le modèle"}</span>
          </label>
        </div>
      )}

      <div className="card p-5">
        <h3 className="mb-3 text-sm font-700">Uploader une balance de vérification</h3>
        <div className="flex flex-wrap items-end gap-3">
          <div><label className="block text-xs font-600 text-slate-500">Mois</label>
            <Select value={String(month)} onValueChange={(v) => setMonth(Number(v))}>
              <SelectTrigger data-testid="acct-bv-month" className="mt-1 w-40"><SelectValue /></SelectTrigger>
              <SelectContent>{MONTHS.map((m, i) => <SelectItem key={i} value={String(i + 1)}>{m}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div><label className="block text-xs font-600 text-slate-500">Année</label>
            <Select value={String(year)} onValueChange={(v) => setYear(Number(v))}>
              <SelectTrigger data-testid="acct-bv-year" className="mt-1 w-32"><SelectValue /></SelectTrigger>
              <SelectContent>{[now.getFullYear() - 1, now.getFullYear(), now.getFullYear() + 1].map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <label className="inline-flex">
            <input type="file" accept=".xlsx" className="hidden" onChange={onBV} disabled={busy} data-testid="acct-bv-input" />
            <span className={`inline-flex cursor-pointer items-center gap-2 rounded-lg bg-[#063044] px-4 py-2 text-sm font-600 text-white hover:bg-[#063044]/90 ${busy ? "opacity-60" : ""}`}><Upload size={15} /> {busy ? "Traitement…" : "Uploader la BV (.xlsx)"}</span>
          </label>
        </div>
        {result && (
          <div className="mt-4 flex flex-wrap gap-3 text-sm" data-testid="acct-bv-result">
            <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 font-600 ${result.balanced ? "bg-emerald-100 text-emerald-700" : "bg-red-100 text-red-700"}`}>
              {result.balanced ? <CheckCircle2 size={14} /> : <AlertTriangle size={14} />}{result.balanced ? "Balancée" : "Déséquilibre"} · écart {money(result.diff)}</span>
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 font-600 text-slate-600">{result.account_count} comptes</span>
            {result.new_accounts?.length > 0 && <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1 font-600 text-amber-700"><Info size={14} /> {result.new_accounts.length} nouveau(x) compte(s)</span>}
            {!result.template_imported && <span className="text-amber-600">⚠ Aucun modèle importé — validation partielle</span>}
          </div>
        )}
      </div>

      <div className="card overflow-hidden">
        <div className="border-b border-slate-200 px-5 py-3"><h3 className="text-sm font-700">Périodes</h3></div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
              <th className="px-5 py-2.5 text-left font-600">Mois</th><th className="px-5 py-2.5 text-left font-600">Statut</th>
              <th className="px-5 py-2.5 text-right font-600">Comptes</th><th className="px-5 py-2.5 text-right font-600">Écart bilan</th>
              <th className="px-5 py-2.5 text-left font-600">Dernier upload</th><th className="px-5 py-2.5 text-right font-600">Action</th>
            </tr></thead>
            <tbody>
              {periods.length === 0 && <tr><td colSpan={6} className="px-5 py-8 text-center text-slate-400">Aucune période.</td></tr>}
              {periods.map((p) => (
                <tr key={p.id} className="border-b border-slate-100" data-testid={`acct-period-row-${p.id}`}>
                  <td className="px-5 py-2.5 font-600">{MONTHS[p.month - 1]} {p.year}</td>
                  <td className="px-5 py-2.5">
                    {p.locked ? <span className="inline-flex items-center gap-1 text-red-600"><Lock size={13} /> Verrouillé</span>
                      : <span className="inline-flex items-center gap-1 text-amber-600"><Unlock size={13} /> Provisoire</span>}
                  </td>
                  <td className="px-5 py-2.5 text-right font-mono-data">{p.account_count ?? "—"}</td>
                  <td className="px-5 py-2.5 text-right font-mono-data" style={{ color: p.balanced ? "#0E9488" : "#DC2626" }}>{money(p.diff)}</td>
                  <td className="px-5 py-2.5 text-xs text-slate-500">{p.last_upload_at ? new Date(p.last_upload_at).toLocaleString("fr-CA") : "—"}</td>
                  <td className="px-5 py-2.5 text-right">
                    {isAdmin ? (
                      <div className="inline-flex items-center gap-2">
                        <Button size="sm" variant="outline" data-testid={`acct-lock-${p.id}`} onClick={() => toggleLock(p)}
                          className={`gap-1 ${p.locked ? "border-emerald-200 text-emerald-700" : "border-red-200 text-red-600"}`}>
                          {p.locked ? <><Unlock size={13} /> Déverrouiller</> : <><Lock size={13} /> Verrouiller</>}
                        </Button>
                        {!p.locked && (
                          <Button size="sm" variant="outline" data-testid={`acct-delete-${p.id}`} onClick={() => setConfirmDel(p)}
                            className="gap-1 border-red-200 text-red-600 hover:bg-red-50">
                            <Trash2 size={13} /> Supprimer
                          </Button>
                        )}
                      </div>
                    ) : <span className="text-xs text-slate-400">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <AnomaliesCard periods={periods} />

      <AlertDialog open={!!confirmDel} onOpenChange={(v) => !v && setConfirmDel(null)}>
        <AlertDialogContent data-testid="acct-delete-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer cette balance de vérification ?</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDel ? `La BV de ${MONTHS[confirmDel.month - 1]} ${confirmDel.year} et ses données seront définitivement supprimées. Cette action est irréversible.` : ""}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="acct-delete-cancel-btn">Annuler</AlertDialogCancel>
            <AlertDialogAction data-testid="acct-delete-confirm-btn" className="bg-red-600 hover:bg-red-700"
              onClick={() => deletePeriod(confirmDel)}>
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={newAcct.open} onOpenChange={() => { /* bloquant : fermeture via bouton uniquement */ }}>
        <DialogContent data-testid="acct-newacct-dialog" className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>Affectation requise — nouveaux comptes détectés</DialogTitle>
            <DialogDescription>Ces comptes sont présents dans la BV mais absents du modèle. Affectez chacun à un compte existant du rapport (son montant y sera regroupé). L'affectation est mémorisée pour les prochains uploads.</DialogDescription>
          </DialogHeader>
          <datalist id="acct-target-list">
            {accts.map((a) => <option key={a.account} value={`${a.account} — ${a.name}`} />)}
          </datalist>
          <div className="max-h-80 space-y-2 overflow-y-auto" data-testid="acct-newacct-list">
            {newAcct.list.map((a) => (
              <div key={a.account} className="grid grid-cols-2 items-center gap-3 rounded-lg border border-slate-200 p-2">
                <div className="text-sm"><span className="font-mono-data text-slate-500">{a.account}</span> <span className="text-slate-700">{a.name}</span></div>
                <div className="flex items-center gap-1.5">
                  <input list="acct-target-list" data-testid={`acct-assign-${a.account}`} placeholder="Regrouper avec le compte…"
                    value={assignText[a.account] || ""}
                    className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm outline-none focus:border-[#063044]"
                    onChange={(e) => { const val = e.target.value; setAssignText((s) => ({ ...s, [a.account]: val })); const m = val.match(/^(\d+)/); setAssign((s) => ({ ...s, [a.account]: m ? Number(m[1]) : "" })); }} />
                  <button type="button" data-testid={`acct-suggest-${a.account}`} onClick={() => suggestMapping(a)} disabled={!!suggesting[a.account]}
                    title="Suggérer une catégorie (IA)"
                    className="inline-flex shrink-0 items-center gap-1 rounded-md border border-[#0E9488]/40 px-2 py-1.5 text-xs font-600 text-[#0E9488] hover:bg-[#0E9488]/10 disabled:opacity-50">
                    <Wand2 size={13} /> {suggesting[a.account] ? "…" : "Suggérer"}
                  </button>
                </div>
              </div>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" data-testid="acct-newacct-skip" onClick={() => { setNewAcct({ open: false, list: [] }); toast.warning("Comptes non affectés — rapports incomplets jusqu'à l'affectation."); }}>Plus tard</Button>
            <Button data-testid="acct-newacct-save" disabled={!allAssigned} onClick={saveAssignments}>Enregistrer les affectations</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ---------- Rapport (Bilan / P&L) ----------
// Reproduit le format Excel d'une ligne de rapport (fond, couleur police, gras, bordures).
function excelRowStyle(ln, boldTotals = true) {
  const st = (ln && ln.style) || {};
  const isDark = st.f === "dark";
  const isGrey = st.f === "grey";
  const cls = [];
  const bold = isDark || isGrey || st.b || (boldTotals && ln.kind === "total") || ln.kind === "header";
  if (bold) cls.push("font-700");
  if (st.t) cls.push("border-t border-slate-300");
  if (st.u) cls.push("border-b-2 border-slate-300");
  const bg = isDark ? "#063044" : isGrey ? "#eef1f5" : undefined;
  let color;
  if (isDark) color = st.c || "#FFFFFF";
  else if (st.c) color = st.c;
  else if (ln.kind === "header") color = "#063044";
  else color = undefined;
  const headerDefault = !isDark && !isGrey && !st.c && ln.kind === "header";
  // Ligne-poste non totalisée du sommaire : rendue comme une ligne de données (poids normal, slate-700).
  const plain = !boldTotals && !bold;
  return { cls: cls.join(" "), bg, color, isDark, headerDefault, plain };
}
function excelCellColor(s, val, ecart) {
  if (s.isDark) return val < 0 ? "#FCA5A5" : (s.color || "#FFFFFF");
  if (val < 0) return "#DC2626";
  if (ecart) return "#64748B";
  return s.color || undefined;
}

function ReportView({ type, title }) {
  const { periods } = usePeriods();
  const [period, setPeriod] = useState("");
  const [rep, setRep] = useState(null);
  const [loading, setLoading] = useState(false);
  const [hideZero, setHideZero] = useState(false);
  const [hiddenGroups, setHiddenGroups] = useState({});
  useEffect(() => {
    if (!periods.length) return;
    const f = sessionStorage.getItem("acct_focus_period");
    if (f && periods.some((p) => p.id === f)) { sessionStorage.removeItem("acct_focus_period"); setPeriod(f); return; }
    if (!periods.some((p) => p.id === period)) setPeriod(periods[0].id);
  }, [periods, period]);
  useEffect(() => {
    if (!period) return;
    const [y, m] = period.split("-").map(Number);
    setLoading(true); setRep(null);
    api.acctReport({ type, year: y, month: m }).then(setRep).catch((e) => toast.error(e.response?.data?.detail || "Rapport indisponible")).finally(() => setLoading(false));
  }, [period, type]);

  const exportExcel = async () => {
    const [y, m] = period.split("-").map(Number);
    try {
      const blob = await api.acctReportExcel({ type, year: y, month: m });
      const url = URL.createObjectURL(blob); const a = document.createElement("a");
      a.href = url; a.download = `${type === "bilan" ? "bilan" : "resultats"}_${period}.xlsx`; a.click(); URL.revokeObjectURL(url);
      toast.success("Export téléchargé");
    } catch (e) { toast.error(e.response?.data?.detail || "Export impossible"); }
  };
  const colLabel = (k) => ({
    reel: rep ? `Réel ${rep.month_label}` : "Réel", cumulatif: "Réel à date",
    bud_rev2: "Bud. Rév-2", ecart_rev2: "Écart Rév-2", bud_rev1: "Bud. Rév-1",
    ecart_rev1: "Écart Rév-1", bud_ca: "Bud. CA", ecart_ca: "Écart CA", reel_prec: "Réel an. préc.",
    bud_rev2_cum: "Bud. Rév-2", ecart_rev2_cum: "Écart Rév-2", bud_rev1_cum: "Bud. Rév-1",
    ecart_rev1_cum: "Écart Rév-1", bud_ca_cum: "Bud. CA", ecart_ca_cum: "Écart CA", prec_cum: "Cumul. an. préc.",
    mois: rep ? `${rep.month_label} ${rep.year}` : "Mois",
  }[k] || k);
  const isEcart = (k) => k.startsWith("ecart");
  const toggleGroups = rep?.col_toggle_groups || null;
  const hiddenKeys = new Set(
    (toggleGroups || []).filter((g) => hiddenGroups[g.id]).flatMap((g) => g.keys)
  );
  const visibleCols = !rep ? [] : rep.value_cols.filter((k) => !hiddenKeys.has(k));
  const visibleGroups = !rep?.col_groups ? null : rep.col_groups
    .map((g) => ({ ...g, keys: g.keys.filter((k) => !hiddenKeys.has(k)) }))
    .filter((g) => g.keys.length > 0);
  const showSep = (k) => k === "cumulatif" && visibleGroups && visibleGroups.length > 1;
  const visibleLines = rep ? rep.lines.filter((ln) => !(hideZero && ln.kind === "data" && visibleCols.every((k) => Math.abs(ln.values[k] || 0) < 0.005))) : [];

  if (!periods.length) return <NoPeriodsState testId={`acct-no-periods-${type}`} />;

  return (
    <div className="space-y-4" data-testid={`acct-report-${type}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <PeriodSelect periods={periods} value={period} onChange={setPeriod} testId={`acct-${type}`} />
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-600" data-testid="acct-hidezero-label">
            <input type="checkbox" checked={hideZero} onChange={(e) => setHideZero(e.target.checked)} data-testid="acct-hidezero-toggle" className="h-4 w-4 rounded border-slate-300" />
            Masquer les comptes à solde zéro
          </label>
          {rep?.col_toggle_groups && (
            <div className="flex flex-wrap items-center gap-2" data-testid="acct-colgroups">
              <span className="text-sm text-slate-500">Colonnes :</span>
              {rep.col_toggle_groups.map((g) => {
                const hidden = !!hiddenGroups[g.id];
                return (
                  <button key={g.id} type="button" data-testid={`acct-colgroup-${g.id}`}
                    onClick={() => setHiddenGroups((s) => ({ ...s, [g.id]: !s[g.id] }))}
                    className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-600 transition-colors ${hidden ? "border-slate-200 bg-white text-slate-400" : "border-[#063044]/30 bg-[#063044]/10 text-[#063044]"}`}>
                    {hidden ? <Plus size={13} /> : <Minus size={13} />} {g.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <Button size="sm" onClick={exportExcel} disabled={!rep} data-testid="acct-export-excel" className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><FileSpreadsheet size={15} /> Excel</Button>
      </div>
      {rep && !rep.locked && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-600 text-amber-700" data-testid="acct-provisional-banner">
          <AlertTriangle size={16} /> Données provisoires — ce mois n'est pas verrouillé.
        </div>
      )}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="text-sm font-700">{title}{rep ? ` — ${rep.month_label} ${rep.year}` : ""}</h3>
          {rep && <span className={`inline-flex items-center gap-1 text-xs font-600 ${rep.balanced ? "text-emerald-600" : "text-red-600"}`}>{rep.balanced ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}{rep.balanced ? "Balancé" : "Déséquilibre"}</span>}
        </div>
        {loading ? <p className="px-5 py-8 text-sm text-slate-500">Chargement…</p> : !rep ? <p className="px-5 py-8 text-sm text-slate-400">Sélectionnez une période avec une BV chargée.</p> : (
          <div className="overflow-auto max-h-[calc(100vh-230px)]">
            <table className="w-full text-sm">
              <thead>
                {visibleGroups && (
                  <tr className="sticky top-0 z-20 border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-500">
                    <th className="bg-white px-4 py-1.5" colSpan={2}></th>
                    {visibleGroups.map((g, gi) => (
                      <th key={g.label} colSpan={g.keys.length} className={`bg-white px-4 py-1.5 text-center font-700 text-slate-600 ${gi > 0 ? "border-l-2 border-slate-200" : ""}`}>{g.label}</th>
                    ))}
                  </tr>
                )}
                <tr className={`sticky z-20 border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400 ${visibleGroups ? "top-[30px]" : "top-0"}`}>
                <th className="bg-white px-4 py-2.5 text-left font-600">Compte</th>
                <th className="bg-white px-4 py-2.5 text-left font-600">Description</th>
                {visibleCols.map((k) => <th key={k} className={`bg-white px-4 py-2.5 text-right font-600 ${isEcart(k) ? "text-slate-500" : ""} ${showSep(k) ? "border-l-2 border-slate-200" : ""}`}>{colLabel(k)}</th>)}
              </tr></thead>
              <tbody className="font-mono-data">
                {visibleLines.map((ln) => {
                  const s = excelRowStyle(ln, !type.includes("sommaire"));
                  return (
                  <tr key={ln.row} data-testid={`acct-line-${ln.row}`}
                    className={`border-b border-slate-50 ${s.cls}`} style={{ background: s.bg }}>
                    <td className="px-4 py-1.5 text-left" style={{ color: s.isDark ? "#94A3B8" : "#94A3B8" }}>{ln.account || ""}</td>
                    <td className={`px-4 py-1.5 text-left font-sans ${s.headerDefault ? "text-[#063044]" : ((!s.color && ln.kind === "data") || s.plain ? "text-slate-700" : "")}`} style={{ color: s.headerDefault ? undefined : (s.color || undefined) }}>{ln.label}</td>
                    {visibleCols.map((k) => (
                      <td key={k} className={`px-4 py-1.5 text-right ${isEcart(k) ? "italic" : ""} ${showSep(k) ? "border-l-2 border-slate-200" : ""}`} style={{ color: excelCellColor(s, ln.values[k], isEcart(k)) }}>{ln.kind === "header" ? "" : money(ln.values[k])}</td>
                    ))}
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function ViewToggle({ value, onChange, options }) {
  return (
    <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm" data-testid="acct-view-toggle">
      {options.map((o) => (
        <button key={o.value} data-testid={`acct-view-${o.value}`} onClick={() => onChange(o.value)}
          className={`rounded-lg px-4 py-1.5 text-sm font-600 transition-colors ${value === o.value ? "bg-[#063044] text-white" : "text-slate-500 hover:text-slate-900"}`}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function AcctBilan() {
  const [v, setV] = useState("detaille");
  return (
    <div className="space-y-4">
      <ViewToggle value={v} onChange={setV} options={[{ value: "detaille", label: "Bilan détaillé" }, { value: "sommaire", label: "Bilan sommaire" }, { value: "sommaire_m", label: "Bilan sommaire (M$)" }]} />
      {v === "detaille" ? <ReportView type="bilan" title="Bilan détaillé" />
        : v === "sommaire_m" ? <BilanSommaireView millions />
        : <BilanSommaireView />}
    </div>
  );
}

export function AcctPnl() {
  const [v, setV] = useState("detaille");
  return (
    <div className="space-y-4">
      <ViewToggle value={v} onChange={setV} options={[{ value: "detaille", label: "État détaillé" }, { value: "sommaire", label: "Résultat sommaire" }]} />
      {v === "detaille" ? <ReportView type="pnl" title="État des résultats" /> : <ReportView type="pnl_sommaire" title="Résultat sommaire" />}
    </div>
  );
}

function BilanSommaireView({ millions = false }) {
  const { periods } = usePeriods();
  const [period, setPeriod] = useState("");
  const [rep, setRep] = useState(null);
  const [loading, setLoading] = useState(false);
  const fmt = millions ? moneyM : money;
  useEffect(() => {
    if (!periods.length) return;
    const f = sessionStorage.getItem("acct_focus_period");
    if (f && periods.some((p) => p.id === f)) { sessionStorage.removeItem("acct_focus_period"); setPeriod(f); return; }
    if (!periods.some((p) => p.id === period)) setPeriod(periods[0].id);
  }, [periods, period]);
  useEffect(() => {
    if (!period) return;
    const [y, m] = period.split("-").map(Number);
    setLoading(true); setRep(null);
    api.acctReport({ type: "bilan_sommaire", year: y, month: m })
      .then(setRep).catch((e) => toast.error(e.response?.data?.detail || "Rapport indisponible")).finally(() => setLoading(false));
  }, [period]);

  const exportExcel = async () => {
    const [y, m] = period.split("-").map(Number);
    try {
      const blob = await api.acctReportExcel({ type: "bilan_sommaire", year: y, month: m });
      const url = URL.createObjectURL(blob); const a = document.createElement("a");
      a.href = url; a.download = `bilan_sommaire_${period}.xlsx`; a.click(); URL.revokeObjectURL(url);
      toast.success("Export téléchargé");
    } catch (e) { toast.error(e.response?.data?.detail || "Export impossible"); }
  };

  const Side = ({ title, rows }) => (
    <div>
      <h4 className="mb-2 border-b-2 border-[#063044] pb-1.5 font-display text-sm font-800 uppercase tracking-wide text-[#063044]">{title}</h4>
      <table className="w-full text-sm">
        <tbody className="font-mono-data">
          {rows.map((l, i) => {
            const s = excelRowStyle(l);
            return (
            <tr key={i} className={`border-b border-slate-50 ${s.cls}`} style={{ background: s.bg }}>
              <td className={`px-3 py-1.5 text-left font-sans ${l.kind === "data" ? "pl-5" : ""} ${s.headerDefault ? "text-[#063044]" : (!s.color && l.kind === "data" ? "text-slate-700" : "")}`} style={{ color: s.headerDefault ? undefined : (s.color || undefined) }}>{l.label}</td>
              <td className="px-3 py-1.5 text-right" style={{ color: l.value == null ? undefined : excelCellColor(s, l.value, false) }}>{l.value == null ? "" : fmt(l.value)}</td>
            </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  if (!periods.length) return <NoPeriodsState testId="acct-no-periods-bilansom" />;

  return (
    <div className="space-y-4" data-testid="acct-bilan-sommaire">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <PeriodSelect periods={periods} value={period} onChange={setPeriod} testId="acct-bilansom" />
        <Button size="sm" onClick={exportExcel} disabled={!rep} data-testid="acct-bilansom-export" className="gap-2 bg-[#063044] hover:bg-[#063044]/90"><FileSpreadsheet size={15} /> Excel</Button>
      </div>
      {rep && !rep.locked && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-600 text-amber-700">
          <AlertTriangle size={16} /> Données provisoires — ce mois n'est pas verrouillé.
        </div>
      )}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="font-display text-sm font-700">Bilan sommaire{millions ? " (en M$)" : ""}{rep ? ` — ${rep.month_label} ${rep.year}` : ""}</h3>
          {rep && <span className={`inline-flex items-center gap-1 text-xs font-600 ${Math.abs(rep.validation) < 1 ? "text-emerald-600" : "text-red-600"}`} data-testid="acct-bilansom-balance">{Math.abs(rep.validation) < 1 ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}{Math.abs(rep.validation) < 1 ? "Balancé" : `Écart ${money(rep.validation)}`}</span>}
        </div>
        {loading ? <p className="px-5 py-8 text-sm text-slate-500">Chargement…</p> : !rep ? <p className="px-5 py-8 text-sm text-slate-400">Sélectionnez une période.</p> : (
          <div className="grid gap-8 p-5 lg:grid-cols-2">
            <Side title="Actif" rows={rep.actif} />
            <Side title="Passif et capitaux" rows={rep.passif} />
          </div>
        )}
      </div>
    </div>
  );
}

export function AcctComingSoon({ label }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-3 p-16 text-center" data-testid="acct-coming-soon">
      <Construction size={40} className="text-slate-300" />
      <h3 className="text-lg font-700">{label}</h3>
      <p className="max-w-md text-sm text-slate-500">Fonctionnalité à venir. Ce module sera développé dans une phase ultérieure.</p>
    </div>
  );
}

export function AcctCashflow() { return <CashflowView />; }
export function AcctAudit() { return <AcctComingSoon label="Rapports d'audit" />; }

// ---------- Flux de trésorerie (méthode indirecte) ----------
function CashflowView() {
  const { periods } = usePeriods();
  const [closeP, setCloseP] = useState("");
  const [openP, setOpenP] = useState("");
  const [rep, setRep] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!periods.length) return;
    if (!periods.some((p) => p.id === closeP)) setCloseP(periods[0].id);
    if (!periods.some((p) => p.id === openP)) setOpenP((periods[1] || periods[0]).id);
  }, [periods, closeP, openP]);

  useEffect(() => {
    if (!openP || !closeP || openP === closeP) { setRep(null); return; }
    const [oy, om] = openP.split("-").map(Number);
    const [cy, cm] = closeP.split("-").map(Number);
    setLoading(true); setRep(null);
    api.acctCashflow({ open_year: oy, open_month: om, close_year: cy, close_month: cm })
      .then(setRep).catch((e) => toast.error(e.response?.data?.detail || "Flux indisponible")).finally(() => setLoading(false));
  }, [openP, closeP]);

  const exportExcel = async () => {
    const [oy, om] = openP.split("-").map(Number);
    const [cy, cm] = closeP.split("-").map(Number);
    try {
      const blob = await api.acctCashflowExcel({ open_year: oy, open_month: om, close_year: cy, close_month: cm });
      const url = URL.createObjectURL(blob); const a = document.createElement("a");
      a.href = url; a.download = `flux_tresorerie_${openP}_${closeP}.xlsx`; a.click(); URL.revokeObjectURL(url);
      toast.success("Export téléchargé");
    } catch (e) { toast.error(e.response?.data?.detail || "Export impossible"); }
  };

  const waterfall = rep ? (() => {
    let run = rep.encaisse_ouverture;
    const steps = [{ name: "Ouverture", range: [0, run], fill: "#808080", delta: run }];
    [["Exploitation", rep.exploitation_total], ["Investissement", rep.investissement_total], ["Financement", rep.financement_total]].forEach(([name, delta]) => {
      const start = run, end = run + delta;
      steps.push({ name, range: [Math.min(start, end), Math.max(start, end)], fill: delta >= 0 ? "#15AF97" : "#F8A942", delta });
      run = end;
    });
    steps.push({ name: "Clôture", range: [0, run], fill: "#063044", delta: run });
    return steps;
  })() : [];

  const Row = ({ label, value, kind, indent }) => (
    <tr className={`border-b border-slate-50 ${kind === "section" ? "bg-slate-100 font-800 text-slate-800" : kind === "subtotal" ? "bg-slate-50 font-700" : kind === "net" ? "border-t-2 border-slate-300 font-800" : ""}`}>
      <td className={`px-4 py-2 text-left ${indent ? "pl-9 font-sans text-slate-600" : "font-sans"}`}>{label}</td>
      <td className="px-4 py-2 text-right font-mono-data" style={{ color: value != null && value < 0 ? "#DC2626" : undefined }}>
        {value == null ? "" : money(value)}
      </td>
    </tr>
  );

  if (!periods.length) return <NoPeriodsState testId="acct-no-periods-cashflow" />;

  return (
    <div className="space-y-4" data-testid="acct-cashflow">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="block text-xs font-600 text-slate-500">Ouverture (solde de départ)</label>
            <div className="mt-1"><PeriodSelect periods={periods} value={openP} onChange={setOpenP} testId="acct-cf-open" /></div>
          </div>
          <div>
            <label className="block text-xs font-600 text-slate-500">Clôture (période courante)</label>
            <div className="mt-1"><PeriodSelect periods={periods} value={closeP} onChange={setCloseP} testId="acct-cf-close" /></div>
          </div>
        </div>
        <Button size="sm" onClick={exportExcel} disabled={!rep} data-testid="acct-cashflow-export" className="gap-2 bg-[#0E9488] hover:bg-[#0E9488]/90"><FileSpreadsheet size={15} /> Excel</Button>
      </div>
      <div className="flex items-start gap-2 rounded-xl border border-sky-200 bg-sky-50 px-4 py-2.5 text-xs text-sky-800" data-testid="acct-cashflow-hint">
        <Info size={15} className="mt-0.5 shrink-0" /> Méthode indirecte. Pour un flux « depuis le début de l'exercice », choisissez comme ouverture la BV de fin d'exercice précédent. Les variations = solde de clôture − solde d'ouverture.
      </div>
      {rep && (
        <div className="card p-5" data-testid="acct-cashflow-waterfall">
          <h3 className="mb-1 text-sm font-700">De l'encaisse d'ouverture à la clôture</h3>
          <p className="mb-4 text-xs text-slate-400">Contribution de chaque activité à la variation de l'encaisse (cascade).</p>
          <div style={{ width: "100%", height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={waterfall} margin={{ top: 10, right: 10, left: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${(v / 1000).toLocaleString("fr-CA")} k`} width={70} />
                <Tooltip cursor={{ fill: "#F1F5F9" }} contentStyle={{ fontSize: 12, borderRadius: 8 }}
                  formatter={(v, n, p) => [money(p.payload.delta), "Montant"]} />
                <Bar dataKey="range" radius={[4, 4, 0, 0]}>
                  {waterfall.map((s, i) => <Cell key={i} fill={s.fill} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
      {rep && !rep.locked && (
        <div className="flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-50 px-4 py-2.5 text-sm font-600 text-amber-700">
          <AlertTriangle size={16} /> Données provisoires — le mois de clôture n'est pas verrouillé.
        </div>
      )}
      <div className="card overflow-hidden">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="text-sm font-700">État des flux de trésorerie{rep ? ` — du ${rep.open_label} au ${rep.close_label}` : ""}</h3>
          {rep && <span className={`inline-flex items-center gap-1 text-xs font-600 ${rep.balanced ? "text-emerald-600" : "text-red-600"}`} data-testid="acct-cashflow-reconcile">{rep.balanced ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}{rep.balanced ? "Réconcilié" : `Écart ${money(rep.ecart)}`}</span>}
        </div>
        {loading ? <p className="px-5 py-8 text-sm text-slate-500">Chargement…</p> : !rep ? <p className="px-5 py-8 text-sm text-slate-400">Sélectionnez deux périodes différentes avec des BV chargées.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-slate-200 text-[11px] uppercase tracking-wider text-slate-400">
                <th className="px-4 py-2.5 text-left font-600">Poste</th>
                <th className="px-4 py-2.5 text-right font-600">Montant</th>
              </tr></thead>
              <tbody>
                <Row label="ACTIVITÉS D'EXPLOITATION" kind="section" />
                <Row label="Bénéfice net (perte nette)" value={rep.benefice_net} indent />
                {Math.abs(rep.amortissement) >= 0.005 && <Row label="Amortissement" value={rep.amortissement} indent />}
                {rep.fdr.length > 0 && <Row label="Variation des éléments hors caisse du fonds de roulement :" />}
                {rep.fdr.map((l, i) => <Row key={`f${i}`} label={l.label} value={l.value} indent />)}
                <Row label="Flux liés aux activités d'exploitation" value={rep.exploitation_total} kind="subtotal" />
                <Row label="ACTIVITÉS D'INVESTISSEMENT" kind="section" />
                {rep.investissement.map((l, i) => <Row key={`i${i}`} label={l.label} value={l.value} indent />)}
                {rep.investissement.length === 0 && <Row label="Aucune activité d'investissement" indent />}
                <Row label="Flux liés aux activités d'investissement" value={rep.investissement_total} kind="subtotal" />
                <Row label="ACTIVITÉS DE FINANCEMENT" kind="section" />
                {rep.financement.map((l, i) => <Row key={`n${i}`} label={l.label} value={l.value} indent />)}
                {rep.financement.length === 0 && <Row label="Aucune activité de financement" indent />}
                <Row label="Flux liés aux activités de financement" value={rep.financement_total} kind="subtotal" />
                <Row label="VARIATION NETTE DE LA TRÉSORERIE" value={rep.variation_nette} kind="net" />
                <Row label="Encaisse à l'ouverture" value={rep.encaisse_ouverture} indent />
                <Row label="Encaisse à la clôture" value={rep.encaisse_cloture} kind="subtotal" />
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
