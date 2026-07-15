import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../lib/api";
import { EN } from "../lib/i18n";

const LanguageContext = createContext(null);
export const useLang = () => useContext(LanguageContext);

export function LanguageProvider({ children }) {
  const [lang, setLangState] = useState(() => localStorage.getItem("lang") || "fr");

  useEffect(() => {
    if (localStorage.getItem("token")) {
      api.getPreferences().then((p) => {
        if (p?.language) { setLangState(p.language); localStorage.setItem("lang", p.language); }
      }).catch(() => {});
    }
  }, []);

  const setLang = (l) => {
    setLangState(l);
    localStorage.setItem("lang", l);
    if (localStorage.getItem("token")) api.updatePreferences({ language: l }).catch(() => {});
  };

  const t = (key) => (lang === "en" ? (EN[key] ?? key) : key);

  return <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>;
}
