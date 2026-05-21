# Frontend

The browser client lives in `frontend/nasa-front`. It is a React, Vite, MUI, and Keycloak application served by Nginx in Docker Compose.

## Run with the full stack

From the repository root:

```bash
docker compose --profile eval up -d --build
```

The frontend is exposed on:

```text
http://localhost:8088
```

## Local development

```bash
cd frontend/nasa-front
npm install
npm run dev
```

Vite serves the app on `http://localhost:5173` unless the port is already in use.
