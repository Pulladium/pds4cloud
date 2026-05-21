import json
import os
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class EvalFault:
    fault_id: str
    stage: str
    job_id: str
    lid: str | None
    failures: int
    duplicates: int


class EvalFaultRegistry:
    def __init__(self, faults: list[EvalFault] | None = None):
        self._faults = faults or []
        self._attempts: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    @classmethod
    def from_env(cls) -> "EvalFaultRegistry":
        raw_faults = os.environ.get("EVAL_FAULTS")
        if raw_faults is None:
            return cls()

        raw_faults = raw_faults.strip()
        if not raw_faults:
            return cls()

        fault_specs = json.loads(raw_faults)
        if not isinstance(fault_specs, list):
            raise ValueError("EVAL_FAULTS must be a JSON list")

        if not all(isinstance(spec, dict) for spec in fault_specs):
            raise ValueError("EVAL_FAULTS entries must be JSON objects")

        faults = [
            EvalFault(
                fault_id=spec["fault_id"],
                stage=spec["stage"],
                job_id=spec["job_id"],
                lid=spec.get("lid"),
                failures=int(spec.get("failures", 0)),
                duplicates=int(spec.get("duplicates", 0)),
            )
            for spec in fault_specs
        ]
        return cls(faults)

    def should_fail(
        self,
        stage: str,
        job_id: str,
        lid: str | None = None,
    ) -> dict[str, object] | None:
        return self._consume(stage, job_id, lid, "failures")

    def should_duplicate(
        self,
        stage: str,
        job_id: str,
        lid: str | None = None,
    ) -> dict[str, object] | None:
        return self._consume(stage, job_id, lid, "duplicates")

    def _consume(
        self,
        stage: str,
        job_id: str,
        lid: str | None,
        limit_attr: str,
    ) -> dict[str, object] | None:
        with self._lock:
            for fault in self._faults:
                if not self._matches(fault, stage, job_id, lid):
                    continue

                limit = getattr(fault, limit_attr)
                if limit <= 0:
                    continue

                attempt_key = (limit_attr, fault.fault_id)
                attempt = self._attempts.get(attempt_key, 0) + 1
                if attempt > limit:
                    continue

                self._attempts[attempt_key] = attempt
                return {
                    "fault_id": fault.fault_id,
                    "stage": fault.stage,
                    "job_id": job_id,
                    "lid": lid if lid is not None else fault.lid,
                    "attempt": attempt,
                    "failures": fault.failures,
                    "duplicates": fault.duplicates,
                }

        return None

    @staticmethod
    def _matches(
        fault: EvalFault,
        stage: str,
        job_id: str,
        lid: str | None,
    ) -> bool:
        return (
            fault.stage == stage
            and (not fault.job_id or fault.job_id == job_id)
            and (fault.lid is None or fault.lid == lid)
        )


_registry: EvalFaultRegistry | None = None
_registry_lock = threading.Lock()


def get_eval_fault_registry() -> EvalFaultRegistry:
    global _registry

    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = EvalFaultRegistry.from_env()

    return _registry
