package com.mars.gateway.proxy;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.web.client.RestTemplate;

import java.net.URI;
import java.security.Principal;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class GatewayProxyControllerTest {

    @Test
    void discoveryAndVectorSearchArePublicViewerRoutes() throws Exception {
        assertThat(preAuthorize("proxyDiscovery").value()).isEqualTo("permitAll()");
        assertThat(preAuthorize("proxyQdrantSearch").value()).isEqualTo("permitAll()");
        assertThat(preAuthorize("proxyPublishedProjects").value()).isEqualTo("permitAll()");
        assertThat(preAuthorize("proxyGeneratedPreviews").value()).isEqualTo("permitAll()");
    }

    @Test
    void researcherRoutesRequireResearcherOrAdmin() throws Exception {
        assertThat(preAuthorize("proxyProjects").value()).isEqualTo("hasAnyRole('RESEARCHER', 'ADMIN')");
        assertThat(preAuthorize("proxyProjectPublish").value()).isEqualTo("hasAnyRole('RESEARCHER', 'ADMIN')");
        assertThat(preAuthorize("proxyQdrantAdd").value()).isEqualTo("hasAnyRole('RESEARCHER', 'ADMIN')");
        assertThat(preAuthorize("proxyModels").value()).isEqualTo("hasAnyRole('RESEARCHER', 'ADMIN')");
    }

    @Test
    void adminRoutesRequireAdmin() throws Exception {
        assertThat(preAuthorize("proxyLangSmith").value()).isEqualTo("hasRole('ADMIN')");
    }

    @Test
    void proxyInjectsAuthenticatedPrincipalAsUserIdHeader() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        GatewayProxyController controller = controllerWith(restTemplate);
        when(restTemplate.exchange(
                eq(URI.create("http://orchestrator/api/projects")),
                eq(HttpMethod.GET),
                org.mockito.ArgumentMatchers.<HttpEntity<?>>any(),
                eq(byte[].class)
        )).thenReturn(ResponseEntity.ok(new byte[0]));

        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/projects");
        request.addHeader("X-User-Id", "spoofed-user");
        request.addHeader("X-User-Roles", "ADMIN");
        request.addHeader("X-Username", "spoofed-username");
        request.setUserPrincipal((Principal) () -> "keycloak-user-1");

        controller.proxyProjects(request, null);

        ArgumentCaptor<HttpEntity<?>> entityCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(
                eq(URI.create("http://orchestrator/api/projects")),
                eq(HttpMethod.GET),
                entityCaptor.capture(),
                eq(byte[].class)
        );
        HttpHeaders capturedHeaders = entityCaptor.getValue().getHeaders();
        assertThat(capturedHeaders.getFirst("X-User-Id")).isEqualTo("keycloak-user-1");
        assertThat(capturedHeaders.containsKey("X-User-Roles")).isFalse();
        assertThat(capturedHeaders.containsKey("X-Username")).isFalse();
    }

    @Test
    void discoveryProxyFiltersIdentityHeadersWithoutInjectingPrincipal() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        GatewayProxyController controller = controllerWith(restTemplate);
        when(restTemplate.exchange(
                eq(URI.create("http://pds/search")),
                eq(HttpMethod.GET),
                org.mockito.ArgumentMatchers.<HttpEntity<?>>any(),
                eq(byte[].class)
        )).thenReturn(ResponseEntity.ok(new byte[0]));

        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/discovery/search");
        request.addHeader("X-User-Id", "spoofed-user");
        request.addHeader("X-User-Roles", "ADMIN");
        request.addHeader("X-Username", "spoofed-username");
        request.setUserPrincipal((Principal) () -> "keycloak-user-1");

        controller.proxyDiscovery(request, null);

        HttpHeaders capturedHeaders = capturedHeaders(restTemplate, URI.create("http://pds/search"));
        assertThat(capturedHeaders.containsKey("X-User-Id")).isFalse();
        assertThat(capturedHeaders.containsKey("X-User-Roles")).isFalse();
        assertThat(capturedHeaders.containsKey("X-Username")).isFalse();
    }

    @Test
    void proxyForwardsUnrelatedHeadersToOrchestrator() {
        RestTemplate restTemplate = mock(RestTemplate.class);
        GatewayProxyController controller = controllerWith(restTemplate);
        when(restTemplate.exchange(
                eq(URI.create("http://orchestrator/api/projects")),
                eq(HttpMethod.GET),
                org.mockito.ArgumentMatchers.<HttpEntity<?>>any(),
                eq(byte[].class)
        )).thenReturn(ResponseEntity.ok(new byte[0]));

        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/projects");
        request.addHeader("X-Request-Id", "request-1");

        controller.proxyProjects(request, null);

        HttpHeaders capturedHeaders = capturedHeaders(restTemplate, URI.create("http://orchestrator/api/projects"));
        assertThat(capturedHeaders.getFirst("X-Request-Id")).isEqualTo("request-1");
    }

    private GatewayProxyController controllerWith(RestTemplate restTemplate) {
        GatewayProxyController controller = new GatewayProxyController(mock(PublishedProjectEnricher.class));
        ReflectionTestUtils.setField(controller, "restTemplate", restTemplate);
        ReflectionTestUtils.setField(controller, "orchtrBaseUrl", "http://orchestrator");
        ReflectionTestUtils.setField(controller, "pdsBaseUrl", "http://pds");
        return controller;
    }

    private HttpHeaders capturedHeaders(RestTemplate restTemplate, URI uri) {
        ArgumentCaptor<HttpEntity<?>> entityCaptor = ArgumentCaptor.forClass(HttpEntity.class);
        verify(restTemplate).exchange(
                eq(uri),
                eq(HttpMethod.GET),
                entityCaptor.capture(),
                eq(byte[].class)
        );
        return entityCaptor.getValue().getHeaders();
    }

    private PreAuthorize preAuthorize(String methodName) throws Exception {
        for (var method : GatewayProxyController.class.getDeclaredMethods()) {
            if (method.getName().equals(methodName)) {
                return method.getAnnotation(PreAuthorize.class);
            }
        }
        throw new NoSuchMethodException(methodName);
    }

}
