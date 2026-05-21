package com.mars.gateway.job;

import com.mars.gateway.config.SecurityConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import java.time.Instant;
import java.util.List;
import java.util.Map;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(AdminController.class)
@Import(SecurityConfig.class)
class AdminControllerTest {

    @Autowired MockMvc mvc;
    @MockBean JobService jobService;

    @Test
    @WithMockUser(roles = "ADMIN")
    void getAllJobs_returnsJobHistoryMetrics() throws Exception {
        Job job = new Job();
        job.setProjectId("proj-1");
        job.setUserId("user-1");
        job.setStatus(JobStatus.COMPLETED);

        when(jobService.getAllJobs()).thenReturn(List.of(job));
        when(jobService.getJobMetrics(job.getId())).thenReturn(Map.of(
                "event_count", 4L,
                "last_stage", "COMPLETED",
                "duration_ms", 1250L
        ));

        mvc.perform(get("/api/admin/jobs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].event_count").value(4))
                .andExpect(jsonPath("$[0].last_stage").value("COMPLETED"))
                .andExpect(jsonPath("$[0].duration_ms").value(1250));
    }

    @Test
    @WithMockUser(roles = "ADMIN")
    void getJobEvents_returnsChronologicalEvents() throws Exception {
        JobEvent event = new JobEvent();
        event.setJobId("job-1");
        event.setStage("PROCESSING_IMAGES");
        event.setStatus("PROCESSING_IMAGES");
        event.setMessage("1/2");
        event.setPayloadJson("{\"job_id\":\"job-1\"}");
        event.setCreatedAt(Instant.parse("2026-05-05T10:00:00Z"));

        when(jobService.getJobEvents("job-1")).thenReturn(List.of(event));

        mvc.perform(get("/api/admin/jobs/job-1/events"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].job_id").value("job-1"))
                .andExpect(jsonPath("$[0].stage").value("PROCESSING_IMAGES"))
                .andExpect(jsonPath("$[0].payload_json").value("{\"job_id\":\"job-1\"}"));
    }
}
