package com.mars.gateway.proxy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.mars.gateway.job.Job;
import com.mars.gateway.job.JobRepository;
import com.mars.gateway.job.JobStatus;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
class PublishedProjectEnricher {

    private final JobRepository jobRepository;
    private final ObjectMapper objectMapper;

    byte[] enrich(byte[] body) {
        try {
            JsonNode root = objectMapper.readTree(body);
            if (!root.isArray()) return body;

            for (JsonNode node : root) {
                if (!node.isObject()) continue;
                ObjectNode project = (ObjectNode) node;
                String projectId = project.path("id").asText("");
                int imageCount = project.path("image_urls").isArray() ? project.path("image_urls").size() : 0;

                ObjectNode metrics = project.putObject("metrics");
                metrics.put("image_count", imageCount);
                jobRepository.findFirstByProjectIdAndStatusOrderByUpdatedAtDesc(projectId, JobStatus.COMPLETED)
                        .ifPresent(job -> addJobMetrics(metrics, job));
            }

            return objectMapper.writeValueAsBytes(root);
        } catch (Exception ignored) {
            return body;
        }
    }

    private void addJobMetrics(ObjectNode metrics, Job job) {
        if (job.getModel() != null) metrics.put("model", job.getModel());
        if (job.getPromptTokens() != null) metrics.put("prompt_tokens", job.getPromptTokens());
        if (job.getCompletionTokens() != null) metrics.put("completion_tokens", job.getCompletionTokens());
        if (job.getCostUsd() != null) metrics.put("cost_usd", job.getCostUsd());
        if (job.getWorkerCount() != null) metrics.put("worker_count", job.getWorkerCount());
        if (job.getStageInfo() != null) metrics.put("stage_info", job.getStageInfo());
    }
}
