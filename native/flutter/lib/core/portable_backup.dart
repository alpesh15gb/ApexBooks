import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';

const encryptedBackupMaximum = 12 * 1024 * 1024;
const encryptableBackupMaximum = 8 * 1024 * 1024;
const _format = 'apex-encrypted-backup';

SecretKey _passwordMaterial(String password) =>
    SecretKey(utf8.encode(password));

Future<SecretKey> _derive(String password, List<int> salt) async {
  final material = _passwordMaterial(password);
  try {
    return await Pbkdf2(
      macAlgorithm: Hmac.sha256(),
      iterations: 250000,
      bits: 256,
    ).deriveKey(secretKey: material, nonce: salt);
  } finally {
    material.destroy();
  }
}

Future<Uint8List> encryptBackup(Uint8List bytes, String password) async {
  if (bytes.length > encryptableBackupMaximum) {
    throw const FormatException('Encrypted backups support up to 8 MB.');
  }
  if (password.length < 12) {
    throw const FormatException(
      'Use a backup password of at least 12 characters.',
    );
  }
  final random = Random.secure();
  final salt = List<int>.generate(16, (_) => random.nextInt(256));
  final cipher = AesGcm.with256bits();
  final key = await _derive(password, salt);
  try {
    final box = await cipher.encrypt(
      bytes,
      secretKey: key,
      nonce: cipher.newNonce(),
    );
    return Uint8List.fromList(
      utf8.encode(
        jsonEncode({
          'format': _format,
          'version': 1,
          'salt': base64Encode(salt),
          'iv': base64Encode(box.nonce),
          'ciphertext': base64Encode([...box.cipherText, ...box.mac.bytes]),
        }),
      ),
    );
  } finally {
    key.destroy();
  }
}

Future<Uint8List> decryptBackup(Uint8List bytes, String password) async {
  if (bytes.length > encryptedBackupMaximum) {
    throw const FormatException('This encrypted backup exceeds 12 MB.');
  }
  final object = jsonDecode(utf8.decode(bytes));
  if (object is! Map || object['format'] != _format || object['version'] != 1) {
    throw const FormatException('Unsupported encrypted backup format.');
  }
  if (password.isEmpty) {
    throw const FormatException(
      'Enter the password used to encrypt this backup.',
    );
  }
  final salt = _decode(object['salt'], 16, 16);
  final iv = _decode(object['iv'], 12, 12);
  final encrypted = _decode(
    object['ciphertext'],
    16,
    encryptableBackupMaximum + 16,
  );
  final cipherLength = encrypted.length - 16;
  final key = await _derive(password, salt);
  try {
    final raw = await AesGcm.with256bits().decrypt(
      SecretBox(
        Uint8List.sublistView(encrypted, 0, cipherLength),
        nonce: iv,
        mac: Mac(Uint8List.sublistView(encrypted, cipherLength)),
      ),
      secretKey: key,
    );
    return Uint8List.fromList(raw);
  } on SecretBoxAuthenticationError {
    throw const FormatException(
      'The password is incorrect or the encrypted backup is damaged.',
    );
  } finally {
    key.destroy();
  }
}

Uint8List _decode(Object? input, int minimum, int maximum) {
  if (input is! String ||
      input.length % 4 != 0 ||
      input.length > ((maximum + 2) ~/ 3) * 4 ||
      !RegExp(r'^[A-Za-z0-9+/]*={0,2}$').hasMatch(input)) {
    throw const FormatException('Invalid encrypted backup metadata.');
  }
  final bytes = base64Decode(input);
  if (bytes.length < minimum || bytes.length > maximum) {
    throw const FormatException('Invalid encrypted backup metadata.');
  }
  return bytes;
}
