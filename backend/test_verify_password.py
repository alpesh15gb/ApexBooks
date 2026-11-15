"""Password re-check used to reveal hidden dashboard figures."""
import unittest

import test_completion


class VerifyPasswordTest(unittest.TestCase):
    def setUp(self):
        self.client, self.headers, _ = test_completion.CompletionTest.client_context(self)
        self.password = self.credentials['password']

    def check(self, password, headers=None):
        return self.client.post('/api/auth/verify-password', headers=self.headers if headers is None else headers,
                                json={'password': password})

    def test_correct_password_is_verified_without_a_new_session(self):
        response = self.check(self.password)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'verified': True})
        self.assertNotIn('token', response.json())
        # The original session is untouched.
        self.assertEqual(self.client.get('/api/companies', headers=self.headers).status_code, 200)

    def test_wrong_password_is_forbidden_not_unauthorized_and_keeps_the_session(self):
        for wrong in ('wrong-password', ''):
            response = self.check(wrong)
            self.assertEqual(response.status_code, 403, response.text)
            self.assertEqual(response.json()['detail'], 'Password is incorrect')
        self.assertEqual(self.client.get('/api/companies', headers=self.headers).status_code, 200)

    def test_requires_a_signed_in_user(self):
        self.assertEqual(self.check(self.password, headers={}).status_code, 401)

    def test_repeated_guesses_are_throttled(self):
        statuses = [self.check('guess-%d' % attempt).status_code for attempt in range(15)]
        self.assertEqual(statuses[0], 403)
        self.assertIn(429, statuses)
        # Even the right password is refused while the limit is active.
        self.assertEqual(self.check(self.password).status_code, 429)


if __name__ == '__main__':
    unittest.main()
