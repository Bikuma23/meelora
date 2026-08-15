import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../lib/api";
import { getToken, setToken, clearToken } from "../lib/token";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null=checking, false=unauth, obj=auth

  useEffect(() => {
    // Emergent Google Auth callback: session_id arrives in the URL fragment.
    // Process it FIRST, exchange it server-side, then clear the fragment.
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS,
    // THIS BREAKS THE AUTH.
    if (window.location.hash && window.location.hash.includes("session_id=")) {
      const sid = new URLSearchParams(window.location.hash.slice(1)).get("session_id");
      const cleanup = () =>
        window.history.replaceState({}, document.title, window.location.pathname + window.location.search);
      if (sid) {
        api
          .googleSession(sid)
          .then((data) => {
            setToken(data.token, true);
            cleanup();
            setUser(data.user);
          })
          .catch(() => {
            cleanup();
            setUser(false);
          });
        return;
      }
      cleanup();
    }
    if (!getToken()) {
      setUser(false);
      return;
    }
    api.me().then(setUser).catch(() => setUser(false));
  }, []);

  const login = async (email, password, remember = true) => {
    const data = await api.login(email, password, remember);
    setToken(data.token, remember);
    setUser(data.user);
  };

  const logout = async () => {
    try { await api.logout(); } catch { /* noop */ }
    clearToken();
    setUser(false);
  };

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}
