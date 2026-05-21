from __future__ import annotations

import csv
import json
import math
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


def now() -> float:
    return time.time()


def round_float(value: float | None, digits: int = 4) -> float | None:
    if value is None or math.isnan(value):
        return None
    return round(float(value), digits)


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    jobs = len(records)
    images = sum(int(r.get("image_count") or 0) for r in records)
    failed_jobs = sum(1 for r in records if str(r.get("status", "")).upper() == "FAILED")
    durations = [float(r["finished_at"]) - float(r["started_at"]) for r in records if r.get("started_at") is not None and r.get("finished_at") is not None]
    starts = [float(r["started_at"]) for r in records if r.get("started_at") is not None]
    finishes = [float(r["finished_at"]) for r in records if r.get("finished_at") is not None]
    work_duration = sum(durations)
    wall_clock_duration = (max(finishes) - min(starts)) if starts and finishes else work_duration
    throughput = (images / wall_clock_duration * 60.0) if wall_clock_duration > 0 else 0.0
    costs = [float(r.get("cost_usd") or 0.0) for r in records]

    mttrs = []
    for r in records:
        if r.get("failed_at") is not None and r.get("recovered_at") is not None:
            mttrs.append(float(r["recovered_at"]) - float(r["failed_at"]))

    stage_values: dict[str, list[float]] = {}
    for r in records:
        for stage, value in (r.get("stage_latencies_ms") or {}).items():
            stage_values.setdefault(stage, []).append(float(value))

    return {
        "jobs": jobs,
        "images": images,
        "failed_jobs": failed_jobs,
        "failure_rate": round_float(failed_jobs / jobs if jobs else 0.0),
        "duration_seconds": round_float(wall_clock_duration),
        "total_work_seconds": round_float(work_duration),
        "throughput_images_per_minute": round_float(throughput, 2),
        "mttr_seconds": round_float(sum(mttrs) / len(mttrs) if mttrs else 0.0),
        "total_cost_usd": round_float(sum(costs), 6),
        "stage_latency_ms": {
            stage: {
                "min": round_float(min(values), 2),
                "max": round_float(max(values), 2),
                "avg": round_float(sum(values) / len(values), 2),
            }
            for stage, values in sorted(stage_values.items())
        },
    }


def summarize_retry_recovery_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    recovered_mttrs = []
    retry_attempts = 0

    for record in records:
        retry_attempts += int(record.get("retry_attempts_observed") or 0)
        if (
            str(record.get("final_status", "")).upper() == "COMPLETED"
            and record.get("failure_injected_at") is not None
            and record.get("recovered_at") is not None
        ):
            recovered_mttrs.append(float(record["recovered_at"]) - float(record["failure_injected_at"]))

    faults = len(records)
    recovered_faults = len(recovered_mttrs)
    return {
        "faults": faults,
        "recovered_faults": recovered_faults,
        "unrecovered_faults": faults - recovered_faults,
        "retry_attempts_observed": retry_attempts,
        "mttr_seconds": round_float(sum(recovered_mttrs) / recovered_faults if recovered_faults else 0.0),
    }


def compare_reference_cost_impact(reference: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    reference_cost = float(reference.get("total_cost_usd") or 0.0)
    proposed_cost = float(proposed.get("total_cost_usd") or 0.0)
    reference_duration = float(reference.get("duration_seconds") or 0.0)
    proposed_duration = float(proposed.get("duration_seconds") or 0.0)
    proposed_images = int(proposed.get("images") or 0)
    avg_cost = proposed_cost / proposed_images if proposed_images else 0.0
    rejected = int(proposed.get("rejected_images") or 0)
    saved = reference_cost - proposed_cost
    return {
        "reference_cost_usd": round_float(reference_cost, 6),
        "proposed_cost_usd": round_float(proposed_cost, 6),
        "cost_saved_usd": round_float(saved, 6),
        "cost_saved_percent": round_float((saved / reference_cost * 100.0) if reference_cost else 0.0, 2),
        "duration_delta_seconds": round_float(proposed_duration - reference_duration, 4),
        "estimated_avoided_cost_usd": round_float(avg_cost * rejected, 6),
    }


def compare_protocol_summaries(reference: dict[str, Any], proposed: dict[str, Any]) -> dict[str, Any]:
    reference_duration = float(reference.get("duration_seconds") or 0.0)
    proposed_duration = float(proposed.get("duration_seconds") or 0.0)
    reference_cost = float(reference.get("total_cost_usd") or 0.0)
    proposed_cost = float(proposed.get("total_cost_usd") or 0.0)
    duration_saved = reference_duration - proposed_duration
    return {
        "reference_duration_seconds": round_float(reference_duration),
        "proposed_duration_seconds": round_float(proposed_duration),
        "duration_saved_seconds": round_float(duration_saved),
        "duration_saved_percent": round_float((duration_saved / reference_duration * 100.0) if reference_duration else 0.0, 2),
        "reference_cost_usd": round_float(reference_cost, 6),
        "proposed_cost_usd": round_float(proposed_cost, 6),
        "cost_delta_usd": round_float(proposed_cost - reference_cost, 6),
        "reference_throughput_images_per_minute": round_float(float(reference.get("throughput_images_per_minute") or 0.0), 2),
        "proposed_throughput_images_per_minute": round_float(float(proposed.get("throughput_images_per_minute") or 0.0), 2),
        "worker_count_delta": int(proposed.get("distinct_worker_count") or 0) - int(reference.get("distinct_worker_count") or 0),
        "max_concurrent_worker_delta": int(proposed.get("max_concurrent_workers_observed") or 0) - int(reference.get("max_concurrent_workers_observed") or 0),
    }


def assert_protocol_condition(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_cases(path: str | Path) -> list[dict[str, Any]]:
    text = Path(path).read_text(encoding="utf-8")
    if path and str(path).endswith(".json"):
        data = json.loads(text)
    else:
        data = _parse_simple_cases_yml(text)
    cases = data.get("cases", data if isinstance(data, list) else [])
    if not isinstance(cases, list) or not cases:
        raise ValueError(f"No cases found in {path}")
    return cases


def load_case_groups(path: str | Path) -> dict[str, list[dict[str, Any]]]:
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith(".json"):
        data = json.loads(text)
        groups = data.get("groups", {})
        return _validate_case_groups(groups, path)

    groups: dict[str, list[dict[str, Any]]] = {}
    current_group: str | None = None
    current_case: dict[str, str] | None = None
    in_groups = False

    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped == "groups:":
            in_groups = True
            current_group = None
            continue
        if stripped == "failure:":
            if current_group and current_case:
                groups[current_group].append(current_case)
                current_case = None
                current_group = None
            break
        if not in_groups:
            continue
        if raw.startswith("  ") and not raw.startswith("    ") and stripped.endswith(":"):
            if current_group and current_case:
                groups[current_group].append(current_case)
            current_group = stripped[:-1]
            groups[current_group] = []
            current_case = None
            continue
        if stripped.startswith("- "):
            if current_group is None:
                raise ValueError(f"Case item found before group in {path}")
            if current_case:
                groups[current_group].append(current_case)
            current_case = {}
            remainder = stripped[2:].strip()
            if remainder:
                k, v = remainder.split(":", 1)
                current_case[k.strip()] = v.strip().strip('"')
            continue
        if current_case is not None and ":" in stripped:
            k, v = stripped.split(":", 1)
            current_case[k.strip()] = v.strip().strip('"')

    if current_group and current_case:
        groups[current_group].append(current_case)

    return _validate_case_groups(groups, path)


def _validate_case_groups(groups: Any, path: str | Path) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(groups, dict) or not groups:
        raise ValueError(f"No groups found in {path}")
    validated: dict[str, list[dict[str, Any]]] = {}
    for group_name, cases in groups.items():
        if not isinstance(cases, list):
            raise ValueError(f"Group {group_name!r} in {path} must be a list of cases")
        if not cases:
            raise ValueError(f"Group {group_name!r} in {path} must contain at least one case")
        validated_cases: list[dict[str, Any]] = []
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                raise ValueError(f"Case {index} in group {group_name!r} in {path} must be a dict")
            case_id = case.get("id")
            lid = case.get("lid")
            if not isinstance(case_id, str) or not case_id.strip():
                raise ValueError(f"Case {index} in group {group_name!r} in {path} must have a nonblank id")
            if not isinstance(lid, str) or not lid.strip():
                raise ValueError(f"Case {index} in group {group_name!r} in {path} must have a nonblank lid")
            validated_cases.append(case)
        validated[str(group_name)] = validated_cases
    return validated


def parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized).timestamp()


def parse_job_events(job_id: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    image_progress = []
    transitions = []
    parse_errors = []
    for event in events:
        transitions.append({
            "stage": event.get("stage"),
            "status": event.get("status"),
            "created_at": event.get("created_at"),
            "duration_ms": event.get("duration_ms"),
        })
        payload_text = event.get("payload_json") or "{}"
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError as exc:
            parse_errors.append({
                "stage": event.get("stage"),
                "created_at": event.get("created_at"),
                "error": exc.msg,
                "payload_excerpt": sanitize_error_text(str(payload_text), limit=300),
            })
            payload = {}
        if not isinstance(payload, dict):
            parse_errors.append({
                "stage": event.get("stage"),
                "created_at": event.get("created_at"),
                "error": f"payload_json decoded to {type(payload).__name__}, expected object",
                "payload_excerpt": sanitize_error_text(str(payload_text), limit=300),
            })
            payload = {}
        progress = payload.get("image_progress")
        if isinstance(progress, dict):
            item = dict(progress)
            item.setdefault("event_at", event.get("created_at"))
            image_progress.append(item)
    return {"job_id": job_id, "transitions": transitions, "image_progress": image_progress, "parse_errors": parse_errors}


def summarize_worker_timeline(parsed_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    workers: set[str] = set()
    images_per_worker: dict[str, set[str]] = {}
    intervals: list[tuple[float, float, str, str]] = []

    for job in parsed_jobs:
        starts: dict[tuple[str, str], float] = {}
        for progress in job.get("image_progress", []):
            worker = str(progress.get("worker_id"))
            lid = str(progress.get("lid"))
            status = str(progress.get("status"))
            event_ts = parse_iso(progress.get("event_at"))
            if worker == "None" or lid == "None" or event_ts is None:
                continue
            workers.add(worker)
            key = (worker, lid)
            if status == "processing":
                starts[key] = event_ts
            elif status in {"done", "error"}:
                images_per_worker.setdefault(worker, set()).add(lid)
                start_ts = starts.get(key, event_ts)
                intervals.append((start_ts, event_ts, worker, lid))

    points: list[tuple[float, int]] = []
    for start_ts, end_ts, _worker, _lid in intervals:
        points.append((start_ts, 1))
        points.append((end_ts, -1))
    active = 0
    max_active = 0
    for _ts, delta in sorted(points, key=lambda x: (x[0], x[1])):
        active += delta
        max_active = max(max_active, active)

    return {
        "distinct_worker_count": len(workers),
        "workers": sorted(workers),
        "images_per_worker": {worker: len(lids) for worker, lids in sorted(images_per_worker.items())},
        "max_concurrent_workers_observed": max_active,
        "intervals": [
            {"started_at": start, "finished_at": end, "worker_id": worker, "lid": lid}
            for start, end, worker, lid in intervals
        ],
    }


def _parse_simple_cases_yml(text: str) -> dict[str, Any]:
    cases: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line == "cases:":
            continue
        if line.startswith("- "):
            if current:
                cases.append(current)
            current = {}
            line = line[2:].strip()
            if line:
                k, v = line.split(":", 1)
                current[k.strip()] = v.strip().strip('"')
            continue
        if current is not None and ":" in line:
            k, v = line.split(":", 1)
            current[k.strip()] = v.strip().strip('"')
    if current:
        cases.append(current)
    return {"cases": cases}


def sanitize_error_text(text: str, limit: int = 1000) -> str:
    sanitized = str(text)
    sanitized = re.sub(
        r"(?i)\bX-Amz-(?:Signature|Credential|Security-Token)=[^&\s,;\"'}]+",
        "[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;\"'}]+",
        r"\1[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(bearer\s+)[^\s,;\"'}]+",
        r"\1[REDACTED]",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(\"?[\w-]*password[\w-]*\"?\s*[:=]\s*\")([^\"]*)(\")",
        r"\1[REDACTED]\3",
        sanitized,
    )
    sanitized = re.sub(
        r"(?i)(\b[\w-]*password[\w-]*\b\s*[:=]\s*)([^\s,;\"'}]+)",
        r"\1[REDACTED]",
        sanitized,
    )
    if len(sanitized) > limit:
        return sanitized[:limit] + "..."
    return sanitized


def _table_cell(value: Any) -> str:
    sanitized = sanitize_error_text("" if value is None else str(value), limit=220)
    return re.sub(r"[\r\n\t]+", " ", sanitized)


def render_plain_text_table(title: str, columns: list[str], rows: list[dict[str, Any]]) -> str:
    sanitized_rows = [
        [
            _table_cell(row.get(column))
            for column in columns
        ]
        for row in rows
    ]
    widths = [
        max([len(str(column))] + [len(row[index]) for row in sanitized_rows])
        for index, column in enumerate(columns)
    ]

    def format_row(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[index]) for index, value in enumerate(values))

    lines = [
        _table_cell(title),
        format_row([str(column) for column in columns]),
        "-+-".join("-" * width for width in widths),
    ]
    lines.extend(format_row(row) for row in sanitized_rows)
    return "\n".join(lines) + "\n"


def http_json(method: str, url: str, payload: Any | None = None, headers: dict[str, str] | None = None, timeout: int = 600) -> Any:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
    attempts = 3
    delays = (0.0, 2.0)
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            last_error = exc
            if exc.code < 500 and exc.code != 429:
                raise RuntimeError(sanitize_error_text(f"{method} {url} failed: HTTP {exc.code}: {body}")) from exc
            if attempt >= attempts:
                raise RuntimeError(sanitize_error_text(f"{method} {url} failed: HTTP {exc.code}: {body}")) from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt >= attempts:
                raise RuntimeError(sanitize_error_text(f"{method} {url} failed: {exc}")) from exc

        delay = delays[min(attempt - 1, len(delays) - 1)] if delays else 0.0
        if delay > 0:
            time.sleep(delay)

    raise RuntimeError(sanitize_error_text(f"{method} {url} failed: {last_error}"))


def keycloak_token(base_url: str, realm: str, username: str, password: str, client_id: str) -> str:
    url = f"{base_url.rstrip('/')}/realms/{realm}/protocol/openid-connect/token"
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": client_id,
        "username": username,
        "password": password,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def _keycloak_admin_token(base_url: str) -> str:
    username = env("KEYCLOAK_ADMIN", "")
    password = env("KEYCLOAK_ADMIN_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("KEYCLOAK_ADMIN and KEYCLOAK_ADMIN_PASSWORD are required to create evaluation users")
    url = f"{base_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
    body = urllib.parse.urlencode({
        "grant_type": "password",
        "client_id": "admin-cli",
        "username": username,
        "password": password,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["access_token"]


def resolve_eval_users(default_users: str = "researcher,researcher-2,researcher-3") -> tuple[list[str], list[str]]:
    users = [item.strip() for item in env("EVAL_USERS", default_users).split(",") if item.strip()]
    passwords = [item.strip() for item in env("EVAL_PASSWORDS", "").split(",") if item.strip()]
    if not passwords:
        password = env("EVAL_PASSWORD", "")
        if password:
            passwords = [password for _ in users]
    if len(users) != len(passwords):
        raise SystemExit("Provide EVAL_PASSWORD or EVAL_PASSWORDS matching EVAL_USERS")
    return users, passwords


def resolve_admin_credentials() -> tuple[str, str]:
    username = env("EVAL_ADMIN_USERNAME", "admin-user")
    password = env("EVAL_ADMIN_PASSWORD", "") or env("KEYCLOAK_ADMIN_PASSWORD", "") or env("EVAL_PASSWORD", "")
    if not username or not password:
        raise SystemExit("Provide EVAL_ADMIN_PASSWORD or KEYCLOAK_ADMIN_PASSWORD for admin event access")
    return username, password


def ensure_keycloak_eval_users(
    base_url: str,
    realm: str,
    client_id: str,
    users: list[str],
    passwords: list[str],
    role_name: str = "RESEARCHER",
) -> None:
    missing: list[tuple[str, str]] = []
    for username, password in zip(users, passwords):
        try:
            keycloak_token(base_url, realm, username, password, client_id)
        except Exception:
            missing.append((username, password))
    if not missing:
        return

    admin_token = _keycloak_admin_token(base_url)
    headers = auth_headers(admin_token)
    admin_base = f"{base_url.rstrip('/')}/admin/realms/{realm}"
    role = http_json("GET", f"{admin_base}/roles/{urllib.parse.quote(role_name)}", headers=headers, timeout=60)

    for username, password in missing:
        query = urllib.parse.urlencode({"username": username, "exact": "true"})
        existing = http_json("GET", f"{admin_base}/users?{query}", headers=headers, timeout=60)
        if not isinstance(existing, list):
            existing = []
        if existing:
            user_id = existing[0]["id"]
            profile = {
                "enabled": True,
                "firstName": username.replace("-", " ").title(),
                "lastName": "Evaluation",
                "email": f"{username}@example.local",
                "emailVerified": True,
                "requiredActions": [],
            }
            http_json("PUT", f"{admin_base}/users/{user_id}", profile, headers=headers, timeout=60)
        else:
            profile = {
                "username": username,
                "enabled": True,
                "firstName": username.replace("-", " ").title(),
                "lastName": "Evaluation",
                "email": f"{username}@example.local",
                "emailVerified": True,
                "requiredActions": [],
            }
            http_json("POST", f"{admin_base}/users", profile, headers=headers, timeout=60)
            existing = http_json("GET", f"{admin_base}/users?{query}", headers=headers, timeout=60)
            if not isinstance(existing, list) or not existing:
                raise RuntimeError(f"Keycloak user creation did not return user {username}")
            user_id = existing[0]["id"]

        credential = {"type": "password", "value": password, "temporary": False}
        http_json("PUT", f"{admin_base}/users/{user_id}/reset-password", credential, headers=headers, timeout=60)
        http_json("POST", f"{admin_base}/users/{user_id}/role-mappings/realm", [role], headers=headers, timeout=60)

        keycloak_token(base_url, realm, username, password, client_id)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _atomic_write(path: str | Path, writer: Any, newline: str | None = None) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            dir=p.parent,
            prefix=f".{p.name}.",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
            newline=newline,
        ) as fh:
            tmp_path = Path(fh.name)
            writer(fh)
            fh.flush()
            os.fsync(fh.fileno())
        tmp_path.replace(p)
        p.chmod(0o644)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def write_json(path: str | Path, payload: Any) -> None:
    _atomic_write(path, lambda fh: fh.write(json.dumps(payload, indent=2, sort_keys=True)))


def write_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        _atomic_write(path, lambda fh: fh.write(""))
        return
    fields = sorted({k for row in rows for k in row.keys()})

    def _write(fh: Any) -> None:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    _atomic_write(path, _write, newline="")


def env(name: str, default: str) -> str:
    return os.getenv(name, default)
