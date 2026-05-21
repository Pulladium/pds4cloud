export function gatewayUrl(path = "") {
  const base = import.meta.env.PROD ? "" : (import.meta.env.VITE_GATEWAY_URL ?? "");
  return `${base}${path}`;
}
