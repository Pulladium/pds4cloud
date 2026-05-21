import Keycloak from "keycloak-js";

const keycloakUrl = import.meta.env.VITE_KEYCLOAK_URL
  ?? (import.meta.env.PROD ? window.location.origin : "http://localhost:8484");

export function createKeycloak() {
  return new Keycloak({
    url: keycloakUrl,
    realm: "pds4cloud",
    clientId: "react-client-certedu-api",
  });
}
