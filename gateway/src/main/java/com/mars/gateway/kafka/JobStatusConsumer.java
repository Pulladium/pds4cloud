package com.mars.gateway.kafka;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mars.gateway.job.JobService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
@Slf4j
public class JobStatusConsumer {

    private final JobService jobService;
    private final ObjectMapper objectMapper;

    @KafkaListener(topics = "job.status", groupId = "spring-gateway")
    public void onStatusUpdate(String message) {
        try {
            JsonNode node = objectMapper.readTree(message);
            String jobId     = node.path("job_id").asText();
            String status    = node.path("status").asText();
            String stageInfo = node.has("stage_info") && !node.path("stage_info").isNull()
                    ? node.path("stage_info").asText("") : null;
            String pdfUrl = node.has("pdf_url") && !node.path("pdf_url").isNull()
                    ? node.path("pdf_url").asText(null) : null;
            String error = node.has("error") && !node.path("error").isNull()
                    ? node.path("error").asText(null) : null;
            Integer promptTokens = node.has("prompt_tokens") && !node.path("prompt_tokens").isNull()
                    ? node.path("prompt_tokens").asInt() : null;
            Integer completionTokens = node.has("completion_tokens") && !node.path("completion_tokens").isNull()
                    ? node.path("completion_tokens").asInt() : null;
            String model = node.has("model") && !node.path("model").isNull()
                    ? node.path("model").asText(null) : null;
            Double costUsd = node.has("cost_usd") && !node.path("cost_usd").isNull()
                    ? node.path("cost_usd").asDouble() : null;
            String imageProgress = node.has("image_progress") && !node.path("image_progress").isNull()
                    ? objectMapper.writeValueAsString(node.path("image_progress")) : null;
            Integer workerCount = node.has("worker_count") && !node.path("worker_count").isNull()
                    ? node.path("worker_count").asInt() : null;

            jobService.applyStatusUpdate(jobId, status, stageInfo, pdfUrl, error,
                    promptTokens, completionTokens, model, costUsd, imageProgress, workerCount, message);
            log.debug("Applied status update job={} status={}", jobId, status);
        } catch (Exception e) {
            log.error("Failed to process job.status message: {}", message, e);
        }
    }
}
