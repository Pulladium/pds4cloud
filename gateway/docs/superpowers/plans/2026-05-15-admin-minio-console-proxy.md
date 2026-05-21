# Admin MinIO Console Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Spring Gateway admin-only proxy for the MinIO dashboard while keeping MinIO `9001` unpublished by default.

**Architecture:** Gateway remains the authorization boundary. It exposes `/api/admin/minio/**`, checks Keycloak `ADMIN` role with `@PreAuthorize`, strips that prefix, and proxies to configurable upstream `http://minio:9001`. Docker Compose keeps MinIO console internal; object downloads through `/mars2020/` remain unchanged.

**Tech Stack:** Spring Boot, Spring Security method authorization, RestTemplate, JUnit 5, Mockito, AssertJ, Docker Compose YAML.

---

## File Structure

- `src/main/java/com/mars/gateway/proxy/GatewayProxyController.java`
  - Add the admin-only MinIO console proxy route.
  - Reuse existing proxy helper, header filtering, and identity-header stripping.
- `src/main/resources/application.yml`
  - Add `proxy.minio-console-base-url` defaulting to `${PROXY_MINIO_CONSOLE_BASE_URL:http://minio:9001}`.
- `src/test/java/com/mars/gateway/proxy/GatewayProxyControllerTest.java`
  - Extend existing controller tests for admin annotation, prefix stripping, configured upstream URL, and identity-header filtering.
- `src/test/java/com/mars/gateway/proxy/DockerComposeMinioExposureTest.java`
  - Add a static compose check that default `docker-compose.yml` does not publish MinIO `9001`.
- `/home/pallad/Backbackup/Backup2/docker-compose.yml`
  - No expected change unless a test reveals `9001` is published. It should remain unpublished.

---

### Task 1: Gateway Admin MinIO Proxy Route

**Files:**
- Modify: `src/test/java/com/mars/gateway/proxy/GatewayProxyControllerTest.java`
- Modify: `src/main/java/com/mars/gateway/proxy/GatewayProxyController.java`
- Modify: `src/main/resources/application.yml`

- [ ] **Step 1: Add failing authorization and proxy tests**

In `src/test/java/com/mars/gateway/proxy/GatewayProxyControllerTest.java`, update `adminRoutesRequireAdmin()` and add two tests:

```java
@Test
void adminRoutesRequireAdmin() throws Exception {
    assertThat(preAuthorize("proxyLangSmith").value()).isEqualTo("hasRole('ADMIN')");
    assertThat(preAuthorize("proxyMinioConsole").value()).isEqualTo("hasRole('ADMIN')");
}

@Test
void minioConsoleProxyStripsAdminPrefixAndUsesConfiguredUpstream() {
    RestTemplate restTemplate = mock(RestTemplate.class);
    GatewayProxyController controller = controllerWith(restTemplate);
    when(restTemplate.exchange(
            eq(URI.create("http://minio-console/api/v1/session?x=1")),
            eq(HttpMethod.GET),
            org.mockito.ArgumentMatchers.<HttpEntity<?>>any(),
            eq(byte[].class)
    )).thenReturn(ResponseEntity.ok(new byte[0]));

    MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/admin/minio/api/v1/session");
    request.setQueryString("x=1");
    request.setUserPrincipal((Principal) () -> "admin-user-1");

    controller.proxyMinioConsole(request, null);

    verify(restTemplate).exchange(
            eq(URI.create("http://minio-console/api/v1/session?x=1")),
            eq(HttpMethod.GET),
            org.mockito.ArgumentMatchers.<HttpEntity<?>>any(),
            eq(byte[].class)
    );
}

@Test
void minioConsoleProxyFiltersTrustedIdentityHeaders() {
    RestTemplate restTemplate = mock(RestTemplate.class);
    GatewayProxyController controller = controllerWith(restTemplate);
    when(restTemplate.exchange(
            eq(URI.create("http://minio-console/")),
            eq(HttpMethod.GET),
            org.mockito.ArgumentMatchers.<HttpEntity<?>>any(),
            eq(byte[].class)
    )).thenReturn(ResponseEntity.ok(new byte[0]));

    MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/admin/minio/");
    request.addHeader("X-User-Id", "spoofed-user");
    request.addHeader("X-User-Roles", "ADMIN");
    request.addHeader("X-Username", "spoofed-username");
    request.setUserPrincipal((Principal) () -> "admin-user-1");

    controller.proxyMinioConsole(request, null);

    HttpHeaders capturedHeaders = capturedHeaders(restTemplate, URI.create("http://minio-console/"));
    assertThat(capturedHeaders.getFirst("X-User-Id")).isEqualTo("admin-user-1");
    assertThat(capturedHeaders.containsKey("X-User-Roles")).isFalse();
    assertThat(capturedHeaders.containsKey("X-Username")).isFalse();
}
```

Update the helper to set the MinIO upstream:

```java
private GatewayProxyController controllerWith(RestTemplate restTemplate) {
    GatewayProxyController controller = new GatewayProxyController(mock(PublishedProjectEnricher.class));
    ReflectionTestUtils.setField(controller, "restTemplate", restTemplate);
    ReflectionTestUtils.setField(controller, "orchtrBaseUrl", "http://orchestrator");
    ReflectionTestUtils.setField(controller, "pdsBaseUrl", "http://pds");
    ReflectionTestUtils.setField(controller, "minioConsoleBaseUrl", "http://minio-console");
    return controller;
}
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
mvn -q -Dtest=GatewayProxyControllerTest test
```

Expected: FAIL because `proxyMinioConsole` and `minioConsoleBaseUrl` do not exist yet.

- [ ] **Step 3: Add MinIO console upstream configuration**

In `src/main/resources/application.yml`, add:

```yaml
proxy:
  minio-console-base-url: ${PROXY_MINIO_CONSOLE_BASE_URL:http://minio:9001}
```

In `src/main/java/com/mars/gateway/proxy/GatewayProxyController.java`, add:

```java
@Value("${proxy.minio-console-base-url:http://minio:9001}")
private String minioConsoleBaseUrl;
```

- [ ] **Step 4: Add the admin-only route**

In `src/main/java/com/mars/gateway/proxy/GatewayProxyController.java`, add near the other admin routes:

```java
@RequestMapping("/api/admin/minio/**")
@PreAuthorize("hasRole('ADMIN')")
public ResponseEntity<byte[]> proxyMinioConsole(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
    return proxy(request, body, minioConsoleBaseUrl, "/api/admin/minio");
}
```

This reuses the existing `proxy()` path, which strips hop-by-hop headers and browser-supplied trusted identity headers, then injects the authenticated principal as `X-User-Id`.

- [ ] **Step 5: Run route tests**

Run:

```bash
mvn -q -Dtest=GatewayProxyControllerTest test
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```bash
git add src/main/java/com/mars/gateway/proxy/GatewayProxyController.java src/main/resources/application.yml src/test/java/com/mars/gateway/proxy/GatewayProxyControllerTest.java
git commit -m "feat: proxy minio console for admins"
```

---

### Task 2: Static Compose Exposure Guard

**Files:**
- Create: `src/test/java/com/mars/gateway/proxy/DockerComposeMinioExposureTest.java`
- Inspect: `/home/pallad/Backbackup/Backup2/docker-compose.yml`

- [ ] **Step 1: Add failing/static compose test**

Create `src/test/java/com/mars/gateway/proxy/DockerComposeMinioExposureTest.java`:

```java
package com.mars.gateway.proxy;

import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;

class DockerComposeMinioExposureTest {

    @Test
    void defaultComposeDoesNotPublishMinioConsolePort() throws Exception {
        String compose = Files.readString(Path.of("../docker-compose.yml"));

        assertThat(compose).contains("command: server /data --console-address ':9001'");
        assertThat(compose).doesNotContain("\"9001:9001\"");
        assertThat(compose).doesNotContain("- 9001:9001");
    }
}
```

- [ ] **Step 2: Run static compose test**

Run:

```bash
mvn -q -Dtest=DockerComposeMinioExposureTest test
```

Expected: PASS in the current repository because `9001` is not published. If it fails, remove the default MinIO `9001` port publication from `/home/pallad/Backbackup/Backup2/docker-compose.yml` and rerun.

- [ ] **Step 3: Commit**

Run:

```bash
git add src/test/java/com/mars/gateway/proxy/DockerComposeMinioExposureTest.java
git commit -m "test: guard minio console exposure"
```

---

### Task 3: Focused Verification

**Files:**
- Verify: `src/main/java/com/mars/gateway/proxy/GatewayProxyController.java`
- Verify: `src/main/resources/application.yml`
- Verify: `src/test/java/com/mars/gateway/proxy/GatewayProxyControllerTest.java`
- Verify: `src/test/java/com/mars/gateway/proxy/DockerComposeMinioExposureTest.java`

- [ ] **Step 1: Run focused gateway tests**

Run:

```bash
mvn -q -Dtest=GatewayProxyControllerTest,DockerComposeMinioExposureTest test
```

Expected: PASS.

- [ ] **Step 2: Check route/security requirements manually**

Run:

```bash
grep -R "proxyMinioConsole\\|minio-console-base-url\\|9001:9001" -n src/main src/test ../docker-compose.yml
```

Expected:

- `proxyMinioConsole` has `@PreAuthorize("hasRole('ADMIN')")`.
- `minio-console-base-url` defaults to `http://minio:9001`.
- No `9001:9001` mapping appears in `../docker-compose.yml`.

- [ ] **Step 3: Check git status**

Run:

```bash
git status --short
```

Expected: clean gateway repo.
