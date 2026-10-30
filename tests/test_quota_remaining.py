"""enforce_ai_quota previously returned None on the allowed path and only
a {"used","limit"} dict on rejection, discarding used/limit data that
check_and_increment already computed on every call. Changed to always
return {"allowed","used","limit","remaining"} so callers can show "X/Y
lượt còn lại hôm nay" right after a successful AI action, not just an
error message when the user runs out. These tests guard the new contract
directly (the quota-gated route/service tests already guard that their
own allow/reject branching still works against the new shape)."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "web" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from utils import quota  # noqa: E402


class EnforceAiQuotaContractTests(unittest.TestCase):
    def test_allowed_call_returns_full_shape_not_none(self):
        with (
            patch.object(quota, 'is_premium', return_value=False),
            patch.object(quota.admin_ops, 'quota_limit', return_value=5),
            patch.object(quota, 'check_and_increment', return_value=(True, 2, 5)),
        ):
            result = quota.enforce_ai_quota('user-1', 'email_summary')
        self.assertEqual(
            {'allowed': True, 'used': 2, 'limit': 5, 'remaining': 3}, result,
        )

    def test_rejected_call_still_reports_used_and_limit(self):
        with (
            patch.object(quota, 'is_premium', return_value=False),
            patch.object(quota.admin_ops, 'quota_limit', return_value=5),
            patch.object(quota, 'check_and_increment', return_value=(False, 6, 5)),
        ):
            result = quota.enforce_ai_quota('user-1', 'email_summary')
        self.assertEqual(
            {'allowed': False, 'used': 6, 'limit': 5, 'remaining': 0}, result,
        )

    def test_remaining_never_goes_negative_when_used_exceeds_limit(self):
        # Can genuinely happen: two concurrent requests both pass the
        # allowed check before either's increment is visible to the other
        # (check_and_increment is atomic per call, but two separate calls
        # can both legitimately land at used=limit+1 and used=limit+2).
        with (
            patch.object(quota, 'is_premium', return_value=False),
            patch.object(quota.admin_ops, 'quota_limit', return_value=5),
            patch.object(quota, 'check_and_increment', return_value=(False, 8, 5)),
        ):
            result = quota.enforce_ai_quota('user-1', 'email_summary')
        self.assertEqual(0, result['remaining'])

    def test_premium_plan_is_looked_up_separately_from_free(self):
        with (
            patch.object(quota, 'is_premium', return_value=True),
            patch.object(quota.admin_ops, 'quota_limit', return_value=999) as limit_mock,
            patch.object(quota, 'check_and_increment', return_value=(True, 1, 999)),
        ):
            quota.enforce_ai_quota('user-1', 'claude')
        limit_mock.assert_called_once_with('plus', 'claude')


if __name__ == '__main__':
    unittest.main()
