from datetime import datetime
from uuid import uuid4

from models import AnalysisArtifact


RESERVED = "RESERVED"
READY = "READY"
IN_REPORT = "IN_REPORT"
EVICTABLE = "EVICTABLE"
FAILED = "FAILED"
MAX_EVICTABLE_PER_PRODUCT = 5


def reserve_analysis(db, product_lid, photo_id, sol, project_id, job_id, user_id, model):
    analysis_id = str(uuid4())
    artifact = AnalysisArtifact(
        id=analysis_id,
        product_lid=product_lid,
        photo_id=photo_id,
        sol=sol,
        project_id=project_id,
        job_id=job_id,
        user_id=user_id,
        model=model,
        status=RESERVED,
        result_path=f"analysis/mastcamz/sol={sol}/{photo_id}/{analysis_id}/result.json",
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def mark_ready(db, analysis_id, analyzed_at=None):
    artifact = db.get(AnalysisArtifact, analysis_id)
    if artifact is None:
        raise ValueError(f"Analysis artifact {analysis_id} not found")

    now = analyzed_at or datetime.utcnow()
    artifact.status = READY
    artifact.completed_at = now
    artifact.updated_at = now
    artifact.error = None
    db.commit()
    db.refresh(artifact)
    return artifact


def mark_failed(db, analysis_id, error):
    artifact = db.get(AnalysisArtifact, analysis_id)
    if artifact is None:
        return

    artifact.status = FAILED
    artifact.error = error
    artifact.updated_at = datetime.utcnow()
    db.commit()


def mark_in_report(db, analysis_ids):
    ids = list(analysis_ids)
    if not ids:
        return

    artifacts = db.query(AnalysisArtifact).filter(AnalysisArtifact.id.in_(ids)).all()
    now = datetime.utcnow()
    for artifact in artifacts:
        if artifact.status != READY:
            raise ValueError(f"Analysis artifact {artifact.id} is not READY")
        artifact.status = IN_REPORT
        artifact.updated_at = now

    db.commit()


def release_to_ready(db, analysis_ids):
    ids = list(analysis_ids)
    if not ids:
        return

    artifacts = db.query(AnalysisArtifact).filter(AnalysisArtifact.id.in_(ids)).all()
    now = datetime.utcnow()
    for artifact in artifacts:
        if artifact.status == IN_REPORT:
            artifact.status = READY
            artifact.updated_at = now

    db.commit()


def mark_evictable_and_prune(db, analysis_ids, storage, now=None):
    ids = list(analysis_ids)
    if not ids:
        return

    artifacts = db.query(AnalysisArtifact).filter(AnalysisArtifact.id.in_(ids)).all()
    timestamp = now or datetime.utcnow()
    product_lids = set()
    for artifact in artifacts:
        if artifact.status != IN_REPORT:
            raise ValueError(f"Analysis artifact {artifact.id} is not IN_REPORT")
        artifact.status = EVICTABLE
        artifact.evictable_at = timestamp
        artifact.updated_at = timestamp
        product_lids.add(artifact.product_lid)

    db.commit()

    for product_lid in product_lids:
        prune_evictable(db, product_lid, storage)


def prune_evictable(db, product_lid, storage):
    evictable = (
        db.query(AnalysisArtifact)
        .filter(
            AnalysisArtifact.product_lid == product_lid,
            AnalysisArtifact.status == EVICTABLE,
        )
        .order_by(
            AnalysisArtifact.evictable_at.asc(),
            AnalysisArtifact.updated_at.asc(),
            AnalysisArtifact.created_at.asc(),
        )
        .all()
    )
    excess = len(evictable) - MAX_EVICTABLE_PER_PRODUCT
    if excess <= 0:
        return

    now = datetime.utcnow()
    for artifact in evictable[:excess]:
        storage.delete_object(artifact.result_path)
        artifact.status = FAILED
        artifact.error = "evicted after PDF generation"
        artifact.updated_at = now

    db.commit()


def ready_artifacts_for_scope(db, product_lid, project_id, user_id):
    return (
        db.query(AnalysisArtifact)
        .filter(
            AnalysisArtifact.product_lid == product_lid,
            AnalysisArtifact.project_id == project_id,
            AnalysisArtifact.user_id == user_id,
            AnalysisArtifact.status == READY,
        )
        .order_by(
            AnalysisArtifact.completed_at.desc(),
            AnalysisArtifact.updated_at.desc(),
        )
        .all()
    )


def completed_artifacts_for_photo(db, sol, photo_id):
    return (
        db.query(AnalysisArtifact)
        .filter(
            AnalysisArtifact.sol == sol,
            AnalysisArtifact.photo_id == photo_id,
            AnalysisArtifact.status.in_([READY, IN_REPORT, EVICTABLE]),
        )
        .order_by(
            AnalysisArtifact.completed_at.desc(),
            AnalysisArtifact.updated_at.desc(),
        )
        .all()
    )


def latest_cache_for_product(db, product_lid):
    artifact = (
        db.query(AnalysisArtifact)
        .filter(
            AnalysisArtifact.product_lid == product_lid,
            AnalysisArtifact.status.in_([READY, IN_REPORT, EVICTABLE]),
        )
        .order_by(
            AnalysisArtifact.completed_at.desc(),
            AnalysisArtifact.updated_at.desc(),
        )
        .first()
    )
    if artifact is None:
        return {
            "status": "none",
            "analysis_id": None,
            "analyzed_at": None,
            "result_path": None,
        }

    return {
        "status": "cached",
        "analysis_id": artifact.id,
        "analyzed_at": artifact.completed_at.isoformat() if artifact.completed_at else None,
        "result_path": artifact.result_path,
    }
