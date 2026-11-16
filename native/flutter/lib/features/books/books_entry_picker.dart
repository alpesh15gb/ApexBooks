import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import 'books_data.dart';

class BooksChoice {
  const BooksChoice(this.record, {this.detail = ''});
  final BooksRecord record;
  final String detail;
}

Future<BooksRecord?> pickBooksRecord(
  BuildContext context,
  WorkspaceContext workspace, {
  required String title,
  required List<String> kinds,
  bool Function(BooksRecord)? accept,
  String Function(BooksRecord)? detail,
}) => showDialog<BooksRecord>(
  context: context,
  builder: (context) => _BooksPicker(
    title: title,
    load: () async {
      final root =
          '/api/companies/${Uri.encodeComponent(workspace.company.id)}';
      final results = <String, BooksChoice>{};
      for (final kind in kinds) {
        var offset = 0;
        while (true) {
          final rows = booksRows(
            await workspace.api.get(
              '$root/records',
              query: {
                'kind': kind,
                'compact': 'true',
                'offset': '$offset',
                'limit': '200',
              },
            ),
          );
          for (final row in rows.map(BooksRecord.new)) {
            if (accept == null || accept(row)) {
              results[row.id] = BooksChoice(
                row,
                detail: detail?.call(row) ?? '',
              );
            }
          }
          if (rows.length < 200) break;
          offset += rows.length;
        }
      }
      return results.values.toList(growable: false);
    },
  ),
);

class _BooksPicker extends StatefulWidget {
  const _BooksPicker({required this.title, required this.load});
  final String title;
  final Future<List<BooksChoice>> Function() load;

  @override
  State<_BooksPicker> createState() => _BooksPickerState();
}

class _BooksPickerState extends State<_BooksPicker> {
  late Future<List<BooksChoice>> _choices;
  String _query = '';

  @override
  void initState() {
    super.initState();
    _choices = widget.load();
  }

  @override
  Widget build(BuildContext context) {
    return Dialog(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 560, maxHeight: 570),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.title,
                      style: Theme.of(context).textTheme.titleLarge,
                    ),
                  ),
                  IconButton(
                    onPressed: () => Navigator.of(context).pop(),
                    tooltip: 'Close',
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                onChanged: (query) => setState(() => _query = query),
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search),
                  labelText: 'Search by name or number',
                ),
              ),
              const SizedBox(height: 8),
              Expanded(
                child: FutureBuilder<List<BooksChoice>>(
                  future: _choices,
                  builder: (context, result) {
                    if (result.connectionState != ConnectionState.done) {
                      return const Center(
                        child: CircularProgressIndicator(
                          semanticsLabel: 'Loading choices',
                        ),
                      );
                    }
                    if (!result.hasData) {
                      return Center(
                        child: OutlinedButton(
                          onPressed: () =>
                              setState(() => _choices = widget.load()),
                          child: const Text('Retry loading choices'),
                        ),
                      );
                    }
                    final matches = result.data!
                        .where((choice) => choice.record.matches(_query))
                        .toList(growable: false);
                    if (matches.isEmpty) {
                      return const Center(child: Text('No matching records.'));
                    }
                    return ListView.builder(
                      itemCount: matches.length,
                      itemBuilder: (context, index) {
                        final choice = matches[index];
                        final row = choice.record;
                        final summary = [
                          if (row.number.isNotEmpty) row.number,
                          choice.detail,
                        ].where((text) => text.isNotEmpty).join(' · ');
                        return ListTile(
                          title: Text(row.party.ifEmptyRecord(row.label)),
                          subtitle: summary.isEmpty ? null : Text(summary),
                          onTap: () => Navigator.of(context).pop(row),
                        );
                      },
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

extension on String {
  String ifEmptyRecord(String fallback) => isEmpty ? fallback : this;
}
