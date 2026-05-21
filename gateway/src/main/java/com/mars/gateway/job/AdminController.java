package com.mars.gateway.job;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.security.access.prepost.PreAuthorize;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/admin")
@RequiredArgsConstructor
@Slf4j
public class AdminController {

    private final JobService jobService;

    // TODO: add Keycloak role check here when Spring/Keycloak integration is done
    @GetMapping("/jobs")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<List<Map<String, Object>>> getAllJobs() {
        List<Job> jobs = jobService.getAllJobs();
        log.info("ADMIN JOBS DEBUG count={} ids={}", jobs.size(), jobs.stream().map(Job::getId).toList());
        return ResponseEntity.ok(jobs.stream().map(this::toResponse).toList());
    }

    @GetMapping("/jobs/{jobId}/events")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<List<Map<String, Object>>> getJobEvents(@PathVariable String jobId) {
        return ResponseEntity.ok(jobService.getJobEvents(jobId).stream().map(this::toEventResponse).toList());
    }

    private Map<String, Object> toResponse(Job job) {
        Map<String, Object> m = new java.util.LinkedHashMap<>();
        m.put("job_id",            job.getId());
        m.put("user_id",           job.getUserId());
        m.put("project_id",        job.getProjectId());
        m.put("status",            job.getStatus() != null ? job.getStatus().name() : "UNKNOWN");
        m.put("model",             job.getModel());
        m.put("prompt_tokens",     job.getPromptTokens());
        m.put("completion_tokens", job.getCompletionTokens());
        m.put("cost_usd",          job.getCostUsd());
        m.put("created_at",        job.getCreatedAt() != null ? job.getCreatedAt().toString() : "");
        m.putAll(jobService.getJobMetrics(job.getId()));
        return m;
    }

    private Map<String, Object> toEventResponse(JobEvent event) {
        Map<String, Object> m = new java.util.LinkedHashMap<>();
        m.put("id",          event.getId());
        m.put("job_id",      event.getJobId());
        m.put("stage",       event.getStage());
        m.put("status",      event.getStatus());
        m.put("message",     event.getMessage());
        m.put("payload_json", event.getPayloadJson());
        m.put("started_at",  event.getStartedAt() != null ? event.getStartedAt().toString() : "");
        m.put("finished_at", event.getFinishedAt() != null ? event.getFinishedAt().toString() : "");
        m.put("duration_ms", event.getDurationMs());
        m.put("created_at",  event.getCreatedAt() != null ? event.getCreatedAt().toString() : "");
        return m;
    }
}
