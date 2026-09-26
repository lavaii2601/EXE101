import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = PROJECT_ROOT / "web" / "frontend" / "index.html"
JS_DIR = PROJECT_ROOT / "web" / "frontend" / "js"


class WebSubscriptionFrontendContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = INDEX_HTML.read_text(encoding="utf-8")
        # app.js was split into per-feature files (web/frontend/js/*.js) --
        # concatenate them all so substring assertions below still work
        # regardless of which file now holds the matching code.
        cls.javascript = ''.join(
            path.read_text(encoding="utf-8") for path in sorted(JS_DIR.glob("*.js"))
        )

    def test_web_exposes_upgrade_and_renew_controls(self):
        self.assertIn('id="subscriptionHeaderBtn"', self.html)
        self.assertIn('id="settingsSubscriptionBtn"', self.html)
        self.assertIn('id="subscriptionModal"', self.html)
        self.assertIn("Nâng cấp Premium", self.html)
        self.assertIn("Gia hạn Premium", self.javascript)

    def test_web_uses_server_entitlement_guard(self):
        self.assertIn("/payments/sepay/checkout", self.javascript)
        self.assertIn("const action = isPremium ? 'renew' : 'purchase'", self.javascript)
        self.assertIn("data.allowed_action === 'renew'", self.javascript)
        self.assertIn("data.allowed_action === 'purchase'", self.javascript)

    def test_web_displays_remaining_premium_time(self):
        self.assertIn("subscriptionRemainingLabel", self.javascript)
        self.assertIn("current_period_end", self.javascript)
        self.assertIn("remaining_seconds", self.javascript)
        self.assertIn('id="settingsSubscriptionStatus"', self.html)

    def test_web_pricing_matches_mobile_and_admin(self):
        self.assertIn("49.000đ", self.html)
        self.assertIn("520.000đ", self.html)
        self.assertIn("SEPay", self.html)
        self.assertIn('data-payment-method="BANK_TRANSFER"', self.html)

    def test_upgrade_modal_compares_current_freemium_with_two_paid_plans(self):
        self.assertNotIn('data-subscription-plan="free"', self.html)
        self.assertIn('id="freePlanCard"', self.html)
        self.assertIn("Gói hiện tại", self.html)
        self.assertIn('data-subscription-plan="monthly"', self.html)
        self.assertIn('data-subscription-plan="yearly"', self.html)
        self.assertIn("Tiết kiệm 12%", self.html)
        self.assertIn('id="subscriptionPlanStep"', self.html)
        self.assertIn('id="subscriptionPaymentStep"', self.html)
        self.assertIn('id="subscriptionContinueBtn"', self.html)
        self.assertIn("showSubscriptionPaymentStep", self.javascript)
        self.assertIn("showSubscriptionPlanStep", self.javascript)


if __name__ == "__main__":
    unittest.main()
