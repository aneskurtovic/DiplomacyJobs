import json
from pathlib import Path

from django.test import TestCase, override_settings
from PIL import Image

PLAIN_STATIC = override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
ICONS = Path(__file__).resolve().parent / "static/board/icons"


@PLAIN_STATIC
class InstallableSiteTests(TestCase):
    def test_manifest_describes_standalone_app(self):
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")
        self.assertEqual(response["Cache-Control"], "max-age=86400")
        self.assertIn("međunarodnim", response.content.decode())
        data = json.loads(response.content)
        self.assertEqual(data["display"], "standalone")
        self.assertEqual([(icon["sizes"], icon["purpose"]) for icon in data["icons"]], [("192x192", "any"), ("512x512", "any"), ("512x512", "maskable")])
        for icon in data["icons"]:
            path = ICONS / Path(icon["src"]).name
            self.assertTrue(path.exists())
            self.assertEqual(Image.open(path).size, tuple(int(side) for side in icon["sizes"].split("x")))

    def test_apple_touch_icon_is_opaque(self):
        with Image.open(ICONS / "apple-touch-icon.png") as image:
            self.assertEqual(image.size, (180, 180))
            self.assertNotIn("A", image.getbands())

    def test_service_worker_precaches_offline_pages(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/javascript"))
        self.assertEqual(response["Cache-Control"], "no-cache")
        body = response.content.decode()
        self.assertIn("/offline/", body)
        self.assertIn("dj-pages-v1", body)

    def test_offline_pages_are_not_indexed(self):
        response = self.client.get("/offline/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "noindex")
        response = self.client.get("/en/offline/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "noindex")
        self.assertContains(response, "You are offline")

    def test_home_page_links_manifest_and_registers_worker(self):
        response = self.client.get("/")
        self.assertContains(response, 'rel="manifest"')
        self.assertContains(response, "register-sw.js")
