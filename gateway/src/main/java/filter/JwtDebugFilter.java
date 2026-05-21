package com.mars.gateway.config.filters;

import jakarta.servlet.*;
import jakarta.servlet.http.HttpServletRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Collection;

@Slf4j
public class JwtDebugFilter extends OncePerRequestFilter {

    private static final String JWT_DEBUG = "JWT.DEBUG";

    @Override
    protected void doFilterInternal(HttpServletRequest httpRequest, jakarta.servlet.http.HttpServletResponse response, FilterChain chain)
            throws IOException, ServletException {
        String path = httpRequest.getRequestURI();
        
        try {
            Authentication auth = SecurityContextHolder.getContext().getAuthentication();
            logRequestAuthState(path, httpRequest, auth);
            
            if (auth != null && auth.isAuthenticated() && auth.getPrincipal() instanceof Jwt jwt) {
                logJwtClaims(path, jwt, auth.getAuthorities());
            }
        } catch (Exception e) {
            log.warn("JWT debug failed for {}: {}", path, e.getMessage(), e);
        }
        
        chain.doFilter(httpRequest, response);
    }

    private void logRequestAuthState(String path, HttpServletRequest request, Authentication auth) {
        String authorization = request.getHeader("Authorization");
        boolean hasBearer = authorization != null && authorization.startsWith("Bearer ");

        log.info(
                "JWT REQUEST DEBUG path={} hasBearerHeader={} authClass={} authenticated={} principalClass={} authorities={}",
                path,
                hasBearer,
                auth != null ? auth.getClass().getName() : null,
                auth != null ? auth.isAuthenticated() : null,
                auth != null && auth.getPrincipal() != null ? auth.getPrincipal().getClass().getName() : null,
                auth != null ? auth.getAuthorities() : null
        );
    }

    private void logJwtClaims(String path, Jwt jwt, Collection<? extends GrantedAuthority> authorities) {
        log.info("=== JWT DEBUG: {} ===", path);
        log.info("Subject: {}", jwt.getSubject());
        log.info("Issuer: {}", jwt.getIssuer());
        log.info("Expires: {}", jwt.getExpiresAt());
        log.info("Token ID (jti): {}", jwt.getId());
        log.info("Issued At: {}", jwt.getIssuedAt());
        
        // Log ALL claims (sanitize sensitive data in production)
        jwt.getClaims().forEach((key, value) -> {
            String valStr = sanitize(value);
            log.info("  [{}] = {}", key, valStr);
        });
        
        log.info("Mapped authorities: {}", authorities);
        log.info("=== END JWT DEBUG ===\n");
    }

    private String sanitize(Object value) {
        if (value == null) return "null";
        if (value instanceof String str) {
            // Truncate tokens, long strings
            return str.length() > 200 ? str.substring(0, 200) + "..." : str;
        }
        return value.toString();
    }
}
