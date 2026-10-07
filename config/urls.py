from django.conf.urls.i18n import i18n_patterns
from django.contrib import admin
from django.urls import path
from board import views
from board import editor
from board.feeds import JobsFeed

urlpatterns = [
    path("feed/", JobsFeed(), name="feed"),
    path("robots.txt", views.robots, name="robots"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
    path("health/", views.health, name="health"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("health/scrape/", views.scrape_health, name="scrape_health"),
    path("admin/", admin.site.urls),
    path("editor/", editor.dashboard, name="editor"),
    path("editor/jobs/<int:pk>/", editor.review_job, name="editor_job"),
]
urlpatterns += i18n_patterns(
    path("", views.jobs, name="jobs"),
    path("jobs/<int:pk>/", views.job_detail, name="job_short"),
    path("jobs/<int:pk>/report/", views.report, name="job_report"),
    path("jobs/<int:pk>/share.png", views.job_share_image, name="job_share_image"),
    path("jobs/<int:pk>/<slug:slug>/", views.job_detail, name="job"),
    path("report/", views.report, name="report"),
    path("sources/", views.sources, name="sources"),
    path("sources/<int:pk>/", views.organization, name="organization_short"),
    path("sources/<int:pk>/<slug:slug>/", views.organization, name="organization"),
    path("offline/", views.offline, name="offline"),
    prefix_default_language=False,
)
