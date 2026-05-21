package com.mars.gateway.job;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

import java.util.List;
import java.util.Optional;

public interface JobRepository extends JpaRepository<Job, String> {

    List<Job> findByProjectIdOrderByCreatedAtDesc(String projectId);

    Optional<Job> findFirstByProjectIdAndStatusOrderByUpdatedAtDesc(String projectId, JobStatus status);

    Optional<Job> findFirstByProjectIdAndStatusAndPdfUrlIsNotNull(String projectId, JobStatus status);

    Optional<Job> findFirstByProjectIdAndStatusNotIn(String projectId, List<JobStatus> statuses);

    Optional<Job> findFirstByUserIdAndStatusNotIn(String userId, List<JobStatus> statuses);

    @Query("SELECT COUNT(j) FROM Job j WHERE j.status NOT IN :statuses")
    long countByStatusNotIn(List<JobStatus> statuses);

    List<Job> findAllByOrderByCreatedAtDesc();
}
