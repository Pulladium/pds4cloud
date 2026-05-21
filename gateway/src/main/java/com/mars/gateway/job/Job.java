package com.mars.gateway.job;

import jakarta.persistence.*;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "jobs")
@Data
@NoArgsConstructor
public class Job {

    @Id
    private String id = UUID.randomUUID().toString();

    @Column(nullable = false)
    private String projectId;

    @Column(nullable = false)
    private String userId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private JobStatus status = JobStatus.PENDING;

    @Column
    private String stageInfo = "";

    @Column(length = 2048)
    private String pdfUrl;

    @Column(columnDefinition = "TEXT")
    private String error;

    @Column
    private Integer promptTokens;

    @Column
    private Integer completionTokens;

    @Column(length = 64)
    private String model;

    @Column
    private Double costUsd;

    @Column(columnDefinition = "TEXT")
    private String imageProgress = "[]";

    @Column
    private Integer workerCount;

    @Column(nullable = false)
    private int retryCount = 0;

    @Column(nullable = false)
    private Instant createdAt = Instant.now();

    @Column(nullable = false)
    private Instant updatedAt = Instant.now();

    @PreUpdate
    void onUpdate() {
        this.updatedAt = Instant.now();
    }
}
