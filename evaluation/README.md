# Evaluation Protocols

This folder contains API-level protocols for thesis solution verification.

## Start stack

```bash
# edit root .env next to docker-compose.yml with real OpenAI, Qdrant,
# LangSmith, Keycloak, Kafka, and MinIO values
docker compose --profile eval up -d --build
```

## Run protocols inside the Compose network

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.run_all --clean
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.multi_user_project.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.functional.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.job_e2e.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.failure.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.load.run --concurrency 2 --repetitions 1
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.idempotency.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.limits.run --attempts 6
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.sequential_reference.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.report
```

Each protocol lives under `evaluation/protocols/<protocol>/`. Results are written next to the protocol under `evaluation/protocols/<protocol>/results/`, and the combined text report is `evaluation/summary.md`. Chart generation is intentionally not part of the evaluation runner.

## Thesis-default multi-user protocol

Default workload:

- 3 authenticated users.
- 1 project per user.
- 5 real PDS images per project.
- 15 total real image analyses.
- Real Gateway, Keycloak, Kafka, Orchestrator, MinIO, OpenAI, Qdrant, and LangSmith path.

Required environment:

- `OPENAI_API_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `LANGSMITH_API_KEY` or `LANGCHAIN_API_KEY`
- `EVAL_PASSWORD`: password used for auto-created evaluation users unless `EVAL_PASSWORDS` is provided.
- `KEYCLOAK_ADMIN`
- `KEYCLOAK_ADMIN_PASSWORD`

Optional environment:

- `EVAL_USERS`: comma-separated evaluation usernames; default is `researcher,researcher-2,researcher-3`.
- `EVAL_PASSWORDS`: comma-separated passwords matching `EVAL_USERS`; if omitted, `EVAL_PASSWORD` is reused for each user.
- `EVAL_ADMIN_USERNAME`: administrative evaluation username; default is `admin-user`.
- `EVAL_ADMIN_PASSWORD`: administrative evaluation password; if omitted, `KEYCLOAK_ADMIN_PASSWORD` is used.

Run:

```bash
docker compose --profile eval up -d --build
docker compose --profile eval exec -T evaluation-runner python -m evaluation.run_all --clean
```

Each protocol can also be run independently with one command:

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --apply
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.multi_user_project.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.sequential_reference.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.single_user_5_image_probe.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.functional.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.failure.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.idempotency.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.limits.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.load.run
```

## Heavy 45-image protocols

The default `run_all` command intentionally does not run the heavy 45-image protocols. They are manual stress/reference protocols built from `evaluation/cases_45.yml`:

- 9 jobs.
- 5 unique real Mastcam-Z calibrated LIDs per job.
- 45 total images.

Run the concurrent worker protocol first, then the sequential reference protocol:

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --cases evaluation/cases_45.yml
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --cases evaluation/cases_45.yml --apply
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.multi_user_project_45.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --cases evaluation/cases_45.yml --apply
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.sequential_reference_45.run
docker compose --profile eval exec -T evaluation-runner python -m evaluation.report
```

The concurrent protocol respects Gateway's active job constraints. With the default three evaluation users it submits jobs in batches of three. If more users are configured, `--max-concurrent-jobs` can raise the submission batch size up to the Gateway limit.

Heavy outputs:

- `evaluation/protocols/multi_user_project_45/results/records.json`
- `evaluation/protocols/multi_user_project_45/results/records.csv`
- `evaluation/protocols/multi_user_project_45/results/summary.json`
- `evaluation/protocols/multi_user_project_45/results/worker_timeline.json`
- `evaluation/protocols/multi_user_project_45/results/events.json`
- `evaluation/protocols/sequential_reference_45/results/records.json`
- `evaluation/protocols/sequential_reference_45/results/records.csv`
- `evaluation/protocols/sequential_reference_45/results/summary.json`
- `evaluation/protocols/sequential_reference_45/results/comparison.json`

Primary outputs:

- `evaluation/protocols/multi_user_project/results/records.json`
- `evaluation/protocols/multi_user_project/results/records.csv`
- `evaluation/protocols/multi_user_project/results/summary.json`
- `evaluation/protocols/multi_user_project/results/worker_timeline.json`
- `evaluation/protocols/multi_user_project/results/events.json`
- `evaluation/protocols/sequential_reference/results/comparison.json`
- `evaluation/reset_manifest.json`
- `evaluation/summary.md`

Interpretation:

- `distinct_worker_count = 1` means the workload effectively used one image worker.
- `distinct_worker_count > 1` proves multiple worker IDs processed the workload.
- `max_concurrent_workers_observed > 1` proves overlap, not just sequential use of different workers.

## Single-user worker probe

Use this diagnostic when checking whether one user with one 5-image project uses multiple workers:

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.protocols.single_user_5_image_probe.run
```

Then regenerate the report:

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.report
```

If using the ad-hoc probe from the current results, inspect:

- `evaluation/protocols/single_user_5_image_probe/results/record.json`
- `evaluation/protocols/single_user_5_image_probe/results/worker_timeline.json`

The latest probe completed 5 images for one user with `max_concurrent_workers_observed = 4`.

## Cold-run reset

Use reset before each cold comparison run. The first command is a dry run and writes a manifest of objects that would be deleted. The second command applies deletion.

```bash
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state
docker compose --profile eval exec -T evaluation-runner python -m evaluation.reset_eval_state --apply
```

The reset protocol removes MinIO artifacts for the deterministic evaluation LIDs and old evaluation report objects referenced by result files. It targets:

- raw/metadata objects under `mastcamz/sol=...`;
- transformed images under `transformed/mastcamz/sol=...`;
- analysis cache under `analysis/mastcamz/sol=...`;
- generated previews for selected products;
- report PDFs under `reports/{job_id}/`.

The manifest includes `object_count`, `object_counts_by_prefix`, and the exact object keys. The dry run should be reviewed before `--apply`; it proves whether a comparison would otherwise be cache-warmed.

For a strict cold sequential-reference/proposed comparison, run reset before the proposed concurrent protocol and again before the sequential reference protocol.

## Metrics

The protocol captures stage latency where exposed, total duration, throughput, failure rate, MTTR proxy, cost, and cost impact of platform limits.
