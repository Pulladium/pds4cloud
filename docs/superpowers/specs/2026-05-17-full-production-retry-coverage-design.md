# Full Production Retry Coverage Evaluation Design

## Goal

Extend the retry recovery evaluation so the thesis evidence covers all production retry boundaries, not only representative analyze and PDF upload faults. The evaluation must also prove Kafka at-least-once behavior through both publish retry and deterministic duplicate-message idempotency checks.

## Scope

This design covers production pipeline and messaging retries only.

Included:

- Gateway Kafka publish retry for `job.submitted`.
- Orchestrator Kafka publish retry for `image.task`.
- Orchestrator Kafka publish retry for `job.status`.
- Ingest retry points for PDS lookup, PDS image download, metadata upload, and image upload.
- Transform retry points for storage download, gray upload, and RGB upload.
- Analyze retry points for image download, OpenAI call, and result upload.
- Image worker process retry around `process_product`.
- Aggregator retry points for PDF generation and PDF upload.
- Kafka duplicate/replay handling for at-least-once semantics.

Excluded:

- `evaluation/eval_lib.http_json` retry. It belongs to the benchmark runner, not the product pipeline, so it should remain unit-tested but not counted as production retry recovery evidence.
- Frontend/browser network behavior.
- Random chaos testing.
- Editing the thesis `.docx`.

## Output Model

Keep the existing output directory:

```text
evaluation/results/retry_recovery_e2e/
```

Add two thesis-facing tables:

```text
production-retry-coverage-table.txt
kafka-idempotency-table.txt
```

Keep existing outputs:

```text
evaluation-results-table.txt
retry-recovery-table.txt
worker-timeline-table.txt
thesis-interpretation-notes.txt
records.json
summary.json
retry_records.json
docker_logs/
```

Add structured evidence:

```text
production_retry_records.json
kafka_idempotency_records.json
```

`evaluation/results/summary.md` must list the new `.txt` tables in the `Thesis Text Tables` section.

## Production Retry Coverage Table

File:

```text
evaluation/results/retry_recovery_e2e/production-retry-coverage-table.txt
```

Columns:

```text
stage | component | fault_id | attempts_observed | recovered | mttr_seconds | final_status | evidence_source
```

Required rows:

```text
pds_lookup
pds_img_download
ingest_metadata_upload
ingest_img_upload
transform_storage_download
transform_gray_upload
transform_rgb_upload
analyze_image_download
analyze_openai_call
analyze_result_upload
image_worker_process
pdf_generation
pdf_upload
job_status_publish
image_task_publish
```

Each row must map to one deterministic evaluation fault. A row counts as recovered only when:

- the injected fault appears in evidence logs;
- a retry attempt is observed;
- the affected job reaches `COMPLETED`;
- `recovered_at` is later than `failure_injected_at`.

## Kafka At-Least-Once / Idempotency Table

File:

```text
evaluation/results/retry_recovery_e2e/kafka-idempotency-table.txt
```

Columns:

```text
topic | component | scenario | retry_or_duplicate_observed | idempotency_guard | final_effect | evidence_source
```

Required rows:

```text
job.submitted | gateway producer | transient publish failure
image.task | orchestrator dispatcher | transient publish failure
job.status | orchestrator producer | transient publish failure
image.result | orchestrator aggregator | duplicate image result replay
job.status | gateway consumer | duplicate status replay
job.status | gateway consumer | duplicate or late terminal status handling
```

Kafka coverage is separate from production retry recovery because Kafka at-least-once semantics require two proofs:

- transient publish failures are retried;
- duplicate or replayed messages do not create duplicate side effects.

## Fault Injection Model

Extend the existing `EVAL_FAULTS` JSON list. Fault specs remain evaluation-only and disabled unless `EVAL_FAULTS` is set.

Example:

```json
[
  {
    "fault_id": "f-pds-lookup-1",
    "stage": "pds_lookup",
    "group": "project_a",
    "lid": "urn:nasa:pds:...",
    "failures": 1
  },
  {
    "fault_id": "f-transform-gray-upload-1",
    "stage": "transform_gray_upload",
    "group": "project_a",
    "lid": "urn:nasa:pds:...",
    "failures": 1
  },
  {
    "fault_id": "f-job-status-publish-1",
    "stage": "job_status_publish",
    "job_id": "",
    "failures": 1
  },
  {
    "fault_id": "f-duplicate-image-result-1",
    "stage": "duplicate_image_result",
    "job_id": "",
    "lid": "urn:nasa:pds:...",
    "duplicates": 1
  }
]
```

Matching rules:

- `stage` is required.
- Empty `job_id` means wildcard.
- Missing `lid` means wildcard.
- `group` is runner metadata used to map faults to jobs after submission.
- `failures` controls transient exception count.
- `duplicates` controls deterministic replay count for duplicate-message scenarios.

Every injected fault log must include:

```text
EVAL_FAULT injected
fault_id
stage
job_id
lid when applicable
attempt
failures or duplicates
```

## Pipeline Hook Points

Add or extend evaluation-only fault hooks at these boundaries:

- `orchtr/nodes/ingest/one.py`
  - before/inside PDS lookup retry;
  - before/inside PDS image download retry;
  - before metadata upload;
  - before image upload.
- `orchtr/nodes/transform/logic.py`
  - before storage download;
  - before gray upload;
  - before RGB upload.
- `orchtr/nodes/analyze/logic.py`
  - before image download;
  - before OpenAI call;
  - before result upload.
- `orchtr/messaging/image_worker.py`
  - existing `analyze`/`process_product` retry hook remains, renamed or mapped to `image_worker_process` in evidence.
- `orchtr/messaging/aggregator.py`
  - before PDF generation;
  - before PDF upload.
- `orchtr/messaging/dispatcher.py`
  - before `image.task` publish.
- `orchtr/messaging/producer.py`
  - before `job.status` publish.
- `gateway/src/main/java/com/mars/gateway/job/JobService.java`
  - before `job.submitted` publish.

Do not add fault hooks to normal production paths unless guarded by explicit evaluation configuration.

## Kafka Duplicate Injection

Duplicate/replay tests should be deterministic. Do not rely on Kafka randomly duplicating messages.

Required scenarios:

- `duplicate_image_result`
  - replay one already accepted `image.result` for the same `job_id` and `lid`;
  - expected guard: aggregator `seen_lids`;
  - expected effect: image count and aggregation remain correct, no duplicate PDF input.
- `duplicate_job_status`
  - replay one status update for the same `job_id`;
  - expected guard: Gateway update by `job_id`;
  - expected effect: one job record, consistent status history.
- `late_terminal_status`
  - replay a terminal status after final completion when feasible;
  - expected guard: terminal status handling does not regress the final state;
  - expected effect: final status remains `COMPLETED`.

If a scenario cannot be safely injected inside the default 3x5 Docker workload, implement it as a focused Docker protocol that uses the same stack and writes to the same `kafka_idempotency_records.json`.

## Runner Behavior

The runner should build a fault plan before workload execution from `evaluation/cases.yml`. It should target stable LIDs instead of post-run job IDs, then map groups to actual job IDs after submission.

The Docker run must use the existing clean-state flow:

```bash
docker compose --profile eval down -v --remove-orphans
EVAL_FAULTS='<serialized-fault-plan>' docker compose --profile eval up -d --build
docker compose --profile eval exec -T evaluation-runner python -m evaluation.run_retry_recovery_e2e --keycloak http://keycloak:8080
```

The code should also support host-side Docker log capture for environments where `evaluation-runner` does not include the Docker CLI. Host-captured logs may be copied into `evaluation/results/retry_recovery_e2e/docker_logs/` and used to regenerate evidence summaries.

## Metrics

Production retry records must include:

```text
fault_id
stage
component
group
job_id
lid
failure_injected_at
recovered_at
mttr_seconds
attempts_observed
final_status
evidence_source
```

Kafka idempotency records must include:

```text
scenario
topic
component
job_id
lid
retry_or_duplicate_observed
idempotency_guard
final_effect
evidence_source
```

Aggregate summary must include:

```text
production_retry_faults
production_retry_recovered
production_retry_unrecovered
kafka_scenarios
kafka_scenarios_passed
retry_attempts_observed
mttr_seconds
failed_jobs
completed_jobs
throughput_images_per_minute
distinct_worker_count
max_concurrent_workers_observed
total_cost_usd
```

## Acceptance Criteria

- Docker evaluation starts from a clean state.
- Default workload processes 3 users, 3 projects, and 15 products.
- Evaluator HTTP retry is not counted in production retry coverage.
- Every required production retry row appears in `production-retry-coverage-table.txt`.
- Every required Kafka row appears in `kafka-idempotency-table.txt`.
- All injected production transient faults recover.
- Kafka publish retry is observed for Gateway and Orchestrator publish paths.
- Kafka duplicate-message scenarios preserve idempotent final effects.
- `failed_jobs` is `0` for the successful full-coverage run.
- Docker logs, JSON records, CSV records, and thesis `.txt` tables are preserved.
- `evaluation/results/summary.md` references the generated `.txt` tables.
- The thesis `.docx` is not modified.

## Risks and Constraints

The default 3x5 run already reaches OpenAI rate limits in some executions. Full fault coverage should minimize added OpenAI calls and prefer one-shot faults. If rate limits make a single all-in-one run unstable, split execution into two deterministic Docker protocols while keeping one combined result directory and two final thesis tables.

Kafka duplicate injection must be precise. Replaying the wrong message at the wrong time could create nondeterministic failures instead of useful evidence. Duplicate scenarios should be implemented with small focused hooks and explicit assertions.

Container-generated files may be owned by the container user. The runbook should include a permission step or write outputs with host-compatible permissions.

## Non-Goals

- Random chaos engineering.
- Exhaustive stress testing beyond the 3x5 thesis workload.
- Proving external OpenAI availability.
- Rewriting the production architecture.
- Editing the thesis document automatically.
