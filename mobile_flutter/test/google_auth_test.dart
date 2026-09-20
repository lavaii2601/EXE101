import 'package:flutter_test/flutter_test.dart';

import 'package:flowmate_ai/api/google_auth.dart';

void main() {
  group('Google OAuth deep links', () {
    test('accepts only the exact OAuth callback route', () {
      expect(
        isGoogleAuthCallback(
          Uri.parse('flowmateai://oauth-callback?access_token=signed-token'),
        ),
        isTrue,
      );
      expect(
        isGoogleAuthCallback(
          Uri.parse('flowmateai://payment-result?access_token=signed-token'),
        ),
        isFalse,
      );
      expect(
        isGoogleAuthCallback(
          Uri.parse('https://oauth-callback?access_token=signed-token'),
        ),
        isFalse,
      );
    });
  });
}
