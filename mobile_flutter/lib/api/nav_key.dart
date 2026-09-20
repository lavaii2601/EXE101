import 'package:flutter/widgets.dart';

// Lets non-widget code (client.dart's centralized 401 handler) show a
// dialog without a BuildContext passed down through every call site. Wired
// into MaterialApp(navigatorKey: navigatorKey) in main.dart.
final navigatorKey = GlobalKey<NavigatorState>();
