import { createContext, useContext, useEffect, useRef, useState } from "react";
import { createKeycloak } from "../config/keycloak.js";
import { setApiAuthClient } from "../api/apiFetch.js";

const KeycloakContext = createContext({ keycloak: null, initialized: false });

export function KeycloakProvider({ children }) {
  const ref = useRef(null);
  const [state, setState] = useState({ keycloak: null, initialized: false });

  useEffect(() => {
    if (ref.current) return;

    const kc = createKeycloak();
    ref.current = kc;
    setApiAuthClient(kc);

    const refresh = () => setState({ keycloak: kc, initialized: true });

    kc.onAuthSuccess = refresh;
    kc.onAuthLogout = refresh;
    kc.onAuthRefreshSuccess = refresh;

    kc.init({ onLoad: "check-sso", pkceMethod: "S256" })
      .then(() => setState({ keycloak: kc, initialized: true }))
      .catch(() => setState({ keycloak: kc, initialized: true }));
  }, []);

  return (
    <KeycloakContext.Provider value={state}>
      {children}
    </KeycloakContext.Provider>
  );
}

export function useKeycloak() {
  return useContext(KeycloakContext);
}
