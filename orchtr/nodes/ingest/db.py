"""
nodes/ingest/db.py — Postgres (Cloud SQL) config and helpers.
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


def ensure_photo_row_if_missing(
    *,
    photo_id: str,
    sol: str,
    source_path: str | None,
    metadata_path: str,
    rgb_path: str | None = None,
    gray_path: str | None = None,
    transform_status: str = "pending",
    analysis_status: str = "pending",
):
    """Insert row into photos only if missing. DO NOT update existing row."""
    if not pg_enabled():
        return
    sql = """
    INSERT INTO photos (
      photo_id, sol, source_path, metadata_path, rgb_path, gray_path,
      transform_status, analysis_status, created_by, updated_by
    )
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON CONFLICT (photo_id) DO NOTHING;
    """
    sol_int = None
    try:
        sol_int = int(sol)
    except Exception:
        pass
    try:
        with pg_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    photo_id, sol_int, source_path, metadata_path,
                    rgb_path, gray_path, transform_status, analysis_status,
                    KEYCLOAK_UUID, KEYCLOAK_UUID,
                ))
    except Exception as e:
        print(f"  WARN: Postgres insert failed for photo_id={photo_id}: {e}")
