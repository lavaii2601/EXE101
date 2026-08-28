"""Backfill a personal workspace for every existing user (Phase 1 migration).

See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md section 13, "Giai doan migration
1: nen tang workspace" -- every existing account needs exactly one personal
workspace before any client can start sending workspace_id.

Usage:
    python scripts/backfill_personal_workspaces.py --dry-run
    python scripts/backfill_personal_workspaces.py --execute
    python scripts/backfill_personal_workspaces.py --rollback <log_file>

--execute is idempotent and safe to re-run (it only touches users that still
lack a personal workspace). --rollback deletes exactly the workspaces one
prior --execute run created, using that run's log file, and asks for typed
confirmation first since it's a destructive operation.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "web" / "backend"))

LOG_DIR = PROJECT_ROOT / "database" / "migrations" / "logs"


def _list_users_without_personal_workspace(conn):
    rows = conn.execute(
        """
        SELECT u.user_id, u.name, u.email
        FROM users u
        LEFT JOIN workspaces w
            ON w.owner_user_id = u.user_id AND w.type = 'personal'
        WHERE w.id IS NULL
        ORDER BY u.created_at ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def dry_run():
    from models import postgres_db as pg

    if not pg.enabled():
        print("DATABASE_URL is not set; nothing to check.")
        return
    with pg.connection() as conn:
        missing = _list_users_without_personal_workspace(conn)
    print(f"{len(missing)} user(s) missing a personal workspace:")
    for user in missing:
        print(f"  - {user['user_id']}  ({user.get('name') or ''} <{user.get('email') or ''}>)")
    print("\nDry run only -- no rows written. Re-run with --execute to create them.")


def execute():
    from models import postgres_db as pg
    from models import workspace as workspace_model

    if not pg.enabled():
        print("DATABASE_URL is not set; nothing to do.")
        return
    with pg.connection() as conn:
        missing = _list_users_without_personal_workspace(conn)
    if not missing:
        print("Every user already has a personal workspace. Nothing to do.")
        return

    created = []
    errors = []
    for user in missing:
        user_id = user['user_id']
        try:
            workspace = workspace_model.ensure_personal_workspace(
                user_id, name=user.get('name') or 'Personal',
            )
            created.append({'user_id': user_id, 'workspace_id': workspace['id']})
            print(f"Created personal workspace {workspace['id']} for {user_id}")
        except Exception as exc:  # noqa: BLE001 -- report and keep going
            errors.append({'user_id': user_id, 'error': str(exc)})
            print(f"FAILED for {user_id}: {exc}", file=sys.stderr)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    log_path = LOG_DIR / f"backfill_personal_workspaces_{timestamp}.json"
    log_path.write_text(
        json.dumps({'created_at': timestamp, 'created': created, 'errors': errors}, indent=2),
        encoding='utf-8',
    )

    print(f"\n{len(created)} workspace(s) created, {len(errors)} error(s).")
    print(f"Rollback log written to {log_path}")
    if errors:
        print(
            "Some users failed -- investigate, then re-run this script "
            "(it is idempotent and will only retry the users still missing a workspace).",
            file=sys.stderr,
        )


def rollback(log_file):
    from models import postgres_db as pg

    if not pg.enabled():
        print("DATABASE_URL is not set; nothing to roll back.")
        return
    path = Path(log_file)
    if not path.exists():
        print(f"Log file not found: {path}", file=sys.stderr)
        sys.exit(1)
    data = json.loads(path.read_text(encoding='utf-8'))
    created = data.get('created', [])
    if not created:
        print("Log file has no created workspaces to roll back.")
        return

    print(f"About to DELETE {len(created)} workspace(s) created by this backfill run:")
    for item in created:
        print(f"  - workspace {item['workspace_id']} (owner {item['user_id']})")
    confirm = input("Type 'yes' to confirm deletion: ").strip().lower()
    if confirm != 'yes':
        print("Aborted.")
        return

    with pg.connection() as conn:
        for item in created:
            # type = 'personal' guard: never lets this script delete a
            # Business workspace even if a log file were hand-edited.
            conn.execute(
                "DELETE FROM workspaces WHERE id = %s AND type = 'personal'",
                (item['workspace_id'],),
            )
    print(f"Rolled back {len(created)} workspace(s).")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help="Report what would be created, without writing.")
    group.add_argument('--execute', action='store_true', help="Create missing personal workspaces.")
    group.add_argument(
        '--rollback', metavar='LOG_FILE',
        help="Delete workspaces created by a previous --execute run, using its log file.",
    )
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
    elif args.execute:
        execute()
    elif args.rollback:
        rollback(args.rollback)


if __name__ == "__main__":
    main()
