import os
import unittest
from pathlib import Path
from xml.etree import ElementTree


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FLUTTER_ROOT = PROJECT_ROOT / 'mobile_flutter'


class MobilePlayReadinessTests(unittest.TestCase):
    def test_android_identity_is_production_ready(self):
        gradle = (FLUTTER_ROOT / 'android' / 'app' / 'build.gradle.kts').read_text(
            encoding='utf-8'
        )
        manifest = ElementTree.parse(
            FLUTTER_ROOT / 'android' / 'app' / 'src' / 'main' / 'AndroidManifest.xml'
        ).getroot()
        application = manifest.find('application')
        android = '{http://schemas.android.com/apk/res/android}'
        android_label = f'{android}label'
        android_round_icon = f'{android}roundIcon'

        self.assertIn('namespace = "pro.flowmate.app"', gradle)
        self.assertIn('applicationId = "pro.flowmate.app"', gradle)
        self.assertNotIn('signingConfigs.getByName("debug")', gradle)
        self.assertIn('key.properties', gradle)
        self.assertEqual('FlowMate AI', application.attrib[android_label])
        self.assertEqual('@mipmap/ic_launcher_round', application.attrib[android_round_icon])
        self.assertTrue(
            (
                FLUTTER_ROOT
                / 'android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml'
            ).exists()
        )

    def test_android_release_hardens_transport_backup_and_deep_links(self):
        manifest = ElementTree.parse(
            FLUTTER_ROOT / 'android' / 'app' / 'src' / 'main' / 'AndroidManifest.xml'
        ).getroot()
        application = manifest.find('application')
        android = '{http://schemas.android.com/apk/res/android}'

        self.assertEqual('false', application.attrib[f'{android}allowBackup'])
        self.assertEqual('false', application.attrib[f'{android}usesCleartextTraffic'])
        self.assertEqual(
            '@xml/data_extraction_rules',
            application.attrib[f'{android}dataExtractionRules'],
        )
        self.assertTrue(
            (FLUTTER_ROOT / 'android/app/src/main/res/xml/backup_rules.xml').exists()
        )
        hosts = {
            node.attrib.get(f'{android}host')
            for node in application.findall('.//data')
            if node.attrib.get(f'{android}scheme') == 'flowmateai'
        }
        self.assertEqual({'oauth-callback', 'payment-result'}, hosts)

    def test_poppins_is_bundled_for_offline_startup(self):
        pubspec = (FLUTTER_ROOT / 'pubspec.yaml').read_text(encoding='utf-8')
        theme = (FLUTTER_ROOT / 'lib/theme/app_theme.dart').read_text(
            encoding='utf-8'
        )

        self.assertNotIn('google_fonts:', pubspec)
        self.assertIn('family: Poppins', pubspec)
        self.assertIn("fontFamily: 'Poppins'", theme)
        for name in (
            'Poppins-Regular.ttf',
            'Poppins-Medium.ttf',
            'Poppins-SemiBold.ttf',
            'Poppins-Bold.ttf',
            'Poppins-ExtraBold.ttf',
            'Poppins-Black.ttf',
            'OFL.txt',
        ):
            self.assertGreater((FLUTTER_ROOT / 'assets/fonts' / name).stat().st_size, 0)

    def test_mobile_api_reuses_one_http_connection_pool(self):
        client = (FLUTTER_ROOT / 'lib/api/client.dart').read_text(encoding='utf-8')

        self.assertIn('final http.Client _httpClient = http.Client();', client)
        self.assertIn("'Accept': 'application/json'", client)
        self.assertNotIn('await http.get(', client)
        self.assertNotIn('await http.post(', client)

    def test_secure_session_io_is_parallelized_for_fast_startup(self):
        session = (FLUTTER_ROOT / 'lib/api/session.dart').read_text(encoding='utf-8')

        self.assertGreaterEqual(session.count('Future.wait(['), 3)

    def test_google_oauth_callback_survives_android_cold_start(self):
        main = (FLUTTER_ROOT / 'lib/main.dart').read_text(encoding='utf-8')
        app_state = (FLUTTER_ROOT / 'lib/state/app_state.dart').read_text(
            encoding='utf-8'
        )

        self.assertIn('getInitialLink()', main)
        self.assertIn('consumeGoogleAuthCallback(initialLink)', main)
        self.assertIn('await appState.bootstrapCompleted', main)
        self.assertIn('Future<void> get bootstrapCompleted', app_state)

    def test_native_splash_is_branded_on_old_and_new_android(self):
        resources = FLUTTER_ROOT / 'android/app/src/main/res'
        legacy = (resources / 'drawable/launch_background.xml').read_text(
            encoding='utf-8'
        )
        android_12 = (resources / 'values-v31/styles.xml').read_text(
            encoding='utf-8'
        )

        self.assertIn('@drawable/launch_logo', legacy)
        self.assertIn('windowSplashScreenAnimatedIcon', android_12)
        self.assertIn('@drawable/ic_launcher_foreground', android_12)
        for density in ('mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi'):
            self.assertGreater(
                (resources / f'drawable-{density}/launch_logo.png').stat().st_size,
                0,
            )

    def test_play_build_disables_external_digital_checkout_by_default(self):
        config = (FLUTTER_ROOT / 'lib' / 'api' / 'config.dart').read_text(
            encoding='utf-8'
        )
        settings = (FLUTTER_ROOT / 'lib' / 'screens' / 'settings_screen.dart').read_text(
            encoding='utf-8'
        )

        self.assertIn("'ENABLE_EXTERNAL_PAYMENTS'", config)
        self.assertIn('defaultValue: false', config)
        self.assertIn(
            'kExternalPaymentsEnabled && !startingPayment',
            settings,
        )

    def test_account_deletion_is_available_in_app_and_on_the_web(self):
        settings = (FLUTTER_ROOT / 'lib' / 'screens' / 'settings_screen.dart').read_text(
            encoding='utf-8'
        )
        app = (PROJECT_ROOT / 'web' / 'backend' / 'app.py').read_text(encoding='utf-8')
        deletion_page = PROJECT_ROOT / 'web' / 'frontend' / 'account-deletion.html'

        self.assertIn("apiPost('/user/account/delete'", settings)
        self.assertIn("@app.route('/account-deletion')", app)
        self.assertTrue(deletion_page.exists())
        self.assertIn(
            'mailto:lecaoduyanh123@gmail.com',
            deletion_page.read_text(encoding='utf-8'),
        )

    def test_store_graphics_have_required_dimensions(self):
        # Parse image headers without adding Pillow as a test dependency.
        import struct

        def jpeg_dimensions(path):
            with path.open('rb') as handle:
                self.assertEqual(b'\xff\xd8', handle.read(2))
                while True:
                    marker_start = handle.read(1)
                    if not marker_start:
                        self.fail(f'JPEG size marker missing: {path}')
                    if marker_start != b'\xff':
                        continue
                    marker = handle.read(1)
                    while marker == b'\xff':
                        marker = handle.read(1)
                    if marker in {b'\xd8', b'\xd9'}:
                        continue
                    length = struct.unpack('>H', handle.read(2))[0]
                    if marker in {bytes([value]) for value in range(0xC0, 0xC4)}:
                        handle.read(1)
                        height, width = struct.unpack('>HH', handle.read(4))
                        return width, height
                    handle.seek(length - 2, 1)

        icon = FLUTTER_ROOT / 'play_store' / 'assets' / 'app-icon-512.png'
        feature = FLUTTER_ROOT / 'play_store' / 'assets' / 'feature-graphic-1024x500.jpg'
        with icon.open('rb') as handle:
            self.assertEqual(b'\x89PNG\r\n\x1a\n', handle.read(8))
            handle.read(8)
            width, height = struct.unpack('>II', handle.read(8))
        self.assertEqual((512, 512), (width, height))
        self.assertEqual((1024, 500), jpeg_dimensions(feature))
        self.assertGreater(os.path.getsize(feature), 50_000)

        for name in ('phone-welcome.png', 'phone-login.png', 'phone-register.png'):
            with (FLUTTER_ROOT / 'play_store' / 'assets' / name).open('rb') as handle:
                self.assertEqual(b'\x89PNG\r\n\x1a\n', handle.read(8))
                handle.read(8)
                width, height = struct.unpack('>II', handle.read(8))
            self.assertEqual((1080, 2400), (width, height), name)

    def test_store_listing_copy_fits_play_limits(self):
        import re

        for language in ('vi', 'en'):
            text = (FLUTTER_ROOT / 'play_store' / f'listing-{language}.md').read_text(
                encoding='utf-8'
            )
            sections = re.split(r'^## .+$', text, flags=re.MULTILINE)
            self.assertGreaterEqual(len(sections), 3)
            short_description = sections[1].strip()
            full_description = sections[2].strip()
            self.assertLessEqual(len(short_description), 80, language)
            self.assertLessEqual(len(full_description), 4000, language)
            release_notes = (
                FLUTTER_ROOT / 'play_store' / f'release-notes-{language}.txt'
            ).read_text(encoding='utf-8').strip()
            self.assertLessEqual(len(release_notes), 500, language)


if __name__ == '__main__':
    unittest.main()
