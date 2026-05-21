package com.mars.gateway.proxy;

import org.junit.jupiter.api.Test;
import org.yaml.snakeyaml.Yaml;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class DockerComposeMinioExposureTest {

    @Test
    void defaultComposeDoesNotPublishMinioConsolePort() throws Exception {
        String compose = Files.readString(Path.of("../docker-compose.yml"));
        Map<?, ?> minio = minioService(compose);

        assertThat(minioCommandContainsConsoleAddress(minio)).isTrue();
        assertThat(publishesMinioConsolePort(compose)).isFalse();
    }

    @Test
    void detectsShortSyntaxConsolePublication() {
        String compose = """
                services:
                  minio:
                    command: server /data --console-address ':9001'
                    ports: ['9001:9001']
                """;

        assertThat(publishesMinioConsolePort(compose)).isTrue();
    }

    @Test
    void detectsHostIpShortSyntaxConsolePublication() {
        String compose = """
                services:
                  minio:
                    command: server /data --console-address ':9001'
                    ports: ['127.0.0.1:9001:9001']
                """;

        assertThat(publishesMinioConsolePort(compose)).isTrue();
    }

    @Test
    void detectsLongSyntaxConsolePublication() {
        String compose = """
                services:
                  minio:
                    command: server /data --console-address ':9001'
                    ports:
                      - target: 9001
                        published: 9001
                """;

        assertThat(publishesMinioConsolePort(compose)).isTrue();
    }

    @Test
    void allowsDifferentPublishedPortOrTarget() {
        assertThat(publishesMinioConsolePort(composeWithPort("9000:9000"))).isFalse();
        assertThat(publishesMinioConsolePort(composeWithPort("9001:9000"))).isFalse();
    }

    @Test
    void detectsConsoleTargetOnAnyPublishedHostPort() {
        assertThat(publishesMinioConsolePort(composeWithPort("19001:9001"))).isTrue();
        assertThat(publishesMinioConsolePort(composeWithPort("127.0.0.1:19001:9001"))).isTrue();
    }

    @Test
    void detectsContainerOnlyShortSyntaxConsolePublication() {
        assertThat(publishesMinioConsolePort(composeWithPort("9001"))).isTrue();
    }

    @Test
    void detectsLongSyntaxConsoleTargetWithoutPublishedPort() {
        String compose = """
                services:
                  minio:
                    command: server /data --console-address ':9001'
                    ports:
                      - target: 9001
                """;

        assertThat(publishesMinioConsolePort(compose)).isTrue();
    }

    @Test
    void ignoresConsolePublicationOnOtherServices() {
        String compose = """
                services:
                  minio:
                    command: server /data --console-address ':9001'
                  other:
                    ports: ['9001:9001']
                """;

        assertThat(publishesMinioConsolePort(compose)).isFalse();
    }

    private static boolean publishesMinioConsolePort(String compose) {
        Object ports = minioService(compose).get("ports");
        if (!(ports instanceof List<?> portEntries)) {
            return false;
        }

        return portEntries.stream().anyMatch(DockerComposeMinioExposureTest::publishesConsolePort);
    }

    private static boolean minioCommandContainsConsoleAddress(Map<?, ?> minio) {
        Object command = minio.get("command");
        if (command instanceof List<?> commandParts) {
            return commandParts.stream().map(String::valueOf).anyMatch("--console-address"::equals)
                    && commandParts.stream().map(String::valueOf).anyMatch(":9001"::equals);
        }

        String commandText = String.valueOf(command);
        return commandText.contains("--console-address") && commandText.contains(":9001");
    }

    private static Map<?, ?> minioService(String compose) {
        Object loaded = new Yaml().load(compose);
        if (!(loaded instanceof Map<?, ?> root)) {
            return Map.of();
        }

        Object services = root.get("services");
        if (!(services instanceof Map<?, ?> serviceMap)) {
            return Map.of();
        }

        Object minio = serviceMap.get("minio");
        if (!(minio instanceof Map<?, ?> minioMap)) {
            return Map.of();
        }

        return minioMap;
    }

    private static boolean publishesConsolePort(Object portEntry) {
        if (portEntry instanceof Map<?, ?> portMap) {
            return numericValue(portMap.get("target")).filter(target -> target == 9001).isPresent();
        }

        if (portEntry instanceof String shortSyntax) {
            return shortSyntaxPublishesConsolePort(shortSyntax);
        }

        return false;
    }

    private static boolean shortSyntaxPublishesConsolePort(String port) {
        String portWithoutProtocol = port.split("/", 2)[0];
        String[] parts = portWithoutProtocol.split(":");
        Optional<Integer> target = numericValue(parts[parts.length - 1]);

        return target.filter(value -> value == 9001).isPresent();
    }

    private static Optional<Integer> numericValue(Object value) {
        if (value instanceof Number number) {
            return Optional.of(number.intValue());
        }

        if (!(value instanceof String text)) {
            return Optional.empty();
        }

        try {
            return Optional.of(Integer.parseInt(text.trim()));
        } catch (NumberFormatException ignored) {
            return Optional.empty();
        }
    }

    private static String composeWithPort(String port) {
        return """
                services:
                  minio:
                    command: server /data --console-address ':9001'
                    ports: ['%s']
                """.formatted(port);
    }
}
