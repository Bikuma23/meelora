import { createContext, useContext } from "react";

// P1.13E — shared navigation actions (Client -> Mandat -> Modules).
export const NavContext = createContext({
  go: () => {},
  enterMandat: () => {},
  enterMeelora: () => {},
  activeCompanyId: null,
  meeloraAccessed: false,
  companies: [],
});

export const useNav = () => useContext(NavContext);
