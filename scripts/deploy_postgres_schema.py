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
    print(f"Applied {path.relative_to(PROJECT_ROOT).as_posix()}", flush=True)


def import_bob_email_training():
    training_sets = [
        (EMAIL_TRAINING_PATH, "email,gmail,bob,training", "bob-email-150"),
        (EXPANDED_TRAINING_PATH, "expanded,bob,training", "bob-expanded-200"),
        (STUDENT_PRIVACY_RESEARCH_PATH, "student,privacy,research,bob,training", "bob-student-privacy-research"),
    ]
    existing_sets = [item for item in training_sets if item[0].exists()]
    if not existing_sets:
        print("No Bob training files found for deploy import.", flush=True)
        return

    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
    from train_bob import _load_documents, import_documents

    try:
        for path, default_tags, source in existing_sets:
            print(f"Importing Bob training from {path.name}...", flush=True)
            documents = _load_documents(
                [path],
                default_tags=default_tags,
                chunk_chars=3500,
            )
            if not documents:
                print(f"No Bob training documents found in {path.name}.", flush=True)
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
                f"{created} created, {updated} updated, {skipped} skipped.",
                flush=True,
            )

        # The labelled corpus is generated deterministically from reviewed
        # semantic building blocks: 500 examples for every tool catalog
        # intent, packed into small RAG documents to avoid 6,000 database
        # rows.  The same corpus powers the offline classifier at runtime.
        sys.path.insert(0, str(PROJECT_ROOT / "web" / "backend"))
        from services.bob_training_cases import build_rag_training_documents, iter_labelled_cases

        labelled_cases = list(iter_labelled_cases())
        intent_documents = build_rag_training_documents(batch_size=50)
        created, updated, skipped = import_documents(
            intent_documents,
            source="bob-intent-500-v1",
            user_id=None,
            update_existing=True,
            dry_run=False,
        )
        print(
            f"Bob intent training completed: {len(labelled_cases)} labelled cases, "
            f"{created} documents created, {updated} updated, {skipped} skipped.",
            flush=True,
        )
    finally:
        from models import postgres_db as pg

        pg.close_pool()


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
    print("PostgreSQL schema deploy completed.", flush=True)
    import_bob_email_training()


if __name__ == "__main__":
    main()
