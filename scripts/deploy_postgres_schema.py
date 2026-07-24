import hashlib
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = PROJECT_ROOT / "database" / "postgres_schema.sql"
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
BOB_MODE_TRAINING_DIR = PROJECT_ROOT / "docs" / "bob-training" / "modes"
BOB_TRAINING_MANIFEST_TITLE = "Bob bilingual training corpus manifest"
BOB_TRAINING_MANIFEST_SOURCE = "bob-training-manifest"


def bob_training_fingerprint():
    digest = hashlib.sha256()
    paths = sorted(BOB_MODE_TRAINING_DIR.glob("*.json"))
    if not paths:
        return ""
    for path in paths:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def bob_training_sync_required():
    fingerprint = bob_training_fingerprint()
    if not fingerprint:
        return False

    sys.path.insert(0, str(PROJECT_ROOT / "web" / "backend"))
    from models import postgres_db as pg

    with pg.connection() as conn:
        row = conn.execute(
            """
            SELECT content
            FROM knowledge_documents
            WHERE title = %s AND source = %s AND user_id IS NULL
            ORDER BY id DESC
            LIMIT 1
            """,
            (BOB_TRAINING_MANIFEST_TITLE, BOB_TRAINING_MANIFEST_SOURCE),
        ).fetchone()
    current = row.get("content") if isinstance(row, dict) else (row[0] if row else "")
    return current != fingerprint


def update_bob_training_manifest(fingerprint):
    from models import postgres_db as pg

    with pg.connection() as conn:
        updated = conn.execute(
            """
            UPDATE knowledge_documents
            SET content = %s, tags = %s, updated_at = NOW()
            WHERE title = %s AND source = %s AND user_id IS NULL
            """,
            (
                fingerprint,
                "bob,training,manifest,bilingual,vi-en",
                BOB_TRAINING_MANIFEST_TITLE,
                BOB_TRAINING_MANIFEST_SOURCE,
            ),
        )
        if updated.rowcount == 0:
            conn.execute(
                """
                INSERT INTO knowledge_documents (title, content, tags, source, user_id)
                VALUES (%s, %s, %s, %s, NULL)
                """,
                (
                    BOB_TRAINING_MANIFEST_TITLE,
                    fingerprint,
                    "bob,training,manifest,bilingual,vi-en",
                    BOB_TRAINING_MANIFEST_SOURCE,
                ),
            )


def apply_sql_file(conn, path):
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cursor:
        cursor.execute(sql)
    print(f"Applied {path.relative_to(PROJECT_ROOT).as_posix()}", flush=True)


def import_bob_email_training():
    training_sets = [
        (path, f"bob,training,mode,{path.stem}", f"bob-mode-v2-{path.stem}")
        for path in sorted(BOB_MODE_TRAINING_DIR.glob("*.json"))
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
        fingerprint = bob_training_fingerprint()
        if fingerprint:
            update_bob_training_manifest(fingerprint)
            print(
                f"Bob bilingual training manifest updated: {fingerprint[:12]}.",
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
    # Training imports can contain more than a thousand documents. The
    # fingerprint avoids repeating that work on unchanged deploys, while the
    # importer batches changed rows in a small number of transactions so the
    # web server can bind its port promptly.
    force_training_import = os.getenv("IMPORT_BOB_TRAINING_ON_DEPLOY", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    training_changed = bob_training_sync_required()
    if force_training_import or training_changed:
        reason = "forced by environment" if force_training_import else "corpus fingerprint changed"
        print(f"Bob training import starting: {reason}.", flush=True)
        import_bob_email_training()
    else:
        from models import postgres_db as pg

        pg.close_pool()
        print(
            "Bob training import skipped; production fingerprint already matches. "
            "Set IMPORT_BOB_TRAINING_ON_DEPLOY=true to force a refresh.",
            flush=True,
        )


if __name__ == "__main__":
    main()
