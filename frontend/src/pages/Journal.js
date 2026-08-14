import { UserAvatar } from "../components/UserAvatar";

import { useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { ScrollText, Plus, Pencil, Trash2, Download } from "lucide-react";

const ACTION_STYLE = {
  "Créer": { bg: "#FBBF241a", color: "#22C55E", icon: Plus },
  "Modifier": { bg: "#0F172A1a", color: "#0F172A", icon: Pencil },
  "Supprimer": { bg: "#EF44441a", color: "#EF4444", icon: Trash2 },
};

export default function Journal() {
  const { t, lang } = useLang();
  const [entries, setEntries] = useState(null);
  const [entityFilter, setEntityFilter] = useState("");
  const [userFilter, setUserFilter] = useState("");
  useEffect(() => { api.getJournal().then(setEntries); }, []);
  const fmtDate = (iso) => {
    try { return new Date(iso).toLocaleString(lang === "en" ? "en-CA" : "fr-CA", { dateStyle: "medium", timeStyle: "short" }); }
    catch { return iso; }
  };
  const entityOptions = useMemo(() => [...new Set((entries || []).map((e) => e.entity).filter(Boolean))].sort(), [entries]);
  const userOptions = useMemo(() => [...new Set((entries || []).map((e) => e.user_name || e.user_email).filter(Boolean))].sort(), [entries]);
  const filtered = useMemo(() => (entries || []).filter((e) =>
    (!entityFilter || e.entity === entityFilter) && (!userFilter || (e.user_name || e.user_email) === userFilter)
  ), [entries, entityFilter, userFilter]);

  const exportCsv = () => {
    const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
    const rows = [["Date", "Utilisateur", "Action", "Entité", "Élément", "Changements"]];
    filtered.forEach((e) => {
      const ch = (Array.isArray(e.changes) ? e.changes : []).map((c) => `${c.label}: ${c.old} -> ${c.new}`).join(" | ");
      rows.push([fmtDate(e.timestamp), e.user_name || e.user_email, t(e.action), t(e.entity), e.label, ch]);
    });
    const csv = "\uFEFF" + rows.map((r) => r.map(esc).join(";")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8;" }));
    const a = document.createElement("a"); a.href = url; a.download = `journal_${new Date().toISOString().slice(0, 10)}.csv`; a.click(); URL.revokeObjectURL(url);
  };

  if (!entries) return <p className="font-mono-data text-sm text-slate-500">{t("Chargement…")}</p>;

  return (
    <div className="space-y-4" data-testid="journal-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500"><b className="text-slate-800">{filtered.length}</b> {t("modification(s) enregistrée(s)")}{(entityFilter || userFilter) ? ` / ${entries.length}` : ""}</p>
        <div className="flex flex-wrap items-center gap-2">
          <select value={entityFilter} onChange={(e) => setEntityFilter(e.target.value)} data-testid="journal-filter-entity"
            className="h-9 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 focus:border-[#22C55E] focus:outline-none">
            <option value="">{t("Toutes les entités")}</option>
            {entityOptions.map((o) => <option key={o} value={o}>{t(o)}</option>)}
          </select>
          <select value={userFilter} onChange={(e) => setUserFilter(e.target.value)} data-testid="journal-filter-user"
            className="h-9 rounded-lg border border-slate-300 bg-white px-3 text-sm text-slate-700 focus:border-[#22C55E] focus:outline-none">
            <option value="">{t("Tous les utilisateurs")}</option>
            {userOptions.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          <button onClick={exportCsv} disabled={!filtered.length} data-testid="journal-export-csv"
            className="inline-flex h-9 items-center gap-2 rounded-lg bg-[#22C55E] px-3 text-sm font-600 text-white transition-colors hover:bg-[#22C55E]/90 disabled:cursor-not-allowed disabled:opacity-40">
            <Download size={15} /> {t("Exporter")}
          </button>
        </div>
      </div>
      <div className="card overflow-hidden">
        {filtered.length === 0 && <p className="p-8 text-center text-sm text-slate-500">{t("Aucune activité pour le moment.")}</p>}
        <ul>
          {filtered.map((e) => {
            const st = ACTION_STYLE[e.action] || { bg: "#e2e8f0", color: "#475569", icon: ScrollText };
            const Icon = st.icon;
            return (
              <li key={e.id} className="flex items-start gap-4 border-b border-slate-100 px-5 py-3.5 last:border-0" data-testid="journal-entry">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg" style={{ background: st.bg, color: st.color }}>
                  <Icon size={16} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm">
                    <span className="font-700" style={{ color: st.color }}>{t(e.action)}</span>
                    <span className="text-slate-500"> · {t(e.entity)}</span>
                    <span className="font-600"> — {e.label}</span>
                  </p>
                  {Array.isArray(e.changes) && e.changes.length > 0 && (
                    <ul className="mt-1.5 flex flex-col gap-1" data-testid="journal-changes">
                      {e.changes.map((c, i) => (
                        <li key={i} className="flex flex-wrap items-center gap-1.5 text-[11px]">
                          <span className="font-600 text-slate-500">{c.label} :</span>
                          <span className="rounded bg-red-50 px-1.5 py-0.5 font-mono-data text-red-600 line-through decoration-red-300">{c.old}</span>
                          <span className="text-slate-400">→</span>
                          <span className="rounded bg-emerald-50 px-1.5 py-0.5 font-mono-data font-600 text-emerald-700">{c.new}</span>
                        </li>
                      ))}
                    </ul>
                  )}
                  <div className="mt-1 flex items-center gap-1.5">
                    <UserAvatar name={e.user_name || e.user_email} showPhoto={false} size={18} />
                    <p className="text-[11px] text-slate-400">{e.user_name || e.user_email}</p>
                  </div>
                </div>
                <span className="shrink-0 font-mono-data text-xs text-slate-400">{fmtDate(e.timestamp)}</span>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
