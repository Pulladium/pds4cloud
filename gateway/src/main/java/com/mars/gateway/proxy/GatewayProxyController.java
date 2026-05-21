package com.mars.gateway.proxy;

import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.net.URI;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

@RestController
@RequiredArgsConstructor
public class GatewayProxyController {

    private static final List<String> HOP_BY_HOP_HEADERS = List.of(
            "host",
            "connection",
            "content-length",
            "transfer-encoding",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailer",
            "upgrade"
    );

    private static final List<String> EXTERNAL_PROXY_HEADERS = List.of(
            "forwarded",
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-port",
            "x-forwarded-proto",
            "x-real-ip"
    );

    private static final List<String> TRUSTED_IDENTITY_HEADERS = List.of(
            "x-user-id",
            "x-user-roles",
            "x-username"
    );

    private final RestTemplate restTemplate = new RestTemplate();

    @Value("${proxy.orchtr-base-url:http://localhost:8000}")
    private String orchtrBaseUrl;

    @Value("${proxy.pds-base-url:https://pds.mcp.nasa.gov/api/search/1}")
    private String pdsBaseUrl;

    private final PublishedProjectEnricher publishedProjectEnricher;

    @RequestMapping("/api/discovery/**")
    @PreAuthorize("permitAll()")
    public ResponseEntity<byte[]> proxyDiscovery(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        return proxy(request, body, pdsBaseUrl, "/api/discovery", true);
    }

    @RequestMapping("/api/qdrant/search")
    @PreAuthorize("permitAll()")
    public ResponseEntity<byte[]> proxyQdrantSearch(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        return proxy(request, body, orchtrBaseUrl, "");
    }

    @RequestMapping("/api/qdrant/add")
    @PreAuthorize("hasAnyRole('RESEARCHER', 'ADMIN')")
    public ResponseEntity<byte[]> proxyQdrantAdd(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        return proxy(request, body, orchtrBaseUrl, "");
    }

    @RequestMapping("/api/projects/published")
    @PreAuthorize("permitAll()")
    public ResponseEntity<byte[]> proxyPublishedProjects(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        ResponseEntity<byte[]> response = proxy(request, body, orchtrBaseUrl, "");
        if (!response.getStatusCode().is2xxSuccessful() || response.getBody() == null) {
            return response;
        }
        return new ResponseEntity<>(
                publishedProjectEnricher.enrich(response.getBody()),
                response.getHeaders(),
                response.getStatusCode()
        );
    }

    @RequestMapping("/api/projects/generated-previews")
    @PreAuthorize("permitAll()")
    public ResponseEntity<byte[]> proxyGeneratedPreviews(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        return proxy(request, body, orchtrBaseUrl, "");
    }

    @PostMapping("/api/projects/{projectId}/publish")
    @PreAuthorize("hasAnyRole('RESEARCHER', 'ADMIN')")
    public ResponseEntity<byte[]> proxyProjectPublish(
            HttpServletRequest request,
            @PathVariable String projectId,
            @RequestParam("comment") String comment,
            @RequestParam(name = "pdf_url", required = false) String pdfUrl,
            @RequestParam(name = "images", required = false) List<MultipartFile> images
    ) throws IOException {
        MultiValueMap<String, Object> form = new LinkedMultiValueMap<>();
        form.add("comment", comment);
        if (pdfUrl != null) {
            form.add("pdf_url", pdfUrl);
        }
        if (images != null) {
            for (MultipartFile image : images) {
                HttpHeaders partHeaders = new HttpHeaders();
                partHeaders.setContentType(MediaType.parseMediaType(image.getContentType()));
                form.add("images", new HttpEntity<>(multipartResource(image), partHeaders));
            }
        }

        HttpHeaders headers = copyHeaders(request);
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        HttpEntity<MultiValueMap<String, Object>> entity = new HttpEntity<>(form, headers);
        URI uri = URI.create(orchtrBaseUrl + proxiedPath(request, ""));
        return exchange(uri, HttpMethod.POST, entity);
    }

    @RequestMapping({"/api/projects", "/api/projects/**"})
    @PreAuthorize("hasAnyRole('RESEARCHER', 'ADMIN')")
    public ResponseEntity<byte[]> proxyProjects(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        return proxy(request, body, orchtrBaseUrl, "");
    }

    @RequestMapping("/api/models")
    @PreAuthorize("hasAnyRole('RESEARCHER', 'ADMIN')")
    public ResponseEntity<byte[]> proxyModels(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        return proxy(request, body, orchtrBaseUrl, "");
    }

    @RequestMapping("/api/langsmith/**")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<byte[]> proxyLangSmith(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        return proxy(request, body, orchtrBaseUrl, "");
    }

    @RequestMapping({"/api/process", "/api/result/**", "/api/image-url"})
    @PreAuthorize("hasAnyRole('RESEARCHER', 'ADMIN')")
    public ResponseEntity<byte[]> proxyAnalysis(HttpServletRequest request, @RequestBody(required = false) byte[] body) {
        return proxy(request, body, orchtrBaseUrl, "");
    }

    private ResponseEntity<byte[]> proxy(HttpServletRequest request, byte[] body, String baseUrl, String stripPrefix) {
        return proxy(request, body, baseUrl, stripPrefix, false);
    }

    private ResponseEntity<byte[]> proxy(HttpServletRequest request, byte[] body, String baseUrl, String stripPrefix, boolean externalTarget) {
        URI uri = URI.create(baseUrl + proxiedPath(request, stripPrefix));
        HttpEntity<byte[]> entity = new HttpEntity<>(body, copyHeaders(request, !externalTarget, externalTarget));
        return exchange(uri, HttpMethod.valueOf(request.getMethod()), entity);
    }

    private ResponseEntity<byte[]> exchange(URI uri, HttpMethod method, HttpEntity<?> entity) {
        ResponseEntity<byte[]> response;
        try {
            response = restTemplate.exchange(uri, method, entity, byte[].class);
        } catch (HttpStatusCodeException e) {
            return new ResponseEntity<>(e.getResponseBodyAsByteArray(), filteredHeaders(e.getResponseHeaders()), e.getStatusCode());
        }

        return new ResponseEntity<>(response.getBody(), filteredHeaders(response.getHeaders()), response.getStatusCode());
    }

    private HttpHeaders filteredHeaders(HttpHeaders source) {
        HttpHeaders responseHeaders = new HttpHeaders();
        if (source == null) return responseHeaders;
        source.forEach((name, values) -> {
            if (!HOP_BY_HOP_HEADERS.contains(name.toLowerCase(Locale.ROOT))) {
                responseHeaders.put(name, values);
            }
        });
        return responseHeaders;
    }

    private String proxiedPath(HttpServletRequest request, String stripPrefix) {
        String path = request.getRequestURI();
        if (!stripPrefix.isBlank() && path.startsWith(stripPrefix)) {
            path = path.substring(stripPrefix.length());
        }
        String query = request.getQueryString();
        return path + (query == null || query.isBlank() ? "" : "?" + query);
    }

    private HttpHeaders copyHeaders(HttpServletRequest request) {
        return copyHeaders(request, true, false);
    }

    private HttpHeaders copyHeaders(HttpServletRequest request, boolean injectIdentity, boolean externalTarget) {
        HttpHeaders headers = new HttpHeaders();
        Collections.list(request.getHeaderNames()).forEach(name -> {
            String lowerName = name.toLowerCase(Locale.ROOT);
            if (!HOP_BY_HOP_HEADERS.contains(lowerName)
                    && !TRUSTED_IDENTITY_HEADERS.contains(lowerName)
                    && !(externalTarget && EXTERNAL_PROXY_HEADERS.contains(lowerName))) {
                headers.put(name, Collections.list(request.getHeaders(name)));
            }
        });
        if (injectIdentity && request.getUserPrincipal() != null && request.getUserPrincipal().getName() != null
                && !request.getUserPrincipal().getName().isBlank()) {
            headers.set("X-User-Id", request.getUserPrincipal().getName());
        }
        return headers;
    }

    private ByteArrayResource multipartResource(MultipartFile file) throws IOException {
        return new ByteArrayResource(file.getBytes()) {
            @Override
            public String getFilename() {
                return file.getOriginalFilename();
            }
        };
    }

}
