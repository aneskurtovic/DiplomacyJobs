from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class SwedenSourceMigrationTests(TransactionTestCase):
    migrate_from = ("board", "0043_candidateprofile_candidatedigest_candidatefeedback_and_more")
    migrate_to = ("board", "0044_sweden_beta_api_source")
    old_url = "https://www.swedenabroad.se/en/embassies/bosnia-and-herzegovina-sarajevo/current/news2/"
    new_url = "https://beta-api.swedenabroad.se/en/embassies/bosnia-and-herzegovina-sarajevo/current/news2/"

    def test_source_identity_and_job_history_survive_url_switch(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps

        Organization = old_apps.get_model("board", "Organization")
        Source = old_apps.get_model("board", "Source")
        Job = old_apps.get_model("board", "Job")

        organization = Organization.objects.create(name="Kingdom of Sweden", kind="embassy")
        source = Source.objects.create(
            organization=organization,
            url=self.old_url,
            adapter="generic",
            enabled=True,
            status="failing",
            consecutive_failures=3,
            adapter_config={"allow_empty": True},
        )
        job = Job.objects.create(
            source=source,
            canonical_url=self.old_url + "example-job/",
            title="National Programme Officer",
            content_hash="sweden-history",
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        new_apps = executor.loader.project_state([self.migrate_to]).apps
        MigratedSource = new_apps.get_model("board", "Source")
        MigratedJob = new_apps.get_model("board", "Job")

        migrated_source = MigratedSource.objects.get(pk=source.pk)
        migrated_job = MigratedJob.objects.get(pk=job.pk)
        self.assertEqual(migrated_source.url, self.new_url)
        self.assertEqual(migrated_source.enabled, True)
        self.assertEqual(migrated_source.status, "failing")
        self.assertEqual(migrated_source.consecutive_failures, 3)
        self.assertEqual(migrated_source.adapter_config, {"allow_empty": True})
        self.assertEqual(migrated_job.source_id, source.pk)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()
