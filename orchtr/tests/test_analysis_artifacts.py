from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from database import Base, engine, SessionLocal
from models import AnalysisArtifact
from services.analysis_artifacts import (
    reserve_analysis,
    mark_ready,
    mark_in_report,
    release_to_ready,
    mark_evictable_and_prune,
    ready_artifacts_for_scope,
    latest_cache_for_product,
)


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_reserve_analysis_creates_versioned_reserved_artifact():
    db = SessionLocal()
    artifact = reserve_analysis(
        db,
        product_lid="urn:test:product",
        photo_id="PHOTO1",
        sol="00001",
        project_id="project-1",
        job_id="job-1",
        user_id="user-1",
        model="gpt-4o",
    )

    assert artifact.status == "RESERVED"
    assert artifact.product_lid == "urn:test:product"
    assert artifact.user_id == "user-1"
    assert artifact.result_path == f"analysis/mastcamz/sol=00001/PHOTO1/{artifact.id}/result.json"
    assert artifact.result_path != ""


def test_reserve_analysis_stores_none_for_missing_model():
    db = SessionLocal()
    artifact = reserve_analysis(
        db,
        product_lid="urn:test:product",
        photo_id="PHOTO1",
        sol="00001",
        project_id="project-1",
        job_id="job-1",
        user_id="user-1",
        model=None,
    )

    assert artifact.model is None


def test_mark_ready_and_in_report_lifecycle():
    db = SessionLocal()
    artifact = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-1", "job-1", "user-1", "gpt-4o")

    mark_ready(db, artifact.id)
    assert db.get(AnalysisArtifact, artifact.id).status == "READY"

    mark_in_report(db, [artifact.id])
    assert db.get(AnalysisArtifact, artifact.id).status == "IN_REPORT"

    release_to_ready(db, [artifact.id])
    assert db.get(AnalysisArtifact, artifact.id).status == "READY"


def test_mark_ready_missing_id_raises_value_error():
    db = SessionLocal()

    with pytest.raises(ValueError):
        mark_ready(db, "missing-analysis-id")


def test_mark_in_report_rejects_non_ready_artifact():
    db = SessionLocal()
    artifact = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-1", "job-1", "user-1", "gpt-4o")

    with pytest.raises(ValueError):
        mark_in_report(db, [artifact.id])


def test_mark_evictable_and_prune_rejects_non_in_report_artifact():
    db = SessionLocal()
    storage = MagicMock()
    artifact = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-1", "job-1", "user-1", "gpt-4o")
    mark_ready(db, artifact.id)

    with pytest.raises(ValueError):
        mark_evictable_and_prune(db, [artifact.id], storage=storage)


def test_mark_evictable_prunes_only_oldest_evictable_artifacts():
    db = SessionLocal()
    storage = MagicMock()
    ids = []
    for idx in range(7):
        artifact = reserve_analysis(db, "urn:test:product", f"PHOTO{idx}", "00001", f"project-{idx}", f"job-{idx}", f"user-{idx}", "gpt-4o")
        mark_ready(db, artifact.id)
        mark_in_report(db, [artifact.id])
        mark_evictable_and_prune(db, [artifact.id], storage=storage, now=datetime(2026, 5, 14) + timedelta(seconds=idx))
        ids.append(artifact.id)

    rows = db.query(AnalysisArtifact).filter(AnalysisArtifact.product_lid == "urn:test:product").all()
    evictable = [row for row in rows if row.status == "EVICTABLE"]
    failed = [row for row in rows if row.status == "FAILED"]

    assert len(evictable) == 5
    assert len(failed) == 2
    assert {row.id for row in failed} == set(ids[:2])
    assert storage.delete_object.call_count == 2


def test_retention_never_prunes_ready_or_in_report():
    db = SessionLocal()
    storage = MagicMock()
    protected_ready = reserve_analysis(db, "urn:test:product", "READY1", "00001", "project-r", "job-r", "user-r", "gpt-4o")
    mark_ready(db, protected_ready.id)
    protected_in_report = reserve_analysis(db, "urn:test:product", "REPORT1", "00001", "project-ir", "job-ir", "user-ir", "gpt-4o")
    mark_ready(db, protected_in_report.id)
    mark_in_report(db, [protected_in_report.id])

    for idx in range(6):
        artifact = reserve_analysis(db, "urn:test:product", f"EVICT{idx}", "00001", f"project-{idx}", f"job-{idx}", f"user-{idx}", "gpt-4o")
        mark_ready(db, artifact.id)
        mark_in_report(db, [artifact.id])
        mark_evictable_and_prune(db, [artifact.id], storage=storage, now=datetime(2026, 5, 14) + timedelta(seconds=idx))

    assert db.get(AnalysisArtifact, protected_ready.id).status == "READY"
    assert db.get(AnalysisArtifact, protected_in_report.id).status == "IN_REPORT"


def test_latest_cache_for_product_uses_metadata_not_storage_scan():
    db = SessionLocal()
    assert latest_cache_for_product(db, product_lid="urn:test:product") == {
        "status": "none",
        "analysis_id": None,
        "analyzed_at": None,
        "result_path": None,
    }

    analyzed_at = datetime(2026, 5, 14, 12, 0, 0)
    artifact = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-1", "job-1", "user-1", "gpt-4o")
    mark_ready(db, artifact.id, analyzed_at=analyzed_at)

    cache = latest_cache_for_product(db, product_lid="urn:test:product")

    assert cache["status"] == "cached"
    assert cache["analysis_id"] == artifact.id
    assert cache["analyzed_at"] == analyzed_at.isoformat()
    assert cache["result_path"] == artifact.result_path


def test_latest_completed_for_scope_reuses_same_project_user_product_only():
    db = SessionLocal()
    matching = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-1", "job-1", "user-1", "gpt-4o")
    other_user = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-1", "job-2", "user-2", "gpt-4o")
    other_project = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-2", "job-3", "user-1", "gpt-4o")
    reserved = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-1", "job-4", "user-1", "gpt-4o")
    evictable = reserve_analysis(db, "urn:test:product", "PHOTO1", "00001", "project-1", "job-5", "user-1", "gpt-4o")
    mark_ready(db, matching.id, analyzed_at=datetime(2026, 5, 14, 12, 0, 0))
    mark_ready(db, other_user.id, analyzed_at=datetime(2026, 5, 14, 13, 0, 0))
    mark_ready(db, other_project.id, analyzed_at=datetime(2026, 5, 14, 14, 0, 0))
    mark_ready(db, evictable.id, analyzed_at=datetime(2026, 5, 14, 15, 0, 0))
    mark_in_report(db, [evictable.id])
    mark_evictable_and_prune(db, [evictable.id], storage=MagicMock(), now=datetime(2026, 5, 14, 16, 0, 0))

    reusable = ready_artifacts_for_scope(db, "urn:test:product", "project-1", "user-1")

    assert [artifact.id for artifact in reusable] == [matching.id]
    assert db.get(AnalysisArtifact, reserved.id).status == "RESERVED"
