import 'package:apex_books/features/banking/bank_data.dart';
import 'package:apex_books/features/banking/bank_forms.dart';
import 'package:apex_books/features/banking/bank_match.dart';
import 'package:apex_books/core/workspace.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_ui/material_ui.dart';

void main() {
  group('statement CSV', () {
    test('HDFC style: Withdrawal Amt / Deposit Amt with DD/MM/YY', () {
      final rows = statementEntries(
        'Account Statement,,,\n'
        'Date,Narration,Chq./Ref.No.,Value Dt,Withdrawal Amt.,Deposit Amt.,Closing Balance\n'
        '01/04/26,UPI-RAVI STORES,0000123,01/04/26,"1,250.50",,"10,000.00"\n'
        '02/04/26,NEFT-ACME LTD,UTR99,02/04/26,,"25,000.00","35,000.00"\n',
      );
      expect(rows, hasLength(2));
      expect(rows[0], {
        'date': '2026-04-01',
        'description': 'UPI-RAVI STORES',
        'reference': '',
        'amount': '-1250.50',
      });
      expect(rows[1]['amount'], '25000.00');
      expect(rows[1]['date'], '2026-04-02');
    });

    test('SBI style: Debit / Credit with DD-MMM-YYYY and Ref No', () {
      final rows = statementEntries(
        'Txn Date,Value Date,Description,Ref No./Cheque No.,Debit,Credit,Balance\n'
        '15-Apr-2026,15-Apr-2026,ATM WDL,REF1,500.00,,9500.00\n'
        '16-Apr-2026,16-Apr-2026,SALARY,REF2,,"40,000.00",49500.00\n',
      );
      expect(rows[0]['date'], '2026-04-15');
      expect(rows[0]['amount'], '-500.00');
      expect(rows[0]['description'], 'ATM WDL');
      expect(rows[1]['amount'], '40000.00');
    });

    test('semicolon and tab files with ISO dates and rupee amounts', () {
      final semicolon = statementEntries(
        'Date;Particulars;Amount\n2026-05-01;Rent;₹ -12,000.00\n',
      );
      expect(semicolon.single['amount'], '-12000.00');
      final tab = statementEntries('Date\tRemarks\tAmount\n2026-05-02\tSale\t300\n');
      expect(tab.single, containsPair('description', 'Sale'));
    });

    test('Cr/Dr suffixes and parentheses set the sign', () {
      final rows = statementEntries(
        'Date,Description,Amount\n'
        '01-05-2026,A,"1,000.00 Cr"\n'
        '02-05-2026,B,250.00Dr\n'
        '03-05-2026,C,(75.50)\n',
      );
      expect([for (final r in rows) r['amount']], ['1000.00', '-250.00', '-75.50']);
    });

    test('rejects bad dates, zero amounts and both debit and credit', () {
      expect(
        () => statementEntries('Date,Description,Amount\n31/02/2026,X,5'),
        throwsFormatException,
      );
      expect(
        () => statementEntries('Date,Description,Amount\n01/02/2026,X,0'),
        throwsFormatException,
      );
      expect(
        () => statementEntries('Date,Description,Debit,Credit\n01/02/2026,X,5,5'),
        throwsFormatException,
      );
    });

    test('MM/DD/YYYY is honoured when chosen', () {
      expect(
        statementEntries('Date,Description,Amount\n04/30/2026,X,5', dmy: false)
            .single['date'],
        '2026-04-30',
      );
    });
  });

  group('match score', () {
    final line = {
      'date': '2026-04-10',
      'description': 'NEFT Ravi Traders INV-7',
      'reference': '',
      'remaining_amount': '100.00',
    };
    test('weights number, amount, name and date proximity', () {
      final record = {
        'number': 'INV-7',
        'name': 'Ravi Traders',
        'date': '2026-04-09',
      };
      expect(bankMatchScore(line, record, BigInt.from(10000)), 160);
      expect(
        bankMatchScore(
          line,
          {'number': 'X', 'name': 'Other', 'date': '2026-04-01'},
          BigInt.from(500),
        ),
        0,
      );
      expect(
        bankMatchScore(
          line,
          {'number': 'X', 'name': 'Other', 'date': '2026-04-05'},
          BigInt.from(500),
        ),
        10,
      );
    });

    test('sorts by score then newest date', () {
      MatchCandidate c(String date, int score) =>
          (record: {'date': date}, available: BigInt.one, score: score);
      final list = [c('2026-01-01', 10), c('2026-01-02', 90), c('2026-01-03', 10)]
        ..sort(compareMatchCandidates);
      expect([for (final x in list) x.record['date']], [
        '2026-01-02',
        '2026-01-03',
        '2026-01-01',
      ]);
    });
  });

  testWidgets('transfer description defaults per direction and is required', (
    tester,
  ) async {
    Json? result;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (context) => TextButton(
            onPressed: () async => result = await showDialog<Json>(
              context: context,
              builder: (_) => const TransferForm(
                accounts: [
                  {'id': 'default', 'name': 'Main'},
                ],
                bank: 'default',
              ),
            ),
            child: const Text('open'),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    final description = find.widgetWithText(TextField, 'Description');
    expect(tester.widget<TextField>(description).controller!.text, 'Cash deposit');

    await tester.tap(find.byType(DropdownButtonFormField<String>).first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Bank to cash').last);
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(description).controller!.text, 'Cash withdrawal');

    await tester.enterText(description, '');
    await tester.enterText(find.widgetWithText(TextField, 'Amount (₹)'), '10');
    await tester.tap(find.text('Review transfer'));
    await tester.pumpAndSettle();
    expect(find.text('Enter a description for this transfer.'), findsOneWidget);

    await tester.enterText(description, 'Petty cash');
    await tester.tap(find.text('Review transfer'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Post transfer'));
    await tester.pumpAndSettle();
    expect(result!['name'], 'Petty cash');
  });
}
