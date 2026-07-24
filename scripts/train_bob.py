#!/usr/bin/env python
"""Import training material into Bob's knowledge base.

This is not model fine-tuning. It adds documents to the same knowledge table
that Bob already uses for RAG lookups in chat.
"""

import argparse
import csv
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from models.knowledge import KnowledgeDocument  # noqa: E402
from models import postgres_db as pg  # noqa: E402


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".json", ".csv"}


def _clean(value):
    return str(value or "").strip()


def _read_text(path):
    return path.read_text(encoding="utf-8-sig").strip()


def _doc_from_text_file(path, default_tags):
    content = _read_text(path)
    if not content:
        return []
    return [
        {
            "title": path.stem.replace("_", " ").replace("-", " ").strip() or path.name,
            "content": content,
            "tags": default_tags,
        }
    ]


def _docs_from_json(path, default_tags):
    raw = json.loads(_read_text(path))
    if isinstance(raw, dict) and isinstance(raw.get("documents"), list):
        raw = raw["documents"]
    elif isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raise ValueError(f"{path} must contain an object, a list, or a documents list")

    docs = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{path} item #{index} must be an object")
        title = _clean(item.get("title") or item.get("name"))
        content = _clean(item.get("content") or item.get("body") or item.get("text"))
        content_en = _clean(item.get("content_en") or item.get("semantic_en"))
        tags = _clean(item.get("tags") or default_tags)
        if title and content:
            if content_en and content_en not in content:
                content = f"{content}\n\nEnglish semantic equivalent:\n{content_en}"
            docs.append({"title": title, "content": content, "tags": tags})
    return docs


def _docs_from_csv(path, default_tags):
    docs = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for index, row in enumerate(reader, start=2):
            title = _clean(row.get("title") or row.get("name"))
            content = _clean(row.get("content") or row.get("body") or row.get("text"))
            tags = _clean(row.get("tags") or default_tags)
            if title and content:
                docs.append({"title": title, "content": content, "tags": tags})
            elif title or content:
                raise ValueError(f"{path}:{index} needs both title and content")
    return docs


def _split_content(content, max_chars):
    if not max_chars or len(content) <= max_chars:
        return [content]

    chunks = []
    current = []
    current_len = 0
    for paragraph in content.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        extra = len(paragraph) + (2 if current else 0)
        if current and current_len + extra > max_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
            current_len = len(paragraph)
        else:
            current.append(paragraph)
            current_len += extra
    if current:
        chunks.append("\n\n".join(current))
    return chunks or [content[:max_chars]]


def _load_documents(paths, default_tags, chunk_chars):
    documents = []
    for raw_path in paths:
        path = Path(raw_path).resolve()
        candidates = []
        if path.is_dir():
            candidates = [
                item
                for item in sorted(path.rglob("*"))
                if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS
            ]
        elif path.is_file():
            candidates = [path]
        else:
            raise FileNotFoundError(path)

        for candidate in candidates:
            suffix = candidate.suffix.lower()
            if suffix == ".json":
                loaded = _docs_from_json(candidate, default_tags)
            elif suffix == ".csv":
                loaded = _docs_from_csv(candidate, default_tags)
            else:
                loaded = _doc_from_text_file(candidate, default_tags)

            for doc in loaded:
                chunks = _split_content(doc["content"], chunk_chars)
                if len(chunks) == 1:
                    documents.append(doc)
                else:
                    width = len(str(len(chunks)))
                    for index, chunk in enumerate(chunks, start=1):
                        documents.append(
                            {
                                "title": f"{doc['title']} ({index:0{width}d}/{len(chunks)})",
                                "content": chunk,
                                "tags": doc["tags"],
                            }
                        )
    return documents


def _init_storage():
    if pg.enabled():
        pg.initialize_schema()
    KnowledgeDocument.init_db()


def _find_existing(doc, source, user_id):
    for existing in KnowledgeDocument.get_all(limit=5000):
        if existing.get("title") != doc["title"]:
            continue
        if existing.get("source") != source:
            continue
        if (existing.get("user_id") or None) != (user_id or None):
            continue
        return existing
    return None


def _existing_key(title, source, user_id):
    return (title, source, user_id or None)


def import_documents(documents, source, user_id, update_existing, dry_run):
    created = 0
    updated = 0
    skipped = 0
    existing_by_key = {}
    if not dry_run:
        for existing in KnowledgeDocument.get_all(limit=50000):
            key = _existing_key(
                existing.get("title"),
                existing.get("source"),
                existing.get("user_id"),
            )
            existing_by_key.setdefault(key, existing)

    for doc in documents:
        existing = existing_by_key.get(_existing_key(doc["title"], source, user_id))
        if existing:
            changed = (
                existing.get("content") != doc["content"]
                or existing.get("tags") != doc["tags"]
            )
            if changed and update_existing:
                updated += 1
                if not dry_run:
                    KnowledgeDocument.update(
                        existing["id"],
                        content=doc["content"],
                        tags=doc["tags"],
                    )
            else:
                skipped += 1
            continue

        created += 1
        if not dry_run:
            created_doc = KnowledgeDocument.create(
                doc["title"],
                doc["content"],
                tags=doc["tags"],
                source=source,
                user_id=user_id,
            )
            existing_by_key[_existing_key(doc["title"], source, user_id)] = created_doc
    return created, updated, skipped


def main():
    parser = argparse.ArgumentParser(
        description="Train Bob by importing documents into the knowledge base."
    )
    parser.add_argument("paths", nargs="+", help="Files or directories to import")
    parser.add_argument("--tags", default="training,bob", help="Default tags")
    parser.add_argument("--source", default="manual", help="Knowledge source label")
    parser.add_argument("--user-id", default=None, help="Attach docs to one user only")
    parser.add_argument(
        "--chunk-chars",
        type=int,
        default=3500,
        help="Split long text/markdown docs into chunks; use 0 to disable",
    )
    parser.add_argument(
        "--no-update-existing",
        action="store_true",
        help="Skip matching title/source/user rows instead of updating them",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()

    documents = _load_documents(args.paths, args.tags, args.chunk_chars)
    if not documents:
        print("No importable documents found.")
        return 1
    if args.dry_run:
        print(
            f"Would import {len(documents)} document(s). "
            "Dry run did not inspect or write the database."
        )
        return 0

    _init_storage()
    created, updated, skipped = import_documents(
        documents,
        source=args.source,
        user_id=args.user_id,
        update_existing=not args.no_update_existing,
        dry_run=args.dry_run,
    )

    print(
        f"Imported {len(documents)} document(s): "
        f"{created} created, {updated} updated, {skipped} skipped."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
