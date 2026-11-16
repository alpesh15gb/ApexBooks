import 'package:material_ui/material_ui.dart';

import 'app.dart';
import 'core/http_api.dart';
import 'core/session.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    runApp(ApexApp(session: ApexSession(origin: apiOrigin())));
  } catch (_) {
    runApp(
      const MaterialApp(
        home: Scaffold(
          body: Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text('Apex Books needs a configured API address.'),
            ),
          ),
        ),
      ),
    );
  }
}
