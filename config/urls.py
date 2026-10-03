from django.contrib import admin
from django.urls import path
from board import views
from board.feeds import JobsFeed

urlpatterns = [
    path("", views.jobs, name="jobs"),
    path("jobs/<int:pk>/", views.job_detail, name="job_short"),
    path("jobs/<int:pk>/report/", views.report, name="job_report"),
    path("jobs/<int:pk>/<slug:slug>/", views.job_detail, name="job"),
    path("report/", views.report, name="report"),
    path("sources/", views.sources, name="sources"),
    path("feed/", JobsFeed(), name="feed"),
    path("robots.txt", views.robots, name="robots"),
    path("sitemap.xml", views.sitemap, name="sitemap"),
    path("health/", views.health, name="health"),
    path("health/scrape/", views.scrape_health, name="scrape_health"),
    path("admin/", admin.site.urls),
]
