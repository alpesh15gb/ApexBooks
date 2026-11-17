import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';

/// Version of this app; keep in step with `version:` in pubspec.yaml.
const apexAppVersion = '1.5.0';
const _appRevision = String.fromEnvironment('APEX_BUILD_SHA');

String normalizedBuildRevision(Object? value) =>
    value is String && RegExp(r'^(?:[a-f0-9]{40}|[a-f0-9]{64})$', caseSensitive: false).hasMatch(value.trim())
    ? value.trim().toLowerCase()
    : 'unknown';

/// Web "About ApexBooks": version and source revisions, for support.
class SettingsAbout extends StatefulWidget {
  const SettingsAbout({required this.api, super.key});

  final ApexApi api;

  @override
  State<SettingsAbout> createState() => _SettingsAboutState();
}

class _SettingsAboutState extends State<SettingsAbout> {
  Json? _build;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      final value = await widget.api.get('/api/capabilities');
      if (mounted && value is Map<String, dynamic>) setState(() => _build = value);
    } catch (_) {
      // The summary then shows "unknown", like the web app without capabilities.
    }
  }

  @override
  Widget build(BuildContext context) {
    const text = TextStyle(fontSize: 12, height: 1.6, color: Apex.muted);
    const code = TextStyle(fontFamily: 'monospace', fontSize: 11, color: Apex.inkSoft);
    Widget line(String label, String value) => Padding(
      padding: const EdgeInsets.only(top: 4),
      child: Text.rich(
        TextSpan(style: text, children: [
          TextSpan(text: '$label '),
          TextSpan(text: value, style: code),
        ]),
      ),
    );
    return Material(
      color: Colors.transparent,
      child: Theme(
      data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: const EdgeInsets.symmetric(horizontal: 4),
        childrenPadding: const EdgeInsets.fromLTRB(4, 0, 4, 8),
        expandedAlignment: Alignment.centerLeft,
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        dense: true,
        title: const Text('About ApexBooks', style: TextStyle(fontSize: 12, color: Apex.muted)),
        children: [
          Text('App $apexAppVersion · API ${_build?['api_version'] ?? 'unknown'}', style: text),
          const SizedBox(height: 6),
          const Text('For support, source revisions:', style: TextStyle(fontSize: 11, color: Apex.muted)),
          line('App', normalizedBuildRevision(_appRevision)),
          line('API', normalizedBuildRevision(_build?['build_revision'])),
        ],
      ),
    ));
  }
}
