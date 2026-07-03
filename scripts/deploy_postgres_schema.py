import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "database" / "postgres_schema.sql"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
EMAIL_TRAINING_PATH = PROJECT_ROOT / "docs" / "bob-training" / "email-150-knowledge.json"


def apply_sql_file(conn, path):
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cursor:
        cursor.execute(sql)
    print(f"Applied {path.relative_to(PROJECT_ROOT).as_posix()}")


def import_bob_email_training():
    if not EMAIL_TRAINING_PATH.exists():
        return

    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from train_bob import _init_storage, _load_documents, import_documents

    documents = _load_documents(
        [EMAIL_TRAINING_PATH],
        default_tags="email,gmail,bob,training",
        chunk_chars=3500,
    )
    if not documents:
        print("No Bob email training documents found.")
        return

    _init_storage()
    created, updated, skipped = import_documents(
        documents,
        source="bob-email-150",
        user_id=None,
        update_existing=True,
        dry_run=False,
    )
    print(
        f"Bob email training import completed: "
        f"{created} created, {updated} updated, {skipped} skipped."
    )


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
    import_bob_email_training()


if __name__ == "__main__":
    main()
