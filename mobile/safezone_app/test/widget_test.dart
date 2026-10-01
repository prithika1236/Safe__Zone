import 'package:flutter_test/flutter_test.dart';
import 'package:safezone_app/main.dart';

void main() {
  testWidgets('SafeZoneApp basic smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const SafeZoneApp());
    expect(find.byType(SafeZoneApp), findsOneWidget);
  });
}
