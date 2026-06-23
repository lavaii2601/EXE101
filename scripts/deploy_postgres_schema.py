import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "database" / "postgres_schema.sql"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"


def apply_sql_file(conn, path):
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cursor:
        cursor.execute(sql)
    print(f"Applied {path.relative_to(PROJECT_ROOT).as_posix()}")


def main():
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is not set; skipping PostgreSQL schema deploy.")
        return

    import psycopg

    with psycopg.connect(database_url) as conn:
        apply_sql_file(conn, SCHEMA_PATH)
        if MIGRATIONS_DIR.exists():
            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                apply_sql_file(conn, migration)
        conn.commit()
    print("PostgreSQL schema deploy completed.")


if __name__ == "__main__":
    main()
