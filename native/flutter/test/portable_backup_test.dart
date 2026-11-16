import 'dart:convert';
import 'dart:typed_data';

import 'package:apex_books/core/portable_backup.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'decrypts a portable envelope produced by an independent AES-GCM writer',
    () async {
      const envelope = '''
{"format":"apex-encrypted-backup","version":1,"salt":"AAECAwQFBgcICQoLDA0ODw==","iv":"EBESExQVFhcYGRob","ciphertext":"N7ISLwSVAunNMJLi9uoHvLBQ2nrt9S3zeOmk58GteYvn"}
''';
      final bytes = Uint8List.fromList(utf8.encode(envelope));
      final raw = await decryptBackup(bytes, 'synthetic safe password');
      expect(utf8.decode(raw), 'Apex format check');
      await expectLater(
        decryptBackup(bytes, 'wrong password'),
        throwsFormatException,
      );
    },
  );

  test(
    'writes authenticated envelopes and rejects modified contents',
    () async {
      final bytes = Uint8List.fromList([0x50, 0x4b, 3, 4, 5, 6]);
      const password = 'synthetic backup password';
      final envelope = await encryptBackup(bytes, password);
      expect(await decryptBackup(envelope, password), bytes);
      final json = jsonDecode(utf8.decode(envelope)) as Map<String, dynamic>;
      final cipher = base64Decode(json['ciphertext'] as String);
      cipher[0] ^= 1;
      json['ciphertext'] = base64Encode(cipher);
      await expectLater(
        decryptBackup(
          Uint8List.fromList(utf8.encode(jsonEncode(json))),
          password,
        ),
        throwsFormatException,
      );
    },
  );
}
