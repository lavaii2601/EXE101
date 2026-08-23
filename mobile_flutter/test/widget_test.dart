import 'package:flutter_test/flutter_test.dart';

import 'package:flowmate_ai/main.dart';

void main() {
  testWidgets('App boots without throwing', (WidgetTester tester) async {
    await tester.pumpWidget(const FlowMateApp());
    // Initial frame is a loading state while AppState.bootstrap() checks the
    // session over the network; just confirm the widget tree builds cleanly.
    await tester.pump();
  });
}
