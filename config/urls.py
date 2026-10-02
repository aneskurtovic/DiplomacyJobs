from django.contrib import admin
from django.urls import path
from board import views
from board.feeds import JobsFeed

urlpatterns = [
    path("", views.jobs, name="jobs"),
    path("sources/", views.sources, name="sources"),
    path("feed/", JobsFeed(), name="feed"),
    path("health/", views.health, name="health"),
    path("health/scrape/", views.scrape_health, name="scrape_health"),
    path("admin/", admin.site.urls),
]
