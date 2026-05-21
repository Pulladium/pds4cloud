# Admin MinIO Console Proxy Design

## Goal

Only Keycloak users with the `admin` role may access the MinIO dashboard. The MinIO console port must not be published directly to the host or exposed through nginx without server-side authorization.

## Current Context

- MinIO runs in Docker as `pds4-minio`.
- MinIO API/object traffic uses port `9000`.
- MinIO console runs internally on port `9001` via `server /data --console-address ':9001'`.
- `docker-compose.yml` currently does not publish MinIO ports.
- Frontend nginx proxies `/mars2020/` to MinIO `9000` for object downloads.
- Spring Gateway is the trusted authorization boundary. It validates Keycloak JWTs and maps roles for `@PreAuthorize`.

## Design

Add an admin-only Spring Gateway proxy for the MinIO console.

The route will be:

```text
/api/admin/minio/**
```

Gateway will protect the route with:

```java
@PreAuthorize("hasRole('ADMIN')")
```

Gateway will proxy requests to:

```text
http://minio:9001
```

The MinIO console itself will still require MinIO credentials. The gateway admin check is an outer access gate; it does not replace MinIO authentication.

## Compose Exposure

Do not publish MinIO `9001` to the host in the default compose file.

This is allowed:

```yaml
minio:
  command: server /data --console-address ':9001'
```

This is not allowed in the default compose file:

```yaml
ports:
  - "9001:9001"
```

Object download proxying through `/mars2020/` remains unchanged.

## Gateway Behavior

Gateway gets a new configurable base URL:

```yaml
proxy:
  minio-console-base-url: ${PROXY_MINIO_CONSOLE_BASE_URL:http://minio:9001}
```

Requests to `/api/admin/minio/**` are proxied to MinIO console with the `/api/admin/minio` prefix stripped.

Examples:

```text
GET /api/admin/minio/      -> GET http://minio:9001/
GET /api/admin/minio/api/v1/session -> GET http://minio:9001/api/v1/session
```

Gateway must continue stripping browser-supplied trusted identity headers before proxying.

## Limitations

MinIO console is a browser application. It may use redirects, cookies, websocket requests, and absolute paths. The first implementation should support normal HTTP proxying and tests should cover authorization and prefix stripping. If MinIO emits absolute paths that do not work behind `/api/admin/minio`, follow-up work may add header/path rewriting or move the console to an admin-only dedicated host.

## Tests

Gateway tests should verify:

- Non-admin authenticated users cannot access `/api/admin/minio/**`.
- Admin users can access `/api/admin/minio/**`.
- Gateway strips `/api/admin/minio` before forwarding to MinIO.
- Browser-supplied trusted identity headers are not forwarded to MinIO.

Compose/config tests or static checks should verify:

- MinIO `9001` is not published in the default compose file.
- The configured MinIO console upstream defaults to `http://minio:9001`.

## Out Of Scope

- Replacing MinIO login with Keycloak SSO.
- Adding MinIO users or policies.
- Publishing `9001` directly for public access.
- Changing `/mars2020/` object download behavior.
