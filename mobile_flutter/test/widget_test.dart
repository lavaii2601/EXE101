import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:flowmate_ai/main.dart';

void main() {
  testWidgets('App boots without throwing', (WidgetTester tester) async {
    await tester.pumpWidget(const FlowMateApp());
    // Initial frame is a branded loading state while secure storage restores
    // the session; it must never regress to an empty screen.
    await tester.pump();
    expect(find.text('FlowMate AI'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}
