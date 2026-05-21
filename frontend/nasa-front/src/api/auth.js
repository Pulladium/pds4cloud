export function userRoles(keycloak) {
  const realmRoles = [
    ...(keycloak?.realmAccess?.roles ?? []),
    ...(keycloak?.tokenParsed?.realm_access?.roles ?? []),
  ];
  const resourceAccess = {
    ...(keycloak?.resourceAccess ?? {}),
    ...(keycloak?.tokenParsed?.resource_access ?? {}),
  };
  const resourceRoles = Object.values(resourceAccess)
    .flatMap((resource) => resource?.roles ?? []);
  return new Set([...realmRoles, ...resourceRoles].map((role) => String(role).toLowerCase()));
}

export function hasAnyRole(keycloak, roles) {
  const available = userRoles(keycloak);
  return roles.some((role) => available.has(String(role).toLowerCase()));
}

export function isResearcherOrAdmin(keycloak) {
  return hasAnyRole(keycloak, ["researcher", "admin"]);
}

export function isAdmin(keycloak) {
  return hasAnyRole(keycloak, ["admin"]);
}
