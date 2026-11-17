import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../ui/apex_theme.dart';
import 'pos_controller.dart';
import 'pos_day_summary.dart';
import 'pos_models.dart';
import 'pos_widgets.dart';

typedef PosRecordsLoader = Future<List<PosJson>> Function();

/// "Daily reconciliation" worksheet from the web `PosRegisterSummary`: posted
/// POS tenders for a business date, a drawer count and the CSV export.
/// With register sessions it sits inside a "Daily totals and CSV export"
/// disclosure; without them it is the whole Register tab.
class PosDailyPanel extends StatefulWidget {
  const PosDailyPanel({
    required this.companyName,
    required this.loadRecords,
    required this.today,
    required this.inDisclosure,
    this.saveFile,
    super.key,
  });

  final String companyName;
  final PosRecordsLoader loadRecords;
  final String Function() today;
  final bool inDisclosure;
  final Future<bool> Function(String name, List<int> bytes)? saveFile;

  @override
  State<PosDailyPanel> createState() => _PosDailyPanelState();
}

class _PosDailyPanelState extends State<PosDailyPanel> {
  late String _date = widget.today();
  late final _dateText = TextEditingController(text: apexDateText(_date));
  final _entries = <String, String>{};
  final _controllers = {
    for (final field in cashCountFields) field.key: TextEditingController(),
  };
  List<PosJson>? _records;
  String _action = '';
  String? _notice;
  bool _noticeIsError = false;
  bool _started = false;

  bool get _busy => _action.isNotEmpty;

  @override
  void initState() {
    super.initState();
    if (!widget.inDisclosure) _start();
  }

  @override
  void dispose() {
    _dateText.dispose();
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  void _start() {
    if (_started) return;
    _started = true;
    _load(refreshOnly: true, quiet: true);
  }

  void _setNotice(String? message, {bool error = false}) => setState(() {
    _notice = message;
    _noticeIsError = error;
  });

  Future<List<PosJson>> _fetch() async {
    try {
      return await widget.loadRecords();
    } catch (error) {
      throw error is PosFailure
          ? error.message
          : 'Could not refresh POS records. Try again.';
    }
  }

  Future<void> _load({required bool refreshOnly, bool quiet = false}) async {
    setState(() {
      _action = refreshOnly ? 'refresh' : 'export';
      _notice = null;
    });
    try {
      final current = await _fetch();
      if (!mounted) return;
      if (refreshOnly) {
        setState(() => _records = current);
        if (!quiet) _setNotice('Posted POS records refreshed.');
        return;
      }
      final before = summarizePosDay(_records ?? const [], _date);
      final latest = summarizePosDay(current, _date);
      final reconciliation = reconcilePosCash(latest, _entries);
      final original = posCloseCsv(
        companyName: widget.companyName,
        date: _date,
        day: before,
        reconciliation: reconcilePosCash(before, _entries),
      );
      if (reconciliation.variance == null ||
          posCloseCsv(
                companyName: widget.companyName,
                date: _date,
                day: latest,
                reconciliation: reconciliation,
              ) !=
              original) {
        setState(() => _records = current);
        _setNotice(
          'Sales or refunds changed. Review the updated figures before exporting.',
          error: true,
        );
        return;
      }
      final bytes = utf8.encode(original);
      final name = 'apex-pos-reconciliation-$_date.csv';
      final saved = widget.saveFile != null
          ? await widget.saveFile!(name, bytes)
          : await saveApexFile(
              name,
              Uint8List.fromList(bytes),
              'text/csv;charset=utf-8',
            );
      if (mounted && saved && !kIsWeb) _setNotice('Saved $name.');
    } catch (error) {
      if (mounted) {
        _setNotice(
          error is String
              ? error
              : error is FormatException
              ? error.message
              : 'Could not refresh POS records.',
          error: true,
        );
      }
    } finally {
      if (mounted) setState(() => _action = '');
    }
  }

  Future<void> _pickDate() async {
    final today = widget.today();
    final current = DateTime.tryParse(_date) ?? DateTime.parse(today);
    final picked = await showDatePicker(
      context: context,
      initialDate: current,
      firstDate: DateTime(2000),
      lastDate: DateTime.parse(today),
    );
    if (picked == null || !mounted) return;
    setState(() {
      _date = picked.toIso8601String().substring(0, 10);
      _dateText.text = apexDateText(_date);
      _entries.clear();
      for (final controller in _controllers.values) {
        controller.clear();
      }
      _notice = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final dateValid = _date.isNotEmpty && _date.compareTo(widget.today()) <= 0;
    final day = summarizePosDay(_records ?? const [], _date);
    final result = reconcilePosCash(day, _entries);
    final variance = result.variance;
    final varianceLabel = variance == null || variance == BigInt.zero
        ? 'Cash variance'
        : variance.isNegative
        ? 'Cash short'
        : 'Cash over';
    String shown(BigInt? value) =>
        value == null ? '—' : drawerMoneyText(value);
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Wrap(
          spacing: 12,
          runSpacing: 10,
          alignment: WrapAlignment.spaceBetween,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 760),
              child: const Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Daily reconciliation',
                    style: TextStyle(
                      fontFamily: Apex.display,
                      fontSize: 22,
                      fontWeight: FontWeight.w600,
                      letterSpacing: -.5,
                      color: Apex.ink,
                    ),
                  ),
                  SizedBox(height: 6),
                  Text(
                    "Review this company's posted POS sales and linked refunds for the business date across all sessions.",
                    style: TextStyle(
                      fontSize: 13,
                      height: 1.5,
                      color: PosColors.muted,
                    ),
                  ),
                ],
              ),
            ),
            OutlinedButton.icon(
              onPressed: _busy ? null : () => _load(refreshOnly: true),
              icon: const Icon(Icons.refresh, size: 16),
              label: Text(
                _action == 'refresh' ? 'Refreshing…' : 'Refresh POS records',
              ),
            ),
          ],
        ),
        if (_notice case final message?) ...[
          const SizedBox(height: 14),
          PosInfoBox(message, error: _noticeIsError),
        ],
        const SizedBox(height: 14),
        Align(
          alignment: Alignment.centerLeft,
          child: SizedBox(
            width: 220,
            child: TextField(
              key: const ValueKey('pos-daily-date'),
              readOnly: true,
              enabled: !_busy,
              controller: _dateText,
              onTap: _pickDate,
              decoration: const InputDecoration(
                labelText: 'Business date',
                suffixIcon: Icon(Icons.calendar_today_outlined, size: 18),
              ),
            ),
          ),
        ),
        if (!dateValid) ...[
          const SizedBox(height: 14),
          Text(
            'Choose today or an earlier business date.',
            style: TextStyle(color: Theme.of(context).colorScheme.error),
          ),
        ],
        if (dateValid) ...[
          const SizedBox(height: 14),
          _tenders(day),
          const SizedBox(height: 14),
          Text(
            '${day.saleCount} ${day.saleCount == 1 ? 'sale' : 'sales'} · ${day.refundCount} linked ${day.refundCount == 1 ? 'refund' : 'refunds'}${day.cancelledCount > 0 ? ' · ${day.cancelledCount} cancelled ${day.cancelledCount == 1 ? 'receipt' : 'receipts'} excluded' : ''}',
          ),
          if (day.unresolvedCount > 0) ...[
            const SizedBox(height: 10),
            Text(
              'Review ${day.unresolvedCount} posted POS sales or refunds with an unresolved tender before reconciling.',
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          const SizedBox(height: 16),
          PosFieldset(
            legend: 'Drawer count',
            children: [
              const Text(
                'Enter the opening float and cash counted. Use the other cash fields for movements outside the POS figures above, such as cash drops.',
                style: TextStyle(fontSize: 13, color: PosColors.muted),
              ),
              for (var index = 0; index < cashCountFields.length; index += 2)
                PosFieldRow([
                  for (final field in cashCountFields.skip(index).take(2))
                    _countField(field, result.invalidFields),
                ]),
            ],
          ),
          const SizedBox(height: 14),
          Semantics(
            liveRegion: true,
            child: PosResultsBox([
              ('Expected cash', shown(result.expected)),
              (
                varianceLabel,
                shown(variance?.abs()),
              ),
            ]),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 12,
            runSpacing: 10,
            alignment: WrapAlignment.spaceBetween,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 520),
                child: const Text(
                  'Export the worksheet for your daily records. Record any accounting adjustment separately.',
                ),
              ),
              OutlinedButton.icon(
                onPressed: _busy || variance == null
                    ? null
                    : () => _load(refreshOnly: false),
                icon: const Icon(Icons.download_outlined, size: 16),
                label: Text(
                  _action == 'export'
                      ? 'Checking POS records…'
                      : 'Export count CSV',
                ),
              ),
            ],
          ),
        ],
      ],
    );
    if (widget.inDisclosure) return body;
    return PosPanel(spacing: 0, children: [body]);
  }

  Widget _countField(CashCountField field, List<String> invalid) {
    final bad = invalid.contains(field.key);
    return TextField(
      controller: _controllers[field.key],
      enabled: !_busy,
      maxLength: 16,
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
      onChanged: (value) => setState(() => _entries[field.key] = value),
      decoration: InputDecoration(
        labelText: '${field.label} (₹)',
        hintText: field.required ? null : '0.00',
        counterText: '',
        errorText: bad
            ? 'Enter a nonnegative amount with up to two decimal places.'
            : null,
        errorMaxLines: 2,
      ),
    );
  }

  Widget _tenders(PosDay day) {
    const head = TextStyle(
      fontSize: 13,
      fontWeight: FontWeight.w700,
      color: PosColors.muted,
    );
    const cell = TextStyle(fontSize: 13.5, color: Apex.ink);
    Widget text(String value, TextStyle style, {bool end = false}) => Padding(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 9),
      child: Text(
        value,
        textAlign: end ? TextAlign.end : TextAlign.start,
        style: style,
      ),
    );
    TableRow row(String label, BigInt sales, BigInt refunds) => TableRow(
      decoration: const BoxDecoration(
        border: Border(top: BorderSide(color: Apex.lineSoft)),
      ),
      children: [
        text(label, cell.copyWith(fontWeight: FontWeight.w600)),
        text(drawerMoneyText(sales), cell, end: true),
        text(drawerMoneyText(refunds), cell, end: true),
        text(
          drawerMoneyText(sales - refunds),
          cell.copyWith(fontWeight: FontWeight.w700),
          end: true,
        ),
      ],
    );
    return Table(
      columnWidths: const {
        0: FlexColumnWidth(1.5),
        1: FlexColumnWidth(1.1),
        2: FlexColumnWidth(1.1),
        3: FlexColumnWidth(1.1),
      },
      children: [
        TableRow(
          children: [
            text('Tender', head),
            text('Sales', head, end: true),
            text('Refunds', head, end: true),
            text('Net', head, end: true),
          ],
        ),
        row('Cash', day.cashSales, day.cashRefunds),
        row('Bank / UPI / card', day.bankSales, day.bankRefunds),
      ],
    );
  }
}

/// "17 Nov 2026" from an ISO date for the date field.
String apexDateText(String iso) {
  final date = DateTime.tryParse(iso);
  if (date == null) return iso;
  const months = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sept',
    'Oct',
    'Nov',
    'Dec',
  ];
  return '${date.day} ${months[date.month - 1]} ${date.year}';
}
