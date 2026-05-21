package com.mars.gateway.job;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface JobEventRepository extends JpaRepository<JobEvent, String> {

    List<JobEvent> findByJobIdOrderByCreatedAtAsc(String jobId);

    long countByJobId(String jobId);

    Optional<JobEvent> findTopByJobIdOrderByCreatedAtDesc(String jobId);
}
