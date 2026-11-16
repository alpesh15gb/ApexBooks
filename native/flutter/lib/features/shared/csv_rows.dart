typedef CsvRow = ({int line, List<String> values});

List<CsvRow> csvRows(String input, {required int maxDataRows}) {
  if (input.length > 1024 * 1024 || input.contains('\u0000')) {
    throw const FormatException('Use a UTF-8 CSV file below 1 MB.');
  }
  final source = input.startsWith('\uFEFF') ? input.substring(1) : input;
  final rows = <CsvRow>[];
  var columns = <String>[];
  var field = StringBuffer();
  var quoted = false;
  var closedQuote = false;
  var line = 1;
  var start = 1;

  void finishCell() {
    columns.add(field.toString().trim());
    field = StringBuffer();
    closedQuote = false;
  }

  void finishRow() {
    finishCell();
    if (columns.any((value) => value.isNotEmpty)) {
      rows.add((line: start, values: columns));
    }
    columns = [];
    if (rows.length > maxDataRows + 1) {
      throw FormatException('Use at most $maxDataRows rows per import.');
    }
  }

  for (var index = 0; index < source.length; index++) {
    final character = source[index];
    final next = index + 1 < source.length ? source[index + 1] : '';
    if (quoted) {
      if (character == '"' && next == '"') {
        field.write('"');
        index++;
      } else if (character == '"') {
        quoted = false;
        closedQuote = true;
      } else {
        field.write(character);
        if (character == '\n' || (character == '\r' && next != '\n')) line++;
      }
    } else if (character == ',') {
      finishCell();
    } else if (character == '\n' || character == '\r') {
      if (character == '\r' && next == '\n') index++;
      finishRow();
      start = ++line;
    } else if (character == '"' && field.isEmpty && !closedQuote) {
      quoted = true;
    } else if (closedQuote && (character == ' ' || character == '\t')) {
      continue;
    } else if (closedQuote || character == '"') {
      throw FormatException('Check the quotation marks on CSV row $line.');
    } else {
      field.write(character);
    }
  }
  if (quoted) {
    throw FormatException('Close the quoted field that ends on CSV row $line.');
  }
  finishRow();
  if (rows.length < 2) {
    throw const FormatException('Include a header and at least one data row.');
  }
  return rows;
}
