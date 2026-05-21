"""
nodes/transform/db.py — Postgres helpers for the transform node.
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


def pg_fetch_pending(limit: int | None) -> list[tuple]:
    """
    Return list of (photo_id, sol, source_path) for rows with transform_status='pending'.
    Raises RuntimeError if Postgres is not configured.
    """
    if not pg_enabled():
        raise RuntimeError("Postgres is not configured (.env/psycopg2 missing).")

    sql = """
    SELECT photo_id, sol, source_path
    FROM photos
    WHERE transform_status = 'pending'
      AND source_path IS NOT NULL
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


def pg_mark_done(photo_id: str, gray_path: str, rgb_path: str | None) -> None:
    if not pg_enabled():
        return
    sql = """
    UPDATE photos
    SET
      gray_path        = %s,
      rgb_path         = %s,
      transform_status = 'done',
      updated_by       = %s,
      updated_at       = NOW()
    WHERE photo_id = %s;
    """
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (gray_path, rgb_path, KEYCLOAK_UUID, photo_id))
        print(f"  PG: done photo_id={photo_id}")
    except Exception as e:
        print(f"  WARN: PG update failed (done) photo_id={photo_id}: {e}")


def pg_mark_failed(photo_id: str, reason: str) -> None:
    if not pg_enabled():
        return
    sql = """
    UPDATE photos
    SET
      transform_status = 'failed',
      updated_by       = %s,
      updated_at       = NOW()
    WHERE photo_id = %s;
    """
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (KEYCLOAK_UUID, photo_id))
        print(f"  PG: failed photo_id={photo_id} reason={reason}")
    except Exception as e:
        print(f"  WARN: PG update failed (failed) photo_id={photo_id}: {e}")
