import os
import time
from pathlib import Path

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://thesis:thesis@db:5432/thesis")
MIGRATIONS_DIR = Path(os.getenv("MIGRATIONS_DIR", "/app/db/migrations"))
MAX_RETRIES = int(os.getenv("MIGRATION_DB_RETRIES", "30"))
RETRY_DELAY_SECONDS = float(os.getenv("MIGRATION_DB_RETRY_DELAY", "2"))


def connect_with_retry() -> psycopg.Connection:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"Connecting to database (attempt {attempt}/{MAX_RETRIES})...")
            return psycopg.connect(DATABASE_URL)
        except psycopg.OperationalError as exc:
            if attempt == MAX_RETRIES:
                raise RuntimeError("Could not connect to database for migrations.") from exc
            time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError("Migration retry loop exited unexpectedly.")


def ensure_schema_migrations_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public.schema_migrations (
                filename text PRIMARY KEY,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def apply_migrations(conn: psycopg.Connection) -> None:
    if not MIGRATIONS_DIR.exists():
        raise RuntimeError(f"Migrations directory not found: {MIGRATIONS_DIR}")

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for migration_path in migration_files:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM public.schema_migrations WHERE filename = %s",
                (migration_path.name,),
            )
            already_applied = cur.fetchone() is not None

            if already_applied:
                print(f"Skipping {migration_path.name}: already applied")
                continue

            print(f"Applying migration: {migration_path.name}")
            sql_text = migration_path.read_text(encoding="utf-8")
            cur.execute(sql_text)
            cur.execute(
                "INSERT INTO public.schema_migrations (filename) VALUES (%s)",
                (migration_path.name,),
            )

        conn.commit()


def main() -> None:
    conn = connect_with_retry()
    try:
        ensure_schema_migrations_table(conn)
        apply_migrations(conn)
        print("Migrations completed.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
