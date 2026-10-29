import io
from unittest.mock import patch
from unittest.mock import Mock

import httpx

from django.core.management import call_command
from django.test import TestCase
from django.test import SimpleTestCase
from django.utils import timezone

from board.models import Organization, ScrapeRun, Source
from board.ingest import request


class RequestRetryTests(SimpleTestCase):
    @patch('board.ingest.time.sleep')
    def test_get_retries_transient_failure_once(self, sleep):
        client = Mock()
        client.get.side_effect = [httpx.ReadTimeout('slow upstream'), httpx.Response(200)]
        self.assertEqual(request(client, 'get', 'https://example.org').status_code, 200)
        self.assertEqual(client.get.call_count, 2)
        sleep.assert_called_once_with(1)

    @patch('board.ingest.time.sleep')
    def test_post_and_challenge_are_not_retried(self, sleep):
        client = Mock()
        client.post.side_effect = httpx.ReadTimeout('slow upstream')
        with self.assertRaises(httpx.ReadTimeout):
            request(client, 'post', 'https://example.org')
        client.post.assert_called_once()
        for status in (202, 403, 429):
            client.get.reset_mock()
            client.get.return_value = httpx.Response(status)
            self.assertEqual(request(client, 'get', 'https://example.org').status_code, status)
            client.get.assert_called_once()
        sleep.assert_not_called()

    @patch('board.ingest.time.sleep')
    def test_gateway_failure_is_bounded(self, sleep):
        client = Mock(get=Mock(side_effect=[httpx.Response(503), httpx.Response(503)]))
        self.assertEqual(request(client, 'get', 'https://example.org').status_code, 503)
        self.assertEqual(client.get.call_count, 2)


class ScrapeOperationsTests(TestCase):
    def setUp(self):
        self.source = Source.objects.create(
            organization=Organization.objects.create(name="Test mission", kind="embassy"),
            url="https://mission.example/jobs", adapter="generic", enabled=True,
            last_success_at=timezone.now(),
        )

    def test_health_detects_three_failures_before_staleness_and_recovers(self):
        for failures, expected in [(0, 200), (1, 200), (2, 200), (3, 503), (0, 200)]:
            Source.objects.filter(pk=self.source.pk).update(consecutive_failures=failures)
            with self.subTest(failures=failures):
                response = self.client.get('/health/scrape/')
                self.assertEqual(response.status_code, expected)
                if expected == 503:
                    self.assertIn(b'consecutive failures', response.content)
        self.assertEqual(self.client.get('/health/').status_code, 200)

    def test_disabled_source_failures_do_not_page(self):
        Source.objects.filter(pk=self.source.pk).update(enabled=False, consecutive_failures=10)
        self.assertEqual(self.client.get('/health/scrape/').status_code, 200)

    def test_expected_failure_is_logged_and_summarized_without_error_payload(self):
        result = ScrapeRun(source=self.source, success=False, error='ReliefWeb feed unusable: HTTP 202, secret-payload')
        with patch('board.management.commands.scrape_jobs.ingest_source', return_value=result), \
             patch('board.management.commands.scrape_jobs.expire_jobs'), \
             patch('board.management.commands.scrape_jobs.reconcile_aggregator_duplicates', return_value=0), \
             self.assertLogs('board.management.commands.scrape_jobs', level='INFO') as logs:
            call_command('scrape_jobs', stdout=io.StringIO())
        output = '\n'.join(logs.output)
        self.assertIn(f'source_id={self.source.pk} adapter=generic category=upstream_block', output)
        self.assertIn('scrape_summary succeeded=0 failed=1 skipped=0', output)
        self.assertNotIn('secret-payload', output)
