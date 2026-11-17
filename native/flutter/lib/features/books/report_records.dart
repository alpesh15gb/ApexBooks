import '../../core/workspace.dart';
import 'books_data.dart';

/// What the web report page derives from the company records: the party choices and the count of
/// unposted legacy documents named in the transaction summary note.
class ReportRecordInfo {
  const ReportRecordInfo({this.parties = const [], this.legacy = 0});
  final List<String> parties;
  final int legacy;
}

const _legacyKinds = {
  'sales_invoice',
  'purchase_bill',
  'payment_in',
  'payment_out',
};

Future<ReportRecordInfo> loadReportRecordInfo(
  WorkspaceContext workspace,
) async {
  const pageSize = 200;
  final names = <String>{};
  var legacy = 0;
  for (final kind in const [
    'party',
    'sales_invoice',
    'purchase_bill',
    'payment_in',
    'payment_out',
  ]) {
    final seen = <String>{};
    for (var offset = 0; offset < 20000; offset += pageSize) {
      final page = booksRows(
        await workspace.api.get(
          '${workspace.path}/records',
          query: {
            'kind': kind,
            'compact': 'true',
            'limit': '$pageSize',
            'offset': '$offset',
          },
        ),
      );
      final before = seen.length;
      for (final row in page) {
        if (!seen.add(booksText(row['id']))) continue;
        final name = booksText(row['name']);
        final byInvoice =
            row['posted'] == true &&
            (kind == 'sales_invoice' || kind == 'purchase_bill');
        if (name.isNotEmpty && (kind == 'party' || byInvoice)) names.add(name);
        if (_legacyKinds.contains(kind) && row['posted'] == false) legacy++;
      }
      if (page.length < pageSize || seen.length == before) break;
    }
  }
  return ReportRecordInfo(parties: names.toList()..sort(), legacy: legacy);
}
