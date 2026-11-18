import 'package:material_ui/material_ui.dart';

import '../../core/apex_files.dart';
import '../../core/workspace.dart';
import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';
import 'books_detail.dart';
import 'books_report_content.dart';
import 'report_catalog.dart';
import 'report_day_book.dart';
import 'report_filters.dart';
import 'report_library.dart';
import 'report_records.dart';

class BooksReports extends StatefulWidget {
  const BooksReports({
    required this.workspace,
    this.active = true,
    this.revision = 0,
    this.report,
    this.reportRequest = 0,
    super.key,
  });

  final WorkspaceContext workspace;
  final bool active;
  final int revision;

  /// Report to open when the navigation asks for one (for example Day book); null shows the library.
  final BooksReport? report;
  final int reportRequest;

  @override
  State<BooksReports> createState() => _BooksReportsState();
}

class _BooksReportsState extends State<BooksReports> {
  BooksReport? _selected;
  late DateTimeRange _range;
  Future<BooksJson>? _future;
  final _details = <String>[];
  String _appliedParty = '';
  ReportRecordInfo _info = const ReportRecordInfo();
  int _infoGeneration = 0;
  bool _exporting = false;
  bool _customPeriod = false;
  bool _quarterly = false;

  /// Last range used by an ordinary dated report, restored after a GST return or as-of report.
  DateTimeRange? _ordinary;

  BooksData get _data =>
      BooksData(widget.workspace.company.id, widget.workspace.api.get);

  @override
  void initState() {
    super.initState();
    _range = _financialYear();
    if (widget.active) _loadInfo();
    if (widget.report case final report?) {
      _read(report, _initialRange(report), notify: false);
    }
  }

  @override
  void didUpdateWidget(covariant BooksReports oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.workspace.company.id != widget.workspace.company.id ||
        oldWidget.workspace.api != widget.workspace.api) {
      _selected = null;
      _future = null;
      _details.clear();
      _appliedParty = '';
      _info = const ReportRecordInfo();
      if (widget.active) _loadInfo();
      _customPeriod = false;
      _quarterly = false;
      _ordinary = null;
      _range = _financialYear();
    } else if (oldWidget.reportRequest != widget.reportRequest &&
        (oldWidget.report != widget.report || widget.report != _selected)) {
      _details.clear();
      if (widget.report case final report?) {
        _appliedParty = '';
        _read(report, _initialRange(report), notify: false);
      } else {
        _selected = null;
        _future = null;
      }
    } else if (widget.active &&
        (!oldWidget.active || oldWidget.revision != widget.revision)) {
      final report = _selected;
      _future = report != null && _details.isEmpty ? _fetch(report) : null;
      _loadInfo();
    }
  }

  static DateTime _today() => DateTime.parse(businessDate());

  static DateTimeRange _financialYear() {
    final today = _today();
    return DateTimeRange(
      start: DateTime(today.year - (today.month < 4 ? 1 : 0), 4),
      end: today,
    );
  }

  static DateTimeRange _dayRange(DateTime day) =>
      DateTimeRange(start: day, end: day);

  static DateTimeRange _returnRange(DateTime month, bool quarterly) {
    final first = quarterly ? ((month.month - 1) ~/ 3) * 3 + 1 : month.month;
    return DateTimeRange(
      start: DateTime(month.year, first),
      end: DateTime(month.year, first + (quarterly ? 3 : 1), 0),
    );
  }

  DateTimeRange _initialRange(BooksReport report) {
    _customPeriod = false;
    if (report == BooksReport.dayBook) return _dayRange(_financialYear().end);
    if (report.gstReturn) return _returnRange(_today(), _quarterly);
    return _financialYear();
  }

  String get _period {
    if (_customPeriod) return 'custom';
    final today = _today();
    final range = _range;
    bool same(DateTimeRange other) =>
        booksDate(other.start) == booksDate(range.start) &&
        booksDate(other.end) == booksDate(range.end);
    if (same(_dayRange(today))) return 'today';
    if (same(_returnRange(today, false))) return 'month';
    if (same(_returnRange(DateTime(today.year, today.month - 1), false))) {
      return 'last_month';
    }
    if (same(_financialYear())) return 'year';
    return 'custom';
  }

  void _read(BooksReport report, DateTimeRange range, {bool notify = true}) {
    void apply() {
      _selected = report;
      _range = range;
      if (!report.gstReturn && !report.asOfOnly) _ordinary = range;
      _future = _fetch(report);
    }

    notify ? setState(apply) : apply();
  }

  Future<BooksJson> _fetch(BooksReport report) async => booksObject(
    await widget.workspace.api.get(
      '${widget.workspace.path}${report.path}',
      query: _query(report, _range, _appliedParty),
    ),
  );

  /// Web query: the party applies to the party statement and to the as-of balance reports.
  static Map<String, String> _query(
    BooksReport report,
    DateTimeRange range,
    String party,
  ) => {
    ...report.query(range.start, range.end),
    if (_partyReports.contains(report) && party.isNotEmpty) 'party': party,
  };

  static const _partyReports = {
    BooksReport.parties,
    BooksReport.ageing,
    BooksReport.credits,
    BooksReport.advances,
  };

  Future<void> _loadInfo() async {
    final generation = ++_infoGeneration;
    final workspace = widget.workspace;
    try {
      final info = await loadReportRecordInfo(workspace);
      if (!mounted ||
          generation != _infoGeneration ||
          workspace != widget.workspace) {
        return;
      }
      setState(() => _info = info);
    } catch (_) {
      // The party list and the legacy count are conveniences; the report still loads.
    }
  }

  @override
  void dispose() {
    super.dispose();
  }

  Future<void> _export(BooksReport report, String format) async {
    if (_exporting) return;
    final workspace = widget.workspace;
    final range = _range;
    final party = _appliedParty;
    setState(() => _exporting = true);
    try {
      final result = await workspace.api.download(
        '${workspace.path}${report.path}.$format',
        query: _query(report, range, party),
      );
      if (!mounted || !widget.active || workspace != widget.workspace) return;
      final slug = report.title.toLowerCase().replaceAll(
        RegExp('[^a-z0-9]+'),
        '-',
      );
      final mime = switch (format) {
        'pdf' => 'application/pdf',
        'json' => 'application/json',
        _ =>
          'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      };
      await saveApexFile(
        'apex-$slug-${booksDate(range.end)}.$format',
        result,
        mime,
      );
    } catch (failure) {
      if (mounted && widget.active) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              failure is ApexApiException
                  ? failure.message
                  : 'Could not save the report.',
            ),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _exporting = false);
    }
  }

  void _open(String id) => setState(() => _details.add(id));

  void _back() => setState(() {
    _details.removeLast();
    final report = _selected;
    if (_details.isEmpty && report != null && _future == null) {
      _future = _fetch(report);
    }
  });

  /// Switches report keeping the web app's period rules: GST returns use a
  /// return month, as-of reports a single date, everything else a range.
  void _choose(BooksReport next) {
    final current = _selected;
    var range = _range;
    if (next.gstReturn) {
      if (current == null || !current.gstReturn) {
        _quarterly = false;
        range = _returnRange(_today(), false);
      }
    } else if (next.asOfOnly) {
      final end = current != null && current.gstReturn
          ? (_ordinary?.end ?? _today())
          : _range.end;
      range = _dayRange(end);
    } else if (current != null && current.asOfOnly) {
      // The web app keeps one date range: an as-of pick becomes the range end.
      final base = _ordinary ?? _financialYear();
      final end = _range.end;
      final start = base.start.isAfter(end)
          ? DateTime(end.month >= 4 ? end.year : end.year - 1, 4, 1)
          : base.start;
      range = DateTimeRange(start: start, end: end);
      _customPeriod = range != base;
    } else if (current == null || current.gstReturn) {
      range = _ordinary ?? _financialYear();
      _customPeriod = false;
    }
    _read(next, range);
  }

  bool _stale(String companyId, ApexApi api, BooksReport report) =>
      !mounted ||
      !widget.active ||
      companyId != widget.workspace.company.id ||
      api != widget.workspace.api ||
      report != _selected;

  Future<DateTime?> _pickDate(
    BooksReport report, {
    required DateTime initial,
    DateTime? first,
    DateTime? last,
    String help = 'Choose date',
  }) async {
    final companyId = widget.workspace.company.id;
    final api = widget.workspace.api;
    final today = _today();
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      currentDate: today,
      firstDate: first ?? DateTime(1900),
      lastDate: last ?? DateTime(today.year + 2, 12, 31),
      helpText: help,
    );
    if (date == null || _stale(companyId, api, report)) return null;
    return date;
  }

  Future<void> _pickFrom(BooksReport report) async {
    final date = await _pickDate(
      report,
      initial: _range.start,
      last: _range.end,
      help: 'Choose start date',
    );
    if (date == null) return;
    _customPeriod = true;
    _read(report, DateTimeRange(start: date, end: _range.end));
  }

  Future<void> _pickTo(BooksReport report) async {
    final dated = report.asOfOnly;
    final date = await _pickDate(
      report,
      initial: _range.end,
      first: dated ? null : _range.start,
      help: report == BooksReport.dayBook
          ? 'Choose day'
          : dated
          ? 'Choose report date'
          : 'Choose end date',
    );
    if (date == null) return;
    if (dated) {
      _read(report, _dayRange(date));
    } else {
      _customPeriod = true;
      _read(report, DateTimeRange(start: _range.start, end: date));
    }
  }

  Future<void> _pickMonth(BooksReport report) async {
    final date = await _pickDate(
      report,
      initial: _range.start,
      help: 'Choose return month',
    );
    if (date == null) return;
    _read(report, _returnRange(date, _quarterly));
  }

  void _setPeriod(BooksReport report, String period) {
    final today = _today();
    if (period == 'custom') {
      setState(() => _customPeriod = true);
      return;
    }
    _customPeriod = false;
    _read(report, switch (period) {
      'today' => _dayRange(today),
      'month' => _returnRange(today, false),
      'last_month' => _returnRange(
        DateTime(today.year, today.month - 1),
        false,
      ),
      _ => _financialYear(),
    });
  }

  void _shiftDay(BooksReport report, int by) {
    final end = _range.end;
    _read(report, _dayRange(DateTime(end.year, end.month, end.day + by)));
  }

  bool _available(BooksReport report) {
    if (report == BooksReport.statements &&
        !widget.workspace.features.contains('financial_statements')) {
      return false;
    }
    if (report == BooksReport.dayBook &&
        !widget.workspace.features.contains('day_book')) {
      return false;
    }
    return true;
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.active) return const SizedBox.shrink();
    if (_details.isNotEmpty) {
      final id = _details.last;
      return BooksRecordDetail(
        key: ValueKey((_data.companyId, id, widget.revision)),
        data: _data,
        id: id,
        workspace: widget.workspace,
        onOpen: _open,
        onBack: _back,
        backLabel: _details.length == 1 ? 'Back to report' : 'Previous record',
      );
    }
    final report = _selected;
    if (report == null) {
      return ReportLibrary(
        key: ValueKey(widget.workspace.company.id),
        available: _available,
        onSelect: (report) {
          _appliedParty = '';
          _choose(report);
        },
      );
    }
    return _report(context, report);
  }

  Widget _backLink() => Align(
    alignment: Alignment.centerLeft,
    child: TextButton.icon(
      onPressed: () => setState(() {
        _selected = null;
        _future = null;
      }),
      style: TextButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 6),
        minimumSize: const Size(0, 32),
      ),
      icon: const Icon(Icons.arrow_back_rounded, size: 16),
      label: const Text('All reports'),
    ),
  );

  Widget _banner(String message, {VoidCallback? retry, String? detail}) =>
      Padding(
        padding: const EdgeInsets.only(top: 16),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: const Color(0xfffcecea),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: const Color(0xfff0c4c0)),
          ),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        message,
                        style: const TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: Apex.red,
                        ),
                      ),
                      if (detail != null && detail.isNotEmpty)
                        Text(
                          detail,
                          style: const TextStyle(
                            fontSize: 12.5,
                            color: Apex.red,
                          ),
                        ),
                    ],
                  ),
                ),
                if (retry != null)
                  TextButton(onPressed: retry, child: const Text('Retry')),
              ],
            ),
          ),
        ),
      );

  Widget _loading() => Padding(
    padding: const EdgeInsets.only(top: 16),
    child: Semantics(
      liveRegion: true,
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LinearProgressIndicator(semanticsLabel: 'Loading report'),
          SizedBox(height: 10),
          Text(
            'Loading report…',
            style: TextStyle(fontSize: 13, color: Apex.muted),
          ),
        ],
      ),
    ),
  );

  List<Widget> _exports(BooksReport report, BooksJson? data, bool done) {
    if (!report.exportable) return const [];
    final ready = data != null && done && !_exporting;
    Widget button(
      String label,
      String format, {
      bool enabled = true,
      String? tip,
    }) {
      final child = OutlinedButton.icon(
        onPressed: ready && enabled ? () => _export(report, format) : null,
        icon: _exporting
            ? const SizedBox.square(
                dimension: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.download_outlined, size: 16),
        label: Text(label),
      );
      return tip == null ? child : Tooltip(message: tip, child: child);
    }

    final json =
        report == BooksReport.gstr1 &&
        data != null &&
        data['export_info'] is Map &&
        (data['export_info'] as Map)['json_available'] == true;
    return [
      button(switch (report) {
        BooksReport.gstr1 => 'GSTN format XLSX',
        BooksReport.gstr2a => 'Purchase books XLSX',
        BooksReport.gstr3b => '3B working XLSX',
        _ => 'XLSX',
      }, 'xlsx'),
      button(report.gstReturn ? 'Working PDF' : 'PDF', 'pdf'),
      if (report == BooksReport.gstr1)
        button(
          'Draft JSON',
          'json',
          enabled: json,
          tip: json
              ? 'Preparation JSON for review in the GST offline tool'
              : 'Resolve the preparation checks shown below',
        ),
    ];
  }

  Widget _report(BuildContext context, BooksReport report) {
    final phone = MediaQuery.sizeOf(context).width < 700;
    final dayBook = report == BooksReport.dayBook;
    return FutureBuilder<BooksJson>(
      future: _future,
      builder: (context, snapshot) {
        final done = snapshot.connectionState == ConnectionState.done;
        final data = snapshot.data;
        final failed = done && data == null;
        void retry() => _read(report, _range);
        final error = snapshot.error;
        final detail = error is ApexApiException ? error.message : null;
        return ApexPage(
          children: [
            if (!dayBook) _backLink(),
            if (dayBook) ...[
              ReportDayBar(
                day: _range.end,
                today: _today(),
                onShift: (by) => _shiftDay(report, by),
                onPick: () => _pickTo(report),
                onToday: () => _read(report, _dayRange(_today())),
              ),
              const SizedBox(height: 4),
              if (failed)
                _banner(
                  'Could not load this report.',
                  retry: retry,
                  detail: detail,
                ),
              ReportDayBook(
                day: booksDate(_range.end),
                data: data,
                failed: failed,
                onOpenRecord: _open,
              ),
            ] else ...[
              ApexPageHeading(
                report.title,
                subtitle: reportSubtitle(report),
                compact: phone,
                actions: [
                  ..._exports(report, data, done),
                  ApexRowIconButton(
                    icon: Icons.refresh_rounded,
                    tooltip: 'Refresh report',
                    onPressed: done ? retry : null,
                  ),
                ],
              ),
              const SizedBox(height: 22),
              ReportFilterPanel(
                report: report,
                reports: [
                  for (final group in reportGroups)
                    for (final item in group.reports)
                      if (_available(item)) item,
                ],
                onReport: (next) {
                  if (next != report) _choose(next);
                },
                range: _range,
                period: _period,
                onPeriod: (period) => _setPeriod(report, period),
                onPickFrom: () => _pickFrom(report),
                onPickTo: () => _pickTo(report),
                onPickMonth: () => _pickMonth(report),
                quarterly: _quarterly,
                onQuarterly: (value) {
                  _quarterly = value;
                  _read(report, _returnRange(_range.start, value));
                },
                party: _info.parties.contains(_appliedParty)
                    ? _appliedParty
                    : '',
                parties: _info.parties,
                onParty: (name) {
                  _appliedParty = name;
                  _read(report, _range);
                },
              ),
              if (!done)
                _loading()
              else if (data == null)
                _banner(
                  'Could not load this report.',
                  retry: retry,
                  detail: detail,
                )
              else
                BooksReportContent(
                  report: report,
                  data: data,
                  onOpenRecord: _open,
                  asOf: booksDate(_range.end),
                  party: _appliedParty,
                  fetch: widget.workspace.api.get,
                  root: widget.workspace.path,
                  from: booksDate(_range.start),
                  stockHistory: widget.workspace.features.contains(
                    'stock_movement_history',
                  ),
                  legacy: _info.legacy,
                ),
            ],
          ],
        );
      },
    );
  }
}
