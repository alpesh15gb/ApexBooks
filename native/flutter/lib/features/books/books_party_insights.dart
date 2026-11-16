import 'package:material_ui/material_ui.dart';

import '../../core/workspace.dart';
import '../../ui/apex_theme.dart';
import 'books_data.dart';

String _partyPath(WorkspaceContext workspace, String party) =>
    '${workspace.path}/parties/${Uri.encodeComponent(party)}';

Future<DateTime?> suggestedBooksDueDate(
  WorkspaceContext workspace,
  String party,
  String documentDate,
) async {
  final result = booksObject(
    await workspace.api.get(
      '${_partyPath(workspace, party)}/due-date',
      query: {'document_date': documentDate},
    ),
  );
  if (result['party_id'] != party || result['document_date'] != documentDate) {
    return null;
  }
  return DateTime.tryParse(booksText(result['suggested_due_date']));
}

typedef BooksPriceChoice = ({String rate, bool inclusive});

Future<BooksPriceChoice?> showBooksPriceHistory(
  BuildContext context,
  WorkspaceContext workspace,
  String party,
  String item, {
  required bool purchase,
}) {
  final side = purchase ? 'purchase' : 'sales';
  final results = workspace.api.get(
    '${_partyPath(workspace, party)}/item-prices',
    query: {'item_id': item, 'side': side},
  );
  return showDialog<BooksPriceChoice>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Past prices for this party'),
      scrollable: true,
      content: SizedBox(
        width: 440,
        child: FutureBuilder(
          future: results,
          builder: (context, snapshot) {
            if (snapshot.connectionState != ConnectionState.done) {
              return const LinearProgressIndicator(
                semanticsLabel: 'Loading past prices',
              );
            }
            final data = snapshot.data;
            if (data is! Json ||
                data['party_id'] != party ||
                data['item_id'] != item ||
                data['side'] != side ||
                data['history'] is! List) {
              return const Text(
                'Past prices are unavailable. You can enter a rate on the line.',
              );
            }
            final rows = booksRows(data['history']);
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (rows.isEmpty)
                  const Text('No posted prices for this item and party.'),
                for (final row in rows)
                  _priceOption(
                    context,
                    row['rate'],
                    row['price_includes_tax'] == true,
                    '${row['number']} · ${row['date']}',
                  ),
                _priceOption(
                  context,
                  data['default_rate'],
                  false,
                  'Item catalogue price',
                ),
              ],
            );
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Keep current rate'),
        ),
      ],
    ),
  );
}

Widget _priceOption(
  BuildContext context,
  Object? amount,
  bool inclusive,
  String description,
) {
  final rate = booksText(amount);
  if (!RegExp(r'^\d+(?:\.\d+)?$').hasMatch(rate)) {
    return const SizedBox.shrink();
  }
  return ListTile(
    contentPadding: EdgeInsets.zero,
    title: Text(booksMoney(rate)),
    subtitle: Text(inclusive ? '$description · Tax included' : description),
    trailing: const Icon(Icons.chevron_right),
    onTap: () => Navigator.pop(context, (rate: rate, inclusive: inclusive)),
  );
}

class BooksPartyCredit extends StatefulWidget {
  const BooksPartyCredit({
    required this.workspace,
    required this.party,
    required this.day,
    required this.amount,
    super.key,
  });

  final WorkspaceContext workspace;
  final String party;
  final String day;
  final String amount;

  @override
  State<BooksPartyCredit> createState() => _BooksPartyCreditState();
}

class _BooksPartyCreditState extends State<BooksPartyCredit> {
  late final _result = widget.workspace.api.get(
    '${_partyPath(widget.workspace, widget.party)}/credit-status',
    query: {'as_of': widget.day, 'proposed_amount': widget.amount},
  );

  @override
  Widget build(BuildContext context) => FutureBuilder(
    future: _result,
    builder: (context, snapshot) {
      final data = snapshot.data;
      if (snapshot.connectionState != ConnectionState.done) {
        return const Text('Checking the customer’s credit limit…');
      }
      if (data is! Json ||
          data['party_id'] != widget.party ||
          data['as_of'] != widget.day) {
        return const Text('Credit status is unavailable.');
      }
      if (data['credit_limit'] == null) return const SizedBox.shrink();
      final exceeded = data['exceeded'] == true;

      return ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 12),
        tileColor: exceeded ? const Color(0xfffcecea) : Apex.mintSoft,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(10),
          side: BorderSide(
            color: exceeded ? const Color(0xfff0c4c0) : Apex.mintLine,
          ),
        ),
        leading: Icon(
          exceeded
              ? Icons.warning_amber_outlined
              : Icons.account_balance_wallet_outlined,
        ),
        title: Text(
          exceeded ? 'Customer credit limit exceeded' : 'Customer credit limit',
        ),
        subtitle: Text(
          '${booksMoney(data['projected_exposure'])} projected · ${booksMoney(data['credit_limit'])} limit',
        ),
      );
    },
  );
}
