package com.mars.gateway.job;

public enum JobStatus {
    PENDING,
    PROCESSING_IMAGES,
    GENERATING_PDF,
    COMPLETED,
    FAILED;

    public boolean isTerminal() {
        return this == COMPLETED || this == FAILED;
    }

    public boolean isActive() {
        return !isTerminal();
    }
}
