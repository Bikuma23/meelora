import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useLang } from "../context/LanguageContext";
import { ScrollText, Plus, Pencil, Trash2 } from "lucide-react";

const ACTION_STYLE = {
  "Créer": { bg: "#F8A9421a", color: "#0E9488", icon: Plus },
  "Modifier": { bg: "#0630441a", color: "#063044", icon: Pencil },
  "Supprimer": { bg: "#EF44441a", color: "#EF4444", icon: Trash2 },
};

export default function Journal() {
  const { t, lang } = useLang();
  const [entries, setEntries] = useState(null);
  useEffect(() => { api.getJournal().then(setEntries); }, []);
  const fmtDate = (iso) => {
    try { return new Date(iso).toLocaleString(lang === "en" ? "en-CA" : "fr-CA", { dateStyle: "medium", timeStyle: "short" }); }
    catch { return iso; }
  };
  if (!entries) return <p className="font-mono-data text-sm text-slate-500">{t("Chargement…")}</p>;

  return (
    <div className="space-y-4" data-testid="journal-page">
      <p className="text-sm text-slate-500"><b className="text-slate-800">{entries.length}</b> {t("modification(s) enregistrée(s)")}</p>
      <div className="card overflow-hidden">
        {entries.length === 0 && <p className="p-8 text-center text-sm text-slate-500">{t("Aucune activité pour le moment.")}</p>}
        <ul>
          {entries.map((e) => {
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
                  <p className="mt-0.5 text-[11px] text-slate-400">{e.user_name || e.user_email}</p>
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
