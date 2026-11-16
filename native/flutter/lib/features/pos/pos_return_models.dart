import 'dart:convert';

import 'pos_models.dart';

enum PosReturnSettlement { credit, cash, bank }

class PosReturnLine {
  PosReturnLine(this.index, PosJson line)
    : description = posText(line['description']),
      unit = posText(line['unit']),
      available = posText(line['remaining_return_quantity']),
      reason = posText(line['return_capacity_reason']);

  final int index;
  final String description;
  final String unit;
  final String available;
  final String reason;

  int? get quantity {
    final value = RegExp(r'^(\d+)(?:\.(\d+))?$').firstMatch(available);
    if (value == null) return null;
    final whole = value[1]!.replaceFirst(RegExp(r'^0+'), '');
    if (whole.length > 12) return 999999999999999;
    final fraction = (value[2] ?? '').padRight(3, '0').substring(0, 3);
    return parsePosDecimal(
      '${whole.isEmpty ? '0' : whole}.$fraction',
      3,
      wholeDigits: 12,
    );
  }
}

class PosReturnCommand {
  PosReturnCommand.create(this.receiptId, PosJson body)
    : key = newPosKey(),
      payload = jsonEncode(body);

  PosReturnCommand.fromJson(PosJson json)
    : receiptId = posText(json['receipt_id']),
      key = posText(json['key']),
      payload = posText(json['payload']) {
    if (receiptId.isEmpty ||
        !RegExp(r'^[0-9a-f]{48}$').hasMatch(key) ||
        parsePosMoney(posText(body['expected_total'])) == null) {
      throw const FormatException('The saved return is incomplete.');
    }
  }

  final String receiptId;
  final String key;
  final String payload;
  PosJson get body => posObject(jsonDecode(payload));
  PosJson toJson() => {'receipt_id': receiptId, 'key': key, 'payload': payload};
}

class PosReturnResult {
  PosReturnResult.fromJson(PosJson result, PosReturnCommand command)
    : credit = posObject(result['credit_note']),
      refund = result['refund'] == null ? null : posObject(result['refund']) {
    final body = command.body;
    final data = posObject(credit['data']);
    if (credit['kind'] != 'credit_note' ||
        posText(credit['id']).isEmpty ||
        posText(credit['number']).isEmpty ||
        data['applied_to'] != command.receiptId ||
        amount != parsePosMoney(posText(body['expected_total']))) {
      throw const FormatException(
        'The server did not confirm the original return.',
      );
    }
    if (body['payment_account'] != null) {
      final settlement = refund;
      if (settlement == null ||
          posText(settlement['id']).isEmpty ||
          posText(settlement['number']).isEmpty ||
          settlement['kind'] != 'customer_refund' ||
          parsePosMoney(posText(settlement['amount'])) != amount) {
        throw const FormatException(
          'The server did not confirm the original refund.',
        );
      }
      final settlementData = posObject(settlement['data']);
      if (settlementData['credit_note_id'] != credit['id'] ||
          settlementData['payment_account'] != body['payment_account']) {
        throw const FormatException('The server returned a different refund.');
      }
    } else if (refund != null) {
      throw const FormatException('The server returned an unexpected refund.');
    }
  }

  final PosJson credit;
  final PosJson? refund;

  int? get amount => parsePosMoney(posText(credit['amount']));
  String get creditNumber => posText(credit['number']);
  String get refundNumber => posText(refund?['number']);
  bool get active =>
      credit['posted'] == true &&
      credit['cancelled'] != true &&
      (refund == null ||
          refund?['posted'] == true && refund?['cancelled'] != true);
}
