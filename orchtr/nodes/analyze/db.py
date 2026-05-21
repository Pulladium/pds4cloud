"""
nodes/analyze/db.py — Postgres helpers for the analyze node.
"""

import os

try:
    import psycopg2
except Exception:
    psycopg2 = None

PGHOST        = os.environ.get("PGHOST")
PGPORT        = int(os.environ.get("PGPORT", "5432"))
PGDATABASE    = os.environ.get("PGDATABASE")
PGUSER        = os.environ.get("PGUSER")
PGPASSWORD    = os.environ.get("PGPASSWORD")
PGSSLMODE     = os.environ.get("PGSSLMODE", "require")
KEYCLOAK_UUID = os.environ.get("KEYCLOAK_UUID")


def pg_enabled() -> bool:
    return bool(psycopg2 and PGHOST and PGDATABASE and PGUSER and PGPASSWORD and KEYCLOAK_UUID)


def pg_conn():
    return psycopg2.connect(
        host=PGHOST, port=PGPORT, dbname=PGDATABASE,
        user=PGUSER, password=PGPASSWORD,
        sslmode=PGSSLMODE, connect_timeout=5,
    )


def pg_fetch_pending_analysis(limit: int | None) -> list[tuple]:
    """
    Return list of (photo_id, sol) for rows with analysis_status='pending'
    and transform_status='done'.
    Raises RuntimeError if Postgres is not configured.
    """
    if not pg_enabled():
        raise RuntimeError("Postgres is not configured (.env/psycopg2 missing).")

    sql = """
    SELECT photo_id, sol
    FROM photos
    WHERE analysis_status = 'pending'
      AND transform_status = 'done'
      AND sol IS NOT NULL
    ORDER BY sol ASC
    """
    params: list = []
    if limit is not None:
        sql += " LIMIT %s"
        params.append(limit)

    with pg_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def pg_mark_analysis_running(photo_id: str) -> None:
    if not pg_enabled():
        return
    sql = """
    UPDATE photos
    SET analysis_status = 'running',
        updated_by      = %s,
        updated_at      = NOW()
    WHERE photo_id = %s;
    """
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (KEYCLOAK_UUID, photo_id))
        print(f"  PG: analysis running photo_id={photo_id}")
    except Exception as e:
        print(f"  WARN: PG update failed (running) photo_id={photo_id}: {e}")


def pg_mark_analysis_done(photo_id: str, result_path: str) -> None:
    if not pg_enabled():
        return
    sql = """
    UPDATE photos
    SET analysis_result_path = %s,
        analysis_status      = 'done',
        updated_by           = %s,
        updated_at           = NOW()
    WHERE photo_id = %s;
    """
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (result_path, KEYCLOAK_UUID, photo_id))
        print(f"  PG: analysis done photo_id={photo_id}")
    except Exception as e:
        print(f"  WARN: PG update failed (done) photo_id={photo_id}: {e}")


def pg_mark_analysis_failed(photo_id: str, reason: str) -> None:
    if not pg_enabled():
        return
    sql = """
    UPDATE photos
    SET analysis_status = 'failed',
        updated_by      = %s,
        updated_at      = NOW()
    WHERE photo_id = %s;
    """
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (KEYCLOAK_UUID, photo_id))
        print(f"  PG: analysis failed photo_id={photo_id} reason={reason}")
    except Exception as e:
        print(f"  WARN: PG update failed (failed) photo_id={photo_id}: {e}")
