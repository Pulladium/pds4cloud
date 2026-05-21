import assert from "node:assert/strict";
import test from "node:test";

import { isAdmin, isResearcherOrAdmin, userRoles } from "../api/auth.js";

test("roles are read from parsed Keycloak token claims", () => {
  const keycloak = {
    tokenParsed: {
      realm_access: {
        roles: ["RESEARCHER", "ADMIN"],
      },
      resource_access: {
        "react-client-certedu-api": {
          roles: ["viewer"],
        },
      },
    },
  };

  assert.deepEqual(userRoles(keycloak), new Set(["researcher", "admin", "viewer"]));
  assert.equal(isAdmin(keycloak), true);
  assert.equal(isResearcherOrAdmin(keycloak), true);
});

test("roles are still read from adapter role fields when present", () => {
  const keycloak = {
    realmAccess: {
      roles: ["ADMIN"],
    },
    resourceAccess: {
      app: {
        roles: ["RESEARCHER"],
      },
    },
  };

  assert.deepEqual(userRoles(keycloak), new Set(["admin", "researcher"]));
  assert.equal(isAdmin(keycloak), true);
});
