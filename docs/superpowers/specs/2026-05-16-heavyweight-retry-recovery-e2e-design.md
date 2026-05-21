# Heavyweight Retry Recovery E2E Evaluation Design

## Goal

Create a thesis-grade end-to-end evaluation protocol that proves retry/recovery behavior under realistic batch load. The protocol must run through the Docker Compose evaluation stack, clean cached artifacts before execution, process the existing thesis-default workload of 3 users with 5 real PDS products each, inject controlled transient failures, capture operational evidence, and generate copy-paste-ready `.txt` result tables for the thesis evaluation chapter.

## Context

The thesis assignment requires reproducible evaluation of functional behavior, load and failure behavior, retry/resume, idempotency, data consistency, operational metrics, MTTR, throughput, failure rate, and baseline-vs-proposed cost impact.

The current evaluation harness already includes multi-user, failure, idempotency, limits, load, sequential-reference, charts, and report generation. Existing results include `mttr_seconds`, but the current failure protocol records `failed_at` and `recovered_at` almost simultaneously for a permanent bad-LID failure, so it is not strong evidence of retry recovery. The new protocol should produce stronger evidence by measuring recovery from controlled transient failures that eventually complete.

## Proposed Protocol

Add `evaluation/run_retry_recovery_e2e.py`.

The protocol runs inside the `evaluation-runner` container and uses the real stack:

`Gateway -> Keycloak -> Kafka -> Orchestrator -> image workers -> MinIO -> OpenAI -> PDF export -> Gateway job state`

Default workload:

- 3 authenticated evaluation users.
- 1 project per user.
- 5 real PDS products per project.
- 15 total image analyses.
- Cold cache reset before the run.
- Admin event fetch after completion.
- Docker log capture for Gateway, Orchestrator, and evaluation-runner.

The protocol writes results to:

`evaluation/results/retry_recovery_e2e/`

Required outputs:

- `records.json`
- `records.csv`
- `summary.json`
- `events.json`
- `worker_timeline.json`
- `docker_logs/`
- `evaluation-results-table.txt`
- `retry-recovery-table.txt`
- `cost-throughput-comparison-table.txt`
- `thesis-interpretation-notes.txt`

## Fault Injection Model

Use deterministic evaluation-only transient faults. Faults must be enabled only by explicit environment variables, so normal development and production paths are unaffected.

Recommended first version:

- Inject one transient analyze/OpenAI-stage failure for one selected job/product, then allow the retry to succeed.
- Inject one transient storage/PDF/upload-stage failure for one selected job, then allow retry to succeed.
- Exercise Kafka publish retry where feasible through an evaluation-only gateway/orchestrator fault flag.
- Keep permanent bad-LID behavior in the existing failure protocol as a negative control, not as MTTR recovery evidence.

Fault injection must record enough evidence to calculate recovery:

- `fault_id`
- `job_id`
- `product_lid` when applicable
- `stage`
- `failure_injected_at`
- `retry_attempts_observed`
- `recovered_at`
- `final_status`
- `error_excerpt`

## Metrics

The protocol must compute per-job and aggregate metrics:

- `completed_jobs`
- `failed_jobs`
- `failure_rate`
- `image_count`
- `job_duration_seconds`
- `throughput_images_per_minute`
- `worker_count`
- `distinct_worker_count`
- `max_concurrent_workers_observed`
- `cost_usd`
- `retry_attempts_observed`
- `mttr_seconds`

MTTR definition for this evaluation:

`mttr_seconds = recovered_at - failure_injected_at`

Only transient failures that recover to `COMPLETED` contribute to MTTR. Permanent validation failures, such as a bad LID, do not contribute to MTTR because they are expected not to recover.

## Thesis Tables

Generate plain-text tables so the thesis chapter can be updated without editing the `.docx` automatically.

`evaluation-results-table.txt` should summarize the heavyweight run:

- users
- projects
- images
- completed jobs
- failed jobs
- failure rate
- duration
- throughput
- max concurrent workers
- total cost

`retry-recovery-table.txt` should summarize each injected transient fault:

- fault id
- affected stage
- job id
- product id or report id
- attempts observed
- failure time
- recovery time
- MTTR seconds
- final status

`cost-throughput-comparison-table.txt` should compare proposed concurrent/retry run against existing sequential reference where available:

- reference duration
- proposed duration
- saved seconds
- saved percent
- reference throughput
- proposed throughput
- cost delta
- worker delta

`thesis-interpretation-notes.txt` should provide concise prose for the evaluation chapter:

- what the protocol proves
- how retry/recovery was measured
- why permanent bad-LID failures are excluded from MTTR
- what limitations remain
- how LangSmith/job events support stage-level observability

## Logging and Evidence Capture

The protocol should preserve raw evidence, not only summaries.

Capture:

- Gateway admin job events for all submitted jobs.
- Worker progress with worker IDs, partitions, offsets, timestamps, and per-image statuses.
- Docker logs for `gateway`, `orchtr`, and `evaluation-runner`.
- Existing chart artifacts when `evaluation.charts` is regenerated.
- A run manifest with exact workload, selected fault targets, start/end timestamps, and environment flags.

Secrets must be sanitized in copied logs and text outputs. Bearer tokens, passwords, and signed URLs should be redacted or truncated before being written into thesis-ready `.txt` files.

## Data Flow

1. Evaluation runner performs a cold reset using `evaluation.reset_eval_state --apply`.
2. Evaluation runner enables deterministic fault flags for the run.
3. Evaluation runner ensures evaluation users exist through Keycloak.
4. Evaluation runner submits three project jobs through Gateway.
5. Orchestrator processes image tasks and triggers controlled transient failures.
6. Existing retry mechanisms retry failed transient operations.
7. Evaluation runner polls jobs until terminal status or timeout.
8. Evaluation runner fetches admin events and worker progress.
9. Evaluation runner computes retry recovery metrics and MTTR.
10. Evaluation runner writes JSON, CSV, Markdown-compatible summaries, and `.txt` tables.

## Acceptance Criteria

- The protocol starts from a cold cache.
- The default run processes 3 users, 3 projects, and 15 images.
- At least two controlled transient faults are injected.
- At least one injected transient failure recovers to `COMPLETED`.
- `mttr_seconds` is non-zero for recovered transient failures.
- Permanent bad-LID failure remains excluded from MTTR.
- JSON, CSV, and `.txt` table outputs are generated.
- Docker logs and admin job events are preserved.
- The protocol can be run from Compose with one command:

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.run_retry_recovery_e2e
```

## Out of Scope

- Editing the thesis `.docx` file automatically.
- Building a full chaos proxy or random fault injection framework.
- Running unbounded stress tests such as 50+ images by default.
- Treating permanent validation failures as recovered failures.
- Adding frontend UI changes for this evaluation.

## Open Implementation Notes

- Reuse existing helpers from `evaluation.eval_lib` and `evaluation.run_multi_user_project_e2e` where possible.
- Reuse existing reset, event parsing, timeline, summary, chart, and report utilities.
- Add only evaluation-mode fault hooks to application services, guarded by environment variables.
- Keep the protocol deterministic so repeated thesis runs are comparable.
