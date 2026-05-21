package com.mars.gateway.kafka;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mars.gateway.job.JobService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.mockito.Mockito.*;

class JobStatusConsumerTest {

    JobService jobService;
    JobStatusConsumer consumer;

    @BeforeEach
    void setUp() {
        jobService = mock(JobService.class);
        consumer = new JobStatusConsumer(jobService, new ObjectMapper());
    }

    @Test
    void onStatusUpdate_callsApplyStatusUpdate_withParsedFields() {
        String msg = """
            {"job_id":"j1","status":"PROCESSING_IMAGES","stage_info":"2/4","pdf_url":null,"error":null}
            """;
        consumer.onStatusUpdate(msg);
        verify(jobService).applyStatusUpdate("j1", "PROCESSING_IMAGES", "2/4", null, null, null, null, null, null, null, null, msg);
    }

    @Test
    void onStatusUpdate_callsApplyStatusUpdate_withPdfUrl() {
        String msg = """
            {"job_id":"j2","status":"COMPLETED","stage_info":"","pdf_url":"https://minio/r.pdf","error":null}
            """;
        consumer.onStatusUpdate(msg);
        verify(jobService).applyStatusUpdate("j2", "COMPLETED", "", "https://minio/r.pdf", null, null, null, null, null, null, null, msg);
    }

    @Test
    void onStatusUpdate_treatsAbsentPdfUrl_asNull() {
        String msg = """
            {"job_id":"j3","status":"PROCESSING_IMAGES","stage_info":"1/2"}
            """;
        consumer.onStatusUpdate(msg);
        verify(jobService).applyStatusUpdate("j3", "PROCESSING_IMAGES", "1/2", null, null, null, null, null, null, null, null, msg);
    }

    @Test
    void onStatusUpdate_passesImageProgressJsonAndWorkerCount() {
        String msg = """
            {
              "job_id":"j4",
              "status":"PROCESSING_IMAGES",
              "image_progress":{"worker_id":2,"lid":"lid1","status":"processing","error":null},
              "worker_count":6
            }
            """;
        consumer.onStatusUpdate(msg);
        verify(jobService).applyStatusUpdate(
                eq("j4"),
                eq("PROCESSING_IMAGES"),
                isNull(),
                isNull(),
                isNull(),
                isNull(),
                isNull(),
                isNull(),
                isNull(),
                eq("{\"worker_id\":2,\"lid\":\"lid1\",\"status\":\"processing\",\"error\":null}"),
                eq(6),
                eq(msg)
        );
    }

    @Test
    void onStatusUpdate_doesNotThrow_onMalformedJson() {
        consumer.onStatusUpdate("not-json{{{");
        verifyNoInteractions(jobService);
    }
}
