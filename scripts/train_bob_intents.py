#!/usr/bin/env python
"""Import Bob's generated 500-case-per-intent corpus into the RAG store."""

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from models.knowledge import KnowledgeDocument  # noqa: E402
from models import postgres_db as pg  # noqa: E402
from services.bob_training_cases import (  # noqa: E402
    CASES_PER_INTENT,
    build_rag_training_documents,
    iter_labelled_cases,
)
from train_bob import import_documents  # noqa: E402


SOURCE = "bob-intent-500-v1"


def main():
    parser = argparse.ArgumentParser(description="Train Bob with 500 labelled cases per tool intent")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cases = list(iter_labelled_cases())
    documents = build_rag_training_documents(batch_size=50)
    if args.dry_run:
        print(
            f"Validated {len(cases)} labelled cases "
            f"({CASES_PER_INTENT} per intent); would import {len(documents)} RAG documents."
        )
        return 0

    if pg.enabled():
        pg.initialize_schema()
    KnowledgeDocument.init_db()
    created, updated, skipped = import_documents(
        documents,
        source=SOURCE,
        user_id=None,
        update_existing=True,
        dry_run=False,
    )
    print(
        f"Trained Bob with {len(cases)} cases in {len(documents)} documents: "
        f"{created} created, {updated} updated, {skipped} skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
