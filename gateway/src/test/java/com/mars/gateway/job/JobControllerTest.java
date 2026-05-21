package com.mars.gateway.job;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mars.gateway.config.SecurityConfig;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(JobController.class)
@Import(SecurityConfig.class)
class JobControllerTest {

    @Autowired MockMvc mvc;
    @Autowired ObjectMapper mapper;
    @MockBean JobService service;

    @Test
    @WithMockUser(username = "eval-user-1", roles = "RESEARCHER")
    void post_jobs_usesAuthenticatedUsernameAsUserId() throws Exception {
        Job job = new Job();
        job.setProjectId("proj-1");
        job.setUserId("eval-user-1");
        job.setStatus(JobStatus.PENDING);
        when(service.submit(eq("proj-1"), eq("eval-user-1"), any(), eq("gpt-4o"))).thenReturn(job);

        mvc.perform(post("/api/jobs")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of(
                        "projectId", "proj-1",
                        "images", List.of(Map.of("lid", "lid1", "thumbUrl", "http://t1"))
                ))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.job_id").exists())
                .andExpect(jsonPath("$.status").value("PENDING"));
    }

    @Test
    @WithMockUser(roles = "RESEARCHER")
    void get_job_by_id_returns_job_fields() throws Exception {
        Job job = new Job();
        job.setProjectId("proj-1");
        job.setUserId("u1");
        job.setStatus(JobStatus.COMPLETED);
        job.setPdfUrl("https://minio/report.pdf");
        job.setWorkerCount(6);
        job.setImageProgress("""
                [{"worker_id":2,"lid":"lid1","status":"done","error":null}]
                """);
        when(service.getById(job.getId())).thenReturn(job);

        mvc.perform(get("/api/jobs/" + job.getId()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("COMPLETED"))
                .andExpect(jsonPath("$.pdf_url").value("https://minio/report.pdf"))
                .andExpect(jsonPath("$.worker_count").value(6))
                .andExpect(jsonPath("$.image_progress[0].worker_id").value(2))
                .andExpect(jsonPath("$.image_progress[0].lid").value("lid1"))
                .andExpect(jsonPath("$.image_progress[0].status").value("done"));
    }

    @Test
    @WithMockUser(roles = "RESEARCHER")
    void get_jobs_by_project_returns_list() throws Exception {
        Job job = new Job();
        job.setProjectId("proj-1");
        job.setUserId("u1");
        job.setStatus(JobStatus.PROCESSING_IMAGES);
        job.setStageInfo("1/3");
        when(service.getByProject("proj-1")).thenReturn(List.of(job));

        mvc.perform(get("/api/jobs/project/proj-1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].status").value("PROCESSING_IMAGES"))
                .andExpect(jsonPath("$[0].stage_info").value("1/3"));
    }
}
