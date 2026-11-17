import 'package:material_ui/material_ui.dart';

import '../../ui/apex_register.dart';
import '../../ui/apex_theme.dart';
import '../../ui/apex_widgets.dart';
import 'books_data.dart';

const _mon = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/// The web's ledger date, 01-Apr-2026.
String _ledgerDate(DateTime date) =>
    '${date.day.toString().padLeft(2, '0')}-${_mon[date.month - 1]}-${date.year}';

String reportFieldDate(DateTime date) =>
    '${date.day.toString().padLeft(2, '0')}-${date.month.toString().padLeft(2, '0')}-${date.year}';

const reportPeriods = <(String, String)>[
  ('today', 'Today'),
  ('month', 'This month'),
  ('last_month', 'Last month'),
  ('year', 'This financial year'),
  ('custom', 'Custom dates'),
];

/// Date field that looks like the register filter selects and opens a picker.
class ReportDateField extends StatelessWidget {
  const ReportDateField({
    required this.label,
    required this.text,
    required this.onTap,
    this.width = 200,
    super.key,
  });

  final String label;
  final String text;
  final VoidCallback onTap;
  final double width;

  @override
  Widget build(BuildContext context) => SizedBox(
    width: width,
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: Apex.muted,
          ),
        ),
        const SizedBox(height: 6),
        Semantics(
          button: true,
          label: '$label, $text',
          excludeSemantics: true,
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(Apex.radiusChip),
            child: Container(
              height: 40,
              padding: const EdgeInsets.symmetric(horizontal: 11),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(Apex.radiusChip),
                border: Border.all(color: Apex.fieldBorder),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      text,
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w500,
                        color: Color(0xff27313d),
                      ),
                    ),
                  ),
                  const Icon(Icons.calendar_today_outlined, size: 16),
                ],
              ),
            ),
          ),
        ),
      ],
    ),
  );
}

/// The web report workbench filters: Report, then Period / From / To (or As of,
/// or the GST return frequency and month), plus the party name for the statement.
class ReportFilterPanel extends StatelessWidget {
  const ReportFilterPanel({
    required this.report,
    required this.reports,
    required this.onReport,
    required this.range,
    required this.period,
    required this.onPeriod,
    required this.onPickFrom,
    required this.onPickTo,
    required this.onPickMonth,
    required this.quarterly,
    required this.onQuarterly,
    required this.party,
    required this.parties,
    required this.onParty,
    super.key,
  });

  final BooksReport report;
  final List<BooksReport> reports;
  final ValueChanged<BooksReport> onReport;
  final DateTimeRange range;
  final String period;
  final ValueChanged<String> onPeriod;
  final VoidCallback onPickFrom;
  final VoidCallback onPickTo;
  final VoidCallback onPickMonth;
  final bool quarterly;
  final ValueChanged<bool> onQuarterly;
  final String party;
  final List<String> parties;
  final ValueChanged<String> onParty;

  static const _months = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];

  @override
  Widget build(BuildContext context) => ApexPanel(
    radius: 10,
    padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
    child: LayoutBuilder(
      builder: (context, limits) {
        final phone = limits.maxWidth < 640;
        double width(double wide) => phone ? limits.maxWidth : wide;
        final children = <Widget>[
          ApexFilterSelect<BooksReport>(
            label: 'Report',
            width: width(280),
            value: reports.contains(report) ? report : reports.first,
            items: [for (final item in reports) (item, item.title)],
            onChanged: onReport,
          ),
          if (report.gstReturn) ...[
            ApexFilterSelect<bool>(
              label: 'Return frequency',
              width: width(180),
              value: quarterly,
              items: const [(false, 'Monthly'), (true, 'Quarterly')],
              onChanged: onQuarterly,
            ),
            ReportDateField(
              label: quarterly ? 'Month in return quarter' : 'Return month',
              text: '${_months[range.start.month - 1]} ${range.start.year}',
              width: width(220),
              onTap: onPickMonth,
            ),
          ] else if (report.asOfOnly)
            ReportDateField(
              label: report == BooksReport.dayBook ? 'Day' : 'As of',
              text: reportFieldDate(range.end),
              width: width(200),
              onTap: onPickTo,
            )
          else ...[
            ApexFilterSelect<String>(
              label: 'Period',
              width: width(220),
              value: period,
              items: reportPeriods,
              onChanged: onPeriod,
            ),
            ReportDateField(
              label: 'From',
              text: reportFieldDate(range.start),
              width: width(200),
              onTap: onPickFrom,
            ),
            ReportDateField(
              label: 'To',
              text: reportFieldDate(range.end),
              width: width(200),
              onTap: onPickTo,
            ),
          ],
          if (const {
            BooksReport.parties,
            BooksReport.ageing,
            BooksReport.credits,
            BooksReport.advances,
          }.contains(report))
            ApexFilterSelect<String>(
              label: 'Party',
              width: width(280),
              value: party,
              items: [
                ('', 'All parties'),
                for (final name in parties) (name, name),
              ],
              onChanged: onParty,
            ),
        ];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(spacing: 16, runSpacing: 14, children: children),
            if (report.gstReturn || !report.asOfOnly) ...[
              const SizedBox(height: 10),
              Text(
                report.gstReturn
                    ? '${booksDate(range.start)} to ${booksDate(range.end)}'
                    : '${_ledgerDate(range.start)} to ${_ledgerDate(range.end)}',
                style: Apex.small,
              ),
            ],
          ],
        );
      },
    ),
  );
}
