import 'dart:convert';

import 'pos_models.dart';

BigInt registerPaise(Object? value) {
  final match = RegExp(r'^(-?)(\d+)(?:\.(\d{1,2}))?$')
      .firstMatch(posText(value));
  if (match == null) {
    throw const FormatException(
      'The register returned an invalid cash amount.',
    );
  }
  return BigInt.parse(
    '${match[1]}${match[2]}${(match[3] ?? '').padRight(2, '0')}',
  );
}

class PosRegisterSession {
  PosRegisterSession.fromJson(PosJson row)
    : id = posText(row['id']),
      date = posText(row['date']),
      data = posObject(row['data']),
      snapshot = posText(row['snapshot']),
      movementRows =
          (row['movements'] as List?)?.map(posObject).toList() ?? [] {
    if (id.isEmpty || row['kind'] != 'pos_register_session') {
      throw const FormatException('The server did not return a register.');
    }
    totals = posObject(closed ? data['closed_totals'] : row['totals']);
    opening = registerPaise(data['opening_float']);
    expected = registerPaise(totals['expected_cash']);
    if (!closed && !RegExp(r'^[0-9a-f]{64}$').hasMatch(snapshot)) {
      throw const FormatException('The register snapshot is missing.');
    }
  }

  final String id;
  final String date;
  final String snapshot;
  final PosJson data;
  final List<PosJson> movementRows;
  late final PosJson totals;
  late final BigInt opening;
  late final BigInt expected;

  bool get closed => posText(data['closed_at']).isNotEmpty;
  BigInt get counted => registerPaise(data['counted_cash']);
  BigInt get variance => registerPaise(data['variance']);
  String get reason => posText(data['close_reason']);
  BigInt total(String field) => registerPaise(totals[field]);
}

class PosRegisterOverview {
  PosRegisterOverview.fromJson(PosJson response)
    : active = response['active'] == null
          ? null
          : PosRegisterSession.fromJson(posObject(response['active'])),
      closed = posList(response['closed'])
          .map(posObject)
          .map(PosRegisterSession.fromJson)
          .toList();

  final PosRegisterSession? active;
  final List<PosRegisterSession> closed;
}

enum RegisterOperation { open, movement, close }

class PosRegisterCommand {
  PosRegisterCommand.create({
    required this.action,
    required PosJson body,
    this.registerId = '',
  }) : key = newPosKey(),
       payload = jsonEncode(body);

  PosRegisterCommand.fromJson(PosJson json)
    : action = RegisterOperation.values.byName(posText(json['action'])),
      registerId = posText(json['register_id']),
      key = posText(json['key']),
      payload = posText(json['payload']) {
    if (!RegExp(r'^[0-9a-f]{48}$').hasMatch(key) ||
        (action == RegisterOperation.open
            ? registerId.isNotEmpty
            : registerId.isEmpty)) {
      throw const FormatException(
        'The saved register operation is incomplete.',
      );
    }
    if (body.isEmpty) {
      throw const FormatException(
        'The saved register operation is incomplete.',
      );
    }
  }

  final RegisterOperation action;
  final String registerId;
  final String key;
  final String payload;
  PosJson get body => posObject(jsonDecode(payload));

  PosJson toJson() => {
    'action': action.name,
    'register_id': registerId,
    'key': key,
    'payload': payload,
  };
}
