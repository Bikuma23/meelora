// Auth token storage with real "remember me" semantics.
// remember=true  -> localStorage (persists across browser restarts)
// remember=false -> sessionStorage (cleared when the tab/browser closes)
const KEY = "token";

export const getToken = () =>
  localStorage.getItem(KEY) || sessionStorage.getItem(KEY) || null;

export const setToken = (token, remember = true) => {
  localStorage.removeItem(KEY);
  sessionStorage.removeItem(KEY);
  (remember ? localStorage : sessionStorage).setItem(KEY, token);
};

export const clearToken = () => {
  localStorage.removeItem(KEY);
  sessionStorage.removeItem(KEY);
};
