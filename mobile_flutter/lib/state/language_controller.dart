import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _storage = FlutterSecureStorage();
const _languageKey = 'flowmate.language';

class LanguageController extends ChangeNotifier {
  String language = 'vi';

  LanguageController() {
    _load();
  }

  Future<void> _load() async {
    final stored = await _storage.read(key: _languageKey);
    if (stored == 'en' || stored == 'vi') {
      language = stored!;
      notifyListeners();
    }
  }

  Future<void> setLanguage(String next) async {
    language = next == 'en' ? 'en' : 'vi';
    notifyListeners();
    await _storage.write(key: _languageKey, value: language);
  }

  /// Mirrors LanguageContext.js's t(vietnamese, english) helper.
  String t(String vietnamese, [String? english]) {
    return language == 'en' ? (english ?? vietnamese) : vietnamese;
  }
}
