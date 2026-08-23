import 'package:flutter_test/flutter_test.dart';

import 'package:flowmate_ai/main.dart';

void main() {
  testWidgets('Welcome screen shows the FlowMate AI headline', (WidgetTester tester) async {
    await tester.pumpWidget(const FlowMateApp());
    expect(find.text('Chào mừng đến với FlowMate AI'), findsOneWidget);
    expect(find.text('Bắt đầu'), findsOneWidget);
  });
}
