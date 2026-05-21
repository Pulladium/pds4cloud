# Keycloak Auth Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up Keycloak in Docker, add a secured ping/pong endpoint to the Spring Boot backend, and wire real login/logout/register into the React frontend.

**Architecture:** Three independent layers executed in order: (1) Docker spins up Keycloak + PostgreSQL; (2) Spring Boot adds Spring Security OAuth2 resource server with a `security.skip-auth` toggle; (3) React wraps the app in `ReactKeycloakProvider` and removes the hardcoded mock auth.

**Tech Stack:** Docker Compose, Keycloak 23.0.6, Spring Boot 4.0.1 (Spring Security + OAuth2 Resource Server), React 19 + keycloak-js v26 + @react-keycloak/web v3.4.0

---

## File Map

### New files
- `mars100-backend/docker/docker-compose.yml` — Keycloak + PostgreSQL services
- `mars100-backend/docker/keycloak-realm-configuration.json` — realm export (downloaded from EdCertificationSystem)
- `mars100-backend/src/main/java/.../PingController.java` — GET /api/ping → "pong"
- `mars100-backend/src/main/java/.../SecurityConfig.java` — OAuth2 resource server, skip-auth toggle
- `mars100-backend/src/main/resources/application-dev.properties` — `security.skip-auth=true`
- `frontend/nasa-front/src/config/keycloak.js` — Keycloak instance config

### Modified files
- `mars100-backend/pom.xml` — add spring-boot-starter-security + spring-boot-starter-oauth2-resource-server
- `mars100-backend/src/main/resources/application.properties` — add JWT issuer URI + skip-auth=false
- `frontend/nasa-front/src/main.jsx` — wrap App in ReactKeycloakProvider
- `frontend/nasa-front/src/Component/UserAppBar.jsx` — remove hardcoded mock, use useKeycloak() hook

---

## Task 1: Docker — Keycloak + PostgreSQL

**Files:**
- Create: `mars100-backend/docker/docker-compose.yml`
- Create: `mars100-backend/docker/keycloak-realm-configuration.json`

- [ ] **Step 1: Create the docker directory**

```bash
mkdir -p /home/pallad/JavaProjects/mars100-backend/docker
cd /home/pallad/JavaProjects/mars100-backend/docker
```

- [ ] **Step 2: Write docker-compose.yml** (MongoDB removed — not needed here)

Create `/home/pallad/JavaProjects/mars100-backend/docker/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:16.2-alpine
    container_name: keycloak_postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: keycloak
      POSTGRES_USER: keycloak
      POSTGRES_PASSWORD: keycloak_password
    networks:
      - keycloak_network

  keycloak:
    image: quay.io/keycloak/keycloak:23.0.6
    container_name: keycloak
    command: start
    environment:
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://postgres:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD: keycloak_password
      KC_HOSTNAME: localhost
      KC_HTTP_PORT: 8080
      KC_HOSTNAME_PORT: 8484
      KC_HTTP_ENABLED: "true"
      KC_HOSTNAME_STRICT_HTTPS: "false"
      KC_HEALTH_ENABLED: "true"
      KEYCLOAK_ADMIN: admin
      KEYCLOAK_ADMIN_PASSWORD: admin_password
    ports:
      - "8484:8080"
    depends_on:
      - postgres
    networks:
      - keycloak_network

volumes:
  postgres_data:

networks:
  keycloak_network:
    driver: bridge
```

- [ ] **Step 3: Download the realm export**

```bash
curl -L \
  https://raw.githubusercontent.com/Pulladium/EdCertificationSystem/master/keycloak-realm-configuration.json \
  -o /home/pallad/JavaProjects/mars100-backend/docker/keycloak-realm-configuration.json
```

Expected: file created, ~78 KB, starts with `{"id":"CertEdu"...`

- [ ] **Step 4: Start Keycloak**

```bash
cd /home/pallad/JavaProjects/mars100-backend/docker
docker compose up -d
```

Expected output ends with:
```
✔ Container keycloak_postgres  Started
✔ Container keycloak           Started
```

- [ ] **Step 5: Wait for Keycloak to be healthy (~30–60 s)**

```bash
docker compose logs -f keycloak | grep -m1 "Running the server"
```

Expected line: `Running the server in production mode. ...`
Press Ctrl+C after it appears.

- [ ] **Step 6: Import the realm via Keycloak Admin REST API**

```bash
# Get admin token
TOKEN=$(curl -s -X POST http://localhost:8484/realms/master/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password&client_id=admin-cli&username=admin&password=admin_password" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Import realm
curl -s -X POST http://localhost:8484/admin/realms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @/home/pallad/JavaProjects/mars100-backend/docker/keycloak-realm-configuration.json \
  -w "\nHTTP %{http_code}\n"
```

Expected: `HTTP 201`

- [ ] **Step 7: Add localhost:5173 as valid redirect URI for the React client**

Open http://localhost:8484 in a browser.
- Login: admin / admin_password
- Navigate to: Realm `CertEdu` → Clients → `react-client-certedu-api` → Settings
- Under **Valid redirect URIs** add: `http://localhost:5173/*`
- Under **Web origins** add: `http://localhost:5173`
- Click Save

- [ ] **Step 8: Create a test user**

In Keycloak admin:
- Navigate to: Realm `CertEdu` → Users → Add user
- Username: `testuser`, Email verified: ON → Save
- Credentials tab → Set password: `testpass`, Temporary: OFF → Save

- [ ] **Step 9: Commit**

```bash
cd /home/pallad/JavaProjects/mars100-backend
git add docker/
git commit -m "feat: add Keycloak + PostgreSQL docker compose"
```

---

## Task 2: Backend — Ping/Pong + Spring Security

**Files:**
- Modify: `mars100-backend/pom.xml`
- Create: `mars100-backend/src/main/java/cz/cvut/fel/sit/av/mars100backend/PingController.java`
- Create: `mars100-backend/src/main/java/cz/cvut/fel/sit/av/mars100backend/SecurityConfig.java`
- Modify: `mars100-backend/src/main/resources/application.properties`
- Create: `mars100-backend/src/main/resources/application-dev.properties`

- [ ] **Step 1: Add Security dependencies to pom.xml**

In `/home/pallad/JavaProjects/mars100-backend/pom.xml`, add inside `<dependencies>`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

- [ ] **Step 2: Create PingController**

Create `/home/pallad/JavaProjects/mars100-backend/src/main/java/cz/cvut/fel/sit/av/mars100backend/PingController.java`:

```java
package cz.cvut.fel.sit.av.mars100backend;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
```

- [ ] **Step 3: Create SecurityConfig**

Create `/home/pallad/JavaProjects/mars100-backend/src/main/java/cz/cvut/fel/sit/av/mars100backend/SecurityConfig.java`:

```java
package cz.cvut.fel.sit.av.mars100backend;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Value("${security.skip-auth:false}")
    private boolean skipAuth;

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        if (skipAuth) {
            http
                .authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
                .csrf(csrf -> csrf.disable());
            return http.build();
        }

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/ping").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .csrf(csrf -> csrf.disable());

        return http.build();
    }
}
```

- [ ] **Step 4: Add security properties to application.properties**

Append to `/home/pallad/JavaProjects/mars100-backend/src/main/resources/application.properties`:

```properties
# --- Security ---
security.skip-auth=false
spring.security.oauth2.resourceserver.jwt.issuer-uri=http://localhost:8484/realms/CertEdu
```

- [ ] **Step 5: Create application-dev.properties**

Create `/home/pallad/JavaProjects/mars100-backend/src/main/resources/application-dev.properties`:

```properties
# Dev mode — skip JWT validation entirely
security.skip-auth=true
```

To activate dev profile: add `--spring.profiles.active=dev` to JVM args or set env `SPRING_PROFILES_ACTIVE=dev`.

- [ ] **Step 6: Build and verify**

```bash
cd /home/pallad/JavaProjects/mars100-backend
./mvnw clean package -DskipTests -q
```

Expected: `BUILD SUCCESS`

- [ ] **Step 7: Test ping is public**

Start the app (with Keycloak running from Task 1):
```bash
./mvnw spring-boot:run &
sleep 10
curl -s http://localhost:8080/api/ping
```

Expected: `pong`

- [ ] **Step 8: Test that other endpoints require auth**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/photos
```

Expected: `401`

- [ ] **Step 9: Test skip-auth dev mode**

```bash
# Kill running app first, then:
SPRING_PROFILES_ACTIVE=dev ./mvnw spring-boot:run &
sleep 10
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/photos
```

Expected: `200` (no token needed)

- [ ] **Step 10: Commit**

```bash
cd /home/pallad/JavaProjects/mars100-backend
git add pom.xml \
  src/main/java/cz/cvut/fel/sit/av/mars100backend/PingController.java \
  src/main/java/cz/cvut/fel/sit/av/mars100backend/SecurityConfig.java \
  src/main/resources/application.properties \
  src/main/resources/application-dev.properties
git commit -m "feat: add ping/pong endpoint and Keycloak JWT security with skip-auth toggle"
```

---

## Task 3: Frontend — Real Keycloak Auth

**Files:**
- Create: `frontend/nasa-front/src/config/keycloak.js`
- Modify: `frontend/nasa-front/src/main.jsx`
- Modify: `frontend/nasa-front/src/Component/UserAppBar.jsx`

- [ ] **Step 1: Install Keycloak packages**

```bash
cd /home/pallad/BachelorProj/frontend/nasa-front
npm install keycloak-js@26.0.7 @react-keycloak/web@3.4.0 --legacy-peer-deps
```

Expected: both packages appear in `node_modules/`, no fatal errors.

- [ ] **Step 2: Create keycloak.js config**

Create `/home/pallad/BachelorProj/frontend/nasa-front/src/config/keycloak.js`:

```js
import Keycloak from "keycloak-js";

const keycloak = new Keycloak({
  url: "http://localhost:8484",
  realm: "CertEdu",
  clientId: "react-client-certedu-api",
});

export default keycloak;
```

- [ ] **Step 3: Update main.jsx to wrap app in ReactKeycloakProvider**

Replace `/home/pallad/BachelorProj/frontend/nasa-front/src/main.jsx` with:

```jsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { ReactKeycloakProvider } from '@react-keycloak/web';
import keycloak from './config/keycloak.js';

const theme = createTheme({
  palette: {
    primary: {
      main: '#d84315',
      light: '#ff7043',
      dark: '#bf360c',
      contrastText: '#ffffff',
    },
    mode: 'dark',
  },
});

const initOptions = {
  onLoad: 'check-sso',
  checkLoginIframe: true,
  pkceMethod: 'S256',
};

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ReactKeycloakProvider authClient={keycloak} initOptions={initOptions}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <App />
      </ThemeProvider>
    </ReactKeycloakProvider>
  </StrictMode>,
);
```

- [ ] **Step 4: Fix UserAppBar — remove mock, use useKeycloak hook**

Replace `/home/pallad/BachelorProj/frontend/nasa-front/src/Component/UserAppBar.jsx` with:

```jsx
import Box from '@mui/material/Box';
import AppBar from '@mui/material/AppBar';
import Toolbar from '@mui/material/Toolbar';
import IconButton from '@mui/material/IconButton';
import Typography from '@mui/material/Typography';
import Button from '@mui/material/Button';
import { styled } from '@mui/material/styles';
import MarsIcon from '../assets/Mars100-icon2.svg?react';
import AIControlPanelTabs from './AIControlPanelTabs';
import { useLocation, useNavigate } from 'react-router-dom';
import { useMediaQuery } from '@mui/material';
import { useKeycloak } from '@react-keycloak/web';

const SpaceAppBar = styled(AppBar)(({ theme }) => ({
  backgroundColor: 'rgba(0, 0, 0, 0.67)',
  boxShadow: 'none',
  backdropFilter: 'blur(10px)',
  position: 'sticky',
  top: 0,
  left: 0,
  right: 0,
  zIndex: 1000,
}));

export default function UserAppBar() {
  const location = useLocation();
  const isMobile = useMediaQuery((theme) => theme.breakpoints.down('sm'));
  const navigate = useNavigate();
  const { keycloak, initialized } = useKeycloak();

  const handleLogoClick = () => {
    navigate('/');
  };

  return (
    <Box sx={{ maxWidth: 1495, mx: 'auto' }}>
      <SpaceAppBar>
        <Toolbar sx={{ justifyContent: isMobile ? 'space-between' : 'flex', width: '100%' }}>
          <IconButton
            onClick={handleLogoClick}
            sx={{ width: '5vh', height: '5vh', p: 0 }}
          >
            <MarsIcon style={{ width: '100%', height: '100%' }} />
          </IconButton>

          {(
            location.pathname === '/missions' ||
            location.pathname === '/analysis' ||
            location.pathname === '/settings' ||
            location.pathname === '/gallery' ||
            location.pathname.startsWith('/discover') ||
            location.pathname.startsWith('/my-projects') ||
            location.pathname.startsWith('/admin')
          ) && (
            <Box sx={{ width: '100%', display: 'flex', justifyContent: 'center', ml: isMobile ? 0 : 2 }}>
              <AIControlPanelTabs currentTab={0} />
            </Box>
          )}

          {initialized && !keycloak.authenticated && (
            <Box sx={{ ml: 'auto', display: 'flex', gap: 1 }}>
              <Button color="inherit" onClick={() => keycloak.login()}>
                Login
              </Button>
              <Button color="inherit" onClick={() => keycloak.register()}>
                Register
              </Button>
            </Box>
          )}

          {initialized && keycloak.authenticated && (
            <Button color="inherit" onClick={() => keycloak.logout()}>
              Logout
            </Button>
          )}
        </Toolbar>
      </SpaceAppBar>
    </Box>
  );
}
```

- [ ] **Step 5: Start dev server and verify**

```bash
cd /home/pallad/BachelorProj/frontend/nasa-front
npm run dev
```

Open http://localhost:5173 in a browser.

Expected:
- Page loads normally (no white screen, no JS errors in console)
- AppBar shows **Login** and **Register** buttons (not Logout) — because no session yet
- Clicking **Login** redirects to `http://localhost:8484/realms/CertEdu/...` login page
- Enter `testuser` / `testpass` → redirects back to `http://localhost:5173/`
- AppBar now shows **Logout**
- Clicking **Logout** ends the session and Login/Register appear again

- [ ] **Step 6: Commit**

```bash
cd /home/pallad/BachelorProj/frontend/nasa-front
git add src/config/keycloak.js src/main.jsx src/Component/UserAppBar.jsx package.json package-lock.json
git commit -m "feat: integrate Keycloak login/logout/register via react-keycloak/web"
```

---

## Manual Keycloak Setup Reminder (one-time, after Task 1 Step 6)

After importing the realm, verify in Keycloak Admin (http://localhost:8484):
- Realm: **CertEdu** exists
- Client `react-client-certedu-api` → Valid redirect URIs contains `http://localhost:5173/*`
- Client `react-client-certedu-api` → Web origins contains `http://localhost:5173`
- At least one user exists with a non-temporary password
