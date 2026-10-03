import ssl

from django.test import SimpleTestCase

from board.ingest import BROWSER_USER_AGENT, INTERMEDIATES, USER_AGENT, open_client, tls_context
from board.models import Source


class TlsContextTests(SimpleTestCase):
    def test_default_context_verifies(self):
        context = tls_context(Source(url="https://example.org/jobs", adapter_config={}))
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_stored_intermediates_never_end_a_chain(self):
        # Each stored intermediate must chain to a root in the trust store; partial chains stay off.
        for pem in INTERMEDIATES.glob("*.pem"):
            host = pem.stem
            with self.subTest(host=host):
                context = tls_context(Source(url=f"https://{host}/", adapter_config={"intermediates": True}))
                self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                self.assertTrue(context.check_hostname)
                self.assertFalse(context.verify_flags & getattr(ssl, "VERIFY_X509_PARTIAL_CHAIN", 0))
                self.assertNotIn("BEGIN CERTIFICATE", pem.read_text("ascii").split("END CERTIFICATE")[-1])

    def test_missing_intermediate_file_fails_loudly(self):
        with self.assertRaises(FileNotFoundError):
            tls_context(Source(url="https://not-stored.example/", adapter_config={"intermediates": True}))

    def test_browser_user_agent_is_opt_in(self):
        with open_client(Source(url="https://example.org/", adapter_config={})) as client:
            self.assertEqual(client.headers["User-Agent"], USER_AGENT)
        with open_client(Source(url="https://example.org/", adapter_config={"browser_user_agent": True})) as client:
            self.assertEqual(client.headers["User-Agent"], BROWSER_USER_AGENT)
