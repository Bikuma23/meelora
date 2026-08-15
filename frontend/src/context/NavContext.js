import { createContext, useContext } from "react";

// P1.13E — shared navigation actions (Client -> Mandat -> Modules).
export const NavContext = createContext({
  go: () => {},
  enterMandat: () => {},
  enterCompanyContext: () => {},
  activeCompanyId: null,
  companies: [],
});

export const useNav = () => useContext(NavContext);
