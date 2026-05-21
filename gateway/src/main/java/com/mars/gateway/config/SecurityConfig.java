package com.mars.gateway.config;

import com.mars.gateway.config.filters.JwtDebugFilter;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.web.authentication.BearerTokenAuthenticationFilter;
import org.springframework.security.web.SecurityFilterChain;

import java.util.*;
import java.util.stream.Collectors;

@Configuration
@EnableWebSecurity
@EnableMethodSecurity(prePostEnabled = true) // 👈 Enables @PreAuthorize for Servlet
@Slf4j
public class SecurityConfig {

    @Value("${security.enabled:false}")
    private boolean securityEnabled;

    @Value("${keycloak.client-id:}")
    private String targetClientId;

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            // Register debug filter after bearer token auth has populated SecurityContext.
            .addFilterAfter(new JwtDebugFilter(), BearerTokenAuthenticationFilter.class)
            
            .csrf(c -> c.disable())
            .cors(c -> c.configurationSource(request -> {
                var cfg = new org.springframework.web.cors.CorsConfiguration();
                cfg.setAllowedOriginPatterns(List.of("*"));
                cfg.setAllowedMethods(List.of("*"));
                cfg.setAllowedHeaders(List.of("*"));
                return cfg;
            }))
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtAuthenticationConverter(jwtAuthenticationConverter()))
            );

        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/health", "/h2-console/**").permitAll()
            .anyRequest().permitAll()
        );
        return http.build();
    }

    /**
     * Converts Keycloak JWT roles → Spring Security GrantedAuthorities
     * Handles: realm_access.roles, resource_access.{client}.roles, and legacy "roles"
     */
    @Bean
    public JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(jwt -> {
            Set<String> allRoles = new HashSet<>();
            
            // 1. Realm roles: realm_access.roles
            Map<String, Object> realmAccess = jwt.getClaimAsMap("realm_access");
            if (realmAccess != null && realmAccess.containsKey("roles")) {
                @SuppressWarnings("unchecked")
                List<String> roles = (List<String>) realmAccess.get("roles");
                if (roles != null) allRoles.addAll(roles);
            }
            
            // 2. Client roles: resource_access.{clientId}.roles
            Map<String, Object> resourceAccess = jwt.getClaimAsMap("resource_access");
            if (resourceAccess != null) {
                Set<String> clientsToCheck = targetClientId.isBlank() 
                    ? resourceAccess.keySet() 
                    : Set.of(targetClientId);
                    
                for (String clientId : clientsToCheck) {
                    Map<String, Object> clientData = (Map<String, Object>) resourceAccess.get(clientId);
                    if (clientData != null && clientData.containsKey("roles")) {
                        @SuppressWarnings("unchecked")
                        List<String> roles = (List<String>) clientData.get("roles");
                        if (roles != null) allRoles.addAll(roles);
                    }
                }
            }
            
            // 3. Legacy top-level "roles" claim (if Keycloak mapper adds it)
            List<String> legacyRoles = jwt.getClaimAsStringList("roles");
            if (legacyRoles != null) allRoles.addAll(legacyRoles);
            
            // Convert to Spring Security format: ROLE_ prefix + uppercase
            List<GrantedAuthority> authorities = allRoles.stream()
                .filter(Objects::nonNull)
                .map(role -> "ROLE_" + role.toUpperCase().replace('-', '_'))
                .map(SimpleGrantedAuthority::new)
                .collect(Collectors.toList());

            log.info(
                "JWT ROLE DEBUG subject={} preferred_username={} client={} realm_access.roles={} resource_access={} legacy_roles={} raw_roles={} mapped_authorities={}",
                jwt.getSubject(),
                jwt.getClaimAsString("preferred_username"),
                targetClientId,
                realmAccess != null ? realmAccess.get("roles") : null,
                resourceAccess,
                legacyRoles,
                allRoles,
                authorities
            );

            return authorities;
        });
        return converter;
    }
}
