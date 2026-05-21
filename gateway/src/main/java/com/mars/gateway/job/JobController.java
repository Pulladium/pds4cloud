package com.mars.gateway.job;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/jobs")
@RequiredArgsConstructor
@PreAuthorize("hasAnyRole('RESEARCHER', 'ADMIN')")
public class JobController {

    private final JobService jobService;
    private final ObjectMapper objectMapper;

    public record SubmitRequest(String projectId, List<JobService.ImageInput> images, String model) {
        public SubmitRequest {
            if (model == null || model.isBlank()) model = "gpt-4o";
        }
    }

    @PostMapping
    public ResponseEntity<Map<String, String>> submit(@RequestBody SubmitRequest req, Authentication authentication) {
        String userId = authentication != null && authentication.getName() != null && !authentication.getName().isBlank()
                ? authentication.getName()
                : "anonymous";
        Job job = jobService.submit(req.projectId(), userId, req.images(), req.model());
        Map<String, String> resp = new java.util.LinkedHashMap<>();
        resp.put("job_id", job.getId());
        resp.put("status", job.getStatus() != null ? job.getStatus().name() : "UNKNOWN");
        return ResponseEntity.ok(resp);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Map<String, Object>> getById(@PathVariable String id) {
        return ResponseEntity.ok(toResponse(jobService.getById(id)));
    }

    @GetMapping("/project/{projectId}")
    public ResponseEntity<List<Map<String, Object>>> getByProject(@PathVariable String projectId) {
        return ResponseEntity.ok(
                jobService.getByProject(projectId).stream().map(this::toResponse).toList()
        );
    }

    private Map<String, Object> toResponse(Job job) {
        Map<String, Object> m = new java.util.LinkedHashMap<>();
        m.put("job_id",            job.getId());
        m.put("project_id",        job.getProjectId());
        m.put("status",            job.getStatus() != null ? job.getStatus().name() : "UNKNOWN");
        m.put("stage_info",        job.getStageInfo() != null ? job.getStageInfo() : "");
        m.put("pdf_url",           job.getPdfUrl());
        m.put("error",             job.getError());
        m.put("prompt_tokens",     job.getPromptTokens());
        m.put("completion_tokens", job.getCompletionTokens());
        m.put("model",             job.getModel());
        m.put("cost_usd",          job.getCostUsd());
        m.put("worker_count",      job.getWorkerCount());
        m.put("image_progress",    parseImageProgress(job.getImageProgress()));
        m.put("created_at",        job.getCreatedAt() != null ? job.getCreatedAt().toString() : "");
        return m;
    }

    private Object parseImageProgress(String imageProgress) {
        if (imageProgress == null || imageProgress.isBlank()) return List.of();
        try {
            return objectMapper.readValue(imageProgress, List.class);
        } catch (Exception e) {
            return List.of();
        }
    }
}
