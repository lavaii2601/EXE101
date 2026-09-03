"""Scheduled Business subscription expiry/grace check (Phase 2 foundation).

See WORKER_BUSINESS_SUBSCRIPTION_DESIGN.md section 6.9. Per that section,
request-time access-state calculation (models/workspace_subscription.py's
get_access_state) is always authoritative and must be correct even if this
job has never run -- every route already computes it fresh. This job's job
is narrower: keep the `workspaces.status` materialized column (added in
Phase 1's schema, unused until now) in sync for anything that wants to
query/filter workspaces by access state without recomputing per row, and
leave an audit trail of state transitions (subscription entering grace,
entering read_only, or recovering back to active).

Proactive notification delivery (email/push when a subscription is about to
expire) is explicitly out of scope here -- no notification infrastructure
exists yet in this codebase. The audit events this job writes
(subscription_access_state_changed) are the natural event source a future
notifier would consume; this job does not invent a parallel one.

Idempotent by construction: a workspace is only touched when its computed
access state differs from the currently stored `workspaces.status`, so
re-running this job (however frequently it's scheduled) never re-applies or
re-announces the same transition twice.

Usage:
    python scripts/check_subscription_expiry.py --dry-run
    python scripts/check_subscription_expiry.py --execute

Scheduling: the design doc calls for running this at least hourly in
production. This script only implements the check itself -- wire it to a
scheduler (e.g. a Railway cron service, GitHub Actions scheduled workflow,
or any other periodic trigger) separately; that's an infrastructure choice
outside this script's scope.
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "web" / "backend"))


def _business_workspaces_with_subscription(conn):
    rows = conn.execute(
        """
        SELECT w.id AS workspace_id, w.name AS workspace_name, w.status AS workspace_status,
               s.status, s.current_period_end, s.grace_period_ends_at
        FROM workspaces w
        JOIN subscriptions s ON s.workspace_id = w.id
        WHERE w.type = 'business'
        ORDER BY w.created_at ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def compute_transitions(rows):
    """Pure function: which workspaces need workspaces.status updated.

    rows: dicts with workspace_id/workspace_name/workspace_status plus the
    subscription fields get_access_state needs (status, current_period_end,
    grace_period_ends_at) -- i.e. exactly what
    _business_workspaces_with_subscription returns, kept separate so this
    logic is testable without a real database.
    """
    from models import workspace_subscription as wsub

    transitions = []
    for row in rows:
        computed_state = wsub.get_access_state(row)
        # ACCESS_NONE has no workspaces.status equivalent (that column only
        # models active/grace/read_only/suspended/archived) -- a business
        # workspace with no subscription yet stays at its default 'active'.
        if computed_state == wsub.ACCESS_NONE:
            continue
        if computed_state != row['workspace_status']:
            transitions.append({
                'workspace_id': row['workspace_id'],
                'workspace_name': row['workspace_name'],
                'from_status': row['workspace_status'],
                'to_status': computed_state,
            })
    return transitions


def _compute_transitions_from_db():
    from models import postgres_db as pg

    with pg.connection() as conn:
        rows = _business_workspaces_with_subscription(conn)
    return compute_transitions(rows)


def dry_run():
    from models import postgres_db as pg

    if not pg.enabled():
        print("DATABASE_URL is not set; nothing to check.")
        return
    transitions = _compute_transitions_from_db()
    print(f"{len(transitions)} workspace(s) need a status transition:")
    for t in transitions:
        print(f"  - {t['workspace_id']} ({t['workspace_name']}): {t['from_status']} -> {t['to_status']}")
    print("\nDry run only -- no rows written. Re-run with --execute to apply.")


def execute():
    from models import postgres_db as pg
    from models import workspace as workspace_model

    if not pg.enabled():
        print("DATABASE_URL is not set; nothing to do.")
        return
    transitions = _compute_transitions_from_db()
    if not transitions:
        print("No workspace status transitions needed.")
        return

    applied = 0
    errors = []
    for t in transitions:
        try:
            with pg.connection() as conn:
                conn.execute(
                    "UPDATE workspaces SET status = %s WHERE id = %s",
                    (t['to_status'], t['workspace_id']),
                )
            workspace_model.record_audit_event(
                t['workspace_id'], None, 'subscription_access_state_changed',
                metadata={'from_status': t['from_status'], 'to_status': t['to_status']},
            )
            applied += 1
            print(f"Updated {t['workspace_id']} ({t['workspace_name']}): {t['from_status']} -> {t['to_status']}")
        except Exception as exc:  # noqa: BLE001 -- report and keep going
            errors.append({'workspace_id': t['workspace_id'], 'error': str(exc)})
            print(f"FAILED for {t['workspace_id']}: {exc}", file=sys.stderr)

    print(f"\n{applied} workspace(s) updated, {len(errors)} error(s).")
    if errors:
        print(
            "Some workspaces failed -- investigate, then re-run this script "
            "(it is idempotent and will only retry workspaces still out of sync).",
            file=sys.stderr,
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--dry-run', action='store_true', help="Report which workspaces would change, without writing.")
    group.add_argument('--execute', action='store_true', help="Apply status transitions and record audit events.")
    args = parser.parse_args()

    if args.dry_run:
        dry_run()
    elif args.execute:
        execute()


if __name__ == "__main__":
    main()
