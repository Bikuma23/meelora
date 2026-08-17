import { createContext, useContext, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

// Extensible nav-badge registry. Add one entry per module that can surface a
// discrete "unseen items" indicator in the sidebar. Each source declares:
//   key     — the nav item key it decorates (root module + sub-item can share it)
//   module  — module_code that must be accessible (server still enforces auth)
//   fetchItems(cid) — returns an array of stable ids of currently actionable items
// The badge count = number of ids the user has NOT yet acknowledged. No financial
// data ever leaves fetchItems as anything other than opaque ids.
export const NAV_BADGE_SOURCES = [
  {
    key: "acct_purchases",
    module: "ACCOUNTING",
    fetchItems: async (cid) => {
      const d = await api.apOverview(cid, {});
      return d.actionable_ids || (d.priorities || []).map((p) => p.id);
    },
  },
];

const NavBadgeContext = createContext({
  counts: {}, acknowledge: () => {}, acknowledgeWith: () => {}, refresh: () => {},
});
export const useNavBadges = () => useContext(NavBadgeContext);

const seenStorageKey = (key, cid) => `navbadge:${key}:${cid}`;
const loadSeen = (key, cid) => {
  try { return new Set(JSON.parse(localStorage.getItem(seenStorageKey(key, cid)) || "[]")); }
  catch { return new Set(); }
};
const saveSeen = (key, cid, set) => {
  try { localStorage.setItem(seenStorageKey(key, cid), JSON.stringify([...set])); } catch { /* ignore */ }
};

export function NavBadgeProvider({ companyId, moduleCodes, children }) {
  const [counts, setCounts] = useState({});
  const itemsRef = useRef({});     // key -> latest [ids]
  const seenRef = useRef({});      // key -> Set(acknowledged ids)
  const pollRef = useRef(null);    // latest poll fn (for external refresh)
  const codesKey = (moduleCodes || []).join(",");

  const recompute = useCallback((key) => {
    const items = itemsRef.current[key] || [];
    const seen = seenRef.current[key] || new Set();
    const unseen = items.filter((id) => !seen.has(id)).length;
    setCounts((c) => (c[key] === unseen ? c : { ...c, [key]: unseen }));
  }, []);

  // Single polling loop, strictly scoped to the active company + accessible
  // modules. Reused across the whole shell (no per-page duplicate poller).
  useEffect(() => {
    if (!companyId) { setCounts({}); return; }
    const sources = NAV_BADGE_SOURCES.filter((s) => (moduleCodes || []).includes(s.module));
    seenRef.current = {};
    sources.forEach((s) => { seenRef.current[s.key] = loadSeen(s.key, companyId); });
    let cancelled = false;
    const poll = async () => {
      for (const s of sources) {
        try {
          const ids = await s.fetchItems(companyId);
          if (cancelled) return;
          itemsRef.current[s.key] = ids;
          recompute(s.key);
        } catch (e) { /* gated by effective rights server-side → leave count as-is */ }
      }
    };
    pollRef.current = poll;
    poll();
    const iv = setInterval(poll, 30000);
    const onVis = () => { if (document.visibilityState === "visible") poll(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { cancelled = true; clearInterval(iv); document.removeEventListener("visibilitychange", onVis); };
  }, [companyId, codesKey, recompute]);

  const acknowledgeWith = useCallback((key, ids) => {
    if (!companyId) return;
    const seen = seenRef.current[key] || new Set();
    (ids || []).forEach((id) => seen.add(id));
    (itemsRef.current[key] || []).forEach((id) => seen.add(id));
    seenRef.current[key] = seen;
    saveSeen(key, companyId, seen);
    recompute(key);
  }, [companyId, recompute]);

  const acknowledge = useCallback((key) => acknowledgeWith(key, itemsRef.current[key] || []), [acknowledgeWith]);
  const refresh = useCallback(() => { pollRef.current && pollRef.current(); }, []);

  return (
    <NavBadgeContext.Provider value={{ counts, acknowledge, acknowledgeWith, refresh }}>
      {children}
    </NavBadgeContext.Provider>
  );
}
