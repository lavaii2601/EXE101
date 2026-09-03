import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
SCRIPTS_DIR = REPO_ROOT / "scripts"
for path in (BACKEND_DIR, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from check_subscription_expiry import compute_transitions  # noqa: E402


def _row(workspace_status, sub_status, current_period_end, grace_period_ends_at=None):
    return {
        'workspace_id': 'ws-1',
        'workspace_name': 'Acme Inc',
        'workspace_status': workspace_status,
        'status': sub_status,
        'current_period_end': current_period_end,
        'grace_period_ends_at': grace_period_ends_at,
    }


class ComputeTransitionsTests(unittest.TestCase):
    def test_no_transition_when_already_in_sync(self):
        row = _row('active', 'active', datetime.now(timezone.utc) + timedelta(days=10))
        self.assertEqual([], compute_transitions([row]))

    def test_transition_detected_when_entering_grace(self):
        row = _row(
            'active', 'past_due',
            datetime.now(timezone.utc) - timedelta(days=1),
        )
        transitions = compute_transitions([row])
        self.assertEqual(1, len(transitions))
        self.assertEqual('active', transitions[0]['from_status'])
        self.assertEqual('grace', transitions[0]['to_status'])

    def test_transition_detected_when_entering_read_only(self):
        row = _row(
            'grace', 'past_due',
            datetime.now(timezone.utc) - timedelta(days=10),
        )
        transitions = compute_transitions([row])
        self.assertEqual(1, len(transitions))
        self.assertEqual('read_only', transitions[0]['to_status'])

    def test_transition_detected_when_renewed_back_to_active(self):
        # workspaces.status is stale ('read_only') from before a renewal
        # extended current_period_end back into the future.
        row = _row(
            'read_only', 'active',
            datetime.now(timezone.utc) + timedelta(days=30),
        )
        transitions = compute_transitions([row])
        self.assertEqual(1, len(transitions))
        self.assertEqual('read_only', transitions[0]['from_status'])
        self.assertEqual('active', transitions[0]['to_status'])

    def test_idempotent_across_repeated_runs(self):
        row = _row(
            'active', 'past_due',
            datetime.now(timezone.utc) - timedelta(days=1),
        )
        first = compute_transitions([row])
        self.assertEqual(1, len(first))
        # Simulate the job having applied the transition: workspace_status
        # now matches the computed state, so a second run must be a no-op.
        row['workspace_status'] = first[0]['to_status']
        second = compute_transitions([row])
        self.assertEqual([], second)

    def test_multiple_workspaces_only_out_of_sync_ones_returned(self):
        in_sync = _row('active', 'active', datetime.now(timezone.utc) + timedelta(days=5))
        in_sync['workspace_id'] = 'ws-sync'
        out_of_sync = _row('active', 'past_due', datetime.now(timezone.utc) - timedelta(days=1))
        out_of_sync['workspace_id'] = 'ws-out-of-sync'
        transitions = compute_transitions([in_sync, out_of_sync])
        self.assertEqual(['ws-out-of-sync'], [t['workspace_id'] for t in transitions])


if __name__ == "__main__":
    unittest.main()
