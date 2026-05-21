package com.mars.gateway.proxy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mars.gateway.job.Job;
import com.mars.gateway.job.JobRepository;
import com.mars.gateway.job.JobStatus;
import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class PublishedProjectEnricherTest {

    @Test
    void enrichesPublishedProjectsWithLatestCompletedJobMetrics() throws Exception {
        JobRepository repo = mock(JobRepository.class);
        ObjectMapper mapper = new ObjectMapper();
        PublishedProjectEnricher enricher = new PublishedProjectEnricher(repo, mapper);

        Job job = new Job();
        job.setStatus(JobStatus.COMPLETED);
        job.setModel("gpt-4o-mini");
        job.setPromptTokens(1200);
        job.setCompletionTokens(340);
        job.setCostUsd(0.023);
        job.setWorkerCount(2);
        job.setStageInfo("Complete");

        when(repo.findFirstByProjectIdAndStatusOrderByUpdatedAtDesc("project-1", JobStatus.COMPLETED))
                .thenReturn(Optional.of(job));

        byte[] body = """
                [{
                  "id": "project-1",
                  "name": "Research",
                  "image_urls": ["https://example.test/1.jpg", "https://example.test/2.jpg"],
                  "pdf_url": "https://example.test/report.pdf"
                }]
                """.getBytes(StandardCharsets.UTF_8);

        var enriched = mapper.readTree(enricher.enrich(body));
        var metrics = enriched.get(0).get("metrics");

        assertThat(metrics.get("model").asText()).isEqualTo("gpt-4o-mini");
        assertThat(metrics.get("prompt_tokens").asInt()).isEqualTo(1200);
        assertThat(metrics.get("completion_tokens").asInt()).isEqualTo(340);
        assertThat(metrics.get("cost_usd").asDouble()).isEqualTo(0.023);
        assertThat(metrics.get("worker_count").asInt()).isEqualTo(2);
        assertThat(metrics.get("image_count").asInt()).isEqualTo(2);
    }
}
