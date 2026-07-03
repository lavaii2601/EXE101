import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "database" / "postgres_schema.sql"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
EMAIL_TRAINING_PATH = PROJECT_ROOT / "docs" / "bob-training" / "email-150-knowledge.json"
EXPANDED_TRAINING_PATH = PROJECT_ROOT / "docs" / "bob-training" / "bob-200-expanded-contexts.json"
STUDENT_PRIVACY_RESEARCH_PATH = PROJECT_ROOT / "docs" / "bob-training" / "bob-student-privacy-research.json"


def apply_sql_file(conn, path):
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cursor:
        cursor.execute(sql)
    print(f"Applied {path.relative_to(PROJECT_ROOT).as_posix()}")


def import_bob_email_training():
    training_sets = [
        (EMAIL_TRAINING_PATH, "email,gmail,bob,training", "bob-email-150"),
        (EXPANDED_TRAINING_PATH, "expanded,bob,training", "bob-expanded-200"),
        (STUDENT_PRIVACY_RESEARCH_PATH, "student,privacy,research,bob,training", "bob-student-privacy-research"),
    ]
    existing_sets = [item for item in training_sets if item[0].exists()]
    if not existing_sets:
        return

    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from train_bob import _init_storage, _load_documents, import_documents

    _init_storage()
    for path, default_tags, source in existing_sets:
        documents = _load_documents(
            [path],
            default_tags=default_tags,
            chunk_chars=3500,
        )
        if not documents:
            print(f"No Bob training documents found in {path.name}.")
            continue

        created, updated, skipped = import_documents(
            documents,
            source=source,
            user_id=None,
            update_existing=True,
            dry_run=False,
        )
        print(
            f"Bob training import completed for {path.name}: "
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
