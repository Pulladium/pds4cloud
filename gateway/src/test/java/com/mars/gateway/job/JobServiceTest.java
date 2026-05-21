package com.mars.gateway.job;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.http.HttpStatus;
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.web.server.ResponseStatusException;

import java.util.List;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(OutputCaptureExtension.class)
class JobServiceTest {

    JobRepository repo;
    JobEventRepository eventRepo;
    KafkaTemplate<String, String> kafka;
    ObjectMapper mapper;
    JobService service;

    @BeforeEach
    void setUp() {
        repo = mock(JobRepository.class);
        eventRepo = mock(JobEventRepository.class);
        kafka = mock(KafkaTemplate.class);
        mapper = new ObjectMapper();
        service = new JobService(repo, eventRepo, kafka, mapper);
    }

    @Test
    void submit_createsJobAndPublishesToKafka() {
        when(repo.findFirstByProjectIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
        when(repo.countByStatusNotIn(any())).thenReturn(0L);
        when(repo.save(any())).thenAnswer(inv -> inv.getArgument(0));

        var images = List.of(new JobService.ImageInput("lid1", "http://thumb1"));
        Job job = service.submit("proj-1", "user-1", images, "gpt-4o");

        assertThat(job.getStatus()).isEqualTo(JobStatus.PENDING);
        assertThat(job.getProjectId()).isEqualTo("proj-1");
        assertThat(job.getUserId()).isEqualTo("user-1");
        verify(kafka).send(eq("job.submitted"), any(String.class));
        verify(eventRepo).save(argThat(event ->
                event.getJobId().equals(job.getId())
                        && event.getStage().equals("SUBMITTED")
                        && event.getStatus().equals("PENDING")
                        && event.getPayloadJson().contains("\"project_id\":\"proj-1\"")
        ));
    }

    @Test
    void submit_retriesKafkaPublishAfterTransientFailure() {
        when(repo.findFirstByProjectIdAndStatusAndPdfUrlIsNotNull(anyString(), any())).thenReturn(Optional.empty());
        when(repo.findFirstByProjectIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
        when(repo.findFirstByUserIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
        when(repo.countByStatusNotIn(any())).thenReturn(0L);
        when(repo.save(any())).thenAnswer(inv -> inv.getArgument(0));
        when(kafka.send(eq("job.submitted"), anyString()))
                .thenReturn(CompletableFuture.failedFuture(new RuntimeException("broker busy")))
                .thenReturn(CompletableFuture.completedFuture(null));

        Job job = service.submit("proj-1", "user-1", List.of(new JobService.ImageInput("lid1", "http://thumb")), "gpt-4o");

        assertThat(job.getStatus()).isEqualTo(JobStatus.PENDING);
        verify(kafka, times(2)).send(eq("job.submitted"), anyString());
    }

    @Test
    void submit_recoversAfterEvalJobSubmittedPublishFault(CapturedOutput output) {
        System.setProperty(
                "EVAL_FAULTS",
                "[{\"fault_id\":\"f-job-submitted-publish-1\",\"stage\":\"job_submitted_publish\",\"job_id\":\"\",\"failures\":1}]"
        );
        try {
            when(repo.findFirstByProjectIdAndStatusAndPdfUrlIsNotNull(anyString(), any())).thenReturn(Optional.empty());
            when(repo.findFirstByProjectIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
            when(repo.findFirstByUserIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
            when(repo.countByStatusNotIn(any())).thenReturn(0L);
            when(repo.save(any())).thenAnswer(inv -> inv.getArgument(0));
            when(kafka.send(eq("job.submitted"), anyString()))
                    .thenReturn(CompletableFuture.completedFuture(null));

            Job job = service.submit("proj-1", "user-1", List.of(new JobService.ImageInput("lid1", "http://thumb")), "gpt-4o");

            assertThat(job.getStatus()).isEqualTo(JobStatus.PENDING);
            verify(kafka, times(1)).send(eq("job.submitted"), anyString());
            assertThat(output).contains("EVAL_FAULT injected");
            assertThat(output).contains("\"stage\":\"job_submitted_publish\"");
            assertThat(output).contains("\"fault_id\":\"f-job-submitted-publish-1\"");
        } finally {
            System.clearProperty("EVAL_FAULTS");
        }
    }

    @Test
    void submit_marksJobFailedWhenKafkaPublishRetriesAreExhausted() {
        when(repo.findFirstByProjectIdAndStatusAndPdfUrlIsNotNull(anyString(), any())).thenReturn(Optional.empty());
        when(repo.findFirstByProjectIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
        when(repo.findFirstByUserIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
        when(repo.countByStatusNotIn(any())).thenReturn(0L);
        when(repo.save(any())).thenAnswer(inv -> inv.getArgument(0));
        when(kafka.send(eq("job.submitted"), anyString()))
                .thenReturn(CompletableFuture.failedFuture(new RuntimeException("broker down")));

        Job job = service.submit("proj-1", "user-1", List.of(new JobService.ImageInput("lid1", "http://thumb")), "gpt-4o");

        assertThat(job.getStatus()).isEqualTo(JobStatus.FAILED);
        assertThat(job.getError()).contains("Kafka publish failed");
        verify(kafka, times(3)).send(eq("job.submitted"), anyString());
        verify(eventRepo).save(argThat(event ->
                event.getJobId().equals(job.getId())
                        && event.getStage().equals("SUBMIT_FAILED")
                        && event.getStatus().equals("FAILED")
                        && event.getMessage().contains("Kafka publish failed")
        ));
    }

    @Test
    void submit_throws409_whenProjectAlreadyHasActiveJob() {
        Job active = new Job();
        active.setStatus(JobStatus.PROCESSING_IMAGES);
        when(repo.findFirstByProjectIdAndStatusNotIn(eq("proj-1"), any()))
                .thenReturn(Optional.of(active));

        var images = List.of(new JobService.ImageInput("lid1", "http://thumb1"));
        assertThatThrownBy(() -> service.submit("proj-1", "user-1", images, "gpt-4o"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("already has an active job");
    }

    @Test
    void submitRejectsProjectWithCompletedPdfReport() {
        Job completed = new Job();
        completed.setId("completed-job");
        completed.setProjectId("project-1");
        completed.setUserId("user-1");
        completed.setStatus(JobStatus.COMPLETED);
        completed.setPdfUrl("https://minio/report.pdf");

        when(repo.findFirstByProjectIdAndStatusAndPdfUrlIsNotNull("project-1", JobStatus.COMPLETED))
                .thenReturn(Optional.of(completed));

        ResponseStatusException ex = assertThrows(ResponseStatusException.class, () ->
                service.submit("project-1", "user-1", List.of(new JobService.ImageInput("lid1", "http://thumb")), "gpt-4o")
        );

        assertThat(ex.getStatusCode()).isEqualTo(HttpStatus.CONFLICT);
        assertThat(ex.getReason()).contains("completed analysis report");
        verify(kafka, never()).send(eq("job.submitted"), anyString());
    }

    @Test
    void submit_throws409_whenUserAlreadyHasActiveJobInAnotherProject() {
        Job active = new Job();
        active.setProjectId("proj-1");
        active.setUserId("user-1");
        active.setStatus(JobStatus.PROCESSING_IMAGES);

        when(repo.findFirstByProjectIdAndStatusNotIn(eq("proj-2"), any()))
                .thenReturn(Optional.empty());
        when(repo.findFirstByUserIdAndStatusNotIn(eq("user-1"), any()))
                .thenReturn(Optional.of(active));

        var images = List.of(new JobService.ImageInput("lid1", "http://thumb1"));
        assertThatThrownBy(() -> service.submit("proj-2", "user-1", images, "gpt-4o"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("User already has an active job");

        verify(kafka, never()).send(any(), any());
    }

    @Test
    void submit_throws429_whenGlobalLimitReached() {
        when(repo.findFirstByProjectIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
        when(repo.findFirstByUserIdAndStatusNotIn(any(), any())).thenReturn(Optional.empty());
        when(repo.countByStatusNotIn(any())).thenReturn(5L);

        var images = List.of(new JobService.ImageInput("lid1", "http://thumb1"));
        assertThatThrownBy(() -> service.submit("proj-1", "user-1", images, "gpt-4o"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("maximum");
    }

    @Test
    void applyStatusUpdate_mergesImageProgressByWorkerAndLid(CapturedOutput output) {
        Job job = new Job();
        job.setStageInfo("2/5");
        job.setImageProgress("""
                [{"worker_id":2,"lid":"lid1","status":"processing","error":null}]
                """);
        when(repo.findById("job-1")).thenReturn(Optional.of(job));
        when(repo.save(any())).thenAnswer(inv -> inv.getArgument(0));
        when(eventRepo.findTopByJobIdOrderByCreatedAtDesc("job-1")).thenReturn(Optional.empty());

        service.applyStatusUpdate(
                "job-1",
                "PROCESSING_IMAGES",
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                "{\"worker_id\":2,\"lid\":\"lid1\",\"status\":\"done\",\"error\":null}",
                6,
                "{\"job_id\":\"job-1\",\"status\":\"PROCESSING_IMAGES\"}"
        );

        assertThat(job.getStageInfo()).isEqualTo("2/5");
        assertThat(job.getWorkerCount()).isEqualTo(6);
        assertThat(job.getImageProgress()).contains("\"status\":\"done\"");
        assertThat(job.getImageProgress()).doesNotContain("processing");
        assertThat(job.getImageProgress()).containsOnlyOnce("\"lid\":\"lid1\"");
        assertThat(output).contains("KAFKA_IDEMPOTENCY duplicate_job_status job=job-1 guard=update_by_job_id final_effect=one_job_record");
        verify(repo).save(job);
        verify(eventRepo).save(argThat(event ->
                event.getJobId().equals("job-1")
                        && event.getStage().equals("PROCESSING_IMAGES")
                        && event.getStatus().equals("PROCESSING_IMAGES")
                        && event.getMessage().equals("2/5")
                        && event.getPayloadJson().contains("\"job_id\":\"job-1\"")
        ));
    }

    @Test
    void applyStatusUpdate_ignoresLateTerminalStatusAfterCompleted(CapturedOutput output) {
        Job job = new Job();
        job.setStatus(JobStatus.COMPLETED);
        job.setPdfUrl("https://minio/report.pdf");
        when(repo.findById("job-1")).thenReturn(Optional.of(job));

        service.applyStatusUpdate(
                "job-1",
                "FAILED",
                "late failure",
                null,
                "late error",
                null,
                null,
                null,
                null,
                null,
                null,
                "{\"job_id\":\"job-1\",\"status\":\"FAILED\"}"
        );

        assertThat(job.getStatus()).isEqualTo(JobStatus.COMPLETED);
        assertThat(job.getPdfUrl()).isEqualTo("https://minio/report.pdf");
        verify(repo, never()).save(any());
        verify(eventRepo, never()).save(any());
        assertThat(output).contains("KAFKA_IDEMPOTENCY late_terminal_status job=job-1 guard=terminal_status final_effect=final_status_unchanged");
    }
}
