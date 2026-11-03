import unittest
from ocr_transport import validate_ocr_base_url


class OcrTransportConfigurationTest(unittest.TestCase):
    def test_https_and_explicit_loopback_http_are_supported(self):
        for url in ('https://synthetic-provider.invalid/v1', 'https://synthetic-provider.invalid/api/v1/',
                    'http://localhost:8008/v1', 'http://127.0.0.1:8008/v1', 'http://127.1.2.3:8008/v1', 'http://[::1]:8008/v1'):
            self.assertEqual(validate_ocr_base_url(url), url.rstrip('/'))

    def test_non_loopback_http_is_rejected_without_host_resolution(self):
        for url in ('http://synthetic-provider.invalid/v1', 'http://192.0.2.1:8088/v1',
                    'http://192.168.1.2/v1', 'http://localhost.example.invalid/v1', 'http://[2001:db8::1]/v1'):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, 'HTTPS outside loopback'):
                validate_ocr_base_url(url)

    def test_invalid_endpoints_do_not_echo_credentials(self):
        for url in ('ftp://localhost/v1', 'https://example.invalid/v2', 'https://example.invalid/v1?key=private',
                    'https://example.invalid/v1#fragment', 'https://synthetic-key@example.invalid/v1',
                    'http://localhost:99999/v1', 'http://[broken/v1', ' https://example.invalid/v1'):
            with self.subTest(url=url):
                try:
                    validate_ocr_base_url(url)
                except ValueError as error:
                    self.assertNotIn('synthetic-key', str(error))
                    self.assertNotIn('private', str(error))
                else:
                    self.fail('Invalid OCR configuration accepted')

    def test_external_http_requires_exact_explicit_boolean_opt_in(self):
        url = 'http://192.0.2.1:8088/v1'
        self.assertEqual(validate_ocr_base_url(url, allow_insecure_http=True), url)
        for flag in (False, None, '1', 'true', 1):
            with self.subTest(flag=flag), self.assertRaises(ValueError):
                validate_ocr_base_url(url, allow_insecure_http=flag)

    def test_opt_in_does_not_bypass_endpoint_validation_or_downgrade_https(self):
        self.assertEqual(validate_ocr_base_url('https://synthetic.invalid/v1', allow_insecure_http=True),
                         'https://synthetic.invalid/v1')
        for url in ('ftp://localhost/v1', 'http://secret@example.invalid/v1',
                    'http://example.invalid/v1?key=secret', 'http://example.invalid:99999/v1'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_ocr_base_url(url, allow_insecure_http=True)
