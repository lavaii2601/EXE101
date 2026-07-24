import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADMIN_HTML = PROJECT_ROOT / 'web' / 'frontend' / 'admin.html'
ADMIN_JS = PROJECT_ROOT / 'web' / 'frontend' / 'js' / 'admin.js'


class AdminFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = ADMIN_HTML.read_text(encoding='utf-8')
        cls.javascript = ADMIN_JS.read_text(encoding='utf-8')

    def test_javascript_dom_ids_exist_and_html_ids_are_unique(self):
        html_ids = re.findall(r'\bid="([^"]+)"', self.html)
        referenced_ids = set(re.findall(r"\$\('([^']+)'\)", self.javascript))
        duplicate_ids = sorted({
            element_id for element_id in html_ids if html_ids.count(element_id) > 1
        })
        missing_ids = sorted(referenced_ids.difference(html_ids))

        self.assertEqual(duplicate_ids, [])
        self.assertEqual(missing_ids, [])

    def test_dashboard_tabs_have_accessible_panels(self):
        self.assertEqual(
            len(re.findall(r'<section\b', self.html)),
            self.html.count('</section>'),
        )
        self.assertEqual(
            len(re.findall(r'<div\b', self.html)),
            self.html.count('</div>'),
        )
        self.assertIn('role="tablist"', self.html)
        self.assertIn('data-dashboard-tab="overview"', self.html)
        self.assertIn('data-dashboard-panel="overview"', self.html)
        self.assertIn('data-dashboard-tab="finance"', self.html)
        self.assertIn('data-dashboard-panel="finance"', self.html)
        self.assertIn('aria-controls="financePanel"', self.html)
        self.assertIn('aria-labelledby="financeTab"', self.html)

    def test_finance_copy_does_not_claim_bank_settlement(self):
        self.assertIn('Thực thu ước tính', self.html)
        self.assertIn('không đồng nghĩa tiền đã settlement', self.html)
        self.assertIn('finance.reporting_timezone', self.javascript)

    def test_subscription_controls_cover_renew_revoke_and_remaining_time(self):
        self.assertIn('data-grant-premium', self.javascript)
        self.assertIn('data-renew-premium', self.javascript)
        self.assertIn('data-revoke-premium', self.javascript)
        self.assertIn('subscription_remaining_seconds', self.javascript)
        self.assertIn('remainingTime(', self.javascript)
        self.assertIn('recentSubscriptionsBody', self.html)


if __name__ == '__main__':
    unittest.main()
