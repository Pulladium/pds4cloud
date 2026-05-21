package com.mars.gateway.job;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "job_events", indexes = {
        @Index(name = "idx_job_events_job_created", columnList = "job_id,created_at")
})
@Data
@NoArgsConstructor
public class JobEvent {

    @Id
    private String id = UUID.randomUUID().toString();

    @Column(name = "job_id", nullable = false)
    private String jobId;

    @Column(nullable = false, length = 128)
    private String stage;

    @Column(nullable = false, length = 64)
    private String status;

    @Column(columnDefinition = "TEXT")
    private String message;

    @Column(name = "payload_json", columnDefinition = "TEXT")
    private String payloadJson;

    @Column(name = "started_at")
    private Instant startedAt;

    @Column(name = "finished_at")
    private Instant finishedAt;

    @Column(name = "duration_ms")
    private Long durationMs;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt = Instant.now();
}
