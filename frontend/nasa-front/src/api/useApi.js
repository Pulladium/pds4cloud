import axios from "axios";
import { useMemo } from "react";
import { useKeycloak } from "../context/KeycloakContext";
import { gatewayUrl } from "./gatewayUrl.js";

export function useApi() {
  const { keycloak, initialized } = useKeycloak();

  return useMemo(() => {
    const api = axios.create({
      baseURL: gatewayUrl(),
      headers: { "Content-Type": "application/json" },
    });

    api.interceptors.request.use(async (config) => {
      if (initialized && keycloak?.authenticated) {
        if (keycloak.isTokenExpired(30)) {
          await keycloak.updateToken(30);
        }
        config.headers.Authorization = `Bearer ${keycloak.token}`;
      }
      return config;
    });

    api.interceptors.response.use(
      (res) => res,
      (error) => Promise.reject(error)
    );

    return api;
  }, [initialized, keycloak]);
}
