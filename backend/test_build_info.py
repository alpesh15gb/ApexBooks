import unittest
from build_info import normalized_revision

class BuildIdentityTest(unittest.TestCase):
    def test_only_explicit_full_hex_identity_is_reported(self):
        for value in (None,'','unknown','abc1234','HEAD','refs/heads/main','a'*39,'a'*41,'a'*40+';echo secret',{},123):
            self.assertEqual(normalized_revision(value),'unknown')
        self.assertEqual(normalized_revision(' '+ 'A'*40 +' '),'a'*40)
        self.assertEqual(normalized_revision('b'*64),'b'*64)
