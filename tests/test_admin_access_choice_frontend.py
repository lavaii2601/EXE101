import glob
import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


class AdminAccessChoiceFrontendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, 'web', 'frontend', 'index.html'), encoding='utf-8') as handle:
            cls.html = handle.read()
        # app.js was split into per-feature files (web/frontend/js/*.js) --
        # concatenate them all so substring assertions below still work
        # regardless of which file now holds the matching code.
        js_dir = os.path.join(ROOT, 'web', 'frontend', 'js')
        cls.javascript = ''.join(
            open(path, encoding='utf-8').read()
            for path in sorted(glob.glob(os.path.join(js_dir, '*.js')))
        )

    def test_admin_choice_exposes_app_and_dashboard_actions(self):
        self.assertIn('id="adminAccessChoice"', self.html)
        self.assertIn('id="adminOpenAppBtn"', self.html)
        self.assertIn('id="adminOpenDashboardBtn"', self.html)

    def test_admin_choice_depends_on_server_role_flag(self):
        self.assertIn('lastAuthStatus?.is_admin', self.javascript)
        self.assertIn("window.location.assign('/admin')", self.javascript)
        self.assertIn("window.location.replace('/app')", self.javascript)


if __name__ == '__main__':
    unittest.main()
