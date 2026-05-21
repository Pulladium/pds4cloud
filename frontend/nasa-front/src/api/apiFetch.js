let authClient = null;

export function setApiAuthClient(client) {
  authClient = client;
}

export async function apiFetch(input, init = {}) {
  const headers = new Headers(init.headers ?? {});

  if (authClient?.authenticated) {
    if (authClient.isTokenExpired?.(30)) {
      await authClient.updateToken(30);
    }
    headers.set("Authorization", `Bearer ${authClient.token}`);
  }

  return fetch(input, { ...init, headers });
}
