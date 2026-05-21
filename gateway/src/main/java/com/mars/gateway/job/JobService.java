package com.mars.gateway.job;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.SneakyThrows;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.ArrayList;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
@Slf4j
public class JobService {

    private static final int MAX_CONCURRENT_JOBS = 5;
    private static final int KAFKA_PUBLISH_ATTEMPTS = 3;
    private static final List<JobStatus> TERMINAL = List.of(JobStatus.COMPLETED, JobStatus.FAILED);

    private final JobRepository repository;
    private final JobEventRepository eventRepository;
    private final KafkaTemplate<String, String> kafkaTemplate;
    private final ObjectMapper objectMapper;
    private final Map<String, Integer> evalFaultAttempts = new ConcurrentHashMap<>();

    public record ImageInput(String lid, String thumbUrl) {}

    @SneakyThrows
    public Job submit(String projectId, String userId, List<ImageInput> images, String model) {
        repository.findFirstByProjectIdAndStatusAndPdfUrlIsNotNull(projectId, JobStatus.COMPLETED)
                .ifPresent(j -> { throw new ResponseStatusException(
                        HttpStatus.CONFLICT,
                        "Project already has a completed analysis report; create a new project to analyze again."); });

        repository.findFirstByProjectIdAndStatusNotIn(projectId, TERMINAL)
                .ifPresent(j -> { throw new ResponseStatusException(
                        HttpStatus.CONFLICT, "Project already has an active job: " + j.getId()); });

        repository.findFirstByUserIdAndStatusNotIn(userId, TERMINAL)
                .ifPresent(j -> { throw new ResponseStatusException(
                        HttpStatus.CONFLICT, "User already has an active job: " + j.getId()); });

        long active = repository.countByStatusNotIn(TERMINAL);
        if (active >= MAX_CONCURRENT_JOBS) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS, "Reached maximum of " + MAX_CONCURRENT_JOBS + " concurrent jobs");
        }

        String effectiveModel = (model != null && !model.isBlank()) ? model : "gpt-4o";

        Job job = new Job();
        job.setProjectId(projectId);
        job.setUserId(userId);
        job.setStatus(JobStatus.PENDING);
        job.setModel(effectiveModel);
        job = repository.save(job);
        log.info("JOB SUBMIT DEBUG saved job={} project={} user={} totalJobs={}",
                job.getId(), projectId, userId, repository.count());

        Map<String, Object> payload = new HashMap<>();
        payload.put("job_id",     job.getId());
        payload.put("project_id", projectId);
        payload.put("user_id",    userId);
        payload.put("model",      effectiveModel);
        payload.put("images", images.stream()
                .map(i -> Map.of("lid", i.lid(), "thumb_url", i.thumbUrl()))
                .toList());

        String payloadJson = objectMapper.writeValueAsString(payload);
        appendEvent(job.getId(), "SUBMITTED", JobStatus.PENDING.name(), "Job submitted", payloadJson);
        try {
            publishSubmittedWithRetry(job.getId(), payloadJson);
        } catch (Exception e) {
            String error = "Kafka publish failed after " + KAFKA_PUBLISH_ATTEMPTS + " attempts: " + e.getMessage();
            job.setStatus(JobStatus.FAILED);
            job.setError(error);
            job.setRetryCount(KAFKA_PUBLISH_ATTEMPTS);
            repository.save(job);
            appendEvent(job.getId(), "SUBMIT_FAILED", JobStatus.FAILED.name(), error, payloadJson);
        }
        return job;
    }

    private void publishSubmittedWithRetry(String jobId, String payloadJson) throws Exception {
        Exception last = null;
        for (int attempt = 1; attempt <= KAFKA_PUBLISH_ATTEMPTS; attempt++) {
            try {
                maybeRaiseEvalFault("job_submitted_publish", jobId);
                CompletableFuture<?> future = kafkaTemplate.send("job.submitted", payloadJson);
                if (future != null) {
                    future.get(10, TimeUnit.SECONDS);
                }
                return;
            } catch (Exception e) {
                last = e;
                log.warn("job.submitted publish attempt {} failed for job {}: {}", attempt, jobId, e.getMessage());
            }
        }
        throw last != null ? last : new IllegalStateException("Kafka publish failed");
    }

    private void maybeRaiseEvalFault(String stage, String jobId) throws Exception {
        String raw = System.getProperty("EVAL_FAULTS");
        if (raw == null || raw.isBlank()) {
            raw = System.getenv("EVAL_FAULTS");
        }
        if (raw == null || raw.isBlank()) {
            return;
        }

        List<Map<String, Object>> specs;
        try {
            specs = objectMapper.readValue(raw, new TypeReference<>() {});
        } catch (Exception e) {
            log.warn("Ignoring invalid EVAL_FAULTS config: {}", e.getMessage());
            return;
        }

        for (Map<String, Object> spec : specs) {
            String specStage = String.valueOf(spec.getOrDefault("stage", ""));
            if (!stage.equals(specStage)) {
                continue;
            }
            String specJobId = String.valueOf(spec.getOrDefault("job_id", ""));
            if (!specJobId.isBlank() && !jobId.equals(specJobId)) {
                continue;
            }

            String faultId = String.valueOf(spec.getOrDefault("fault_id", stage));
            int failures = intValue(spec.get("failures"), 1);
            if (failures <= 0) {
                continue;
            }
            String attemptKey = faultId + "|" + stage + "|" + jobId;
            int attempt = evalFaultAttempts.merge(attemptKey, 1, Integer::sum);
            if (attempt > failures) {
                continue;
            }

            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("fault_id", faultId);
            payload.put("stage", stage);
            payload.put("job_id", jobId);
            payload.put("attempt", attempt);
            payload.put("failures", failures);
            log.warn("EVAL_FAULT injected {}", objectMapper.writeValueAsString(payload));
            throw new RuntimeException("eval fault injected: " + faultId);
        }
    }

    private int intValue(Object value, int fallback) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value instanceof String text && !text.isBlank()) {
            try {
                return Integer.parseInt(text);
            } catch (NumberFormatException ignored) {
                return fallback;
            }
        }
        return fallback;
    }

    public Job getById(String jobId) {
        return repository.findById(jobId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Job not found: " + jobId));
    }

    public List<Job> getByProject(String projectId) {
        return repository.findByProjectIdOrderByCreatedAtDesc(projectId);
    }

    public void applyStatusUpdate(String jobId, String status, String stageInfo,
                                   String pdfUrl, String error,
                                   Integer promptTokens, Integer completionTokens,
                                   String model, Double costUsd,
                                   String imageProgress, Integer workerCount,
                                   String payloadJson) {
        repository.findById(jobId).ifPresent(job -> {
            if (job.getStatus() != null && job.getStatus().isTerminal()) {
                log.info("KAFKA_IDEMPOTENCY late_terminal_status job={} guard=terminal_status final_effect=final_status_unchanged", jobId);
                return;
            }
            try {
                job.setStatus(JobStatus.valueOf(status));
            } catch (IllegalArgumentException e) {
                return;
            }
            String effectiveStageInfo = stageInfo != null ? stageInfo : job.getStageInfo();
            appendEvent(jobId, status, status, eventMessage(effectiveStageInfo, error, imageProgress), payloadJson);
            if (stageInfo != null) job.setStageInfo(stageInfo);
            if (pdfUrl  != null) job.setPdfUrl(pdfUrl);
            if (error   != null) job.setError(error);
            if (promptTokens     != null) job.setPromptTokens(promptTokens);
            if (completionTokens != null) job.setCompletionTokens(completionTokens);
            if (model            != null) job.setModel(model);
            if (costUsd          != null) job.setCostUsd(costUsd);
            if (workerCount      != null) job.setWorkerCount(workerCount);
            if (imageProgress    != null) job.setImageProgress(mergeImageProgress(jobId, job.getImageProgress(), imageProgress));
            repository.save(job);
            log.info("JOB STATUS DEBUG updated job={} status={} promptTokens={} completionTokens={} costUsd={} totalJobs={}",
                    jobId, job.getStatus(), job.getPromptTokens(), job.getCompletionTokens(), job.getCostUsd(), repository.count());
        });
    }

    private String eventMessage(String stageInfo, String error, String imageProgress) {
        if (error != null && !error.isBlank()) return error;
        if (stageInfo != null && !stageInfo.isBlank()) return stageInfo;
        if (imageProgress != null && !imageProgress.isBlank()) return imageProgress;
        return "";
    }

    private void appendEvent(String jobId, String stage, String status, String message, String payloadJson) {
        Instant now = Instant.now();
        JobEvent event = new JobEvent();
        event.setJobId(jobId);
        event.setStage(stage != null && !stage.isBlank() ? stage : "UNKNOWN");
        event.setStatus(status != null && !status.isBlank() ? status : "UNKNOWN");
        event.setMessage(message);
        event.setPayloadJson(payloadJson);
        event.setFinishedAt(now);
        event.setCreatedAt(now);

        eventRepository.findTopByJobIdOrderByCreatedAtDesc(jobId)
                .map(JobEvent::getCreatedAt)
                .ifPresentOrElse(previous -> {
                    event.setStartedAt(previous);
                    event.setDurationMs(Duration.between(previous, now).toMillis());
                }, () -> event.setStartedAt(now));

        eventRepository.save(event);
    }

    @SneakyThrows
    private String mergeImageProgress(String jobId, String currentJson, String updateJson) {
        List<Map<String, Object>> current;
        if (currentJson == null || currentJson.isBlank()) {
            current = new ArrayList<>();
        } else {
            current = new ArrayList<>(objectMapper.readValue(
                    currentJson,
                    objectMapper.getTypeFactory().constructCollectionType(List.class, Map.class)
            ));
        }

        Map<String, Object> update = objectMapper.readValue(updateJson, Map.class);
        Object updateWorkerId = update.get("worker_id");
        Object updateLid = update.get("lid");

        boolean replaced = false;
        for (int i = 0; i < current.size(); i++) {
            Map<String, Object> item = current.get(i);
            if (java.util.Objects.equals(item.get("worker_id"), updateWorkerId)
                    && java.util.Objects.equals(item.get("lid"), updateLid)) {
                current.set(i, update);
                replaced = true;
                log.info("KAFKA_IDEMPOTENCY duplicate_job_status job={} guard=update_by_job_id final_effect=one_job_record", jobId);
                break;
            }
        }
        if (!replaced) {
            current.add(update);
        }

        return objectMapper.writeValueAsString(current);
    }

    public List<Job> getAllJobs() {
        return repository.findAllByOrderByCreatedAtDesc();
    }

    public List<JobEvent> getJobEvents(String jobId) {
        getById(jobId);
        return eventRepository.findByJobIdOrderByCreatedAtAsc(jobId);
    }

    public Map<String, Object> getJobMetrics(String jobId) {
        List<JobEvent> events = eventRepository.findByJobIdOrderByCreatedAtAsc(jobId);
        Map<String, Object> metrics = new HashMap<>();
        metrics.put("event_count", eventRepository.countByJobId(jobId));
        metrics.put("last_stage", events.isEmpty() ? null : events.getLast().getStage());
        metrics.put("duration_ms", durationMs(events));
        return metrics;
    }

    private Long durationMs(List<JobEvent> events) {
        if (events.size() < 2) return null;
        Instant first = events.getFirst().getCreatedAt();
        Instant last = events.getLast().getCreatedAt();
        if (first == null || last == null) return null;
        return Duration.between(first, last).toMillis();
    }
}
