import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../lib/api";
import { getToken } from "../lib/token";
import { EN } from "../lib/i18n";

const LanguageContext = createContext(null);
export const useLang = () => useContext(LanguageContext);

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => localStorage.getItem("lang") || "fr");

  useEffect(() => {
    if (getToken()) {
      api.getPreferences().then((p) => {
        if (p?.language) { setLangState(p.language); localStorage.setItem("lang", p.language); }
      }).catch(() => {});
    }
  }, []);

  const setLang = (l) => {
    setLangState(l);
    localStorage.setItem("lang", l);
    if (getToken()) api.updatePreferences({ language: l }).catch(() => {});
  };

  // Only FR and EN are fully translated. DE/IT are selectable but fall back to FR.
  const t = (key) => (lang === "en" ? (EN[key] ?? key) : key);

  return <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>;
}
