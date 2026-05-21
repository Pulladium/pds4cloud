# PDS4Cloud Frontend

React/Vite frontend for PDS4Cloud. The app provides authenticated project management, Mastcam-Z product discovery, job submission/progress, published projects, vector search, LangSmith status, and admin views.

## Commands

```bash
npm install
npm run dev
npm run build
npm run lint
```

The production Docker image builds the Vite app and serves it through Nginx.

## PDS4 page index

The discovery UI uses `public/pds4-page-index.json`. Regenerate it when the product-page source changes:

```bash
npm run build:pds4-page-index
```

## Local Keycloak CORS

The frontend uses `http://localhost:8484/realms/pds4cloud` with the client
`react-client-certedu-api`. If login redirects back successfully but the browser
blocks `.../protocol/openid-connect/token` with a missing
`Access-Control-Allow-Origin` header, update that Keycloak client:

- Valid redirect URIs: `http://localhost:5173/*`
- Web origins: `http://localhost:5173`

For another Vite port, use that exact origin instead. Restart the frontend after
changing the Keycloak client settings.
